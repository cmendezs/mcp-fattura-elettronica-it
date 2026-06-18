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

### v0.3.0
#### Changed
- `ItalianInvoice(EN16931Invoice)` subclass scaffolded in `models.py`; `FatturaGenerator`
  updated to use EN 16931 field names throughout. **[IT-SC-7] resolved.**

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
