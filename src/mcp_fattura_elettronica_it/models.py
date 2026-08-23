"""
Italian invoice model — FatturaPA XSD v1.2.3 / SdI, per AdE Specifiche Tecniche 1.9.1.

NOTE on version numbers: "Specifiche Tecniche" (Allegato A, the AdE controls/codifiche
document) and the XSD schema are two SEPARATE artefacts with independent version
numbers. Specifiche Tecniche 1.9.1 (in force 2026-05-15) does NOT change the XSD —
the bundled schema remains v1.2.3. Do not conflate the two numbers.

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

from datetime import date
from decimal import Decimal

from mcp_einvoicing_core.en16931 import EN16931Invoice, EN16931LineItem, EN16931Tax
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# AltriDatiGestionali — free-form structured management data (DettaglioLinee)
# ---------------------------------------------------------------------------
#
# XSD: DettaglioLineeType/AltriDatiGestionali (AltriDatiGestionaliType),
# schemas/FatturaPA_FPR12_v1.2.3.xsd lines ~1017, 1026-1031. maxOccurs="unbounded"
# per line, so a line item may carry zero or more entries.
#
# This block is defined in the XSD but had no Python emission path before this
# change (IT-SC-... AltriDatiGestionali gap). Specifiche Tecniche 1.9.1 introduced
# a new codifica ("ESENZSPORT") for this block — see SPORT_WORKER_EXEMPTION_TIPO_DATO
# below — but the block itself is generic and pre-dates 1.9.1.


class AltriDatiGestionaliEntry(BaseModel):
    """A single AltriDatiGestionali entry — generic structured management data.

    Fields map 1:1 to the XSD AltriDatiGestionaliType sequence (TipoDato,
    RiferimentoTesto, RiferimentoNumero, RiferimentoData), in that order.
    Only TipoDato is mandatory; the other three are optional and their use
    depends on the specific codifica (see AdE Allegato A – Specifiche Tecniche).
    """

    tipo_dato: str = Field(
        ...,
        max_length=10,
        description="TipoDato (String10) — AdE codifica string, e.g. 'ESENZSPORT'.",
    )
    riferimento_testo: str | None = Field(
        default=None,
        max_length=60,
        description="RiferimentoTesto (String60) — alphanumeric reference value.",
    )
    riferimento_numero: Decimal | None = Field(
        default=None,
        description="RiferimentoNumero (Amount8Decimal) — numeric reference value.",
    )
    riferimento_data: date | None = Field(
        default=None,
        description="RiferimentoData (xs:date) — date reference value.",
    )


# Verified against AdE "Specifiche tecniche operative del SdI" v1.9.1 (Allegato A),
# changelog entry dated 31/03/2026, in force 2026-05-15: "Al fine di riportare in
# fattura il riferimento a compensi riferiti all'ambito del lavoro sportivo
# dilettantistico di cui all'articolo 36, comma 6 del decreto legislativo 36 del
# 2021, i quali godono di un'esenzione dall'imponibile fino a 15.000,00 euro annui,
# l'elemento TipoDato può essere valorizzato con la stringa "ESENZSPORT"." (p. 54).
# No RiferimentoTesto/RiferimentoNumero is mandated for this codifica (unlike e.g.
# "ALI-COMP", which requires RiferimentoNumero) — riferimento_numero below is an
# optional convenience for callers who want to record the cumulative annual amount.
SPORT_WORKER_EXEMPTION_TIPO_DATO = "ESENZSPORT"
SPORT_WORKER_EXEMPTION_ANNUAL_THRESHOLD_EUR = Decimal("15000.00")
SPORT_WORKER_EXEMPTION_LEGAL_REF = "Art. 36, comma 6, D.Lgs. 36/2021"


def build_sport_worker_exemption_altri_dati_gestionali(
    riferimento_numero: Decimal | None = None,
    riferimento_data: date | None = None,
) -> AltriDatiGestionaliEntry:
    """Build the AltriDatiGestionali entry for the sport-worker IRPEF exemption.

    Covers compensation under art. 36, comma 6, D.Lgs. 36/2021 (lavoro sportivo
    dilettantistico), exempt from the taxable base up to EUR 15,000/year.
    Sets TipoDato to the AdE-verified codifica string 'ESENZSPORT'
    (Specifiche Tecniche 1.9.1). riferimento_numero and riferimento_data are
    optional — the spec does not mandate them for this specific codifica.
    """
    return AltriDatiGestionaliEntry(
        tipo_dato=SPORT_WORKER_EXEMPTION_TIPO_DATO,
        riferimento_numero=riferimento_numero,
        riferimento_data=riferimento_data,
    )


class ItalianLineItem(EN16931LineItem):
    """Invoice line — EN 16931 BG-25, narrowed for FatturaPA.

    natura: FatturaPA Natura exemption code (N1–N7 and sub-codes) for this line.
    Escape hatch for tax_category values that resolve_natura() cannot map
    unambiguously (Z, AE, L, M) — set explicitly in that case.

    altri_dati_gestionali: zero or more AltriDatiGestionali entries (generic
    structured management data), e.g. the sport-worker IRPEF exemption codifica
    via build_sport_worker_exemption_altri_dati_gestionali().
    """

    natura: str | None = Field(
        default=None,
        description="FatturaPA Natura exemption code for this line, if any.",
    )

    altri_dati_gestionali: list[AltriDatiGestionaliEntry] | None = Field(
        default=None,
        description=(
            "AltriDatiGestionali entries for this line (DettaglioLinee, "
            "maxOccurs unbounded). Emitted after Natura in the XSD element order."
        ),
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
    """FatturaPA invoice (XSD v1.2.3, Specifiche Tecniche 1.9.1) — EN 16931 CIUS for Italy.

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

    # ── Gruppo IVA (VAT-group) support — CodiceFiscale alongside IdFiscaleIVA ──
    #
    # Added as flat fields on ItalianInvoice (matching the existing regime_fiscale
    # pattern) rather than on a party subclass: `seller`/`buyer` are still plain
    # EN16931Party instances, and narrowing their type to an IT-specific subclass
    # would be a breaking change for existing callers (EN16931Party instances are
    # not automatically valid instances of a stricter subclass under Pydantic v2
    # model validation). This keeps the change additive.

    cedente_codice_fiscale: str | None = Field(
        default=None,
        description=(
            "Codice Fiscale of the seller (CedentePrestatore/DatiAnagrafici/CodiceFiscale), "
            "optional. Set this when the seller's vat_id is a VAT-group (Gruppo IVA) "
            "IdFiscaleIVA: value must be the Codice Fiscale of the specific participating "
            "member company, never the group's own CF."
        ),
    )

    cessionario_codice_fiscale: str | None = Field(
        default=None,
        description=(
            "Codice Fiscale of the buyer (CessionarioCommittente/DatiAnagrafici/CodiceFiscale). "
            "Either this or the buyer's vat_id (IdFiscaleIVA) must identify the buyer. "
            "When the buyer's vat_id is a VAT-group (Gruppo IVA) IdFiscaleIVA, set this to "
            "the Codice Fiscale of the specific participating member, never the group's own "
            "CF — SdI rejects the group's own CF here with scarto code 00327 "
            "(see mcp_fattura_elettronica_it.sdi.notifications.SCARTO_CODE_REFERENCE). "
            "VAT-group membership itself cannot be validated offline."
        ),
    )

    # ── DatiBeniServizi — Natura-aware line items and tax lines ──────────────

    line_items: list[ItalianLineItem] = Field(  # type: ignore[assignment]
        default_factory=list,
        description="Invoice lines (BG-25), narrowed with an optional Natura code.",
    )

    tax_lines: list[ItalianTax] = Field(  # type: ignore[assignment]
        ...,
        description="VAT breakdown (BG-23), narrowed with an optional Natura code.",
    )
