"""
Italian invoice model — FatturaPA v1.2.3 / SdI.

ItalianInvoice subclasses EN16931Invoice (the correct root for any format that is a
CIUS or extension of EN 16931-1:2017).  FatturaPA is the Italian CIUS of EN 16931,
identified by its BR-IT business rules (CIUS-IT). No profile URN is published by AdE;
the XSD namespace serves as the format identifier.

Italian-specific fields (DatiTrasmissione, regime fiscale, IPA office code) are added
as optional Field() declarations on this subclass.  Core fields are never duplicated.

NOTE: audit/audit_vs_core.py must be created and pass before publishing v0.3.0.
The _IS_EN16931_FAMILY constant in that script must be set to True.
"""

from __future__ import annotations

from mcp_einvoicing_core.en16931 import EN16931Invoice, EN16931LineItem, EN16931Tax
from pydantic import Field


class ItalianLineItem(EN16931LineItem):
    """Invoice line — EN 16931 BG-25, narrowed for FatturaPA.

    natura: FatturaPA Natura exemption code (N1–N7 and sub-codes) for this line.
    Escape hatch for tax_category values that resolve_natura() cannot map
    unambiguously (Z, AE, L, M) — set explicitly in that case.
    """

    natura: str | None = Field(
        default=None,
        description="FatturaPA Natura exemption code for this line, if any.",
    )


class ItalianTax(EN16931Tax):
    """VAT breakdown entry — EN 16931 BG-23, narrowed for FatturaPA.

    natura: FatturaPA Natura exemption code (N1–N7 and sub-codes) for this
    DatiRiepilogo group. Escape hatch, as with ItalianLineItem.natura.
    """

    natura: str | None = Field(
        default=None,
        description="FatturaPA Natura exemption code for this VAT group, if any.",
    )


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
        max_length=10,
        description=(
            "Unique sequential SDI send identifier (ProgressivoInvio), max 10 alphanumeric chars. "
            "Must be unique per transmitter Partita IVA. "
            "Use generate_progressivo_invio() to obtain one in the MCP workflow."
        ),
    )

    codice_destinatario: str = Field(
        description=(
            "SDI recipient code (CodiceDestinatario): 6-char IPA office code (FPA12/B2G), "
            "7-char B2B intermediary code (FPR12), or '0000000' for PEC routing."
        ),
    )

    pec_destinatario: str | None = Field(
        default=None,
        description="PEC address for routing when codice_destinatario is '0000000'.",
    )

    formato_trasmissione: str = Field(
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

    # ── DatiBeniServizi — Natura-aware line items and tax lines ──────────────

    line_items: list[ItalianLineItem] = Field(  # type: ignore[assignment]
        default_factory=list,
        description="Invoice lines (BG-25), narrowed with an optional Natura code.",
    )

    tax_lines: list[ItalianTax] = Field(  # type: ignore[assignment]
        ..., description="VAT breakdown (BG-23), narrowed with an optional Natura code.",
    )
