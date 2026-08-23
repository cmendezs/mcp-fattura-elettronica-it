"""Tests for archive MCP tools."""

from __future__ import annotations

import pytest
from fastmcp.client import Client

from mcp_fattura_elettronica_it.server import mcp


class TestArchiveToolRegistration:
    @pytest.mark.asyncio
    async def test_archive_tools_registered(self):
        async with Client(mcp) as client:
            tools = await client.list_tools()
        names = {t.name for t in tools}
        expected = {
            "it__archive_invoice",
            "it__retrieve_archived_invoice",
            "it__verify_archive_integrity",
            "it__list_archived_invoices",
            "it__build_pacchetto_versamento",
        }
        assert expected.issubset(names)


class TestArchiveInvoice:
    @pytest.mark.asyncio
    async def test_missing_document_returns_error(self):
        async with Client(mcp) as client:
            result = await client.call_tool("it__archive_invoice", {"document_base64": ""})
        text = result.content[0].text if result.content else ""
        assert "MISSING_PARAM" in text


class TestRetrieveArchivedInvoice:
    @pytest.mark.asyncio
    async def test_missing_id_returns_error(self):
        async with Client(mcp) as client:
            result = await client.call_tool("it__retrieve_archived_invoice", {"document_id": ""})
        text = result.content[0].text if result.content else ""
        assert "MISSING_PARAM" in text


class TestVerifyArchiveIntegrity:
    @pytest.mark.asyncio
    async def test_missing_id_returns_error(self):
        async with Client(mcp) as client:
            result = await client.call_tool("it__verify_archive_integrity", {"document_id": ""})
        text = result.content[0].text if result.content else ""
        assert "MISSING_PARAM" in text
