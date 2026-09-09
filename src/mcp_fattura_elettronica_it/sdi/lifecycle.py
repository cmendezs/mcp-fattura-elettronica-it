"""SDI lifecycle manager implementing core BaseLifecycleManager."""

from __future__ import annotations

from typing import Any

from mcp_einvoicing_core.base_server import (
    BaseLifecycleManager,
    SearchCriteria,
    SubmissionMetadata,
    SubmitResult,
)
from mcp_einvoicing_core.logging_utils import get_logger

from mcp_fattura_elettronica_it.sdi.client import SDICoopClient
from mcp_fattura_elettronica_it.sdi.config import SDISettings

logger = get_logger(__name__)


class SDISubmissionMetadata(SubmissionMetadata):
    """Typed metadata for ``SDILifecycleManager.submit_document``.

    Added v0.8.0 (CORE-2, core audit Step 8): replaces the untyped
    ``dict`` this method previously took.
    """

    filename: str
    channel_id: str | None = None


class SDIEsitoMetadata(SubmissionMetadata):
    """Typed metadata for ``SDILifecycleManager.submit_lifecycle_status``.

    Added v0.8.0 (CORE-2, core audit Step 8), alongside
    `SDISubmissionMetadata` — see its docstring for the rationale.
    """

    nome_file: str
    esito_xml: bytes = b""


class SDILifecycleManager(BaseLifecycleManager):
    """Lifecycle manager for SDI invoice submission and status tracking."""

    def __init__(self, settings: SDISettings | None = None) -> None:
        self._settings = settings or SDISettings()
        self._client = SDICoopClient(self._settings)

    async def submit_document(
        self,
        document: bytes | str,
        metadata: SDISubmissionMetadata,
    ) -> SubmitResult:
        """Submit a signed invoice to SDI.

        Args:
            document: Signed invoice bytes or base64-encoded string.
            metadata: `SDISubmissionMetadata` with the required ``filename``
                and an optional ``channel_id`` override.

        Returns:
            SubmitResult with IdentificativoSDI as invoice_ref.
        """
        if isinstance(document, str):
            document = document.encode("utf-8")

        if not metadata.filename:
            raise ValueError("metadata.filename is required for SDI submission")

        result = await self._client.send_invoice(document, metadata.filename)

        id_sdi = result.get("identificativo_sdi", "")

        return SubmitResult(
            invoice_ref=str(id_sdi),
            status="submitted",
            raw=result,
        )

    async def get_document_status(self, document_id: str) -> dict[str, Any]:
        """Return the last known status of a submitted invoice.

        SDI communicates status asynchronously via notifications (RC, NS, MC,
        etc.). This method returns the locally tracked status. For real-time
        status, parse incoming notifications using ``parse_notification``.
        """
        logger.info("SDI status query for IdentificativoSDI=%s", document_id)
        return {
            "identificativo_sdi": document_id,
            "status": "unknown",
            "note": (
                "SDI communicates status asynchronously via notifications. "
                "Use it__parse_sdi_notification to process received notifications."
            ),
        }

    async def search_documents(self, criteria: SearchCriteria) -> list[dict[str, Any]]:
        """Search is not supported by SDICoop.

        SDI does not provide a query API. Document tracking must be maintained
        locally by processing incoming notifications.
        """
        return []

    async def submit_lifecycle_status(
        self,
        document_id: str,
        status: str,
        metadata: SDIEsitoMetadata,
    ) -> dict[str, Any]:
        """Send an acceptance (EC01) or rejection (EC02) notification to SDI.

        Args:
            document_id: IdentificativoSDI of the invoice.
            status: ``"EC01"`` for acceptance, ``"EC02"`` for rejection.
            metadata: `SDIEsitoMetadata` with ``nome_file`` and ``esito_xml``.
        """
        result = await self._client.send_esito(document_id, metadata.nome_file, metadata.esito_xml)
        return result
