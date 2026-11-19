"""Render PDF drawing sheets to PNG so they can be read visually.

usage: python pdf_to_png.py <out_dir> <dpi> <file.pdf> [more.pdf ...]
       (dpi 110 is enough to read a full A1/A0 sheet; use 200-300 + crop for small text)

Run WITHOUT `-I`/`-s`: PyMuPDF (fitz) is installed in the user site-packages.
"""
import os, sys
import fitz  # PyMuPDF

out, dpi = sys.argv[1], int(sys.argv[2])
os.makedirs(out, exist_ok=True)
for path in sys.argv[3:]:
    doc = fitz.open(path)
    stem = os.path.splitext(os.path.basename(path))[0]
    for i, page in enumerate(doc):
        dst = os.path.join(out, f"{stem}_p{i}.png")
        page.get_pixmap(dpi=dpi).save(dst)
        print(dst, page.rect.width, "x", page.rect.height, "pt")
