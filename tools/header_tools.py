"""
MCP tools for the FatturaElettronicaHeader section of FatturaPA v1.6.1.

Covers transmission data, seller/buyer validation, fiscal regime codes,
Partita IVA validation, ProgressivoInvio generation, and SDI recipient lookup.
"""

from __future__ import annotations

import random
import re
from typing import Annotated, Optional

from fastmcp import FastMCP
from pydantic import Field

from mcp_einvoicing_core.logging_utils import get_logger

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
                    "6-character alphanumeric SDI recipient code assigned to the buyer's "
                    "intermediary. Use '0000000' (7 zeros) when routing via PEC email instead."
                )
            ),
        ],
        pec_destinatario: Annotated[
            Optional[str],
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
        denominazione: Annotated[
            Optional[str],
            Field(
                default=None,
                description="Company name (Denominazione). Mutually exclusive with nome+cognome.",
            ),
        ] = None,
        nome: Annotated[
            Optional[str],
            Field(default=None, description="First name (Nome), for individual sellers."),
        ] = None,
        cognome: Annotated[
            Optional[str],
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

        Validates: either denominazione or both nome+cognome must be provided (mutually
        exclusive); regime_fiscale must be a valid RF01–RF19 code; Italian Partita IVA
        (id_paese='IT') must be exactly 11 digits.

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

        if errors:
            return {"error": "; ".join(errors)}

        anagrafica: dict = {}
        if denominazione:
            anagrafica["Denominazione"] = denominazione
        else:
            anagrafica["Nome"] = nome
            anagrafica["Cognome"] = cognome

        return {
            "CedentePrestatore": {
                "DatiAnagrafici": {
                    "IdFiscaleIVA": {"IdPaese": id_paese.upper(), "IdCodice": id_codice},
                    "Anagrafica": anagrafica,
                    "RegimeFiscale": regime_fiscale,
                },
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
            Optional[str],
            Field(
                default=None,
                description=(
                    "Company name of the buyer. "
                    "Mutually exclusive with nome+cognome."
                ),
            ),
        ] = None,
        nome: Annotated[
            Optional[str],
            Field(default=None, description="First name of the buyer (natural person)."),
        ] = None,
        cognome: Annotated[
            Optional[str],
            Field(default=None, description="Last name of the buyer (natural person)."),
        ] = None,
        id_paese: Annotated[
            Optional[str],
            Field(
                default=None,
                description=(
                    "ISO country code for IdFiscaleIVA. Required for VAT-registered buyers. "
                    "Omit for Italian buyers identified only by CodiceFiscale."
                ),
            ),
        ] = None,
        id_codice: Annotated[
            Optional[str],
            Field(
                default=None,
                description="VAT number of the buyer. Required if id_paese is provided.",
            ),
        ] = None,
        codice_fiscale: Annotated[
            Optional[str],
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

        On success returns {'CessionarioCommittente': {...}} ready for generate_fattura_xml().
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

        return {
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

        if not re.match(r"^\d{11}$", piva):
            return {"valid": False, "value": piva, "error": "Partita IVA must be exactly 11 digits."}

        total = 0
        for i, digit in enumerate(piva[:10]):
            d = int(digit)
            if i % 2 == 1:
                d *= 2
                if d > 9:
                    d -= 9
            total += d

        expected = (10 - (total % 10)) % 10
        actual = int(piva[10])

        if expected != actual:
            return {
                "valid": False,
                "value": piva,
                "error": f"Checksum mismatch: expected {expected}, got {actual}.",
            }

        return {"valid": True, "value": piva}

    @mcp.tool()
    def generate_progressivo_invio(
        prefix: Annotated[
            Optional[str],
            Field(
                default=None,
                description=(
                    "Optional alphabetic prefix (max 3 chars) to prepend to the sequence number. "
                    "E.g. 'INV' → 'INV00001'. Total length must not exceed 10 chars."
                ),
            ),
        ] = None,
        sequence: Annotated[
            Optional[int],
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
            Optional[str],
            Field(
                default=None,
                description=(
                    "6-character alphanumeric SDI CodiceDestinatario to look up. "
                    "Special value '0000000' (7 zeros) indicates PEC routing."
                ),
            ),
        ] = None,
        pec: Annotated[
            Optional[str],
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
        - codice is 6 alphanumeric chars (e.g. 'ABC123') → routing_type: 'SDI_CODE'
        - codice is '0000000' (7 zeros) → routing_type: 'PEC'; pec_destinatario is then
          mandatory in build_transmission_header()
        - pec only (no codice) → validates email format, routing_type: 'PEC'

        Limitation: performs format validation only — no live query against the SDI
        SOAP directory service (planned for a future release).

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
            elif re.match(r"^[A-Z0-9]{6}$", codice_upper):
                result["routing_type"] = "SDI_CODE"
                result["codice_destinatario"] = codice_upper
                result["note"] = (
                    "Valid 6-character SDI code. "
                    "Live directory lookup via SDI SOAP is not available in v0.1.0."
                )
                # TODO v0.2: Live lookup via SDI SOAP directory service.
            else:
                return {
                    "error": (
                        f"Invalid CodiceDestinatario '{codice}'. "
                        "Must be 6 alphanumeric chars or '0000000' for PEC routing."
                    )
                }

        if pec:
            if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", pec):
                return {"error": f"Invalid PEC format: '{pec}'."}
            result["pec_destinatario"] = pec
            result["routing_type"] = result.get("routing_type", "PEC")

        return result
