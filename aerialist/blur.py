"""Blur: hides part of a page (names, numbers, faces in a screenshot) behind a blurred copy of it.
When it is written into the PDF, whatever was under the box (text, picture pixels, small drawings)
is removed first, so the hidden words can't be copied, searched or recovered from the file."""
import pymupdf
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage

SCALE = 2  # pixels per point in the blurred picture written into the PDF


def cell_pt(rect):
    """How coarse the blur is, in points: coarser for bigger boxes, so big headings are hidden too."""
    return max(6.0, min(16.0, min(rect.width, rect.height) / 2.5))


def blur_image(img, cell_px):
    """A heavily blurred copy of img: shrunk to a few pixels per cell, then smoothly enlarged twice."""
    w, h = img.width(), img.height()
    if w < 1 or h < 1:
        return img
    out = img
    for step in (cell_px, cell_px / 2, cell_px / 3, cell_px / 4):
        sw, sh = max(1, round(w / max(1.0, step))), max(1, round(h / max(1.0, step)))
        out = out.scaled(sw, sh, Qt.IgnoreAspectRatio, Qt.SmoothTransformation) \
                 .scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    return out


def render(page, rect, scale):
    """The page inside rect (on-screen page coordinates) as a QImage, blurred."""
    clip = pymupdf.Rect(rect) & page.rect
    if clip.is_empty:
        return None
    pix = page.get_pixmap(clip=clip, matrix=pymupdf.Matrix(scale, scale), alpha=False)
    img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888).copy()
    return blur_image(img, cell_pt(rect) * scale)


def jpeg(img):
    from .overlay import jpeg_or_png
    return jpeg_or_png(img.convertToFormat(QImage.Format_RGB32))


def write(page, rect):
    """Blur rect (on-screen page coordinates) into the page for good."""
    img = render(page, rect, SCALE)
    if img is None:
        return
    from .overlay import to_page
    r = to_page(page, pymupdf.Rect(rect) & page.rect)
    page.add_redact_annot(r, fill=False)
    page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_PIXELS,
                          graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED)
    page.insert_image(r, stream=jpeg(img), rotate=page.rotation)
