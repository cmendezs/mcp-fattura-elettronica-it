"""
Tests for tools/wire_format_tools.py — UBL 2.1 and CII generation, validation, parsing.

Covers: generate → parse round-trips, validation success/failure, missing-field errors.
"""

from __future__ import annotations

import asyncio

from fastmcp import FastMCP
from mcp_fattura_elettronica_it.tools.wire_format_tools import register_wire_format_tools

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

_mcp = FastMCP(name="test-wire-formats")
register_wire_format_tools(_mcp)


async def _get_tools():
    tools = await _mcp.list_tools()
    return {t.name: t.fn for t in tools}


_tools = asyncio.run(_get_tools())


def call(name: str, **kwargs):
    return _tools[name](**kwargs)


# ---------------------------------------------------------------------------
# Minimal valid invoice fixture
# ---------------------------------------------------------------------------

_ADDRESS = {
    "line_one": "Via Roma 1",
    "city": "Milano",
    "postcode": "20121",
    "country_code": "IT",
}

_SELLER = {
    "name": "Acme IT Srl",
    "vat_id": "IT01234567897",
    "address": _ADDRESS,
}

_BUYER = {
    "name": "Cliente SpA",
    "vat_id": "IT09876543217",
    "address": _ADDRESS,
}

_LINE = {
    "line_id": "1",
    "name": "Servizio consulenza",
    "quantity": "1",
    "unit_code": "C62",
    "unit_price": "1000.00",
    "line_net_amount": "1000.00",
    "tax_category": "S",
    "tax_rate": "22",
}

_TAX = {
    "category": "S",
    "rate": "22",
    "taxable_amount": "1000.00",
    "tax_amount": "220.00",
}

_MINIMAL_INVOICE = {
    "profile": "urn:cen.eu:en16931:2017",
    "invoice_number": "IT-2026-001",
    "invoice_date": "2026-05-31",
    "invoice_type_code": "380",
    "currency_code": "EUR",
    "seller": _SELLER,
    "buyer": _BUYER,
    "line_items": [_LINE],
    "tax_lines": [_TAX],
    "sum_of_line_net_amounts": "1000.00",
    "tax_exclusive_amount": "1000.00",
    "tax_total": "220.00",
    "tax_inclusive_amount": "1220.00",
    "allowances_total": "0.00",
    "charges_total": "0.00",
    "prepaid_amount": "0.00",
    "rounding_amount": "0.00",
    "amount_due": "1220.00",
}


# ---------------------------------------------------------------------------
# generate_ubl_invoice
# ---------------------------------------------------------------------------


class TestGenerateUBL:
    def test_success_returns_xml(self):
        result = call("generate_ubl_invoice", invoice_data=_MINIMAL_INVOICE)
        assert "error" not in result
        assert "xml" in result
        assert result["format"] == "UBL-2.1"
        assert result["length_bytes"] > 0

    def test_xml_contains_required_ubl_elements(self):
        result = call("generate_ubl_invoice", invoice_data=_MINIMAL_INVOICE)
        xml = result["xml"]
        assert "Invoice" in xml
        assert "IT-2026-001" in xml
        assert "Acme IT Srl" in xml
        assert "Cliente SpA" in xml

    def test_invalid_invoice_returns_error(self):
        result = call("generate_ubl_invoice", invoice_data={"invoice_number": "X"})
        assert "error" in result

    def test_credit_note_type_code(self):
        data = {**_MINIMAL_INVOICE, "invoice_type_code": "381"}
        result = call("generate_ubl_invoice", invoice_data=data)
        assert "error" not in result
        assert "CreditNote" in result["xml"]


# ---------------------------------------------------------------------------
# generate_cii_invoice
# ---------------------------------------------------------------------------


class TestGenerateCII:
    def test_success_returns_xml(self):
        result = call("generate_cii_invoice", invoice_data=_MINIMAL_INVOICE)
        assert "error" not in result
        assert "xml" in result
        assert result["format"] == "CII-D16B"
        assert result["length_bytes"] > 0

    def test_xml_contains_required_cii_elements(self):
        result = call("generate_cii_invoice", invoice_data=_MINIMAL_INVOICE)
        xml = result["xml"]
        assert "CrossIndustryInvoice" in xml
        assert "IT-2026-001" in xml
        assert "Acme IT Srl" in xml

    def test_invalid_invoice_returns_error(self):
        result = call("generate_cii_invoice", invoice_data={"profile": "x"})
        assert "error" in result


# ---------------------------------------------------------------------------
# validate_ubl_invoice
# ---------------------------------------------------------------------------


class TestValidateUBL:
    def _get_ubl_xml(self) -> str:
        return call("generate_ubl_invoice", invoice_data=_MINIMAL_INVOICE)["xml"]

    def test_valid_ubl_passes(self):
        xml = self._get_ubl_xml()
        result = call("validate_ubl_invoice", xml_string=xml)
        assert result["valid"] is True

    def test_invalid_xml_fails(self):
        result = call("validate_ubl_invoice", xml_string="<not-valid-xml")
        assert result["valid"] is False
        assert result["errors"]

    def test_empty_xml_fails(self):
        result = call("validate_ubl_invoice", xml_string="")
        assert result["valid"] is False


# ---------------------------------------------------------------------------
# parse_ubl_invoice
# ---------------------------------------------------------------------------


class TestParseUBL:
    def _get_ubl_xml(self) -> str:
        return call("generate_ubl_invoice", invoice_data=_MINIMAL_INVOICE)["xml"]

    def test_round_trip_invoice_number(self):
        xml = self._get_ubl_xml()
        result = call("parse_ubl_invoice", xml_string=xml)
        assert "error" not in result
        assert result["invoice_number"] == "IT-2026-001"

    def test_round_trip_seller_name(self):
        xml = self._get_ubl_xml()
        result = call("parse_ubl_invoice", xml_string=xml)
        assert result["seller"]["name"] == "Acme IT Srl"

    def test_round_trip_line_count(self):
        xml = self._get_ubl_xml()
        result = call("parse_ubl_invoice", xml_string=xml)
        assert len(result["line_items"]) == 1

    def test_invalid_xml_returns_error(self):
        result = call("parse_ubl_invoice", xml_string="<bad>")
        assert "error" in result


# ---------------------------------------------------------------------------
# validate_cii_invoice
# ---------------------------------------------------------------------------


class TestValidateCII:
    def _get_cii_xml(self) -> str:
        return call("generate_cii_invoice", invoice_data=_MINIMAL_INVOICE)["xml"]

    def test_valid_cii_passes(self):
        xml = self._get_cii_xml()
        result = call("validate_cii_invoice", xml_string=xml)
        assert result["valid"] is True

    def test_invalid_xml_fails(self):
        result = call("validate_cii_invoice", xml_string="<garbage")
        assert result["valid"] is False

    def test_empty_xml_fails(self):
        result = call("validate_cii_invoice", xml_string="")
        assert result["valid"] is False


# ---------------------------------------------------------------------------
# parse_cii_invoice
# ---------------------------------------------------------------------------


class TestParseCII:
    def _get_cii_xml(self) -> str:
        return call("generate_cii_invoice", invoice_data=_MINIMAL_INVOICE)["xml"]

    def test_round_trip_invoice_number(self):
        xml = self._get_cii_xml()
        result = call("parse_cii_invoice", xml_string=xml)
        assert "error" not in result
        assert result["invoice_number"] == "IT-2026-001"

    def test_round_trip_seller_name(self):
        xml = self._get_cii_xml()
        result = call("parse_cii_invoice", xml_string=xml)
        assert result["seller"]["name"] == "Acme IT Srl"

    def test_round_trip_line_count(self):
        xml = self._get_cii_xml()
        result = call("parse_cii_invoice", xml_string=xml)
        assert len(result["line_items"]) == 1

    def test_invalid_xml_returns_error(self):
        result = call("parse_cii_invoice", xml_string="<bad>")
        assert "error" in result
