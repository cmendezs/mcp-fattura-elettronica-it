"""
MCP tools for FatturaSemplificata (VFSM10) generation, XSD validation, and parsing.

Covers simplified invoices TD07/TD08/TD09 per art. 21-bis DPR 633/72 (amounts up to
EUR 400). Uses the VFSM10 XSD v1.0.2 namespace
http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.0.

VFSM10 is NOT an EN 16931 CIUS. It is a separate Agenzia delle Entrate format with a
flatter body structure (no per-line VAT breakdown, no DatiRiepilogo).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Optional

from fastmcp import FastMCP
from pydantic import Field

from mcp_einvoicing_core.logging_utils import get_logger
from mcp_einvoicing_core.xml_utils import safe_fromstring, safe_parser, xml_escape

logger = get_logger(__name__)

FATTURA_SEMPLIFICATA_NS = "http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.0"

_VALID_TIPO_DOCUMENTO = {"TD07", "TD08", "TD09"}

_XSD_CACHE_FSM: dict[str, Path] = {}


def _get_vfsm10_xsd_path() -> Path:
    """Resolve the VFSM10 XSD schema path."""
    if "FSM10" in _XSD_CACHE_FSM:
        return _XSD_CACHE_FSM["FSM10"]
    env_path = os.getenv("FATTURA_SEMPLIFICATA_XSD_PATH")
    if env_path:
        path = Path(env_path)
    else:
        path = Path(__file__).parent.parent / "schemas" / "FatturaSemplificata_VFSM10_v1.0.2.xsd"
    _XSD_CACHE_FSM["FSM10"] = path
    return path


def register_simplified_tools(mcp: FastMCP) -> None:
    """Register the 3 FatturaSemplificata (VFSM10) tools on the FastMCP instance."""

    @mcp.tool()
    def generate_fattura_semplificata(
        dati_trasmissione: Annotated[
            dict,
            Field(
                description=(
                    "Transmission data: IdTrasmittente (IdPaese + IdCodice), "
                    "ProgressivoInvio, CodiceDestinatario (7-char, or '0000000' for PEC), "
                    "and optionally PECDestinatario. FormatoTrasmissione is always FSM10."
                )
            ),
        ],
        cedente_prestatore: Annotated[
            dict,
            Field(
                description=(
                    "Seller data: IdFiscaleIVA (IdPaese + IdCodice), optional CodiceFiscale, "
                    "Denominazione or Nome+Cognome, Sede (Indirizzo, CAP, Comune, Nazione), "
                    "RegimeFiscale (RF01-RF19)."
                )
            ),
        ],
        cessionario_committente: Annotated[
            dict,
            Field(
                description=(
                    "Buyer data: IdentificativiFiscali (IdFiscaleIVA and/or CodiceFiscale), "
                    "optional AltriDatiIdentificativi (Denominazione or Nome+Cognome, Sede)."
                )
            ),
        ],
        dati_generali: Annotated[
            dict,
            Field(
                description=(
                    "General document data: TipoDocumento (TD07/TD08/TD09), Divisa, "
                    "Data (YYYY-MM-DD), Numero. Optional: BolloVirtuale ('SI'), "
                    "DatiFatturaRettificata (NumeroFR, DataFR, ElementiRettificati) for TD08/TD09."
                )
            ),
        ],
        dati_beni_servizi: Annotated[
            list,
            Field(
                description=(
                    "List of goods/services entries. Each entry: Descrizione (max 1000 chars), "
                    "Importo (decimal, tax-inclusive amount), DatiIVA (Imposta and/or Aliquota), "
                    "optional Natura code, optional RiferimentoNormativo."
                )
            ),
        ],
        allegati: Annotated[
            Optional[list],
            Field(
                default=None,
                description=(
                    "Optional list of attachments. Each: NomeAttachment, Attachment (base64), "
                    "optional FormatoAttachment, DescrizioneAttachment."
                ),
            ),
        ] = None,
    ) -> dict:
        """Assemble a complete FatturaSemplificata VFSM10 XML document.

        Use this for simplified invoices (TD07), simplified credit notes (TD08), and
        simplified debit notes (TD09) per art. 21-bis DPR 633/72. These are valid for
        transactions up to EUR 400 (tax-inclusive).

        The simplified format has a flatter structure than the ordinary FatturaPA: no
        per-line VAT breakdown (DettaglioLinee/DatiRiepilogo), no DatiPagamento in the body.
        Each DatiBeniServizi entry carries its own Descrizione, Importo, and DatiIVA.

        On success returns {'xml': str, 'filename': str, 'length_bytes': int}.
        On error returns {'error': '<reason>'}.
        """
        try:
            dt = dati_trasmissione.get("DatiTrasmissione", dati_trasmissione)
            cp = cedente_prestatore.get("CedentePrestatore", cedente_prestatore)
            cc = cessionario_committente.get("CessionarioCommittente", cessionario_committente)
            dg = dati_generali.get("DatiGenerali", dati_generali)

            id_trasm = dt.get("IdTrasmittente", {})
            id_paese = id_trasm.get("IdPaese", "IT")
            id_codice = id_trasm.get("IdCodice", "")
            progressivo = dt.get("ProgressivoInvio", "00001")
            codice_dest = dt.get("CodiceDestinatario", "0000000")
            pec_dest = dt.get("PECDestinatario", "")

            dg_doc = dg.get("DatiGeneraliDocumento", dg)
            tipo_doc = dg_doc.get("TipoDocumento", "TD07")
            if tipo_doc not in _VALID_TIPO_DOCUMENTO:
                return {
                    "error": (
                        f"Invalid TipoDocumento '{tipo_doc}' for simplified invoices. "
                        f"Valid codes: {', '.join(sorted(_VALID_TIPO_DOCUMENTO))}."
                    )
                }

            divisa = dg_doc.get("Divisa", "EUR")
            data_doc = dg_doc.get("Data", "")
            numero_doc = dg_doc.get("Numero", "")
            bollo = dg_doc.get("BolloVirtuale", "")

            # Seller
            cp_id_iva = cp.get("IdFiscaleIVA", {})
            cp_cf = cp.get("CodiceFiscale", "")
            cp_sede = cp.get("Sede", {})
            cp_regime = cp.get("RegimeFiscale", "RF01")

            def _cp_name_xml() -> str:
                if "Denominazione" in cp:
                    return f"<Denominazione>{xml_escape(cp['Denominazione'])}</Denominazione>"
                return (
                    f"<Nome>{xml_escape(cp.get('Nome', ''))}</Nome>"
                    f"<Cognome>{xml_escape(cp.get('Cognome', ''))}</Cognome>"
                )

            def _sede_xml(sede: dict) -> str:
                parts = [f"<Indirizzo>{xml_escape(sede.get('Indirizzo', ''))}</Indirizzo>"]
                if sede.get("NumeroCivico"):
                    parts.append(f"<NumeroCivico>{xml_escape(sede['NumeroCivico'])}</NumeroCivico>")
                parts.append(f"<CAP>{sede.get('CAP', '')}</CAP>")
                parts.append(f"<Comune>{xml_escape(sede.get('Comune', ''))}</Comune>")
                if sede.get("Provincia"):
                    parts.append(f"<Provincia>{sede['Provincia']}</Provincia>")
                parts.append(f"<Nazione>{sede.get('Nazione', 'IT')}</Nazione>")
                return "".join(parts)

            # Buyer
            cc_idf = cc.get("IdentificativiFiscali", cc)
            cc_id_iva = cc_idf.get("IdFiscaleIVA", {})
            cc_cf = cc_idf.get("CodiceFiscale", "")
            cc_altri = cc.get("AltriDatiIdentificativi", {})

            def _cc_identificativi_xml() -> str:
                parts = []
                if cc_id_iva:
                    parts.append(
                        f"<IdFiscaleIVA>"
                        f"<IdPaese>{cc_id_iva.get('IdPaese', 'IT')}</IdPaese>"
                        f"<IdCodice>{cc_id_iva.get('IdCodice', '')}</IdCodice>"
                        f"</IdFiscaleIVA>"
                    )
                if cc_cf:
                    parts.append(f"<CodiceFiscale>{cc_cf}</CodiceFiscale>")
                return "".join(parts)

            def _cc_altri_xml() -> str:
                if not cc_altri:
                    return ""
                parts = []
                if "Denominazione" in cc_altri:
                    parts.append(f"<Denominazione>{xml_escape(cc_altri['Denominazione'])}</Denominazione>")
                elif "Nome" in cc_altri:
                    parts.append(f"<Nome>{xml_escape(cc_altri.get('Nome', ''))}</Nome>")
                    parts.append(f"<Cognome>{xml_escape(cc_altri.get('Cognome', ''))}</Cognome>")
                if "Sede" in cc_altri:
                    parts.append(f"<Sede>{_sede_xml(cc_altri['Sede'])}</Sede>")
                return f"<AltriDatiIdentificativi>{''.join(parts)}</AltriDatiIdentificativi>"

            # DatiBeniServizi
            def _beni_servizi_xml(items: list) -> str:
                parts = []
                for item in items:
                    entry = item.get("DatiBeniServizi", item)
                    desc = xml_escape(entry.get("Descrizione", "")[:1000])
                    importo = entry.get("Importo", "0.00")
                    dati_iva = entry.get("DatiIVA", {})
                    iva_parts = []
                    if "Imposta" in dati_iva:
                        iva_parts.append(f"<Imposta>{dati_iva['Imposta']}</Imposta>")
                    if "Aliquota" in dati_iva:
                        iva_parts.append(f"<Aliquota>{dati_iva['Aliquota']}</Aliquota>")
                    natura = f"<Natura>{entry['Natura']}</Natura>" if "Natura" in entry else ""
                    rif_norm = (
                        f"<RiferimentoNormativo>{xml_escape(entry['RiferimentoNormativo'][:100])}</RiferimentoNormativo>"
                        if "RiferimentoNormativo" in entry else ""
                    )
                    parts.append(
                        f"<DatiBeniServizi>"
                        f"<Descrizione>{desc}</Descrizione>"
                        f"<Importo>{importo}</Importo>"
                        f"<DatiIVA>{''.join(iva_parts)}</DatiIVA>"
                        f"{natura}{rif_norm}"
                        f"</DatiBeniServizi>"
                    )
                return "".join(parts)

            # Allegati (simplified format uses NomeAttachment, not NomeAllegato)
            def _allegati_xml(allegati_list: Optional[list]) -> str:
                if not allegati_list:
                    return ""
                parts = []
                for a in allegati_list:
                    entry = a.get("Allegati", a)
                    fmt = (
                        f"<FormatoAttachment>{xml_escape(entry['FormatoAttachment'])}</FormatoAttachment>"
                        if "FormatoAttachment" in entry else ""
                    )
                    desc = (
                        f"<DescrizioneAttachment>{xml_escape(entry['DescrizioneAttachment'][:100])}</DescrizioneAttachment>"
                        if "DescrizioneAttachment" in entry else ""
                    )
                    parts.append(
                        f"<Allegati>"
                        f"<NomeAttachment>{xml_escape(entry['NomeAttachment'])}</NomeAttachment>"
                        f"{fmt}{desc}"
                        f"<Attachment>{entry['Attachment']}</Attachment>"
                        f"</Allegati>"
                    )
                return "".join(parts)

            # DatiFatturaRettificata (for TD08/TD09)
            dati_rett = dg.get("DatiFatturaRettificata", dg_doc.get("DatiFatturaRettificata"))
            rett_xml = ""
            if dati_rett:
                rett_xml = (
                    f"<DatiFatturaRettificata>"
                    f"<NumeroFR>{xml_escape(dati_rett.get('NumeroFR', ''))}</NumeroFR>"
                    f"<DataFR>{dati_rett.get('DataFR', '')}</DataFR>"
                    f"<ElementiRettificati>{xml_escape(dati_rett.get('ElementiRettificati', '')[:1000])}</ElementiRettificati>"
                    f"</DatiFatturaRettificata>"
                )

            pec_xml = f"<PECDestinatario>{xml_escape(pec_dest)}</PECDestinatario>" if pec_dest else ""
            cp_cf_xml = f"<CodiceFiscale>{cp_cf}</CodiceFiscale>" if cp_cf else ""
            bollo_xml = f"<BolloVirtuale>{bollo}</BolloVirtuale>" if bollo else ""

            xml = (
                f'<?xml version="1.0" encoding="UTF-8"?>'
                f'<p:FatturaElettronicaSemplificata versione="FSM10" '
                f'xmlns:p="{FATTURA_SEMPLIFICATA_NS}" '
                f'xmlns:ds="http://www.w3.org/2000/09/xmldsig#" '
                f'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
                f"<FatturaElettronicaHeader>"
                f"<DatiTrasmissione>"
                f"<IdTrasmittente>"
                f"<IdPaese>{id_paese}</IdPaese>"
                f"<IdCodice>{id_codice}</IdCodice>"
                f"</IdTrasmittente>"
                f"<ProgressivoInvio>{progressivo}</ProgressivoInvio>"
                f"<FormatoTrasmissione>FSM10</FormatoTrasmissione>"
                f"<CodiceDestinatario>{codice_dest}</CodiceDestinatario>"
                f"{pec_xml}"
                f"</DatiTrasmissione>"
                f"<CedentePrestatore>"
                f"<IdFiscaleIVA>"
                f"<IdPaese>{cp_id_iva.get('IdPaese', 'IT')}</IdPaese>"
                f"<IdCodice>{cp_id_iva.get('IdCodice', '')}</IdCodice>"
                f"</IdFiscaleIVA>"
                f"{cp_cf_xml}"
                f"{_cp_name_xml()}"
                f"<Sede>{_sede_xml(cp_sede)}</Sede>"
                f"<RegimeFiscale>{cp_regime}</RegimeFiscale>"
                f"</CedentePrestatore>"
                f"<CessionarioCommittente>"
                f"<IdentificativiFiscali>"
                f"{_cc_identificativi_xml()}"
                f"</IdentificativiFiscali>"
                f"{_cc_altri_xml()}"
                f"</CessionarioCommittente>"
                f"</FatturaElettronicaHeader>"
                f"<FatturaElettronicaBody>"
                f"<DatiGenerali>"
                f"<DatiGeneraliDocumento>"
                f"<TipoDocumento>{tipo_doc}</TipoDocumento>"
                f"<Divisa>{divisa}</Divisa>"
                f"<Data>{data_doc}</Data>"
                f"<Numero>{numero_doc}</Numero>"
                f"{bollo_xml}"
                f"</DatiGeneraliDocumento>"
                f"{rett_xml}"
                f"</DatiGenerali>"
                f"{_beni_servizi_xml(dati_beni_servizi)}"
                f"{_allegati_xml(allegati)}"
                f"</FatturaElettronicaBody>"
                f"</p:FatturaElettronicaSemplificata>"
            )

            piva = cp_id_iva.get("IdCodice", "00000000000")
            filename = f"IT{piva}_{progressivo}.xml"

            return {
                "xml": xml,
                "filename": filename,
                "length_bytes": len(xml.encode("utf-8")),
            }

        except Exception as exc:
            logger.exception("Error generating FatturaSemplificata XML")
            return {"error": f"XML generation failed: {exc}"}

    @mcp.tool()
    def validate_fattura_semplificata_xsd(
        xml_string: Annotated[
            str,
            Field(
                description=(
                    "Complete FatturaSemplificata XML string to validate. "
                    "Must include the FatturaElettronicaSemplificata root element with "
                    "namespace http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.0."
                )
            ),
        ],
    ) -> dict:
        """Validate a FatturaSemplificata XML string against the VFSM10 XSD v1.0.2.

        Call this immediately after generate_fattura_semplificata() to confirm XSD
        conformance. Also use to verify third-party simplified invoices.

        Requires lxml. Validates namespace, element structure, data types, and cardinality.

        On success returns {'valid': true, 'errors': []}.
        On failure returns {'valid': false, 'errors': ['...']}.
        On setup error returns {'error': '<reason>'}.
        """
        try:
            from lxml import etree
        except ImportError:
            return {"error": "lxml is not installed. Run: pip install lxml"}

        try:
            xml_bytes = xml_string.encode("utf-8") if isinstance(xml_string, str) else xml_string
            xml_doc = safe_fromstring(xml_bytes)
        except etree.XMLSyntaxError as exc:
            return {"valid": False, "errors": [f"XML parse error: {exc}"]}

        xsd_path = _get_vfsm10_xsd_path()
        if not xsd_path.exists():
            return {"error": f"VFSM10 XSD schema not found at '{xsd_path}'."}

        try:
            schemas_dir = xsd_path.parent
            xmldsig_path = schemas_dir / "xmldsig-core-schema.xsd"

            parser = safe_parser()
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
            return {"error": f"Failed to load VFSM10 XSD schema: {exc}"}

        is_valid = schema.validate(xml_doc)
        if is_valid:
            return {"valid": True, "errors": []}
        else:
            errors = [str(e) for e in schema.error_log]
            return {"valid": False, "errors": errors}

    @mcp.tool()
    def parse_fattura_semplificata_xml(
        xml_string: Annotated[
            str,
            Field(
                description=(
                    "FatturaSemplificata XML string to parse. "
                    "Accepts VFSM10 format (namespace v1.0)."
                )
            ),
        ],
    ) -> dict:
        """Parse a FatturaSemplificata XML string into a structured Python dict.

        Use this to inspect simplified invoices (TD07/TD08/TD09) received from
        counterparties or to verify output of generate_fattura_semplificata().

        Extracts: versione, transmission data, seller identity and address, buyer
        fiscal identifiers and optional address, document type/date/number, all
        DatiBeniServizi entries, and DatiFatturaRettificata if present.

        On success returns {'versione': str, 'header': {...}, 'body': {...}}.
        On error returns {'error': '<reason>'}.
        """
        try:
            from lxml import etree
        except ImportError:
            return {"error": "lxml is not installed. Run: pip install lxml"}

        try:
            xml_bytes = xml_string.encode("utf-8") if isinstance(xml_string, str) else xml_string
            root = safe_fromstring(xml_bytes)
        except etree.XMLSyntaxError as exc:
            return {"error": f"XML parse error: {exc}"}

        ns = {"p": FATTURA_SEMPLIFICATA_NS}
        versione = root.get("versione", "unknown")

        def _find(element, xpath: str):
            nodes = element.xpath(xpath, namespaces=ns)
            if nodes:
                return nodes[0]
            return element.find(xpath)

        def _txt(el, path: str) -> Optional[str]:
            if el is None:
                return None
            node = el.find(path)
            return node.text if node is not None else None

        header = _find(root, "FatturaElettronicaHeader")
        body = _find(root, "FatturaElettronicaBody")

        result: dict = {"versione": versione, "header": {}, "body": {}}

        if header is not None:
            dt = header.find("DatiTrasmissione")
            result["header"]["dati_trasmissione"] = {
                "id_paese": _txt(dt, "IdTrasmittente/IdPaese") if dt is not None else None,
                "id_codice": _txt(dt, "IdTrasmittente/IdCodice") if dt is not None else None,
                "progressivo_invio": _txt(dt, "ProgressivoInvio") if dt is not None else None,
                "formato_trasmissione": _txt(dt, "FormatoTrasmissione") if dt is not None else None,
                "codice_destinatario": _txt(dt, "CodiceDestinatario") if dt is not None else None,
                "pec_destinatario": _txt(dt, "PECDestinatario") if dt is not None else None,
            }

            cp = header.find("CedentePrestatore")
            if cp is not None:
                result["header"]["cedente_prestatore"] = {
                    "id_paese": _txt(cp, "IdFiscaleIVA/IdPaese"),
                    "id_codice": _txt(cp, "IdFiscaleIVA/IdCodice"),
                    "codice_fiscale": _txt(cp, "CodiceFiscale"),
                    "denominazione": _txt(cp, "Denominazione"),
                    "nome": _txt(cp, "Nome"),
                    "cognome": _txt(cp, "Cognome"),
                    "regime_fiscale": _txt(cp, "RegimeFiscale"),
                    "indirizzo": _txt(cp, "Sede/Indirizzo"),
                    "cap": _txt(cp, "Sede/CAP"),
                    "comune": _txt(cp, "Sede/Comune"),
                    "nazione": _txt(cp, "Sede/Nazione"),
                }

            cc = header.find("CessionarioCommittente")
            if cc is not None:
                idf = cc.find("IdentificativiFiscali")
                altri = cc.find("AltriDatiIdentificativi")
                result["header"]["cessionario_committente"] = {
                    "id_paese": _txt(idf, "IdFiscaleIVA/IdPaese") if idf is not None else None,
                    "id_codice": _txt(idf, "IdFiscaleIVA/IdCodice") if idf is not None else None,
                    "codice_fiscale": _txt(idf, "CodiceFiscale") if idf is not None else None,
                    "denominazione": _txt(altri, "Denominazione") if altri is not None else None,
                    "nome": _txt(altri, "Nome") if altri is not None else None,
                    "cognome": _txt(altri, "Cognome") if altri is not None else None,
                    "indirizzo": _txt(altri, "Sede/Indirizzo") if altri is not None else None,
                    "cap": _txt(altri, "Sede/CAP") if altri is not None else None,
                    "comune": _txt(altri, "Sede/Comune") if altri is not None else None,
                    "nazione": _txt(altri, "Sede/Nazione") if altri is not None else None,
                }

        if body is not None:
            dg = body.find("DatiGenerali/DatiGeneraliDocumento")
            result["body"]["dati_generali"] = {
                "tipo_documento": _txt(dg, "TipoDocumento") if dg is not None else None,
                "divisa": _txt(dg, "Divisa") if dg is not None else None,
                "data": _txt(dg, "Data") if dg is not None else None,
                "numero": _txt(dg, "Numero") if dg is not None else None,
            }

            dfr = body.find("DatiGenerali/DatiFatturaRettificata")
            if dfr is not None:
                result["body"]["dati_fattura_rettificata"] = {
                    "numero_fr": _txt(dfr, "NumeroFR"),
                    "data_fr": _txt(dfr, "DataFR"),
                    "elementi_rettificati": _txt(dfr, "ElementiRettificati"),
                }

            beni_servizi = []
            for bs in body.findall("DatiBeniServizi"):
                dati_iva_el = bs.find("DatiIVA")
                entry: dict = {
                    "descrizione": _txt(bs, "Descrizione"),
                    "importo": _txt(bs, "Importo"),
                    "imposta": _txt(dati_iva_el, "Imposta") if dati_iva_el is not None else None,
                    "aliquota": _txt(dati_iva_el, "Aliquota") if dati_iva_el is not None else None,
                    "natura": _txt(bs, "Natura"),
                    "riferimento_normativo": _txt(bs, "RiferimentoNormativo"),
                }
                beni_servizi.append(entry)
            result["body"]["dati_beni_servizi"] = beni_servizi

        return result
