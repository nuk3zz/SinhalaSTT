"""Read plain text out of pasted files: TXT, PDF, or DOCX.

Used by the "Open file..." buttons so a user can load a script from a document
instead of copy-pasting it.
"""

from __future__ import annotations

from pathlib import Path


SUPPORTED_DOCUMENT_SUFFIXES = {".txt", ".pdf", ".docx"}


class DocumentReadError(Exception):
    """A user-friendly document reading error."""


def read_text_from_file(file_path: str | Path) -> str:
    path = Path(file_path).expanduser()

    if not path.exists() or not path.is_file():
        raise DocumentReadError(f"File not found: {path}")

    suffix = path.suffix.lower()
    if suffix == ".txt":
        return _read_txt(path)
    if suffix == ".pdf":
        return _read_pdf(path)
    if suffix == ".docx":
        return _read_docx(path)

    raise DocumentReadError(
        f"Unsupported file type: {suffix or 'unknown'}. Please choose a TXT, PDF, or DOCX file."
    )


def _read_txt(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        # Fall back for files saved in another encoding.
        return path.read_text(encoding="latin-1")


def _read_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as error:  # pragma: no cover - dependency missing
        raise DocumentReadError(
            "PDF support is not available in this build. Please paste the text instead."
        ) from error

    try:
        reader = PdfReader(str(path))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as error:
        raise DocumentReadError(f"Could not read this PDF: {error}") from error

    text = "\n".join(pages).strip()
    if not text:
        raise DocumentReadError(
            "No text could be read from this PDF. It may be a scanned image rather than text."
        )
    return text


def _read_docx(path: Path) -> str:
    try:
        from docx import Document
    except ImportError as error:  # pragma: no cover - dependency missing
        raise DocumentReadError(
            "DOCX support is not available in this build. Please paste the text instead."
        ) from error

    try:
        document = Document(str(path))
        paragraphs = [paragraph.text for paragraph in document.paragraphs]
    except Exception as error:
        raise DocumentReadError(f"Could not read this DOCX: {error}") from error

    text = "\n".join(paragraphs).strip()
    if not text:
        raise DocumentReadError("No text could be read from this DOCX file.")
    return text
