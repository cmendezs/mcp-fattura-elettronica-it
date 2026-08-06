"""
Tests for tools/adapters.py — FatturaGenerator, FatturaValidator, FatturaParser,
ItalyPartyValidator.

Covers IT-SC-21: UNCL5305 -> Natura resolution via resolve_natura(), including
the DocumentGenerationError escape-hatch path for ambiguous UNCL5305 codes.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from mcp_einvoicing_core.en16931 import EN16931Address, EN16931Party
from mcp_einvoicing_core.exceptions import DocumentGenerationError

from mcp_fattura_elettronica_it.models import ItalianInvoice, ItalianLineItem, ItalianTax
from mcp_fattura_elettronica_it.tools.adapters import FatturaGenerator, FatturaParser

SELLER = EN16931Party(
    name="ACME Srl",
    address=EN16931Address(line_one="Via Roma 1", city="Roma", postcode="00100", country_code="IT"),
    vat_id="IT01234567897",
)

BUYER = EN16931Party(
    name="Buyer Srl",
    address=EN16931Address(line_one="Via Verdi 2", city="Milano", postcode="20100", country_code="IT"),
    vat_id="IT98765432109",
)


def _invoice(line_items, tax_lines) -> ItalianInvoice:
    return ItalianInvoice(
        profile="urn:cen.eu:en16931:2017",
        invoice_number="2026/001",
        invoice_date="2026-01-15",
        seller=SELLER,
        buyer=BUYER,
        sum_of_line_net_amounts=Decimal("1000.00"),
        tax_exclusive_amount=Decimal("1000.00"),
        tax_total=Decimal("0.00"),
        tax_inclusive_amount=Decimal("1000.00"),
        amount_due=Decimal("1000.00"),
        line_items=line_items,
        tax_lines=tax_lines,
        progressivo_invio="00001",
        codice_destinatario="ABC123",
        formato_trasmissione="FPR12",
    )


class TestFatturaGeneratorNaturaResolution:
    def test_exempt_line_resolves_to_n4(self):
        """IT-SC-21: tax_category 'E' resolves to Natura N4 without an explicit override."""
        line = ItalianLineItem(
            line_id="1",
            name="Prestazione esente",
            quantity=Decimal(1),
            unit_code="EA",
            unit_price=Decimal("1000.00"),
            line_net_amount=Decimal("1000.00"),
            tax_category="E",
            tax_rate=Decimal("0.00"),
        )
        tax = ItalianTax(
            category="E",
            rate=Decimal("0.00"),
            taxable_amount=Decimal("1000.00"),
            tax_amount=Decimal("0.00"),
        )
        invoice = _invoice([line], [tax])

        xml = FatturaGenerator().generate(invoice)

        assert "<Natura>N4</Natura>" in xml

    def test_ambiguous_category_without_explicit_natura_raises(self):
        """IT-SC-21: 'AE' (reverse charge) has no unambiguous Natura mapping."""
        line = ItalianLineItem(
            line_id="1",
            name="Subappalto edile",
            quantity=Decimal(1),
            unit_code="EA",
            unit_price=Decimal("1000.00"),
            line_net_amount=Decimal("1000.00"),
            tax_category="AE",
            tax_rate=Decimal("0.00"),
        )
        tax = ItalianTax(
            category="AE",
            rate=Decimal("0.00"),
            taxable_amount=Decimal("1000.00"),
            tax_amount=Decimal("0.00"),
        )
        invoice = _invoice([line], [tax])

        with pytest.raises(DocumentGenerationError):
            FatturaGenerator().generate(invoice)

    def test_ambiguous_category_with_explicit_natura_succeeds(self):
        """IT-SC-21: explicit natura on the line item is the escape hatch for 'AE'."""
        line = ItalianLineItem(
            line_id="1",
            name="Subappalto edile",
            quantity=Decimal(1),
            unit_code="EA",
            unit_price=Decimal("1000.00"),
            line_net_amount=Decimal("1000.00"),
            tax_category="AE",
            tax_rate=Decimal("0.00"),
            natura="N6.3",
        )
        tax = ItalianTax(
            category="AE",
            rate=Decimal("0.00"),
            taxable_amount=Decimal("1000.00"),
            tax_amount=Decimal("0.00"),
            natura="N6.3",
        )
        invoice = _invoice([line], [tax])

        xml = FatturaGenerator().generate(invoice)

        assert "<Natura>N6.3</Natura>" in xml

    def test_multi_body_fpa12_parses_to_two_bodies(self):
        """IT-LC-4: FatturaParser parses a multi-body FPA12 file into two bodies."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<p:FatturaElettronica versione="FPA12" xmlns:p="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2">
<FatturaElettronicaHeader><DatiTrasmissione><ProgressivoInvio>00001</ProgressivoInvio></DatiTrasmissione></FatturaElettronicaHeader>
<FatturaElettronicaBody><DatiGenerali><DatiGeneraliDocumento><Numero>2026/001</Numero></DatiGeneraliDocumento></DatiGenerali></FatturaElettronicaBody>
<FatturaElettronicaBody><DatiGenerali><DatiGeneraliDocumento><Numero>2026/002</Numero></DatiGeneraliDocumento></DatiGenerali></FatturaElettronicaBody>
</p:FatturaElettronica>"""

        result = FatturaParser().parse(xml)

        assert len(result["bodies"]) == 2
        assert result["body"] == result["bodies"][0]
        assert result["bodies"][0]["dati_generali"]["numero"] == "2026/001"
        assert result["bodies"][1]["dati_generali"]["numero"] == "2026/002"

    def test_standard_rate_emits_no_natura(self):
        """IT-SC-21: 'S' (standard rate) never emits a Natura element."""
        line = ItalianLineItem(
            line_id="1",
            name="Consulenza",
            quantity=Decimal(1),
            unit_code="EA",
            unit_price=Decimal("1000.00"),
            line_net_amount=Decimal("1000.00"),
            tax_category="S",
            tax_rate=Decimal("22.00"),
        )
        tax = ItalianTax(
            category="S",
            rate=Decimal("22.00"),
            taxable_amount=Decimal("1000.00"),
            tax_amount=Decimal("220.00"),
        )
        invoice = _invoice([line], [tax])

        xml = FatturaGenerator().generate(invoice)

        assert "<Natura>" not in xml
