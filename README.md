# mcp-fattura-elettronica-it 🇮🇹

[English](README.md) | [Italiano](README.it.md)

<!-- mcp-name: io.github.cmendezs/mcp-fattura-elettronica-it -->

![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)
[![PyPI version](https://img.shields.io/pypi/v/mcp-fattura-elettronica-it.svg)](https://pypi.org/project/mcp-fattura-elettronica-it/)
[![Python](https://img.shields.io/pypi/pyversions/mcp-fattura-elettronica-it.svg)](https://pypi.org/project/mcp-fattura-elettronica-it/) [![mcp-fattura-elettronica-it MCP server](https://glama.ai/mcp/servers/cmendezs/mcp-fattura-elettronica-it/badges/score.svg)](https://glama.ai/mcp/servers/cmendezs/mcp-fattura-elettronica-it)
[![Listed in italia-mcp-servers](https://img.shields.io/badge/listed%20in-italia--mcp--servers-blue)](https://github.com/bsab/italia-mcp-servers)

---

## Introduction

A Python MCP server for **Italian electronic invoicing** in **FatturaPA XML** format (SDI / Agenzia delle Entrate standard, XSD v1.2.3, Specifiche Tecniche 1.9.1). It enables AI agents (Claude, IDEs) to generate, validate, and analyze B2B, B2G, and cross-border electronic invoices that are directly compliant with the technical specifications of the Sistema di Interscambio (SDI). It is built on [`mcp-einvoicing-core`](https://github.com/cmendezs/mcp-einvoicing-core), the shared base library for e-invoicing MCP servers.

> **Note:** "Specifiche Tecniche" (the AdE Allegato A controls/codifiche document) and the XSD schema are two separate artefacts with independent version numbers. Specifiche Tecniche 1.9.1 (in force 2026-05-15) does **not** change the XSD — the bundled schema remains v1.2.3.

This is a **Model Context Protocol (MCP)** server exposing **43 tools** covering the full lifecycle of a FatturaPA XML document: transmission header construction, seller/buyer validation (including Gruppo IVA / VAT-group CodiceFiscale), document type codes (TD01-TD28), line items with AltriDatiGestionali support, VAT summary computation, payment terms, XSD validation against the official Agenzia delle Entrate schema (v1.2.3), XML generation, parsing, JSON export, SDI filename generation, withholding tax (ritenuta d'acconto) calculation, digital signatures (XAdES-BES and CAdES-BES), direct SDI transmission via SDICoop SOAP, SDI notification parsing, and conservazione sostitutiva (legally compliant archiving per AgID). Licensed under **Apache 2.0**.

## Installation

### Via PyPI (recommended)

```bash
pip install mcp-fattura-elettronica-it
```

`mcp-einvoicing-core` is installed automatically as a dependency.
`lxml` is also required and included, so no extra steps are needed.

Without prior installation, using `uvx`:

```bash
uvx mcp-fattura-elettronica-it
```

### From source

```bash
git clone https://github.com/cmendezs/mcp-fattura-elettronica-it.git
cd mcp-fattura-elettronica-it

python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

pip install -e ".[dev]"
cp .env.example .env
```

## Configuration

The available environment variables are:

| Variable | Description | Default |
|----------|-------------|---------|
| `LOG_LEVEL` | Log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) | `INFO` |
| `FATTURA_XSD_PATH` | Path to the FatturaPA XSD file | `schemas/FatturaPA_v1.2.3.xsd` |
| `SDI_ENVIRONMENT` | SDI environment: `test` or `production` | `test` |
| `SDI_CERT_PATH` | Path to the PKCS#12 mTLS certificate for SDI | (none) |
| `SDI_CERT_PASSWORD` | Passphrase for the PKCS#12 file | (none) |
| `SDI_ENDPOINT_URL` | SDICoop endpoint URL override | (auto from environment) |
| `SDI_CHANNEL_ID` | Channel ID assigned during AdE accreditation | (none) |
| `EINVOICING_SIGNER_SOCKET` | Unix socket for the signer microservice | (none) |
| `EINVOICING_SIGNER_TOKEN` | Auth token for the signer microservice | (none) |
| `CONSERVAZIONE_STORAGE_PATH` | Local archive storage path (dev only) | `.conservazione/` |

## Claude Desktop integration

Add the following to your `claude_desktop_config.json` file:

```json
{
  "mcpServers": {
    "fattura-elettronica-it": {
      "command": "uvx",
      "args": ["mcp-fattura-elettronica-it"],
      "env": {
        "SDI_ENVIRONMENT": "test",
        "SDI_CERT_PATH": "/path/to/your-cert.p12",
        "SDI_CERT_PASSWORD": "your-cert-password",
        "SDI_CHANNEL_ID": "your-channel-id"
      }
    }
  }
}
```

## Cursor integration

Cursor supports MCP servers via stdio. Add the configuration in:
- **Global** (all projects): `~/.cursor/mcp.json`
- **Project** (this repository only): `.cursor/mcp.json`

```json
{
  "mcpServers": {
    "fattura-elettronica-it": {
      "command": "uvx",
      "args": ["mcp-fattura-elettronica-it"],
      "env": {
        "SDI_ENVIRONMENT": "test",
        "SDI_CERT_PATH": "/path/to/your-cert.p12",
        "SDI_CERT_PASSWORD": "your-cert-password",
        "SDI_CHANNEL_ID": "your-channel-id"
      }
    }
  }
}
```

Reload the Cursor window (`Ctrl+Shift+P` then *Reload Window*) to apply the changes.

## Kiro integration

Kiro supports MCP servers via its dedicated configuration file. Two levels are available:
- **Global** (all projects): `~/.kiro/settings/mcp.json`
- **Workspace** (this repository only): `.kiro/settings/mcp.json`

```json
{
  "mcpServers": {
    "fattura-elettronica-it": {
      "command": "uvx",
      "args": ["mcp-fattura-elettronica-it"],
      "env": {
        "SDI_ENVIRONMENT": "test",
        "SDI_CERT_PATH": "/path/to/your-cert.p12",
        "SDI_CERT_PASSWORD": "your-cert-password",
        "SDI_CHANNEL_ID": "your-channel-id"
      },
      "disabled": false,
      "autoApprove": []
    }
  }
}
```

The file is automatically reloaded on save. You can also open the config via the command palette (`Cmd+Shift+P` / `Ctrl+Shift+P`) then *MCP*.

> **Kiro security tip**: rather than writing secrets in plain text, use the syntax `"SDI_CERT_PASSWORD": "${SDI_CERT_PASSWORD}"`, Kiro resolves shell environment variables at startup.

## Available tools

### Header: FatturaElettronicaHeader (7 tools)

| Tool | Description |
|------|-------------|
| `build_transmission_header` | Build DatiTrasmissione block: ProgressivoInvio, CodiceDestinatario, PECDestinatario |
| `validate_cedente_prestatore` | Validate seller block: IdFiscaleIVA, optional Gruppo IVA member CodiceFiscale, Anagrafica, Sede, RegimeFiscale codes |
| `validate_cessionario` | Validate buyer block: IdFiscaleIVA or CodiceFiscale, Sede (warns on the structural precondition of scarto code 00327 for Gruppo IVA) |
| `get_regime_fiscale_codes` | Return all valid RegimeFiscale codes with descriptions (RF01-RF19) |
| `validate_partita_iva` | Validate Italian VAT number (Partita IVA) format and checksum (11 digits) |
| `generate_progressivo_invio` | Generate a unique ProgressivoInvio identifier (max 10 alphanumeric chars) |
| `lookup_codice_destinatario` | Return info about a CodiceDestinatario (6-char SDI code) or PEC address (300-code max per accredited channel, Specifiche Tecniche 1.9.1) |

### Body: FatturaElettronicaBody (8 tools)

| Tool | Description |
|------|-------------|
| `build_dati_generali` | Build DatiGenerali block: TipoDocumento, Divisa, Data, Numero, Causale |
| `get_tipo_documento_codes` | Return all TD01-TD28 codes with descriptions and use cases (incl. cross-border) |
| `add_linea_dettaglio` | Add a DettaglioLinee entry: NumeroLinea, Descrizione, Quantita, PrezzoUnitario, optional AltriDatiGestionali |
| `build_sport_worker_exemption_dato_gestionale` | Build the AltriDatiGestionali entry for the sport-worker IRPEF exemption (TipoDato='ESENZSPORT', Specifiche Tecniche 1.9.1) |
| `compute_totali` | Compute DatiRiepilogo: imponibile, imposta, AliquotaIVA from line items |
| `get_natura_codes` | Return all Natura codes (N1-N7 and sub-codes) for VAT exemption with legal references |
| `build_dati_pagamento` | Build DatiPagamento: CondizioniPagamento (TP01/02/03), ModalitaPagamento (MP01-MP23) |
| `add_allegato` | Attach a base64-encoded document to the Allegati block with name and format |

### Global: generation and validation (7 tools)

| Tool | Description |
|------|-------------|
| `generate_fattura_xml` | Generate a complete FatturaPA XML file from structured input data |
| `validate_fattura_xsd` | Validate a FatturaPA XML string against the official XSD schema v1.2.3 |
| `parse_fattura_xml` | Parse an existing FatturaPA XML string and return a structured JSON dict |
| `export_to_json` | Export a parsed FatturaPA structure to clean JSON format |
| `validate_partita_iva_format` | Validate Partita IVA format and Luhn-like checksum (11-digit Italian VAT) |
| `get_sdi_filename` | Generate the official SDI filename: IT{PartitaIVA}_{ProgressivoInvio}.xml |
| `check_ritenuta_acconto` | Check and compute ritenuta d'acconto (withholding tax) for professional invoices |

### Simplified invoices: FatturaSemplificata VFSM10 (3 tools)

| Tool | Description |
|------|-------------|
| `generate_fattura_semplificata` | Generate a simplified invoice XML (TD07/TD08/TD09) using VFSM10 format |
| `validate_fattura_semplificata_xsd` | Validate a simplified invoice XML against the VFSM10 XSD v1.0.2 |
| `parse_fattura_semplificata_xml` | Parse a simplified invoice XML into a structured dict |

Simplified invoices (art. 21-bis DPR 633/72) are valid for transactions up to EUR 400
(tax-inclusive). They use a flatter structure than ordinary FatturaPA: no per-line VAT
breakdown, no DatiRiepilogo. Each `DatiBeniServizi` entry carries its own `Descrizione`,
`Importo`, and `DatiIVA`. The VFSM10 format uses namespace `v1.0` and is separate from
the EN 16931 CIUS used by ordinary invoices.

### Digital signatures (2 tools)

| Tool | Description |
|------|-------------|
| `sign_fattura_xades` | Apply XAdES-BES enveloped XML signature (.xml). Requires PKCS#12 cert. |
| `sign_fattura_cades` | Apply CAdES-BES CMS/PKCS#7 attached signature (.xml.p7m). Requires PKCS#12 cert. |

Both signature formats are accepted by SDI (Specifiche tecniche SDI v1.8.4, section 2.1).
Supports dual mode: signer microservice (keeps keys out of the MCP process) or direct PKCS#12 loading.
Requires `cryptography>=42.0.0` (installed via the `[xml-sign]` extra on `mcp-einvoicing-core`).

### SDI integration (5 tools)

| Tool | Description |
|------|-------------|
| `submit_to_sdi` | Submit a signed invoice to SDI via SDICoop SOAP (mTLS) |
| `check_sdi_status` | Check submission status by IdentificativoSDI |
| `parse_sdi_notification` | Parse SDI notification XML (RC/NS/MC/NE/EC/SE/DT/MT/AT); known scarto codes (e.g. 00327, Gruppo IVA CodiceFiscale) include a supplementary `reference_note` |
| `send_esito_committente` | Send acceptance (EC01) or rejection (EC02) to SDI |
| `get_sdi_channel_info` | Show current SDI channel configuration |

Requires AdE accreditation for production use. Configure via `SDI_CERT_PATH`, `SDI_CERT_PASSWORD`,
`SDI_ENVIRONMENT` (test/production), and `SDI_ENDPOINT_URL` (override) environment variables.

### Conservazione sostitutiva / archiving (5 tools)

| Tool | Description |
|------|-------------|
| `archive_invoice` | Archive a signed invoice with SHA-256 hash and 10-year retention |
| `retrieve_archived_invoice` | Retrieve an archived document by ID |
| `verify_archive_integrity` | Verify SHA-256 hash integrity of an archived document |
| `list_archived_invoices` | List all archived invoices |
| `build_pacchetto_versamento` | Build a PdV ZIP archive for transfer to an AgID-accredited conservator |

Per AgID circolare 65/2014 and DM 17/06/2014, electronic invoices must be archived for
a minimum of 10 years. The local filesystem backend is for development only; production
requires integration with an AgID-accredited conservazione provider.

### Usage examples

**Example 1: Generate a complete B2B invoice**

```
1. validate_partita_iva_format("01234567897")
   → { "valid": true }

2. generate_progressivo_invio(sequence=1)
   → { "progressivo_invio": "00001" }

3. build_transmission_header(id_paese="IT", id_codice="01234567897",
     progressivo_invio="00001", formato_trasmissione="FPR12",
     codice_destinatario="ABC123")

4. validate_cedente_prestatore(id_paese="IT", id_codice="01234567897",
     denominazione="ACME Srl", regime_fiscale="RF01",
     indirizzo="Via Roma 1", cap="00100", comune="Roma", nazione="IT")

5. validate_cessionario(denominazione="Buyer Srl",
     id_paese="IT", id_codice="98765432109",
     indirizzo="Via Verdi 2", cap="20100", comune="Milano")

6. build_dati_generali(tipo_documento="TD01", data="2026-01-15",
     numero="2026/001", divisa="EUR")

7. add_linea_dettaglio(numero_linea=1, descrizione="Consulenza informatica",
     quantita=8, unita_misura="ORE", prezzo_unitario=100.0,
     prezzo_totale=800.0, aliquota_iva=22.0)

8. compute_totali(linee=[{"prezzo_totale": 800.0, "aliquota_iva": 22.0}])
   → { "totale_fattura": "976.00" }

9. build_dati_pagamento(condizioni_pagamento="TP02", modalita_pagamento="MP05",
     importo_pagamento=976.0, iban="IT60X0542811101000000123456")

10. generate_fattura_xml(...all previous blocks...)
    → { "xml": "<?xml ...", "filename": "IT01234567897_00001.xml" }

11. validate_fattura_xsd(xml_string=...)
    → { "valid": true }
```

**Example 2: Professional invoice with withholding tax**

```
check_ritenuta_acconto(imponibile=1000.0, tipo_ritenuta="RT02",
  causale_pagamento="A")
→ {
    "DatiRitenuta": {
      "TipoRitenuta": "RT02",
      "ImportoRitenuta": "200.00",
      "AliquotaRitenuta": "20.00",
      "CausalePagamento": "A"
    },
    "importo_ritenuta": "200.00"
  }
```

**Example 3: Look up VAT exemption codes**

```
get_natura_codes()
→ codes: [
    { "code": "N3.1", "description": "Non imponibili — esportazioni",
      "legal_ref": "Art. 8 DPR 633/72" },
    { "code": "N6.1", "description": "Inversione contabile — rottami",
      "legal_ref": "Art. 74 c. 7-8 DPR 633/72" },
    ...
  ]
```

## Architecture

```
mcp-fattura-elettronica-it (this package, standalone MCP server)
├── ItalyPartyValidator(BasePartyValidator)   ← Partita IVA modulo-10
├── FatturaGenerator(BaseDocumentGenerator)   ← FatturaPA XML v1.2.3
├── FatturaValidator(BaseDocumentValidator)   ← lxml XSD v1.2.3
└── FatturaParser(BaseDocumentParser)         ← lxml xpath

        ↑ extends
mcp-einvoicing-core (shared foundation, installed as dependency)
├── BaseDocumentGenerator / Validator / Parser / PartyValidator
├── InvoiceDocument, InvoiceParty, InvoiceLineItem … (Pydantic)
├── xml_utils, logging_utils, exceptions
└── EInvoicingMCPServer (optional multi-country aggregator)
```

## Supported standards

| Resource | Link |
|----------|------|
| FatturaPA specifications | [fatturapa.gov.it](https://www.fatturapa.gov.it) |
| Official XSD v1.2.3 | [Schema v1.2.2, Agenzia delle Entrate](https://www.fatturapa.gov.it/it/norme-e-aggiornamenti/documentazione-fatturapa/) |
| Specifiche Tecniche (Allegato A) 1.9.1, in force 2026-05-15 | [Agenzia delle Entrate](https://www.agenziaentrate.gov.it/portale/specifiche-tecniche-versione-1.9.1-%C2%A0-utilizzabili-dal-15-maggio-2026-) — separate artefact from the XSD; does not change it |
| XML namespace | `http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2` |
| SDI, Sistema di Interscambio | [Agenzia delle Entrate](https://www.agenziaentrate.gov.it/portale/web/guest/aree-tematiche/fatturazione-elettronica) |
| Withholding tax (ritenuta d'acconto) | Art. 25 DPR 600/73, Modello 770 |

## Tests

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run all tests
pytest tests/ -v

# Run only MCP integration tests
pytest tests/test_mcp_integration.py -v
```

## Contributing

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## Other e-invoicing MCP servers

| Country | Server |
|---------|--------|
| 🌍 Global | [mcp-einvoicing-core](https://github.com/cmendezs/mcp-einvoicing-core) |
| 🇧🇪 Belgium | [mcp-einvoicing-be](https://github.com/cmendezs/mcp-einvoicing-be) |
| 🇧🇷 Brazil | [mcp-nfe-br](https://github.com/cmendezs/mcp-nfe-br) |
| 🇫🇷 France | [mcp-facture-electronique-fr](https://github.com/cmendezs/mcp-facture-electronique-fr) |
| 🇩🇪 Germany | [mcp-einvoicing-de](https://github.com/cmendezs/mcp-einvoicing-de) |
| 🇮🇹 Italy | [mcp-fattura-elettronica-it](https://github.com/cmendezs/mcp-fattura-elettronica-it) |
| 🇲🇽 Mexico | [mcp-cfdi-mx](https://github.com/cmendezs/mcp-cfdi-mx) |
| 🇵🇱 Poland | [mcp-ksef-pl](https://github.com/cmendezs/mcp-ksef-pl) |
| 🇸🇬 Singapore | [mcp-invoicenow-sg](https://github.com/cmendezs/mcp-invoicenow-sg) |
| 🇪🇸 Spain | [mcp-facturacion-electronica-es](https://github.com/cmendezs/mcp-facturacion-electronica-es) |
| 🇦🇪 United Arab Emirates | [mcp-einvoicing-ae](https://github.com/cmendezs/mcp-einvoicing-ae) |

## License

This project is distributed under the **Apache 2.0** license. See the [LICENSE](LICENSE) file for full details. For the full version history, see [CHANGELOG.md](CHANGELOG.md).
