"""The review sheet must be able to point at the value on a sideways fax.

Regression guard for the bbox -> PDF coordinate mapping, which is easy to get
backwards and impossible to eyeball once the image is 96 px tall.
"""

import io

import pymupdf
from PIL import Image

from chronik.pdfutil import Document
from samples.rasterize import build_image_pdf


def _marker_pdf(path):
    doc = pymupdf.open()
    page = doc.new_page(width=400, height=600)
    page.draw_rect(pymupdf.Rect(40, 80, 200, 110), color=(0, 0, 0), fill=(0, 0, 0))
    doc.save(path)
    return path


def _dark_fraction(png: bytes) -> float:
    img = Image.open(io.BytesIO(png)).convert("L")
    px = list(img.get_flattened_data()) if hasattr(img, "get_flattened_data") else list(img.getdata())
    return sum(1 for v in px if v < 90) / max(len(px), 1)


def _locate(page, rotation: int):
    pix = page.get_pixmap(matrix=pymupdf.Matrix(rotation), alpha=False)
    s, n, w, h = pix.samples, pix.n, pix.width, pix.height
    xs, ys = [], []
    for y in range(h):
        row = y * w * n
        for x in range(w):
            if s[row + x * n] < 90:
                xs.append(x)
                ys.append(y)
    assert xs, "marker vanished"
    return [min(xs) / w, min(ys) / h, max(xs) / w, max(ys) / h]


def test_bbox_crop_on_sideways_page(tmp_path):
    src = _marker_pdf(tmp_path / "marker.pdf")
    out = build_image_pdf(src, tmp_path / "marker_rot.pdf", rotations={1: 90}, quality="scan")
    doc = pymupdf.open(out)
    bbox = _locate(doc[0], 90)  # what the model would report from the upright view

    with Document(out) as d:
        png = d.crop_by_bbox(1, bbox, rotation=90, dpi=100, pad_pt=6)
    assert png is not None
    # the crop should be mostly the marker, i.e. the mapping landed on it
    assert _dark_fraction(png) > 0.25


def test_unrotated_bbox_crop(tmp_path):
    src = _marker_pdf(tmp_path / "marker2.pdf")
    doc = pymupdf.open(src)
    bbox = _locate(doc[0], 0)
    with Document(src) as d:
        png = d.crop_by_bbox(1, bbox, dpi=100, pad_pt=6)
    assert _dark_fraction(png) > 0.25
