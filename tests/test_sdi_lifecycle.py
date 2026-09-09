"""Tests for SDILifecycleManager's typed submission contract (CORE-2, core audit Step 8)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from mcp_einvoicing_core.base_server import SearchCriteria

from mcp_fattura_elettronica_it.sdi.config import SDISettings
from mcp_fattura_elettronica_it.sdi.lifecycle import (
    SDIEsitoMetadata,
    SDILifecycleManager,
    SDISubmissionMetadata,
)


@pytest.fixture
def manager() -> SDILifecycleManager:
    mgr = SDILifecycleManager(SDISettings(cert_path="/fake/cert.p12"))
    mgr._client = AsyncMock()
    return mgr


class TestSubmitDocument:
    @pytest.mark.asyncio
    async def test_submits_with_typed_metadata(self, manager: SDILifecycleManager) -> None:
        manager._client.send_invoice.return_value = {"identificativo_sdi": "12345"}

        result = await manager.submit_document(
            b"<xml/>", SDISubmissionMetadata(filename="IT01234567890_00001.xml")
        )

        manager._client.send_invoice.assert_awaited_once_with(b"<xml/>", "IT01234567890_00001.xml")
        assert result.invoice_ref == "12345"
        assert result.status == "submitted"

    @pytest.mark.asyncio
    async def test_encodes_str_document_to_bytes(self, manager: SDILifecycleManager) -> None:
        manager._client.send_invoice.return_value = {"identificativo_sdi": "1"}

        await manager.submit_document("<xml/>", SDISubmissionMetadata(filename="f.xml"))

        args, _ = manager._client.send_invoice.await_args
        assert isinstance(args[0], bytes)

    @pytest.mark.asyncio
    async def test_empty_filename_raises(self, manager: SDILifecycleManager) -> None:
        with pytest.raises(ValueError, match="filename"):
            await manager.submit_document(b"<xml/>", SDISubmissionMetadata(filename=""))


class TestSubmitLifecycleStatus:
    @pytest.mark.asyncio
    async def test_submits_with_typed_metadata(self, manager: SDILifecycleManager) -> None:
        manager._client.send_esito.return_value = {"status": "ok"}

        result = await manager.submit_lifecycle_status(
            "12345",
            "EC01",
            SDIEsitoMetadata(nome_file="IT01234567890_00001_EC_001.xml", esito_xml=b"<xml/>"),
        )

        manager._client.send_esito.assert_awaited_once_with(
            "12345", "IT01234567890_00001_EC_001.xml", b"<xml/>"
        )
        assert result == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_str_esito_xml_is_coerced_to_bytes(self) -> None:
        metadata = SDIEsitoMetadata(nome_file="f.xml", esito_xml="<xml/>")
        assert metadata.esito_xml == b"<xml/>"


class TestSearchDocuments:
    @pytest.mark.asyncio
    async def test_returns_empty_list(self, manager: SDILifecycleManager) -> None:
        assert await manager.search_documents(SearchCriteria()) == []
