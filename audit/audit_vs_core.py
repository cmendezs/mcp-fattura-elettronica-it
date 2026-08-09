"""Pre-publish audit: verify mcp-fattura-elettronica-it coherence against mcp-einvoicing-core.

Run standalone (from the workspace root):
    uv run python mcp-fattura-elettronica-it/audit/audit_vs_core.py
    uv run python mcp-fattura-elettronica-it/audit/audit_vs_core.py --output mcp-fattura-elettronica-it/audit/report.json
    uv run python mcp-fattura-elettronica-it/audit/audit_vs_core.py --fail-on blocking
    uv run python mcp-fattura-elettronica-it/audit/audit_vs_core.py --fail-on warnings

Exit codes:
    0  All checks passed
    1  Warnings only (non-blocking)
    2  Blocking failures found

This script is designed to be importable with no side effects; all execution
is guarded by `if __name__ == "__main__"`.

CHECK 1 and CHECK 4 are delegated to mcp_einvoicing_core.audit.
CHECK 2 (tool registry), CHECK 3 (EN16931Invoice field coverage), and CHECK 5
(IT-specific structural) are implemented here.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from mcp_einvoicing_core.audit import (
    SEVERITY_BLOCKING,
    SEVERITY_OK,
    SEVERITY_WARNING,
    AuditReport,
    CheckFinding,
    CheckResult,
    _try_import,
    make_report,
    parse_audit_args,
    render_summary_table,
    run_check_core_coverage,
    run_check_version_compatibility,
)

_PKG_DIR = Path(__file__).parent.parent

# ---------------------------------------------------------------------------
# CHECK 1 configuration — country-specific constants
# ---------------------------------------------------------------------------

# FatturaPA v1.2.3 is an Italian CIUS of EN 16931-1:2017 (confirmed by AdE
# mapping document and the profile URN urn:cen.eu:en16931:2017#conformant#...).
# IT-SC-7 scaffolded ItalianInvoice(EN16931Invoice) in models.py; FatturaGenerator
# still accepts InvoiceDocument during the migration period.
_IS_EN16931_FAMILY: bool = True
_PRIMARY_INVOICE_CLASS: tuple[str, str] = ("mcp_fattura_elettronica_it.models", "ItalianInvoice")

_INTENTIONAL_OVERRIDES: dict[str, set[str]] = {
    # IT uses EInvoicingMCPServer; the following are internal helpers or lifecycle
    # ABC not needed in country tool handlers. InvoiceDocument/InvoiceParty/
    # TaxIdValidationResult are cross-module re-exports of core.models symbols
    # (IT uses ItalianInvoice(EN16931Invoice), not the InvoiceDocument tree).
    # ABC/Any/BaseModel/FastMCP/Field/Generic/TypeVar/abstractmethod are
    # stdlib/Pydantic/FastMCP imports used internally by base_server.py itself.
    "mcp_einvoicing_core.base_server": {
        "assert_not_read_only",
        "BaseLifecycleManager",
        "SubmitResult",
        "InvoiceDocument",
        "InvoiceParty",
        "TaxIdValidationResult",
        "ABC",
        "Any",
        "BaseModel",
        "FastMCP",
        "Field",
        "Generic",
        "TypeVar",
        "abstractmethod",
    },
    # XAdES signing is out of scope for v0.2.x (FatturaPA uses XAdES only for
    # PA channel enrollment, not invoice signing). CAdES signing IS implemented
    # (tools/signing_tools.py: SignerClient microservice, or CAdESSigner/
    # CAdESSignerConfig via a function-local import when no signer microservice
    # is configured) — CHECK 1's module-level scan cannot see that lazy import,
    # so CAdESSigner/CAdESSignerConfig are listed here despite being used.
    # ABC/abstractmethod/dataclass/datetime/field/timezone are stdlib imports
    # used internally by digital_signature.py itself.
    "mcp_einvoicing_core.digital_signature": {
        "BaseDocumentSigner",
        "XAdESEPESSigner",
        "XAdESSignerConfig",
        # OVERRIDE-REASON: XMLDSigSigner/XMLDSigSignerConfig (core v1.4.0) is
        # the BR NF-e plain enveloped XML-DSig signer; not applicable to
        # FatturaPA, which is signed via CAdES (PKCS#7) before SDI submission
        "XMLDSigSigner",
        "XMLDSigSignerConfig",
        # OVERRIDE-REASON: used via a function-local import in signing_tools.py
        # to avoid loading the crypto dependency chain unless a local cert path
        # is supplied; CHECK 1 only scans module-level attributes.
        "CAdESSigner",
        "CAdESSignerConfig",
        # OVERRIDE-REASON: load_certificate_der (core v1.16.0) is a helper for
        # country packages building custom auth claims from a cert's public
        # bytes (e.g. ES FACe's JWS "username" claim); IT has no such flow.
        "load_certificate_der",
        "ABC",
        "abstractmethod",
        "dataclass",
        "datetime",
        "field",
        "timezone",
    },
    # FatturaPA artefacts (XSD schemas) are bundled in schemas/ and do not
    # use the download_rules framework. Path/dataclass/entry_points/field are
    # stdlib imports used internally by download_rules.py; main is its CLI
    # entrypoint, not part of the importable surface.
    "mcp_einvoicing_core.download_rules": {
        "DownloadSpec",
        "download_artefacts",
        "Path",
        "dataclass",
        "entry_points",
        "field",
        "main",
    },
    # EN16931Party and EN16931LineItem not yet subclassed (IT-SC-7 in progress).
    # ItalianInvoice(EN16931Invoice) is scaffolded; sub-models (address, allowance,
    # payment means, tax) are deferred to IT-SC-7 completion.
    # BaseModel/Decimal/Field/date/field_validator/model_validator are
    # stdlib/Pydantic imports used internally by en16931.py itself.
    "mcp_einvoicing_core.en16931": {
        "EN16931Party",
        "EN16931LineItem",
        "EN16931Address",
        "EN16931AllowanceCharge",
        "EN16931PaymentMeans",
        "EN16931Tax",
        "BaseModel",
        "Decimal",
        "Field",
        "date",
        "field_validator",
        "model_validator",
    },
    # FatturaPA tool handlers return {'error': ...} dicts; core exception types
    # are not yet raised directly from IT tool code.
    "mcp_einvoicing_core.exceptions": {
        "EInvoicingError",
        "PlatformError",
        "ValidationError",
        "AuthError",
        "AuthenticationError",
        "DocumentGenerationError",
        "PartyValidationError",
        "SchematronValidationError",
        "XSDValidationError",
    },
    # No clearance API in FatturaPA v0.2.x — no SDI submission, no OAuth2 tokens.
    # AuthenticationError is a cross-module re-export of exceptions.AuthenticationError,
    # already excluded above for the same reason. BaseEInvoicingConfig is unused —
    # IT's own sdi/config.py defines its BaseSettings config directly. Any/BaseModel/
    # BaseSettings/Enum/Field/Path/field_validator/parsedate_to_datetime/urlparse are
    # stdlib/Pydantic imports used internally by http_client.py itself.
    "mcp_einvoicing_core.http_client": {
        "BaseEInvoicingClient",
        "OAuthValues",
        "OAuthConfig",
        "TokenCache",
        "AuthenticationError",
        "BaseEInvoicingConfig",
        # OVERRIDE-REASON: JWSConfig (core v1.16.0) configures RS256/x5c JWT
        # auth for platforms like ES FACe; no such auth mode in IT's SDI flows.
        "JWSConfig",
        "Any",
        "BaseModel",
        "BaseSettings",
        "Enum",
        "Field",
        "Path",
        "field_validator",
        "parsedate_to_datetime",
        "urlparse",
    },
    # InvoiceDocument sub-models not yet used in the flat-layout IT tools.
    # FatturaGenerator maps from InvoiceDocument top-level fields directly.
    # InvoiceDocument itself is unused too — IT's primary model is
    # ItalianInvoice(EN16931Invoice), not the InvoiceDocument tree.
    # BaseModel/Decimal/Field/field_validator/model_validator are stdlib/Pydantic
    # imports used internally by models.py itself.
    "mcp_einvoicing_core.models": {
        "InvoiceDocument",
        "InvoiceParty",
        "InvoiceLineItem",
        "InvoiceTaxLine",
        "InvoicePaymentMeans",
        "TaxIdValidationResult",
        "PaymentTerms",
        "VATSummary",
        "PartyAddress",
        "BaseModel",
        "Decimal",
        "Field",
        "field_validator",
        "model_validator",
    },
    # Peppol not used in FatturaPA B2B/B2G flows.
    # UBL 2.1/Peppol support blocked on IT-CORE-1 (no core UBL serialisers).
    # Enum/dataclass/field are stdlib imports used internally by peppol.py itself.
    "mcp_einvoicing_core.peppol": {
        "PeppolParticipantId",
        "PeppolSMPClient",
        "PeppolEnvironment",
        "PeppolLookupResult",
        "PeppolServiceInfo",
        "Enum",
        "dataclass",
        "field",
    },
    # PDF/A-3 embedding not required by FatturaPA (XML-only format).
    "mcp_einvoicing_core.pdf": {
        "PDFEmbedder",
    },
    # Profile registry not used; FatturaPA uses a fixed XSD namespace.
    # dataclass is a stdlib import used internally by profile_registry.py itself.
    "mcp_einvoicing_core.profile_registry": {
        "ProfileRegistry",
        "set_profile_registry",
        "ProfileEntry",
        "dataclass",
    },
    # QR codes not required by FatturaPA spec.
    "mcp_einvoicing_core.qr": {
        "generate_qr_png_base64",
    },
    # Schematron not used; FatturaPA uses XSD-only validation.
    # BaseXSDValidator is available but FatturaValidator extends BaseDocumentValidator
    # directly with its own lxml-based XSD check. get_xslt_version and
    # load_schematron_validator are Schematron/SVRL-only helpers, also unused.
    # ABC/Path/abstractmethod/dataclass/field are stdlib imports used internally
    # by schematron.py itself.
    "mcp_einvoicing_core.schematron": {
        "SchematronValidator",
        "BaseStructuredValidator",
        "BaseXSDValidator",
        "BaseJSONValidator",
        "ValidationMessage",
        "ValidationResult",
        "SaxonSchematronValidator",
        "get_xslt_version",
        "load_schematron_validator",
        "ABC",
        "Path",
        "abstractmethod",
        "dataclass",
        "field",
    },
    # IT tools use template-string XML generation; xml_element/xml_optional/
    # xml_escape produce per-element fragments not needed with the current approach.
    # resolve_xml_input and mark_untrusted* are security helpers for user-supplied
    # XML — not yet wired into parse_fattura_xml (planned for security hardening).
    # Any/Decimal are stdlib/typing imports used internally by xml_utils.py itself.
    "mcp_einvoicing_core.xml_utils": {
        "xml_element",
        "xml_optional",
        "xml_escape",
        "resolve_xml_input",
        "mark_untrusted",
        "mark_untrusted_fields",
        "format_error",
        "Any",
        "Decimal",
    },
}

_PKG_MODULES: list[str] = [
    "mcp_fattura_elettronica_it.server",
    "mcp_fattura_elettronica_it.models",
    "mcp_fattura_elettronica_it.natura",
    "mcp_fattura_elettronica_it.archive.conservazione",
    "mcp_fattura_elettronica_it.sdi.client",
    "mcp_fattura_elettronica_it.sdi.lifecycle",
    "mcp_fattura_elettronica_it.sdi.notifications",
    "mcp_fattura_elettronica_it.sdi.soap",
    "mcp_fattura_elettronica_it.tools.header_tools",
    "mcp_fattura_elettronica_it.tools.body_tools",
    "mcp_fattura_elettronica_it.tools.global_tools",
    "mcp_fattura_elettronica_it.tools.adapters",
    "mcp_fattura_elettronica_it.tools.archive_tools",
    "mcp_fattura_elettronica_it.tools.sdi_tools",
    "mcp_fattura_elettronica_it.tools.signing_tools",
    "mcp_fattura_elettronica_it.tools.simplified_tools",
    "mcp_fattura_elettronica_it.tools.wire_format_tools",
]

_PYPROJECT = Path(__file__).parent.parent / "pyproject.toml"


# ---------------------------------------------------------------------------
# CHECK 2 — Tool registry completeness
# ---------------------------------------------------------------------------

_REQUIRED_TOOLS: dict[str, str] = {
    # Header tools (7)
    "build_transmission_header":   "Build DatiTrasmissione block (SDI routing)",
    "validate_cedente_prestatore": "Validate seller block (tax ID, address, regime)",
    "validate_cessionario":        "Validate buyer block (tax ID, CodiceFiscale)",
    "get_regime_fiscale_codes":    "List all RegimeFiscale codes RF01-RF19",
    "generate_progressivo_invio":  "Generate a unique ProgressivoInvio sequence",
    "lookup_codice_destinatario":  "Validate SDI recipient code (6/7-char) or PEC address",
    "validate_partita_iva":        "Validate Italian Partita IVA (modulo-10 checksum)",
    # Body tools (7)
    "build_dati_generali":         "Build DatiGenerali (TD01-TD29, date, number, currency)",
    "get_tipo_documento_codes":    "List all document type codes TD01-TD29",
    "add_linea_dettaglio":         "Add a DettaglioLinee line item",
    "compute_totali":              "Compute DatiRiepilogo VAT summary from line items",
    "get_natura_codes":            "List all Natura exemption codes (N1-N7 and sub-codes)",
    "build_dati_pagamento":        "Build DatiPagamento (TP01/02/03, MP01-MP23)",
    "add_allegato":                "Attach a base64-encoded file to the invoice",
    # Global tools (7)
    "generate_fattura_xml":        "Assemble a complete FatturaPA v1.2.3 XML document",
    "validate_fattura_xsd":        "Validate XML against FatturaPA XSD (FPR12 or FPA12)",
    "parse_fattura_xml":           "Parse a FatturaPA XML into structured JSON",
    "export_to_json":              "Export parsed invoice to clean JSON format",
    "validate_partita_iva_format": "Standalone Partita IVA format and checksum check",
    "get_sdi_filename":            "Generate the SDI filename IT{PIVA}_{Progressivo}.xml",
    "check_ritenuta_acconto":      "Compute ritenuta d'acconto RT01-RT06",
}


def _collect_registered_tools() -> set[str]:
    import asyncio
    registered: set[str] = set()
    try:
        from fastmcp import FastMCP as _FastMCP
        from mcp_fattura_elettronica_it.tools.body_tools import register_body_tools
        from mcp_fattura_elettronica_it.tools.global_tools import register_global_tools
        from mcp_fattura_elettronica_it.tools.header_tools import register_header_tools

        test_mcp = _FastMCP("it-audit-test")
        register_header_tools(test_mcp)
        register_body_tools(test_mcp)
        register_global_tools(test_mcp)

        registered = {t.name for t in asyncio.run(test_mcp.list_tools())}
    except Exception:
        pass
    return registered


def run_check_2() -> CheckResult:
    """CHECK 2 — Tool registry completeness."""
    result = CheckResult(check_id="CHECK_2", name="Tool registry completeness")
    registered = _collect_registered_tools()

    for tool_name, description in _REQUIRED_TOOLS.items():
        tag = "[OK]" if tool_name in registered else "[MISSING_TOOL]"
        sev = SEVERITY_OK if tool_name in registered else SEVERITY_BLOCKING
        result.findings.append(CheckFinding(
            check_id="CHECK_2", tag=tag, severity=sev,
            symbol=tool_name,
            message=(
                f"Tool '{tool_name}' is present. ({description})"
                if tool_name in registered
                else (
                    f"Required tool '{tool_name}' ({description}) not found. "
                    "Ensure it is decorated with @mcp.tool."
                )
            ),
        ))
    for tool_name in sorted(registered - set(_REQUIRED_TOOLS)):
        result.findings.append(CheckFinding(
            check_id="CHECK_2", tag="[EXTRA]", severity=SEVERITY_OK,
            symbol=tool_name,
            message=f"Tool '{tool_name}' is present but not in the required spec.",
        ))
    return result


# ---------------------------------------------------------------------------
# CHECK 3 — EN16931Invoice field availability
# ---------------------------------------------------------------------------

_REQUIRED_EN16931_FIELDS: dict[str, str] = {
    "invoice_number": "BT-1  — Invoice number",
    "invoice_date":   "BT-2  — Invoice issue date",
    "currency_code":  "BT-5  — Invoice currency code",
    "seller":         "BG-4  — Seller party",
    "buyer":          "BG-7  — Buyer party",
    "line_items":     "BG-25 — Invoice line items",
    "tax_lines":      "BG-23 — Tax breakdown",
}


def run_check_3() -> CheckResult:
    """CHECK 3 — EN16931Invoice field availability (IT is EN 16931 CIUS)."""
    result = CheckResult(check_id="CHECK_3", name="EN16931Invoice field availability")
    core_mod, err = _try_import("mcp_einvoicing_core.en16931")
    if core_mod is None:
        result.skipped = True
        result.skip_reason = f"Could not import mcp_einvoicing_core.en16931: {err}"
        return result

    invoice_cls = getattr(core_mod, "EN16931Invoice", None)
    if invoice_cls is None:
        result.findings.append(CheckFinding(
            check_id="CHECK_3", tag="[MISSING]", severity=SEVERITY_BLOCKING,
            symbol="mcp_einvoicing_core.en16931.EN16931Invoice",
            message="EN16931Invoice not found in core — core may be outdated.",
        ))
        return result

    result.findings.append(CheckFinding(
        check_id="CHECK_3", tag="[OK]", severity=SEVERITY_OK,
        symbol="mcp_einvoicing_core.en16931.EN16931Invoice",
        message="EN16931Invoice is available from core.",
    ))

    model_fields: set[str] = (
        set(invoice_cls.model_fields.keys())
        if hasattr(invoice_cls, "model_fields")
        else set()
    )
    for field_name, description in _REQUIRED_EN16931_FIELDS.items():
        tag = "[OK]" if field_name in model_fields else "[FIELD_MISSING]"
        sev = SEVERITY_OK if field_name in model_fields else SEVERITY_WARNING
        result.findings.append(CheckFinding(
            check_id="CHECK_3", tag=tag, severity=sev,
            symbol=f"EN16931Invoice.{field_name}",
            message=(
                f"Required field present. {description}"
                if field_name in model_fields
                else (
                    f"Field '{field_name}' ({description}) not found in EN16931Invoice. "
                    "Verify ItalianInvoice subclass will not fail at runtime."
                )
            ),
        ))
    return result


# ---------------------------------------------------------------------------
# CHECK 5 — FatturaPA-specific structural checks
# ---------------------------------------------------------------------------

def run_check_5() -> CheckResult:
    """CHECK 5 — FatturaPA-specific structural and schema checks."""
    result = CheckResult(check_id="CHECK_5", name="FatturaPA-specific structural checks")

    # 5a: server module exports main and mcp
    server_mod, err = _try_import("mcp_fattura_elettronica_it.server")
    if server_mod is None:
        result.findings.append(CheckFinding(
            check_id="CHECK_5", tag="[MISSING]", severity=SEVERITY_BLOCKING,
            symbol="server",
            message=f"Could not import server module: {err}",
        ))
    else:
        for attr in ("main", "mcp"):
            tag = "[OK]" if hasattr(server_mod, attr) else "[MISSING]"
            sev = SEVERITY_OK if hasattr(server_mod, attr) else SEVERITY_BLOCKING
            result.findings.append(CheckFinding(
                check_id="CHECK_5", tag=tag, severity=sev,
                symbol=f"server.{attr}",
                message=(
                    f"server.{attr} is present."
                    if hasattr(server_mod, attr)
                    else f"server.{attr} is missing — required for MCP server operation."
                ),
            ))
        mcp_obj = getattr(server_mod, "mcp", None)
        if mcp_obj is not None:
            mcp_type = type(mcp_obj).__name__
            tag = "[OK]" if mcp_type == "FastMCP" else "[UNEXPECTED_TYPE]"
            sev = SEVERITY_OK if mcp_type == "FastMCP" else SEVERITY_WARNING
            result.findings.append(CheckFinding(
                check_id="CHECK_5", tag=tag, severity=sev,
                symbol="server.mcp",
                message=(
                    "server.mcp is a FastMCP instance."
                    if mcp_type == "FastMCP"
                    else (
                        f"server.mcp is {mcp_type!r}, expected FastMCP. "
                        "Verify tool registration is using FastMCP decorators."
                    )
                ),
            ))

    # 5b: FPR12 and FPA12 XSD schema files
    schemas_dir = _PKG_DIR / "src" / "mcp_fattura_elettronica_it" / "schemas"
    required_schemas = {
        "FatturaPA_FPR12_v1.2.3.xsd": "FatturaPA B2B/B2C (FPR12) schema — AdE v1.2.3",
        "FatturaPA_FPA12_v1.2.3.xsd": "FatturaPA B2G/PA (FPA12) schema — AdE v1.2.3",
    }
    if schemas_dir.exists():
        for schema_file, description in required_schemas.items():
            xsd_path = schemas_dir / schema_file
            tag = "[OK]" if xsd_path.exists() else "[MISSING_SCHEMA]"
            sev = SEVERITY_OK if xsd_path.exists() else SEVERITY_BLOCKING
            result.findings.append(CheckFinding(
                check_id="CHECK_5", tag=tag, severity=sev,
                symbol=f"schemas/{schema_file}",
                message=(
                    f"XSD schema present: {description}."
                    if xsd_path.exists()
                    else (
                        f"Required XSD '{schema_file}' ({description}) not found. "
                        "Download from https://www.fatturapa.gov.it."
                    )
                ),
            ))
    else:
        result.findings.append(CheckFinding(
            check_id="CHECK_5", tag="[MISSING_SCHEMA]", severity=SEVERITY_BLOCKING,
            symbol="schemas/",
            message=(
                "schemas/ directory not found. FatturaPA XSD validation will fail. "
                "Download XSD files from https://www.fatturapa.gov.it."
            ),
        ))

    # 5c: ItalianInvoice(EN16931Invoice) scaffold check (IT-SC-7)
    models_mod, err = _try_import("mcp_fattura_elettronica_it.models")
    if models_mod is None:
        result.findings.append(CheckFinding(
            check_id="CHECK_5", tag="[MISSING]", severity=SEVERITY_WARNING,
            symbol="models.ItalianInvoice",
            message=(
                f"Could not import models module: {err}. "
                "ItalianInvoice(EN16931Invoice) scaffold (IT-SC-7) not importable."
            ),
        ))
    else:
        italian_invoice_cls = getattr(models_mod, "ItalianInvoice", None)
        if italian_invoice_cls is None:
            result.findings.append(CheckFinding(
                check_id="CHECK_5", tag="[MISSING]", severity=SEVERITY_WARNING,
                symbol="models.ItalianInvoice",
                message="ItalianInvoice not found in models.py. IT-SC-7 scaffold may be incomplete.",
            ))
        else:
            try:
                from mcp_einvoicing_core.en16931 import EN16931Invoice
                if issubclass(italian_invoice_cls, EN16931Invoice):
                    result.findings.append(CheckFinding(
                        check_id="CHECK_5", tag="[OK]", severity=SEVERITY_OK,
                        symbol="models.ItalianInvoice",
                        message="ItalianInvoice(EN16931Invoice) is correctly scaffolded.",
                    ))
                else:
                    result.findings.append(CheckFinding(
                        check_id="CHECK_5", tag="[WRONG_BASE_CLASS]", severity=SEVERITY_BLOCKING,
                        symbol="models.ItalianInvoice",
                        message=(
                            f"ItalianInvoice extends {italian_invoice_cls.__bases__!r} "
                            "but must extend EN16931Invoice (FatturaPA is an EN 16931 CIUS)."
                        ),
                    ))
            except ImportError as exc:
                result.findings.append(CheckFinding(
                    check_id="CHECK_5", tag="[SKIP]", severity=SEVERITY_WARNING,
                    symbol="models.ItalianInvoice base class check",
                    message=f"Could not verify base class: {exc}",
                ))

    # 5d: generate→validate XSD roundtrip for FPR12 and FPA12 (IT-AG-1)
    result.findings.extend(_run_xsd_roundtrip_check())

    return result


def _run_xsd_roundtrip_check() -> list[CheckFinding]:
    """5d — generate one canonical FPR12 and one FPA12 invoice and XSD-validate both.

    IT-SC-19/IT-SC-20 shipped as BLOCKING findings because the audit gate never
    exercised generate_fattura_xml() against the bundled XSD. This sub-check
    closes that hole: it fails BLOCKING whenever generated output does not
    validate, so a future schema regression cannot pass the gate silently.
    """
    import asyncio

    findings: list[CheckFinding] = []
    try:
        from fastmcp import FastMCP as _FastMCP
        from mcp_fattura_elettronica_it.tools.global_tools import register_global_tools

        test_mcp = _FastMCP("it-audit-xsd-roundtrip")
        register_global_tools(test_mcp)
        tools = {t.name: t.fn for t in asyncio.run(test_mcp.list_tools())}
        generate = tools["generate_fattura_xml"]
        validate = tools["validate_fattura_xsd"]
    except Exception as exc:
        findings.append(CheckFinding(
            check_id="CHECK_5", tag="[SKIP]", severity=SEVERITY_WARNING,
            symbol="xsd_roundtrip",
            message=f"Could not register global tools for XSD roundtrip check: {exc}",
        ))
        return findings

    cedente_prestatore = {
        "CedentePrestatore": {
            "DatiAnagrafici": {
                "IdFiscaleIVA": {"IdPaese": "IT", "IdCodice": "01234567897"},
                "Anagrafica": {"Denominazione": "Audit Gate Srl"},
                "RegimeFiscale": "RF01",
            },
            "Sede": {"Indirizzo": "Via Roma 1", "CAP": "00100", "Comune": "Roma", "Nazione": "IT"},
        }
    }
    cessionario_committente = {
        "CessionarioCommittente": {
            "DatiAnagrafici": {
                "IdFiscaleIVA": {"IdPaese": "IT", "IdCodice": "98765432109"},
                "Anagrafica": {"Denominazione": "Buyer Srl"},
            },
            "Sede": {"Indirizzo": "Via Verdi 2", "CAP": "20100", "Comune": "Milano", "Nazione": "IT"},
        }
    }
    dati_generali = {
        "DatiGenerali": {
            "DatiGeneraliDocumento": {
                "TipoDocumento": "TD01",
                "Divisa": "EUR",
                "Data": "2026-01-15",
                "Numero": "2026/001",
            }
        }
    }
    dettaglio_linee = [
        {
            "DettaglioLinee": {
                "NumeroLinea": 1,
                "Descrizione": "Consulenza",
                "PrezzoUnitario": "1000.00",
                "PrezzoTotale": "1000.00",
                "AliquotaIVA": "22.00",
            }
        }
    ]
    dati_riepilogo = [
        {
            "AliquotaIVA": "22.00",
            "ImponibileImporto": "1000.00",
            "Imposta": "220.00",
            "EsigibilitaIVA": "I",
        }
    ]

    _cases = {
        "FPR12": "ABC123",
        "FPA12": "A1B2C3",  # 6-char IPA office code
    }
    for formato, codice_dest in _cases.items():
        dati_trasmissione = {
            "DatiTrasmissione": {
                "IdTrasmittente": {"IdPaese": "IT", "IdCodice": "01234567897"},
                "ProgressivoInvio": "00001",
                "FormatoTrasmissione": formato,
                "CodiceDestinatario": codice_dest,
            }
        }
        gen_result = generate(
            dati_trasmissione=dati_trasmissione,
            cedente_prestatore=cedente_prestatore,
            cessionario_committente=cessionario_committente,
            dati_generali=dati_generali,
            dettaglio_linee=dettaglio_linee,
            dati_riepilogo=dati_riepilogo,
        )
        symbol = f"xsd_roundtrip[{formato}]"
        if "error" in gen_result:
            findings.append(CheckFinding(
                check_id="CHECK_5", tag="[GENERATION_FAILED]", severity=SEVERITY_BLOCKING,
                symbol=symbol,
                message=f"generate_fattura_xml() failed for {formato}: {gen_result['error']}",
            ))
            continue

        xsd_result = validate(xml_string=gen_result["xml"])
        if xsd_result.get("valid") is True:
            findings.append(CheckFinding(
                check_id="CHECK_5", tag="[OK]", severity=SEVERITY_OK,
                symbol=symbol,
                message=f"generate_fattura_xml() output for {formato} validates against the bundled XSD.",
            ))
        else:
            findings.append(CheckFinding(
                check_id="CHECK_5", tag="[XSD_INVALID]", severity=SEVERITY_BLOCKING,
                symbol=symbol,
                message=(
                    f"generate_fattura_xml() output for {formato} fails XSD validation: "
                    f"{xsd_result.get('errors', xsd_result)}"
                ),
            ))

    return findings


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# CHECK 6 — Parallel-implementation detector (Phase 0a.2)
# ---------------------------------------------------------------------------

_CORE_CAPABILITIES: list[tuple[str, str, list[str]]] = [
    ("cii_ubl_conversion", "mcp_einvoicing_core.convert", [
        "convert_wire_format",
    ]),
    ("peppol_participant_lookup", "mcp_einvoicing_core.peppol", [
        "PeppolSMPClient",
    ]),
    ("en16931_cii_parsing", "mcp_einvoicing_core.wire_formats", [
        "EN16931CIIParser", "EN16931CIISerializer",
    ]),
    ("en16931_ubl_parsing", "mcp_einvoicing_core.wire_formats", [
        "EN16931UBLParser", "EN16931UBLSerializer",
    ]),
    ("schematron_validation", "mcp_einvoicing_core.schematron", [
        "SchematronValidator",
    ]),
    ("xades_xmldsig_signing", "mcp_einvoicing_core.digital_signature", [
        "XAdESEPESSigner", "XMLDSigSigner",
    ]),
    ("http_client", "mcp_einvoicing_core.http_client", [
        "BaseEInvoicingClient",
    ]),
    ("routing_identifier_validation", "mcp_einvoicing_core.routing", [
        "RoutingIdentifier",
    ]),
    ("peppol_as4_transport", "mcp_einvoicing_core.peppol.transport", [
        "AS4MessageEnvelope", "AS4TransportClient", "PeppolTransmitter",
    ]),
]

_INTENTIONAL_PARALLEL_IMPLEMENTATIONS: dict[tuple[str, str], str] = {}


def run_check_6() -> CheckResult:
    """CHECK 6 — Parallel-implementation scan."""
    import ast

    result = CheckResult(check_id="CHECK_6", name="Parallel-implementation detector")

    pkg_root = Path(__file__).parent.parent / "src" / "mcp_fattura_elettronica_it"
    if not pkg_root.is_dir():
        result.findings.append(CheckFinding(
            check_id="CHECK_6", tag="[SKIP]", severity=SEVERITY_OK,
            symbol="mcp_fattura_elettronica_it",
            message="Package source directory not found; skipping parallel-implementation scan.",
        ))
        return result

    defined_names: dict[str, str] = {}
    for py_file in pkg_root.rglob("*.py"):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                defined_names[node.name] = str(py_file.relative_to(pkg_root.parent.parent))

    found_any = False
    for cap_tag, core_module, symbols in _CORE_CAPABILITIES:
        for symbol in symbols:
            if symbol not in defined_names:
                continue

            override_key = (cap_tag, symbol)
            if override_key in _INTENTIONAL_PARALLEL_IMPLEMENTATIONS:
                result.findings.append(CheckFinding(
                    check_id="CHECK_6", tag="[OVERRIDE]", severity=SEVERITY_OK,
                    symbol=symbol,
                    message=(
                        f"Parallel implementation of {symbol} ({cap_tag}) in "
                        f"{defined_names[symbol]} is intentional: "
                        f"{_INTENTIONAL_PARALLEL_IMPLEMENTATIONS[override_key]}"
                    ),
                ))
                continue

            found_any = True
            result.findings.append(CheckFinding(
                check_id="CHECK_6", tag="[PARALLEL]", severity=SEVERITY_WARNING,
                symbol=symbol,
                message=(
                    f"Country package defines {symbol!r} in {defined_names[symbol]}, "
                    f"which mirrors core capability {cap_tag!r} from {core_module}. "
                    "Delegate to the core symbol or register in "
                    "_INTENTIONAL_PARALLEL_IMPLEMENTATIONS with a justification."
                ),
            ))

    if not found_any and not result.findings:
        result.findings.append(CheckFinding(
            check_id="CHECK_6", tag="[OK]", severity=SEVERITY_OK,
            symbol="*",
            message="No parallel implementations of core capabilities detected.",
        ))

    return result


def run_audit() -> AuditReport:
    """Execute all checks and return the aggregated AuditReport. No side effects."""
    report = make_report("mcp-fattura-elettronica-it", _PYPROJECT)

    report.checks.append(run_check_core_coverage(
        package_name="mcp-fattura-elettronica-it",
        package_modules=_PKG_MODULES,
        intentional_overrides=_INTENTIONAL_OVERRIDES,
        is_en16931_family=_IS_EN16931_FAMILY,
        primary_invoice_class=_PRIMARY_INVOICE_CLASS,
    ))
    report.checks.append(run_check_2())
    report.checks.append(run_check_3())
    report.checks.append(run_check_version_compatibility(
        package_name="mcp-fattura-elettronica-it",
        pyproject_path=_PYPROJECT,
    ))
    report.checks.append(run_check_5())
    report.checks.append(run_check_6())

    return report


def main(argv: list[str] | None = None) -> int:
    args = parse_audit_args(
        "Pre-publish audit: mcp-fattura-elettronica-it vs mcp-einvoicing-core", argv
    )
    report = run_audit()

    output_path = Path(args.output) if args.output else _PKG_DIR / "audit" / "report.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")

    if not args.quiet:
        print(render_summary_table(report))
        print(f"\nJSON report written to: {output_path}")

    if args.fail_on == "never":
        return 0
    if args.fail_on == "warnings":
        return min(report.exit_code, 2)
    return 2 if report.total_blocking > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
