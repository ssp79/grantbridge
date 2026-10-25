"""Reading an uploaded solicitation: validation first, then text.

GrantBridge accepts three document types and nothing else. A file is identified by its *content*, not its name,
so renaming a file does not get it past the check. Nothing is executed, no path from the upload is ever opened,
and the bytes are not written to disk: they are read in memory, turned into text, and dropped. Only the text and
the excerpts the user confirms are stored.

Every failure raises `UploadError` with a sentence a nonprofit user can act on, including the case this cannot
handle: a scanned PDF with no text layer, which would need OCR that GrantBridge does not have.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass

MAX_BYTES = 8 * 1024 * 1024      # one solicitation; the largest federal notices are a few hundred KB of text
MAX_PAGES = 80
MAX_CHARS = 250_000              # about 40,000 words: beyond this the document is not a solicitation
MIN_TEXT_CHARS = 200             # less than this from a whole PDF means there is no text layer to read
SUPPORTED = ("pdf", "docx", "txt")
PDF_MAGIC = b"%PDF-"
ZIP_MAGIC = b"PK\x03\x04"


class UploadError(Exception):
    """Something about the file means GrantBridge cannot read it. The message is shown to the user."""


@dataclass(frozen=True)
class Document:
    name: str
    kind: str          # pdf, docx or txt
    text: str
    pages: int | None  # for a PDF; None for the others
    truncated: bool


def sniff(data: bytes, filename: str = "") -> str:
    """The file's real type, from its first bytes. The name is only a tie-breaker between zip-based formats."""
    if not data:
        raise UploadError("That file is empty.")
    if data.startswith(PDF_MAGIC):
        return "pdf"
    if data.startswith(ZIP_MAGIC):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as bundle:
                names = set(bundle.namelist())
        except zipfile.BadZipFile:
            raise UploadError("That file looks damaged and could not be opened.") from None
        if "word/document.xml" in names:
            return "docx"
        raise UploadError("That looks like a zip archive or an older Office file. GrantBridge reads PDF, DOCX "
                          "and plain text. If it is a .doc, save it as .docx and try again.")
    if _is_text(data):
        return "txt"
    raise UploadError("GrantBridge could not recognise that file. It reads PDF, DOCX and plain text documents.")


UTF16_BOMS = (b"\xff\xfe", b"\xfe\xff")


def _is_text(data: bytes) -> bool:
    if data.startswith(UTF16_BOMS):   # UTF-16 is full of NUL bytes, so check the mark before the binary test
        try:
            data[: len(data) // 2 * 2].decode("utf-16")
            return True
        except UnicodeDecodeError:
            return False
    if b"\x00" in data[:4096]:
        return False
    for encoding in ("utf-8", "utf-16", "cp1252"):
        try:
            data[:4096].decode(encoding)
            return True
        except UnicodeDecodeError:
            continue
    return False


def read(data: bytes, filename: str) -> Document:
    """Validate and extract. Raises UploadError with a plain-language reason if the file cannot be read."""
    if len(data) > MAX_BYTES:
        raise UploadError(f"That file is {len(data) / 1_048_576:.1f} MB. The limit is "
                          f"{MAX_BYTES // 1_048_576} MB per document.")
    kind = sniff(data, filename)
    if kind == "pdf":
        text, pages = _read_pdf(data)
    elif kind == "docx":
        text, pages = _read_docx(data), None
    else:
        text, pages = _read_txt(data), None
    text = _tidy(text)
    if len(text.strip()) < MIN_TEXT_CHARS:
        if kind == "pdf":
            raise UploadError("GrantBridge could not find any text in that PDF. It is probably a scan or a set of "
                              "images; GrantBridge cannot read those, because it has no OCR. Please upload a PDF "
                              "with selectable text, a DOCX, or paste the text instead.")
        raise UploadError("There was almost no text in that file. Please check it is the right document.")
    truncated = len(text) > MAX_CHARS
    return Document(name=filename or f"document.{kind}", kind=kind, text=text[:MAX_CHARS], pages=pages,
                    truncated=truncated)


def _read_pdf(data: bytes) -> tuple[str, int]:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:                                   # many PDFs are "encrypted" with an empty owner password
                if reader.decrypt("") == 0:
                    raise UploadError("That PDF is password-protected. Please remove the password and try again.")
            except UploadError:
                raise
            except Exception:
                raise UploadError("That PDF is password-protected. Please remove the password and try "
                                  "again.") from None
        pages = len(reader.pages)
        if pages > MAX_PAGES:
            raise UploadError(f"That PDF has {pages} pages. GrantBridge reads up to {MAX_PAGES}. Please upload the "
                              "sections that describe the application.")
        parts = []
        for page in reader.pages[:MAX_PAGES]:
            try:
                parts.append(page.extract_text() or "")
            except Exception:                      # one unreadable page should not lose the whole document
                parts.append("")
    except UploadError:
        raise
    except (PdfReadError, Exception) as err:       # pypdf raises a wide range on malformed files
        raise UploadError("That PDF could not be read. It may be damaged or incomplete.") from err
    return "\n".join(parts), pages


def _read_docx(data: bytes) -> str:
    import docx

    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as err:
        raise UploadError("That Word document could not be read. It may be damaged, or saved in an older "
                          "format. Try saving it again as .docx.") from err
    parts = [p.text for p in document.paragraphs]
    for table in document.tables:                  # application questions often live in a table
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            if any(cells):
                parts.append(" | ".join(cells))
    return "\n".join(parts)


def _read_txt(data: bytes) -> str:
    for encoding in ("utf-8", "utf-16", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise UploadError("That text file is in an encoding GrantBridge could not read. Please save it as UTF-8.")


def _tidy(text: str) -> str:
    """Collapse the ragged whitespace PDF extraction produces, without losing paragraph breaks."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return "\n".join(line.strip() for line in text.split("\n")).strip()
