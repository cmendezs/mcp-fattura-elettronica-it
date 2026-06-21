"""
Italian invoice model — FatturaPA v1.2.3 / SdI.

ItalianInvoice subclasses EN16931Invoice (the correct root for any format that is a
CIUS or extension of EN 16931-1:2017).  FatturaPA is the Italian CIUS of EN 16931,
confirmed by its conformance statement and the profile URN
  urn:cen.eu:en16931:2017#conformant#urn:UBL.BE:1.0.0.20180214

Italian-specific fields (DatiTrasmissione, regime fiscale, IPA office code) are added
as optional Field() declarations on this subclass.  Core fields are never duplicated.

NOTE: audit/audit_vs_core.py must be created and pass before publishing v0.3.0.
The _IS_EN16931_FAMILY constant in that script must be set to True.
"""

from __future__ import annotations

from typing import Optional

from pydantic import Field

from mcp_einvoicing_core.en16931 import EN16931Invoice


class ItalianInvoice(EN16931Invoice):
    """FatturaPA v1.2.3 invoice — EN 16931 CIUS for Italy.

    Extends EN16931Invoice with Italian DatiTrasmissione fields and SdI routing data.
    Used by FatturaGenerator when an IT-typed document is required.

    FatturaPA document type codes (TipoDocumento) are carried in `invoice_type_code`
    using their native TD01–TD28 values rather than the UN/CEFACT UNCL1001 codes,
    consistent with how the Italian CIUS profiles map the BT-3 business term.
    """

    # ── DatiTrasmissione — SdI routing ───────────────────────────────────────

    progressivo_invio: str = Field(
        default="00001",
        max_length=10,
        description=(
            "Unique sequential SDI send identifier (ProgressivoInvio), max 10 alphanumeric chars. "
            "Must be unique per transmitter Partita IVA. "
            "Use generate_progressivo_invio() to obtain one in the MCP workflow."
        ),
    )

    codice_destinatario: str = Field(
        default="0000000",
        description=(
            "SDI recipient code (CodiceDestinatario): 6-char IPA office code (FPA12/B2G), "
            "7-char B2B intermediary code (FPR12), or '0000000' for PEC routing."
        ),
    )

    pec_destinatario: Optional[str] = Field(
        default=None,
        description="PEC address for routing when codice_destinatario is '0000000'.",
    )

    formato_trasmissione: str = Field(
        default="FPR12",
        description="Transmission format: 'FPR12' (B2B/B2C) or 'FPA12' (B2G/PA).",
    )

    # ── CedentePrestatore — seller regime ────────────────────────────────────

    regime_fiscale: str = Field(
        default="RF01",
        description=(
            "Seller fiscal regime code (RegimeFiscale) RF01–RF19. "
            "RF01 (ordinary) covers most companies. "
            "Use get_regime_fiscale_codes() for the complete list."
        ),
    )

    # ── CessionarioCommittente — B2G office routing ──────────────────────────

    codice_ufficio: Optional[str] = Field(
        default=None,
        max_length=20,
        description=(
            "IPA office code (CodiceUfficio) for B2G invoices (FPA12). "
            "Required for all invoices addressed to a Public Administration. "
            "Absence causes SdI routing rejection. "
            "Look up at https://www.indicepa.gov.it."
        ),
    )
