"""Tests for signing tools (it__sign_fattura_xades, it__sign_fattura_cades)."""

from __future__ import annotations

import pytest
from fastmcp.client import Client

from mcp_fattura_elettronica_it.server import mcp

_SAMPLE_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    "<p:FatturaElettronica xmlns:p="
    '"http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2" '
    'versione="FPR12">'
    "<FatturaElettronicaHeader/>"
    "<FatturaElettronicaBody/>"
    "</p:FatturaElettronica>"
)


class TestSignFatturaXAdES:
    @pytest.mark.asyncio
    async def test_tool_registered(self):
        async with Client(mcp) as client:
            tools = await client.list_tools()
        names = {t.name for t in tools}
        assert "it__sign_fattura_xades" in names

    @pytest.mark.asyncio
    async def test_missing_xml_returns_error(self):
        async with Client(mcp) as client:
            result = await client.call_tool("it__sign_fattura_xades", {"xml": ""})
        text = result.content[0].text if result.content else ""
        assert "error" in text.lower() or "MISSING_PARAM" in text


class TestSignFatturaCAdES:
    @pytest.mark.asyncio
    async def test_tool_registered(self):
        async with Client(mcp) as client:
            tools = await client.list_tools()
        names = {t.name for t in tools}
        assert "it__sign_fattura_cades" in names

    @pytest.mark.asyncio
    async def test_missing_xml_returns_error(self):
        async with Client(mcp) as client:
            result = await client.call_tool("it__sign_fattura_cades", {"xml": ""})
        text = result.content[0].text if result.content else ""
        assert "error" in text.lower() or "MISSING_PARAM" in text
