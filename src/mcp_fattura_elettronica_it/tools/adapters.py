"""
IT-specific adapter classes that extend mcp-einvoicing-core abstract base classes.

These classes bind the FatturaPA implementation to the shared core contracts,
enabling mcp-fattura-elettronica-it to participate in multi-country aggregators
(EInvoicingMCPServer) while remaining fully standalone.
"""

from __future__ import annotations

from pathlib import Path

from mcp_einvoicing_core.base_server import (
    BaseDocumentGenerator,
    BaseDocumentParser,
    BaseDocumentValidator,
    BasePartyValidator,
)
from mcp_einvoicing_core.exceptions import DocumentGenerationError
from mcp_einvoicing_core.logging_utils import get_logger
from mcp_einvoicing_core.models import (
    DocumentValidationResult,
    TaxIdentifier,
)
from mcp_einvoicing_core.xml_utils import safe_fromstring, safe_parser, xml_escape

from mcp_fattura_elettronica_it.models import ItalianInvoice
from mcp_fattura_elettronica_it.natura import resolve_natura

logger = get_logger(__name__)

_FATTURA_NS = "http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2"
_SCHEMAS_DIR = Path(__file__).parent.parent / "schemas"


# ---------------------------------------------------------------------------
# FatturaGenerator
# ---------------------------------------------------------------------------


class FatturaGenerator(BaseDocumentGenerator[ItalianInvoice]):
    """Generates FatturaPA v1.2.3 XML from an ItalianInvoice (EN 16931 IT CIUS)."""

    def get_format_name(self) -> str:
        return "FatturaPA"

    def get_country_code(self) -> str:
        return "IT"

    def get_namespace(self) -> str | None:
        return _FATTURA_NS

    def generate(self, document: ItalianInvoice) -> str:
        """Convert an ItalianInvoice to a FatturaPA v1.2.3 XML string.

        Parties must be EN16931Party instances with vat_id set to the full
        country-prefixed identifier (e.g. 'IT01234567890'). Natural persons
        are not yet supported via this adapter — use the global_tools
        generate_fattura_xml tool for individual-person invoices until
        IT-SC-6 (ItalianParty subclass with nome/cognome) is implemented.

        Gruppo IVA (VAT-group) CodiceFiscale: set document.cedente_codice_fiscale
        and/or document.cessionario_codice_fiscale (flat fields on ItalianInvoice,
        not on the party) to the Codice Fiscale of the specific participating
        member — never the group's own CF. These are unrelated to IT-SC-6: they
        do not require a party subclass, since CodiceFiscale is emitted alongside
        the existing EN16931Party.vat_id-derived IdFiscaleIVA rather than replacing
        any party field.
        """
        formato = document.formato_trasmissione
        seller = document.seller
        buyer = document.buyer

        seller_vat = seller.vat_id or ""
        seller_paese = seller_vat[:2].upper() if len(seller_vat) >= 2 else "IT"
        seller_codice = seller_vat[2:] if len(seller_vat) > 2 else seller_vat
        seller_ana = f"<Denominazione>{xml_escape(seller.name)}</Denominazione>"
        s_addr = seller.address
        seller_sede = (
            f"<Indirizzo>{xml_escape(s_addr.line_one)}</Indirizzo>"
            f"<CAP>{xml_escape(s_addr.postcode)}</CAP>"
            f"<Comune>{xml_escape(s_addr.city)}</Comune>"
            f"<Nazione>{s_addr.country_code}</Nazione>"
            if s_addr
            else ""
        )

        buyer_vat = buyer.vat_id or ""
        buyer_paese = buyer_vat[:2].upper() if len(buyer_vat) >= 2 else ""
        buyer_codice = buyer_vat[2:] if len(buyer_vat) > 2 else buyer_vat
        buyer_id_xml = ""
        if buyer_vat:
            buyer_id_xml = (
                f"<IdFiscaleIVA>"
                f"<IdPaese>{buyer_paese}</IdPaese>"
                f"<IdCodice>{buyer_codice}</IdCodice>"
                f"</IdFiscaleIVA>"
            )
        # Gruppo IVA (VAT-group): cessionario_codice_fiscale must identify the
        # specific participating member, never the group's own CF — see
        # ItalianInvoice.cessionario_codice_fiscale and sdi.notifications.
        # SCARTO_CODE_REFERENCE['00327'].
        buyer_cf_xml = (
            f"<CodiceFiscale>{xml_escape(document.cessionario_codice_fiscale)}</CodiceFiscale>"
            if document.cessionario_codice_fiscale
            else ""
        )
        buyer_ana = f"<Denominazione>{xml_escape(buyer.name)}</Denominazione>"
        b_addr = buyer.address
        buyer_sede = (
            f"<Indirizzo>{xml_escape(b_addr.line_one)}</Indirizzo>"
            f"<CAP>{xml_escape(b_addr.postcode)}</CAP>"
            f"<Comune>{xml_escape(b_addr.city)}</Comune>"
            f"<Nazione>{b_addr.country_code}</Nazione>"
            if b_addr
            else ""
        )

        codice_dest = document.codice_destinatario
        pec_dest = document.pec_destinatario
        if codice_dest == "0000000" and not pec_dest:
            raise DocumentGenerationError(
                "CodiceDestinatario is '0000000' (PEC routing) but pec_destinatario is absent. "
                "Set pec_destinatario on the document or use a 6/7-char SDI routing code."
            )
        pec_xml = f"<PECDestinatario>{xml_escape(pec_dest)}</PECDestinatario>" if pec_dest else ""

        linee_xml = ""
        for line in document.line_items:
            qta = f"<Quantita>{line.quantity}</Quantita>" if line.quantity is not None else ""
            um = f"<UnitaMisura>{line.unit_code}</UnitaMisura>" if line.unit_code else ""
            natura_code = resolve_natura(line.tax_category, explicit=line.natura)
            nat = f"<Natura>{xml_escape(natura_code)}</Natura>" if natura_code else ""
            # AltriDatiGestionali is last in the XSD DettaglioLineeType sequence
            # (after Natura / RiferimentoAmministrazione).
            adg = ""
            if line.altri_dati_gestionali:
                for entry in line.altri_dati_gestionali:
                    rt = (
                        f"<RiferimentoTesto>{xml_escape(entry.riferimento_testo)}</RiferimentoTesto>"
                        if entry.riferimento_testo
                        else ""
                    )
                    rn = (
                        f"<RiferimentoNumero>{entry.riferimento_numero:.2f}</RiferimentoNumero>"
                        if entry.riferimento_numero is not None
                        else ""
                    )
                    rd = (
                        f"<RiferimentoData>{entry.riferimento_data.isoformat()}</RiferimentoData>"
                        if entry.riferimento_data
                        else ""
                    )
                    adg += (
                        f"<AltriDatiGestionali>"
                        f"<TipoDato>{xml_escape(entry.tipo_dato)}</TipoDato>"
                        f"{rt}{rn}{rd}"
                        f"</AltriDatiGestionali>"
                    )
            linee_xml += (
                f"<DettaglioLinee>"
                f"<NumeroLinea>{line.line_id}</NumeroLinea>"
                f"<Descrizione>{xml_escape(line.name)}</Descrizione>"
                f"{qta}{um}"
                f"<PrezzoUnitario>{line.unit_price:.8f}</PrezzoUnitario>"
                f"<PrezzoTotale>{line.line_net_amount:.2f}</PrezzoTotale>"
                f"<AliquotaIVA>{line.tax_rate:.2f}</AliquotaIVA>"
                f"{nat}"
                f"{adg}"
                f"</DettaglioLinee>"
            )

        riepilogo_xml = ""
        for tax in document.tax_lines:
            natura_code = resolve_natura(tax.category, explicit=tax.natura)
            nat = f"<Natura>{xml_escape(natura_code)}</Natura>" if natura_code else ""
            riepilogo_xml += (
                f"<DatiRiepilogo>"
                f"<AliquotaIVA>{tax.rate:.2f}</AliquotaIVA>"
                f"{nat}"
                f"<ImponibileImporto>{tax.taxable_amount:.2f}</ImponibileImporto>"
                f"<Imposta>{tax.tax_amount:.2f}</Imposta>"
                f"<EsigibilitaIVA>I</EsigibilitaIVA>"
                f"</DatiRiepilogo>"
            )

        pagamento_xml = ""
        if document.payment_means:
            pm = document.payment_means
            tp = "TP02"  # default: deferred payment
            due = document.due_date
            scad = (
                f"<DataScadenzaPagamento>{due}</DataScadenzaPagamento>"
                if due else ""
            )
            iban = f"<IBAN>{xml_escape(pm.iban)}</IBAN>" if pm.iban else ""
            pagamento_xml = (
                f"<DatiPagamento>"
                f"<CondizioniPagamento>{tp}</CondizioniPagamento>"
                f"<DettaglioPagamento>"
                f"<ModalitaPagamento>{xml_escape(pm.type_code)}</ModalitaPagamento>"
                f"{scad}"
                f"<ImportoPagamento>{document.amount_due:.2f}</ImportoPagamento>"
                f"{iban}"
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
            f"<ProgressivoInvio>{xml_escape(document.progressivo_invio)}</ProgressivoInvio>"
            f"<FormatoTrasmissione>{formato}</FormatoTrasmissione>"
            f"<CodiceDestinatario>{xml_escape(codice_dest)}</CodiceDestinatario>"
            f"{pec_xml}"
            f"</DatiTrasmissione>"
            f"<CedentePrestatore>"
            f"<DatiAnagrafici>"
            f"<IdFiscaleIVA>"
            f"<IdPaese>{seller_paese}</IdPaese>"
            f"<IdCodice>{seller_codice}</IdCodice>"
            f"</IdFiscaleIVA>"
            f"{f'<CodiceFiscale>{xml_escape(document.cedente_codice_fiscale)}</CodiceFiscale>' if document.cedente_codice_fiscale else ''}"
            f"<Anagrafica>{seller_ana}</Anagrafica>"
            f"<RegimeFiscale>{xml_escape(document.regime_fiscale)}</RegimeFiscale>"
            f"</DatiAnagrafici>"
            f"<Sede>{seller_sede}</Sede>"
            f"</CedentePrestatore>"
            f"<CessionarioCommittente>"
            f"<DatiAnagrafici>"
            f"{buyer_id_xml}"
            f"{buyer_cf_xml}"
            f"<Anagrafica>{buyer_ana}</Anagrafica>"
            f"</DatiAnagrafici>"
            f"<Sede>{buyer_sede}</Sede>"
            f"</CessionarioCommittente>"
            f"</FatturaElettronicaHeader>"
            f"<FatturaElettronicaBody>"
            f"<DatiGenerali>"
            f"<DatiGeneraliDocumento>"
            f"<TipoDocumento>{xml_escape(document.invoice_type_code)}</TipoDocumento>"
            f"<Divisa>{xml_escape(document.currency_code)}</Divisa>"
            f"<Data>{document.invoice_date}</Data>"
            f"<Numero>{xml_escape(document.invoice_number)}</Numero>"
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
    """Validates FatturaPA XML against the official AdE XSD schemas v1.2.3.

    Selects FPR12 or FPA12 schema based on the document's `versione` attribute.
    """

    def get_schema_version(self) -> str:
        return "FatturaPA v1.2.3"

    def get_schema_path(self) -> str | None:
        path = _SCHEMAS_DIR / "FatturaPA_FPR12_v1.2.3.xsd"
        return str(path) if path.exists() else None

    def _get_schema_path_for_format(self, formato: str) -> str | None:
        """Resolve the bundled schema file for FPR12 or FPA12.

        Both files share the same ordinary FatturaPA schema content (v1.2.2);
        they differ only in SdI business rules, not in XSD structure.
        """
        filename = "FatturaPA_FPA12_v1.2.3.xsd" if formato == "FPA12" else "FatturaPA_FPR12_v1.2.3.xsd"
        path = _SCHEMAS_DIR / filename
        return str(path) if path.exists() else None

    def validate(self, document_content: str | bytes) -> DocumentValidationResult:
        """Validate FatturaPA XML against the format-appropriate XSD schema using lxml."""
        try:
            from lxml import etree
        except ImportError:
            return DocumentValidationResult(
                valid=False, errors=["lxml is not installed"], warnings=[], metadata={}
            )

        try:
            xml_bytes = document_content.encode("utf-8") if isinstance(document_content, str) else document_content
            xml_doc = safe_fromstring(xml_bytes)
        except etree.XMLSyntaxError as exc:
            return DocumentValidationResult(
                valid=False, errors=[f"XML parse error: {exc}"], warnings=[], metadata={}
            )

        versione = xml_doc.get("versione", "FPR12")
        xsd_path_str = self._get_schema_path_for_format(versione)
        if not xsd_path_str:
            return DocumentValidationResult(
                valid=False, errors=[f"XSD schema not found for format '{versione}'"], warnings=[], metadata={}
            )

        xsd_path = Path(xsd_path_str)
        xmldsig_path = xsd_path.parent / "xmldsig-core-schema.xsd"

        try:
            parser = safe_parser()
            if xmldsig_path.exists():
                class _LocalResolver(etree.Resolver):
                    def resolve(self, url, id, context):
                        if "xmldsig" in url:
                            return self.resolve_filename(str(xmldsig_path), context)
                        return None
                parser.resolvers.add(_LocalResolver())
            xsd_doc = etree.parse(str(xsd_path), parser)
            schema = etree.XMLSchema(xsd_doc)
        except Exception as exc:  # noqa: BLE001 — XSD load can fail in ways lxml doesn't type; surface as a validation result, not a crash
            return DocumentValidationResult(
                valid=False, errors=[f"Failed to load XSD: {exc}"], warnings=[], metadata={}
            )

        if schema.validate(xml_doc):
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
            root = safe_fromstring(xml_bytes)
        except etree.XMLSyntaxError as exc:
            return {"error": f"XML parse error: {exc}"}

        def _txt(el, path: str) -> str | None:
            if el is None:
                return None
            node = el.find(path)
            return node.text if node is not None else None

        versione = root.get("versione", "unknown")
        header = root.find("FatturaElettronicaHeader")
        body_elements = root.findall("FatturaElettronicaBody")

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
                    "codice_fiscale": _txt(cp_an, "CodiceFiscale"),
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

        def _parse_body(body) -> dict:
            dg = body.find("DatiGenerali/DatiGeneraliDocumento")
            body_result: dict = {
                "dati_generali": {
                    "tipo_documento": _txt(dg, "TipoDocumento"),
                    "divisa": _txt(dg, "Divisa"),
                    "data": _txt(dg, "Data"),
                    "numero": _txt(dg, "Numero"),
                    "causale": _txt(dg, "Causale"),
                },
                "dettaglio_linee": [
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
                ],
                "dati_riepilogo": [
                    {
                        "aliquota_iva": _txt(r, "AliquotaIVA"),
                        "natura": _txt(r, "Natura"),
                        "imponibile": _txt(r, "ImponibileImporto"),
                        "imposta": _txt(r, "Imposta"),
                        "esigibilita_iva": _txt(r, "EsigibilitaIVA"),
                    }
                    for r in body.findall("DatiBeniServizi/DatiRiepilogo")
                ],
            }

            dp = body.find("DatiPagamento")
            if dp is not None:
                ddp = dp.find("DettaglioPagamento")
                body_result["dati_pagamento"] = {
                    "condizioni_pagamento": _txt(dp, "CondizioniPagamento"),
                    "modalita_pagamento": _txt(ddp, "ModalitaPagamento"),
                    "importo_pagamento": _txt(ddp, "ImportoPagamento"),
                    "data_scadenza": _txt(ddp, "DataScadenzaPagamento"),
                    "iban": _txt(ddp, "IBAN"),
                }

            return body_result

        bodies = [_parse_body(body) for body in body_elements]
        if bodies:
            result["body"] = bodies[0]
            result["bodies"] = bodies

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
        valid, error = TaxIdentifier.validate_it_partita_iva(piva)
        if not valid:
            return {"valid": False, "value": piva, "error": error}
        return {"valid": True, "value": piva}
