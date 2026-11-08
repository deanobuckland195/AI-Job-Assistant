"""Bounded local document reading and isolated extraction. No network access."""

import base64
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_TEXT_CHARS = 200_000
MAX_SEGMENTS = 2000
MAX_PAGES = 30
EXTRACTION_TIMEOUT = 15


class DocumentError(ValueError):
    """A safe, user-facing extraction or validation failure."""


@dataclass
class Segment:
    reference: str
    source_text: str
    reviewed_text: str


@dataclass
class ExtractedDocument:
    filename: str
    file_type: str
    size_bytes: int
    sha256: str
    extractor: str
    segments: list[Segment]
    warnings: list[str] = field(default_factory=list)


def validate_segments(segments):
    if not segments or not any(s.reviewed_text.strip() for s in segments):
        raise DocumentError("No readable text remains. Scanned PDFs need OCR, which is not supported.")
    if len(segments) > MAX_SEGMENTS:
        raise DocumentError(f"Document exceeds the {MAX_SEGMENTS} source-unit limit.")
    for attribute in ("source_text", "reviewed_text"):
        if sum(len(getattr(s, attribute)) for s in segments) > MAX_TEXT_CHARS:
            raise DocumentError(f"Document exceeds the {MAX_TEXT_CHARS:,}-character extraction limit.")


def extract_document(path):
    path = Path(path)
    kind = path.suffix.lower().lstrip(".")
    if kind not in {"pdf", "docx", "txt"}:
        raise DocumentError("Unsupported file type. Choose a PDF, DOCX or UTF-8 TXT file.")
    # Read a regular file once; never extract archives to disk or follow links.
    try:
        if path.is_symlink():
            raise DocumentError("Symbolic links are not supported; choose the original file.")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        flags |= getattr(os, "O_BINARY", 0)
        with os.fdopen(os.open(path, flags), "rb") as file:
            info = os.fstat(file.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise DocumentError("Choose a regular document file.")
            if info.st_size > MAX_FILE_BYTES:
                raise DocumentError("File exceeds the 5 MiB size limit.")
            data = file.read(MAX_FILE_BYTES + 1)
    except OSError:
        raise DocumentError("Cannot read this file. Check that it exists and is accessible.") from None
    if not data:
        raise DocumentError("The document is empty.")
    if len(data) > MAX_FILE_BYTES:
        raise DocumentError("File exceeds the 5 MiB size limit.")
    # Pass only bounded bytes, not a path. The child cannot accidentally open a
    # different CV if the original file is replaced while extraction runs.
    payload = json.dumps({"kind": kind, "data": base64.b64encode(data).decode("ascii")})
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parent.parent)
    try:
        result = subprocess.run(
            [sys.executable, "-B", "-m", "job_assistant.extraction_worker"],
            input=payload, text=True, encoding="utf-8", stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, timeout=EXTRACTION_TIMEOUT, env=env,
        )
    except subprocess.TimeoutExpired:
        raise DocumentError("Extraction exceeded the 15-second time limit. Try a simpler document.") from None
    except OSError:
        raise DocumentError("Could not start the document extractor.") from None
    if result.returncode:
        raise DocumentError("Extraction failed or exceeded resource limits. Try a simpler document.")
    try:
        extracted = json.loads(result.stdout)
        if "error" in extracted:
            raise DocumentError(extracted["error"])
        segments = [Segment(**s) for s in extracted["segments"]]
        validate_segments(segments)
        return ExtractedDocument(path.name, kind, len(data), hashlib.sha256(data).hexdigest(),
                                 extracted["extractor"], segments, extracted["warnings"])
    except (KeyError, TypeError, json.JSONDecodeError):
        raise DocumentError("The extractor returned an invalid result.") from None
