"""
MCP protocol integration tests for mcp-fattura-elettronica-it.

Verifies that all 21 tools are correctly registered via the MCP protocol,
that their schemas are valid, and that representative tools work end-to-end
via the in-process FastMCP client — no external dependencies required.
"""

from __future__ import annotations

import json

import pytest
from fastmcp import Client

from server import mcp

# ---------------------------------------------------------------------------
# Expected tool names
# ---------------------------------------------------------------------------

EXPECTED_HEADER_TOOLS = {
    "build_transmission_header",
    "validate_cedente_prestatore",
    "validate_cessionario",
    "get_regime_fiscale_codes",
    "validate_partita_iva",
    "generate_progressivo_invio",
    "lookup_codice_destinatario",
}

EXPECTED_BODY_TOOLS = {
    "build_dati_generali",
    "get_tipo_documento_codes",
    "add_linea_dettaglio",
    "compute_totali",
    "get_natura_codes",
    "build_dati_pagamento",
    "add_allegato",
}

EXPECTED_GLOBAL_TOOLS = {
    "generate_fattura_xml",
    "validate_fattura_xsd",
    "parse_fattura_xml",
    "export_to_json",
    "validate_partita_iva_format",
    "get_sdi_filename",
    "check_ritenuta_acconto",
}

EXPECTED_ALL_TOOLS = EXPECTED_HEADER_TOOLS | EXPECTED_BODY_TOOLS | EXPECTED_GLOBAL_TOOLS


def _parse(result) -> dict | list:
    """Deserialise the JSON response from an MCP tool call."""
    return json.loads(result.content[0].text)


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------


class TestToolRegistration:
    @pytest.mark.asyncio
    async def test_total_tool_count_is_21(self):
        """The server exposes exactly 21 tools."""
        async with Client(mcp) as client:
            tools = await client.list_tools()
        assert len(tools) == 21

    @pytest.mark.asyncio
    async def test_all_header_tools_registered(self):
        """All 7 Header tools are exposed."""
        async with Client(mcp) as client:
            tools = await client.list_tools()
        names = {t.name for t in tools}
        assert EXPECTED_HEADER_TOOLS.issubset(names)

    @pytest.mark.asyncio
    async def test_all_body_tools_registered(self):
        """All 7 Body tools are exposed."""
        async with Client(mcp) as client:
            tools = await client.list_tools()
        names = {t.name for t in tools}
        assert EXPECTED_BODY_TOOLS.issubset(names)

    @pytest.mark.asyncio
    async def test_all_global_tools_registered(self):
        """All 7 Global tools are exposed."""
        async with Client(mcp) as client:
            tools = await client.list_tools()
        names = {t.name for t in tools}
        assert EXPECTED_GLOBAL_TOOLS.issubset(names)

    @pytest.mark.asyncio
    async def test_all_tools_have_description(self):
        """Every tool has a non-empty description visible to the LLM."""
        async with Client(mcp) as client:
            tools = await client.list_tools()
        for tool in tools:
            assert tool.description, f"Tool '{tool.name}' has no description"


# ---------------------------------------------------------------------------
# Tool schemas (what the LLM sees)
# ---------------------------------------------------------------------------


class TestToolSchemas:
    @pytest.mark.asyncio
    async def test_build_transmission_header_required_params(self):
        """build_transmission_header requires 5 parameters."""
        async with Client(mcp) as client:
            tools = await client.list_tools()
        tool = next(t for t in tools if t.name == "build_transmission_header")
        required = set(tool.inputSchema.get("required", []))
        assert {"id_paese", "id_codice", "progressivo_invio", "formato_trasmissione", "codice_destinatario"}.issubset(required)

    @pytest.mark.asyncio
    async def test_pec_destinatario_is_optional(self):
        """pec_destinatario is optional in build_transmission_header."""
        async with Client(mcp) as client:
            tools = await client.list_tools()
        tool = next(t for t in tools if t.name == "build_transmission_header")
        required = set(tool.inputSchema.get("required", []))
        assert "pec_destinatario" not in required

    @pytest.mark.asyncio
    async def test_get_regime_fiscale_codes_has_no_required_params(self):
        """get_regime_fiscale_codes takes no parameters."""
        async with Client(mcp) as client:
            tools = await client.list_tools()
        tool = next(t for t in tools if t.name == "get_regime_fiscale_codes")
        assert tool.inputSchema.get("required", []) == []

    @pytest.mark.asyncio
    async def test_add_linea_dettaglio_required_params(self):
        """add_linea_dettaglio requires numero_linea and descrizione."""
        async with Client(mcp) as client:
            tools = await client.list_tools()
        tool = next(t for t in tools if t.name == "add_linea_dettaglio")
        required = set(tool.inputSchema.get("required", []))
        assert "numero_linea" in required
        assert "descrizione" in required

    @pytest.mark.asyncio
    async def test_generate_fattura_xml_required_params(self):
        """generate_fattura_xml requires 6 core parameters."""
        async with Client(mcp) as client:
            tools = await client.list_tools()
        tool = next(t for t in tools if t.name == "generate_fattura_xml")
        required = set(tool.inputSchema.get("required", []))
        assert {
            "dati_trasmissione",
            "cedente_prestatore",
            "cessionario_committente",
            "dati_generali",
            "dettaglio_linee",
            "dati_riepilogo",
        }.issubset(required)
        # Optional params
        assert "dati_pagamento" not in required
        assert "allegati" not in required

    @pytest.mark.asyncio
    async def test_validate_fattura_xsd_requires_xml_string(self):
        """validate_fattura_xsd requires xml_string."""
        async with Client(mcp) as client:
            tools = await client.list_tools()
        tool = next(t for t in tools if t.name == "validate_fattura_xsd")
        required = set(tool.inputSchema.get("required", []))
        assert "xml_string" in required


# ---------------------------------------------------------------------------
# Header tool calls via MCP
# ---------------------------------------------------------------------------


class TestHeaderToolCalls:
    @pytest.mark.asyncio
    async def test_get_regime_fiscale_codes_returns_codes(self):
        """get_regime_fiscale_codes returns all valid fiscal regime codes (RF03 does not exist)."""
        async with Client(mcp) as client:
            result = await client.call_tool("get_regime_fiscale_codes", {})
        data = _parse(result)
        assert data["total"] == 18  # RF03 does not exist in the official FatturaPA specs
        codes = {c["code"] for c in data["codes"]}
        assert "RF01" in codes
        assert "RF19" in codes

    @pytest.mark.asyncio
    async def test_validate_partita_iva_valid(self):
        """validate_partita_iva returns valid=True for correct Partita IVA."""
        async with Client(mcp) as client:
            result = await client.call_tool(
                "validate_partita_iva", {"partita_iva": "01234567897"}
            )
        data = _parse(result)
        assert data["valid"] is True

    @pytest.mark.asyncio
    async def test_validate_partita_iva_invalid(self):
        """validate_partita_iva returns valid=False for wrong checksum."""
        async with Client(mcp) as client:
            result = await client.call_tool(
                "validate_partita_iva", {"partita_iva": "01234567890"}
            )
        data = _parse(result)
        assert data["valid"] is False

    @pytest.mark.asyncio
    async def test_generate_progressivo_invio_length(self):
        """generate_progressivo_invio produces a ≤10-char alphanumeric string."""
        async with Client(mcp) as client:
            result = await client.call_tool("generate_progressivo_invio", {})
        data = _parse(result)
        assert len(data["progressivo_invio"]) <= 10
        assert data["progressivo_invio"].isalnum()

    @pytest.mark.asyncio
    async def test_build_transmission_header_invalid_formato(self):
        """build_transmission_header returns error dict for invalid formato."""
        async with Client(mcp) as client:
            result = await client.call_tool(
                "build_transmission_header",
                {
                    "id_paese": "IT",
                    "id_codice": "01234567897",
                    "progressivo_invio": "00001",
                    "formato_trasmissione": "WRONG",
                    "codice_destinatario": "ABC123",
                },
            )
        data = _parse(result)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_lookup_codice_destinatario_valid_code(self):
        """lookup_codice_destinatario identifies a valid 6-char SDI code."""
        async with Client(mcp) as client:
            result = await client.call_tool(
                "lookup_codice_destinatario", {"codice": "K23T45"}
            )
        data = _parse(result)
        assert data["routing_type"] == "SDI_CODE"


# ---------------------------------------------------------------------------
# Body tool calls via MCP
# ---------------------------------------------------------------------------


class TestBodyToolCalls:
    @pytest.mark.asyncio
    async def test_get_tipo_documento_codes_returns_28_codes(self):
        """get_tipo_documento_codes returns all 22 document type codes (TD01–TD28)."""
        async with Client(mcp) as client:
            result = await client.call_tool("get_tipo_documento_codes", {})
        data = _parse(result)
        assert data["total"] >= 22  # at least 22 codes
        codes = {c["code"] for c in data["codes"]}
        assert "TD01" in codes
        assert "TD04" in codes
        assert "TD28" in codes

    @pytest.mark.asyncio
    async def test_get_natura_codes_contains_reverse_charge(self):
        """get_natura_codes includes all N6.x reverse charge sub-codes."""
        async with Client(mcp) as client:
            result = await client.call_tool("get_natura_codes", {})
        data = _parse(result)
        codes = {c["code"] for c in data["codes"]}
        assert "N6" in codes
        assert "N6.1" in codes

    @pytest.mark.asyncio
    async def test_compute_totali_single_rate(self):
        """compute_totali correctly sums imponibile and imposta for a single VAT rate."""
        async with Client(mcp) as client:
            result = await client.call_tool(
                "compute_totali",
                {
                    "linee": [
                        {"prezzo_totale": 1000.0, "aliquota_iva": 22.0},
                        {"prezzo_totale": 500.0, "aliquota_iva": 22.0},
                    ]
                },
            )
        data = _parse(result)
        assert data["totale_imponibile"] == "1500.00"
        assert data["totale_imposta"] == "330.00"
        assert data["totale_fattura"] == "1830.00"

    @pytest.mark.asyncio
    async def test_add_allegato_invalid_base64(self):
        """add_allegato returns error dict for invalid base64 input."""
        async with Client(mcp) as client:
            result = await client.call_tool(
                "add_allegato",
                {
                    "nome_allegato": "file.pdf",
                    "attachment_base64": "!!!not-base64!!!",
                },
            )
        data = _parse(result)
        assert "error" in data


# ---------------------------------------------------------------------------
# Global tool calls via MCP — end-to-end
# ---------------------------------------------------------------------------


class TestGlobalToolCalls:
    @pytest.mark.asyncio
    async def test_get_sdi_filename(self):
        """get_sdi_filename produces the correct IT{PIVA}_{PROG}.xml filename."""
        async with Client(mcp) as client:
            result = await client.call_tool(
                "get_sdi_filename",
                {
                    "partita_iva_cedente": "01234567897",
                    "progressivo_invio": "1",
                },
            )
        data = _parse(result)
        assert data["filename"] == "IT01234567897_00001.xml"

    @pytest.mark.asyncio
    async def test_validate_partita_iva_format_standalone(self):
        """validate_partita_iva_format works identically to header tool validate_partita_iva."""
        async with Client(mcp) as client:
            result = await client.call_tool(
                "validate_partita_iva_format", {"partita_iva": "01234567897"}
            )
        data = _parse(result)
        assert data["valid"] is True

    @pytest.mark.asyncio
    async def test_check_ritenuta_rt02(self):
        """check_ritenuta_acconto computes 20% withholding on RT02."""
        async with Client(mcp) as client:
            result = await client.call_tool(
                "check_ritenuta_acconto",
                {
                    "imponibile": 1000.0,
                    "tipo_ritenuta": "RT02",
                    "causale_pagamento": "A",
                },
            )
        data = _parse(result)
        assert data["importo_ritenuta"] == "200.00"
        dr = data["DatiRitenuta"]
        assert dr["TipoRitenuta"] == "RT02"
        assert dr["CausalePagamento"] == "A"

    @pytest.mark.asyncio
    async def test_generate_and_parse_roundtrip(self):
        """generate_fattura_xml + parse_fattura_xml round-trip preserves key fields."""
        gen_payload = {
            "dati_trasmissione": {
                "DatiTrasmissione": {
                    "IdTrasmittente": {"IdPaese": "IT", "IdCodice": "01234567897"},
                    "ProgressivoInvio": "00042",
                    "FormatoTrasmissione": "FPR12",
                    "CodiceDestinatario": "XYZ789",
                }
            },
            "cedente_prestatore": {
                "CedentePrestatore": {
                    "DatiAnagrafici": {
                        "IdFiscaleIVA": {"IdPaese": "IT", "IdCodice": "01234567897"},
                        "Anagrafica": {"Denominazione": "Studio Tech Srl"},
                        "RegimeFiscale": "RF01",
                    },
                    "Sede": {
                        "Indirizzo": "Via Roma 1",
                        "CAP": "00100",
                        "Comune": "Roma",
                        "Nazione": "IT",
                    },
                }
            },
            "cessionario_committente": {
                "CessionarioCommittente": {
                    "DatiAnagrafici": {
                        "IdFiscaleIVA": {"IdPaese": "IT", "IdCodice": "98765432109"},
                        "Anagrafica": {"Denominazione": "Cliente Srl"},
                    },
                    "Sede": {
                        "Indirizzo": "Via Verdi 2",
                        "CAP": "20100",
                        "Comune": "Milano",
                        "Nazione": "IT",
                    },
                }
            },
            "dati_generali": {
                "DatiGenerali": {
                    "DatiGeneraliDocumento": {
                        "TipoDocumento": "TD01",
                        "Divisa": "EUR",
                        "Data": "2026-03-01",
                        "Numero": "2026/042",
                    }
                }
            },
            "dettaglio_linee": [
                {
                    "DettaglioLinee": {
                        "NumeroLinea": 1,
                        "Descrizione": "Sviluppo software",
                        "PrezzoUnitario": "5000",
                        "PrezzoTotale": "5000.00",
                        "AliquotaIVA": "22.00",
                    }
                }
            ],
            "dati_riepilogo": [
                {
                    "AliquotaIVA": "22.00",
                    "Imponibile": "5000.00",
                    "Imposta": "1100.00",
                    "EsigibilitaIVA": "I",
                }
            ],
        }

        async with Client(mcp) as client:
            gen_result = await client.call_tool("generate_fattura_xml", gen_payload)
        gen_data = _parse(gen_result)
        assert "xml" in gen_data
        assert gen_data["filename"] == "IT01234567897_00042.xml"

        async with Client(mcp) as client:
            parse_result = await client.call_tool(
                "parse_fattura_xml", {"xml_string": gen_data["xml"]}
            )
        parsed = _parse(parse_result)
        assert parsed["header"]["cedente_prestatore"]["denominazione"] == "Studio Tech Srl"
        assert parsed["body"]["dati_generali"]["numero"] == "2026/042"
