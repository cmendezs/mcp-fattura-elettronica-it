"""Pacchetto di Versamento (PdV) assembly per AgID specs.

A PdV is a ZIP archive containing the documents to be archived and an
XML index (Indice del Pacchetto di Versamento, IPdV) that describes
the contents, their hashes, and archival metadata.

[NEED: verify exact IPdV XML schema from AgID technical documentation]
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from datetime import datetime, timezone
from typing import Any

from lxml import etree


def build_indice_pdv(
    documents: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> str:
    """Build the XML index for a Pacchetto di Versamento.

    Args:
        documents: List of dicts with keys ``filename``, ``hash`` (SHA-256 hex),
            ``format_id``, and ``size_bytes``.
        metadata: Package-level metadata with keys ``producer_id``,
            ``archive_date``, ``retention_years``.

    Returns:
        UTF-8 XML string of the IPdV index.
    """
    root = etree.Element("IndicePackage")
    root.set("version", "1.0")

    header = etree.SubElement(root, "Header")
    etree.SubElement(header, "ProducerId").text = metadata.get("producer_id", "")
    etree.SubElement(header, "ArchiveDate").text = metadata.get(
        "archive_date", datetime.now(timezone.utc).isoformat()
    )
    etree.SubElement(header, "RetentionYears").text = str(
        metadata.get("retention_years", 10)
    )

    docs_el = etree.SubElement(root, "Documents")
    for doc in documents:
        doc_el = etree.SubElement(docs_el, "Document")
        etree.SubElement(doc_el, "Filename").text = doc["filename"]
        etree.SubElement(doc_el, "Hash").text = doc["hash"]
        etree.SubElement(doc_el, "FormatId").text = doc.get("format_id", "")
        etree.SubElement(doc_el, "SizeBytes").text = str(doc.get("size_bytes", 0))

    return etree.tostring(root, encoding="unicode", pretty_print=True)


def build_pacchetto_di_versamento(
    documents: list[tuple[str, bytes]],
    metadata: dict[str, Any],
) -> bytes:
    """Assemble a Pacchetto di Versamento (PdV) ZIP archive.

    Args:
        documents: List of ``(filename, content_bytes)`` tuples.
        metadata: Package-level metadata passed to ``build_indice_pdv``.

    Returns:
        ZIP archive bytes containing all documents and the IPdV index.
    """
    doc_entries: list[dict[str, Any]] = []
    for filename, content in documents:
        doc_entries.append({
            "filename": filename,
            "hash": hashlib.sha256(content).hexdigest(),
            "format_id": metadata.get("format_id", "FatturaPA-1.2.3"),
            "size_bytes": len(content),
        })

    index_xml = build_indice_pdv(doc_entries, metadata)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for filename, content in documents:
            zf.writestr(filename, content)
        zf.writestr("IPdV.xml", index_xml)

    return buf.getvalue()
