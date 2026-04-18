# mcp-fattura-elettronica-it 🇮🇹
<!-- mcp-name: io.github.cmendezs/mcp-fattura-elettronica-it -->

![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)
[![PyPI version](https://img.shields.io/pypi/v/mcp-fattura-elettronica-it.svg)](https://pypi.org/project/mcp-fattura-elettronica-it/)
[![Python](https://img.shields.io/pypi/pyversions/mcp-fattura-elettronica-it.svg)](https://pypi.org/project/mcp-fattura-elettronica-it/)

Server MCP Python per la **fatturazione elettronica italiana** in formato **FatturaPA XML** (standard SDI / Agenzia delle Entrate, versione 1.6.1). Permette agli agenti IA (Claude, IDE) di generare, validare e analizzare fatture elettroniche B2B, B2G e transfrontaliere direttamente conformi alle specifiche tecniche del Sistema di Interscambio (SDI).

---

## English summary

This is a **Model Context Protocol (MCP)** server for **Italian electronic invoicing**. It exposes **21 tools** covering the full lifecycle of a FatturaPA XML document: transmission header construction, seller/buyer validation, document type codes (TD01–TD28), line items, VAT summary computation, payment terms, XSD validation against the official Agenzia delle Entrate schema (v1.6.1), XML generation, parsing, JSON export, SDI filename generation, and withholding tax (ritenuta d'acconto) calculation. The server requires no external API calls — all logic runs locally. Licensed under **Apache 2.0**.

---

## 🚀 Installazione

### Via PyPI (raccomandato)

```bash
pip install mcp-fattura-elettronica-it
```

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

---

## ⚙️ Configurazione

Il server non richiede credenziali esterne in v0.1.0. Le variabili d'ambiente disponibili sono:

| Variabile | Descrizione | Default |
|-----------|-------------|---------|
| `LOG_LEVEL` | Livello di log (`DEBUG`, `INFO`, `WARNING`, `ERROR`) | `INFO` |
| `FATTURA_XSD_PATH` | Percorso del file XSD FatturaPA | `schemas/FatturaPA_v1.6.1.xsd` |

### 🤖 Integrazione Claude Desktop

Aggiungere al file `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "fattura-elettronica-it": {
      "command": "uvx",
      "args": ["mcp-fattura-elettronica-it"]
    }
  }
}
```

### ⌨️ Integrazione Cursor

File di configurazione (`~/.cursor/mcp.json` oppure `.cursor/mcp.json` nella cartella del progetto):

```json
{
  "mcpServers": {
    "fattura-elettronica-it": {
      "command": "uvx",
      "args": ["mcp-fattura-elettronica-it"]
    }
  }
}
```

### 🪐 Integrazione Kiro

```json
{
  "mcpServers": {
    "fattura-elettronica-it": {
      "command": "uvx",
      "args": ["mcp-fattura-elettronica-it"],
      "disabled": false,
      "autoApprove": []
    }
  }
}
```

---

## 🧰 Strumenti MCP disponibili

### Header — FatturaElettronicaHeader (7 strumenti)

| Strumento | Descrizione |
|-----------|-------------|
| `build_transmission_header` | Build DatiTrasmissione block: ProgressivoInvio, CodiceDestinatario, PECDestinatario |
| `validate_cedente_prestatore` | Validate seller block: IdFiscaleIVA, Anagrafica, Sede, RegimeFiscale codes |
| `validate_cessionario` | Validate buyer block: IdFiscaleIVA or CodiceFiscale, Sede |
| `get_regime_fiscale_codes` | Return all valid RegimeFiscale codes with descriptions (RF01–RF19) |
| `validate_partita_iva` | Validate Italian VAT number (Partita IVA) format and checksum (11 digits) |
| `generate_progressivo_invio` | Generate a unique ProgressivoInvio identifier (max 10 alphanumeric chars) |
| `lookup_codice_destinatario` | Return info about a CodiceDestinatario (6-char SDI code) or PEC address |

### Body — FatturaElettronicaBody (7 strumenti)

| Strumento | Descrizione |
|-----------|-------------|
| `build_dati_generali` | Build DatiGenerali block: TipoDocumento, Divisa, Data, Numero, Causale |
| `get_tipo_documento_codes` | Return all TD01–TD28 codes with descriptions and use cases (incl. cross-border) |
| `add_linea_dettaglio` | Add a DettaglioLinee entry: NumeroLinea, Descrizione, Quantita, PrezzoUnitario |
| `compute_totali` | Compute DatiRiepilogo: imponibile, imposta, AliquotaIVA from line items |
| `get_natura_codes` | Return all Natura codes (N1–N7 and sub-codes) for VAT exemption with legal references |
| `build_dati_pagamento` | Build DatiPagamento: CondizioniPagamento (TP01/02/03), ModalitaPagamento (MP01–MP23) |
| `add_allegato` | Attach a base64-encoded document to the Allegati block with name and format |

### Globali — generazione e validazione (7 strumenti)

| Strumento | Descrizione |
|-----------|-------------|
| `generate_fattura_xml` | Generate a complete FatturaPA XML file from structured input data |
| `validate_fattura_xsd` | Validate a FatturaPA XML string against the official XSD schema v1.6.1 |
| `parse_fattura_xml` | Parse an existing FatturaPA XML string and return a structured JSON dict |
| `export_to_json` | Export a parsed FatturaPA structure to clean JSON format |
| `validate_partita_iva_format` | Validate Partita IVA format and Luhn-like checksum (11-digit Italian VAT) |
| `get_sdi_filename` | Generate the official SDI filename: IT{PartitaIVA}_{ProgressivoInvio}.xml |
| `check_ritenuta_acconto` | Check and compute ritenuta d'acconto (withholding tax) for professional invoices |

---

## Esempi di utilizzo

### Esempio 1 — Generare una fattura B2B completa

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

### Esempio 2 — Fattura professionale con ritenuta d'acconto

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

### Esempio 3 — Consultare i codici di esenzione IVA

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

---

## 📚 Standard di riferimento

| Risorsa | Link |
|---------|------|
| Specifiche FatturaPA | [fatturapa.gov.it](https://www.fatturapa.gov.it) |
| XSD ufficiale v1.6.1 | [Schema v1.2.2 — Agenzia delle Entrate](https://www.fatturapa.gov.it/it/norme-e-aggiornamenti/documentazione-fatturapa/) |
| Namespace XML | `http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2` |
| SDI — Sistema di Interscambio | [Agenzia delle Entrate](https://www.agenziaentrate.gov.it/portale/web/guest/aree-tematiche/fatturazione-elettronica) |
| Ritenuta d'acconto | Art. 25 DPR 600/73 — Modello 770 |

---

## 🧪 Test

```bash
# Installare le dipendenze di sviluppo
pip install -e ".[dev]"

# Eseguire tutti i test
pytest tests/ -v

# Eseguire solo i test di integrazione MCP
pytest tests/test_mcp_integration.py -v
```

---

## Roadmap

| Versione | Funzionalità |
|----------|--------------|
| **v0.1.0** (attuale) | Generazione XML, validazione XSD, parsing, 21 strumenti MCP, ritenuta d'acconto |
| **v0.2** | Firma digitale CAdES-BES e XAdES (smart card, HSM, P12) |
| **v0.3** | Integrazione diretta SDI via SDICoop SOAP e SFTP — invio e ricezione |
| **v0.4** | Fattura Semplificata (TD07/TD08/TD09) — importi ≤ 400 EUR |
| **v0.5** | Conservazione a norma — integrazione con provider accreditati AgID |

---

## 📄 Licenza

Questo progetto è distribuito sotto licenza **Apache 2.0**.  
Vedere il file [LICENSE](LICENSE) per i dettagli completi.

Copyright 2026 cmendezs

---

*Progetto mantenuto da [cmendezs](https://github.com/cmendezs). Per domande relative all'implementazione dello standard FatturaPA, aprire una Issue.*
