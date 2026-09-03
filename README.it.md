# mcp-fattura-elettronica-it 🇮🇹

[English](README.md) | [Italiano](README.it.md)

<!-- mcp-name: io.github.cmendezs/mcp-fattura-elettronica-it -->

![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)
[![PyPI version](https://img.shields.io/pypi/v/mcp-fattura-elettronica-it.svg)](https://pypi.org/project/mcp-fattura-elettronica-it/)
[![Python](https://img.shields.io/pypi/pyversions/mcp-fattura-elettronica-it.svg)](https://pypi.org/project/mcp-fattura-elettronica-it/) [![mcp-fattura-elettronica-it MCP server](https://glama.ai/mcp/servers/cmendezs/mcp-fattura-elettronica-it/badges/score.svg)](https://glama.ai/mcp/servers/cmendezs/mcp-fattura-elettronica-it)

---

## Introduzione

Server MCP Python per la **fatturazione elettronica italiana** in formato **FatturaPA XML** (standard SDI / Agenzia delle Entrate, XSD v1.2.3, Specifiche Tecniche 1.9.1). Permette agli agenti IA (Claude, IDE) di generare, validare e analizzare fatture elettroniche B2B, B2G e transfrontaliere direttamente conformi alle specifiche tecniche del Sistema di Interscambio (SDI). E costruito su [`mcp-einvoicing-core`](https://github.com/cmendezs/mcp-einvoicing-core), la libreria di base condivisa per i server MCP di fatturazione elettronica.

> **Nota:** le "Specifiche Tecniche" (Allegato A, il documento AdE su controlli e codifiche) e lo schema XSD sono due artefatti distinti con numerazioni indipendenti. La versione 1.9.1 delle Specifiche Tecniche (in vigore dal 15/05/2026) **non** modifica l'XSD, che resta alla v1.2.3.

Si tratta di un server **Model Context Protocol (MCP)** che espone **43 strumenti** per l'intero ciclo di vita di un documento FatturaPA XML: costruzione dell'header di trasmissione, validazione cedente/cessionario (incluso il CodiceFiscale per Gruppo IVA), codici tipo documento (TD01-TD28), righe dettaglio con supporto AltriDatiGestionali, calcolo riepilogo IVA, condizioni di pagamento, validazione XSD contro lo schema ufficiale dell'Agenzia delle Entrate (v1.2.3), generazione XML, parsing, esportazione JSON, generazione del nome file SDI, calcolo della ritenuta d'acconto, firma digitale (XAdES-BES e CAdES-BES), trasmissione diretta al SDI via SDICoop SOAP, parsing delle notifiche SDI e conservazione sostitutiva (archiviazione conforme AgID). Licenza **Apache 2.0**.

## Installazione

### Via PyPI (raccomandato)

```bash
pip install mcp-fattura-elettronica-it
```

`mcp-einvoicing-core` viene installato automaticamente come dipendenza.
Anche `lxml` è richiesto e incluso, nessun passaggio aggiuntivo necessario.

Senza installazione previa con `uvx`:

```bash
uvx mcp-fattura-elettronica-it
```

### Dalle sorgenti

```bash
git clone https://github.com/cmendezs/mcp-fattura-elettronica-it.git
cd mcp-fattura-elettronica-it

python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

pip install -e ".[dev]"
cp .env.example .env
```

## Configurazione

Le variabili d'ambiente disponibili sono:

| Variabile | Descrizione | Default |
|-----------|-------------|---------|
| `LOG_LEVEL` | Livello di log (`DEBUG`, `INFO`, `WARNING`, `ERROR`) | `INFO` |
| `FATTURA_XSD_PATH` | Percorso del file XSD FatturaPA | `schemas/FatturaPA_v1.2.3.xsd` |
| `SDI_ENVIRONMENT` | Ambiente SDI: `test` o `production` | `test` |
| `SDI_CERT_PATH` | Percorso del certificato PKCS#12 mTLS per SDI | (nessuno) |
| `SDI_CERT_PASSWORD` | Password del file PKCS#12 | (nessuno) |
| `SDI_ENDPOINT_URL` | URL endpoint SDICoop (override) | (auto da ambiente) |
| `SDI_CHANNEL_ID` | ID canale assegnato durante accreditamento AdE | (nessuno) |
| `EINVOICING_SIGNER_SOCKET` | Socket Unix per il microservizio di firma | (nessuno) |
| `EINVOICING_SIGNER_TOKEN` | Token di autenticazione per il microservizio di firma | (nessuno) |
| `CONSERVAZIONE_STORAGE_PATH` | Percorso archivio locale (solo sviluppo) | `.conservazione/` |

## Integrazione Claude Desktop

Aggiungere al file `claude_desktop_config.json`:

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

## Integrazione Cursor

Cursor supporta i server MCP via stdio. Aggiungere la configurazione in:
- **Globale** (tutti i progetti): `~/.cursor/mcp.json`
- **Progetto** (solo questo repository): `.cursor/mcp.json`

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

Ricaricare la finestra di Cursor (`Ctrl+Shift+P` poi *Reload Window*) per applicare le modifiche.

## Integrazione Kiro

Kiro supporta i server MCP tramite il proprio file di configurazione dedicato. Due livelli sono disponibili:
- **Globale** (tutti i progetti): `~/.kiro/settings/mcp.json`
- **Workspace** (solo questo repository): `.kiro/settings/mcp.json`

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

Il file viene ricaricato automaticamente al salvataggio. È anche possibile aprire la configurazione dalla command palette (`Cmd+Shift+P` / `Ctrl+Shift+P`) e poi *MCP*.

> **Suggerimento di sicurezza Kiro**: invece di scrivere i segreti in chiaro, usare la sintassi `"SDI_CERT_PASSWORD": "${SDI_CERT_PASSWORD}"`, Kiro risolve le variabili d'ambiente della shell all'avvio.

## Strumenti disponibili

### Header: FatturaElettronicaHeader (7 strumenti)

| Strumento | Descrizione |
|-----------|-------------|
| `build_transmission_header` | Build DatiTrasmissione block: ProgressivoInvio, CodiceDestinatario, PECDestinatario |
| `validate_cedente_prestatore` | Validate seller block: IdFiscaleIVA, optional Gruppo IVA member CodiceFiscale, Anagrafica, Sede, RegimeFiscale codes |
| `validate_cessionario` | Validate buyer block: IdFiscaleIVA or CodiceFiscale, Sede (warns on the structural precondition of scarto code 00327 for Gruppo IVA) |
| `get_regime_fiscale_codes` | Return all valid RegimeFiscale codes with descriptions (RF01-RF19) |
| `validate_partita_iva` | Validate Italian VAT number (Partita IVA) format and checksum (11 digits) |
| `generate_progressivo_invio` | Generate a unique ProgressivoInvio identifier (max 10 alphanumeric chars) |
| `lookup_codice_destinatario` | Return info about a CodiceDestinatario (6-char SDI code) or PEC address (300-code max per accredited channel, Specifiche Tecniche 1.9.1) |

### Body: FatturaElettronicaBody (8 strumenti)

| Strumento | Descrizione |
|-----------|-------------|
| `build_dati_generali` | Build DatiGenerali block: TipoDocumento, Divisa, Data, Numero, Causale |
| `get_tipo_documento_codes` | Return all TD01-TD28 codes with descriptions and use cases (incl. cross-border) |
| `add_linea_dettaglio` | Add a DettaglioLinee entry: NumeroLinea, Descrizione, Quantita, PrezzoUnitario, optional AltriDatiGestionali |
| `build_sport_worker_exemption_dato_gestionale` | Build the AltriDatiGestionali entry for the sport-worker IRPEF exemption (TipoDato='ESENZSPORT', Specifiche Tecniche 1.9.1) |
| `compute_totali` | Compute DatiRiepilogo: imponibile, imposta, AliquotaIVA from line items |
| `get_natura_codes` | Return all Natura codes (N1-N7 and sub-codes) for VAT exemption with legal references |
| `build_dati_pagamento` | Build DatiPagamento: CondizioniPagamento (TP01/02/03), ModalitaPagamento (MP01-MP23) |
| `add_allegato` | Attach a base64-encoded document to the Allegati block with name and format |

### Globali: generazione e validazione (7 strumenti)

| Strumento | Descrizione |
|-----------|-------------|
| `generate_fattura_xml` | Generate a complete FatturaPA XML file from structured input data |
| `validate_fattura_xsd` | Validate a FatturaPA XML string against the official XSD schema v1.2.3 |
| `parse_fattura_xml` | Parse an existing FatturaPA XML string and return a structured JSON dict |
| `export_to_json` | Export a parsed FatturaPA structure to clean JSON format |
| `validate_partita_iva_format` | Validate Partita IVA format and Luhn-like checksum (11-digit Italian VAT) |
| `get_sdi_filename` | Generate the official SDI filename: IT{PartitaIVA}_{ProgressivoInvio}.xml |
| `check_ritenuta_acconto` | Check and compute ritenuta d'acconto (withholding tax) for professional invoices |

### Firma digitale (2 strumenti)

| Strumento | Descrizione |
|-----------|-------------|
| `sign_fattura_xades` | Firma XAdES-BES enveloped XML (.xml). Richiede certificato PKCS#12. |
| `sign_fattura_cades` | Firma CAdES-BES CMS/PKCS#7 (.xml.p7m). Richiede certificato PKCS#12. |

### Integrazione SDI (5 strumenti)

| Strumento | Descrizione |
|-----------|-------------|
| `submit_to_sdi` | Invia fattura firmata al SDI via SDICoop SOAP (mTLS) |
| `check_sdi_status` | Verifica stato invio tramite IdentificativoSDI |
| `parse_sdi_notification` | Parsing notifiche SDI (RC/NS/MC/NE/EC/SE/DT/MT/AT); i codici di scarto noti (es. 00327, CodiceFiscale di Gruppo IVA) includono una `reference_note` supplementare |
| `send_esito_committente` | Invia accettazione (EC01) o rifiuto (EC02) al SDI |
| `get_sdi_channel_info` | Mostra configurazione canale SDI |

### Conservazione sostitutiva (5 strumenti)

| Strumento | Descrizione |
|-----------|-------------|
| `archive_invoice` | Archivia fattura firmata con hash SHA-256 e conservazione 10 anni |
| `retrieve_archived_invoice` | Recupera documento archiviato tramite ID |
| `verify_archive_integrity` | Verifica integrita hash SHA-256 |
| `list_archived_invoices` | Elenco fatture archiviate |
| `build_pacchetto_versamento` | Costruisci PdV ZIP per trasferimento a conservatore accreditato AgID |

### Esempi di utilizzo

**Esempio 1: Generare una fattura B2B completa**

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

10. generate_fattura_xml(...tutti i blocchi precedenti...)
    → { "xml": "<?xml ...", "filename": "IT01234567897_00001.xml" }

11. validate_fattura_xsd(xml_string=...)
    → { "valid": true }
```

**Esempio 2: Fattura professionale con ritenuta d'acconto**

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

**Esempio 3: Consultare i codici di esenzione IVA**

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

## Architettura

```
mcp-fattura-elettronica-it (questo pacchetto, server MCP standalone)
├── ItalyPartyValidator(BasePartyValidator)   ← Partita IVA modulo-10
├── FatturaGenerator(BaseDocumentGenerator)   ← FatturaPA XML v1.2.3
├── FatturaValidator(BaseDocumentValidator)   ← lxml XSD v1.2.3
└── FatturaParser(BaseDocumentParser)         ← lxml xpath

        ↑ estende
mcp-einvoicing-core (base condivisa, installata come dipendenza)
├── BaseDocumentGenerator / Validator / Parser / PartyValidator
├── InvoiceDocument, InvoiceParty, InvoiceLineItem … (Pydantic)
├── xml_utils, logging_utils, exceptions
└── EInvoicingMCPServer (aggregatore multi-paese opzionale)
```

## Standard supportati

| Risorsa | Link |
|---------|------|
| Specifiche FatturaPA | [fatturapa.gov.it](https://www.fatturapa.gov.it) |
| XSD ufficiale v1.2.3 | [Schema v1.2.2, Agenzia delle Entrate](https://www.fatturapa.gov.it/it/norme-e-aggiornamenti/documentazione-fatturapa/) |
| Specifiche Tecniche (Allegato A) 1.9.1, in vigore dal 15/05/2026 | [Agenzia delle Entrate](https://www.agenziaentrate.gov.it/portale/specifiche-tecniche-versione-1.9.1-%C2%A0-utilizzabili-dal-15-maggio-2026-) — artefatto distinto dall'XSD, che non modifica |
| Namespace XML | `http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2` |
| SDI, Sistema di Interscambio | [Agenzia delle Entrate](https://www.agenziaentrate.gov.it/portale/web/guest/aree-tematiche/fatturazione-elettronica) |
| Ritenuta d'acconto | Art. 25 DPR 600/73, Modello 770 |

## Test

```bash
# Installare le dipendenze di sviluppo
pip install -e ".[dev]"

# Eseguire tutti i test
pytest tests/ -v

# Eseguire solo i test di integrazione MCP
pytest tests/test_mcp_integration.py -v
```

## Contribuire

I contributi sono benvenuti — vedere [CONTRIBUTING.md](CONTRIBUTING.md) per le linee guida.

## Altri server MCP per la fatturazione elettronica

| Paese | Server |
|-------|--------|
| 🌍 Globale | [mcp-einvoicing-core](https://github.com/cmendezs/mcp-einvoicing-core) |
| 🇧🇪 Belgio | [mcp-einvoicing-be](https://github.com/cmendezs/mcp-einvoicing-be) |
| 🇧🇷 Brasile | [mcp-nfe-br](https://github.com/cmendezs/mcp-nfe-br) |
| 🇫🇷 Francia | [mcp-facture-electronique-fr](https://github.com/cmendezs/mcp-facture-electronique-fr) |
| 🇩🇪 Germania | [mcp-einvoicing-de](https://github.com/cmendezs/mcp-einvoicing-de) |
| 🇮🇹 Italia | [mcp-fattura-elettronica-it](https://github.com/cmendezs/mcp-fattura-elettronica-it) |
| 🇲🇽 Messico | [mcp-cfdi-mx](https://github.com/cmendezs/mcp-cfdi-mx) |
| 🇵🇱 Polonia | [mcp-ksef-pl](https://github.com/cmendezs/mcp-ksef-pl) |
| 🇸🇬 Singapore | [mcp-invoicenow-sg](https://github.com/cmendezs/mcp-invoicenow-sg) |
| 🇪🇸 Spagna | [mcp-facturacion-electronica-es](https://github.com/cmendezs/mcp-facturacion-electronica-es) |
| 🇦🇪 Emirati Arabi Uniti | [mcp-einvoicing-ae](https://github.com/cmendezs/mcp-einvoicing-ae) |

## Licenza

Questo progetto è distribuito sotto licenza **Apache 2.0**. Vedere il file [LICENSE](LICENSE) per i dettagli completi. Per la cronologia completa delle versioni, vedere [CHANGELOG.md](CHANGELOG.md).
