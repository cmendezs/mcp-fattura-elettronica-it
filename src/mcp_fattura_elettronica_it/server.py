"""
Entry point for the MCP server mcp-fattura-elettronica-it.

Exposes 21 tools for generating, validating, and analysing Italian electronic
invoices in FatturaPA XML format (SDI / Agenzia delle Entrate standard v1.2.3).

Usage:
    python server.py                    # stdio mode (Claude Desktop / claude.ai/code)
    fastmcp dev server.py               # development mode with inspector
    fastmcp install server.py           # install in Claude Desktop
"""

from __future__ import annotations

from mcp_einvoicing_core import EInvoicingMCPServer
from mcp_einvoicing_core.logging_utils import get_logger, setup_logging

from mcp_fattura_elettronica_it.tools.body_tools import register_body_tools
from mcp_fattura_elettronica_it.tools.global_tools import register_global_tools
from mcp_fattura_elettronica_it.tools.header_tools import register_header_tools
from mcp_fattura_elettronica_it.tools.simplified_tools import register_simplified_tools
from mcp_fattura_elettronica_it.tools.wire_format_tools import register_wire_format_tools

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

setup_logging()
logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Server initialisation
# ---------------------------------------------------------------------------

_server = EInvoicingMCPServer(
    name="mcp-fattura-elettronica-it",
    instructions=(
        "MCP server for Italian electronic invoicing (FatturaPA v1.2.3 / SDI). "
        "Generates, validates, and analyses e-invoices for B2B, B2G, and cross-border "
        "transactions compliant with Agenzia delle Entrate specifications.\n\n"
        "**Header tools** — FatturaElettronicaHeader (6 tools):\n"
        "  • build_transmission_header: Build DatiTrasmissione block (SDI routing)\n"
        "  • validate_cedente_prestatore: Validate seller block (tax ID, address, regime)\n"
        "  • validate_cessionario: Validate buyer block (tax ID or CodiceFiscale)\n"
        "  • get_regime_fiscale_codes: List all RegimeFiscale codes RF01–RF19\n"
        "  • generate_progressivo_invio: Generate a unique ProgressivoInvio sequence\n"
        "  • lookup_codice_destinatario: Validate SDI recipient code or PEC address\n\n"
        "**Body tools** — FatturaElettronicaBody (7 tools):\n"
        "  • build_dati_generali: Build DatiGenerali (type TD01–TD28, date, number)\n"
        "  • get_tipo_documento_codes: List all document type codes TD01–TD28\n"
        "  • add_linea_dettaglio: Add a DettaglioLinee line item\n"
        "  • compute_totali: Compute DatiRiepilogo VAT summary from line items\n"
        "  • get_natura_codes: List all Natura exemption codes (N1–N7 and sub-codes)\n"
        "  • build_dati_pagamento: Build DatiPagamento (terms TP01/02/03, method MP01–MP23)\n"
        "  • add_allegato: Attach a base64-encoded file to the invoice\n\n"
        "**Global tools** — generation and validation (7 tools):\n"
        "  • generate_fattura_xml: Assemble a complete FatturaPA XML document\n"
        "  • validate_fattura_xsd: Validate XML against the official XSD v1.2.3\n"
        "  • parse_fattura_xml: Parse an existing FatturaPA XML into structured JSON\n"
        "  • export_to_json: Export parsed invoice to clean JSON format\n"
        "  • validate_partita_iva_format: Standalone Partita IVA format + checksum check\n"
        "  • get_sdi_filename: Generate the SDI filename IT{PIVA}_{Progressivo}.xml\n"
        "  • check_ritenuta_acconto: Compute withholding tax (ritenuta d'acconto) RT01–RT06\n\n"
        "**Recommended workflow for generating a new invoice:**\n"
        "1. validate_partita_iva_format(seller_piva) → verify seller VAT number\n"
        "2. generate_progressivo_invio() → get a unique sequence number\n"
        "3. build_transmission_header(...) → DatiTrasmissione\n"
        "4. validate_cedente_prestatore(...) → seller block\n"
        "5. validate_cessionario(...) → buyer block\n"
        "6. build_dati_generali(tipo_documento='TD01', ...) → DatiGenerali\n"
        "7. add_linea_dettaglio(...) × N → line items\n"
        "8. compute_totali(linee) → DatiRiepilogo\n"
        "9. build_dati_pagamento(...) → DatiPagamento\n"
        "10. generate_fattura_xml(...) → XML string + SDI filename\n"
        "11. validate_fattura_xsd(xml) → XSD conformance check\n\n"
        "**Simplified invoice tools** — FatturaSemplificata VFSM10 (3 tools):\n"
        "  • generate_fattura_semplificata: Assemble TD07/TD08/TD09 simplified invoice XML\n"
        "  • validate_fattura_semplificata_xsd: Validate against VFSM10 XSD v1.0.2\n"
        "  • parse_fattura_semplificata_xml: Parse a simplified invoice XML into structured dict\n\n"
        "**Wire-format tools** — EN 16931 UBL 2.1 and CII (6 tools):\n"
        "  • generate_ubl_invoice: ItalianInvoice → UBL 2.1 Invoice XML (cross-border / Peppol)\n"
        "  • generate_cii_invoice: ItalianInvoice → CII CrossIndustryInvoice XML (Factur-X / ZUGFeRD)\n"
        "  • validate_ubl_invoice: Structural validation of UBL 2.1 XML\n"
        "  • parse_ubl_invoice: UBL 2.1 XML → EN 16931 field dict\n"
        "  • validate_cii_invoice: Structural validation of CII XML\n"
        "  • parse_cii_invoice: CII XML → EN 16931 field dict\n\n"
        "**Scope boundary:** This server covers FatturaPA XML generation, XSD validation, "
        "and parsing. SdI submission and notification handling are out of scope for v0.3.x. "
        "Direct SDI integration (SDICoop SOAP + SFTP) is planned for v0.4.0 under IT-SDI-1.\n\n"
        "Out of scope v0.3.x: digital signature (CAdES/XAdES), direct SDI transmission.\n"
        "XSD: FatturaPA v1.2.3 — namespace http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2"
    ),
)
mcp = _server.mcp

# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

register_header_tools(mcp)
register_body_tools(mcp)
register_global_tools(mcp)
register_simplified_tools(mcp)
register_wire_format_tools(mcp)

logger.info(
    "MCP server 'mcp-fattura-elettronica-it' initialised — "
    "7 Header + 7 Body + 7 Global + 3 Simplified + 6 Wire-format = 30 tools"
)

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Start the MCP server in stdio mode."""
    _server.run()


if __name__ == "__main__":
    main()
