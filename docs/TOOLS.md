# Tool reference — `mcp_fattura_elettronica_it`

This file is generated from the MCP server's tool registry by `scripts/gen_tool_reference.py`. Do not edit it by hand; run the script instead.

**Tools:** 43

## `add_allegato`

Build an Allegati (attachment) entry to include in a FatturaPA document.

Use this when you need to attach supporting documents (e.g. DDT, contract, PDF)
to the invoice. Call once per file, collect results in a list, and pass it to
generate_fattura_xml() as the allegati parameter.

attachment_base64 must be valid standard base64 (RFC 4648); the tool verifies
decodability. nome_allegato must include the file extension (e.g. 'contract.pdf').
formato_allegato (e.g. 'PDF', 'XML', 'ZIP') is optional but recommended for
recipients to identify the content without decoding.

On success returns {'Allegati': {'NomeAllegato', 'Attachment', 'size_bytes', ...}}.
On failure returns {'error': '<reason>'} (invalid base64 or name > 60 chars).

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `nome_allegato` | string | yes |  | Attachment file name (NomeAllegato), max 60 chars. Include the extension (e.g. 'contract.pdf', 'ddt_001.pdf'). |
| `attachment_base64` | string | yes |  | Base64-encoded content of the attachment. Any binary file is accepted; common formats: PDF, XML, JPG, ZIP. |
| `formato_allegato` | string | null | no | `None` | MIME type or format description (FormatoAllegato), max 10 chars. Examples: 'PDF', 'XML', 'ZIP'. Optional but recommended. |
| `descrizione_allegato` | string | null | no | `None` | Short description of the attachment content, max 100 chars. Optional. |

## `add_linea_dettaglio`

Build a single DettaglioLinee (line item) entry for the FatturaElettronicaBody.

Use this as step 7 in the invoice generation workflow — call once per line item
after build_dati_generali(). Collect all returned dicts into a list and pass it
to compute_totali() (step 8) and then generate_fattura_xml() (step 10).

numero_linea must be sequential starting at 1; do not reuse numbers in the same invoice.
prezzo_totale must be provided explicitly (not computed); use negative values for credit notes.
When aliquota_iva is 0.0, natura is required — call get_natura_codes() to select the code.
Set ritenuta='SI' on lines subject to withholding tax and include the DatiRitenuta block
from check_ritenuta_acconto() when generating XML.
altri_dati_gestionali (optional): structured management data entries, emitted after
Natura in the XSD element order. See build_sport_worker_exemption_dato_gestionale()
for the codifica introduced by Specifiche Tecniche 1.9.1.

On success returns {'DettaglioLinee': {...}}, plus 'warnings' (list[str])
when aliquota_iva is a non-standard IT VAT rate (outside 4, 5, 10, 22).
On failure returns {'error': '<reason>'}.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `numero_linea` | integer | yes |  | Sequential line number starting at 1. Each DettaglioLinee entry must have a unique NumeroLinea. |
| `descrizione` | string | yes |  | Description of the good or service (max 1000 chars). |
| `quantita` | number | null | no | `None` | Quantity (Quantita). Optional for services billed as a lump sum. When provided, unit_price × quantita should equal prezzo_totale. |
| `unita_misura` | string | null | no | `None` | Unit of measure (e.g. 'PZ', 'KG', 'ORE', 'M2'). Optional. |
| `prezzo_unitario` | number | no | `0.0` | Unit price before VAT (PrezzoUnitario). Negative for credit notes. |
| `prezzo_totale` | number | no | `0.0` | Total line amount before VAT (PrezzoTotale = quantita × prezzo_unitario). Must be provided explicitly; the tool does not auto-compute it. |
| `aliquota_iva` | number | no | `22.0` | VAT rate as a percentage (e.g. 22.0 for 22%, 10.0 for 10%, 0.0 for exempt). Use 0.0 together with a Natura code for exempt/out-of-scope supplies. |
| `natura` | string | null | no | `None` | Natura exemption code: N1, N2.1, N2.2, N3.1–N3.6, N4, N5, N6.1–N6.9, N7. Parent codes N2, N3, N6 are invalid since Jan 2021 and are not accepted. Required when aliquota_iva is 0.0. Use get_natura_codes() for the full list. |
| `ritenuta` | string | null | no | `None` | Withholding tax flag: 'SI' to indicate that this line is subject to ritenuta d'acconto. Use check_ritenuta_acconto() to compute the amount. |
| `altri_dati_gestionali` | array[object] | null | no | `None` | Optional list of AltriDatiGestionali entries (DettaglioLinee, XSD maxOccurs unbounded). Each entry is a dict with XSD-cased keys: 'TipoDato' (str, required, max 10 chars), 'RiferimentoTesto' (str, optional, max 60 chars), 'RiferimentoNumero' (str/float, optional), 'RiferimentoData' (str YYYY-MM-DD, optional) — the same shape returned by build_sport_worker_exemption_dato_gestionale()['AltriDatiGestionali'], which can be passed straight through in this list for the sport-worker IRPEF exemption codifica ('ESENZSPORT'). |

## `build_dati_generali`

Build the DatiGenerali block required in every FatturaElettronicaBody.

Use this as step 6 in the invoice generation workflow, after validate_cessionario()
and before add_linea_dettaglio(). Call get_tipo_documento_codes() first to select
the correct TD code (most invoices use TD01; credit notes use TD04; professional
fee invoices use TD06).

For credit notes (TD04) or debit notes (TD05), set id_documento_riferimento to the
original invoice number and data_documento_riferimento to its issue date.

Validates: tipo_documento must be a valid TD01–TD28 code; data must be YYYY-MM-DD;
numero must not exceed 20 characters.

On success returns {'DatiGenerali': {...}} ready for generate_fattura_xml().
On failure returns {'error': '<reason>'}.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `tipo_documento` | string | yes |  | Document type code TD01–TD28. Use get_tipo_documento_codes() for the full list. Most invoices use TD01 (standard invoice). |
| `data` | string | yes |  | Invoice date in ISO 8601 format (YYYY-MM-DD), e.g. '2026-01-15'. Must not be a future date for ordinary invoices. |
| `numero` | string | yes |  | Invoice number (Numero), max 20 alphanumeric chars. Must be unique and sequential per fiscal year. |
| `divisa` | string | no | `'EUR'` | ISO 4217 currency code. Default 'EUR'. Other currencies for cross-border invoices. |
| `causale` | string | array[string] | null | no | `None` | Free-text description/reason for the invoice (Causale), max 200 chars each. Pass a single string or a list of strings for multiple Causale elements. The XSD allows maxOccurs='unbounded'. |
| `rif_numero_linea` | integer | null | no | `None` | Line number reference for credit/debit notes linking back to the original invoice. |
| `id_documento_riferimento` | string | null | no | `None` | Number of the original invoice (for credit notes TD04, debit notes TD05, etc.). |
| `data_documento_riferimento` | string | null | no | `None` | Date of the original invoice (YYYY-MM-DD), for TD04/TD05. |

## `build_dati_pagamento`

Build the DatiPagamento block for the FatturaElettronicaBody.

Use this as step 9 in the invoice generation workflow, after compute_totali() and
before generate_fattura_xml(). The block is optional in the XML but strongly
recommended for B2B invoices.

condizioni_pagamento: TP01 = instalments, TP02 = single full payment, TP03 = advance.
modalita_pagamento: MP05 (bank transfer) is most common for B2B; include iban when using MP05.
importo_pagamento: for TP02 this should equal totale_fattura from compute_totali();
for TP01 (instalments) call this tool once per instalment tranche.

Validates: condizioni_pagamento in {TP01, TP02, TP03}; modalita_pagamento in MP01–MP23;
IBAN format (letters + digits, max 34 chars); data_scadenza_pagamento is YYYY-MM-DD.

On success returns {'DatiPagamento': {...}} ready for generate_fattura_xml().
On failure returns {'error': '<reason>'}.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `condizioni_pagamento` | string | yes |  | Payment terms code: 'TP01' = full payment in instalments, 'TP02' = full single payment, 'TP03' = advance payment. |
| `modalita_pagamento` | string | yes |  | Payment method code MP01–MP23. Common values: MP05 (bonifico/bank transfer), MP01 (cash), MP08 (card), MP19/MP20/MP21 (SEPA direct debit), MP23 (PagoPA). Use a valid MP code from the FatturaPA reference. |
| `importo_pagamento` | number | yes |  | Payment amount (may equal or differ from invoice total for instalments). |
| `data_scadenza_pagamento` | string | null | no | `None` | Payment due date (YYYY-MM-DD). Omit for immediate payment. |
| `iban` | string | null | no | `None` | IBAN for bank transfer (MP05). Validated for format (letters+digits, max 34 chars). |
| `istituto_finanziario` | string | null | no | `None` | Name of the financial institution (bank name). Optional. |

## `build_sport_worker_exemption_dato_gestionale`

Build the AltriDatiGestionali entry for the sport-worker IRPEF exemption codifica.

Covers compensation under art. 36, comma 6, D.Lgs. 36/2021 (lavoro sportivo
dilettantistico), exempt from the taxable base up to EUR 15,000/year. Sets
TipoDato to 'ESENZSPORT' — verified against AdE Allegato A – Specifiche
Tecniche 1.9.1 (in force 2026-05-15). RiferimentoTesto/RiferimentoNumero are
not mandated for this codifica (unlike e.g. 'ALI-COMP', which requires
RiferimentoNumero); both are left to the caller's discretion here.

Pass the returned dict's 'AltriDatiGestionali' value inside a list to
add_linea_dettaglio()'s altri_dati_gestionali parameter — or pass the dict
itself if you are constructing the list manually.

On success returns {'AltriDatiGestionali': {'TipoDato': 'ESENZSPORT', ...}}.
On failure (invalid riferimento_data) returns {'error': '<reason>'}.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `riferimento_numero` | number | null | no | `None` | Optional cumulative annual compensation amount (EUR) to record in RiferimentoNumero. Not mandated by the spec for this codifica — a convenience for callers who want to track it on the invoice. |
| `riferimento_data` | string | null | no | `None` | Optional reference date (YYYY-MM-DD) for RiferimentoData. |

## `build_transmission_header`

Build the DatiTrasmissione block required in every FatturaPA header.

Use this as step 3 in the invoice generation workflow, after
generate_progressivo_invio() and before validate_cedente_prestatore().
Use lookup_codice_destinatario() first to confirm the recipient code format.

Validates: formato_trasmissione must be 'FPA12' or 'FPR12'; progressivo_invio
must be 1–10 alphanumeric characters; pec_destinatario is required when
codice_destinatario is '0000000'.

On success returns {'DatiTrasmissione': {...}} ready to pass to generate_fattura_xml().
On failure returns {'error': '<reason>'} — do not proceed to XML generation.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `id_paese` | string | yes |  | Two-letter ISO 3166-1 country code of the transmitter (e.g. 'IT'). Usually 'IT' for Italian entities. |
| `id_codice` | string | yes |  | Tax identifier of the transmitter: Partita IVA (11 digits) for Italian entities, or foreign tax ID (max 28 chars) for cross-border. |
| `progressivo_invio` | string | yes |  | Unique sequential send identifier, max 10 alphanumeric characters. Use generate_progressivo_invio() to obtain one automatically. |
| `formato_trasmissione` | string | yes |  | Transmission format: 'FPA12' for invoices to Public Administration (PA), 'FPR12' for invoices to private parties (B2B / B2C). |
| `codice_destinatario` | string | yes |  | SDI recipient code: 6-char for PA offices (IPA code, FPA12), 7-char for B2B intermediaries (FPR12), or '0000000' (7 zeros) for PEC routing. Use lookup_codice_destinatario() to validate the code first. |
| `pec_destinatario` | string | null | no | `None` | PEC (certified email) address of the recipient. Required only when codice_destinatario is '0000000'. |

## `check_ritenuta_acconto`

Compute ritenuta d'acconto (withholding tax) for professional invoices.

Use this when issuing professional service invoices (TD01 or TD06) that are subject
to withholding tax — typically for self-employed professionals, agents, or freelancers.
Also mark the relevant line items with ritenuta='SI' in add_linea_dettaglio(), and pass
the returned 'DatiRitenuta' dict to generate_fattura_xml() as dati_ritenuta.

tipo_ritenuta determines the rate: RT01/RT02 = 20% (ritenuta d'acconto, statutory default).
RT03 (INPS), RT04 (ENASARCO), RT05 (ENPAM), RT06 (other) have variable rates:
aliquota_override or importo_override is required for all of them.
causale_pagamento: income category code for Mod. 770 (e.g. 'A' professional fees, 'O' occasional).
aliquota_override: supply the actual rate (%) for RT03-RT06, or to override the 20% default for RT01/RT02.
importo_override: supply the exact withholding amount when rate-based computation is imprecise.

Validates: tipo_ritenuta must be in RT01-RT06. RT03-RT06 require aliquota_override or importo_override.

On success returns {'DatiRitenuta': {...}, 'importo_ritenuta': str, 'aliquota_applicata': str,
'imponibile_ritenuta': str, 'description': str, 'legal_ref': str}.
On failure returns {'error': '<reason>'}.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `imponibile` | number | yes |  | Taxable base amount subject to withholding tax (imponibile della ritenuta). Usually equals the net invoice total for professional services. |
| `tipo_ritenuta` | string | yes |  | Ritenuta/contributo type code: RT01 (persone fisiche, 20% default), RT02 (persone giuridiche, 20% default), RT03 (contributo INPS, variable rate, override required), RT04 (contributo ENASARCO, variable rate, override required), RT05 (contributo ENPAM, variable rate, override required), RT06 (altro contributo previdenziale, override required). |
| `causale_pagamento` | string | yes |  | Income category code for withholding tax (CausalePagamento). Common values: A (professional fees), B (agent commissions), L (employment), O (occasional work), Q (commissions). See Agenzia delle Entrate Mod. 770 for the complete list. |
| `aliquota_override` | number | null | no | `None` | Override the withholding rate as a percentage (e.g. 4.0 for 4%). Required for RT06 (variable rate). Optional override for RT01–RT05 when the statutory rate differs from the indicative table value. When provided, the table rate is ignored. |
| `importo_override` | number | null | no | `None` | Override the withholding amount directly (e.g. 200.00). Use when the exact amount is known rather than computing from the rate. When both aliquota_override and importo_override are provided, importo_override takes precedence for the amount; aliquota_override is used for the AliquotaRitenuta field. |

## `compute_totali`

Compute DatiRiepilogo VAT summary totals grouped by AliquotaIVA and Natura.

Use this as step 8 in the invoice generation workflow, after all add_linea_dettaglio()
calls and before generate_fattura_xml(). Pass the raw line values (not the
DettaglioLinee dicts): each item needs 'prezzo_totale' (float), 'aliquota_iva' (float),
and optionally 'natura' (str).

Groups lines by (aliquota_iva, natura) pair, sums imponibile, and computes
imposta = imponibile × aliquota / 100 (rounded HALF_UP to 2 decimal places).
EsigibilitaIVA defaults to 'I' (immediata) for all groups.

Always succeeds (empty list produces empty DatiRiepilogo). Returns:
{'DatiRiepilogo': [...], 'totale_imponibile': str, 'totale_imposta': str, 'totale_fattura': str}.
Pass 'DatiRiepilogo' directly to generate_fattura_xml() as dati_riepilogo.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `linee` | array[any] | yes |  | List of line item dicts, each containing at least: 'prezzo_totale' (float), 'aliquota_iva' (float), and optionally 'natura' (str). These are the raw values, not the DettaglioLinee dicts. |

## `export_to_json`

Serialize a parsed FatturaPA dict to a clean, indented JSON string.

Call this after parse_fattura_xml() when you need a human-readable or
machine-transferable representation of the invoice. By default, null/empty
fields are omitted (include_empty=False) to reduce noise in the output.

indent controls JSON indentation (0 = compact, 2 = standard readable, 4 = wide).
include_empty=True retains all keys even when their value is null or empty string.

Always succeeds. Returns {'json_string': str, 'size_chars': int}.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `parsed_fattura` | object | yes |  | Parsed FatturaPA dict as returned by parse_fattura_xml(). Will be serialised to a clean, indented JSON string. |
| `indent` | integer | no | `2` | JSON indentation level (0–8 spaces). Default 2. |
| `include_empty` | boolean | no | `False` | Include fields with null/empty values in output. Default False. |

## `generate_cii_invoice`

Generate a CII CrossIndustryInvoice XML document from an ItalianInvoice dict.

Use this when a CII (UN/CEFACT) wire format is required — for example,
for Factur-X embedded XML or ZUGFeRD-compatible output.
This tool does NOT produce FatturaPA XML; use generate_fattura_xml()
for SdI submission.

Italian national fields are accepted but not emitted (same policy as
generate_ubl_invoice).

On success returns {'xml': str, 'length_bytes': int, 'format': 'CII-D16B'}.
On validation error returns {'error': str, 'details': list[str]}.
On unexpected error returns {'error': str}.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `invoice_data` | object | yes |  | ItalianInvoice-compatible dict to serialise to CII XML (UN/CEFACT CrossIndustryInvoice D16B). Same field requirements as generate_ubl_invoice(). profile (BT-24) for Factur-X / ZUGFeRD-compatible output: 'urn:cen.eu:en16931:2017#conformant#urn:factur-x.eu:1p0:extended' (Extended) or 'urn:cen.eu:en16931:2017' (EN 16931 core). [Inference: profile URN for FatturaPA extended via CII not yet standardised; verify with AdE before production use.] |

## `generate_fattura_semplificata`

Assemble a complete FatturaSemplificata VFSM10 XML document.

Use this for simplified invoices (TD07), simplified credit notes (TD08), and
simplified debit notes (TD09) per art. 21-bis DPR 633/72. These are valid for
transactions up to EUR 400 (tax-inclusive).

The simplified format has a flatter structure than the ordinary FatturaPA: no
per-line VAT breakdown (DettaglioLinee/DatiRiepilogo), no DatiPagamento in the body.
Each DatiBeniServizi entry carries its own Descrizione, Importo, and DatiIVA.

On success returns {'xml': str, 'filename': str, 'length_bytes': int}.
On error returns {'error': '<reason>'}.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `dati_trasmissione` | object | yes |  | Transmission data: IdTrasmittente (IdPaese + IdCodice), ProgressivoInvio, CodiceDestinatario (7-char, or '0000000' for PEC), and optionally PECDestinatario. FormatoTrasmissione is always FSM10. |
| `cedente_prestatore` | object | yes |  | Seller data: IdFiscaleIVA (IdPaese + IdCodice), optional CodiceFiscale, Denominazione or Nome+Cognome, Sede (Indirizzo, CAP, Comune, Nazione), RegimeFiscale (RF01-RF19). |
| `cessionario_committente` | object | yes |  | Buyer data: IdentificativiFiscali (IdFiscaleIVA and/or CodiceFiscale), optional AltriDatiIdentificativi (Denominazione or Nome+Cognome, Sede). |
| `dati_generali` | object | yes |  | General document data: TipoDocumento (TD07/TD08/TD09), Divisa, Data (YYYY-MM-DD), Numero. Optional: BolloVirtuale ('SI'), DatiFatturaRettificata (NumeroFR, DataFR, ElementiRettificati) for TD08/TD09. |
| `dati_beni_servizi` | array[any] | yes |  | List of goods/services entries. Each entry: Descrizione (max 1000 chars), Importo (decimal, tax-inclusive amount), DatiIVA (Imposta and/or Aliquota), optional Natura code, optional RiferimentoNormativo. |
| `allegati` | array[any] | null | no | `None` | Optional list of attachments. Each: NomeAttachment, Attachment (base64), optional FormatoAttachment, DescrizioneAttachment. |

## `generate_fattura_xml`

Assemble a complete FatturaPA v1.2.3 XML document from all prepared blocks.

Use this as step 10 in the invoice generation workflow — the final assembly step.
All required blocks must come from their respective builder/validator tools;
pass the full dict returned by each tool (the function unwraps the top-level key).

Required: dati_trasmissione, cedente_prestatore, cessionario_committente,
dati_generali, dettaglio_linee (list), dati_riepilogo (list from compute_totali()).
Optional: dati_pagamento, allegati (list), dati_ritenuta.

Does NOT validate against the XSD schema — call validate_fattura_xsd() (step 11)
on the returned 'xml' string immediately after to confirm conformance.

On success returns {'xml': str, 'filename': str, 'formato_trasmissione': str, 'length_bytes': int}.
On unexpected error returns {'error': '<reason>'}.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `dati_trasmissione` | object | yes |  | DatiTrasmissione block from build_transmission_header(). Must contain IdTrasmittente, ProgressivoInvio, FormatoTrasmissione, and CodiceDestinatario. |
| `cedente_prestatore` | object | yes |  | CedentePrestatore block from validate_cedente_prestatore(). Contains seller's tax ID, name, address, and fiscal regime. |
| `cessionario_committente` | object | yes |  | CessionarioCommittente block from validate_cessionario(). Contains buyer's tax ID, name, and address. |
| `dati_generali` | object | yes |  | DatiGenerali block from build_dati_generali(). Contains document type, date, number, and currency. |
| `dettaglio_linee` | array[any] | yes |  | List of DettaglioLinee dicts from add_linea_dettaglio(). Each entry must have NumeroLinea, Descrizione, PrezzoUnitario, PrezzoTotale, and AliquotaIVA. |
| `dati_riepilogo` | array[any] | yes |  | List of DatiRiepilogo dicts from compute_totali(). Contains VAT summary grouped by AliquotaIVA. |
| `dati_pagamento` | object | null | no | `None` | DatiPagamento block from build_dati_pagamento(). Optional. |
| `allegati` | array[any] | null | no | `None` | List of Allegati dicts from add_allegato(). Optional. |
| `dati_ritenuta` | object | null | no | `None` | DatiRitenuta block from check_ritenuta_acconto(). Required for professional invoices with withholding tax (ritenuta d'acconto). |
| `additional_bodies` | array[any] | null | no | `None` | Additional FatturaElettronicaBody blocks for FPA12 batch invoicing. Each entry is a dict with keys: dati_generali, dettaglio_linee, dati_riepilogo, and optionally dati_pagamento, allegati, dati_ritenuta. Only valid for FPA12 (B2G) transmissions; FPR12 does not support batching. |

## `generate_progressivo_invio`

Generate a ProgressivoInvio identifier for the DatiTrasmissione block.

Use this as step 2 in the invoice generation workflow, before
build_transmission_header(). The SDI requires each ProgressivoInvio to be unique
per transmitter Partita IVA — in production, pass an explicit monotonically
increasing sequence number; use the random default only for testing.

prefix (optional): alphabetic 1–3 char prefix, e.g. 'INV' → 'INV00001'.
sequence (optional): integer 1–9999999; random 5-digit value if omitted.
Total length must not exceed 10 characters.

On success returns {'progressivo_invio': str, 'length': int}.
On failure (invalid prefix) returns {'error': '<reason>'}.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `prefix` | string | null | no | `None` | Optional alphabetic prefix (max 3 chars) to prepend to the sequence number. E.g. 'INV' → 'INV00001'. Total length must not exceed 10 chars. |
| `sequence` | integer | null | no | `None` | Explicit sequence number (1–9999999). If omitted, a random 5-digit number is generated. Callers should track their own sequence in production. |

## `generate_ubl_invoice`

Generate a UBL 2.1 Invoice XML document from an ItalianInvoice dict.

Use this for cross-border B2B invoices or Peppol-routed documents.
This tool does NOT produce FatturaPA XML; use generate_fattura_xml()
for SdI submission.

Italian national fields (progressivo_invio, codice_destinatario,
regime_fiscale) are accepted in the input dict but are not emitted
in the UBL output — they belong in the FatturaPA DatiTrasmissione header.

profile (BT-24) should be the Peppol BIS Billing 3.0 customisation ID
('urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0')
or the EN 16931 core profile ('urn:cen.eu:en16931:2017') for non-Peppol use.
[Inference: FatturaPA-specific CIUS URN not yet standardised for UBL; verify
with AdE if UBL submission to an IT-specific platform is intended.]

On success returns {'xml': str, 'length_bytes': int, 'format': 'UBL-2.1'}.
On validation error returns {'error': str, 'details': list[str]}.
On unexpected error returns {'error': str}.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `invoice_data` | object | yes |  | ItalianInvoice-compatible dict to serialise to UBL 2.1 XML. Required top-level fields: profile (str, BT-24 customisation ID), invoice_number (str), invoice_date (ISO 8601 date string), invoice_type_code (str, '380' invoice / '381' credit note), currency_code (str, 'EUR'), seller (dict with name, address), buyer (dict with name, address), line_items (list of line dicts), tax_lines (list of tax dicts), sum_of_line_net_amounts, tax_exclusive_amount, tax_total, tax_inclusive_amount, amount_due (all Decimal-compatible strings or numbers). Optional: note, buyer_reference, payment_means, due_date, progressivo_invio, codice_destinatario, regime_fiscale. address fields: line_one, city, postcode, country_code (2-char ISO). party fields: name (str), vat_id (optional, with country prefix, e.g. 'IT01234567890'). line fields: line_id, name, quantity, unit_code, unit_price, line_net_amount, tax_category (UNCL5305, e.g. 'S'), tax_rate (%, e.g. 22). tax fields: category, rate, taxable_amount, tax_amount. |

## `get_natura_codes`

Return the complete list of valid Natura exemption codes with legal references.

Call this when add_linea_dettaglio() requires a Natura code (i.e. aliquota_iva is 0.0).
Common codes: N1 (excluded, art. 15), N2.1 (out-of-scope, territoriality),
N3.1 (exports), N3.2 (intra-EU supplies), N4 (VAT-exempt), N6.x (reverse charge),
N7 (OSS/IOSS — VAT paid in another EU state).
Note: parent codes N2, N3, N6 were removed from the FatturaPA XSD enumeration
effective 1 January 2021. Use sub-codes (N2.1, N2.2, N3.1–N3.6, N6.1–N6.9) instead.

Always succeeds. Returns {'codes': [{'code', 'description', 'legal_ref'}, ...], 'total': int}.

_No parameters._

## `get_regime_fiscale_codes`

Return the complete list of RegimeFiscale codes (RF01–RF19) with descriptions.

Call this to look up the correct fiscal regime code before calling
validate_cedente_prestatore(). Every Italian seller must declare a regime:
RF01 (ordinary) covers most companies; RF19 (forfettario) covers flat-rate
sole traders; all other codes cover specialised VAT regimes.

Always succeeds. Returns {'codes': [{'code': str, 'description': str}, ...], 'total': int}.

_No parameters._

## `get_sdi_filename`

Generate the canonical SDI filename for a FatturaPA document.

Use this when you need the official filename independently of generate_fattura_xml()
(which also produces the filename). The SDI specification requires the format:
IT{PartitaIVA}_{ProgressivoInvio}.xml, e.g. IT01234567890_00001.xml.

Validates: partita_iva_cedente must be exactly 11 digits; progressivo_invio must be
1–10 alphanumeric characters. Purely numeric progressivo shorter than 5 digits is
zero-padded to 5 digits (e.g. '1' → '00001').

On success returns {'filename': str, 'partita_iva': str, 'progressivo_invio': str, 'length': int}.
On failure returns {'error': '<reason>'}.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `partita_iva_cedente` | string | yes |  | Partita IVA of the sender (CedentePrestatore) — 11 digits, without prefix. The SDI prepends 'IT' automatically. |
| `progressivo_invio` | string | yes |  | ProgressivoInvio used in DatiTrasmissione — max 10 alphanumeric chars. Zero-padded to 5 digits if purely numeric and shorter than 5 chars. |

## `get_tipo_documento_codes`

Return the complete list of document type codes (TD01–TD28) with descriptions and use cases.

Call this to choose the correct TipoDocumento before calling build_dati_generali().
Common codes: TD01 (standard invoice), TD04 (credit note), TD05 (debit note),
TD06 (professional fee), TD16–TD19 (reverse charge self-invoices), TD28 (San Marino).

Always succeeds. Returns {'codes': [{'code', 'description', 'use_case'}, ...], 'total': int}.

_No parameters._

## `it__archive_invoice`

Archive a signed invoice for conservazione sostitutiva. Stores the document with SHA-256 hash, timestamp, and retention metadata per AgID circolare 65/2014. Returns the archive metadata including document_id and retention_until date.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `document_base64` | string | yes |  |  |
| `format_id` | string | no | `'FatturaPA-1.2.3'` |  |
| `signer_id` | string | no | `''` |  |
| `document_id` | string | no | `''` |  |

## `it__build_pacchetto_versamento`

Build a Pacchetto di Versamento (PdV) ZIP archive containing one or more signed invoices and an XML index (IPdV). The PdV is the unit of transfer to an AgID-accredited conservazione provider.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `documents_json` | string | yes |  |  |
| `producer_id` | string | no | `''` |  |

## `it__check_sdi_status`

Check the status of a previously submitted invoice by its IdentificativoSDI. SDI communicates status asynchronously via notifications; this returns the last known local status.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `identificativo_sdi` | string | yes |  |  |

## `it__get_sdi_channel_info`

Show current SDI channel configuration: environment, channel type, channel ID, endpoint URL, and certificate status. Does not expose sensitive values (cert_password).

_No parameters._

## `it__list_archived_invoices`

List all archived invoices. Returns a list of archive metadata records sorted by archive date.

_No parameters._

## `it__parse_sdi_notification`

Parse an SDI notification XML into a structured dict. Supports all notification types: RC (delivery receipt), NS (rejection with error codes), MC (delivery failure), NE (seller outcome), EC (buyer acceptance/rejection), SE (outcome rejection), DT (deadline expiry), MT (metadata), AT (undeliverable attestation).

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `notification_xml` | string | yes |  |  |

## `it__retrieve_archived_invoice`

Retrieve an archived invoice by its document_id. Returns the document content (base64-encoded) and its archive metadata.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `document_id` | string | yes |  |  |

## `it__send_esito_committente`

Send an acceptance (EC01) or rejection (EC02) notification to SDI for a received invoice. The esito XML must conform to the NotificaEsitoCommittente schema (MessaggiTypes_v1.1.xsd). Requires confirmation (irreversible).

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `identificativo_sdi` | string | yes |  |  |
| `esito` | string | yes |  |  |
| `nome_file` | string | yes |  |  |
| `esito_xml` | string | yes |  |  |
| `confirmation_token` | string | null | no | `None` |  |

## `it__sign_fattura_cades`

Apply a CAdES-BES (CMS/PKCS#7) attached signature to a FatturaPA XML document. The output is a DER-encoded .xml.p7m file (base64-encoded in the response). Requires a qualified PKCS#12 certificate. Uses the signer microservice when available, falls back to direct signing. Requires confirmation (irreversible).

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `xml` | string | yes |  |  |
| `cert_path` | string | no | `''` |  |
| `cert_password` | string | null | no | `None` |  |
| `confirmation_token` | string | null | no | `None` |  |

## `it__sign_fattura_xades`

Apply an XAdES-BES enveloped XML signature to a FatturaPA XML document. The signed XML retains the .xml extension. Requires a qualified PKCS#12 certificate. Uses the signer microservice when available, falls back to direct signing. Requires confirmation (irreversible).

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `xml` | string | yes |  |  |
| `cert_path` | string | no | `''` |  |
| `cert_password` | string | null | no | `None` |  |
| `confirmation_token` | string | null | no | `None` |  |

## `it__submit_to_sdi`

Submit a signed FatturaPA invoice to SDI via SDICoop. The invoice must be signed (XAdES-BES or CAdES-BES) before submission. Requires mTLS certificate configuration. Returns the IdentificativoSDI assigned by SDI. Requires confirmation (irreversible).

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `signed_file_base64` | string | yes |  |  |
| `filename` | string | yes |  |  |
| `confirmation_token` | string | null | no | `None` |  |

## `it__verify_archive_integrity`

Verify the integrity of an archived document by recomputing its SHA-256 hash and comparing against the stored hash.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `document_id` | string | yes |  |  |

## `lookup_codice_destinatario`

Validate the format of a CodiceDestinatario (SDI recipient code) or PEC address.

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

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `codice` | string | null | no | `None` | SDI CodiceDestinatario to look up: 6-char alphanumeric for PA offices (IPA code, FPA12 B2G invoices), 7-char alphanumeric for B2B intermediaries (FPR12), or '0000000' (7 zeros) for PEC routing. IPA codes can be verified at https://www.indicepa.gov.it. |
| `pec` | string | null | no | `None` | PEC address to validate format (user@domain.ext). When a PEC is provided, CodiceDestinatario must be '0000000'. |

## `parse_cii_invoice`

Parse a CII CrossIndustryInvoice XML string into an EN 16931 structured dict.

Extracts the EN 16931 core field set. Italian national fields are returned
with their ItalianInvoice defaults since CII does not carry them.

Use this to inspect Factur-X / ZUGFeRD invoices, or to round-trip the output
of generate_cii_invoice() for verification.

On success returns the ItalianInvoice fields as a JSON-serialisable dict.
On failure returns {'error': str}.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `xml_string` | string | yes |  | CII CrossIndustryInvoice XML string to parse. Returns an EN 16931 field dict. National extensions are silently ignored. |

## `parse_fattura_semplificata_xml`

Parse a FatturaSemplificata XML string into a structured Python dict.

Use this to inspect simplified invoices (TD07/TD08/TD09) received from
counterparties or to verify output of generate_fattura_semplificata().

Extracts: versione, transmission data, seller identity and address, buyer
fiscal identifiers and optional address, document type/date/number, all
DatiBeniServizi entries, and DatiFatturaRettificata if present.

On success returns {'versione': str, 'header': {...}, 'body': {...}}.
On error returns {'error': '<reason>'}.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `xml_string` | string | yes |  | FatturaSemplificata XML string to parse. Accepts VFSM10 format (namespace v1.0). |

## `parse_fattura_xml`

Parse a FatturaPA XML string into a structured Python dict.

Use this to inspect or process invoices received from counterparties, or to
verify the output of generate_fattura_xml(). Accepts both FPR12 (B2B) and
FPA12 (PA) formats. The result can be passed directly to export_to_json().

Extracts: versione, transmission data, seller/buyer identity and address,
document type/date/number/causale, all DettaglioLinee, DatiRiepilogo, and
DatiPagamento if present. Fields not found in the XML are returned as null.

On success returns {'versione': str, 'header': {...}, 'body': {...}}.
On XML parse error returns {'error': 'XML parse error: <detail>'}.
On missing lxml returns {'error': 'lxml is not installed...'}.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `xml_string` | string | yes |  | FatturaPA XML string to parse. Accepts both single-invoice (FPR12) and PA-addressed (FPA12) formats. |

## `parse_ubl_invoice`

Parse a UBL 2.1 invoice XML string into an EN 16931 structured dict.

Extracts the EN 16931 core field set. Italian national fields
(progressivo_invio, regime_fiscale, etc.) are returned with their
ItalianInvoice defaults since UBL 2.1 does not carry them.

Use this to inspect cross-border invoices received in UBL format, or to
round-trip the output of generate_ubl_invoice() for verification.

On success returns the ItalianInvoice fields as a JSON-serialisable dict.
On failure returns {'error': str}.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `xml_string` | string | yes |  | UBL 2.1 Invoice or CreditNote XML string to parse. Returns an EN 16931 field dict. National extensions are silently ignored. |

## `validate_cedente_prestatore`

Validate and build the CedentePrestatore (seller) block for FatturaPA.

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

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `id_paese` | string | yes |  | ISO 3166-1 two-letter country code of the seller (e.g. 'IT'). |
| `id_codice` | string | yes |  | Partita IVA (11 digits) or foreign VAT number of the seller. |
| `codice_fiscale` | string | null | no | `None` | Codice Fiscale of the seller, optional. Set this when id_codice is a VAT-group (Gruppo IVA) IdFiscaleIVA: value must be the Codice Fiscale of the specific participating member company, never the group's own CF. Emitted as DatiAnagrafici/CodiceFiscale, between IdFiscaleIVA and Anagrafica per the XSD element order. |
| `denominazione` | string | null | no | `None` | Company name (Denominazione). Mutually exclusive with nome+cognome. |
| `nome` | string | null | no | `None` | First name (Nome), for individual sellers. |
| `cognome` | string | null | no | `None` | Last name (Cognome), for individual sellers. |
| `regime_fiscale` | string | no | `'RF01'` | Fiscal regime code RF01–RF19. Use get_regime_fiscale_codes() for the complete list. Most companies use RF01 (ordinary regime). |
| `indirizzo` | string | no | `''` | Street address (via, piazza…) of the registered office. |
| `cap` | string | no | `''` | Italian postal code (5 digits) or foreign equivalent. |
| `comune` | string | no | `''` | City/municipality of the registered office. |
| `nazione` | string | no | `'IT'` | ISO 3166-1 two-letter country code of the registered office. |

## `validate_cessionario`

Validate and build the CessionarioCommittente (buyer) block for FatturaPA.

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

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `denominazione` | string | null | no | `None` | Company name of the buyer. Mutually exclusive with nome+cognome. |
| `nome` | string | null | no | `None` | First name of the buyer (natural person). |
| `cognome` | string | null | no | `None` | Last name of the buyer (natural person). |
| `id_paese` | string | null | no | `None` | ISO country code for IdFiscaleIVA. Required for VAT-registered buyers. Omit for Italian buyers identified only by CodiceFiscale. |
| `id_codice` | string | null | no | `None` | VAT number of the buyer. Required if id_paese is provided. |
| `codice_fiscale` | string | null | no | `None` | Italian fiscal code (16-char alphanumeric for individuals, 11-digit numeric for companies). Alternative to IdFiscaleIVA. |
| `indirizzo` | string | no | `''` | Street address of the buyer. |
| `cap` | string | no | `''` | Postal code of the buyer. |
| `comune` | string | no | `''` | City of the buyer. |
| `nazione` | string | no | `'IT'` | ISO country code of the buyer. |

## `validate_cii_invoice`

Validate a CII CrossIndustryInvoice XML string for structural correctness.

Performs structural validation by parsing the XML into an EN16931Invoice
and checking that required core fields are present and non-empty.

Note: this tool does NOT validate against the normative CII D16B XSD schema.
For full schema validation use a dedicated CII or ZUGFeRD validator.

On success returns {'valid': true, 'warnings': list[str]}.
On failure returns {'valid': false, 'errors': list[str]}.
On parse error returns {'valid': false, 'errors': ['XML parse error: ...']}.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `xml_string` | string | yes |  | CII CrossIndustryInvoice XML string to validate. Must contain a root rsm:CrossIndustryInvoice element. |

## `validate_fattura_semplificata_xsd`

Validate a FatturaSemplificata XML string against the VFSM10 XSD v1.0.2.

Call this immediately after generate_fattura_semplificata() to confirm XSD
conformance. Also use to verify third-party simplified invoices.

Requires lxml. Validates namespace, element structure, data types, and cardinality.

On success returns {'valid': true, 'errors': []}.
On failure returns {'valid': false, 'errors': ['...']}.
On setup error returns {'error': '<reason>'}.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `xml_string` | string | yes |  | Complete FatturaSemplificata XML string to validate. Must include the FatturaElettronicaSemplificata root element with namespace http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.0. |

## `validate_fattura_xsd`

Validate a FatturaPA XML string against the official Agenzia delle Entrate XSD v1.2.3.

Use this as step 11 — always call immediately after generate_fattura_xml() before
storing or transmitting the document. Also use to verify third-party invoices received
from suppliers.

Automatically selects the correct XSD based on the document's `versione` attribute:
FPR12 (B2B/B2C) uses `FatturaPA_FPR12_v1.2.3.xsd`; FPA12 (B2G) uses
`FatturaPA_FPA12_v1.2.3.xsd`. FATTURA_XSD_PATH env var overrides both.

Requires lxml. Validates namespace, element structure, data types, and cardinality.

On success returns {'valid': true, 'formato_trasmissione': 'FPR12'|'FPA12', 'errors': []}.
On failure returns {'valid': false, 'errors': ['<lxml error message>', ...]}.
On setup error (missing lxml or XSD file) returns {'error': '<reason>'}.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `xml_string` | string | yes |  | Complete FatturaPA XML string to validate. Must include the FatturaElettronica root element with the correct namespace (http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2). |

## `validate_partita_iva`

Validate an Italian Partita IVA for format (11 digits) and modulo-10 checksum.

Call this as an early sanity check on the seller's VAT number before passing it to
validate_cedente_prestatore(). Strips whitespace before validation.

Applies the official Agenzia delle Entrate control algorithm: odd-position digits are
taken as-is; even-position digits are doubled (subtract 9 if > 9); the last digit must
equal (10 - sum % 10) % 10.

On success returns {'valid': true, 'value': '<cleaned_piva>'}.
On failure returns {'valid': false, 'value': '<input>', 'error': '<reason>'}.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `partita_iva` | string | yes |  | Italian Partita IVA (VAT number) to validate. Must be exactly 11 digits. Whitespace is stripped before validation. |

## `validate_partita_iva_format`

Validate an Italian Partita IVA for format (11 digits) and modulo-10 checksum.

Use this as step 1 in the invoice generation workflow before any other tool.
Equivalent to validate_partita_iva() in header tools — use this standalone version
when you only need the validation result without importing header tools.

Strips whitespace, checks for exactly 11 digits, then applies the official
Agenzia delle Entrate control algorithm to verify the check digit.

On success returns {'valid': true, 'value': '<cleaned_piva>'}.
On failure returns {'valid': false, 'value': '<input>', 'error': '<reason>'}.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `partita_iva` | string | yes |  | Italian Partita IVA (VAT number) to validate. Must be exactly 11 digits. Whitespace is stripped before validation. |

## `validate_ubl_invoice`

Validate a UBL 2.1 invoice XML string for structural correctness.

Performs structural validation by parsing the XML into an EN16931Invoice
and checking that required core fields (invoice_number, invoice_date,
seller, buyer, at least one line item) are present and non-empty.

Note: this tool does NOT validate against the normative UBL 2.1 XSD schema
(the UBL XSD files are not bundled with this package). For full XSD
validation use a dedicated UBL validator or the Peppol Validator tool.

On success returns {'valid': true, 'warnings': list[str]}.
On failure returns {'valid': false, 'errors': list[str]}.
On parse error returns {'valid': false, 'errors': ['XML parse error: ...']}.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `xml_string` | string | yes |  | UBL 2.1 Invoice or CreditNote XML string to validate. Must contain a root element in the UBL Invoice-2 or CreditNote-2 namespace. |
