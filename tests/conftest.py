"""Synthetic fixtures only: no access to existing CVs or user databases."""

import io
import socket

import pytest
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
from docx import Document


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Tests must not use the network")
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)


def pdf_bytes(texts, encrypted=False):
    writer = PdfWriter()
    for text in texts:
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject({
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        })
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
        if text:
            stream = DecodedStreamObject()
            escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            stream.set_data(f"BT /F1 12 Tf 50 700 Td ({escaped}) Tj ET".encode("ascii"))
            page[NameObject("/Contents")] = writer._add_object(stream)
    if encrypted:
        writer.encrypt("synthetic-password", algorithm="RC4-128")
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


@pytest.fixture
def make_pdf(tmp_path):
    def make(texts=("Demo Candidate", "Python and SQL"), encrypted=False, name="synthetic.pdf"):
        path = tmp_path / name
        path.write_bytes(pdf_bytes(texts, encrypted))
        return path
    return make


@pytest.fixture
def make_docx(tmp_path):
    def make():
        document = Document()
        document.add_paragraph("Demo Candidate")
        table = document.add_table(rows=1, cols=2)
        table.cell(0, 0).text = "Python"
        table.cell(0, 1).text = "SQL"
        nested = table.cell(0, 1).add_table(rows=1, cols=1)
        nested.cell(0, 0).text = "Nested project"
        document.add_paragraph("Career goals")
        path = tmp_path / "synthetic.docx"
        document.save(path)
        return path
    return make
