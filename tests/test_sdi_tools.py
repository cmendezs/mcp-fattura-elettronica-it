"""Tests for SDI integration tools."""

from __future__ import annotations

import pytest
from fastmcp.client import Client

from mcp_fattura_elettronica_it.server import mcp


class TestSDIToolRegistration:
    @pytest.mark.asyncio
    async def test_sdi_tools_registered(self):
        async with Client(mcp) as client:
            tools = await client.list_tools()
        names = {t.name for t in tools}
        expected = {
            "it__submit_to_sdi",
            "it__check_sdi_status",
            "it__parse_sdi_notification",
            "it__send_esito_committente",
            "it__get_sdi_channel_info",
        }
        assert expected.issubset(names)


class TestSubmitToSDI:
    @pytest.mark.asyncio
    async def test_missing_file_returns_error(self):
        async with Client(mcp) as client:
            result = await client.call_tool(
                "it__submit_to_sdi",
                {"signed_file_base64": "", "filename": "test.xml"},
            )
        text = result.content[0].text if result.content else ""
        assert "MISSING_PARAM" in text

    @pytest.mark.asyncio
    async def test_missing_filename_returns_error(self):
        async with Client(mcp) as client:
            result = await client.call_tool(
                "it__submit_to_sdi",
                {"signed_file_base64": "dGVzdA==", "filename": ""},
            )
        text = result.content[0].text if result.content else ""
        assert "MISSING_PARAM" in text


class TestGetSDIChannelInfo:
    @pytest.mark.asyncio
    async def test_returns_config(self):
        async with Client(mcp) as client:
            result = await client.call_tool("it__get_sdi_channel_info", {})
        text = result.content[0].text if result.content else ""
        assert "environment" in text
        assert "sdicoop" in text.lower() or "channel" in text


class TestSendEsitoCommittente:
    @pytest.mark.asyncio
    async def test_invalid_esito_returns_error(self):
        async with Client(mcp) as client:
            result = await client.call_tool(
                "it__send_esito_committente",
                {
                    "identificativo_sdi": "123456789012",
                    "esito": "INVALID",
                    "nome_file": "test_EC_001.xml",
                    "esito_xml": "<test/>",
                },
            )
        text = result.content[0].text if result.content else ""
        assert "INVALID_PARAM" in text
