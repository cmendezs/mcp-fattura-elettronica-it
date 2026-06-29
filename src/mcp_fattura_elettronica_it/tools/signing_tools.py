"""MCP tools for FatturaPA digital signatures (XAdES-BES and CAdES-BES).

SDI accepts two signature formats (Specifiche tecniche SDI v1.8.4, s2.1):
- XAdES-BES: enveloped XML signature, file extension .xml
- CAdES-BES: CMS/PKCS#7 attached signature, file extension .xml.p7m

Both require a qualified electronic signature (firma elettronica qualificata)
issued by an accredited CA for production use.
"""

from __future__ import annotations

import base64
from typing import Any

from fastmcp import FastMCP

from mcp_einvoicing_core.base_server import assert_not_read_only
from mcp_einvoicing_core.confirmation import ConfirmationGate
from mcp_einvoicing_core.logging_utils import get_logger
from mcp_einvoicing_core.signer_client import SignerClient

logger = get_logger(__name__)


def _ok(data: dict[str, Any]) -> dict[str, Any]:
    return data


def _err(message: str, code: str) -> dict[str, Any]:
    return {"error": message, "error_code": code}


def register_signing_tools(mcp: FastMCP) -> None:
    """Register FatturaPA signing tools on *mcp*."""

    @mcp.tool(
        name="it__sign_fattura_xades",
        description=(
            "Apply an XAdES-BES enveloped XML signature to a FatturaPA XML document. "
            "The signed XML retains the .xml extension. Requires a qualified PKCS#12 "
            "certificate. Uses the signer microservice when available, falls back to "
            "direct signing. Requires confirmation (irreversible)."
        ),
    )
    async def sign_fattura_xades(
        xml: str,
        cert_path: str = "",
        cert_password: str | None = None,
        confirmation_token: str | None = None,
    ) -> dict[str, Any]:
        try:
            if not xml:
                return _err("xml is required", "MISSING_PARAM")

            assert_not_read_only("SDI_READ_ONLY")
            gate = ConfirmationGate.get_default()
            if not gate.is_confirmed(confirmation_token):
                return gate.pending_response(
                    action="it__sign_fattura_xades",
                    summary=(
                        "Apply XAdES-BES signature to a FatturaPA XML document using "
                        "a PKCS#12 certificate. The signed XML will contain a legally "
                        "binding electronic signature."
                    ),
                    token=confirmation_token,
                )

            xml_bytes = xml.encode("utf-8")

            if SignerClient.is_configured():
                signer_client = SignerClient.from_env()
                signed_bytes = await signer_client.sign(
                    xml_bytes, algorithm="xades"
                )
                logger.info("FatturaPA XAdES-BES signature applied via signer microservice")
            else:
                if not cert_path:
                    return _err(
                        "cert_path is required when signer microservice is not configured "
                        "(EINVOICING_SIGNER_SOCKET not set)",
                        "MISSING_PARAM",
                    )
                from mcp_einvoicing_core.digital_signature import (
                    XAdESEPESSigner,
                    XAdESSignerConfig,
                )

                config = XAdESSignerConfig(
                    cert_path=cert_path,
                    cert_password=cert_password,
                    signature_policy_id=None,
                )
                signer = XAdESEPESSigner(config)
                signed_bytes = signer.sign(xml_bytes)
                logger.info("FatturaPA XAdES-BES signature applied with cert %s", cert_path)

            gate.consume(confirmation_token)
            return _ok({
                "signed_xml": signed_bytes.decode("utf-8"),
                "signature_format": "XAdES-BES",
            })

        except ImportError as exc:
            return _err(
                f"cryptography>=42.0.0 is required for XAdES signing: {exc}",
                "MISSING_DEPENDENCY",
            )
        except Exception as exc:
            logger.exception("it__sign_fattura_xades failed")
            return _err(str(exc), "SIGNING_ERROR")

    @mcp.tool(
        name="it__sign_fattura_cades",
        description=(
            "Apply a CAdES-BES (CMS/PKCS#7) attached signature to a FatturaPA XML "
            "document. The output is a DER-encoded .xml.p7m file (base64-encoded in "
            "the response). Requires a qualified PKCS#12 certificate. Uses the signer "
            "microservice when available, falls back to direct signing. "
            "Requires confirmation (irreversible)."
        ),
    )
    async def sign_fattura_cades(
        xml: str,
        cert_path: str = "",
        cert_password: str | None = None,
        confirmation_token: str | None = None,
    ) -> dict[str, Any]:
        try:
            if not xml:
                return _err("xml is required", "MISSING_PARAM")

            assert_not_read_only("SDI_READ_ONLY")
            gate = ConfirmationGate.get_default()
            if not gate.is_confirmed(confirmation_token):
                return gate.pending_response(
                    action="it__sign_fattura_cades",
                    summary=(
                        "Apply CAdES-BES (CMS/PKCS#7) signature to a FatturaPA XML "
                        "document. The output is a .xml.p7m file containing the signed "
                        "invoice in PKCS#7 format."
                    ),
                    token=confirmation_token,
                )

            xml_bytes = xml.encode("utf-8")

            if SignerClient.is_configured():
                signer_client = SignerClient.from_env()
                signed_bytes = await signer_client.sign(
                    xml_bytes, algorithm="cades-bes"
                )
                logger.info("FatturaPA CAdES-BES signature applied via signer microservice")
            else:
                if not cert_path:
                    return _err(
                        "cert_path is required when signer microservice is not configured "
                        "(EINVOICING_SIGNER_SOCKET not set)",
                        "MISSING_PARAM",
                    )
                from mcp_einvoicing_core.digital_signature import (
                    CAdESSigner,
                    CAdESSignerConfig,
                )

                config = CAdESSignerConfig(
                    cert_path=cert_path,
                    cert_password=cert_password,
                )
                signer = CAdESSigner(config)
                signed_bytes = signer.sign(xml_bytes)
                logger.info("FatturaPA CAdES-BES signature applied with cert %s", cert_path)

            gate.consume(confirmation_token)
            return _ok({
                "signed_p7m_base64": base64.b64encode(signed_bytes).decode(),
                "signature_format": "CAdES-BES",
                "length_bytes": len(signed_bytes),
            })

        except ImportError as exc:
            return _err(
                f"cryptography>=42.0.0 is required for CAdES signing: {exc}",
                "MISSING_DEPENDENCY",
            )
        except Exception as exc:
            logger.exception("it__sign_fattura_cades failed")
            return _err(str(exc), "SIGNING_ERROR")
