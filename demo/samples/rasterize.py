"""Turn a born-digital PDF into a realistic (bad) fax / scan.

Real inboxes are full of these: no text layer, speckled background, skewed,
sometimes fed sideways. Drawing samples with a text layer would hide all of the
hard parts, so the demos go through this filter.

    python -m samples.rasterize
"""

from __future__ import annotations

import io
import random
from pathlib import Path

import pymupdf
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

random.seed(11)


def _speckle(img: Image.Image, amount: int = 900, dark: int = 40) -> Image.Image:
    px = img.load()
    w, h = img.size
    for _ in range(amount):
        x, y = random.randrange(w), random.randrange(h)
        v = random.randint(dark, dark + 60)
        px[x, y] = v
    # thin horizontal banding, as fax machines produce
    for _ in range(6):
        y = random.randrange(h)
        for x in range(0, w, 2):
            if random.random() < 0.6:
                px[x, y] = min(int(px[x, y]) + 25, 255)
    return img


def faxify_page(png: bytes, rotation: int = 0, dpi: int = 200, quality: str = "fax") -> bytes:
    img = Image.open(io.BytesIO(png)).convert("L")
    if rotation:
        # content fed sideways into the scanner: rotate the content and fit it
        # onto the portrait bed, leaving the white bands a sideways sheet
        # really produces.
        rotated = img.rotate(-rotation, expand=True)
        canvas = Image.new("L", img.size, 255)
        scale = min(img.width / rotated.width, img.height / rotated.height) * 0.92
        size = (int(rotated.width * scale), int(rotated.height * scale))
        rotated = rotated.resize(size, Image.LANCZOS)
        canvas.paste(rotated, ((img.width - size[0]) // 2, (img.height - size[1]) // 2))
        img = canvas

    if quality == "fax":
        img = img.filter(ImageFilter.GaussianBlur(0.6))
        img = ImageEnhance.Contrast(img).enhance(0.82)
        img = _speckle(img)
        img = img.filter(ImageFilter.MinFilter(3))  # thickens the strokes
    else:  # phone-camera / flatbed scan of handwriting
        img = img.filter(ImageFilter.GaussianBlur(0.35))
        img = ImageEnhance.Contrast(img).enhance(0.9)
        img = img.rotate(random.uniform(-1.2, 1.2), resample=Image.BICUBIC, fillcolor=255)
    return _to_png(img)


def _to_png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def build_image_pdf(
    src_pdf: Path,
    dst_pdf: Path,
    rotations: dict[int, int] | None = None,
    quality: str = "fax",
    dpi: int = 200,
) -> Path:
    rotations = rotations or {}
    src = pymupdf.open(src_pdf)
    out = pymupdf.open()
    for i, page in enumerate(src, start=1):
        png = page.get_pixmap(dpi=dpi).tobytes("png")
        processed = faxify_page(png, rotations.get(i, 0), dpi=dpi, quality=quality)
        new = out.new_page(width=page.rect.width, height=page.rect.height)
        new.insert_image(new.rect, stream=processed)
    out.save(dst_pdf, deflate=True, garbage=3)
    out.close()
    src.close()
    return dst_pdf


if __name__ == "__main__":
    base = Path(__file__).resolve().parent
    tmp = base / "_textlayer"
    tmp.mkdir(exist_ok=True)

    from .build_samples import clean_po, fax_multipage, handwritten_po

    fax_src = tmp / "fax_src.pdf"
    fax_multipage(fax_src)
    build_image_pdf(fax_src, base / "fax_multipage.pdf", rotations={2: 90}, quality="fax")

    hand_src = tmp / "hand_src.pdf"
    handwritten_po(hand_src)
    build_image_pdf(hand_src, base / "handwritten_po.pdf", quality="scan")

    for p in sorted(base.glob("*.pdf")):
        import pymupdf as f

        d = f.open(p)
        print(f"{p.name:22s} pages={d.page_count} text_chars={sum(len(pg.get_text()) for pg in d)}")
