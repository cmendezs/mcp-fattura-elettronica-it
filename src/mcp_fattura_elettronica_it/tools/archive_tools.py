"""MCP tools for conservazione sostitutiva (legally compliant archiving).

Per AgID circolare 65/2014, electronic invoices must be archived for a
minimum of 10 years with guaranteed integrity and readability.
"""

from __future__ import annotations

import base64
from typing import Any

from fastmcp import FastMCP
from mcp_einvoicing_core.logging_utils import get_logger

from mcp_fattura_elettronica_it.archive.conservazione import (
    ConservazioneProvider,
    ConservazioneSettings,
)
from mcp_fattura_elettronica_it.archive.pacchetto import build_pacchetto_di_versamento

logger = get_logger(__name__)


def _ok(data: dict[str, Any]) -> dict[str, Any]:
    return data


def _err(message: str, code: str) -> dict[str, Any]:
    return {"error": message, "error_code": code}


def register_archive_tools(mcp: FastMCP) -> None:
    """Register conservazione sostitutiva tools on *mcp*."""

    @mcp.tool(
        name="it__archive_invoice",
        description=(
            "Archive a signed invoice for conservazione sostitutiva. Stores the "
            "document with SHA-256 hash, timestamp, and retention metadata per "
            "AgID circolare 65/2014. Returns the archive metadata including "
            "document_id and retention_until date."
        ),
    )
    async def archive_invoice(
        document_base64: str,
        format_id: str = "FatturaPA-1.2.3",
        signer_id: str = "",
        document_id: str = "",
    ) -> dict[str, Any]:
        try:
            if not document_base64:
                return _err("document_base64 is required", "MISSING_PARAM")

            doc_bytes = base64.b64decode(document_base64)
            settings = ConservazioneSettings()
            provider = ConservazioneProvider(settings)

            metadata: dict[str, Any] = {"format_id": format_id}
            if signer_id:
                metadata["signer_id"] = signer_id
            if document_id:
                metadata["document_id"] = document_id

            result = await provider.archive_document(doc_bytes, metadata)
            return _ok(result.model_dump(mode="json"))

        except Exception as exc:
            logger.exception("it__archive_invoice failed")
            return _err(str(exc), "ARCHIVE_ERROR")

    @mcp.tool(
        name="it__retrieve_archived_invoice",
        description=(
            "Retrieve an archived invoice by its document_id. Returns the "
            "document content (base64-encoded) and its archive metadata."
        ),
    )
    async def retrieve_archived_invoice(
        document_id: str,
    ) -> dict[str, Any]:
        try:
            if not document_id:
                return _err("document_id is required", "MISSING_PARAM")

            provider = ConservazioneProvider()
            doc_bytes, meta = await provider.retrieve_document(document_id)
            return _ok({
                "document_base64": base64.b64encode(doc_bytes).decode(),
                "length_bytes": len(doc_bytes),
                **meta.model_dump(mode="json"),
            })

        except FileNotFoundError:
            return _err(f"Document not found: {document_id}", "NOT_FOUND")
        except Exception as exc:
            logger.exception("it__retrieve_archived_invoice failed")
            return _err(str(exc), "ARCHIVE_ERROR")

    @mcp.tool(
        name="it__verify_archive_integrity",
        description=(
            "Verify the integrity of an archived document by recomputing its "
            "SHA-256 hash and comparing against the stored hash."
        ),
    )
    async def verify_archive_integrity(
        document_id: str,
    ) -> dict[str, Any]:
        try:
            if not document_id:
                return _err("document_id is required", "MISSING_PARAM")

            provider = ConservazioneProvider()
            is_valid = await provider.verify_integrity(document_id)
            return _ok({
                "document_id": document_id,
                "integrity_valid": is_valid,
            })

        except Exception as exc:
            logger.exception("it__verify_archive_integrity failed")
            return _err(str(exc), "ARCHIVE_ERROR")

    @mcp.tool(
        name="it__list_archived_invoices",
        description=(
            "List all archived invoices. Returns a list of archive metadata "
            "records sorted by archive date."
        ),
    )
    async def list_archived_invoices() -> dict[str, Any]:
        try:
            provider = ConservazioneProvider()
            results = await provider.list_documents({})
            return _ok({
                "count": len(results),
                "documents": [r.model_dump(mode="json") for r in results],
            })

        except Exception as exc:
            logger.exception("it__list_archived_invoices failed")
            return _err(str(exc), "ARCHIVE_ERROR")

    @mcp.tool(
        name="it__build_pacchetto_versamento",
        description=(
            "Build a Pacchetto di Versamento (PdV) ZIP archive containing one or "
            "more signed invoices and an XML index (IPdV). The PdV is the unit of "
            "transfer to an AgID-accredited conservazione provider."
        ),
    )
    async def build_pdv(
        documents_json: str,
        producer_id: str = "",
    ) -> dict[str, Any]:
        try:
            import json

            docs_raw = json.loads(documents_json)
            if not isinstance(docs_raw, list) or not docs_raw:
                return _err(
                    "documents_json must be a non-empty JSON array of "
                    '{"filename": str, "content_base64": str} objects',
                    "INVALID_PARAM",
                )

            documents: list[tuple[str, bytes]] = []
            for entry in docs_raw:
                filename = entry.get("filename", "")
                content_b64 = entry.get("content_base64", "")
                if not filename or not content_b64:
                    return _err(
                        "Each document must have 'filename' and 'content_base64'",
                        "INVALID_PARAM",
                    )
                documents.append((filename, base64.b64decode(content_b64)))

            metadata: dict[str, Any] = {}
            if producer_id:
                metadata["producer_id"] = producer_id

            pdv_bytes = build_pacchetto_di_versamento(documents, metadata)
            return _ok({
                "pdv_base64": base64.b64encode(pdv_bytes).decode(),
                "length_bytes": len(pdv_bytes),
                "document_count": len(documents),
            })

        except json.JSONDecodeError as exc:
            return _err(f"Invalid JSON: {exc}", "INVALID_PARAM")
        except Exception as exc:
            logger.exception("it__build_pacchetto_versamento failed")
            return _err(str(exc), "ARCHIVE_ERROR")
