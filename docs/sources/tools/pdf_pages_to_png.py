"""Turn an image-only PDF (each page one embedded picture) into one PNG per page, so an agent can LOOK at it.

    python3 docs/sources/tools/pdf_pages_to_png.py deck.pdf out_dir

Why this exists: the decks are image-only PDFs. They have no text layer, PyPDF2's own image export returns
noise for them (it does not undo the PNG row predictor), and the Read tool cannot rasterise a PDF unless
`pdftoppm` is installed — which it is not on this machine. So the raw image streams are decoded here.

Needs `PyPDF2` (present in the system python3, absent from the project venv) and nothing else: the PNG is
written by hand. Handles the case that occurs in these decks — FlateDecode, 8-bit RGB, PNG predictors 10-15.
It ignores any soft mask, so a page with transparency may differ slightly from the original. For a PDF that
is real text and vector drawings (the Candlestick Bible) use `render_pdf_pages.swift` instead.
"""
import os
import struct
import sys
import zlib

import PyPDF2


def unpredict(data: bytes, width: int, bpp: int) -> bytes:
    stride = width * bpp
    rows = len(data) // (stride + 1)
    out = bytearray()
    prev = bytearray(stride)
    for r in range(rows):
        kind = data[r * (stride + 1)]
        line = bytearray(data[r * (stride + 1) + 1 : (r + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            if kind == 1:
                line[i] = (line[i] + a) & 255
            elif kind == 2:
                line[i] = (line[i] + b) & 255
            elif kind == 3:
                line[i] = (line[i] + ((a + b) >> 1)) & 255
            elif kind == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        out += line
        prev = line
    return bytes(out)


def write_png(path: str, width: int, height: int, rgb: bytes) -> None:
    def chunk(tag: bytes, body: bytes) -> bytes:
        crc = zlib.crc32(tag + body) & 0xFFFFFFFF
        return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", crc)

    stride = width * 3
    raw = b"".join(b"\x00" + rgb[y * stride : (y + 1) * stride] for y in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    with open(path, "wb") as handle:
        handle.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def main(pdf: str, out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    reader = PyPDF2.PdfReader(pdf)
    for number, page in enumerate(reader.pages, 1):
        image = list(page["/Resources"]["/XObject"].values())[0].get_object()
        width, height = image["/Width"], image["/Height"]
        parms = image.get("/DecodeParms", {})
        parms = parms.get_object() if hasattr(parms, "get_object") else parms
        data = zlib.decompress(image._data)
        if parms.get("/Predictor", 1) >= 10:
            data = unpredict(data, width, 3)
        write_png(os.path.join(out_dir, f"p{number:02d}.png"), width, height, data)
    print(f"{len(reader.pages)} page(s) written to {out_dir}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
