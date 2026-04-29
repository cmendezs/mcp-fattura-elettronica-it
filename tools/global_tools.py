"""
MCP tools for global FatturaPA operations: generation, XSD validation, parsing,
JSON export, Partita IVA validation, SDI filename generation, and ritenuta d'acconto.
"""

from __future__ import annotations

import json
import os
import re
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Annotated, Optional

from fastmcp import FastMCP
from pydantic import Field

from mcp_einvoicing_core.logging_utils import get_logger
from mcp_einvoicing_core.xml_utils import filter_empty_values

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# XSD schema path resolution
# ---------------------------------------------------------------------------

_XSD_PATH: Optional[Path] = None


def _get_xsd_path() -> Path:
    """Resolve the XSD schema path from env var or default location."""
    global _XSD_PATH
    if _XSD_PATH is None:
        env_path = os.getenv("FATTURA_XSD_PATH")
        if env_path:
            _XSD_PATH = Path(env_path)
        else:
            _XSD_PATH = Path(__file__).parent.parent / "schemas" / "FatturaPA_v1.6.1.xsd"
    return _XSD_PATH


# ---------------------------------------------------------------------------
# FatturaPA namespace
# ---------------------------------------------------------------------------

FATTURA_NS = "http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2"

# ---------------------------------------------------------------------------
# Ritenuta d'acconto reference table
# ---------------------------------------------------------------------------

TIPO_RITENUTA: dict[str, dict] = {
    "RT01": {
        "description": "Persone fisiche — lavoro autonomo occasionale",
        "rate": Decimal("0.20"),
        "legal_ref": "Art. 25 DPR 600/73",
    },
    "RT02": {
        "description": "Persone fisiche — lavoro autonomo professionale",
        "rate": Decimal("0.20"),
        "legal_ref": "Art. 25 DPR 600/73",
    },
    "RT03": {
        "description": "Persone giuridiche — provvigioni agenti",
        "rate": Decimal("0.2320"),
        "legal_ref": "Art. 25-bis DPR 600/73",
    },
    "RT04": {
        "description": "Persone fisiche — provvigioni agenti",
        "rate": Decimal("0.2320"),
        "legal_ref": "Art. 25-bis DPR 600/73",
    },
    "RT05": {
        "description": "Condominio — corrispettivi lavori di cui all'art. 25-ter",
        "rate": Decimal("0.04"),
        "legal_ref": "Art. 25-ter DPR 600/73",
    },
    "RT06": {
        "description": "Persone fisiche — redditi di lavoro dipendente",
        "rate": Decimal("0.30"),
        "legal_ref": "Art. 23 DPR 600/73",
    },
}


def register_global_tools(mcp: FastMCP) -> None:
    """Register the 7 global FatturaPA tools on the FastMCP instance."""

    @mcp.tool()
    def generate_fattura_xml(
        dati_trasmissione: Annotated[
            dict,
            Field(
                description=(
                    "DatiTrasmissione block from build_transmission_header(). "
                    "Must contain IdTrasmittente, ProgressivoInvio, FormatoTrasmissione, "
                    "and CodiceDestinatario."
                )
            ),
        ],
        cedente_prestatore: Annotated[
            dict,
            Field(
                description=(
                    "CedentePrestatore block from validate_cedente_prestatore(). "
                    "Contains seller's tax ID, name, address, and fiscal regime."
                )
            ),
        ],
        cessionario_committente: Annotated[
            dict,
            Field(
                description=(
                    "CessionarioCommittente block from validate_cessionario(). "
                    "Contains buyer's tax ID, name, and address."
                )
            ),
        ],
        dati_generali: Annotated[
            dict,
            Field(
                description=(
                    "DatiGenerali block from build_dati_generali(). "
                    "Contains document type, date, number, and currency."
                )
            ),
        ],
        dettaglio_linee: Annotated[
            list,
            Field(
                description=(
                    "List of DettaglioLinee dicts from add_linea_dettaglio(). "
                    "Each entry must have NumeroLinea, Descrizione, PrezzoUnitario, "
                    "PrezzoTotale, and AliquotaIVA."
                )
            ),
        ],
        dati_riepilogo: Annotated[
            list,
            Field(
                description=(
                    "List of DatiRiepilogo dicts from compute_totali(). "
                    "Contains VAT summary grouped by AliquotaIVA."
                )
            ),
        ],
        dati_pagamento: Annotated[
            Optional[dict],
            Field(
                default=None,
                description="DatiPagamento block from build_dati_pagamento(). Optional.",
            ),
        ] = None,
        allegati: Annotated[
            Optional[list],
            Field(
                default=None,
                description="List of Allegati dicts from add_allegato(). Optional.",
            ),
        ] = None,
        dati_ritenuta: Annotated[
            Optional[dict],
            Field(
                default=None,
                description=(
                    "DatiRitenuta block from check_ritenuta_acconto(). "
                    "Required for professional invoices with withholding tax (ritenuta d'acconto)."
                ),
            ),
        ] = None,
    ) -> dict:
        """Assemble a complete FatturaPA v1.6.1 XML document from all prepared blocks.

        Use this as step 10 in the invoice generation workflow — the final assembly step.
        All required blocks must come from their respective builder/validator tools;
        pass the full dict returned by each tool (the function unwraps the top-level key).

        Required: dati_trasmissione, cedente_prestatore, cessionario_committente,
        dati_generali, dettaglio_linee (list), dati_riepilogo (list from compute_totali()).
        Optional: dati_pagamento, allegati (list), dati_ritenuta.

        Does NOT validate against the XSD schema — call validate_fattura_xsd() (step 11)
        on the returned 'xml' string immediately after to confirm conformance.

        On success returns {'xml': str, 'filename': str, 'formato_trasmissione': str, 'length_bytes': int}.
        On unexpected error returns {'error': '<reason>'}.
        """
        try:
            dt = dati_trasmissione.get("DatiTrasmissione", dati_trasmissione)
            cp = cedente_prestatore.get("CedentePrestatore", cedente_prestatore)
            cc = cessionario_committente.get("CessionarioCommittente", cessionario_committente)
            dg = dati_generali.get("DatiGenerali", dati_generali)

            formato = dt.get("FormatoTrasmissione", "FPR12")
            id_trasmittente = dt.get("IdTrasmittente", {})
            id_paese_tx = id_trasmittente.get("IdPaese", "IT")
            id_codice_tx = id_trasmittente.get("IdCodice", "")
            progressivo = dt.get("ProgressivoInvio", "00001")
            codice_dest = dt.get("CodiceDestinatario", "0000000")
            pec_dest = dt.get("PECDestinatario", "")

            cp_dati = cp.get("DatiAnagrafici", {})
            cp_id = cp_dati.get("IdFiscaleIVA", {})
            cp_anagrafica = cp_dati.get("Anagrafica", {})
            cp_regime = cp_dati.get("RegimeFiscale", "RF01")
            cp_sede = cp.get("Sede", {})

            cc_dati = cc.get("DatiAnagrafici", {})
            cc_id = cc_dati.get("IdFiscaleIVA", {})
            cc_cf = cc_dati.get("CodiceFiscale", "")
            cc_anagrafica = cc_dati.get("Anagrafica", {})
            cc_sede = cc.get("Sede", {})

            dg_doc = dg.get("DatiGeneraliDocumento", dg)
            tipo_doc = dg_doc.get("TipoDocumento", "TD01")
            divisa = dg_doc.get("Divisa", "EUR")
            data_doc = dg_doc.get("Data", "")
            numero_doc = dg_doc.get("Numero", "")
            causale = dg_doc.get("Causale", "")

            def _seller_name(anagrafica: dict) -> str:
                if "Denominazione" in anagrafica:
                    return f"<Denominazione>{anagrafica['Denominazione']}</Denominazione>"
                return (
                    f"<Nome>{anagrafica.get('Nome', '')}</Nome>"
                    f"<Cognome>{anagrafica.get('Cognome', '')}</Cognome>"
                )

            def _buyer_id(cc_id: dict, cc_cf: str) -> str:
                parts = []
                if cc_id:
                    parts.append(
                        f"<IdFiscaleIVA>"
                        f"<IdPaese>{cc_id.get('IdPaese', 'IT')}</IdPaese>"
                        f"<IdCodice>{cc_id.get('IdCodice', '')}</IdCodice>"
                        f"</IdFiscaleIVA>"
                    )
                if cc_cf:
                    parts.append(f"<CodiceFiscale>{cc_cf}</CodiceFiscale>")
                return "".join(parts)

            def _linee_xml(linee: list) -> str:
                parts = []
                for linea in linee:
                    ld = linea.get("DettaglioLinee", linea)
                    qta = f"<Quantita>{ld['Quantita']}</Quantita>" if "Quantita" in ld else ""
                    um = f"<UnitaMisura>{ld['UnitaMisura']}</UnitaMisura>" if "UnitaMisura" in ld else ""
                    nat = f"<Natura>{ld['Natura']}</Natura>" if "Natura" in ld else ""
                    rit = f"<Ritenuta>{ld['Ritenuta']}</Ritenuta>" if "Ritenuta" in ld else ""
                    parts.append(
                        f"<DettaglioLinee>"
                        f"<NumeroLinea>{ld['NumeroLinea']}</NumeroLinea>"
                        f"<Descrizione>{ld['Descrizione']}</Descrizione>"
                        f"{qta}{um}"
                        f"<PrezzoUnitario>{ld['PrezzoUnitario']}</PrezzoUnitario>"
                        f"<PrezzoTotale>{ld['PrezzoTotale']}</PrezzoTotale>"
                        f"<AliquotaIVA>{ld['AliquotaIVA']}</AliquotaIVA>"
                        f"{nat}{rit}"
                        f"</DettaglioLinee>"
                    )
                return "".join(parts)

            def _riepilogo_xml(riepilogo: list) -> str:
                parts = []
                for r in riepilogo:
                    nat = f"<Natura>{r['Natura']}</Natura>" if "Natura" in r else ""
                    parts.append(
                        f"<DatiRiepilogo>"
                        f"<AliquotaIVA>{r['AliquotaIVA']}</AliquotaIVA>"
                        f"{nat}"
                        f"<Imponibile>{r['Imponibile']}</Imponibile>"
                        f"<Imposta>{r['Imposta']}</Imposta>"
                        f"<EsigibilitaIVA>{r.get('EsigibilitaIVA', 'I')}</EsigibilitaIVA>"
                        f"</DatiRiepilogo>"
                    )
                return "".join(parts)

            def _pagamento_xml(pagamento: Optional[dict]) -> str:
                if not pagamento:
                    return ""
                p = pagamento.get("DatiPagamento", pagamento)
                dp = p.get("DettaglioPagamento", {})
                scad = f"<DataScadenzaPagamento>{dp['DataScadenzaPagamento']}</DataScadenzaPagamento>" if "DataScadenzaPagamento" in dp else ""
                iban = f"<IBAN>{dp['IBAN']}</IBAN>" if "IBAN" in dp else ""
                banca = f"<IstitutoFinanziario>{dp['IstitutoFinanziario']}</IstitutoFinanziario>" if "IstitutoFinanziario" in dp else ""
                return (
                    f"<DatiPagamento>"
                    f"<CondizioniPagamento>{p['CondizioniPagamento']}</CondizioniPagamento>"
                    f"<DettaglioPagamento>"
                    f"<ModalitaPagamento>{dp['ModalitaPagamento']}</ModalitaPagamento>"
                    f"{scad}"
                    f"<ImportoPagamento>{dp['ImportoPagamento']}</ImportoPagamento>"
                    f"{iban}{banca}"
                    f"</DettaglioPagamento>"
                    f"</DatiPagamento>"
                )

            def _allegati_xml(allegati_list: Optional[list]) -> str:
                if not allegati_list:
                    return ""
                parts = []
                for a in allegati_list:
                    entry = a.get("Allegati", a)
                    fmt = f"<FormatoAllegato>{entry['FormatoAllegato']}</FormatoAllegato>" if "FormatoAllegato" in entry else ""
                    desc = f"<DescrizioneAllegato>{entry['DescrizioneAllegato']}</DescrizioneAllegato>" if "DescrizioneAllegato" in entry else ""
                    parts.append(
                        f"<Allegati>"
                        f"<NomeAllegato>{entry['NomeAllegato']}</NomeAllegato>"
                        f"{fmt}{desc}"
                        f"<Attachment>{entry['Attachment']}</Attachment>"
                        f"</Allegati>"
                    )
                return "".join(parts)

            def _ritenuta_xml(ritenuta: Optional[dict]) -> str:
                if not ritenuta:
                    return ""
                r = ritenuta.get("DatiRitenuta", ritenuta)
                return (
                    f"<DatiRitenuta>"
                    f"<TipoRitenuta>{r['TipoRitenuta']}</TipoRitenuta>"
                    f"<ImportoRitenuta>{r['ImportoRitenuta']}</ImportoRitenuta>"
                    f"<AliquotaRitenuta>{r['AliquotaRitenuta']}</AliquotaRitenuta>"
                    f"<CausalePagamento>{r['CausalePagamento']}</CausalePagamento>"
                    f"</DatiRitenuta>"
                )

            pec_xml = f"<PECDestinatario>{pec_dest}</PECDestinatario>" if pec_dest else ""
            causale_xml = f"<Causale>{causale}</Causale>" if causale else ""

            xml = (
                f'<?xml version="1.0" encoding="UTF-8"?>'
                f'<p:FatturaElettronica versione="{formato}" '
                f'xmlns:p="{FATTURA_NS}" '
                f'xmlns:ds="http://www.w3.org/2000/09/xmldsig#" '
                f'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
                f"<FatturaElettronicaHeader>"
                f"<DatiTrasmissione>"
                f"<IdTrasmittente>"
                f"<IdPaese>{id_paese_tx}</IdPaese>"
                f"<IdCodice>{id_codice_tx}</IdCodice>"
                f"</IdTrasmittente>"
                f"<ProgressivoInvio>{progressivo}</ProgressivoInvio>"
                f"<FormatoTrasmissione>{formato}</FormatoTrasmissione>"
                f"<CodiceDestinatario>{codice_dest}</CodiceDestinatario>"
                f"{pec_xml}"
                f"</DatiTrasmissione>"
                f"<CedentePrestatore>"
                f"<DatiAnagrafici>"
                f"<IdFiscaleIVA>"
                f"<IdPaese>{cp_id.get('IdPaese', 'IT')}</IdPaese>"
                f"<IdCodice>{cp_id.get('IdCodice', '')}</IdCodice>"
                f"</IdFiscaleIVA>"
                f"<Anagrafica>{_seller_name(cp_anagrafica)}</Anagrafica>"
                f"<RegimeFiscale>{cp_regime}</RegimeFiscale>"
                f"</DatiAnagrafici>"
                f"<Sede>"
                f"<Indirizzo>{cp_sede.get('Indirizzo', '')}</Indirizzo>"
                f"<CAP>{cp_sede.get('CAP', '')}</CAP>"
                f"<Comune>{cp_sede.get('Comune', '')}</Comune>"
                f"<Nazione>{cp_sede.get('Nazione', 'IT')}</Nazione>"
                f"</Sede>"
                f"</CedentePrestatore>"
                f"<CessionarioCommittente>"
                f"<DatiAnagrafici>"
                f"{_buyer_id(cc_id, cc_cf)}"
                f"<Anagrafica>{_seller_name(cc_anagrafica)}</Anagrafica>"
                f"</DatiAnagrafici>"
                f"<Sede>"
                f"<Indirizzo>{cc_sede.get('Indirizzo', '')}</Indirizzo>"
                f"<CAP>{cc_sede.get('CAP', '')}</CAP>"
                f"<Comune>{cc_sede.get('Comune', '')}</Comune>"
                f"<Nazione>{cc_sede.get('Nazione', 'IT')}</Nazione>"
                f"</Sede>"
                f"</CessionarioCommittente>"
                f"</FatturaElettronicaHeader>"
                f"<FatturaElettronicaBody>"
                f"<DatiGenerali>"
                f"<DatiGeneraliDocumento>"
                f"<TipoDocumento>{tipo_doc}</TipoDocumento>"
                f"<Divisa>{divisa}</Divisa>"
                f"<Data>{data_doc}</Data>"
                f"<Numero>{numero_doc}</Numero>"
                f"{causale_xml}"
                f"{_ritenuta_xml(dati_ritenuta)}"
                f"</DatiGeneraliDocumento>"
                f"</DatiGenerali>"
                f"<DatiBeniServizi>"
                f"{_linee_xml(dettaglio_linee)}"
                f"{_riepilogo_xml(dati_riepilogo)}"
                f"</DatiBeniServizi>"
                f"{_pagamento_xml(dati_pagamento)}"
                f"{_allegati_xml(allegati)}"
                f"</FatturaElettronicaBody>"
                f"</p:FatturaElettronica>"
            )

            # Generate SDI filename from seller Partita IVA
            piva = cp_id.get("IdCodice", "00000000000")
            filename = f"IT{piva}_{progressivo}.xml"

            return {
                "xml": xml,
                "filename": filename,
                "formato_trasmissione": formato,
                "length_bytes": len(xml.encode("utf-8")),
            }

        except Exception as exc:
            logger.exception("Error generating FatturaPA XML")
            return {"error": f"XML generation failed: {exc}"}

    @mcp.tool()
    def validate_fattura_xsd(
        xml_string: Annotated[
            str,
            Field(
                description=(
                    "Complete FatturaPA XML string to validate. "
                    "Must include the FatturaElettronica root element with the correct "
                    "namespace (http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2)."
                )
            ),
        ],
    ) -> dict:
        """Validate a FatturaPA XML string against the official Agenzia delle Entrate XSD v1.6.1.

        Use this as step 11 — always call immediately after generate_fattura_xml() before
        storing or transmitting the document. Also use to verify third-party invoices received
        from suppliers.

        Requires lxml to be installed and the bundled XSD schema file to be present (or
        FATTURA_XSD_PATH env var to point to it). Validates namespace, element structure,
        data types, and cardinality constraints.

        On success returns {'valid': true, 'formato_trasmissione': 'FPR12'|'FPA12', 'errors': []}.
        On failure returns {'valid': false, 'errors': ['<lxml error message>', ...]}.
        On setup error (missing lxml or XSD file) returns {'error': '<reason>'}.
        """
        try:
            from lxml import etree
        except ImportError:
            return {"error": "lxml is not installed. Run: pip install lxml"}

        xsd_path = _get_xsd_path()
        if not xsd_path.exists():
            return {"error": f"XSD schema not found at '{xsd_path}'. Check FATTURA_XSD_PATH."}

        try:
            xml_bytes = xml_string.encode("utf-8") if isinstance(xml_string, str) else xml_string
            xml_doc = etree.fromstring(xml_bytes)
        except etree.XMLSyntaxError as exc:
            return {"valid": False, "errors": [f"XML parse error: {exc}"]}

        try:
            # Build a resolver that maps the xmldsig namespace to the local schema file
            # so lxml can load the XSD without network access.
            schemas_dir = xsd_path.parent
            xmldsig_path = schemas_dir / "xmldsig-core-schema.xsd"

            parser = etree.XMLParser()
            if xmldsig_path.exists():
                class _LocalResolver(etree.Resolver):
                    def resolve(self, url, id, context):
                        if "xmldsig" in url or "xmldsig-core" in url:
                            return self.resolve_filename(str(xmldsig_path), context)
                        return None
                parser.resolvers.add(_LocalResolver())

            xsd_doc = etree.parse(str(xsd_path), parser)
            schema = etree.XMLSchema(xsd_doc)
        except Exception as exc:
            return {"error": f"Failed to load XSD schema: {exc}"}

        is_valid = schema.validate(xml_doc)
        if is_valid:
            versione = xml_doc.get("versione", "unknown")
            return {"valid": True, "formato_trasmissione": versione, "errors": []}
        else:
            errors = [str(e) for e in schema.error_log]
            return {"valid": False, "errors": errors}

    @mcp.tool()
    def parse_fattura_xml(
        xml_string: Annotated[
            str,
            Field(
                description=(
                    "FatturaPA XML string to parse. "
                    "Accepts both single-invoice (FPR12) and PA-addressed (FPA12) formats."
                )
            ),
        ],
    ) -> dict:
        """Parse a FatturaPA XML string into a structured Python dict.

        Use this to inspect or process invoices received from counterparties, or to
        verify the output of generate_fattura_xml(). Accepts both FPR12 (B2B) and
        FPA12 (PA) formats. The result can be passed directly to export_to_json().

        Extracts: versione, transmission data, seller/buyer identity and address,
        document type/date/number/causale, all DettaglioLinee, DatiRiepilogo, and
        DatiPagamento if present. Fields not found in the XML are returned as null.

        On success returns {'versione': str, 'header': {...}, 'body': {...}}.
        On XML parse error returns {'error': 'XML parse error: <detail>'}.
        On missing lxml returns {'error': 'lxml is not installed...'}.
        """
        try:
            from lxml import etree
        except ImportError:
            return {"error": "lxml is not installed. Run: pip install lxml"}

        try:
            xml_bytes = xml_string.encode("utf-8") if isinstance(xml_string, str) else xml_string
            root = etree.fromstring(xml_bytes)
        except etree.XMLSyntaxError as exc:
            return {"error": f"XML parse error: {exc}"}

        ns = {"p": FATTURA_NS}

        def _text(element, xpath: str) -> Optional[str]:
            nodes = element.xpath(xpath, namespaces=ns)
            return nodes[0].text if nodes else None

        def _find(element, xpath: str):
            nodes = element.xpath(xpath, namespaces=ns)
            return nodes[0] if nodes else None

        versione = root.get("versione", "unknown")

        _h = _find(root, "FatturaElettronicaHeader")
        header = _h if _h is not None else _find(root, "p:FatturaElettronicaHeader")
        _b = _find(root, "FatturaElettronicaBody")
        body = _b if _b is not None else _find(root, "p:FatturaElettronicaBody")

        # Fallback: search without namespace
        if header is None:
            header = root.find("FatturaElettronicaHeader")
        if body is None:
            body = root.find("FatturaElettronicaBody")

        def _txt(el, path: str) -> Optional[str]:
            if el is None:
                return None
            node = el.find(path)
            return node.text if node is not None else None

        result: dict = {
            "versione": versione,
            "header": {},
            "body": {},
        }

        if header is not None:
            dt = header.find("DatiTrasmissione")
            cp = header.find("CedentePrestatore")
            cc = header.find("CessionarioCommittente")

            result["header"]["dati_trasmissione"] = {
                "id_paese": _txt(dt, "IdTrasmittente/IdPaese") if dt is not None else None,
                "id_codice": _txt(dt, "IdTrasmittente/IdCodice") if dt is not None else None,
                "progressivo_invio": _txt(dt, "ProgressivoInvio") if dt is not None else None,
                "formato_trasmissione": _txt(dt, "FormatoTrasmissione") if dt is not None else None,
                "codice_destinatario": _txt(dt, "CodiceDestinatario") if dt is not None else None,
                "pec_destinatario": _txt(dt, "PECDestinatario") if dt is not None else None,
            }

            if cp is not None:
                cp_an = cp.find("DatiAnagrafici")
                result["header"]["cedente_prestatore"] = {
                    "id_paese": _txt(cp_an, "IdFiscaleIVA/IdPaese") if cp_an is not None else None,
                    "id_codice": _txt(cp_an, "IdFiscaleIVA/IdCodice") if cp_an is not None else None,
                    "denominazione": _txt(cp_an, "Anagrafica/Denominazione") if cp_an is not None else None,
                    "nome": _txt(cp_an, "Anagrafica/Nome") if cp_an is not None else None,
                    "cognome": _txt(cp_an, "Anagrafica/Cognome") if cp_an is not None else None,
                    "regime_fiscale": _txt(cp_an, "RegimeFiscale") if cp_an is not None else None,
                    "indirizzo": _txt(cp, "Sede/Indirizzo"),
                    "cap": _txt(cp, "Sede/CAP"),
                    "comune": _txt(cp, "Sede/Comune"),
                    "nazione": _txt(cp, "Sede/Nazione"),
                }

            if cc is not None:
                cc_an = cc.find("DatiAnagrafici")
                result["header"]["cessionario_committente"] = {
                    "id_paese": _txt(cc_an, "IdFiscaleIVA/IdPaese") if cc_an is not None else None,
                    "id_codice": _txt(cc_an, "IdFiscaleIVA/IdCodice") if cc_an is not None else None,
                    "codice_fiscale": _txt(cc_an, "CodiceFiscale") if cc_an is not None else None,
                    "denominazione": _txt(cc_an, "Anagrafica/Denominazione") if cc_an is not None else None,
                    "nome": _txt(cc_an, "Anagrafica/Nome") if cc_an is not None else None,
                    "cognome": _txt(cc_an, "Anagrafica/Cognome") if cc_an is not None else None,
                    "indirizzo": _txt(cc, "Sede/Indirizzo"),
                    "cap": _txt(cc, "Sede/CAP"),
                    "comune": _txt(cc, "Sede/Comune"),
                    "nazione": _txt(cc, "Sede/Nazione"),
                }

        if body is not None:
            dg = body.find("DatiGenerali/DatiGeneraliDocumento")
            result["body"]["dati_generali"] = {
                "tipo_documento": _txt(dg, "TipoDocumento") if dg is not None else None,
                "divisa": _txt(dg, "Divisa") if dg is not None else None,
                "data": _txt(dg, "Data") if dg is not None else None,
                "numero": _txt(dg, "Numero") if dg is not None else None,
                "causale": _txt(dg, "Causale") if dg is not None else None,
            }

            linee = []
            for linea in body.findall("DatiBeniServizi/DettaglioLinee"):
                linee.append({
                    "numero_linea": _txt(linea, "NumeroLinea"),
                    "descrizione": _txt(linea, "Descrizione"),
                    "quantita": _txt(linea, "Quantita"),
                    "prezzo_unitario": _txt(linea, "PrezzoUnitario"),
                    "prezzo_totale": _txt(linea, "PrezzoTotale"),
                    "aliquota_iva": _txt(linea, "AliquotaIVA"),
                    "natura": _txt(linea, "Natura"),
                })
            result["body"]["dettaglio_linee"] = linee

            riepilogo = []
            for r in body.findall("DatiBeniServizi/DatiRiepilogo"):
                riepilogo.append({
                    "aliquota_iva": _txt(r, "AliquotaIVA"),
                    "natura": _txt(r, "Natura"),
                    "imponibile": _txt(r, "Imponibile"),
                    "imposta": _txt(r, "Imposta"),
                    "esigibilita_iva": _txt(r, "EsigibilitaIVA"),
                })
            result["body"]["dati_riepilogo"] = riepilogo

            dp = body.find("DatiPagamento")
            if dp is not None:
                ddp = dp.find("DettaglioPagamento")
                result["body"]["dati_pagamento"] = {
                    "condizioni_pagamento": _txt(dp, "CondizioniPagamento"),
                    "modalita_pagamento": _txt(ddp, "ModalitaPagamento") if ddp is not None else None,
                    "importo_pagamento": _txt(ddp, "ImportoPagamento") if ddp is not None else None,
                    "data_scadenza": _txt(ddp, "DataScadenzaPagamento") if ddp is not None else None,
                    "iban": _txt(ddp, "IBAN") if ddp is not None else None,
                }

        return result

    @mcp.tool()
    def export_to_json(
        parsed_fattura: Annotated[
            dict,
            Field(
                description=(
                    "Parsed FatturaPA dict as returned by parse_fattura_xml(). "
                    "Will be serialised to a clean, indented JSON string."
                )
            ),
        ],
        indent: Annotated[
            int,
            Field(
                default=2,
                ge=0,
                le=8,
                description="JSON indentation level (0–8 spaces). Default 2.",
            ),
        ] = 2,
        include_empty: Annotated[
            bool,
            Field(
                default=False,
                description="Include fields with null/empty values in output. Default False.",
            ),
        ] = False,
    ) -> dict:
        """Serialize a parsed FatturaPA dict to a clean, indented JSON string.

        Call this after parse_fattura_xml() when you need a human-readable or
        machine-transferable representation of the invoice. By default, null/empty
        fields are omitted (include_empty=False) to reduce noise in the output.

        indent controls JSON indentation (0 = compact, 2 = standard readable, 4 = wide).
        include_empty=True retains all keys even when their value is null or empty string.

        Always succeeds. Returns {'json_string': str, 'size_chars': int}.
        """
        data = filter_empty_values(parsed_fattura) if not include_empty else parsed_fattura
        json_str = json.dumps(data, indent=indent, ensure_ascii=False)
        return {"json_string": json_str, "size_chars": len(json_str)}

    @mcp.tool()
    def validate_partita_iva_format(
        partita_iva: Annotated[
            str,
            Field(
                description=(
                    "Italian Partita IVA (VAT number) to validate. "
                    "Must be exactly 11 digits. Whitespace is stripped before validation."
                )
            ),
        ],
    ) -> dict:
        """Validate an Italian Partita IVA for format (11 digits) and modulo-10 checksum.

        Use this as step 1 in the invoice generation workflow before any other tool.
        Equivalent to validate_partita_iva() in header tools — use this standalone version
        when you only need the validation result without importing header tools.

        Strips whitespace, checks for exactly 11 digits, then applies the official
        Agenzia delle Entrate control algorithm to verify the check digit.

        On success returns {'valid': true, 'value': '<cleaned_piva>'}.
        On failure returns {'valid': false, 'value': '<input>', 'error': '<reason>'}.
        """
        piva = partita_iva.strip()

        if not re.match(r"^\d{11}$", piva):
            return {
                "valid": False,
                "value": piva,
                "error": "Partita IVA must be exactly 11 digits.",
            }

        total = 0
        for i, digit in enumerate(piva[:10]):
            d = int(digit)
            if i % 2 == 1:
                d *= 2
                if d > 9:
                    d -= 9
            total += d

        expected = (10 - (total % 10)) % 10
        actual = int(piva[10])

        if expected != actual:
            return {
                "valid": False,
                "value": piva,
                "error": f"Checksum mismatch: expected {expected}, got {actual}.",
            }

        return {"valid": True, "value": piva}

    @mcp.tool()
    def get_sdi_filename(
        partita_iva_cedente: Annotated[
            str,
            Field(
                description=(
                    "Partita IVA of the sender (CedentePrestatore) — 11 digits, without prefix. "
                    "The SDI prepends 'IT' automatically."
                )
            ),
        ],
        progressivo_invio: Annotated[
            str,
            Field(
                description=(
                    "ProgressivoInvio used in DatiTrasmissione — max 10 alphanumeric chars. "
                    "Zero-padded to 5 digits if purely numeric and shorter than 5 chars."
                )
            ),
        ],
    ) -> dict:
        """Generate the canonical SDI filename for a FatturaPA document.

        Use this when you need the official filename independently of generate_fattura_xml()
        (which also produces the filename). The SDI specification requires the format:
        IT{PartitaIVA}_{ProgressivoInvio}.xml, e.g. IT01234567890_00001.xml.

        Validates: partita_iva_cedente must be exactly 11 digits; progressivo_invio must be
        1–10 alphanumeric characters. Purely numeric progressivo shorter than 5 digits is
        zero-padded to 5 digits (e.g. '1' → '00001').

        On success returns {'filename': str, 'partita_iva': str, 'progressivo_invio': str, 'length': int}.
        On failure returns {'error': '<reason>'}.
        """
        piva = partita_iva_cedente.strip()

        if not re.match(r"^\d{11}$", piva):
            return {"error": "partita_iva_cedente must be exactly 11 digits."}

        progressivo = progressivo_invio.strip()
        if not re.match(r"^[A-Za-z0-9]{1,10}$", progressivo):
            return {"error": "progressivo_invio must be 1–10 alphanumeric characters."}

        # Zero-pad if purely numeric and shorter than 5 digits
        if re.match(r"^\d+$", progressivo) and len(progressivo) < 5:
            progressivo = progressivo.zfill(5)

        filename = f"IT{piva}_{progressivo}.xml"
        return {
            "filename": filename,
            "partita_iva": piva,
            "progressivo_invio": progressivo,
            "length": len(filename),
        }

    @mcp.tool()
    def check_ritenuta_acconto(
        imponibile: Annotated[
            float,
            Field(
                description=(
                    "Taxable base amount subject to withholding tax (imponibile della ritenuta). "
                    "Usually equals the net invoice total for professional services."
                )
            ),
        ],
        tipo_ritenuta: Annotated[
            str,
            Field(
                description=(
                    "Withholding tax type code: "
                    "RT01 (natural person, occasional work, 20%), "
                    "RT02 (natural person, professional, 20%), "
                    "RT03 (legal entity, agent commissions, 23.20%), "
                    "RT04 (natural person, agent commissions, 23.20%), "
                    "RT05 (condominium, 4%), "
                    "RT06 (employment income, 30%)."
                )
            ),
        ],
        causale_pagamento: Annotated[
            str,
            Field(
                description=(
                    "Income category code for withholding tax (CausalePagamento). "
                    "Common values: A (professional fees), B (agent commissions), "
                    "L (employment), O (occasional work), Q (commissions). "
                    "See Agenzia delle Entrate Mod. 770 for the complete list."
                )
            ),
        ],
    ) -> dict:
        """Compute ritenuta d'acconto (withholding tax) for professional invoices.

        Use this when issuing professional service invoices (TD01 or TD06) that are subject
        to withholding tax — typically for self-employed professionals, agents, or freelancers.
        Also mark the relevant line items with ritenuta='SI' in add_linea_dettaglio(), and pass
        the returned 'DatiRitenuta' dict to generate_fattura_xml() as dati_ritenuta.

        tipo_ritenuta determines the rate: RT01/RT02 = 20% (natural person, professional/occasional),
        RT03/RT04 = 23.20% (agent commissions), RT05 = 4% (condominium), RT06 = 30% (employment).
        causale_pagamento: income category code for Mod. 770 (e.g. 'A' professional fees, 'O' occasional).

        Validates: tipo_ritenuta must be in RT01–RT06. imponibile is typically the net invoice total.

        On success returns {'DatiRitenuta': {...}, 'importo_ritenuta': str, 'aliquota_applicata': str,
        'imponibile_ritenuta': str, 'description': str, 'legal_ref': str}.
        On failure returns {'error': '<reason>'}.
        """
        if tipo_ritenuta not in TIPO_RITENUTA:
            return {
                "error": (
                    f"Invalid tipo_ritenuta '{tipo_ritenuta}'. "
                    f"Valid codes: {', '.join(TIPO_RITENUTA.keys())}."
                )
            }

        ritenuta_info = TIPO_RITENUTA[tipo_ritenuta]
        base = Decimal(str(imponibile))
        rate = ritenuta_info["rate"]
        importo = (base * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        aliquota_pct = (rate * 100).quantize(Decimal("0.01"))

        return {
            "DatiRitenuta": {
                "TipoRitenuta": tipo_ritenuta,
                "ImportoRitenuta": str(importo),
                "AliquotaRitenuta": str(aliquota_pct),
                "CausalePagamento": causale_pagamento.upper(),
            },
            "importo_ritenuta": str(importo),
            "aliquota_applicata": str(aliquota_pct),
            "imponibile_ritenuta": str(base.quantize(Decimal("0.01"))),
            "description": ritenuta_info["description"],
            "legal_ref": ritenuta_info["legal_ref"],
        }
