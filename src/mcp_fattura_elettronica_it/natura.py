"""Natura exemption codes and the UNCL5305 -> Natura mapping.

NATURA_CODES is the FatturaPA reference table (N1-N7 and sub-codes), re-exported
from here and imported back into tools/body_tools.py so the tool surface is
unchanged and there is exactly one implementation (see audit CHECK 6).

UNCL5305_TO_NATURA maps the EN 16931 UNCL5305 VAT category code (BT-118 on
EN16931Tax.category / BT-151 on EN16931LineItem.tax_category) to the FatturaPA
Natura code, for the subset of mappings that are unambiguous without further
business context. See context-library/countries/it.md "Exemption and
special-scheme codes" for the source table.
"""

from __future__ import annotations

from mcp_einvoicing_core.exceptions import DocumentGenerationError

# ---------------------------------------------------------------------------
# Natura codes reference table (N1-N7)
# ---------------------------------------------------------------------------

NATURA_CODES: dict[str, dict] = {
    # Parent codes N2, N3, N6 removed — retired from FatturaPA NaturaType XSD enumeration
    # effective 1 January 2021 (AdE Circular 14/E 2019). Use sub-codes only.
    "N1": {"description": "Escluse ex art. 15", "legal_ref": "Art. 15 DPR 633/72"},
    "N2.1": {"description": "Non soggette ad IVA ai sensi degli artt. da 7 a 7-septies del DPR 633/72", "legal_ref": "Art. 7–7-septies DPR 633/72 (territoriality)"},
    "N2.2": {"description": "Non soggette — altri casi", "legal_ref": "Other out-of-scope cases"},
    "N3.1": {"description": "Non imponibili — esportazioni", "legal_ref": "Art. 8 DPR 633/72 (exports)"},
    "N3.2": {"description": "Non imponibili — cessioni intracomunitarie", "legal_ref": "Art. 41 DL 331/93 (intra-EU)"},
    "N3.3": {"description": "Non imponibili — cessioni verso San Marino", "legal_ref": "Art. 71 DPR 633/72"},
    "N3.4": {"description": "Non imponibili — operazioni assimilate alle cessioni all'esportazione", "legal_ref": "Art. 8-bis DPR 633/72"},
    "N3.5": {"description": "Non imponibili — a seguito di dichiarazioni d'intento", "legal_ref": "Habitual exporter declaration (lettera d'intento)"},
    "N3.6": {"description": "Non imponibili — altre operazioni che non concorrono alla formazione del plafond", "legal_ref": "Other zero-rated not forming VAT ceiling"},
    "N4": {"description": "Esenti", "legal_ref": "Art. 10 DPR 633/72 (VAT-exempt supplies)"},
    "N5": {"description": "Regime del margine / IVA non esposta in fattura", "legal_ref": "Art. 36 DL 41/95 (margin scheme)"},
    "N6.1": {"description": "Inversione contabile — cessione di rottami e altri materiali di recupero", "legal_ref": "Art. 74 c. 7-8 DPR 633/72"},
    "N6.2": {"description": "Inversione contabile — cessione di oro e argento puro", "legal_ref": "Art. 17 c. 5 DPR 633/72"},
    "N6.3": {"description": "Inversione contabile — subappalto nel settore edile", "legal_ref": "Art. 17 c. 6 lett. a DPR 633/72"},
    "N6.4": {"description": "Inversione contabile — cessione di fabbricati", "legal_ref": "Art. 17 c. 6 lett. a-bis DPR 633/72"},
    "N6.5": {"description": "Inversione contabile — cessione di telefoni cellulari", "legal_ref": "Art. 17 c. 6 lett. b DPR 633/72"},
    "N6.6": {"description": "Inversione contabile — cessione di prodotti elettronici", "legal_ref": "Art. 17 c. 6 lett. c DPR 633/72"},
    "N6.7": {"description": "Inversione contabile — prestazioni comparto edile e settori connessi", "legal_ref": "Art. 17 c. 6 lett. a-ter DPR 633/72"},
    "N6.8": {"description": "Inversione contabile — operazioni settore energetico", "legal_ref": "Art. 17 c. 6 lett. d-bis/d-ter/d-quater DPR 633/72"},
    "N6.9": {"description": "Inversione contabile — altri casi", "legal_ref": "Other reverse charge cases"},
    "N7": {"description": "IVA assolta in altro stato UE (one stop shop)", "legal_ref": "OSS / IOSS — VAT paid in another EU member state"},
}

# ---------------------------------------------------------------------------
# UNCL5305 -> Natura mapping (unambiguous subset only)
# ---------------------------------------------------------------------------
#
# Only codes whose UNCL5305 meaning maps to exactly one Natura code without
# additional business context are included here. Source: context-library/
# countries/it.md "Exemption and special-scheme codes (FatturaPA Natura)".
#
# S  (Standard rate)          -> no Natura (line is taxed; Natura is omitted)
# E  (Exempt from tax)        -> N4  — Art. 10 DPR 633/1972
# K  (VAT exempt intra-EU)    -> N3.2 — Art. 41 D.L. 331/1993 (intra-EU supplies)
# G  (Free export item, VAT not charged) -> N3.1 — Art. 8 c.1 DPR 633/1972 (exports)
# O  (Services outside scope of tax)     -> N2.2 — out-of-scope, other cases
#
# Z, AE, L, M are deliberately unmapped: their correct Natura sub-code
# (N3.x for zero-rated variants, N6.x for reverse charge) depends on business
# context that the bare UNCL5305 category does not carry. Callers must pass
# an explicit Natura for these categories.
UNCL5305_TO_NATURA: dict[str, str | None] = {
    "S": None,
    "E": "N4",
    "K": "N3.2",
    "G": "N3.1",
    "O": "N2.2",
}


def resolve_natura(category: str, explicit: str | None = None) -> str | None:
    """Resolve the Natura code for a UNCL5305 tax category.

    Returns `explicit` when supplied (the caller's escape hatch). Otherwise
    looks up `category` in UNCL5305_TO_NATURA. Raises DocumentGenerationError
    when the category is not in the mapping and no explicit value was given —
    this covers Z, AE, L, M and any other UNCL5305 code not listed above.
    """
    if explicit is not None:
        return explicit
    if category in UNCL5305_TO_NATURA:
        return UNCL5305_TO_NATURA[category]
    raise DocumentGenerationError(
        f"UNCL5305 category '{category}' has no unambiguous Natura mapping. "
        "Set an explicit Natura code (see get_natura_codes() / NATURA_CODES)."
    )
