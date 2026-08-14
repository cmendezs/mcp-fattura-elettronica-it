# Release Process for mcp-fattura-elettronica-it

This document outlines the complete workflow for releasing new versions to PyPI and the MCP registry.

## One-Time Setup Requirements

**GitHub Actions — PyPI Trusted Publishing:**
PyPI publishing is fully automated via OIDC (no token stored). The Trusted Publisher is configured on PyPI under `cmendezs/mcp-fattura-elettronica-it`, workflow `publish.yml`, environment `pypi`. No `.env` or secret needed.

**MCP Publisher CLI:**
Binary installed at `~/.local/bin/mcp-publisher` (already in `PATH`). To update to a newer version:
```bash
curl -L "https://github.com/modelcontextprotocol/registry/releases/latest/download/mcp-publisher_darwin_arm64.tar.gz" \
  | tar xzf - -C ~/.local/bin/
```

**MCP Registry Authentication:**
Authenticate once with GitHub (device flow):
```bash
mcp-publisher login github
```

## Release Workflow

**Step 1 — Version Bump:**
Update the version in `pyproject.toml` and `server.json`:
```toml
# pyproject.toml
version = "X.Y.Z"
```
```json
// server.json
"version": "X.Y.Z",
"packages": [{ "version": "X.Y.Z", ... }]
```

**Step 2 — Commit, Tag and Push:**
GitHub Actions publishes to PyPI automatically on tag push.
```bash
git add pyproject.toml server.json
git commit -m "bump: version X.Y.Z"
git push origin main
git tag vX.Y.Z
git push origin vX.Y.Z
```

**Step 3 — MCP Registry Publication:**
```bash
mcp-publisher publish
```

## Changelog

### v0.7.0 — 2026-08-14
#### Added
- AltriDatiGestionali (DettaglioLinee) emission: new `AltriDatiGestionaliEntry`
  model, `altri_dati_gestionali` parameter on `add_linea_dettaglio`, and
  `build_sport_worker_exemption_dato_gestionale` tool for the sport-worker
  IRPEF exemption codifica (`TipoDato='ESENZSPORT'`, verified against AdE
  Allegato A — Specifiche Tecniche 1.9.1). Wired into `generate_fattura_xml`
  and `FatturaGenerator`. Regulatory-watch closure.
- Gruppo IVA (VAT-group) `CodiceFiscale` support alongside `IdFiscaleIVA`, for
  both CedentePrestatore (seller) and CessionarioCommittente (buyer): new
  `codice_fiscale` parameter on `validate_cedente_prestatore`; documented
  Gruppo IVA use in `validate_cessionario`; new `cedente_codice_fiscale` /
  `cessionario_codice_fiscale` fields on `ItalianInvoice`. `validate_cessionario`
  now returns a `warnings` entry when the structural precondition of scarto
  code 00327 is detected (buyer `IdFiscaleIVA` absent + 11-digit `CodiceFiscale`).
- `SCARTO_CODE_REFERENCE` static lookup table in `sdi/notifications.py`
  (currently covers 00327); `SDIErrore.reference_note` supplements the SdI's
  own `<Descrizione>` text when the code is catalogued.
- Server now exposes 43 tools (was 42).
#### Changed
- Server instructions, tool docstrings, `README.md`/`README.it.md`, and
  `server.json` updated from stale/conflated FatturaPA version references to
  distinguish the XSD (unchanged, v1.2.3) from the AdE Specifiche Tecniche
  (Allegato A), now 1.9.1, in force 2026-05-15. Fixed `tools/__init__.py`
  mislabeled version string.
- `lookup_codice_destinatario` docstring documents the 300-code maximum per
  accredited reception channel (Specifiche Tecniche 1.9.1); the per-invoice
  6/7-character format validation is unchanged.
#### Investigation
- **[Step 1 verification, this release]** Confirmed against the AdE Allegato
  A — Specifiche Tecniche 1.9.1 PDF (changelog entry dated 31/03/2026, in
  force 2026-05-15): (1) `AltriDatiGestionali/TipoDato = "ESENZSPORT"` for the
  sport-worker exemption (D.Lgs. 36/2021 art. 36, comma 6, EUR 15,000/year
  threshold) — no `RiferimentoTesto`/`RiferimentoNumero` mandated; (2)
  `CodiceDestinatario` cap is 300 codes per accredited channel; (3) scarto
  code 00327 fires when the buyer's `IdFiscaleIVA` is absent and the supplied
  `CodiceFiscale` is a VAT group's own CF rather than a participating
  member's. All three verified from the primary source; no placeholders
  needed.

### v0.6.0 — 2026-08-07
#### Fixed
- `<Imponibile>` renamed to `<ImponibileImporto>` in all emitted and parsed
  XML; the previous element name did not match the FatturaPA XSD, so
  generated invoices failed schema validation. **[IT-SC-19] resolved, BLOCKING.**
- Removed the invalid `<CodiceUfficio>` element/field from PA-destined
  invoices; added correct 6-char IPA `CodiceDestinatario` validation for
  FPA12. **[IT-SC-20] resolved, BLOCKING.**
- SdI notification parsing made namespace-robust via local-name matching,
  no longer brittle to prefix variation. **[IT-SC-22] resolved.**
- `identificativo_sdi` now always present as a snake_case key in SOAP
  response parsing. **[IT-LC-4] resolved.**
- XML-escaping applied to header fields previously interpolated raw.
  **[IT-SH-4] resolved.**
- Removed orphan, mislabeled `FatturaPA_v1.6.1.xsd` (no such version exists;
  content was actually v1.2.2).
#### Added
- UNCL5305-to-Natura exemption code resolution (`natura.py`), with an
  explicit-code escape hatch for ambiguous categories. **[IT-SC-21] resolved.**
- Permanent audit-gate regression check that generates and XSD-validates a
  canonical FPR12/FPA12 invoice on every gate run. **[IT-AG-1] resolved.**
- Multi-body FPA12 XML parsing support (`bodies` list). **[IT-LC-3] resolved.**
- Non-standard IT VAT rate now returned as a caller-visible warning, not
  just logged. **[IT-TL-5] resolved.**
#### Changed
- Strengthened test assertions across the suite so a schema-invalid
  document can no longer pass silently. **[IT-TC-1] resolved.**
#### Investigation
- **[IT-LC-5]** SDICoop endpoint URLs: checked against the bundled SdI
  technical spec (v1.8.4); endpoint URLs are deferred to separate
  "Istruzioni per il servizio SDICoop" documents on the AdE accreditation
  portal, not bundled in `specs/`. `[NEED: verify]` marker retained in
  `sdi/config.py`.

### v0.5.0 — 2026-06-29
#### Added
- IT-SIGN-1: XAdES-BES and CAdES-BES digital signatures (2 tools: `it__sign_fattura_xades`, `it__sign_fattura_cades`). Dual mode: signer microservice or direct PKCS#12.
- IT-SDI-1: Direct SDI integration via SDICoop SOAP with mTLS (5 tools: `it__submit_to_sdi`, `it__check_sdi_status`, `it__parse_sdi_notification`, `it__send_esito_committente`, `it__get_sdi_channel_info`). Full notification parser for all 9 SDI notification types.
- IT-ARCH-1: Conservazione sostitutiva per AgID circolare 65/2014 (5 tools: `it__archive_invoice`, `it__retrieve_archived_invoice`, `it__verify_archive_integrity`, `it__list_archived_invoices`, `it__build_pacchetto_versamento`). Local filesystem backend for dev; PdV ZIP assembly.
- Server now exposes 42 tools (was 30).
#### Changed
- Core dependency updated to `mcp-einvoicing-core>=1.12.0,<2.0.0` (was >=1.1.0).

### v0.2.5 — 2026-05-31
#### Added
- `generate_ubl_invoice` tool — serialises an `ItalianInvoice` dict to UBL 2.1
  Invoice/CreditNote XML using `EN16931UBLSerializer` from core v1.3.0.
  **[IT-SC-15] resolved.**
- `generate_cii_invoice` tool — serialises an `ItalianInvoice` dict to CII
  CrossIndustryInvoice XML using `EN16931CIISerializer`. Suitable for Factur-X
  and ZUGFeRD-compatible output. **[IT-SC-16] resolved.**
- `validate_ubl_invoice` and `parse_ubl_invoice` tools. **[IT-SC-17] resolved.**
- `validate_cii_invoice` and `parse_cii_invoice` tools. **[IT-SC-18] resolved.**
- Server now exposes 27 tools (was 21).
#### Fixed
- CI: retagged `v0.2.5` to include `publish.yml` YAML fix (bare `python -c` →
  `run: |` heredoc).
- `server.json` description shortened to 86 chars (registry 100-char limit).

### v0.3.0 — 2026-06-28
#### Added
- `additional_bodies` parameter on `generate_fattura_xml` for FPA12 batch invoicing
  (multiple `<FatturaElettronicaBody>` per envelope). **[IT-SC-14] resolved.**
- Codice Fiscale validation in `validate_cessionario` using core
  `TaxIdentifier.validate_it_codice_fiscale` (16-char) and `validate_it_partita_iva`
  (11-digit company format). **[IT-TL-3] resolved.**
- Informational VAT rate warning in `add_linea_dettaglio` when rate is non-zero
  and outside {4, 5, 10, 22}. **[IT-TL-4] resolved.**
- SdI lifecycle scope boundary documented in server instructions. **[IT-LC-2] resolved.**
- Server now exposes 30 tools (was 27).
#### Changed
- `ItalianInvoice` transmission fields (`progressivo_invio`, `codice_destinatario`,
  `formato_trasmissione`) no longer have defaults; callers must set them explicitly.
  Wire-format parsers supply defaults when parsing UBL/CII. **[IT-SC-6] resolved.**
- Belgian Peppol URN removed from `models.py` docstring; no FatturaPA profile URN
  exists (verified against AdE spec v1.4 and EU Regole tecniche v2.6).
  **[IT-SH-2] and [IT-INV-2] resolved.**
#### Investigation
- **[IT-INV-1]** Codice Fiscale validator: confirmed stale `[NEED:]` marker; core
  validator now used in `validate_cessionario`.
- **[IT-INV-2]** FatturaPA profile URN: no URN exists; CIUS-IT defined by BR-IT
  rules, not a URN. XSD namespace is the format identifier.
- **[IT-INV-3]** Rounding mode: ROUND_HALF_UP confirmed correct; AdE spec is
  silent on rounding mode.

### v0.2.3
#### Fixed
- XML escaping via `xml_escape` applied to all free-text fields in
  `generate_fattura_xml` and `FatturaGenerator.generate()`. **[IT-SH-1] resolved.**
- Obsolete Natura codes N2, N3, N6 removed from `NATURA_CODES`
  (invalid since Jan 2021 XSD update). **[IT-TL-2] resolved.**
- `aliquota_override` / `importo_override` optional params added to
  `check_ritenuta_acconto` for RT06. **[IT-TL-1] resolved.**
- `PECDestinatario` emitted when `codice_destinatario='0000000'`; error raised
  if `pec_destinatario` is absent. **[IT-LC-1] resolved.**

### v0.2.0 — 2026-04-19

#### Changed
- Refactored internals to extend `mcp-einvoicing-core>=0.1.0`
  (logging utils, XML utils — `format_amount`, `format_quantity`, `validate_date_iso`,
  `validate_iban`, `filter_empty_values` — now imported from the shared core)
- No changes to public MCP tool names or signatures
- `lxml` remains a direct dependency (required for XSD validation, deliberately excluded from core)

#### Added
- `mcp-einvoicing-core` listed as explicit dependency in `pyproject.toml`
- `tools/adapters.py`: IT-specific adapter classes extending core base abstractions:
  `FatturaGenerator`, `FatturaValidator`, `FatturaParser`, `ItalyPartyValidator`
- Architecture diagram in `README.md` showing the core dependency hierarchy
- `[tool.uv.sources]` in `pyproject.toml` for local development against the core source tree

---

## Critical Notes

- The MCP registry does **not** sync automatically with PyPI or GitHub — each release requires a manual `mcp-publisher publish`.
- The `description` field in `server.json` must stay **≤ 100 characters**.
- PyPI rejects re-uploads of the same version — always bump before tagging.
- GitHub Actions creates the GitHub Release automatically (with release notes) alongside the PyPI publish.
