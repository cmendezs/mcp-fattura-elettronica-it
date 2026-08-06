# specs — mcp-fattura-elettronica-it

Reference documents for the Italian FatturaPA / SdI electronic invoicing package.
All files sourced from Agenzia delle Entrate (AdE) official publications.
Retrieved: 2026-05-21.

---

## XSD schemas (active — in `../schemas/`)

The XSD files are stored in `../schemas/` so the validator can load them without
path gymnastics. This directory holds the non-schema specs only.

| File | Version | Format | Source URL | Retrieved |
|---|---|---|---|---|
| `../schemas/FatturaPA_FPR12_v1.2.3.xsd` | 1.2.3 | FPR12 (B2B/B2C) | https://www.fatturapa.gov.it | 2026-05-21 |
| `../schemas/FatturaPA_FPA12_v1.2.3.xsd` | 1.2.3 | FPA12 (B2G/PA) | https://www.fatturapa.gov.it | 2026-05-21 |
| `../schemas/FatturaSemplificata_VFSM10_v1.0.2.xsd` | 1.0.2 | VFSM10 (simplified invoice) | https://www.fatturapa.gov.it | 2026-05-21 |

**Namespace note:** FPR12 and FPA12 share namespace
`http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2`. The simplified invoice
format (VFSM10, covering TD07/TD08/TD09) uses a separate namespace
`http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.0` and is a distinct XML
format; it cannot be validated against the ordinary invoice XSD.

**Schema content note:** `FatturaPA_FPR12_v1.2.3.xsd` and `FatturaPA_FPA12_v1.2.3.xsd`
are byte-identical — the ordinary FatturaPA schema does not itself distinguish FPR12
from FPA12. The two `FormatoTrasmissione` values differ only in SdI business rules
(e.g. the 6-char IPA `CodiceDestinatario` required for FPA12), not in XSD structure.
Both files are kept bundled under separate names so format-keyed schema lookup
(`_get_xsd_path`) stays simple, and so the audit gate's schema-presence check
(CHECK 5b) continues to verify both.

---

## Technical specifications

| File | Description | Version | Source | Retrieved |
|---|---|---|---|---|
| `Specifiche-tecniche-relative-al-Sistema-di-Interscambio-versione-1.8.4.pdf` | SdI technical specification — submission endpoints, notification types, file format rules | 1.8.4 | AdE / fatturapa.gov.it | 2026-05-21 |
| `Specifiche_tecniche_del_formato_FatturaPA_V1.4.pdf` | FatturaPA XML format specification (older reference; v1.4) | 1.4 | AdE | 2026-05-21 |
| `Specifiche-Tecniche-Fatturazione-Europea-v2.6.pdf` | European e-invoicing technical specification — EN 16931 / UBL / CII interoperability | 2.6 | AdE | 2026-05-21 |

---

## Presentation materials

| File | Description | Format |
|---|---|---|
| `RappresentazioneTabellareFattOrdinaria-1.pdf` | Tabular reference for ordinary FatturaPA elements | PDF |
| `RappresentazioneTabellareFattSemplificata-1.pdf` | Tabular reference for simplified invoice (FatturaSemplificata) elements | PDF |
| `Foglio_di_stile_fatturaPA_v1.2.3.xsl` | XSL stylesheet for rendering ordinary FatturaPA XML (v1.2.3) | XSL |
| `Foglio_di_stile_fattura_ordinaria_ver1.2.3.xsl` | XSL stylesheet for ordinary invoice (v1.2.3, alternate) | XSL |
| `Foglio_di_stile_VFSM10_v1.0.2.xsl` | XSL stylesheet for simplified invoice VFSM10 (v1.0.2) | XSL |

---

## Version history note

The FatturaPA ordinary invoice XSD was at **v1.2.2** when this package was first
scaffolded. The current mandatory version is **v1.2.3**, which adds TD29
(Comunicazione per omessa o irregolare fatturazione, art. 6 c.8 D.Lgs. 471/97).
The XML namespace (`http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2`)
is unchanged between 1.2.2 and 1.2.3.

There is no FatturaPA version "1.6.1". All references to that label in code comments
or docstrings are erroneous and have been corrected to "1.2.3".

---

## SDICoop endpoint URLs — unresolved (IT-LC-5)

`sdi/config.py:75` carries `[NEED: verify SDICoop test/production endpoint URLs from AdE
accreditation portal]` for the hardcoded defaults `https://testservizi.fatturapa.it/ricevi_fatture`
(test) and `https://servizi.fatturapa.it/ricevi_fatture` (production).

Checked 2026-08-06 against the bundled `Specifiche-tecniche-relative-al-Sistema-di-Interscambio-
versione-1.8.4.pdf`: the document describes the SdICoop web-service model (SOAP/HTTPS, WSDL) at a
conceptual level (§3.1.2, §3.2.2) but explicitly defers the actual endpoint URLs and WSDL contracts
to separate documents — "Istruzioni per il servizio SDICoop - Trasmissione" and "... - Ricezione" —
published on the AdE accreditation portal, which is not bundled in `specs/`. No endpoint URL string
appears anywhere in the PDF.

**Result: not confirmed.** The `[NEED: verify]` marker in `sdi/config.py` stays in place. Resolving
this requires either downloading the "Istruzioni per il servizio SDICoop" documents from the AdE
accreditation portal, or verified confirmation from an accredited SDI channel operator.

---

## No public SdI API

SdI does not expose a public Swagger/OpenAPI endpoint. Connectivity to production is
via accredited SOAP web services, SFTP, or PEC. Accreditation requires registration
of your endpoint and certificate with AdE. The `Specifiche-tecniche-relative-al-
Sistema-di-Interscambio-versione-1.8.4.pdf` describes the SOAP interface in detail.
