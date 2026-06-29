"""SDICoop SOAP client for invoice transmission and notification exchange.

Uses mTLS certificate authentication per SDI spec v1.8.4, section 3.1.2.
Max attachment size: 5 MB per SOAP message.
"""

from __future__ import annotations

from typing import Any

from mcp_einvoicing_core.exceptions import PlatformError
from mcp_einvoicing_core.http_client import AuthMode, BaseEInvoicingClient
from mcp_einvoicing_core.logging_utils import get_logger

from mcp_fattura_elettronica_it.sdi.config import SDISettings
from mcp_fattura_elettronica_it.sdi.soap import (
    build_notifica_esito_envelope,
    build_ricevi_fatture_envelope,
    parse_sdi_soap_response,
)

logger = get_logger(__name__)

_MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024


class SDICoopClient(BaseEInvoicingClient):
    """SOAP client for SDICoop invoice transmission and notification exchange."""

    def __init__(self, settings: SDISettings) -> None:
        self._settings = settings
        super().__init__(
            base_url=settings.effective_endpoint,
            auth_mode=AuthMode.MTLS,
            cert_path=settings.cert_path or None,
            cert_password=settings.cert_password,
            http_timeout=float(settings.timeout),
        )

    async def send_invoice(
        self,
        signed_file: bytes,
        filename: str,
    ) -> dict[str, Any]:
        """Submit a signed invoice to SDI via the RiceviFatture operation.

        Args:
            signed_file: Signed invoice bytes (.xml or .xml.p7m).
            filename: SDI-compliant filename.

        Returns:
            Parsed SOAP response dict with ``identificativo_sdi`` on success.

        Raises:
            ValueError: If the attachment exceeds the 5 MB limit.
            PlatformError: On HTTP or SOAP-level errors.
        """
        if len(signed_file) > _MAX_ATTACHMENT_BYTES:
            raise ValueError(
                f"Attachment size {len(signed_file)} bytes exceeds the SDICoop "
                f"limit of {_MAX_ATTACHMENT_BYTES} bytes (5 MB)"
            )

        envelope = build_ricevi_fatture_envelope(filename, signed_file)
        return await self._post_soap(envelope)

    async def send_esito(
        self,
        id_sdi: str,
        nome_file: str,
        esito_xml: bytes,
    ) -> dict[str, Any]:
        """Send an acceptance (EC01) or rejection (EC02) notification.

        Args:
            id_sdi: IdentificativoSDI of the received invoice.
            nome_file: Notification filename per SDI naming convention.
            esito_xml: The EC notification XML bytes.

        Returns:
            Parsed SOAP response dict.

        Raises:
            PlatformError: On HTTP or SOAP-level errors.
        """
        envelope = build_notifica_esito_envelope(id_sdi, nome_file, esito_xml)
        return await self._post_soap(envelope)

    async def _post_soap(self, envelope: bytes) -> dict[str, Any]:
        """POST a SOAP envelope to the SDICoop endpoint.

        Returns:
            Parsed response dict from ``parse_sdi_soap_response``.
        """
        client = await self._get_client()
        response = await client.post(
            self._base_url,
            content=envelope,
            headers={
                "Content-Type": "text/xml; charset=utf-8",
                "SOAPAction": '""',
            },
        )

        if not response.is_success:
            raise PlatformError(
                f"SDICoop SOAP call failed with HTTP {response.status_code}",
                status_code=response.status_code,
                response_body=response.text[:500],
            )

        result = parse_sdi_soap_response(response.content)
        if result.get("errore"):
            raise PlatformError(
                f"SDI returned error: {result['errore']}",
                status_code=response.status_code,
                response_body=str(result),
            )

        return result
