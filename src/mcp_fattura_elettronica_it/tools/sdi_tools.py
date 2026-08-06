"""MCP tools for SDI (Sistema di Interscambio) integration.

Covers invoice submission via SDICoop, notification parsing, and
buyer acceptance/rejection (esito committente).
"""

from __future__ import annotations

import base64
from typing import Any

from fastmcp import FastMCP
from mcp_einvoicing_core.base_server import assert_not_read_only
from mcp_einvoicing_core.confirmation import ConfirmationGate
from mcp_einvoicing_core.logging_utils import get_logger

from mcp_fattura_elettronica_it.sdi.config import SDISettings
from mcp_fattura_elettronica_it.sdi.lifecycle import SDILifecycleManager
from mcp_fattura_elettronica_it.sdi.notifications import parse_notification

logger = get_logger(__name__)


def _ok(data: dict[str, Any]) -> dict[str, Any]:
    return data


def _err(message: str, code: str) -> dict[str, Any]:
    return {"error": message, "error_code": code}


def register_sdi_tools(mcp: FastMCP) -> None:
    """Register SDI integration tools on *mcp*."""

    @mcp.tool(
        name="it__submit_to_sdi",
        description=(
            "Submit a signed FatturaPA invoice to SDI via SDICoop. The invoice must "
            "be signed (XAdES-BES or CAdES-BES) before submission. Requires mTLS "
            "certificate configuration. Returns the IdentificativoSDI assigned by SDI. "
            "Requires confirmation (irreversible)."
        ),
    )
    async def submit_to_sdi(
        signed_file_base64: str,
        filename: str,
        confirmation_token: str | None = None,
    ) -> dict[str, Any]:
        try:
            if not signed_file_base64:
                return _err("signed_file_base64 is required", "MISSING_PARAM")
            if not filename:
                return _err("filename is required", "MISSING_PARAM")

            assert_not_read_only("SDI_READ_ONLY")
            gate = ConfirmationGate.get_default()
            if not gate.is_confirmed(confirmation_token):
                return gate.pending_response(
                    action="it__submit_to_sdi",
                    summary=(
                        f"Submit signed invoice '{filename}' to SDI via SDICoop. "
                        "This submits the invoice to the Italian tax authority. "
                        "The action is irreversible in production."
                    ),
                    token=confirmation_token,
                )

            signed_bytes = base64.b64decode(signed_file_base64)
            settings = SDISettings()
            manager = SDILifecycleManager(settings)
            result = await manager.submit_document(
                signed_bytes, {"filename": filename}
            )

            gate.consume(confirmation_token)
            return _ok({
                "identificativo_sdi": result.invoice_ref,
                "status": result.status,
                "environment": settings.environment.value,
                "raw": result.raw,
            })

        except Exception as exc:
            logger.exception("it__submit_to_sdi failed")
            return _err(str(exc), "SUBMISSION_ERROR")

    @mcp.tool(
        name="it__check_sdi_status",
        description=(
            "Check the status of a previously submitted invoice by its "
            "IdentificativoSDI. SDI communicates status asynchronously via "
            "notifications; this returns the last known local status."
        ),
    )
    async def check_sdi_status(
        identificativo_sdi: str,
    ) -> dict[str, Any]:
        try:
            if not identificativo_sdi:
                return _err("identificativo_sdi is required", "MISSING_PARAM")

            manager = SDILifecycleManager()
            return await manager.get_document_status(identificativo_sdi)

        except Exception as exc:
            logger.exception("it__check_sdi_status failed")
            return _err(str(exc), "STATUS_ERROR")

    @mcp.tool(
        name="it__parse_sdi_notification",
        description=(
            "Parse an SDI notification XML into a structured dict. Supports all "
            "notification types: RC (delivery receipt), NS (rejection with error "
            "codes), MC (delivery failure), NE (seller outcome), EC (buyer "
            "acceptance/rejection), SE (outcome rejection), DT (deadline expiry), "
            "MT (metadata), AT (undeliverable attestation)."
        ),
    )
    async def parse_sdi_notification_tool(
        notification_xml: str,
    ) -> dict[str, Any]:
        try:
            if not notification_xml:
                return _err("notification_xml is required", "MISSING_PARAM")

            notification = parse_notification(notification_xml.encode("utf-8"))
            return _ok(notification.model_dump(exclude_none=True))

        except ValueError as exc:
            return _err(str(exc), "PARSE_ERROR")
        except Exception as exc:
            logger.exception("it__parse_sdi_notification failed")
            return _err(str(exc), "PARSE_ERROR")

    @mcp.tool(
        name="it__send_esito_committente",
        description=(
            "Send an acceptance (EC01) or rejection (EC02) notification to SDI for "
            "a received invoice. The esito XML must conform to the "
            "NotificaEsitoCommittente schema (MessaggiTypes_v1.1.xsd). "
            "Requires confirmation (irreversible)."
        ),
    )
    async def send_esito_committente(
        identificativo_sdi: str,
        esito: str,
        nome_file: str,
        esito_xml: str,
        confirmation_token: str | None = None,
    ) -> dict[str, Any]:
        try:
            if not identificativo_sdi:
                return _err("identificativo_sdi is required", "MISSING_PARAM")
            if esito not in ("EC01", "EC02"):
                return _err("esito must be 'EC01' (accept) or 'EC02' (reject)", "INVALID_PARAM")
            if not nome_file:
                return _err("nome_file is required", "MISSING_PARAM")
            if not esito_xml:
                return _err("esito_xml is required", "MISSING_PARAM")

            assert_not_read_only("SDI_READ_ONLY")
            gate = ConfirmationGate.get_default()
            action_label = "accept" if esito == "EC01" else "reject"
            if not gate.is_confirmed(confirmation_token):
                return gate.pending_response(
                    action="it__send_esito_committente",
                    summary=(
                        f"Send {action_label} ({esito}) notification to SDI for "
                        f"invoice IdentificativoSDI={identificativo_sdi}. "
                        "This action is irreversible."
                    ),
                    token=confirmation_token,
                )

            manager = SDILifecycleManager()
            result = await manager.submit_lifecycle_status(
                identificativo_sdi,
                esito,
                {"nome_file": nome_file, "esito_xml": esito_xml.encode("utf-8")},
            )

            gate.consume(confirmation_token)
            return _ok({"status": "sent", "esito": esito, "raw": result})

        except Exception as exc:
            logger.exception("it__send_esito_committente failed")
            return _err(str(exc), "ESITO_ERROR")

    @mcp.tool(
        name="it__get_sdi_channel_info",
        description=(
            "Show current SDI channel configuration: environment, channel type, "
            "channel ID, endpoint URL, and certificate status. Does not expose "
            "sensitive values (cert_password)."
        ),
    )
    async def get_sdi_channel_info() -> dict[str, Any]:
        settings = SDISettings()
        return _ok({
            "environment": settings.environment.value,
            "channel": settings.channel.value,
            "channel_id": settings.channel_id or "(not configured)",
            "endpoint_url": settings.effective_endpoint,
            "cert_configured": bool(settings.cert_path),
            "timeout": settings.timeout,
        })
