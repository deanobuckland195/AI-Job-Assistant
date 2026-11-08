import io
import subprocess
import zipfile

import pytest

from job_assistant import documents
from job_assistant.documents import DocumentError, extract_document


def test_txt_preserves_unicode_and_line_references(tmp_path):
    path = tmp_path / "sample.TXT"
    text = "Demo Candidate — Python\r\n\nSQL\n"
    path.write_bytes(text.encode("utf-8-sig"))
    result = extract_document(path)
    assert result.file_type == "txt"
    assert result.filename == path.name
    assert result.size_bytes == len(path.read_bytes())
    assert len(result.sha256) == 64
    assert "".join(s.source_text for s in result.segments) == text
    assert [s.reference for s in result.segments] == ["line 1", "line 2", "line 3"]
    assert all(s.reviewed_text == s.source_text for s in result.segments)


def test_pdf_preserves_page_evidence(make_pdf):
    result = extract_document(make_pdf())
    assert [s.reference for s in result.segments] == ["page 1", "page 2"]
    assert "Demo Candidate" in result.segments[0].source_text
    assert "Python and SQL" in result.segments[1].source_text
    assert result.extractor.startswith("pypdf ")


def test_docx_preserves_paragraphs_and_nested_tables(make_docx):
    result = extract_document(make_docx())
    assert result.segments[0].reference == "body/paragraph 1"
    assert result.segments[-1].reference == "body/paragraph 2"
    nested = next(s for s in result.segments if s.source_text == "Nested project")
    assert "table 1/row 1/cell 2/table 1" in nested.reference
    assert "Python" in [s.source_text for s in result.segments]
    assert "SQL" in [s.source_text for s in result.segments]
    assert result.extractor.startswith("python-docx ")
    assert result.warnings


def test_docx_includes_header_footer_evidence(tmp_path):
    from docx import Document
    document = Document()
    document.add_paragraph("Synthetic CV body")
    document.sections[0].header.paragraphs[0].text = "Synthetic contact details"
    document.sections[0].footer.paragraphs[0].text = "Synthetic footer"
    document.add_section()
    path = tmp_path / "header.docx"
    document.save(path)
    result = extract_document(path)
    header = [s for s in result.segments if s.source_text == "Synthetic contact details"]
    footer = [s for s in result.segments if s.source_text == "Synthetic footer"]
    assert len(header) == len(footer) == 1
    assert header[0].reference == "section 1/header/paragraph 1"
    assert footer[0].reference == "section 1/footer/paragraph 1"


@pytest.mark.parametrize("extension, data, message", [
    ("doc", b"legacy", "Unsupported file type"),
    ("txt", b"", "empty"),
    ("txt", b"\xff\xfe", "UTF-8"),
    ("txt", b"abc\x00def", "plain text"),
    ("txt", b"%PDF-1.7\nnot text", "TXT extension"),
    ("txt", b" \n\t", "No readable text"),
    ("pdf", b"Plain text", "PDF extension"),
    ("pdf", b"%PDF-1.7\nBroken", "corrupt"),
    ("docx", b"not a ZIP", "DOCX"),
    ("docx", bytes.fromhex("d0cf11e0a1b11ae1") + b"encrypted", "Encrypted Office"),
])
def test_reject_invalid_documents(tmp_path, extension, data, message):
    path = tmp_path / f"bad.{extension}"
    path.write_bytes(data)
    with pytest.raises(DocumentError, match=message):
        extract_document(path)


def test_missing_file(tmp_path):
    with pytest.raises(DocumentError, match="Cannot read"):
        extract_document(tmp_path / "missing.txt")


def test_symlink_not_followed(tmp_path):
    target = tmp_path / "target.txt"
    target.write_text("Synthetic")
    link = tmp_path / "link.txt"
    link.symlink_to(target)
    with pytest.raises(DocumentError, match="Symbolic links"):
        extract_document(link)


def test_directory_not_read(tmp_path):
    path = tmp_path / "directory.txt"
    path.mkdir()
    with pytest.raises(DocumentError):
        extract_document(path)


def test_oversized_file_rejected_before_worker(tmp_path, monkeypatch):
    path = tmp_path / "large.txt"
    with path.open("wb") as file:
        file.truncate(documents.MAX_FILE_BYTES + 1)
    monkeypatch.setattr(documents.subprocess, "run", lambda *a, **kw: pytest.fail("Worker must not run"))
    with pytest.raises(DocumentError, match="5 MiB"):
        extract_document(path)


@pytest.mark.parametrize("text, message", [
    ("x" * (documents.MAX_TEXT_CHARS + 1), "character"),
    ("x\n" * (documents.MAX_SEGMENTS + 1), "source-unit"),
])
def test_text_extraction_limits(tmp_path, text, message):
    path = tmp_path / "limited.txt"
    path.write_text(text)
    with pytest.raises(DocumentError, match=message):
        extract_document(path)


def test_pdf_page_limit(make_pdf):
    with pytest.raises(DocumentError, match="30-page"):
        extract_document(make_pdf(["x"] * 31))


def test_encrypted_pdf_rejected_even_if_password_known(make_pdf):
    with pytest.raises(DocumentError, match="Encrypted PDFs"):
        extract_document(make_pdf(encrypted=True))


def test_image_only_or_blank_pdf_explains_ocr(make_pdf):
    with pytest.raises(DocumentError, match="OCR"):
        extract_document(make_pdf([""]))


def test_partial_pdf_extraction_warns_about_empty_page(make_pdf):
    result = extract_document(make_pdf(["Python", ""]))
    assert len(result.segments) == 2
    assert any("Page 2" in w for w in result.warnings)


def make_zip(entries):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries:
            archive.writestr(name, data)
    return output.getvalue()


@pytest.mark.parametrize("entries, message", [
    ([("unrelated.txt", "data")], "not a DOCX"),
    ([("word/document.xml", "x" * 100_000)], "expansion"),
    ([("word/document.xml", "<!DOCTYPE x><x/>")], "entity declarations"),
    ([("word/document.xml", "a")] + [(f"x{i}", "b") for i in range(500)], "extraction limits"),
])
def test_docx_archive_safety(tmp_path, entries, message):
    path = tmp_path / "bad.docx"
    path.write_bytes(make_zip(entries))
    with pytest.raises(DocumentError, match=message):
        extract_document(path)


def test_encrypted_zip_flag_rejected(tmp_path):
    data = bytearray(make_zip([("word/document.xml", "synthetic")]))
    local = data.index(b"PK\x03\x04")
    central = data.index(b"PK\x01\x02")
    data[local + 6] |= 1
    data[central + 8] |= 1
    path = tmp_path / "encrypted.docx"
    path.write_bytes(data)
    with pytest.raises(DocumentError, match="Encrypted DOCX"):
        extract_document(path)


def test_timeout_is_safe(tmp_path, monkeypatch):
    path = tmp_path / "sample.txt"
    path.write_text("Synthetic")
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("extractor", 15)
    monkeypatch.setattr(documents.subprocess, "run", timeout)
    with pytest.raises(DocumentError, match="time limit"):
        extract_document(path)


@pytest.mark.parametrize("returncode, output, message", [
    (1, "", "resource limits"),
    (0, "not json", "invalid result"),
])
def test_worker_failures_are_safe(tmp_path, monkeypatch, returncode, output, message):
    path = tmp_path / "sample.txt"
    path.write_text("Synthetic")
    monkeypatch.setattr(documents.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess([], returncode, output))
    with pytest.raises(DocumentError, match=message):
        extract_document(path)


def test_no_raw_parser_error_or_document_logging(tmp_path, caplog):
    path = tmp_path / "secret.pdf"
    path.write_bytes(b"%PDF-1.7\nSYNTHETIC_PRIVATE_MARKER")
    with pytest.raises(DocumentError) as caught:
        extract_document(path)
    assert "SYNTHETIC_PRIVATE_MARKER" not in str(caught.value)
    assert "SYNTHETIC_PRIVATE_MARKER" not in caplog.text
