"""SDI lifecycle manager implementing core BaseLifecycleManager."""

from __future__ import annotations

from typing import Any, Optional

from mcp_einvoicing_core.base_server import BaseLifecycleManager, SubmitResult
from mcp_einvoicing_core.logging_utils import get_logger

from mcp_fattura_elettronica_it.sdi.client import SDICoopClient
from mcp_fattura_elettronica_it.sdi.config import SDISettings

logger = get_logger(__name__)


class SDILifecycleManager(BaseLifecycleManager):
    """Lifecycle manager for SDI invoice submission and status tracking."""

    def __init__(self, settings: Optional[SDISettings] = None) -> None:
        self._settings = settings or SDISettings()
        self._client = SDICoopClient(self._settings)

    async def submit_document(
        self,
        document: bytes | str,
        metadata: dict[str, Any],
    ) -> SubmitResult:
        """Submit a signed invoice to SDI.

        Args:
            document: Signed invoice bytes or base64-encoded string.
            metadata: Must contain ``filename`` (str). May contain
                ``channel_id`` to override the configured channel.

        Returns:
            SubmitResult with IdentificativoSDI as invoice_ref.
        """
        if isinstance(document, str):
            document = document.encode("utf-8")

        filename = metadata.get("filename", "")
        if not filename:
            raise ValueError("metadata['filename'] is required for SDI submission")

        result = await self._client.send_invoice(document, filename)

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

    async def search_documents(
        self, criteria: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Search is not supported by SDICoop.

        SDI does not provide a query API. Document tracking must be maintained
        locally by processing incoming notifications.
        """
        return []

    async def submit_lifecycle_status(
        self,
        document_id: str,
        status: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        """Send an acceptance (EC01) or rejection (EC02) notification to SDI.

        Args:
            document_id: IdentificativoSDI of the invoice.
            status: ``"EC01"`` for acceptance, ``"EC02"`` for rejection.
            metadata: Must contain ``nome_file`` and ``esito_xml`` (bytes).
        """
        nome_file = metadata.get("nome_file", "")
        esito_xml = metadata.get("esito_xml", b"")
        if isinstance(esito_xml, str):
            esito_xml = esito_xml.encode("utf-8")

        result = await self._client.send_esito(document_id, nome_file, esito_xml)
        return result
