"""Tests for SDI notification parsing."""

from __future__ import annotations

import pytest

from mcp_fattura_elettronica_it.sdi.notifications import (
    SDINotificationType,
    parse_notification,
)

_RC_XML = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<RicevutaConsegna>
  <IdentificativoSdI>123456789012</IdentificativoSdI>
  <NomeFile>IT01234567890_00001.xml</NomeFile>
  <DataOraRicezione>2026-06-29T10:00</DataOraRicezione>
  <DataOraConsegna>2026-06-29T10:01</DataOraConsegna>
  <Destinatario>
    <Codice>ABCDEFG</Codice>
    <Descrizione>Acme Srl</Descrizione>
  </Destinatario>
  <MessageId>999</MessageId>
</RicevutaConsegna>
"""

_NS_XML = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<NotificaScarto>
  <IdentificativoSdI>123456789012</IdentificativoSdI>
  <NomeFile>IT01234567890_00001.xml</NomeFile>
  <DataOraRicezione>2026-06-29T10:00</DataOraRicezione>
  <ListaErrori>
    <Errore>
      <Codice>00200</Codice>
      <Descrizione>File non conforme</Descrizione>
    </Errore>
    <Errore>
      <Codice>00305</Codice>
      <Descrizione>IdFiscaleIVA non valido</Descrizione>
    </Errore>
  </ListaErrori>
  <MessageId>1000</MessageId>
</NotificaScarto>
"""

_EC_XML = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<NotificaEsitoCommittente>
  <IdentificativoSdI>123456789012</IdentificativoSdI>
  <RiferimentoFattura>
    <NumeroFattura>2026/001</NumeroFattura>
    <AnnoFattura>2026</AnnoFattura>
    <PosizioneFattura>1</PosizioneFattura>
  </RiferimentoFattura>
  <Esito>EC01</Esito>
  <MessageIdCommittente>ABC123</MessageIdCommittente>
</NotificaEsitoCommittente>
"""

_DT_XML = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<NotificaDecorrenzaTermini>
  <IdentificativoSdI>123456789012</IdentificativoSdI>
  <RiferimentoFattura>
    <NumeroFattura>2026/001</NumeroFattura>
    <AnnoFattura>2026</AnnoFattura>
  </RiferimentoFattura>
  <NomeFile>IT01234567890_00001.xml</NomeFile>
  <Descrizione>Termine scaduto</Descrizione>
  <MessageId>1001</MessageId>
</NotificaDecorrenzaTermini>
"""

_MT_XML = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<MetadatiInvioFile>
  <IdentificativoSdI>123456789012</IdentificativoSdI>
  <NomeFile>IT01234567890_00001.xml</NomeFile>
  <CodiceDestinatario>ABCDEFG</CodiceDestinatario>
  <Formato>FPR12</Formato>
  <TentativiInvio>1</TentativiInvio>
  <MessageId>1002</MessageId>
</MetadatiInvioFile>
"""

# IT-LC-3: prefixed-namespace fixtures. Real SDI notifications are sometimes
# wrapped in a namespace-prefixed root by the calling SOAP/transport layer;
# _text() must resolve fields by local name, not only for the unprefixed case.
_RC_XML_PREFIXED = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<ns:RicevutaConsegna xmlns:ns="http://www.fatturapa.gov.it/sdi/messaggi/v1.0">
  <ns:IdentificativoSdI>123456789012</ns:IdentificativoSdI>
  <ns:NomeFile>IT01234567890_00001.xml</ns:NomeFile>
  <ns:DataOraRicezione>2026-06-29T10:00</ns:DataOraRicezione>
  <ns:DataOraConsegna>2026-06-29T10:01</ns:DataOraConsegna>
  <ns:MessageId>999</ns:MessageId>
</ns:RicevutaConsegna>
"""

_NS_XML_PREFIXED = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<ns:NotificaScarto xmlns:ns="http://www.fatturapa.gov.it/sdi/messaggi/v1.0">
  <ns:IdentificativoSdI>123456789012</ns:IdentificativoSdI>
  <ns:NomeFile>IT01234567890_00001.xml</ns:NomeFile>
  <ns:DataOraRicezione>2026-06-29T10:00</ns:DataOraRicezione>
  <ns:ListaErrori>
    <ns:Errore>
      <ns:Codice>00200</ns:Codice>
      <ns:Descrizione>File non conforme</ns:Descrizione>
    </ns:Errore>
  </ns:ListaErrori>
  <ns:MessageId>1000</ns:MessageId>
</ns:NotificaScarto>
"""


class TestParseRicevutaConsegna:
    def test_type_is_rc(self):
        n = parse_notification(_RC_XML)
        assert n.tipo == SDINotificationType.RC

    def test_fields_parsed(self):
        n = parse_notification(_RC_XML)
        assert n.identificativo_sdi == "123456789012"
        assert n.nome_file == "IT01234567890_00001.xml"
        assert n.data_ora_consegna == "2026-06-29T10:01"
        assert n.message_id == "999"


class TestParseNotificaScarto:
    def test_type_is_ns(self):
        n = parse_notification(_NS_XML)
        assert n.tipo == SDINotificationType.NS

    def test_errors_parsed(self):
        n = parse_notification(_NS_XML)
        assert len(n.errori) == 2
        assert n.errori[0].codice == "00200"
        assert n.errori[1].codice == "00305"


class TestParseEsitoCommittente:
    def test_type_is_ec(self):
        n = parse_notification(_EC_XML)
        assert n.tipo == SDINotificationType.EC

    def test_esito_parsed(self):
        n = parse_notification(_EC_XML)
        assert n.esito == "EC01"

    def test_riferimento_fattura(self):
        n = parse_notification(_EC_XML)
        assert n.riferimento_fattura is not None
        assert n.riferimento_fattura.numero_fattura == "2026/001"
        assert n.riferimento_fattura.anno_fattura == "2026"
        assert n.riferimento_fattura.posizione_fattura == "1"


class TestParseDecorrenzaTermini:
    def test_type_is_dt(self):
        n = parse_notification(_DT_XML)
        assert n.tipo == SDINotificationType.DT

    def test_descrizione(self):
        n = parse_notification(_DT_XML)
        assert n.descrizione == "Termine scaduto"


class TestParseMetadatiInvioFile:
    def test_type_is_mt(self):
        n = parse_notification(_MT_XML)
        assert n.tipo == SDINotificationType.MT

    def test_metadata_fields(self):
        n = parse_notification(_MT_XML)
        assert n.codice_destinatario == "ABCDEFG"
        assert n.formato == "FPR12"
        assert n.tentativi_invio == "1"


class TestUnrecognisedRoot:
    def test_raises_value_error(self):
        with pytest.raises(ValueError, match="Unrecognised"):
            parse_notification(b"<UnknownRoot/>")


class TestParsePrefixedNamespace:
    """IT-LC-3: fields must resolve by local name under a prefixed namespace."""

    def test_ricevuta_consegna_identificativo_sdi(self):
        n = parse_notification(_RC_XML_PREFIXED)
        assert n.tipo == SDINotificationType.RC
        assert n.identificativo_sdi == "123456789012"
        assert n.nome_file == "IT01234567890_00001.xml"
        assert n.data_ora_consegna == "2026-06-29T10:01"

    def test_notifica_scarto_identificativo_sdi(self):
        n = parse_notification(_NS_XML_PREFIXED)
        assert n.tipo == SDINotificationType.NS
        assert n.identificativo_sdi == "123456789012"
        assert len(n.errori) == 1
        assert n.errori[0].codice == "00200"
