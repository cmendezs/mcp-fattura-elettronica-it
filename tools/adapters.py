"""
IT-specific adapter classes that extend mcp-einvoicing-core abstract base classes.

These classes bind the FatturaPA implementation to the shared core contracts,
enabling mcp-fattura-elettronica-it to participate in multi-country aggregators
(EInvoicingMCPServer) while remaining fully standalone.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from mcp_einvoicing_core.base_server import (
    BaseDocumentGenerator,
    BaseDocumentParser,
    BaseDocumentValidator,
    BasePartyValidator,
)
from mcp_einvoicing_core.logging_utils import get_logger
from mcp_einvoicing_core.models import (
    DocumentValidationResult,
    InvoiceDocument,
)

logger = get_logger(__name__)

_FATTURA_NS = "http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2"
_SCHEMAS_DIR = Path(__file__).parent.parent / "schemas"


# ---------------------------------------------------------------------------
# FatturaGenerator
# ---------------------------------------------------------------------------


class FatturaGenerator(BaseDocumentGenerator):
    """Generates FatturaPA v1.6.1 XML from a core InvoiceDocument."""

    def get_format_name(self) -> str:
        return "FatturaPA"

    def get_country_code(self) -> str:
        return "IT"

    def get_namespace(self) -> Optional[str]:
        return _FATTURA_NS

    def generate(self, document: InvoiceDocument) -> str:
        """Convert an InvoiceDocument to a FatturaPA v1.6.1 XML string."""
        formato = document.transmission_format or "FPR12"
        seller = document.seller
        buyer = document.buyer

        seller_paese = seller.tax_id.country_code
        seller_codice = seller.tax_id.identifier
        seller_ana = (
            f"<Denominazione>{seller.name}</Denominazione>"
            if seller.name
            else f"<Nome>{seller.first_name or ''}</Nome><Cognome>{seller.last_name or ''}</Cognome>"
        )
        s_addr = seller.address
        seller_sede = (
            f"<Indirizzo>{s_addr.street}</Indirizzo>"
            f"<CAP>{s_addr.postal_code}</CAP>"
            f"<Comune>{s_addr.city}</Comune>"
            f"<Nazione>{s_addr.country_code}</Nazione>"
            if s_addr
            else ""
        )

        buyer_id_xml = ""
        if buyer.tax_id:
            buyer_id_xml = (
                f"<IdFiscaleIVA>"
                f"<IdPaese>{buyer.tax_id.country_code}</IdPaese>"
                f"<IdCodice>{buyer.tax_id.identifier}</IdCodice>"
                f"</IdFiscaleIVA>"
            )
        if buyer.alt_tax_id:
            buyer_id_xml += f"<CodiceFiscale>{buyer.alt_tax_id}</CodiceFiscale>"
        buyer_ana = (
            f"<Denominazione>{buyer.name}</Denominazione>"
            if buyer.name
            else f"<Nome>{buyer.first_name or ''}</Nome><Cognome>{buyer.last_name or ''}</Cognome>"
        )
        b_addr = buyer.address
        buyer_sede = (
            f"<Indirizzo>{b_addr.street}</Indirizzo>"
            f"<CAP>{b_addr.postal_code}</CAP>"
            f"<Comune>{b_addr.city}</Comune>"
            f"<Nazione>{b_addr.country_code}</Nazione>"
            if b_addr
            else ""
        )

        linee_xml = ""
        for line in document.lines:
            qta = f"<Quantita>{line.quantity}</Quantita>" if line.quantity is not None else ""
            um = f"<UnitaMisura>{line.unit_of_measure}</UnitaMisura>" if line.unit_of_measure else ""
            nat = f"<Natura>{line.vat_exemption_code}</Natura>" if line.vat_exemption_code else ""
            linee_xml += (
                f"<DettaglioLinee>"
                f"<NumeroLinea>{line.line_number}</NumeroLinea>"
                f"<Descrizione>{line.description}</Descrizione>"
                f"{qta}{um}"
                f"<PrezzoUnitario>{line.unit_price:.8f}</PrezzoUnitario>"
                f"<PrezzoTotale>{line.total_price:.2f}</PrezzoTotale>"
                f"<AliquotaIVA>{line.vat_rate:.2f}</AliquotaIVA>"
                f"{nat}"
                f"</DettaglioLinee>"
            )

        riepilogo_xml = ""
        for vat in document.vat_summary:
            nat = f"<Natura>{vat.vat_exemption_code}</Natura>" if vat.vat_exemption_code else ""
            riepilogo_xml += (
                f"<DatiRiepilogo>"
                f"<AliquotaIVA>{vat.vat_rate:.2f}</AliquotaIVA>"
                f"{nat}"
                f"<Imponibile>{vat.taxable_base:.2f}</Imponibile>"
                f"<Imposta>{vat.vat_amount:.2f}</Imposta>"
                f"<EsigibilitaIVA>I</EsigibilitaIVA>"
                f"</DatiRiepilogo>"
            )

        pagamento_xml = ""
        if document.payment:
            p = document.payment
            tp = p.payment_terms_code or "TP02"
            scad = f"<DataScadenzaPagamento>{p.due_date}</DataScadenzaPagamento>" if p.due_date else ""
            iban = f"<IBAN>{p.iban}</IBAN>" if p.iban else ""
            banca = f"<IstitutoFinanziario>{p.bank_name}</IstitutoFinanziario>" if p.bank_name else ""
            pagamento_xml = (
                f"<DatiPagamento>"
                f"<CondizioniPagamento>{tp}</CondizioniPagamento>"
                f"<DettaglioPagamento>"
                f"<ModalitaPagamento>{p.payment_method_code}</ModalitaPagamento>"
                f"{scad}"
                f"<ImportoPagamento>{p.amount:.2f}</ImportoPagamento>"
                f"{iban}{banca}"
                f"</DettaglioPagamento>"
                f"</DatiPagamento>"
            )

        return (
            f'<?xml version="1.0" encoding="UTF-8"?>'
            f'<p:FatturaElettronica versione="{formato}" '
            f'xmlns:p="{_FATTURA_NS}" '
            f'xmlns:ds="http://www.w3.org/2000/09/xmldsig#" '
            f'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            f"<FatturaElettronicaHeader>"
            f"<DatiTrasmissione>"
            f"<IdTrasmittente>"
            f"<IdPaese>{seller_paese}</IdPaese>"
            f"<IdCodice>{seller_codice}</IdCodice>"
            f"</IdTrasmittente>"
            f"<ProgressivoInvio>00001</ProgressivoInvio>"
            f"<FormatoTrasmissione>{formato}</FormatoTrasmissione>"
            f"<CodiceDestinatario>0000000</CodiceDestinatario>"
            f"</DatiTrasmissione>"
            f"<CedentePrestatore>"
            f"<DatiAnagrafici>"
            f"<IdFiscaleIVA>"
            f"<IdPaese>{seller_paese}</IdPaese>"
            f"<IdCodice>{seller_codice}</IdCodice>"
            f"</IdFiscaleIVA>"
            f"<Anagrafica>{seller_ana}</Anagrafica>"
            f"<RegimeFiscale>RF01</RegimeFiscale>"
            f"</DatiAnagrafici>"
            f"<Sede>{seller_sede}</Sede>"
            f"</CedentePrestatore>"
            f"<CessionarioCommittente>"
            f"<DatiAnagrafici>"
            f"{buyer_id_xml}"
            f"<Anagrafica>{buyer_ana}</Anagrafica>"
            f"</DatiAnagrafici>"
            f"<Sede>{buyer_sede}</Sede>"
            f"</CessionarioCommittente>"
            f"</FatturaElettronicaHeader>"
            f"<FatturaElettronicaBody>"
            f"<DatiGenerali>"
            f"<DatiGeneraliDocumento>"
            f"<TipoDocumento>{document.document_type}</TipoDocumento>"
            f"<Divisa>{document.currency}</Divisa>"
            f"<Data>{document.date}</Data>"
            f"<Numero>{document.number}</Numero>"
            f"</DatiGeneraliDocumento>"
            f"</DatiGenerali>"
            f"<DatiBeniServizi>"
            f"{linee_xml}"
            f"{riepilogo_xml}"
            f"</DatiBeniServizi>"
            f"{pagamento_xml}"
            f"</FatturaElettronicaBody>"
            f"</p:FatturaElettronica>"
        )


# ---------------------------------------------------------------------------
# FatturaValidator
# ---------------------------------------------------------------------------


class FatturaValidator(BaseDocumentValidator):
    """Validates FatturaPA XML against the official XSD schema v1.6.1."""

    def get_schema_version(self) -> str:
        return "FatturaPA v1.6.1"

    def get_schema_path(self) -> Optional[str]:
        path = _SCHEMAS_DIR / "FatturaPA_v1.6.1.xsd"
        return str(path) if path.exists() else None

    def validate(self, document_content: str | bytes) -> DocumentValidationResult:
        """Validate FatturaPA XML against XSD schema using lxml."""
        try:
            from lxml import etree
        except ImportError:
            return DocumentValidationResult(
                valid=False, errors=["lxml is not installed"], warnings=[], metadata={}
            )

        xsd_path_str = self.get_schema_path()
        if not xsd_path_str:
            return DocumentValidationResult(
                valid=False, errors=["XSD schema not found"], warnings=[], metadata={}
            )

        xsd_path = Path(xsd_path_str)
        xmldsig_path = xsd_path.parent / "xmldsig-core-schema.xsd"

        try:
            xml_bytes = document_content.encode("utf-8") if isinstance(document_content, str) else document_content
            xml_doc = etree.fromstring(xml_bytes)
        except etree.XMLSyntaxError as exc:
            return DocumentValidationResult(
                valid=False, errors=[f"XML parse error: {exc}"], warnings=[], metadata={}
            )

        try:
            parser = etree.XMLParser()
            if xmldsig_path.exists():
                class _LocalResolver(etree.Resolver):
                    def resolve(self, url, id, context):
                        if "xmldsig" in url:
                            return self.resolve_filename(str(xmldsig_path), context)
                        return None
                parser.resolvers.add(_LocalResolver())
            xsd_doc = etree.parse(str(xsd_path), parser)
            schema = etree.XMLSchema(xsd_doc)
        except Exception as exc:
            return DocumentValidationResult(
                valid=False, errors=[f"Failed to load XSD: {exc}"], warnings=[], metadata={}
            )

        if schema.validate(xml_doc):
            versione = xml_doc.get("versione", "unknown")
            return DocumentValidationResult(
                valid=True, errors=[], warnings=[],
                metadata={"formato_trasmissione": versione, "schema": self.get_schema_version()},
            )
        return DocumentValidationResult(
            valid=False,
            errors=[str(e) for e in schema.error_log],
            warnings=[],
            metadata={},
        )


# ---------------------------------------------------------------------------
# FatturaParser
# ---------------------------------------------------------------------------


class FatturaParser(BaseDocumentParser):
    """Parses FatturaPA XML into a structured dict."""

    def parse(self, document_content: str | bytes) -> dict:
        """Parse FatturaPA XML and return a structured dict."""
        try:
            from lxml import etree
        except ImportError:
            return {"error": "lxml is not installed"}

        xml_bytes = document_content.encode("utf-8") if isinstance(document_content, str) else document_content
        try:
            root = etree.fromstring(xml_bytes)
        except etree.XMLSyntaxError as exc:
            return {"error": f"XML parse error: {exc}"}

        def _txt(el, path: str) -> Optional[str]:
            if el is None:
                return None
            node = el.find(path)
            return node.text if node is not None else None

        versione = root.get("versione", "unknown")
        header = root.find("FatturaElettronicaHeader")
        body = root.find("FatturaElettronicaBody")

        result: dict = {"versione": versione, "header": {}, "body": {}}

        if header is not None:
            dt = header.find("DatiTrasmissione")
            cp = header.find("CedentePrestatore")
            cc = header.find("CessionarioCommittente")

            result["header"]["dati_trasmissione"] = {
                "id_paese": _txt(dt, "IdTrasmittente/IdPaese"),
                "id_codice": _txt(dt, "IdTrasmittente/IdCodice"),
                "progressivo_invio": _txt(dt, "ProgressivoInvio"),
                "formato_trasmissione": _txt(dt, "FormatoTrasmissione"),
                "codice_destinatario": _txt(dt, "CodiceDestinatario"),
                "pec_destinatario": _txt(dt, "PECDestinatario"),
            }

            if cp is not None:
                cp_an = cp.find("DatiAnagrafici")
                result["header"]["cedente_prestatore"] = {
                    "id_paese": _txt(cp_an, "IdFiscaleIVA/IdPaese"),
                    "id_codice": _txt(cp_an, "IdFiscaleIVA/IdCodice"),
                    "denominazione": _txt(cp_an, "Anagrafica/Denominazione"),
                    "nome": _txt(cp_an, "Anagrafica/Nome"),
                    "cognome": _txt(cp_an, "Anagrafica/Cognome"),
                    "regime_fiscale": _txt(cp_an, "RegimeFiscale"),
                    "indirizzo": _txt(cp, "Sede/Indirizzo"),
                    "cap": _txt(cp, "Sede/CAP"),
                    "comune": _txt(cp, "Sede/Comune"),
                    "nazione": _txt(cp, "Sede/Nazione"),
                }

            if cc is not None:
                cc_an = cc.find("DatiAnagrafici")
                result["header"]["cessionario_committente"] = {
                    "id_paese": _txt(cc_an, "IdFiscaleIVA/IdPaese"),
                    "id_codice": _txt(cc_an, "IdFiscaleIVA/IdCodice"),
                    "codice_fiscale": _txt(cc_an, "CodiceFiscale"),
                    "denominazione": _txt(cc_an, "Anagrafica/Denominazione"),
                    "nome": _txt(cc_an, "Anagrafica/Nome"),
                    "cognome": _txt(cc_an, "Anagrafica/Cognome"),
                    "indirizzo": _txt(cc, "Sede/Indirizzo"),
                    "cap": _txt(cc, "Sede/CAP"),
                    "comune": _txt(cc, "Sede/Comune"),
                    "nazione": _txt(cc, "Sede/Nazione"),
                }

        if body is not None:
            dg = body.find("DatiGenerali/DatiGeneraliDocumento")
            result["body"]["dati_generali"] = {
                "tipo_documento": _txt(dg, "TipoDocumento"),
                "divisa": _txt(dg, "Divisa"),
                "data": _txt(dg, "Data"),
                "numero": _txt(dg, "Numero"),
                "causale": _txt(dg, "Causale"),
            }

            result["body"]["dettaglio_linee"] = [
                {
                    "numero_linea": _txt(ld, "NumeroLinea"),
                    "descrizione": _txt(ld, "Descrizione"),
                    "quantita": _txt(ld, "Quantita"),
                    "prezzo_unitario": _txt(ld, "PrezzoUnitario"),
                    "prezzo_totale": _txt(ld, "PrezzoTotale"),
                    "aliquota_iva": _txt(ld, "AliquotaIVA"),
                    "natura": _txt(ld, "Natura"),
                }
                for ld in body.findall("DatiBeniServizi/DettaglioLinee")
            ]

            result["body"]["dati_riepilogo"] = [
                {
                    "aliquota_iva": _txt(r, "AliquotaIVA"),
                    "natura": _txt(r, "Natura"),
                    "imponibile": _txt(r, "Imponibile"),
                    "imposta": _txt(r, "Imposta"),
                    "esigibilita_iva": _txt(r, "EsigibilitaIVA"),
                }
                for r in body.findall("DatiBeniServizi/DatiRiepilogo")
            ]

            dp = body.find("DatiPagamento")
            if dp is not None:
                ddp = dp.find("DettaglioPagamento")
                result["body"]["dati_pagamento"] = {
                    "condizioni_pagamento": _txt(dp, "CondizioniPagamento"),
                    "modalita_pagamento": _txt(ddp, "ModalitaPagamento"),
                    "importo_pagamento": _txt(ddp, "ImportoPagamento"),
                    "data_scadenza": _txt(ddp, "DataScadenzaPagamento"),
                    "iban": _txt(ddp, "IBAN"),
                }

        return result


# ---------------------------------------------------------------------------
# ItalyPartyValidator
# ---------------------------------------------------------------------------


class ItalyPartyValidator(BasePartyValidator):
    """Italian party validator — Partita IVA modulo-10 checksum (Agenzia delle Entrate)."""

    def validate_seller(self, **kwargs) -> dict:
        """Validate seller (CedentePrestatore) fields."""
        errors: list[str] = []
        id_paese = kwargs.get("id_paese", "IT")
        id_codice = kwargs.get("id_codice", "")
        denominazione = kwargs.get("denominazione")
        nome = kwargs.get("nome")
        cognome = kwargs.get("cognome")
        regime_fiscale = kwargs.get("regime_fiscale", "RF01")

        if not denominazione and not (nome and cognome):
            errors.append("Either 'denominazione' or both 'nome' and 'cognome' are required.")
        if denominazione and (nome or cognome):
            errors.append("'denominazione' is mutually exclusive with 'nome'/'cognome'.")
        if id_paese.upper() == "IT":
            result = self.validate_tax_id(id_codice, "IT")
            if not result.get("valid"):
                errors.append(result.get("error", "Invalid Partita IVA."))

        if errors:
            return {"valid": False, "errors": errors}
        return {"valid": True, "id_paese": id_paese.upper(), "id_codice": id_codice,
                "regime_fiscale": regime_fiscale}

    def validate_buyer(self, **kwargs) -> dict:
        """Validate buyer (CessionarioCommittente) fields."""
        errors: list[str] = []
        id_paese = kwargs.get("id_paese")
        id_codice = kwargs.get("id_codice")
        codice_fiscale = kwargs.get("codice_fiscale")
        denominazione = kwargs.get("denominazione")
        nome = kwargs.get("nome")
        cognome = kwargs.get("cognome")

        if not denominazione and not (nome and cognome):
            errors.append("Either 'denominazione' or both 'nome' and 'cognome' are required.")
        if denominazione and (nome or cognome):
            errors.append("'denominazione' is mutually exclusive with 'nome'/'cognome'.")
        if not id_codice and not codice_fiscale:
            errors.append("At least one of 'id_codice' or 'codice_fiscale' is required.")

        if errors:
            return {"valid": False, "errors": errors}
        return {"valid": True, "id_paese": id_paese, "id_codice": id_codice,
                "codice_fiscale": codice_fiscale}

    def validate_tax_id(self, tax_id: str, country_code: str) -> dict:
        """Validate Italian Partita IVA using the Agenzia delle Entrate modulo-10 algorithm."""
        if country_code.upper() != "IT":
            return {
                "valid": False,
                "error": f"ItalyPartyValidator only validates IT tax IDs, got '{country_code}'.",
            }

        piva = tax_id.strip()
        if not re.match(r"^\d{11}$", piva):
            return {"valid": False, "value": piva, "error": "Partita IVA must be exactly 11 digits."}

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
