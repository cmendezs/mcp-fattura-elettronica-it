"""Conservazione sostitutiva provider implementing core BaseArchiveProvider.

Per AgID circolare 65/2014 and DM 17/06/2014, electronic invoices transmitted
via SDI must be archived for a minimum of 10 years using a process that
guarantees integrity, authenticity, and readability over time.

This module provides a local filesystem implementation for development and
testing. Production use requires integration with an AgID-accredited
conservazione provider (e.g. InfoCert, Aruba PEC, Namirial).

[NEED: specific AgID-accredited provider API details for production integration]
"""

from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from mcp_einvoicing_core.archive import ArchiveMetadata, BaseArchiveProvider
from mcp_einvoicing_core.logging_utils import get_logger
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = get_logger(__name__)

_DEFAULT_RETENTION_YEARS = 10


class ConservazioneSettings(BaseSettings):
    """Configuration for conservazione sostitutiva."""

    model_config = SettingsConfigDict(
        env_prefix="CONSERVAZIONE_",
        env_file=".env",
        extra="ignore",
    )

    storage_path: str = Field(
        default="",
        description=(
            "Local filesystem path for development/test archival storage. "
            "Production must use an AgID-accredited provider."
        ),
    )
    provider_url: str = Field(
        default="",
        description="API URL of the AgID-accredited conservazione provider.",
    )
    api_key: str = Field(
        default="",
        description="API key for the conservazione provider.",
    )
    retention_years: int = Field(
        default=_DEFAULT_RETENTION_YEARS,
        description="Retention period in years (minimum 10 per DM 17/06/2014).",
    )


class ConservazioneProvider(BaseArchiveProvider):
    """Local filesystem conservazione provider for development and testing.

    Production deployments must replace this with an integration to an
    AgID-accredited conservazione provider. This local implementation
    stores documents as files with JSON metadata sidecar files.
    """

    def __init__(self, settings: ConservazioneSettings | None = None) -> None:
        self._settings = settings or ConservazioneSettings()
        self._storage_path = Path(
            self._settings.storage_path or os.path.join(os.getcwd(), ".conservazione")
        )

    def _ensure_storage(self) -> Path:
        self._storage_path.mkdir(parents=True, exist_ok=True)
        return self._storage_path

    async def archive_document(self, document: bytes, metadata: dict[str, Any]) -> ArchiveMetadata:
        storage = self._ensure_storage()
        doc_hash = hashlib.sha256(document).hexdigest()
        now = datetime.now(UTC)
        retention_until = now + timedelta(days=365 * self._settings.retention_years)

        doc_id = metadata.get("document_id") or f"{now.strftime('%Y%m%d%H%M%S')}_{doc_hash[:12]}"
        format_id = metadata.get("format_id", "FatturaPA-1.2.3")
        signer_id = metadata.get("signer_id")

        doc_path = storage / f"{doc_id}.dat"
        meta_path = storage / f"{doc_id}.meta.json"

        doc_path.write_bytes(document)

        archive_meta = ArchiveMetadata(
            document_id=doc_id,
            document_hash=doc_hash,
            archive_timestamp=now,
            retention_until=retention_until,
            format_id=format_id,
            signer_id=signer_id,
            raw=metadata,
        )

        meta_path.write_text(archive_meta.model_dump_json(indent=2), encoding="utf-8")

        logger.info(
            "Archived document %s (hash=%s, retention_until=%s)",
            doc_id,
            doc_hash[:16],
            retention_until.isoformat(),
        )
        return archive_meta

    async def retrieve_document(self, document_id: str) -> tuple[bytes, ArchiveMetadata]:
        storage = self._ensure_storage()
        doc_path = storage / f"{document_id}.dat"
        meta_path = storage / f"{document_id}.meta.json"

        if not doc_path.exists():
            raise FileNotFoundError(f"Archived document not found: {document_id}")

        document = doc_path.read_bytes()
        meta_json = meta_path.read_text(encoding="utf-8")
        meta = ArchiveMetadata.model_validate_json(meta_json)

        return document, meta

    async def list_documents(self, criteria: dict[str, Any]) -> list[ArchiveMetadata]:
        storage = self._ensure_storage()
        results: list[ArchiveMetadata] = []

        for meta_file in sorted(storage.glob("*.meta.json")):
            meta = ArchiveMetadata.model_validate_json(meta_file.read_text(encoding="utf-8"))
            results.append(meta)

        return results

    async def verify_integrity(self, document_id: str) -> bool:
        try:
            document, meta = await self.retrieve_document(document_id)
        except FileNotFoundError:
            return False

        actual_hash = hashlib.sha256(document).hexdigest()
        return actual_hash == meta.document_hash
