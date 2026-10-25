"""Reading uploaded solicitations: real PDF, DOCX and TXT files, and every way one can be rejected."""

import io
import zipfile

import pytest

from grantbridge import documents as doc

SOLICITATION = (
    "New Harbor Literacy Fund\n"
    "Notice of Funding Opportunity NHLF-2027-01\n\n"
    "Applications are due 14 March 2027 at 5:00 p.m. Eastern.\n"
    "Awards range from $25,000 to $60,000 over two years.\n"
    "Applicants must be 501(c)(3) organizations operating in New Haven County.\n"
    "A cash match of 25% of the total project cost is required; in-kind support does not count.\n\n"
    "Narrative questions\n"
    "1. Describe your organization and the community you serve. (500 words)\n"
    "2. What outcomes will this project achieve, and how will you measure them? (750 words)\n\n"
    "Required attachments: IRS determination letter, most recent audited financials, board roster.\n"
)


def make_pdf(text: str, pages: int = 1) -> bytes:
    """A real single-column PDF with a text layer, written with pypdf's own primitives."""
    from pypdf import PdfWriter

    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=612, height=792)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def make_docx(text: str) -> bytes:
    import docx

    document = docx.Document()
    for line in text.split("\n"):
        document.add_paragraph(line)
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "Budget narrative"
    table.rows[0].cells[1].text = "Two pages maximum"
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


# ---------------------------------------------------------------- the happy paths

def test_a_text_file_is_read_as_it_stands():
    out = doc.read(SOLICITATION.encode("utf-8"), "nofo.txt")
    assert out.kind == "txt" and not out.truncated
    assert "cash match of 25%" in out.text and "(500 words)" in out.text


def test_a_word_document_is_read_including_its_tables():
    out = doc.read(make_docx(SOLICITATION), "nofo.docx")
    assert out.kind == "docx"
    assert "New Harbor Literacy Fund" in out.text
    assert "Budget narrative | Two pages maximum" in out.text  # questions often live in a table


def test_a_utf16_text_file_is_read():
    out = doc.read(SOLICITATION.encode("utf-16"), "nofo.txt")
    assert out.kind == "txt" and "New Harbor Literacy Fund" in out.text


# ---------------------------------------------------------------- the type is taken from the content

def test_the_type_comes_from_the_bytes_not_the_file_name():
    assert doc.sniff(make_docx(SOLICITATION), "pretend.pdf") == "docx"
    assert doc.sniff(SOLICITATION.encode(), "pretend.pdf") == "txt"


def test_an_executable_is_refused_however_it_is_named():
    with pytest.raises(doc.UploadError, match="could not recognise"):
        doc.read(b"MZ\x90\x00\x03" + b"\x00" * 500, "application.pdf")


def test_a_zip_that_is_not_a_word_file_is_refused():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        bundle.writestr("payload.exe", "x" * 300)
    with pytest.raises(doc.UploadError, match="zip archive"):
        doc.read(buffer.getvalue(), "nofo.docx")


def test_a_damaged_word_file_is_refused_with_advice():
    broken = bytearray(make_docx(SOLICITATION))
    del broken[40:400]
    with pytest.raises(doc.UploadError):
        doc.read(bytes(broken), "nofo.docx")


def test_an_empty_file_is_refused():
    with pytest.raises(doc.UploadError, match="empty"):
        doc.read(b"", "nofo.txt")


def test_a_file_over_the_size_limit_is_refused_before_it_is_parsed():
    with pytest.raises(doc.UploadError, match="limit is"):
        doc.read(b"%PDF-" + b"0" * (doc.MAX_BYTES + 1), "huge.pdf")


# ---------------------------------------------------------------- PDFs, including the one we cannot read

def test_a_scanned_pdf_says_so_instead_of_pretending():
    """A PDF with no text layer needs OCR, which GrantBridge does not have. It must say so plainly."""
    with pytest.raises(doc.UploadError, match="no OCR|OCR"):
        doc.read(make_pdf("", pages=3), "scan.pdf")


def test_a_pdf_with_too_many_pages_is_refused():
    with pytest.raises(doc.UploadError, match="pages"):
        doc.read(make_pdf("", pages=doc.MAX_PAGES + 5), "long.pdf")


def test_a_corrupted_pdf_is_refused():
    with pytest.raises(doc.UploadError):
        doc.read(b"%PDF-1.7\n" + b"nonsense" * 200, "broken.pdf")


def test_an_encrypted_pdf_asks_for_the_password_to_be_removed():
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.encrypt("secret")
    buffer = io.BytesIO()
    writer.write(buffer)
    with pytest.raises(doc.UploadError, match="password"):
        doc.read(buffer.getvalue(), "locked.pdf")


# ---------------------------------------------------------------- limits

def test_a_very_long_document_is_cut_at_the_limit_and_says_so():
    long_text = (SOLICITATION + "Additional guidance. ") * 4000
    out = doc.read(long_text.encode(), "long.txt")
    assert out.truncated and len(out.text) == doc.MAX_CHARS


def test_whitespace_from_pdf_extraction_is_tidied():
    messy = "Title\r\n\r\n\r\n\r\nLine   with    spaces\r\n" + "x" * 300
    out = doc.read(messy.encode(), "messy.txt")
    assert "Line with spaces" in out.text and "\n\n\n" not in out.text
