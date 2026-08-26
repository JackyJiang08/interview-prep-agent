"""Write the committed synthetic resume PDF, and build PDFs for the tests.

A minimal writer rather than a library: the fixture must be tiny, regenerable
from this file, and free of any real person's details. Text goes through the
standard Helvetica font in WinAnsi encoding, which is what lets the bullet
character survive extraction.

Run as a script to regenerate ``resume_synthetic.pdf`` next to this file.
"""

from __future__ import annotations

from pathlib import Path

Line = tuple[str, int]  # text, font size

RESUME_PAGES: list[list[Line]] = [
    [
        ("JORDAN EXAMPLE", 16),
        ("Data Analyst - Springfield", 11),
        ("", 11),
        ("EXPERIENCE", 13),
        ("Data Analyst, Example Co. (2022 - present)", 11),
        ("• Owned funnel analysis for a subscription product, writing SQL", 11),
        ("against a warehouse of roughly 40 million events.", 11),
        ("• Built scheduled ETL pipelines loading application logs into a", 11),
        ("cloud data warehouse, with row-count and freshness checks.", 11),
        ("", 11),
        ("Page 1 of 2", 9),
    ],
    [
        ("Jordan Example - Resume", 9),
        ("Skills", 13),
        ("• SQL, Python, pandas, Airflow", 11),
        ("• Funnel analysis, dashboarding, experiment readouts", 11),
        ("", 11),
        ("Page 2 of 2", 9),
    ],
]


def build_pdf(pages: list[list[Line]]) -> bytes:
    """Assemble a valid single-font PDF from lines of text per page.

    An empty page list entry produces a page with no text at all — the
    no-text-layer case the tests need.
    """
    objects: list[bytes] = []

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    pages_id = len(objects) + 1 + 2 * len(pages)  # allocated after the pages
    page_ids: list[int] = []
    for lines in pages:
        content = _content_stream(lines)
        stream = add(
            b"<< /Length "
            + str(len(content)).encode()
            + b" >>\nstream\n"
            + content
            + b"\nendstream"
        )
        page = add(
            b"<< /Type /Page /Parent " + str(pages_id).encode() + b" 0 R "
            b"/MediaBox [0 0 612 792] /Resources << /Font << /F1 "
            + str(font).encode()
            + b" 0 R >> >> "
            b"/Contents " + str(stream).encode() + b" 0 R >>"
        )
        page_ids.append(page)
    kids = b" ".join(str(page).encode() + b" 0 R" for page in page_ids)
    assert (
        add(b"<< /Type /Pages /Kids [" + kids + b"] /Count " + str(len(page_ids)).encode() + b" >>")
        == pages_id
    )
    catalog = add(b"<< /Type /Catalog /Pages " + str(pages_id).encode() + b" 0 R >>")

    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += str(number).encode() + b" 0 obj\n" + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 " + str(len(objects) + 1).encode() + b"\n0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        b"trailer\n<< /Size "
        + str(len(objects) + 1).encode()
        + b" /Root "
        + str(catalog).encode()
        + b" 0 R >>\n"
        b"startxref\n" + str(xref).encode() + b"\n%%EOF\n"
    )
    return bytes(out)


def _content_stream(lines: list[Line]) -> bytes:
    if not lines:
        return b""
    parts = [b"BT", b"72 740 Td"]
    for text, size in lines:
        parts.append(b"/F1 " + str(size).encode() + b" Tf")
        if text:
            parts.append(b"(" + _escape(text) + b") Tj")
        parts.append(b"0 " + str(-(size + 5)).encode() + b" Td")
    parts.append(b"ET")
    return b"\n".join(parts)


def _escape(text: str) -> bytes:
    encoded = text.encode("cp1252")
    return encoded.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


if __name__ == "__main__":
    target = Path(__file__).with_name("resume_synthetic.pdf")
    target.write_bytes(build_pdf(RESUME_PAGES))
    print(f"wrote {target} ({target.stat().st_size} bytes)")
