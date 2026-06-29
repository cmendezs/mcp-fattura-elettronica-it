"""Tests for conservazione sostitutiva provider and PdV assembly."""

from __future__ import annotations

import zipfile
from io import BytesIO
from pathlib import Path

import pytest

from mcp_fattura_elettronica_it.archive.conservazione import (
    ConservazioneProvider,
    ConservazioneSettings,
)
from mcp_fattura_elettronica_it.archive.pacchetto import (
    build_indice_pdv,
    build_pacchetto_di_versamento,
)


@pytest.fixture()
def storage_path(tmp_path: Path) -> Path:
    return tmp_path / "archive"


@pytest.fixture()
def provider(storage_path: Path) -> ConservazioneProvider:
    settings = ConservazioneSettings(storage_path=str(storage_path))
    return ConservazioneProvider(settings)


_SAMPLE_DOC = b"<FatturaElettronica>test</FatturaElettronica>"


class TestConservazioneProvider:
    @pytest.mark.asyncio
    async def test_archive_and_retrieve_round_trip(self, provider: ConservazioneProvider):
        meta = await provider.archive_document(_SAMPLE_DOC, {"format_id": "FatturaPA-1.2.3"})
        assert meta.document_id
        assert meta.document_hash
        assert meta.format_id == "FatturaPA-1.2.3"

        doc, retrieved_meta = await provider.retrieve_document(meta.document_id)
        assert doc == _SAMPLE_DOC
        assert retrieved_meta.document_hash == meta.document_hash

    @pytest.mark.asyncio
    async def test_verify_integrity_valid(self, provider: ConservazioneProvider):
        meta = await provider.archive_document(_SAMPLE_DOC, {})
        assert await provider.verify_integrity(meta.document_id) is True

    @pytest.mark.asyncio
    async def test_verify_integrity_invalid(self, provider: ConservazioneProvider, storage_path: Path):
        meta = await provider.archive_document(_SAMPLE_DOC, {})
        doc_path = storage_path / f"{meta.document_id}.dat"
        doc_path.write_bytes(b"tampered content")
        assert await provider.verify_integrity(meta.document_id) is False

    @pytest.mark.asyncio
    async def test_verify_integrity_missing(self, provider: ConservazioneProvider):
        assert await provider.verify_integrity("nonexistent") is False

    @pytest.mark.asyncio
    async def test_list_documents(self, provider: ConservazioneProvider):
        await provider.archive_document(b"doc1", {"document_id": "doc-a"})
        await provider.archive_document(b"doc2", {"document_id": "doc-b"})
        results = await provider.list_documents({})
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_retrieve_not_found(self, provider: ConservazioneProvider):
        with pytest.raises(FileNotFoundError):
            await provider.retrieve_document("nonexistent")

    @pytest.mark.asyncio
    async def test_retention_period(self, provider: ConservazioneProvider):
        meta = await provider.archive_document(_SAMPLE_DOC, {})
        diff = meta.retention_until - meta.archive_timestamp
        assert diff.days >= 365 * 10 - 1


class TestPacchettoDiVersamento:
    def test_build_pdv_creates_valid_zip(self):
        docs = [
            ("invoice1.xml", b"<inv1/>"),
            ("invoice2.xml.p7m", b"\x30\x80" + b"\x00" * 100),
        ]
        pdv_bytes = build_pacchetto_di_versamento(docs, {"producer_id": "IT01234567890"})
        assert len(pdv_bytes) > 0

        with zipfile.ZipFile(BytesIO(pdv_bytes)) as zf:
            names = zf.namelist()
            assert "invoice1.xml" in names
            assert "invoice2.xml.p7m" in names
            assert "IPdV.xml" in names

    def test_pdv_index_contains_hashes(self):
        docs = [("test.xml", b"<test/>")]
        pdv_bytes = build_pacchetto_di_versamento(docs, {})
        with zipfile.ZipFile(BytesIO(pdv_bytes)) as zf:
            index = zf.read("IPdV.xml").decode("utf-8")
            assert "<Hash>" in index
            assert "<Filename>test.xml</Filename>" in index

    def test_build_indice_pdv(self):
        docs = [
            {"filename": "a.xml", "hash": "abc123", "format_id": "FatturaPA-1.2.3", "size_bytes": 100},
        ]
        xml = build_indice_pdv(docs, {"producer_id": "TEST", "retention_years": 10})
        assert "<ProducerId>TEST</ProducerId>" in xml
        assert "<RetentionYears>10</RetentionYears>" in xml
        assert "<Filename>a.xml</Filename>" in xml
