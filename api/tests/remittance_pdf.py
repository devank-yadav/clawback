"""A text-only PDF writer for the sample remittance and the remittance tests: no dependencies, same bytes every time.

Each line of text is one line of Courier on a landscape letter page, the way a distributor's AP system prints a
remittance advice. The text must be plain ASCII.

    python -m api.tests.remittance_pdf    # rewrites data/samples/remittances/northmart-march-2026.pdf from its .txt
"""

from __future__ import annotations

from pathlib import Path

SAMPLES = Path(__file__).resolve().parents[2] / "data" / "samples" / "remittances"
SAMPLE_TXT = SAMPLES / "northmart-march-2026.txt"
SAMPLE_PDF = SAMPLES / "northmart-march-2026.pdf"

WIDTH, HEIGHT, MARGIN = 792, 612, 36
FONT_SIZE, LEADING = 8, 11


def _escape(line: str) -> str:
    return line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def pdf_bytes(text: str) -> bytes:
    """One or more pages of `text`, a line per row of Courier."""
    text.encode("ascii")  # raises on anything the standard font can't show as written
    lines = text.splitlines()
    per_page = (HEIGHT - 2 * MARGIN) // LEADING
    pages = [lines[i:i + per_page] for i in range(0, len(lines), per_page)] or [[]]
    objects: list[bytes] = [b"<< /Type /Catalog /Pages 2 0 R >>", b"",
                            b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>"]
    kids = []
    for page in pages:
        body = "".join(f"({_escape(line)}) Tj T*\n" for line in page)
        stream = f"BT /F1 {FONT_SIZE} Tf {LEADING} TL {MARGIN} {HEIGHT - MARGIN - FONT_SIZE} Td\n{body}ET".encode()
        objects.append(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream))
        objects.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] /Resources << /Font << /F1 3 0 R >> >> "
                       b"/Contents %d 0 R >>" % (WIDTH, HEIGHT, len(objects)))
        kids.append(len(objects))
    objects[1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (" ".join(f"{k} 0 R" for k in kids).encode(), len(kids))
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for n, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (n, obj)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return bytes(out)


def main() -> int:
    SAMPLE_PDF.write_bytes(pdf_bytes(SAMPLE_TXT.read_text()))
    print(f"wrote {SAMPLE_PDF} ({SAMPLE_PDF.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
