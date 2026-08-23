"""SOAP envelope construction and parsing for SDICoop protocol.

SDICoop uses SOAP 1.1 with attachments over HTTPS + TLS 1.2.
The two primary operations are RiceviFatture (send invoice) and
NotificaEsito (send buyer acceptance/rejection).
"""

from __future__ import annotations

import base64

from lxml import etree
from mcp_einvoicing_core.xml_utils import safe_fromstring

_SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"
_SDI_NS = "http://www.fatturapa.gov.it/sdi/ws/trasmissione/v1.0/types"

_SOAP_NSMAP = {"soapenv": _SOAP_NS, "sdi": _SDI_NS}


def build_ricevi_fatture_envelope(
    filename: str,
    file_content: bytes,
) -> bytes:
    """Build a SOAP envelope for the RiceviFatture operation.

    Args:
        filename: SDI-compliant filename (e.g. ``IT01234567890_00001.xml``).
        file_content: Signed invoice bytes (XML or P7M).

    Returns:
        UTF-8 encoded SOAP envelope bytes.
    """
    envelope = etree.Element(f"{{{_SOAP_NS}}}Envelope", nsmap=_SOAP_NSMAP)
    etree.SubElement(envelope, f"{{{_SOAP_NS}}}Header")
    body = etree.SubElement(envelope, f"{{{_SOAP_NS}}}Body")

    richiesta = etree.SubElement(body, f"{{{_SDI_NS}}}fileSdIAccoglienza")
    etree.SubElement(richiesta, f"{{{_SDI_NS}}}NomeFile").text = filename
    etree.SubElement(richiesta, f"{{{_SDI_NS}}}File").text = base64.b64encode(file_content).decode()

    return etree.tostring(envelope, xml_declaration=True, encoding="UTF-8")


def build_notifica_esito_envelope(
    id_sdi: str,
    nome_file: str,
    esito_xml: bytes,
) -> bytes:
    """Build a SOAP envelope for the NotificaEsito operation.

    Args:
        id_sdi: The IdentificativoSDI of the received invoice.
        nome_file: Notification filename following SDI naming convention.
        esito_xml: The EC notification XML bytes (EC01 acceptance or EC02 rejection).

    Returns:
        UTF-8 encoded SOAP envelope bytes.
    """
    envelope = etree.Element(f"{{{_SOAP_NS}}}Envelope", nsmap=_SOAP_NSMAP)
    etree.SubElement(envelope, f"{{{_SOAP_NS}}}Header")
    body = etree.SubElement(envelope, f"{{{_SOAP_NS}}}Body")

    richiesta = etree.SubElement(body, f"{{{_SDI_NS}}}risposta")
    etree.SubElement(richiesta, f"{{{_SDI_NS}}}IdentificativoSdI").text = id_sdi
    etree.SubElement(richiesta, f"{{{_SDI_NS}}}NomeFile").text = nome_file
    etree.SubElement(richiesta, f"{{{_SDI_NS}}}File").text = base64.b64encode(esito_xml).decode()

    return etree.tostring(envelope, xml_declaration=True, encoding="UTF-8")


def parse_sdi_soap_response(response_bytes: bytes) -> dict:
    """Parse an SDI SOAP response and extract the result fields.

    Returns:
        Dict with at minimum ``identificativo_sdi`` (str) and ``errore`` (str or None).
    """
    root = safe_fromstring(response_bytes)
    body = root.find(f".//{{{_SOAP_NS}}}Body")
    if body is None:
        return {"errore": "No SOAP Body found in response"}

    result: dict = {}
    for child in body.iter():
        local = etree.QName(child).localname
        if child.text and child.text.strip():
            result[local] = child.text.strip()

    if "IdentificativoSdI" in result:
        result["identificativo_sdi"] = result["IdentificativoSdI"]

    fault = root.find(f".//{{{_SOAP_NS}}}Fault")
    if fault is not None:
        faultstring = fault.findtext("faultstring") or "Unknown SOAP fault"
        result["errore"] = faultstring

    return result
