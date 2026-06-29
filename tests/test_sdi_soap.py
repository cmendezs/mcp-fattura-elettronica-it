"""Tests for SDI SOAP envelope construction and parsing."""

from __future__ import annotations

from lxml import etree

from mcp_fattura_elettronica_it.sdi.soap import (
    build_notifica_esito_envelope,
    build_ricevi_fatture_envelope,
    parse_sdi_soap_response,
)


class TestBuildRiceviFattureEnvelope:
    def test_produces_valid_xml(self):
        result = build_ricevi_fatture_envelope(
            "IT01234567890_00001.xml", b"<test/>"
        )
        root = etree.fromstring(result)
        assert "Envelope" in root.tag

    def test_contains_filename(self):
        result = build_ricevi_fatture_envelope(
            "IT01234567890_00001.xml", b"<test/>"
        )
        assert b"IT01234567890_00001.xml" in result

    def test_contains_base64_content(self):
        result = build_ricevi_fatture_envelope("test.xml", b"hello")
        assert b"aGVsbG8=" in result


class TestBuildNotificaEsitoEnvelope:
    def test_produces_valid_xml(self):
        result = build_notifica_esito_envelope(
            "123456789012", "test_EC_001.xml", b"<esito/>"
        )
        root = etree.fromstring(result)
        assert "Envelope" in root.tag

    def test_contains_id_sdi(self):
        result = build_notifica_esito_envelope(
            "123456789012", "test_EC_001.xml", b"<esito/>"
        )
        assert b"123456789012" in result


class TestParseSdiSoapResponse:
    def test_extracts_fields(self):
        response = (
            b'<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">'
            b"<soapenv:Body>"
            b"<IdentificativoSdI>999888777666</IdentificativoSdI>"
            b"<DataOraRicezione>2026-06-29T10:00</DataOraRicezione>"
            b"</soapenv:Body>"
            b"</soapenv:Envelope>"
        )
        result = parse_sdi_soap_response(response)
        assert result["IdentificativoSdI"] == "999888777666"

    def test_soap_fault_extracted(self):
        response = (
            b'<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">'
            b"<soapenv:Body>"
            b"<soapenv:Fault>"
            b"<faultstring>Internal Error</faultstring>"
            b"</soapenv:Fault>"
            b"</soapenv:Body>"
            b"</soapenv:Envelope>"
        )
        result = parse_sdi_soap_response(response)
        assert result["errore"] == "Internal Error"
