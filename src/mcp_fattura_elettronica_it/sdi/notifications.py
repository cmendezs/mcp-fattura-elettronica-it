"""SDI notification parsing (Allegato B-1, Specifiche tecniche SDI v1.8.4).

Notification types per section 1.1:
  RC — Ricevuta di consegna
  NS — Notifica di scarto
  MC — Notifica di mancata consegna
  NE — Notifica di esito (cedente)
  EC — Notifica di esito committente
  SE — Scarto esito committente
  DT — Notifica decorrenza termini
  MT — Metadati invio file
  AT — Attestazione impossibilita di recapito
"""

from __future__ import annotations

from enum import Enum

from mcp_einvoicing_core.logging_utils import get_logger
from mcp_einvoicing_core.xml_utils import safe_fromstring
from pydantic import BaseModel, Field

logger = get_logger(__name__)


class SDINotificationType(str, Enum):
    """SDI notification/receipt type codes."""

    RC = "RC"
    NS = "NS"
    MC = "MC"
    NE = "NE"
    EC = "EC"
    SE = "SE"
    DT = "DT"
    MT = "MT"
    AT = "AT"


_ROOT_TAG_TO_TYPE: dict[str, SDINotificationType] = {
    "RicevutaConsegna": SDINotificationType.RC,
    "NotificaScarto": SDINotificationType.NS,
    "NotificaMancataConsegna": SDINotificationType.MC,
    "NotificaEsito": SDINotificationType.NE,
    "NotificaEsitoCommittente": SDINotificationType.EC,
    "ScartoEsitoCommittente": SDINotificationType.SE,
    "NotificaDecorrenzaTermini": SDINotificationType.DT,
    "MetadatiInvioFile": SDINotificationType.MT,
    "AttestazioneTrasmissioneFattura": SDINotificationType.AT,
}


# ---------------------------------------------------------------------------
# Scarto (rejection) control-code reference
# ---------------------------------------------------------------------------
#
# NotificaScarto XML already carries a <Descrizione> per error from SdI itself;
# this table is a SUPPLEMENT (not a replacement) for codes where added context
# is useful. Currently covers only the control code introduced by AdE
# Specifiche Tecniche 1.9.1 (in force 2026-05-15). Extend as further codes are
# verified against the AdE Allegato A — Specifiche Tecniche document.
#
# Source: AdE "Specifiche tecniche operative del SdI" v1.9.1, changelog entry
# dated 31/03/2026 ("Introdotto nuovo controllo sulla fattura con codice
# 00327") and control-code table: "Codice: 00327 — Descrizione in caso di
# fatture ordinarie: 1.4.1.2 <CodiceFiscale> di gruppo IVA non riferito ad un
# partecipante, in assenza di <IdFiscaleIVA> di gruppo IVA [...] Lo scarto
# avviene se, in assenza di PIVA del cessionario/committente, il CF è
# valorizzato con quello di un gruppo IVA e non di una sua partecipata. Il CF
# deve essere valorizzato con il CF della società partecipante al gruppo Iva."
SCARTO_CODE_REFERENCE: dict[str, str] = {
    "00327": (
        "Buyer (CessionarioCommittente) IdFiscaleIVA is absent and the CodiceFiscale "
        "supplied belongs to a VAT group (Gruppo IVA) itself rather than to one of its "
        "participating members. Set CodiceFiscale to the Codice Fiscale of the specific "
        "member company that is party to this transaction, not the group's own CF. "
        "(AdE Specifiche Tecniche 1.9.1, in force 2026-05-15.)"
    ),
}


def describe_scarto_code(codice: str) -> str | None:
    """Return a supplementary human-readable description for a known scarto (rejection) code.

    Looks up `codice` in SCARTO_CODE_REFERENCE. Returns None for codes not yet
    catalogued here — most scarto codes rely solely on the <Descrizione> text
    the SdI notification itself carries; this table only adds context for
    codes where that text benefits from further explanation.
    """
    return SCARTO_CODE_REFERENCE.get(codice)


class SDIErrore(BaseModel):
    """A single error entry from a NotificaScarto ListaErrori."""

    codice: str = Field(description="SDI error code (e.g. '00200').")
    descrizione: str = Field(description="Human-readable error description.")
    reference_note: str | None = Field(
        default=None,
        description=(
            "Supplementary description from SCARTO_CODE_REFERENCE, when `codice` is "
            "catalogued there. None for codes not yet catalogued."
        ),
    )


class RiferimentoFattura(BaseModel):
    """Invoice reference within a notification."""

    numero_fattura: str | None = None
    anno_fattura: str | None = None
    posizione_fattura: str | None = None


class SDINotification(BaseModel):
    """Parsed SDI notification with common and type-specific fields."""

    tipo: SDINotificationType = Field(description="Notification type code.")
    identificativo_sdi: str = Field(description="12-digit SDI file identifier.")
    nome_file: str | None = None
    data_ora_ricezione: str | None = None
    data_ora_consegna: str | None = None
    message_id: str | None = None
    descrizione: str | None = None
    note: str | None = None

    errori: list[SDIErrore] = Field(default_factory=list, description="Errors (NS only).")
    esito: str | None = Field(default=None, description="EC01 (accept) or EC02 (reject), for EC/NE.")
    scarto: str | None = Field(default=None, description="EN00/EN01 for SE.")
    riferimento_fattura: RiferimentoFattura | None = None

    codice_destinatario: str | None = None
    formato: str | None = None
    tentativi_invio: str | None = None
    hash_file_originale: str | None = None


def parse_notification(xml_bytes: bytes) -> SDINotification:
    """Parse an SDI notification XML into a structured model.

    The notification type is detected from the root element name.

    Args:
        xml_bytes: Raw XML bytes of the notification.

    Returns:
        Parsed SDINotification.

    Raises:
        ValueError: If the root element is not a recognised notification type.
    """
    root = safe_fromstring(xml_bytes)
    local_name = root.tag.split("}")[-1] if "}" in root.tag else root.tag

    tipo = _ROOT_TAG_TO_TYPE.get(local_name)
    if tipo is None:
        raise ValueError(
            f"Unrecognised SDI notification root element: {local_name!r}. "
            f"Expected one of: {', '.join(_ROOT_TAG_TO_TYPE.keys())}"
        )

    def _text(tag: str) -> str | None:
        for el in root.iter():
            el_local = el.tag.split("}")[-1] if "}" in el.tag else el.tag
            if el_local == tag and el.text:
                return el.text.strip()
        return None

    errori: list[SDIErrore] = []
    for errore_el in root.iter():
        el_local = errore_el.tag.split("}")[-1] if "}" in errore_el.tag else errore_el.tag
        if el_local == "Errore":
            codice_el = errore_el.find("Codice")
            desc_el = errore_el.find("Descrizione")
            if codice_el is None:
                for child in errore_el:
                    child_local = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                    if child_local == "Codice":
                        codice_el = child
                    elif child_local == "Descrizione":
                        desc_el = child
            if codice_el is not None:
                codice_val = codice_el.text or ""
                errori.append(SDIErrore(
                    codice=codice_val,
                    descrizione=(desc_el.text or "") if desc_el is not None else "",
                    reference_note=describe_scarto_code(codice_val),
                ))

    rif_fattura: RiferimentoFattura | None = None
    rif_el = None
    for el in root.iter():
        el_local = el.tag.split("}")[-1] if "}" in el.tag else el.tag
        if el_local == "RiferimentoFattura":
            rif_el = el
            break
    if rif_el is not None:
        def _rif_text(tag: str) -> str | None:
            for child in rif_el:
                child_local = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if child_local == tag and child.text:
                    return child.text.strip()
            return None

        rif_fattura = RiferimentoFattura(
            numero_fattura=_rif_text("NumeroFattura"),
            anno_fattura=_rif_text("AnnoFattura"),
            posizione_fattura=_rif_text("PosizioneFattura"),
        )

    return SDINotification(
        tipo=tipo,
        identificativo_sdi=_text("IdentificativoSdI") or "",
        nome_file=_text("NomeFile"),
        data_ora_ricezione=_text("DataOraRicezione"),
        data_ora_consegna=_text("DataOraConsegna"),
        message_id=_text("MessageId"),
        descrizione=_text("Descrizione"),
        note=_text("Note"),
        errori=errori,
        esito=_text("Esito"),
        scarto=_text("Scarto"),
        riferimento_fattura=rif_fattura,
        codice_destinatario=_text("CodiceDestinatario"),
        formato=_text("Formato"),
        tentativi_invio=_text("TentativiInvio"),
        hash_file_originale=_text("HashFileOriginale"),
    )
