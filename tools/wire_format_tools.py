"""
EN 16931 wire-format tools for mcp-fattura-elettronica-it: UBL 2.1 and CII.

Implements IT-SC-15/16 (generate) and IT-SC-17/18 (parse, validate):
  • generate_ubl_invoice  — ItalianInvoice → UBL 2.1 XML
  • generate_cii_invoice  — ItalianInvoice → CII CrossIndustryInvoice XML
  • validate_ubl_invoice  — structural validation of UBL XML
  • parse_ubl_invoice     — UBL XML → EN 16931 field dict
  • validate_cii_invoice  — structural validation of CII XML
  • parse_cii_invoice     — CII XML → EN 16931 field dict

These tools operate on the EN 16931 core invoice tree (ItalianInvoice subclasses
EN16931Invoice). They complement the FatturaPA workflow but produce different
wire formats; use them for cross-border or Peppol-routed invoices, not for
direct SdI submission (which requires FatturaPA XML — use generate_fattura_xml).
"""

from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field, ValidationError

from mcp_einvoicing_core.logging_utils import get_logger
from mcp_einvoicing_core.wire_formats import (
    EN16931CIIParser,
    EN16931CIISerializer,
    EN16931UBLParser,
    EN16931UBLSerializer,
)
from models import ItalianInvoice

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# IT-specific subclasses (extension point for future national fields)
# ---------------------------------------------------------------------------


class _ITUBLSerializer(EN16931UBLSerializer):
    """UBL 2.1 serialiser for ItalianInvoice.

    Inherits full EN 16931 UBL serialisation from core. Italian-national fields
    (progressivo_invio, codice_destinatario, regime_fiscale) are not part of
    the UBL 2.1 Invoice schema and are intentionally omitted. They belong in
    the FatturaPA DatiTrasmissione wrapper, which is only used for SdI routing.
    """


class _ITCIISerializer(EN16931CIISerializer):
    """CII serialiser for ItalianInvoice. Same policy as _ITUBLSerializer."""


class _ITUBLParser(EN16931UBLParser):
    """UBL 2.1 parser that returns an ItalianInvoice (IT defaults applied)."""

    def parse(self, xml_bytes: bytes) -> ItalianInvoice:  # type: ignore[override]
        base = super().parse(xml_bytes)
        return ItalianInvoice(**base.model_dump())


class _ITCIIParser(EN16931CIIParser):
    """CII parser that returns an ItalianInvoice (IT defaults applied)."""

    def parse(self, xml_bytes: bytes) -> ItalianInvoice:  # type: ignore[override]
        base = super().parse(xml_bytes)
        return ItalianInvoice(**base.model_dump())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _invoice_to_dict(inv: ItalianInvoice) -> dict:
    """Convert ItalianInvoice to a JSON-serialisable dict (dates as ISO strings)."""
    data = inv.model_dump(mode="json")
    return data


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------


def register_wire_format_tools(mcp: FastMCP) -> None:
    """Register the 6 EN 16931 wire-format tools on the FastMCP instance."""

    @mcp.tool()
    def generate_ubl_invoice(
        invoice_data: Annotated[
            dict,
            Field(
                description=(
                    "ItalianInvoice-compatible dict to serialise to UBL 2.1 XML. "
                    "Required top-level fields: profile (str, BT-24 customisation ID), "
                    "invoice_number (str), invoice_date (ISO 8601 date string), "
                    "invoice_type_code (str, '380' invoice / '381' credit note), "
                    "currency_code (str, 'EUR'), "
                    "seller (dict with name, address), buyer (dict with name, address), "
                    "line_items (list of line dicts), tax_lines (list of tax dicts), "
                    "sum_of_line_net_amounts, tax_exclusive_amount, tax_total, "
                    "tax_inclusive_amount, amount_due (all Decimal-compatible strings or numbers). "
                    "Optional: note, buyer_reference, payment_means, due_date, "
                    "progressivo_invio, codice_destinatario, regime_fiscale. "
                    "address fields: line_one, city, postcode, country_code (2-char ISO). "
                    "party fields: name (str), vat_id (optional, with country prefix, e.g. 'IT01234567890'). "
                    "line fields: line_id, name, quantity, unit_code, unit_price, "
                    "line_net_amount, tax_category (UNCL5305, e.g. 'S'), tax_rate (%, e.g. 22). "
                    "tax fields: category, rate, taxable_amount, tax_amount."
                )
            ),
        ],
    ) -> dict:
        """Generate a UBL 2.1 Invoice XML document from an ItalianInvoice dict.

        Use this for cross-border B2B invoices or Peppol-routed documents.
        This tool does NOT produce FatturaPA XML; use generate_fattura_xml()
        for SdI submission.

        Italian national fields (progressivo_invio, codice_destinatario,
        regime_fiscale) are accepted in the input dict but are not emitted
        in the UBL output — they belong in the FatturaPA DatiTrasmissione header.

        profile (BT-24) should be the Peppol BIS Billing 3.0 customisation ID
        ('urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0')
        or the EN 16931 core profile ('urn:cen.eu:en16931:2017') for non-Peppol use.
        [Inference: FatturaPA-specific CIUS URN not yet standardised for UBL; verify
        with AdE if UBL submission to an IT-specific platform is intended.]

        On success returns {'xml': str, 'length_bytes': int, 'format': 'UBL-2.1'}.
        On validation error returns {'error': str, 'details': list[str]}.
        On unexpected error returns {'error': str}.
        """
        try:
            invoice = ItalianInvoice.model_validate(invoice_data)
        except ValidationError as exc:
            errors = [str(e["msg"]) for e in exc.errors()]
            return {"error": "Invoice validation failed.", "details": errors}
        except Exception as exc:
            return {"error": f"Failed to parse invoice_data: {exc}"}

        try:
            xml_bytes = _ITUBLSerializer().serialize(invoice)
            xml_str = xml_bytes.decode("utf-8")
            return {
                "xml": xml_str,
                "length_bytes": len(xml_bytes),
                "format": "UBL-2.1",
            }
        except Exception as exc:
            logger.exception("UBL serialisation failed")
            return {"error": f"UBL serialisation failed: {exc}"}

    @mcp.tool()
    def generate_cii_invoice(
        invoice_data: Annotated[
            dict,
            Field(
                description=(
                    "ItalianInvoice-compatible dict to serialise to CII XML "
                    "(UN/CEFACT CrossIndustryInvoice D16B). "
                    "Same field requirements as generate_ubl_invoice(). "
                    "profile (BT-24) for Factur-X / ZUGFeRD-compatible output: "
                    "'urn:cen.eu:en16931:2017#conformant#urn:factur-x.eu:1p0:extended' "
                    "(Extended) or 'urn:cen.eu:en16931:2017' (EN 16931 core). "
                    "[Inference: profile URN for FatturaPA extended via CII not yet "
                    "standardised; verify with AdE before production use.]"
                )
            ),
        ],
    ) -> dict:
        """Generate a CII CrossIndustryInvoice XML document from an ItalianInvoice dict.

        Use this when a CII (UN/CEFACT) wire format is required — for example,
        for Factur-X embedded XML or ZUGFeRD-compatible output.
        This tool does NOT produce FatturaPA XML; use generate_fattura_xml()
        for SdI submission.

        Italian national fields are accepted but not emitted (same policy as
        generate_ubl_invoice).

        On success returns {'xml': str, 'length_bytes': int, 'format': 'CII-D16B'}.
        On validation error returns {'error': str, 'details': list[str]}.
        On unexpected error returns {'error': str}.
        """
        try:
            invoice = ItalianInvoice.model_validate(invoice_data)
        except ValidationError as exc:
            errors = [str(e["msg"]) for e in exc.errors()]
            return {"error": "Invoice validation failed.", "details": errors}
        except Exception as exc:
            return {"error": f"Failed to parse invoice_data: {exc}"}

        try:
            xml_bytes = _ITCIISerializer().serialize(invoice)
            xml_str = xml_bytes.decode("utf-8")
            return {
                "xml": xml_str,
                "length_bytes": len(xml_bytes),
                "format": "CII-D16B",
            }
        except Exception as exc:
            logger.exception("CII serialisation failed")
            return {"error": f"CII serialisation failed: {exc}"}

    @mcp.tool()
    def validate_ubl_invoice(
        xml_string: Annotated[
            str,
            Field(
                description=(
                    "UBL 2.1 Invoice or CreditNote XML string to validate. "
                    "Must contain a root element in the UBL Invoice-2 or CreditNote-2 namespace."
                )
            ),
        ],
    ) -> dict:
        """Validate a UBL 2.1 invoice XML string for structural correctness.

        Performs structural validation by parsing the XML into an EN16931Invoice
        and checking that required core fields (invoice_number, invoice_date,
        seller, buyer, at least one line item) are present and non-empty.

        Note: this tool does NOT validate against the normative UBL 2.1 XSD schema
        (the UBL XSD files are not bundled with this package). For full XSD
        validation use a dedicated UBL validator or the Peppol Validator tool.

        On success returns {'valid': true, 'warnings': list[str]}.
        On failure returns {'valid': false, 'errors': list[str]}.
        On parse error returns {'valid': false, 'errors': ['XML parse error: ...']}.
        """
        try:
            xml_bytes = xml_string.encode("utf-8") if isinstance(xml_string, str) else xml_string
            invoice = _ITUBLParser().parse(xml_bytes)
        except Exception as exc:
            return {"valid": False, "errors": [f"XML parse error: {exc}"]}

        errors: list[str] = []
        warnings: list[str] = []

        if not invoice.invoice_number:
            errors.append("Missing invoice_number (BT-1 / cbc:ID).")
        if not invoice.seller or not invoice.seller.name:
            errors.append("Missing seller name (BT-27).")
        if not invoice.buyer or not invoice.buyer.name:
            errors.append("Missing buyer name (BT-44).")
        if not invoice.line_items:
            errors.append("No line items found.")
        if not invoice.tax_lines:
            warnings.append("No tax subtotals found (BG-23). Document may be incomplete.")

        if errors:
            return {"valid": False, "errors": errors}
        return {"valid": True, "warnings": warnings}

    @mcp.tool()
    def parse_ubl_invoice(
        xml_string: Annotated[
            str,
            Field(
                description=(
                    "UBL 2.1 Invoice or CreditNote XML string to parse. "
                    "Returns an EN 16931 field dict. National extensions are silently ignored."
                )
            ),
        ],
    ) -> dict:
        """Parse a UBL 2.1 invoice XML string into an EN 16931 structured dict.

        Extracts the EN 16931 core field set. Italian national fields
        (progressivo_invio, regime_fiscale, etc.) are returned with their
        ItalianInvoice defaults since UBL 2.1 does not carry them.

        Use this to inspect cross-border invoices received in UBL format, or to
        round-trip the output of generate_ubl_invoice() for verification.

        On success returns the ItalianInvoice fields as a JSON-serialisable dict.
        On failure returns {'error': str}.
        """
        try:
            xml_bytes = xml_string.encode("utf-8") if isinstance(xml_string, str) else xml_string
            invoice = _ITUBLParser().parse(xml_bytes)
            return _invoice_to_dict(invoice)
        except Exception as exc:
            logger.exception("UBL parse failed")
            return {"error": f"UBL parse failed: {exc}"}

    @mcp.tool()
    def validate_cii_invoice(
        xml_string: Annotated[
            str,
            Field(
                description=(
                    "CII CrossIndustryInvoice XML string to validate. "
                    "Must contain a root rsm:CrossIndustryInvoice element."
                )
            ),
        ],
    ) -> dict:
        """Validate a CII CrossIndustryInvoice XML string for structural correctness.

        Performs structural validation by parsing the XML into an EN16931Invoice
        and checking that required core fields are present and non-empty.

        Note: this tool does NOT validate against the normative CII D16B XSD schema.
        For full schema validation use a dedicated CII or ZUGFeRD validator.

        On success returns {'valid': true, 'warnings': list[str]}.
        On failure returns {'valid': false, 'errors': list[str]}.
        On parse error returns {'valid': false, 'errors': ['XML parse error: ...']}.
        """
        try:
            xml_bytes = xml_string.encode("utf-8") if isinstance(xml_string, str) else xml_string
            invoice = _ITCIIParser().parse(xml_bytes)
        except Exception as exc:
            return {"valid": False, "errors": [f"XML parse error: {exc}"]}

        errors: list[str] = []
        warnings: list[str] = []

        if not invoice.invoice_number:
            errors.append("Missing invoice_number (BT-1 / ram:ID).")
        if not invoice.seller or not invoice.seller.name:
            errors.append("Missing seller name (BT-27).")
        if not invoice.buyer or not invoice.buyer.name:
            errors.append("Missing buyer name (BT-44).")
        if not invoice.line_items:
            errors.append("No line items found.")
        if not invoice.tax_lines:
            warnings.append("No tax subtotals found (BG-23). Document may be incomplete.")

        if errors:
            return {"valid": False, "errors": errors}
        return {"valid": True, "warnings": warnings}

    @mcp.tool()
    def parse_cii_invoice(
        xml_string: Annotated[
            str,
            Field(
                description=(
                    "CII CrossIndustryInvoice XML string to parse. "
                    "Returns an EN 16931 field dict. National extensions are silently ignored."
                )
            ),
        ],
    ) -> dict:
        """Parse a CII CrossIndustryInvoice XML string into an EN 16931 structured dict.

        Extracts the EN 16931 core field set. Italian national fields are returned
        with their ItalianInvoice defaults since CII does not carry them.

        Use this to inspect Factur-X / ZUGFeRD invoices, or to round-trip the output
        of generate_cii_invoice() for verification.

        On success returns the ItalianInvoice fields as a JSON-serialisable dict.
        On failure returns {'error': str}.
        """
        try:
            xml_bytes = xml_string.encode("utf-8") if isinstance(xml_string, str) else xml_string
            invoice = _ITCIIParser().parse(xml_bytes)
            return _invoice_to_dict(invoice)
        except Exception as exc:
            logger.exception("CII parse failed")
            return {"error": f"CII parse failed: {exc}"}
