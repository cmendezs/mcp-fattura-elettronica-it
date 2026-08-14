"""
MCP tools for the FatturaElettronicaHeader section of FatturaPA (XSD v1.2.3,
Specifiche Tecniche 1.9.1 — the two version numbers are independent; 1.9.1 does
not change the XSD).

Covers transmission data, seller/buyer validation, fiscal regime codes,
Partita IVA validation, ProgressivoInvio generation, and SDI recipient lookup.
"""

from __future__ import annotations

import random
import re
from typing import Annotated

from fastmcp import FastMCP
from mcp_einvoicing_core.logging_utils import get_logger
from mcp_einvoicing_core.models import TaxIdentifier
from pydantic import Field

from mcp_fattura_elettronica_it.sdi.notifications import SCARTO_CODE_REFERENCE

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# RegimeFiscale reference table (RF01–RF19)
# ---------------------------------------------------------------------------

REGIME_FISCALE: dict[str, str] = {
    "RF01": "Regime ordinario",
    "RF02": "Regime contribuenti minimi (art. 1, c.96-117, L. 244/2007)",
    "RF04": "Agricoltura e attività connesse e pesca (artt. 34 e 34-bis, DPR 633/72)",
    "RF05": "Vendita sali e tabacchi (art. 74, c.1, DPR. 633/72)",
    "RF06": "Commercio fiammiferi (art. 74, c.1, DPR. 633/72)",
    "RF07": "Editoria (art. 74, c.1, DPR. 633/72)",
    "RF08": "Gestione servizi telefonia pubblica (art. 74, c.1, DPR. 633/72)",
    "RF09": "Rivendita documenti di trasporto pubblico e di sosta (art. 74, c.1, DPR. 633/72)",
    "RF10": "Intrattenimenti, giochi e altre attività (art. 74, c.6, DPR. 633/72)",
    "RF11": "Agenzie viaggi e turismo (art. 74-ter, DPR. 633/72)",
    "RF12": "Agriturismo (art. 5, c.2, L. 413/91)",
    "RF13": "Vendite a domicilio (art. 25-bis, c.6, DPR. 600/73)",
    "RF14": "Rivendita beni usati, oggetti d'arte, d'antiquariato o da collezione (art. 36, DL 41/95)",
    "RF15": "Agenzie di vendite all'asta di oggetti d'arte, antiquariato o da collezione (art. 40-bis, DL 41/95)",
    "RF16": "IVA per cassa P.A. (art. 6, c.5, DPR. 633/72)",
    "RF17": "IVA per cassa (art. 32-bis, DL 83/2012)",
    "RF18": "Altro",
    "RF19": "Regime forfettario (art. 1, c.54-89, L. 190/2014)",
}

# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------


def register_header_tools(mcp: FastMCP) -> None:
    """Register the 7 FatturaElettronicaHeader tools on the FastMCP instance."""

    @mcp.tool()
    def build_transmission_header(
        id_paese: Annotated[
            str,
            Field(
                description=(
                    "Two-letter ISO 3166-1 country code of the transmitter (e.g. 'IT'). "
                    "Usually 'IT' for Italian entities."
                )
            ),
        ],
        id_codice: Annotated[
            str,
            Field(
                description=(
                    "Tax identifier of the transmitter: Partita IVA (11 digits) for Italian "
                    "entities, or foreign tax ID (max 28 chars) for cross-border."
                )
            ),
        ],
        progressivo_invio: Annotated[
            str,
            Field(
                description=(
                    "Unique sequential send identifier, max 10 alphanumeric characters. "
                    "Use generate_progressivo_invio() to obtain one automatically."
                )
            ),
        ],
        formato_trasmissione: Annotated[
            str,
            Field(
                description=(
                    "Transmission format: 'FPA12' for invoices to Public Administration (PA), "
                    "'FPR12' for invoices to private parties (B2B / B2C)."
                )
            ),
        ],
        codice_destinatario: Annotated[
            str,
            Field(
                description=(
                    "SDI recipient code: 6-char for PA offices (IPA code, FPA12), "
                    "7-char for B2B intermediaries (FPR12), or '0000000' (7 zeros) for PEC routing. "
                    "Use lookup_codice_destinatario() to validate the code first."
                )
            ),
        ],
        pec_destinatario: Annotated[
            str | None,
            Field(
                default=None,
                description=(
                    "PEC (certified email) address of the recipient. "
                    "Required only when codice_destinatario is '0000000'."
                ),
            ),
        ] = None,
    ) -> dict:
        """Build the DatiTrasmissione block required in every FatturaPA header.

        Use this as step 3 in the invoice generation workflow, after
        generate_progressivo_invio() and before validate_cedente_prestatore().
        Use lookup_codice_destinatario() first to confirm the recipient code format.

        Validates: formato_trasmissione must be 'FPA12' or 'FPR12'; progressivo_invio
        must be 1–10 alphanumeric characters; pec_destinatario is required when
        codice_destinatario is '0000000'.

        On success returns {'DatiTrasmissione': {...}} ready to pass to generate_fattura_xml().
        On failure returns {'error': '<reason>'} — do not proceed to XML generation.
        """
        if formato_trasmissione not in ("FPA12", "FPR12"):
            return {"error": f"Invalid formato_trasmissione '{formato_trasmissione}'. Must be 'FPA12' or 'FPR12'."}

        if len(progressivo_invio) > 10 or not re.match(r"^[A-Za-z0-9]+$", progressivo_invio):
            return {"error": "progressivo_invio must be 1–10 alphanumeric characters."}

        if codice_destinatario == "0000000" and not pec_destinatario:
            return {"error": "pec_destinatario is required when codice_destinatario is '0000000'."}

        result: dict = {
            "DatiTrasmissione": {
                "IdTrasmittente": {
                    "IdPaese": id_paese.upper(),
                    "IdCodice": id_codice,
                },
                "ProgressivoInvio": progressivo_invio,
                "FormatoTrasmissione": formato_trasmissione,
                "CodiceDestinatario": codice_destinatario,
            }
        }
        if pec_destinatario:
            result["DatiTrasmissione"]["PECDestinatario"] = pec_destinatario

        return result

    @mcp.tool()
    def validate_cedente_prestatore(
        id_paese: Annotated[
            str,
            Field(description="ISO 3166-1 two-letter country code of the seller (e.g. 'IT')."),
        ],
        id_codice: Annotated[
            str,
            Field(description="Partita IVA (11 digits) or foreign VAT number of the seller."),
        ],
        codice_fiscale: Annotated[
            str | None,
            Field(
                default=None,
                description=(
                    "Codice Fiscale of the seller, optional. Set this when id_codice is a "
                    "VAT-group (Gruppo IVA) IdFiscaleIVA: value must be the Codice Fiscale of "
                    "the specific participating member company, never the group's own CF. "
                    "Emitted as DatiAnagrafici/CodiceFiscale, between IdFiscaleIVA and "
                    "Anagrafica per the XSD element order."
                ),
            ),
        ] = None,
        denominazione: Annotated[
            str | None,
            Field(
                default=None,
                description="Company name (Denominazione). Mutually exclusive with nome+cognome.",
            ),
        ] = None,
        nome: Annotated[
            str | None,
            Field(default=None, description="First name (Nome), for individual sellers."),
        ] = None,
        cognome: Annotated[
            str | None,
            Field(default=None, description="Last name (Cognome), for individual sellers."),
        ] = None,
        regime_fiscale: Annotated[
            str,
            Field(
                description=(
                    "Fiscal regime code RF01–RF19. Use get_regime_fiscale_codes() for the "
                    "complete list. Most companies use RF01 (ordinary regime)."
                )
            ),
        ] = "RF01",
        indirizzo: Annotated[
            str,
            Field(description="Street address (via, piazza…) of the registered office."),
        ] = "",
        cap: Annotated[
            str,
            Field(description="Italian postal code (5 digits) or foreign equivalent."),
        ] = "",
        comune: Annotated[
            str,
            Field(description="City/municipality of the registered office."),
        ] = "",
        nazione: Annotated[
            str,
            Field(description="ISO 3166-1 two-letter country code of the registered office."),
        ] = "IT",
    ) -> dict:
        """Validate and build the CedentePrestatore (seller) block for FatturaPA.

        Use this as step 4 in the invoice generation workflow, after
        build_transmission_header() and before validate_cessionario().
        Call get_regime_fiscale_codes() first if you need to look up the RF code.

        Gruppo IVA (VAT-group) sellers: when id_codice is a VAT-group IdFiscaleIVA,
        pass codice_fiscale set to the Codice Fiscale of the specific participating
        member company issuing this invoice, never the group's own CF. This mirrors
        the buyer-side rule enforced by SdI scarto code 00327 (see
        mcp_fattura_elettronica_it.sdi.notifications.SCARTO_CODE_REFERENCE); SdI does
        not publish an equivalent seller-side control code, but the same distinction
        applies structurally.

        Validates: either denominazione or both nome+cognome must be provided (mutually
        exclusive); regime_fiscale must be a valid RF01–RF19 code; Italian Partita IVA
        (id_paese='IT') must be exactly 11 digits; codice_fiscale, if provided, must be
        16 alphanumeric characters (individuals) or 11 digits (companies/VAT groups).

        On success returns {'CedentePrestatore': {...}} ready to pass to generate_fattura_xml().
        On failure returns {'error': '<reason>'} listing all validation issues joined by '; '.
        """
        errors: list[str] = []

        if not denominazione and not (nome and cognome):
            errors.append("Either 'denominazione' or both 'nome' and 'cognome' are required.")

        if denominazione and (nome or cognome):
            errors.append("'denominazione' is mutually exclusive with 'nome'/'cognome'.")

        if regime_fiscale not in REGIME_FISCALE:
            errors.append(
                f"Invalid regime_fiscale '{regime_fiscale}'. "
                f"Valid codes: {', '.join(REGIME_FISCALE.keys())}."
            )

        if id_paese == "IT" and not re.match(r"^\d{11}$", id_codice):
            errors.append("Italian Partita IVA must be exactly 11 digits.")

        if codice_fiscale:
            cf = codice_fiscale.strip()
            if len(cf) == 16:
                valid_cf, cf_err = TaxIdentifier.validate_it_codice_fiscale(cf)
                if not valid_cf:
                    errors.append(f"Invalid Codice Fiscale: {cf_err}")
            elif len(cf) == 11 and cf.isdigit():
                valid_piva, piva_err = TaxIdentifier.validate_it_partita_iva(cf)
                if not valid_piva:
                    errors.append(f"Invalid Codice Fiscale (numeric/company format): {piva_err}")
            else:
                errors.append(
                    "Codice Fiscale must be 16 alphanumeric characters (individuals) "
                    "or 11 digits (companies/VAT groups)."
                )

        if errors:
            return {"error": "; ".join(errors)}

        anagrafica: dict = {}
        if denominazione:
            anagrafica["Denominazione"] = denominazione
        else:
            anagrafica["Nome"] = nome
            anagrafica["Cognome"] = cognome

        dati_anagrafici: dict = {"IdFiscaleIVA": {"IdPaese": id_paese.upper(), "IdCodice": id_codice}}
        if codice_fiscale:
            dati_anagrafici["CodiceFiscale"] = codice_fiscale.strip()
        dati_anagrafici["Anagrafica"] = anagrafica
        dati_anagrafici["RegimeFiscale"] = regime_fiscale

        return {
            "CedentePrestatore": {
                "DatiAnagrafici": dati_anagrafici,
                "Sede": {
                    "Indirizzo": indirizzo,
                    "CAP": cap,
                    "Comune": comune,
                    "Nazione": nazione.upper(),
                },
            }
        }

    @mcp.tool()
    def validate_cessionario(
        denominazione: Annotated[
            str | None,
            Field(
                default=None,
                description=(
                    "Company name of the buyer. "
                    "Mutually exclusive with nome+cognome."
                ),
            ),
        ] = None,
        nome: Annotated[
            str | None,
            Field(default=None, description="First name of the buyer (natural person)."),
        ] = None,
        cognome: Annotated[
            str | None,
            Field(default=None, description="Last name of the buyer (natural person)."),
        ] = None,
        id_paese: Annotated[
            str | None,
            Field(
                default=None,
                description=(
                    "ISO country code for IdFiscaleIVA. Required for VAT-registered buyers. "
                    "Omit for Italian buyers identified only by CodiceFiscale."
                ),
            ),
        ] = None,
        id_codice: Annotated[
            str | None,
            Field(
                default=None,
                description="VAT number of the buyer. Required if id_paese is provided.",
            ),
        ] = None,
        codice_fiscale: Annotated[
            str | None,
            Field(
                default=None,
                description=(
                    "Italian fiscal code (16-char alphanumeric for individuals, "
                    "11-digit numeric for companies). Alternative to IdFiscaleIVA."
                ),
            ),
        ] = None,
        indirizzo: Annotated[str, Field(description="Street address of the buyer.")] = "",
        cap: Annotated[str, Field(description="Postal code of the buyer.")] = "",
        comune: Annotated[str, Field(description="City of the buyer.")] = "",
        nazione: Annotated[str, Field(description="ISO country code of the buyer.")] = "IT",
    ) -> dict:
        """Validate and build the CessionarioCommittente (buyer) block for FatturaPA.

        Use this as step 5 in the invoice generation workflow, after
        validate_cedente_prestatore() and before build_dati_generali().

        Validates: either denominazione or both nome+cognome must be provided (mutually
        exclusive); at least one tax identifier (id_codice with id_paese, or codice_fiscale)
        is required; id_codice requires id_paese to be set.

        Italian B2C buyers with only a CodiceFiscale: set codice_fiscale and leave
        id_paese/id_codice empty. Foreign B2B buyers: set id_paese + id_codice.
        For B2G invoices (FPA12): routing to the Public Administration is via a 6-char
        IPA office CodiceDestinatario in build_transmission_header(), not via this tool —
        look up the code at https://www.indicepa.gov.it.

        Gruppo IVA (VAT-group) buyers: when id_paese/id_codice are omitted and
        codice_fiscale is an 11-digit (company-format) code, this may be a VAT-group's
        own CF rather than a participating member's. SdI rejects that combination with
        scarto code 00327 (see mcp_fattura_elettronica_it.sdi.notifications.
        SCARTO_CODE_REFERENCE) — this tool cannot validate VAT-group membership offline,
        so it only warns on the detectable structural precondition (IdFiscaleIVA absent
        + 11-digit codice_fiscale); the returned 'warnings' list flags this case. Confirm
        codice_fiscale identifies the specific member company, not the group itself.

        On success returns {'CessionarioCommittente': {...}} ready for generate_fattura_xml(),
        plus 'warnings' (list[str]) when the 00327 structural precondition is detected.
        On failure returns {'error': '<reason>'} listing all issues joined by '; '.
        """
        errors: list[str] = []

        if not denominazione and not (nome and cognome):
            errors.append("Either 'denominazione' or both 'nome' and 'cognome' are required.")

        if denominazione and (nome or cognome):
            errors.append("'denominazione' is mutually exclusive with 'nome'/'cognome'.")

        if not id_codice and not codice_fiscale:
            errors.append("At least one of 'id_codice' (with 'id_paese') or 'codice_fiscale' is required.")

        if id_paese and not id_codice:
            errors.append("'id_codice' is required when 'id_paese' is provided.")

        if codice_fiscale:
            cf = codice_fiscale.strip()
            if len(cf) == 16:
                valid_cf, cf_err = TaxIdentifier.validate_it_codice_fiscale(cf)
                if not valid_cf:
                    errors.append(f"Invalid Codice Fiscale: {cf_err}")
            elif len(cf) == 11 and cf.isdigit():
                valid_piva, piva_err = TaxIdentifier.validate_it_partita_iva(cf)
                if not valid_piva:
                    errors.append(f"Invalid Codice Fiscale (numeric/company format): {piva_err}")
            else:
                errors.append(
                    "Codice Fiscale must be 16 alphanumeric characters (individuals) "
                    "or 11 digits (companies)."
                )

        if errors:
            return {"error": "; ".join(errors)}

        anagrafica: dict = {}
        if denominazione:
            anagrafica["Denominazione"] = denominazione
        else:
            anagrafica["Nome"] = nome
            anagrafica["Cognome"] = cognome

        dati_anagrafici: dict = {"Anagrafica": anagrafica}
        if id_paese and id_codice:
            dati_anagrafici["IdFiscaleIVA"] = {"IdPaese": id_paese.upper(), "IdCodice": id_codice}
        if codice_fiscale:
            dati_anagrafici["CodiceFiscale"] = codice_fiscale

        result: dict = {
            "CessionarioCommittente": {
                "DatiAnagrafici": dati_anagrafici,
                "Sede": {
                    "Indirizzo": indirizzo,
                    "CAP": cap,
                    "Comune": comune,
                    "Nazione": nazione.upper(),
                },
            }
        }

        # Proactive warning for the detectable structural precondition of scarto
        # code 00327: IdFiscaleIVA absent + an 11-digit (company/VAT-group-format)
        # CodiceFiscale. VAT-group *membership* cannot be checked offline — only
        # this structural signal — so this is a warning, not a blocking error.
        if not (id_paese and id_codice) and codice_fiscale:
            cf_stripped = codice_fiscale.strip()
            if len(cf_stripped) == 11 and cf_stripped.isdigit():
                result["warnings"] = [
                    (
                        f"IdFiscaleIVA is absent and codice_fiscale ('{cf_stripped}') is an "
                        "11-digit company-format code. If this CodiceFiscale identifies a VAT "
                        "group (Gruppo IVA) itself rather than a specific participating member, "
                        "SdI will reject the invoice with scarto code 00327: "
                        f"{SCARTO_CODE_REFERENCE['00327']} This cannot be validated offline; "
                        "confirm the CF identifies the correct member company."
                    )
                ]

        return result

    @mcp.tool()
    def get_regime_fiscale_codes() -> dict:
        """Return the complete list of RegimeFiscale codes (RF01–RF19) with descriptions.

        Call this to look up the correct fiscal regime code before calling
        validate_cedente_prestatore(). Every Italian seller must declare a regime:
        RF01 (ordinary) covers most companies; RF19 (forfettario) covers flat-rate
        sole traders; all other codes cover specialised VAT regimes.

        Always succeeds. Returns {'codes': [{'code': str, 'description': str}, ...], 'total': int}.
        """
        codes = [{"code": code, "description": desc} for code, desc in REGIME_FISCALE.items()]
        return {"codes": codes, "total": len(codes)}

    @mcp.tool()
    def validate_partita_iva(
        partita_iva: Annotated[
            str,
            Field(
                description=(
                    "Italian Partita IVA (VAT number) to validate. "
                    "Must be exactly 11 digits. Whitespace is stripped before validation."
                )
            ),
        ],
    ) -> dict:
        """Validate an Italian Partita IVA for format (11 digits) and modulo-10 checksum.

        Call this as an early sanity check on the seller's VAT number before passing it to
        validate_cedente_prestatore(). Strips whitespace before validation.

        Applies the official Agenzia delle Entrate control algorithm: odd-position digits are
        taken as-is; even-position digits are doubled (subtract 9 if > 9); the last digit must
        equal (10 - sum % 10) % 10.

        On success returns {'valid': true, 'value': '<cleaned_piva>'}.
        On failure returns {'valid': false, 'value': '<input>', 'error': '<reason>'}.
        """
        piva = partita_iva.strip()
        valid, error = TaxIdentifier.validate_it_partita_iva(piva)
        if not valid:
            return {"valid": False, "value": piva, "error": error}
        return {"valid": True, "value": piva}

    @mcp.tool()
    def generate_progressivo_invio(
        prefix: Annotated[
            str | None,
            Field(
                default=None,
                description=(
                    "Optional alphabetic prefix (max 3 chars) to prepend to the sequence number. "
                    "E.g. 'INV' → 'INV00001'. Total length must not exceed 10 chars."
                ),
            ),
        ] = None,
        sequence: Annotated[
            int | None,
            Field(
                default=None,
                ge=1,
                le=9999999,
                description=(
                    "Explicit sequence number (1–9999999). If omitted, a random 5-digit "
                    "number is generated. Callers should track their own sequence in production."
                ),
            ),
        ] = None,
    ) -> dict:
        """Generate a ProgressivoInvio identifier for the DatiTrasmissione block.

        Use this as step 2 in the invoice generation workflow, before
        build_transmission_header(). The SDI requires each ProgressivoInvio to be unique
        per transmitter Partita IVA — in production, pass an explicit monotonically
        increasing sequence number; use the random default only for testing.

        prefix (optional): alphabetic 1–3 char prefix, e.g. 'INV' → 'INV00001'.
        sequence (optional): integer 1–9999999; random 5-digit value if omitted.
        Total length must not exceed 10 characters.

        On success returns {'progressivo_invio': str, 'length': int}.
        On failure (invalid prefix) returns {'error': '<reason>'}.
        """
        if prefix and not re.match(r"^[A-Za-z]{1,3}$", prefix):
            return {"error": "prefix must be 1–3 alphabetic characters."}

        seq_num = sequence if sequence is not None else random.randint(1, 99999)
        prefix_str = prefix.upper() if prefix else ""

        # Pad sequence to fill remaining width up to 10 chars
        remaining = 10 - len(prefix_str)
        seq_str = str(seq_num).zfill(min(remaining, 5))

        progressivo = (prefix_str + seq_str)[:10]

        return {"progressivo_invio": progressivo, "length": len(progressivo)}

    @mcp.tool()
    def lookup_codice_destinatario(
        codice: Annotated[
            str | None,
            Field(
                default=None,
                description=(
                    "SDI CodiceDestinatario to look up: 6-char alphanumeric for PA offices "
                    "(IPA code, FPA12 B2G invoices), 7-char alphanumeric for B2B intermediaries "
                    "(FPR12), or '0000000' (7 zeros) for PEC routing. "
                    "IPA codes can be verified at https://www.indicepa.gov.it."
                ),
            ),
        ] = None,
        pec: Annotated[
            str | None,
            Field(
                default=None,
                description=(
                    "PEC address to validate format (user@domain.ext). "
                    "When a PEC is provided, CodiceDestinatario must be '0000000'."
                ),
            ),
        ] = None,
    ) -> dict:
        """Validate the format of a CodiceDestinatario (SDI recipient code) or PEC address.

        Call this before build_transmission_header() to confirm the recipient routing type
        and that the code or PEC address is correctly formatted. At least one of codice
        or pec must be provided.

        Routing rules:
        - codice is 6 alphanumeric chars (e.g. 'A1B2C3') → routing_type: 'SDI_CODE' (PA/IPA, FPA12)
        - codice is 7 alphanumeric chars (e.g. 'X1Y2Z3W') → routing_type: 'SDI_CODE' (B2B intermediary, FPR12)
        - codice is '0000000' (7 zeros) → routing_type: 'PEC'; pec_destinatario is then
          mandatory in build_transmission_header()
        - pec only (no codice) → validates email format, routing_type: 'PEC'

        IPA note: 6-char = IPA code (PA), 7-char = B2B intermediary code (FPR12 routing).
        PA office codes can be looked up at https://www.indicepa.gov.it.
        This tool performs format validation only, no live query against the SDI SOAP
        directory service or the IPA registry (planned for a future release).

        Per-channel cap (reference only, not enforced here — this tool validates the
        format of a single code, not channel-wide allocation): per AdE Specifiche
        Tecniche 1.9.1 (in force 2026-05-15), an accredited reception channel (WS or
        SFTP) may request a maximum of 300 CodiceDestinatario codes via the Sistema di
        Accreditamento once it has passed to production. This cap is unrelated to, and
        does not change, the per-invoice 6/7-character format validated above.

        On success returns a dict with 'routing_type', 'codice_destinatario' and/or
        'pec_destinatario', and a 'note' with usage guidance.
        On invalid input returns {'error': '<reason>'}.
        """
        if not codice and not pec:
            return {"error": "At least one of 'codice' or 'pec' must be provided."}

        result: dict = {}

        if codice:
            codice_upper = codice.upper()
            if codice_upper == "0000000":
                result["routing_type"] = "PEC"
                result["codice_destinatario"] = "0000000"
                result["note"] = "Use pec_destinatario field in DatiTrasmissione for PEC routing."
            elif re.match(r"^[A-Z0-9]{6,7}$", codice_upper):
                result["routing_type"] = "SDI_CODE"
                result["codice_destinatario"] = codice_upper
                code_len = len(codice_upper)
                result["note"] = (
                    f"Valid {code_len}-character SDI code "
                    f"({'PA/IPA office (FPA12)' if code_len == 6 else 'B2B intermediary (FPR12)'})."
                    " Live directory lookup via SDI SOAP is not available in v0.2.2."
                )
            else:
                return {
                    "error": (
                        f"Invalid CodiceDestinatario '{codice}'. "
                        "Must be 6 alphanumeric chars (PA/IPA), 7 alphanumeric chars (B2B intermediary), "
                        "or '0000000' for PEC routing."
                    )
                }

        if pec:
            if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", pec):
                return {"error": f"Invalid PEC format: '{pec}'."}
            result["pec_destinatario"] = pec
            result["routing_type"] = result.get("routing_type", "PEC")

        return result
