"""Private subprocess entry point. Only structured results reach the parent."""

import base64
from dataclasses import asdict
from importlib.metadata import version
import io
import json
import logging
import sys
import warnings
import zipfile

from .documents import DocumentError, MAX_PAGES, MAX_SEGMENTS, MAX_TEXT_CHARS, Segment, validate_segments

MAX_ZIP_BYTES = 20 * 1024 * 1024
MAX_ZIP_MEMBER = 5 * 1024 * 1024


def extract_bytes(data, kind):
    segments = []
    notes = []
    chars = 0

    def add(reference, text):
        nonlocal chars
        chars += len(text)
        if chars > MAX_TEXT_CHARS:
            raise DocumentError("Document exceeds the 200,000-character extraction limit.")
        if len(segments) >= MAX_SEGMENTS:
            raise DocumentError("Document exceeds the 2000 source-unit limit.")
        segments.append(Segment(reference, text, text))

    if kind == "txt":
        if data.startswith((b"%PDF-", b"PK\x03\x04", bytes.fromhex("d0cf11e0a1b11ae1"))):
            raise DocumentError("File contents do not match the TXT extension.")
        try:
            text = data.decode("utf-8-sig")
        except UnicodeError:
            raise DocumentError("TXT files must use UTF-8 encoding.") from None
        if any(ord(c) < 32 and c not in "\n\r\t\f" for c in text):
            raise DocumentError("This does not look like a plain text document.")
        for number, line in enumerate(text.splitlines(keepends=True), 1):
            add(f"line {number}", line)
        extractor = "Python UTF-8 decoder"
    elif kind == "pdf":
        from pypdf import PdfReader
        from pypdf.errors import DependencyError
        if not data.startswith(b"%PDF-"):
            raise DocumentError("File contents do not match the PDF extension.")
        try:
            reader = PdfReader(io.BytesIO(data), strict=True)
        except DependencyError:
            raise DocumentError("Encrypted PDFs are not supported. Export an unencrypted copy locally.") from None
        if reader.is_encrypted:
            raise DocumentError("Encrypted PDFs are not supported. Export an unencrypted copy locally.")
        if len(reader.pages) > MAX_PAGES:
            raise DocumentError(f"PDF exceeds the {MAX_PAGES}-page limit.")
        for number, page in enumerate(reader.pages, 1):
            text = page.extract_text() or ""
            add(f"page {number}", text)
            if not text.strip():
                notes.append(f"Page {number} has no extractable text; images are not transcribed.")
        notes.append("PDF reading order and layout can be imperfect. Review every page; OCR is not included.")
        extractor = "pypdf " + version("pypdf")
    else:
        if data.startswith(bytes.fromhex("d0cf11e0a1b11ae1")):
            raise DocumentError("Encrypted Office files and legacy DOC files are not supported.")
        if not zipfile.is_zipfile(io.BytesIO(data)):
            raise DocumentError("File contents do not match DOCX (or the file is corrupt).")
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > 500 or sum(e.file_size for e in entries) > MAX_ZIP_BYTES:
                raise DocumentError("DOCX archive exceeds safe extraction limits.")
            if len({e.filename for e in entries}) != len(entries):
                raise DocumentError("DOCX archive has duplicate entries.")
            if "word/document.xml" not in archive.namelist():
                raise DocumentError("This archive is not a DOCX document.")
            for entry in entries:
                if entry.flag_bits & 1:
                    raise DocumentError("Encrypted DOCX archives are not supported.")
                if (entry.file_size > MAX_ZIP_MEMBER or
                        entry.file_size > max(entry.compress_size, 1) * 200):
                    raise DocumentError("DOCX archive exceeds safe expansion limits.")
                # No extraction to filesystem, including for traversal names.
                if entry.filename.lower().endswith((".xml", ".rels")):
                    xml = archive.read(entry).lower()
                    if b"<!doctype" in xml or b"<!entity" in xml:
                        raise DocumentError("DOCX XML entity declarations are not supported.")
            if archive.testzip() is not None:
                raise DocumentError("The DOCX archive is corrupt.")
        from docx import Document
        from docx.text.paragraph import Paragraph

        def walk(container, prefix, depth=0):
            if depth > 10:
                raise DocumentError("DOCX table nesting exceeds the safe limit.")
            paragraphs = tables = 0
            for block in container.iter_inner_content():
                if isinstance(block, Paragraph):
                    paragraphs += 1
                    add(f"{prefix}/paragraph {paragraphs}", block.text)
                else:
                    tables += 1
                    seen_cells = set()
                    for row_number, row in enumerate(block.rows, 1):
                        for column, cell in enumerate(row.cells, 1):
                            # Merged cells can appear more than once in the grid.
                            if cell._tc in seen_cells:
                                continue
                            seen_cells.add(cell._tc)
                            walk(cell, f"{prefix}/table {tables}/row {row_number}/cell {column}", depth + 1)

        document = Document(io.BytesIO(data))
        walk(document, "body")
        seen_stories = set()
        for section_number, section in enumerate(document.sections, 1):
            for name in ("header", "first_page_header", "even_page_header",
                         "footer", "first_page_footer", "even_page_footer"):
                story = getattr(section, name)
                if story.is_linked_to_previous or story.part.partname in seen_stories:
                    continue
                seen_stories.add(story.part.partname)
                walk(story, f"section {section_number}/{name}")
        notes.append("DOCX references identify body paragraphs and table cells, not rendered pages. "
                     "Defined headers and footers are included once. Text boxes, comments, images "
                     "and tracked changes may be omitted.")
        extractor = "python-docx " + version("python-docx")
    validate_segments(segments)
    return {"segments": [asdict(s) for s in segments], "extractor": extractor, "warnings": notes}


def main():
    logging.disable(logging.CRITICAL)
    warnings.filterwarnings("ignore")
    # Linux offers a dependable address-space limit. Other platforms retain
    # the parent timeout, input, output, page and archive limits.
    if sys.platform.startswith("linux"):
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    try:
        payload = json.load(sys.stdin)
        result = extract_bytes(base64.b64decode(payload["data"], validate=True), payload["kind"])
    except DocumentError as error:
        result = {"error": str(error)}
    except ImportError:
        result = {"error": "Document libraries are missing. Run: python -m pip install -r requirements.txt"}
    except Exception:
        # Never echo parser exceptions: they may include document text.
        result = {"error": "The document is corrupt or uses an unsupported document structure."}
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
