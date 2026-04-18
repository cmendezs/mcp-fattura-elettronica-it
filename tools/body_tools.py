"""
MCP tools for the FatturaElettronicaBody section of FatturaPA v1.6.1.

Covers general document data, line items, VAT summary, payment terms,
Natura exemption codes, and attachments.
"""

from __future__ import annotations

import base64
import logging
import re
from decimal import Decimal, ROUND_HALF_UP
from typing import Annotated, Optional

from fastmcp import FastMCP
from pydantic import Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# TipoDocumento reference table (TD01–TD28)
# ---------------------------------------------------------------------------

TIPO_DOCUMENTO: dict[str, dict] = {
    "TD01": {"description": "Fattura", "use_case": "Standard B2B/B2G invoice"},
    "TD02": {"description": "Acconto/anticipo su fattura", "use_case": "Advance payment on invoice"},
    "TD03": {"description": "Acconto/anticipo su parcella", "use_case": "Advance payment on professional fee"},
    "TD04": {"description": "Nota di credito", "use_case": "Credit note (reversal of TD01)"},
    "TD05": {"description": "Nota di debito", "use_case": "Debit note"},
    "TD06": {"description": "Parcella", "use_case": "Professional fee invoice (avvocati, medici, etc.)"},
    "TD07": {"description": "Fattura semplificata", "use_case": "Simplified invoice ≤400 EUR — TODO v0.2"},
    "TD08": {"description": "Nota di credito semplificata", "use_case": "Simplified credit note — TODO v0.2"},
    "TD09": {"description": "Nota di debito semplificata", "use_case": "Simplified debit note — TODO v0.2"},
    "TD16": {"description": "Integrazione fattura reverse charge interno", "use_case": "Domestic reverse charge self-invoice"},
    "TD17": {"description": "Integrazione/autofattura acquisto servizi dall'estero", "use_case": "Self-invoice for services purchased abroad"},
    "TD18": {"description": "Integrazione acquisto beni intracomunitari", "use_case": "Self-invoice for intra-EU goods purchase"},
    "TD19": {"description": "Integrazione/autofattura acquisto beni ex art.17 c.2 DPR 633/72", "use_case": "Self-invoice for goods under art. 17(2)"},
    "TD20": {"description": "Autofattura per regolarizzazione e integrazione delle fatture", "use_case": "Self-invoice for regularisation"},
    "TD21": {"description": "Autofattura per splafonamento", "use_case": "Self-invoice for VAT exemption ceiling exceeded"},
    "TD22": {"description": "Estrazione beni da Deposito IVA", "use_case": "Extraction of goods from VAT warehouse"},
    "TD23": {"description": "Estrazione beni da Deposito IVA con versamento IVA", "use_case": "Extraction with VAT payment"},
    "TD24": {"description": "Fattura differita di cui all'art.21, c.4, lett. a", "use_case": "Deferred invoice (goods, DDT-based)"},
    "TD25": {"description": "Fattura differita di cui all'art.21, c.4, terzo periodo lett. b", "use_case": "Deferred invoice (services)"},
    "TD26": {"description": "Cessione di beni ammortizzabili e per passaggi interni", "use_case": "Transfer of depreciable assets"},
    "TD27": {"description": "Fattura per autoconsumo o per cessioni gratuite senza rivalsa", "use_case": "Invoice for self-consumption or free transfers"},
    "TD28": {"description": "Acquisti da San Marino con IVA (art. 16, c. 11, D.Lgs. 175/2014)", "use_case": "Purchases from San Marino with VAT (cross-border since 2022)"},
}

# ---------------------------------------------------------------------------
# Natura codes reference table (N1–N7)
# ---------------------------------------------------------------------------

NATURA_CODES: dict[str, dict] = {
    "N1": {"description": "Escluse ex art. 15", "legal_ref": "Art. 15 DPR 633/72"},
    "N2": {"description": "Non soggette", "legal_ref": "Various exclusions from VAT scope"},
    "N2.1": {"description": "Non soggette ad IVA ai sensi degli artt. da 7 a 7-septies del DPR 633/72", "legal_ref": "Art. 7–7-septies DPR 633/72 (territoriality)"},
    "N2.2": {"description": "Non soggette — altri casi", "legal_ref": "Other out-of-scope cases"},
    "N3": {"description": "Non imponibili", "legal_ref": "Zero-rated supplies"},
    "N3.1": {"description": "Non imponibili — esportazioni", "legal_ref": "Art. 8 DPR 633/72 (exports)"},
    "N3.2": {"description": "Non imponibili — cessioni intracomunitarie", "legal_ref": "Art. 41 DL 331/93 (intra-EU)"},
    "N3.3": {"description": "Non imponibili — cessioni verso San Marino", "legal_ref": "Art. 71 DPR 633/72"},
    "N3.4": {"description": "Non imponibili — operazioni assimilate alle cessioni all'esportazione", "legal_ref": "Art. 8-bis DPR 633/72"},
    "N3.5": {"description": "Non imponibili — a seguito di dichiarazioni d'intento", "legal_ref": "Habitual exporter declaration (lettera d'intento)"},
    "N3.6": {"description": "Non imponibili — altre operazioni che non concorrono alla formazione del plafond", "legal_ref": "Other zero-rated not forming VAT ceiling"},
    "N4": {"description": "Esenti", "legal_ref": "Art. 10 DPR 633/72 (VAT-exempt supplies)"},
    "N5": {"description": "Regime del margine / IVA non esposta in fattura", "legal_ref": "Art. 36 DL 41/95 (margin scheme)"},
    "N6": {"description": "Inversione contabile (reverse charge)", "legal_ref": "Various reverse charge provisions"},
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
# ModalitaPagamento reference table (MP01–MP23)
# ---------------------------------------------------------------------------

MODALITA_PAGAMENTO: dict[str, str] = {
    "MP01": "Contanti",
    "MP02": "Assegno",
    "MP03": "Assegno circolare",
    "MP04": "Contanti presso Tesoreria",
    "MP05": "Bonifico",
    "MP06": "Vaglia cambiario",
    "MP07": "Bollettino bancario",
    "MP08": "Carta di pagamento",
    "MP09": "RID",
    "MP10": "RID utenze",
    "MP11": "RID veloce",
    "MP12": "RIBA",
    "MP13": "MAV",
    "MP14": "Quietanza erario stato",
    "MP15": "Giroconto su conti di contabilità speciale",
    "MP16": "Domiciliazione bancaria",
    "MP17": "Domiciliazione postale",
    "MP18": "Bollettino di c/c postale",
    "MP19": "SEPA Direct Debit",
    "MP20": "SEPA Direct Debit CORE",
    "MP21": "SEPA Direct Debit B2B",
    "MP22": "Trattenuta su somme già riscosse",
    "MP23": "PagoPA",
}


def register_body_tools(mcp: FastMCP) -> None:
    """Register the 7 FatturaElettronicaBody tools on the FastMCP instance."""

    @mcp.tool()
    def build_dati_generali(
        tipo_documento: Annotated[
            str,
            Field(
                description=(
                    "Document type code TD01–TD28. Use get_tipo_documento_codes() for the "
                    "full list. Most invoices use TD01 (standard invoice)."
                )
            ),
        ],
        data: Annotated[
            str,
            Field(
                description=(
                    "Invoice date in ISO 8601 format (YYYY-MM-DD), e.g. '2026-01-15'. "
                    "Must not be a future date for ordinary invoices."
                )
            ),
        ],
        numero: Annotated[
            str,
            Field(
                description=(
                    "Invoice number (Numero), max 20 alphanumeric chars. "
                    "Must be unique and sequential per fiscal year."
                )
            ),
        ],
        divisa: Annotated[
            str,
            Field(
                default="EUR",
                description="ISO 4217 currency code. Default 'EUR'. Other currencies for cross-border invoices.",
            ),
        ] = "EUR",
        causale: Annotated[
            Optional[str],
            Field(
                default=None,
                description=(
                    "Optional free-text description/reason for the invoice (Causale), "
                    "max 200 chars. Can appear multiple times — pass a single string here."
                ),
            ),
        ] = None,
        rif_numero_linea: Annotated[
            Optional[int],
            Field(
                default=None,
                description="Line number reference for credit/debit notes linking back to the original invoice.",
            ),
        ] = None,
        id_documento_riferimento: Annotated[
            Optional[str],
            Field(
                default=None,
                description="Number of the original invoice (for credit notes TD04, debit notes TD05, etc.).",
            ),
        ] = None,
        data_documento_riferimento: Annotated[
            Optional[str],
            Field(
                default=None,
                description="Date of the original invoice (YYYY-MM-DD), for TD04/TD05.",
            ),
        ] = None,
    ) -> dict:
        """Build a DatiGenerali block for the FatturaElettronicaBody.

        Constructs the general document data section required in every FatturaPA body,
        including document type, currency, date, number, and optional reference to the
        original document (for credit/debit notes).

        Args:
            tipo_documento: Document type code (TD01–TD28).
            data: Invoice date (YYYY-MM-DD).
            numero: Invoice number (max 20 chars).
            divisa: Currency code (default EUR).
            causale: Optional description/reason text.
            rif_numero_linea: Line reference for credit/debit notes.
            id_documento_riferimento: Number of referenced original invoice.
            data_documento_riferimento: Date of referenced original invoice.

        Returns:
            A dict representing the DatiGenerali block, or an error dict on failure.
        """
        if tipo_documento not in TIPO_DOCUMENTO:
            return {
                "error": (
                    f"Invalid tipo_documento '{tipo_documento}'. "
                    f"Valid codes: {', '.join(TIPO_DOCUMENTO.keys())}."
                )
            }

        if not re.match(r"^\d{4}-\d{2}-\d{2}$", data):
            return {"error": f"Invalid date format '{data}'. Use YYYY-MM-DD."}

        if len(numero) > 20:
            return {"error": "Invoice number (Numero) must not exceed 20 characters."}

        dati_generali_documento: dict = {
            "TipoDocumento": tipo_documento,
            "Divisa": divisa.upper(),
            "Data": data,
            "Numero": numero,
        }

        if causale:
            dati_generali_documento["Causale"] = causale[:200]

        dati_generali: dict = {"DatiGeneraliDocumento": dati_generali_documento}

        if id_documento_riferimento:
            dati_riferimento: dict = {"IdDocumento": id_documento_riferimento}
            if data_documento_riferimento:
                dati_riferimento["Data"] = data_documento_riferimento
            if rif_numero_linea:
                dati_riferimento["RiferimentoNumeroLinea"] = rif_numero_linea
            dati_generali["DatiFattureCollegate"] = dati_riferimento

        return {"DatiGenerali": dati_generali}

    @mcp.tool()
    def get_tipo_documento_codes() -> dict:
        """Return all document type codes TD01–TD28 with descriptions and use cases.

        Provides the complete FatturaPA reference table for TipoDocumento, including
        self-invoicing types (TD16–TD27) for reverse charge and cross-border operations,
        and the San Marino VAT type TD28 introduced in 2022.

        Returns:
            A dict with 'codes' (list of {code, description, use_case}) and 'total'.
        """
        codes = [
            {"code": code, "description": info["description"], "use_case": info["use_case"]}
            for code, info in TIPO_DOCUMENTO.items()
        ]
        return {"codes": codes, "total": len(codes)}

    @mcp.tool()
    def add_linea_dettaglio(
        numero_linea: Annotated[
            int,
            Field(
                description=(
                    "Sequential line number starting at 1. "
                    "Each DettaglioLinee entry must have a unique NumeroLinea."
                ),
                ge=1,
                le=9999,
            ),
        ],
        descrizione: Annotated[
            str,
            Field(description="Description of the good or service (max 1000 chars)."),
        ],
        quantita: Annotated[
            Optional[float],
            Field(
                default=None,
                description=(
                    "Quantity (Quantita). Optional for services billed as a lump sum. "
                    "When provided, unit_price × quantita should equal prezzo_totale."
                ),
            ),
        ] = None,
        unita_misura: Annotated[
            Optional[str],
            Field(
                default=None,
                description="Unit of measure (e.g. 'PZ', 'KG', 'ORE', 'M2'). Optional.",
            ),
        ] = None,
        prezzo_unitario: Annotated[
            float,
            Field(description="Unit price before VAT (PrezzoUnitario). Negative for credit notes."),
        ] = 0.0,
        prezzo_totale: Annotated[
            float,
            Field(
                description=(
                    "Total line amount before VAT (PrezzoTotale = quantita × prezzo_unitario). "
                    "Must be provided explicitly; the tool does not auto-compute it."
                )
            ),
        ] = 0.0,
        aliquota_iva: Annotated[
            float,
            Field(
                description=(
                    "VAT rate as a percentage (e.g. 22.0 for 22%, 10.0 for 10%, 0.0 for exempt). "
                    "Use 0.0 together with a Natura code for exempt/out-of-scope supplies."
                ),
                ge=0.0,
                le=100.0,
            ),
        ] = 22.0,
        natura: Annotated[
            Optional[str],
            Field(
                default=None,
                description=(
                    "Natura exemption code (N1–N7, N2.1, N2.2, N3.1–N3.6, N6.1–N6.9, N7). "
                    "Required when aliquota_iva is 0.0. Use get_natura_codes() for the full list."
                ),
            ),
        ] = None,
        ritenuta: Annotated[
            Optional[str],
            Field(
                default=None,
                description=(
                    "Withholding tax flag: 'SI' to indicate that this line is subject to "
                    "ritenuta d'acconto. Use check_ritenuta_acconto() to compute the amount."
                ),
            ),
        ] = None,
    ) -> dict:
        """Add a DettaglioLinee entry to the FatturaElettronicaBody.

        Constructs a single line item for an Italian electronic invoice. Validates
        the Natura code requirement when VAT rate is zero. Returns the structured
        DettaglioLinee dict ready to be included in the body lines array.

        Args:
            numero_linea: Sequential line number (1–9999).
            descrizione: Good or service description (max 1000 chars).
            quantita: Quantity (optional for lump-sum services).
            unita_misura: Unit of measure.
            prezzo_unitario: Unit price before VAT.
            prezzo_totale: Total line amount before VAT.
            aliquota_iva: VAT rate percentage (0.0–100.0).
            natura: Natura exemption code, required when aliquota_iva is 0.0.
            ritenuta: 'SI' if line is subject to withholding tax.

        Returns:
            A dict with the DettaglioLinee entry, or an error dict on failure.
        """
        if aliquota_iva == 0.0 and not natura:
            return {
                "error": (
                    "A Natura code is required when aliquota_iva is 0.0. "
                    "Use get_natura_codes() to choose the correct code."
                )
            }

        if natura and natura not in NATURA_CODES:
            return {
                "error": (
                    f"Invalid natura code '{natura}'. "
                    "Use get_natura_codes() for the complete list."
                )
            }

        if ritenuta and ritenuta not in ("SI",):
            return {"error": "ritenuta must be 'SI' or omitted."}

        linea: dict = {
            "NumeroLinea": numero_linea,
            "Descrizione": descrizione[:1000],
            "PrezzoUnitario": f"{prezzo_unitario:.8f}".rstrip("0").rstrip("."),
            "PrezzoTotale": f"{prezzo_totale:.2f}",
            "AliquotaIVA": f"{aliquota_iva:.2f}",
        }

        if quantita is not None:
            linea["Quantita"] = f"{quantita:.8f}".rstrip("0").rstrip(".")
        if unita_misura:
            linea["UnitaMisura"] = unita_misura
        if natura:
            linea["Natura"] = natura
        if ritenuta:
            linea["Ritenuta"] = ritenuta

        return {"DettaglioLinee": linea}

    @mcp.tool()
    def compute_totali(
        linee: Annotated[
            list,
            Field(
                description=(
                    "List of line item dicts, each containing at least: "
                    "'prezzo_totale' (float), 'aliquota_iva' (float), and optionally 'natura' (str). "
                    "These are the raw values, not the DettaglioLinee dicts."
                )
            ),
        ],
    ) -> dict:
        """Compute DatiRiepilogo totals (taxable base and VAT) grouped by VAT rate.

        Aggregates line items by AliquotaIVA and optional Natura code, computing
        imponibile (taxable base) and imposta (VAT amount) for each group. Returns
        the DatiRiepilogo array required in the FatturaElettronicaBody.

        Args:
            linee: List of dicts with 'prezzo_totale', 'aliquota_iva', and optional 'natura'.

        Returns:
            A dict with 'DatiRiepilogo' (list of summary entries) and 'totale_fattura'.
        """
        groups: dict[tuple, dict] = {}

        for linea in linee:
            prezzo_totale = Decimal(str(linea.get("prezzo_totale", 0)))
            aliquota = Decimal(str(linea.get("aliquota_iva", 22)))
            natura = linea.get("natura")

            key = (str(aliquota), natura or "")
            if key not in groups:
                groups[key] = {
                    "AliquotaIVA": f"{aliquota:.2f}",
                    "Imponibile": Decimal("0"),
                    "Imposta": Decimal("0"),
                    "Natura": natura,
                    "EsigibilitaIVA": "I",  # Immediata (default)
                }

            groups[key]["Imponibile"] += prezzo_totale
            if aliquota > 0:
                groups[key]["Imposta"] += (prezzo_totale * aliquota / 100).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )

        riepilogo = []
        totale_imponibile = Decimal("0")
        totale_imposta = Decimal("0")

        for entry in groups.values():
            imponibile = entry["Imponibile"].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            imposta = entry["Imposta"].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            totale_imponibile += imponibile
            totale_imposta += imposta

            riepilogo_entry: dict = {
                "AliquotaIVA": entry["AliquotaIVA"],
                "Imponibile": str(imponibile),
                "Imposta": str(imposta),
                "EsigibilitaIVA": entry["EsigibilitaIVA"],
            }
            if entry["Natura"]:
                riepilogo_entry["Natura"] = entry["Natura"]

            riepilogo.append(riepilogo_entry)

        totale_fattura = (totale_imponibile + totale_imposta).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        return {
            "DatiRiepilogo": riepilogo,
            "totale_imponibile": str(totale_imponibile.quantize(Decimal("0.01"))),
            "totale_imposta": str(totale_imposta.quantize(Decimal("0.01"))),
            "totale_fattura": str(totale_fattura),
        }

    @mcp.tool()
    def get_natura_codes() -> dict:
        """Return all Natura exemption codes (N1–N7 and sub-codes) with legal references.

        Provides the complete reference table for VAT exemption/exclusion codes required
        in DettaglioLinee when AliquotaIVA is 0.00. Includes reverse charge codes (N6.x),
        intra-EU codes (N3.2), export codes (N3.1), and the OSS/IOSS code (N7).

        Returns:
            A dict with 'codes' (list of {code, description, legal_ref}) and 'total'.
        """
        codes = [
            {"code": code, "description": info["description"], "legal_ref": info["legal_ref"]}
            for code, info in NATURA_CODES.items()
        ]
        return {"codes": codes, "total": len(codes)}

    @mcp.tool()
    def build_dati_pagamento(
        condizioni_pagamento: Annotated[
            str,
            Field(
                description=(
                    "Payment terms code: "
                    "'TP01' = full payment in instalments, "
                    "'TP02' = full single payment, "
                    "'TP03' = advance payment."
                )
            ),
        ],
        modalita_pagamento: Annotated[
            str,
            Field(
                description=(
                    "Payment method code MP01–MP23. Common values: "
                    "MP05 (bonifico/bank transfer), MP01 (cash), MP08 (card), "
                    "MP19/MP20/MP21 (SEPA direct debit), MP23 (PagoPA). "
                    "Use a valid MP code from the FatturaPA reference."
                )
            ),
        ],
        importo_pagamento: Annotated[
            float,
            Field(description="Payment amount (may equal or differ from invoice total for instalments)."),
        ],
        data_scadenza_pagamento: Annotated[
            Optional[str],
            Field(
                default=None,
                description="Payment due date (YYYY-MM-DD). Omit for immediate payment.",
            ),
        ] = None,
        iban: Annotated[
            Optional[str],
            Field(
                default=None,
                description="IBAN for bank transfer (MP05). Validated for format (letters+digits, max 34 chars).",
            ),
        ] = None,
        istituto_finanziario: Annotated[
            Optional[str],
            Field(
                default=None,
                description="Name of the financial institution (bank name). Optional.",
            ),
        ] = None,
    ) -> dict:
        """Build a DatiPagamento block for the FatturaElettronicaBody.

        Constructs the payment terms and method section required in every FatturaPA body.
        Validates CondizioniPagamento and ModalitaPagamento codes, IBAN format, and
        due date format.

        Args:
            condizioni_pagamento: Payment terms code (TP01/TP02/TP03).
            modalita_pagamento: Payment method code (MP01–MP23).
            importo_pagamento: Payment amount.
            data_scadenza_pagamento: Due date (YYYY-MM-DD).
            iban: IBAN for bank transfers.
            istituto_finanziario: Bank name.

        Returns:
            A dict with the DatiPagamento block, or an error dict on failure.
        """
        if condizioni_pagamento not in ("TP01", "TP02", "TP03"):
            return {
                "error": (
                    f"Invalid condizioni_pagamento '{condizioni_pagamento}'. "
                    "Valid values: TP01 (instalments), TP02 (single payment), TP03 (advance)."
                )
            }

        if modalita_pagamento not in MODALITA_PAGAMENTO:
            return {
                "error": (
                    f"Invalid modalita_pagamento '{modalita_pagamento}'. "
                    f"Valid codes: {', '.join(MODALITA_PAGAMENTO.keys())}."
                )
            }

        if iban and not re.match(r"^[A-Z]{2}[0-9]{2}[A-Z0-9]{1,30}$", iban.replace(" ", "").upper()):
            return {"error": f"Invalid IBAN format: '{iban}'."}

        if data_scadenza_pagamento and not re.match(r"^\d{4}-\d{2}-\d{2}$", data_scadenza_pagamento):
            return {"error": f"Invalid due date format '{data_scadenza_pagamento}'. Use YYYY-MM-DD."}

        dettaglio_pagamento: dict = {
            "ModalitaPagamento": modalita_pagamento,
            "ImportoPagamento": f"{importo_pagamento:.2f}",
        }

        if data_scadenza_pagamento:
            dettaglio_pagamento["DataScadenzaPagamento"] = data_scadenza_pagamento
        if iban:
            dettaglio_pagamento["IBAN"] = iban.replace(" ", "").upper()
        if istituto_finanziario:
            dettaglio_pagamento["IstitutoFinanziario"] = istituto_finanziario

        return {
            "DatiPagamento": {
                "CondizioniPagamento": condizioni_pagamento,
                "DettaglioPagamento": dettaglio_pagamento,
            }
        }

    @mcp.tool()
    def add_allegato(
        nome_allegato: Annotated[
            str,
            Field(
                description=(
                    "Attachment file name (NomeAllegato), max 60 chars. "
                    "Include the extension (e.g. 'contract.pdf', 'ddt_001.pdf')."
                )
            ),
        ],
        attachment_base64: Annotated[
            str,
            Field(
                description=(
                    "Base64-encoded content of the attachment. "
                    "Any binary file is accepted; common formats: PDF, XML, JPG, ZIP."
                )
            ),
        ],
        formato_allegato: Annotated[
            Optional[str],
            Field(
                default=None,
                description=(
                    "MIME type or format description (FormatoAllegato), max 10 chars. "
                    "Examples: 'PDF', 'XML', 'ZIP'. Optional but recommended."
                ),
            ),
        ] = None,
        descrizione_allegato: Annotated[
            Optional[str],
            Field(
                default=None,
                description="Short description of the attachment content, max 100 chars. Optional.",
            ),
        ] = None,
    ) -> dict:
        """Attach a base64-encoded document to the Allegati block of a FatturaPA.

        Validates the base64 encoding and constructs the Allegati entry with name,
        content, format, and optional description. Multiple attachments can be added
        by calling this tool once per file.

        Args:
            nome_allegato: File name of the attachment (max 60 chars).
            attachment_base64: Base64-encoded binary content.
            formato_allegato: MIME type/format code (max 10 chars).
            descrizione_allegato: Optional description (max 100 chars).

        Returns:
            A dict with the Allegati entry (without decoded content), or an error dict.
        """
        try:
            decoded = base64.b64decode(attachment_base64)
        except Exception as exc:
            return {"error": f"Invalid base64 content: {exc}"}

        if len(nome_allegato) > 60:
            return {"error": "nome_allegato must not exceed 60 characters."}

        allegato: dict = {
            "NomeAllegato": nome_allegato,
            "Attachment": attachment_base64,
            "size_bytes": len(decoded),
        }

        if formato_allegato:
            allegato["FormatoAllegato"] = formato_allegato[:10]
        if descrizione_allegato:
            allegato["DescrizioneAllegato"] = descrizione_allegato[:100]

        return {"Allegati": allegato}
