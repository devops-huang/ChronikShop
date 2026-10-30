"""PDF plumbing: page rendering, text layer access, rotation, crop extraction.

Kept deliberately small and dependency-light (PyMuPDF only) so it can run
inside an Azure Container App or as an Azure Function without surprises.
"""

from __future__ import annotations

import base64
import hashlib
import io
from dataclasses import dataclass
from pathlib import Path

import pymupdf


@dataclass
class PageView:
    page_no: int                 # 1-based
    text: str
    has_text_layer: bool
    width_pt: float
    height_pt: float
    image_count: int


class Document:
    """Thin wrapper over a PDF that the pipeline can treat as immutable."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._doc = pymupdf.open(self.path)
        self.sha256 = hashlib.sha256(self.path.read_bytes()).hexdigest()

    # -- lifecycle -------------------------------------------------------- #
    def close(self) -> None:
        self._doc.close()

    def __enter__(self) -> "Document":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- pages ------------------------------------------------------------ #
    @property
    def page_count(self) -> int:
        return self._doc.page_count

    def page_view(self, page_no: int) -> PageView:
        p = self._doc[page_no - 1]
        text = p.get_text("text") or ""
        return PageView(
            page_no=page_no,
            text=text,
            has_text_layer=len(text.strip()) > 40,
            width_pt=p.rect.width,
            height_pt=p.rect.height,
            image_count=len(p.get_images(full=True)),
        )

    def page_views(self) -> list[PageView]:
        return [self.page_view(i) for i in range(1, self.page_count + 1)]

    def all_text(self) -> str:
        return "\n".join(v.text for v in self.page_views())

    # -- rotation --------------------------------------------------------- #
    def detect_rotation_from_text(self, page_no: int) -> int:
        """Detect 90/270 rotation from the text layer by measuring line direction.

        Works for born-digital PDFs where the producer emitted rotated text.
        Scanned pages have no text layer; there the vision model's rotation hint
        is used instead (see :mod:`chronik.pipeline`).
        """
        p = self._doc[page_no - 1]
        spans: list[tuple[float, float]] = []
        for block in p.get_text("dict").get("blocks", []):
            for line in block.get("lines", []):
                x0, y0, x1, y1 = line["bbox"]
                spans.append((x1 - x0, y1 - y0))
        if not spans:
            return 0
        horizontal = sum(1 for w, h in spans if w >= h)
        vertical = sum(1 for w, h in spans if h > w)
        if vertical > horizontal * 2:
            return 90
        return 0

    def render_page_png(
        self,
        page_no: int,
        rotation: int = 0,
        dpi: int = 200,
        clip: tuple[float, float, float, float] | None = None,
    ) -> bytes:
        p = self._doc[page_no - 1]
        matrix = pymupdf.Matrix(dpi / 72, dpi / 72) * pymupdf.Matrix(rotation)
        kwargs = {"matrix": matrix, "alpha": False}
        if clip is not None:
            kwargs["clip"] = pymupdf.Rect(*clip)
        pix = p.get_pixmap(**kwargs)
        return pix.tobytes("png")

    def crop_around_text(
        self,
        page_no: int,
        quote: str,
        pad: float = 24.0,
        dpi: int = 160,
    ) -> bytes | None:
        """Crop the page region around ``quote`` — used by the review sheet."""
        p = self._doc[page_no - 1]
        needle = (quote or "").strip()
        if not needle:
            return None
        rects = p.search_for(needle[:80])
        if not rects:
            # fall back to the longest word-ish token
            for token in sorted(needle.split(), key=len, reverse=True)[:3]:
                if len(token) < 3:
                    continue
                rects = p.search_for(token)
                if rects:
                    break
        if not rects:
            return None
        r = pymupdf.Rect(rects[0])
        for extra in rects[1:]:
            r |= extra
        r = pymupdf.Rect(r.x0 - pad, r.y0 - pad * 1.6, r.x1 + pad, r.y1 + pad * 0.6)
        r &= p.rect
        if r.is_empty:
            return None
        return self.render_page_png(page_no, dpi=dpi, clip=(r.x0, r.y0, r.x1, r.y1))

    def crop_by_bbox(
        self,
        page_no: int,
        bbox: list[float],
        pad_pt: float = 7.0,
        dpi: int = 150,
        rotation: int = 0,
    ) -> bytes | None:
        """Render a normalised bbox with a little context.

        The bbox arrives in the coordinates of the *upright* page the model was
        shown. When we had to rotate a sideways fax, that view is rotated
        relative to the PDF page, so the box is mapped back through the inverse
        of the render matrix before clipping.
        """
        if not bbox or len(bbox) != 4:
            return None
        p = self._doc[page_no - 1]
        w, h = p.rect.width, p.rect.height
        if rotation % 360 in (90, 270):
            w, h = h, w
        x0, y0, x1, y1 = bbox
        rect = pymupdf.Rect(x0 * w - pad_pt, y0 * h - pad_pt * 1.1, x1 * w + pad_pt, y1 * h + pad_pt * 0.5)
        if rotation % 360 in (90, 180, 270):
            # inverse of the render mapping (verified against get_pixmap):
            #   90 : (x,y) -> (H-y, x)      270: (x,y) -> (y, W-x)
            #  180 : (x,y) -> (W-x, H-y)
            PW, PH = p.rect.width, p.rect.height
            corners = [(rect.x0, rect.y0), (rect.x1, rect.y0), (rect.x0, rect.y1), (rect.x1, rect.y1)]
            mapped = []
            for cx, cy in corners:
                if rotation == 90:
                    mapped.append((cy, PH - cx))
                elif rotation == 270:
                    mapped.append((PW - cy, cx))
                else:
                    mapped.append((PW - cx, PH - cy))
            xs = [m[0] for m in mapped]
            ys = [m[1] for m in mapped]
            rect = pymupdf.Rect(min(xs), min(ys), max(xs), max(ys))
        rect &= p.rect
        if rect.is_empty or rect.width < 4 or rect.height < 4:
            return None
        return self.render_page_png(page_no, rotation, dpi=dpi, clip=(rect.x0, rect.y0, rect.x1, rect.y1))

    def page_thumbnail_b64(self, page_no: int, rotation: int = 0, dpi: int = 110) -> str:
        return base64.b64encode(self.render_page_png(page_no, rotation, dpi)).decode()


def png_b64(data: bytes | None) -> str | None:
    if not data:
        return None
    return base64.b64encode(data).decode()


def sniff_pdf(path: Path) -> bool:
    try:
        with open(path, "rb") as fh:
            return fh.read(5) == b"%PDF-"
    except OSError:
        return False
