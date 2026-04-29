"""
Tests for tools/header_tools.py — FatturaElettronicaHeader tools.

Covers happy path, validation errors, and edge cases for all 7 header tools.
"""

from __future__ import annotations


import asyncio

from tools.header_tools import (
    REGIME_FISCALE,
    register_header_tools,
)
from fastmcp import FastMCP


# ---------------------------------------------------------------------------
# Helpers — instantiate tools directly by calling the registered functions
# ---------------------------------------------------------------------------

_mcp = FastMCP(name="test-header")
register_header_tools(_mcp)


async def _get_tools():
    tools = await _mcp.list_tools()
    return {t.name: t.fn for t in tools}


_tools = asyncio.run(_get_tools())


def call(name: str, **kwargs):
    return _tools[name](**kwargs)


# ---------------------------------------------------------------------------
# build_transmission_header
# ---------------------------------------------------------------------------


class TestBuildTransmissionHeader:
    def test_happy_path_sdi_code(self):
        result = call(
            "build_transmission_header",
            id_paese="IT",
            id_codice="12345678901",
            progressivo_invio="00001",
            formato_trasmissione="FPR12",
            codice_destinatario="ABC123",
        )
        dt = result["DatiTrasmissione"]
        assert dt["IdTrasmittente"]["IdPaese"] == "IT"
        assert dt["ProgressivoInvio"] == "00001"
        assert dt["FormatoTrasmissione"] == "FPR12"
        assert dt["CodiceDestinatario"] == "ABC123"
        assert "PECDestinatario" not in dt

    def test_happy_path_pec_routing(self):
        result = call(
            "build_transmission_header",
            id_paese="IT",
            id_codice="12345678901",
            progressivo_invio="00002",
            formato_trasmissione="FPA12",
            codice_destinatario="0000000",
            pec_destinatario="buyer@pec.it",
        )
        dt = result["DatiTrasmissione"]
        assert dt["CodiceDestinatario"] == "0000000"
        assert dt["PECDestinatario"] == "buyer@pec.it"

    def test_invalid_formato_trasmissione(self):
        result = call(
            "build_transmission_header",
            id_paese="IT",
            id_codice="12345678901",
            progressivo_invio="00001",
            formato_trasmissione="INVALID",
            codice_destinatario="ABC123",
        )
        assert "error" in result

    def test_pec_required_when_codice_is_zeros(self):
        result = call(
            "build_transmission_header",
            id_paese="IT",
            id_codice="12345678901",
            progressivo_invio="00001",
            formato_trasmissione="FPR12",
            codice_destinatario="0000000",
        )
        assert "error" in result

    def test_progressivo_too_long(self):
        result = call(
            "build_transmission_header",
            id_paese="IT",
            id_codice="12345678901",
            progressivo_invio="12345678901",  # 11 chars
            formato_trasmissione="FPR12",
            codice_destinatario="ABC123",
        )
        assert "error" in result

    def test_id_paese_uppercased(self):
        result = call(
            "build_transmission_header",
            id_paese="it",
            id_codice="12345678901",
            progressivo_invio="00001",
            formato_trasmissione="FPR12",
            codice_destinatario="ABC123",
        )
        assert result["DatiTrasmissione"]["IdTrasmittente"]["IdPaese"] == "IT"


# ---------------------------------------------------------------------------
# validate_cedente_prestatore
# ---------------------------------------------------------------------------


class TestValidateCedentePrestatore:
    def test_happy_path_company(self):
        result = call(
            "validate_cedente_prestatore",
            id_paese="IT",
            id_codice="12345678901",
            denominazione="ACME Srl",
            regime_fiscale="RF01",
            indirizzo="Via Roma 1",
            cap="00100",
            comune="Roma",
            nazione="IT",
        )
        cp = result["CedentePrestatore"]
        assert cp["DatiAnagrafici"]["Anagrafica"]["Denominazione"] == "ACME Srl"
        assert cp["DatiAnagrafici"]["RegimeFiscale"] == "RF01"

    def test_happy_path_individual(self):
        result = call(
            "validate_cedente_prestatore",
            id_paese="IT",
            id_codice="12345678901",
            nome="Mario",
            cognome="Rossi",
            regime_fiscale="RF19",
            indirizzo="Via Garibaldi 5",
            cap="20100",
            comune="Milano",
            nazione="IT",
        )
        anagrafica = result["CedentePrestatore"]["DatiAnagrafici"]["Anagrafica"]
        assert anagrafica["Nome"] == "Mario"
        assert anagrafica["Cognome"] == "Rossi"

    def test_missing_name_returns_error(self):
        result = call(
            "validate_cedente_prestatore",
            id_paese="IT",
            id_codice="12345678901",
            regime_fiscale="RF01",
        )
        assert "error" in result

    def test_denominazione_and_nome_mutually_exclusive(self):
        result = call(
            "validate_cedente_prestatore",
            id_paese="IT",
            id_codice="12345678901",
            denominazione="ACME",
            nome="Mario",
            regime_fiscale="RF01",
        )
        assert "error" in result

    def test_invalid_regime_fiscale(self):
        result = call(
            "validate_cedente_prestatore",
            id_paese="IT",
            id_codice="12345678901",
            denominazione="ACME",
            regime_fiscale="RF99",
        )
        assert "error" in result

    def test_italian_piva_must_be_11_digits(self):
        result = call(
            "validate_cedente_prestatore",
            id_paese="IT",
            id_codice="1234",  # too short
            denominazione="ACME",
            regime_fiscale="RF01",
        )
        assert "error" in result


# ---------------------------------------------------------------------------
# validate_cessionario
# ---------------------------------------------------------------------------


class TestValidateCessionario:
    def test_happy_path_with_vat(self):
        result = call(
            "validate_cessionario",
            denominazione="Buyer Srl",
            id_paese="IT",
            id_codice="98765432109",
            indirizzo="Via Verdi 2",
            cap="10100",
            comune="Torino",
            nazione="IT",
        )
        cc = result["CessionarioCommittente"]
        assert cc["DatiAnagrafici"]["IdFiscaleIVA"]["IdCodice"] == "98765432109"

    def test_happy_path_with_codice_fiscale_only(self):
        result = call(
            "validate_cessionario",
            nome="Luigi",
            cognome="Bianchi",
            codice_fiscale="BNCLGI80A01H501T",
            indirizzo="Via Dante 10",
            cap="50100",
            comune="Firenze",
        )
        cc = result["CessionarioCommittente"]
        assert cc["DatiAnagrafici"]["CodiceFiscale"] == "BNCLGI80A01H501T"

    def test_no_tax_identifier_returns_error(self):
        result = call(
            "validate_cessionario",
            denominazione="Buyer Srl",
        )
        assert "error" in result

    def test_id_paese_without_id_codice_returns_error(self):
        result = call(
            "validate_cessionario",
            denominazione="Buyer Srl",
            id_paese="IT",
        )
        assert "error" in result

    def test_missing_name_returns_error(self):
        result = call(
            "validate_cessionario",
            id_paese="IT",
            id_codice="98765432109",
        )
        assert "error" in result


# ---------------------------------------------------------------------------
# get_regime_fiscale_codes
# ---------------------------------------------------------------------------


class TestGetRegimeFiscaleCodes:
    def test_returns_all_codes(self):
        result = call("get_regime_fiscale_codes")
        assert result["total"] == len(REGIME_FISCALE)  # 18 codes (RF03 does not exist in official specs)
        codes = {c["code"] for c in result["codes"]}
        assert "RF01" in codes
        assert "RF19" in codes

    def test_each_entry_has_description(self):
        result = call("get_regime_fiscale_codes")
        for entry in result["codes"]:
            assert entry["description"]


# ---------------------------------------------------------------------------
# validate_partita_iva
# ---------------------------------------------------------------------------


class TestValidatePartitaIva:
    def test_valid_piva(self):
        # 01234567897 — classic test Partita IVA with correct checksum
        result = call("validate_partita_iva", partita_iva="01234567897")
        assert result["valid"] is True

    def test_invalid_checksum(self):
        result = call("validate_partita_iva", partita_iva="01234567890")
        assert result["valid"] is False
        assert "Checksum" in result["error"]

    def test_not_11_digits(self):
        result = call("validate_partita_iva", partita_iva="1234567")
        assert result["valid"] is False

    def test_whitespace_stripped(self):
        result = call("validate_partita_iva", partita_iva=" 01234567897 ")
        assert result["value"] == "01234567897"

    def test_letters_rejected(self):
        result = call("validate_partita_iva", partita_iva="1234567890A")
        assert result["valid"] is False


# ---------------------------------------------------------------------------
# generate_progressivo_invio
# ---------------------------------------------------------------------------


class TestGenerateProgressivoInvio:
    def test_generates_string_max_10_chars(self):
        result = call("generate_progressivo_invio")
        assert "progressivo_invio" in result
        assert len(result["progressivo_invio"]) <= 10
        assert result["progressivo_invio"].isalnum()

    def test_with_prefix(self):
        result = call("generate_progressivo_invio", prefix="INV", sequence=1)
        assert result["progressivo_invio"].startswith("INV")

    def test_with_explicit_sequence(self):
        result = call("generate_progressivo_invio", sequence=42)
        assert "42" in result["progressivo_invio"]

    def test_invalid_prefix_rejected(self):
        result = call("generate_progressivo_invio", prefix="12X")
        assert "error" in result

    def test_prefix_uppercased(self):
        result = call("generate_progressivo_invio", prefix="inv", sequence=1)
        assert result["progressivo_invio"].startswith("INV")


# ---------------------------------------------------------------------------
# lookup_codice_destinatario
# ---------------------------------------------------------------------------


class TestLookupCodiceDestinatario:
    def test_valid_sdi_code(self):
        result = call("lookup_codice_destinatario", codice="ABC123")
        assert result["routing_type"] == "SDI_CODE"
        assert result["codice_destinatario"] == "ABC123"

    def test_zeros_code_is_pec_routing(self):
        result = call("lookup_codice_destinatario", codice="0000000", pec="buyer@pec.it")
        assert result["routing_type"] == "PEC"
        assert result["pec_destinatario"] == "buyer@pec.it"

    def test_invalid_codice_rejected(self):
        result = call("lookup_codice_destinatario", codice="TOOLONG123")
        assert "error" in result

    def test_no_input_returns_error(self):
        result = call("lookup_codice_destinatario")
        assert "error" in result

    def test_invalid_pec_format(self):
        result = call("lookup_codice_destinatario", pec="not-an-email")
        assert "error" in result

    def test_pec_only(self):
        result = call("lookup_codice_destinatario", pec="info@legalmail.it")
        assert result["routing_type"] == "PEC"
        assert "pec_destinatario" in result
