"""
Tests for tools/simplified_tools.py — FatturaSemplificata VFSM10 tools.

Covers generate, XSD validate, and parse for TD07/TD08/TD09 simplified invoices.
"""

from __future__ import annotations

import asyncio

from fastmcp import FastMCP
from mcp_fattura_elettronica_it.tools.simplified_tools import register_simplified_tools

# Also import global tools to test that TD07 is rejected by the ordinary generator
from mcp_fattura_elettronica_it.tools.global_tools import register_global_tools

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

_mcp = FastMCP(name="test-simplified")
register_simplified_tools(_mcp)
register_global_tools(_mcp)


async def _get_tools():
    tools = await _mcp.list_tools()
    return {t.name: t.fn for t in tools}


_tools = asyncio.run(_get_tools())


def call(name: str, **kwargs):
    return _tools[name](**kwargs)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

VALID_DATI_TRASMISSIONE = {
    "IdTrasmittente": {"IdPaese": "IT", "IdCodice": "01234567897"},
    "ProgressivoInvio": "00001",
    "CodiceDestinatario": "ABCDEFG",
}

VALID_CEDENTE = {
    "IdFiscaleIVA": {"IdPaese": "IT", "IdCodice": "01234567897"},
    "Denominazione": "Bar Rossi Srl",
    "Sede": {"Indirizzo": "Via Roma 1", "CAP": "00100", "Comune": "Roma", "Nazione": "IT"},
    "RegimeFiscale": "RF01",
}

VALID_CESSIONARIO = {
    "IdentificativiFiscali": {
        "CodiceFiscale": "RSSMRA80A01H501T",
    },
    "AltriDatiIdentificativi": {
        "Denominazione": "Mario Rossi",
        "Sede": {"Indirizzo": "Via Verdi 2", "CAP": "20100", "Comune": "Milano", "Nazione": "IT"},
    },
}

VALID_DATI_GENERALI = {
    "DatiGeneraliDocumento": {
        "TipoDocumento": "TD07",
        "Divisa": "EUR",
        "Data": "2026-06-15",
        "Numero": "S001",
    }
}

VALID_BENI_SERVIZI = [
    {
        "Descrizione": "Caffe e cornetto",
        "Importo": "3.66",
        "DatiIVA": {"Imposta": "0.66", "Aliquota": "22.00"},
    }
]


def _generate_simplified() -> dict:
    return call(
        "generate_fattura_semplificata",
        dati_trasmissione=VALID_DATI_TRASMISSIONE,
        cedente_prestatore=VALID_CEDENTE,
        cessionario_committente=VALID_CESSIONARIO,
        dati_generali=VALID_DATI_GENERALI,
        dati_beni_servizi=VALID_BENI_SERVIZI,
    )


# ---------------------------------------------------------------------------
# generate_fattura_semplificata
# ---------------------------------------------------------------------------


class TestGenerateFatturaSemplificata:
    def test_generates_xml(self):
        result = _generate_simplified()
        assert "error" not in result
        assert "FatturaElettronicaSemplificata" in result["xml"]
        assert "FSM10" in result["xml"]

    def test_filename_follows_sdi_convention(self):
        result = _generate_simplified()
        assert result["filename"] == "IT01234567897_00001.xml"

    def test_contains_seller_name(self):
        result = _generate_simplified()
        assert "Bar Rossi Srl" in result["xml"]

    def test_contains_buyer_cf(self):
        result = _generate_simplified()
        assert "RSSMRA80A01H501T" in result["xml"]

    def test_contains_beni_servizi(self):
        result = _generate_simplified()
        assert "<DatiBeniServizi>" in result["xml"]
        assert "Caffe e cornetto" in result["xml"]
        assert "<Importo>3.66</Importo>" in result["xml"]

    def test_contains_dati_iva(self):
        result = _generate_simplified()
        assert "<DatiIVA>" in result["xml"]
        assert "<Imposta>0.66</Imposta>" in result["xml"]
        assert "<Aliquota>22.00</Aliquota>" in result["xml"]

    def test_rejects_td01(self):
        dg = {
            "DatiGeneraliDocumento": {
                "TipoDocumento": "TD01",
                "Divisa": "EUR",
                "Data": "2026-06-15",
                "Numero": "001",
            }
        }
        result = call(
            "generate_fattura_semplificata",
            dati_trasmissione=VALID_DATI_TRASMISSIONE,
            cedente_prestatore=VALID_CEDENTE,
            cessionario_committente=VALID_CESSIONARIO,
            dati_generali=dg,
            dati_beni_servizi=VALID_BENI_SERVIZI,
        )
        assert "error" in result
        assert "TD01" in result["error"]

    def test_td08_with_rettificata(self):
        dg = {
            "DatiGeneraliDocumento": {
                "TipoDocumento": "TD08",
                "Divisa": "EUR",
                "Data": "2026-06-20",
                "Numero": "NC001",
            },
            "DatiFatturaRettificata": {
                "NumeroFR": "S001",
                "DataFR": "2026-06-15",
                "ElementiRettificati": "Importo errato",
            },
        }
        result = call(
            "generate_fattura_semplificata",
            dati_trasmissione=VALID_DATI_TRASMISSIONE,
            cedente_prestatore=VALID_CEDENTE,
            cessionario_committente=VALID_CESSIONARIO,
            dati_generali=dg,
            dati_beni_servizi=VALID_BENI_SERVIZI,
        )
        assert "error" not in result
        assert "<DatiFatturaRettificata>" in result["xml"]
        assert "<NumeroFR>S001</NumeroFR>" in result["xml"]

    def test_uses_vfsm10_namespace(self):
        result = _generate_simplified()
        assert "ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.0" in result["xml"]

    def test_length_bytes_is_positive(self):
        result = _generate_simplified()
        assert result["length_bytes"] > 0

    def test_multiple_beni_servizi(self):
        items = [
            {"Descrizione": "Item 1", "Importo": "10.00", "DatiIVA": {"Aliquota": "22.00"}},
            {"Descrizione": "Item 2", "Importo": "5.00", "DatiIVA": {"Aliquota": "10.00"}},
        ]
        result = call(
            "generate_fattura_semplificata",
            dati_trasmissione=VALID_DATI_TRASMISSIONE,
            cedente_prestatore=VALID_CEDENTE,
            cessionario_committente=VALID_CESSIONARIO,
            dati_generali=VALID_DATI_GENERALI,
            dati_beni_servizi=items,
        )
        assert "error" not in result
        assert result["xml"].count("<DatiBeniServizi>") == 2


# ---------------------------------------------------------------------------
# validate_fattura_semplificata_xsd
# ---------------------------------------------------------------------------


class TestValidateFatturaSemplificataXsd:
    def test_valid_xml_structure(self):
        xml = _generate_simplified()["xml"]
        result = call("validate_fattura_semplificata_xsd", xml_string=xml)
        assert "valid" in result

    def test_malformed_xml(self):
        result = call("validate_fattura_semplificata_xsd", xml_string="<not-valid")
        assert result.get("valid") is False or "error" in result

    def test_empty_string(self):
        result = call("validate_fattura_semplificata_xsd", xml_string="")
        assert result.get("valid") is False or "error" in result


# ---------------------------------------------------------------------------
# parse_fattura_semplificata_xml
# ---------------------------------------------------------------------------


class TestParseFatturaSemplificataXml:
    def test_round_trip(self):
        xml = _generate_simplified()["xml"]
        result = call("parse_fattura_semplificata_xml", xml_string=xml)
        assert "error" not in result
        assert result["versione"] == "FSM10"

    def test_parses_seller(self):
        xml = _generate_simplified()["xml"]
        result = call("parse_fattura_semplificata_xml", xml_string=xml)
        cp = result["header"]["cedente_prestatore"]
        assert cp["denominazione"] == "Bar Rossi Srl"
        assert cp["regime_fiscale"] == "RF01"
        assert cp["id_codice"] == "01234567897"

    def test_parses_buyer(self):
        xml = _generate_simplified()["xml"]
        result = call("parse_fattura_semplificata_xml", xml_string=xml)
        cc = result["header"]["cessionario_committente"]
        assert cc["codice_fiscale"] == "RSSMRA80A01H501T"
        assert cc["denominazione"] == "Mario Rossi"

    def test_parses_dati_generali(self):
        xml = _generate_simplified()["xml"]
        result = call("parse_fattura_semplificata_xml", xml_string=xml)
        dg = result["body"]["dati_generali"]
        assert dg["tipo_documento"] == "TD07"
        assert dg["numero"] == "S001"

    def test_parses_beni_servizi(self):
        xml = _generate_simplified()["xml"]
        result = call("parse_fattura_semplificata_xml", xml_string=xml)
        bs = result["body"]["dati_beni_servizi"]
        assert len(bs) == 1
        assert bs[0]["descrizione"] == "Caffe e cornetto"
        assert bs[0]["importo"] == "3.66"
        assert bs[0]["imposta"] == "0.66"

    def test_invalid_xml(self):
        result = call("parse_fattura_semplificata_xml", xml_string="not xml")
        assert "error" in result


# ---------------------------------------------------------------------------
# Cross-format rejection: TD07 in ordinary generator
# ---------------------------------------------------------------------------


class TestCrossFormatRejection:
    def test_td07_rejected_by_ordinary_generator(self):
        """TD07 should not be accepted by generate_fattura_xml (ordinary format)."""
        dg = {
            "DatiGenerali": {
                "DatiGeneraliDocumento": {
                    "TipoDocumento": "TD07",
                    "Divisa": "EUR",
                    "Data": "2026-06-15",
                    "Numero": "001",
                }
            }
        }
        dt = {
            "DatiTrasmissione": {
                "IdTrasmittente": {"IdPaese": "IT", "IdCodice": "01234567897"},
                "ProgressivoInvio": "00001",
                "FormatoTrasmissione": "FPR12",
                "CodiceDestinatario": "ABCDEFG",
            }
        }
        cp = {
            "CedentePrestatore": {
                "DatiAnagrafici": {
                    "IdFiscaleIVA": {"IdPaese": "IT", "IdCodice": "01234567897"},
                    "Anagrafica": {"Denominazione": "ACME"},
                    "RegimeFiscale": "RF01",
                },
                "Sede": {"Indirizzo": "Via Roma 1", "CAP": "00100", "Comune": "Roma", "Nazione": "IT"},
            }
        }
        cc = {
            "CessionarioCommittente": {
                "DatiAnagrafici": {
                    "IdFiscaleIVA": {"IdPaese": "IT", "IdCodice": "98765432109"},
                    "Anagrafica": {"Denominazione": "Buyer"},
                },
                "Sede": {"Indirizzo": "Via Verdi 2", "CAP": "20100", "Comune": "Milano", "Nazione": "IT"},
            }
        }
        linee = [{"DettaglioLinee": {"NumeroLinea": 1, "Descrizione": "X", "PrezzoUnitario": "10", "PrezzoTotale": "10.00", "AliquotaIVA": "22.00"}}]
        riepilogo = [{"AliquotaIVA": "22.00", "ImponibileImporto": "10.00", "Imposta": "2.20", "EsigibilitaIVA": "I"}]

        result = call(
            "generate_fattura_xml",
            dati_trasmissione=dt,
            cedente_prestatore=cp,
            cessionario_committente=cc,
            dati_generali=dg,
            dettaglio_linee=linee,
            dati_riepilogo=riepilogo,
        )
        assert "error" in result
        assert "simplified" in result["error"].lower() or "TD07" in result["error"]
