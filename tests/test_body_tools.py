"""
Tests for tools/body_tools.py — FatturaElettronicaBody tools.

Covers happy path, validation errors, and edge cases for all 7 body tools.
"""

from __future__ import annotations

import base64

import asyncio

import pytest

from fastmcp import FastMCP
from tools.body_tools import NATURA_CODES, TIPO_DOCUMENTO, register_body_tools

# ---------------------------------------------------------------------------
# Helper setup
# ---------------------------------------------------------------------------

_mcp = FastMCP(name="test-body")
register_body_tools(_mcp)


async def _get_tools():
    tools = await _mcp.list_tools()
    return {t.name: t.fn for t in tools}


_tools = asyncio.run(_get_tools())


def call(name: str, **kwargs):
    return _tools[name](**kwargs)


# ---------------------------------------------------------------------------
# build_dati_generali
# ---------------------------------------------------------------------------


class TestBuildDatiGenerali:
    def test_happy_path_td01(self):
        result = call(
            "build_dati_generali",
            tipo_documento="TD01",
            data="2026-01-15",
            numero="2026/001",
            divisa="EUR",
        )
        dg = result["DatiGenerali"]["DatiGeneraliDocumento"]
        assert dg["TipoDocumento"] == "TD01"
        assert dg["Data"] == "2026-01-15"
        assert dg["Numero"] == "2026/001"
        assert dg["Divisa"] == "EUR"

    def test_with_causale(self):
        result = call(
            "build_dati_generali",
            tipo_documento="TD01",
            data="2026-01-15",
            numero="001",
            causale="Consulenza gennaio 2026",
        )
        dg = result["DatiGenerali"]["DatiGeneraliDocumento"]
        assert dg["Causale"] == "Consulenza gennaio 2026"

    def test_with_documento_riferimento(self):
        result = call(
            "build_dati_generali",
            tipo_documento="TD04",
            data="2026-02-01",
            numero="NC001",
            id_documento_riferimento="2026/001",
            data_documento_riferimento="2026-01-15",
        )
        assert "DatiFattureCollegate" in result["DatiGenerali"]
        assert result["DatiGenerali"]["DatiFattureCollegate"]["IdDocumento"] == "2026/001"

    def test_invalid_tipo_documento(self):
        result = call(
            "build_dati_generali",
            tipo_documento="TD99",
            data="2026-01-15",
            numero="001",
        )
        assert "error" in result

    def test_invalid_date_format(self):
        result = call(
            "build_dati_generali",
            tipo_documento="TD01",
            data="15/01/2026",
            numero="001",
        )
        assert "error" in result

    def test_numero_too_long(self):
        result = call(
            "build_dati_generali",
            tipo_documento="TD01",
            data="2026-01-15",
            numero="A" * 21,
        )
        assert "error" in result

    def test_causale_truncated_at_200_chars(self):
        long_causale = "X" * 300
        result = call(
            "build_dati_generali",
            tipo_documento="TD01",
            data="2026-01-15",
            numero="001",
            causale=long_causale,
        )
        dg = result["DatiGenerali"]["DatiGeneraliDocumento"]
        assert len(dg["Causale"]) == 200


# ---------------------------------------------------------------------------
# get_tipo_documento_codes
# ---------------------------------------------------------------------------


class TestGetTipoDocumentoCodes:
    def test_returns_all_codes(self):
        result = call("get_tipo_documento_codes")
        assert result["total"] == len(TIPO_DOCUMENTO)
        codes = {c["code"] for c in result["codes"]}
        assert "TD01" in codes
        assert "TD28" in codes

    def test_each_entry_has_use_case(self):
        result = call("get_tipo_documento_codes")
        for entry in result["codes"]:
            assert entry["use_case"]


# ---------------------------------------------------------------------------
# add_linea_dettaglio
# ---------------------------------------------------------------------------


class TestAddLineaDettaglio:
    def test_happy_path_standard_line(self):
        result = call(
            "add_linea_dettaglio",
            numero_linea=1,
            descrizione="Consulenza informatica",
            quantita=8.0,
            unita_misura="ORE",
            prezzo_unitario=100.0,
            prezzo_totale=800.0,
            aliquota_iva=22.0,
        )
        linea = result["DettaglioLinee"]
        assert linea["NumeroLinea"] == 1
        assert linea["AliquotaIVA"] == "22.00"
        assert linea["Quantita"] == "8"
        assert linea["UnitaMisura"] == "ORE"

    def test_zero_vat_requires_natura(self):
        result = call(
            "add_linea_dettaglio",
            numero_linea=1,
            descrizione="Prestazione esente",
            prezzo_unitario=500.0,
            prezzo_totale=500.0,
            aliquota_iva=0.0,
        )
        assert "error" in result
        assert "Natura" in result["error"]

    def test_zero_vat_with_natura(self):
        result = call(
            "add_linea_dettaglio",
            numero_linea=1,
            descrizione="Esportazione",
            prezzo_unitario=1000.0,
            prezzo_totale=1000.0,
            aliquota_iva=0.0,
            natura="N3.1",
        )
        linea = result["DettaglioLinee"]
        assert linea["Natura"] == "N3.1"
        assert linea["AliquotaIVA"] == "0.00"

    def test_invalid_natura_code(self):
        result = call(
            "add_linea_dettaglio",
            numero_linea=1,
            descrizione="Test",
            prezzo_unitario=100.0,
            prezzo_totale=100.0,
            aliquota_iva=0.0,
            natura="N99",
        )
        assert "error" in result

    def test_ritenuta_flag(self):
        result = call(
            "add_linea_dettaglio",
            numero_linea=1,
            descrizione="Parcella professionale",
            prezzo_unitario=1000.0,
            prezzo_totale=1000.0,
            aliquota_iva=22.0,
            ritenuta="SI",
        )
        assert result["DettaglioLinee"]["Ritenuta"] == "SI"

    def test_descrizione_truncated_at_1000(self):
        result = call(
            "add_linea_dettaglio",
            numero_linea=1,
            descrizione="X" * 1500,
            prezzo_unitario=100.0,
            prezzo_totale=100.0,
            aliquota_iva=22.0,
        )
        assert len(result["DettaglioLinee"]["Descrizione"]) == 1000

    def test_service_line_without_quantita(self):
        result = call(
            "add_linea_dettaglio",
            numero_linea=1,
            descrizione="Canone mensile",
            prezzo_unitario=500.0,
            prezzo_totale=500.0,
            aliquota_iva=22.0,
        )
        assert "Quantita" not in result["DettaglioLinee"]


# ---------------------------------------------------------------------------
# compute_totali
# ---------------------------------------------------------------------------


class TestComputeTotali:
    def test_single_vat_rate(self):
        linee = [
            {"prezzo_totale": 1000.0, "aliquota_iva": 22.0},
            {"prezzo_totale": 500.0, "aliquota_iva": 22.0},
        ]
        result = call("compute_totali", linee=linee)
        assert result["totale_imponibile"] == "1500.00"
        assert result["totale_imposta"] == "330.00"
        assert result["totale_fattura"] == "1830.00"

    def test_mixed_vat_rates(self):
        linee = [
            {"prezzo_totale": 1000.0, "aliquota_iva": 22.0},
            {"prezzo_totale": 200.0, "aliquota_iva": 10.0},
        ]
        result = call("compute_totali", linee=linee)
        assert len(result["DatiRiepilogo"]) == 2
        assert result["totale_fattura"] == "1440.00"

    def test_zero_vat_natura(self):
        linee = [
            {"prezzo_totale": 500.0, "aliquota_iva": 0.0, "natura": "N3.1"},
        ]
        result = call("compute_totali", linee=linee)
        riepilogo = result["DatiRiepilogo"][0]
        assert riepilogo["Imposta"] == "0.00"
        assert riepilogo["Natura"] == "N3.1"

    def test_empty_linee_returns_zero(self):
        result = call("compute_totali", linee=[])
        assert result["totale_fattura"] == "0.00"
        assert result["DatiRiepilogo"] == []


# ---------------------------------------------------------------------------
# get_natura_codes
# ---------------------------------------------------------------------------


class TestGetNaturaCodes:
    def test_returns_all_codes(self):
        result = call("get_natura_codes")
        assert result["total"] == len(NATURA_CODES)

    def test_contains_reverse_charge(self):
        result = call("get_natura_codes")
        codes = {c["code"] for c in result["codes"]}
        assert "N6" in codes
        assert "N6.1" in codes
        assert "N6.9" in codes

    def test_each_entry_has_legal_ref(self):
        result = call("get_natura_codes")
        for entry in result["codes"]:
            assert entry["legal_ref"]


# ---------------------------------------------------------------------------
# build_dati_pagamento
# ---------------------------------------------------------------------------


class TestBuildDatiPagamento:
    def test_happy_path_bank_transfer(self):
        result = call(
            "build_dati_pagamento",
            condizioni_pagamento="TP02",
            modalita_pagamento="MP05",
            importo_pagamento=1830.0,
            iban="IT60X0542811101000000123456",
            data_scadenza_pagamento="2026-02-28",
        )
        p = result["DatiPagamento"]
        assert p["CondizioniPagamento"] == "TP02"
        dp = p["DettaglioPagamento"]
        assert dp["ModalitaPagamento"] == "MP05"
        assert dp["IBAN"] == "IT60X0542811101000000123456"

    def test_invalid_condizioni(self):
        result = call(
            "build_dati_pagamento",
            condizioni_pagamento="TP99",
            modalita_pagamento="MP05",
            importo_pagamento=100.0,
        )
        assert "error" in result

    def test_invalid_modalita(self):
        result = call(
            "build_dati_pagamento",
            condizioni_pagamento="TP02",
            modalita_pagamento="MP99",
            importo_pagamento=100.0,
        )
        assert "error" in result

    def test_invalid_iban(self):
        result = call(
            "build_dati_pagamento",
            condizioni_pagamento="TP02",
            modalita_pagamento="MP05",
            importo_pagamento=100.0,
            iban="NOT_AN_IBAN",
        )
        assert "error" in result

    def test_invalid_due_date_format(self):
        result = call(
            "build_dati_pagamento",
            condizioni_pagamento="TP02",
            modalita_pagamento="MP01",
            importo_pagamento=100.0,
            data_scadenza_pagamento="28-02-2026",
        )
        assert "error" in result

    def test_pagopa_payment_method(self):
        result = call(
            "build_dati_pagamento",
            condizioni_pagamento="TP02",
            modalita_pagamento="MP23",
            importo_pagamento=500.0,
        )
        assert result["DatiPagamento"]["DettaglioPagamento"]["ModalitaPagamento"] == "MP23"


# ---------------------------------------------------------------------------
# add_allegato
# ---------------------------------------------------------------------------


class TestAddAllegato:
    def test_happy_path(self):
        content = base64.b64encode(b"%PDF-1.4 fake content").decode()
        result = call(
            "add_allegato",
            nome_allegato="contratto.pdf",
            attachment_base64=content,
            formato_allegato="PDF",
            descrizione_allegato="Contratto di riferimento",
        )
        a = result["Allegati"]
        assert a["NomeAllegato"] == "contratto.pdf"
        assert a["FormatoAllegato"] == "PDF"
        assert a["size_bytes"] > 0

    def test_invalid_base64_rejected(self):
        result = call(
            "add_allegato",
            nome_allegato="file.pdf",
            attachment_base64="!!!not-valid-base64!!!",
        )
        assert "error" in result

    def test_nome_too_long_rejected(self):
        content = base64.b64encode(b"data").decode()
        result = call(
            "add_allegato",
            nome_allegato="A" * 61,
            attachment_base64=content,
        )
        assert "error" in result

    def test_formato_truncated_at_10(self):
        content = base64.b64encode(b"data").decode()
        result = call(
            "add_allegato",
            nome_allegato="file.txt",
            attachment_base64=content,
            formato_allegato="VERYLONGFORMAT",
        )
        assert len(result["Allegati"]["FormatoAllegato"]) == 10

    def test_descrizione_truncated_at_100(self):
        content = base64.b64encode(b"data").decode()
        result = call(
            "add_allegato",
            nome_allegato="file.txt",
            attachment_base64=content,
            descrizione_allegato="D" * 200,
        )
        assert len(result["Allegati"]["DescrizioneAllegato"]) == 100
