"""Workarounds for PDFs whose text positions are broken.

Some PDFs (e.g. manuals exported as pictures of the words) draw every line of text as a picture and
carry the searchable text as hidden "actual text" whose letters all sit at the picture's corner with
no width, so search matches come back as zero-width boxes: nothing to highlight. For those, the
match is placed inside the picture it belongs to, in proportion to where the word falls in that
picture's text (measured with Helvetica widths), which lands on or very near the word."""
import xml.etree.ElementTree as ET

import pymupdf

_helv = None


def _length(text):
    global _helv
    if _helv is None:
        _helv = pymupdf.Font("helv")
    return _helv.text_length(text, 10)


def _groups(page):
    """Runs of zero-width letters that share one spot: [(x, y0, y1, text)]."""
    out = []
    root = ET.fromstring(page.get_textpage().extractXML())
    for line in root.iter("line"):
        run, key = [], None
        for ch in line.iter("char"):
            q = [float(v) for v in ch.get("quad").split()]
            k = (q[0], q[1], q[5]) if abs(q[2] - q[0]) < 0.01 else None
            if k != key and run:
                if key:
                    out.append((*key, "".join(run)))
                run = []
            key = k
            run.append(ch.get("c"))
        if run and key:
            out.append((*key, "".join(run)))
    return out


def _picture_at(page, x, y0, y1):
    best = None
    for info in page.get_image_info():
        b = pymupdf.Rect(info["bbox"])
        if abs(b.x0 - x) < 1.5 and y0 - 3 < b.y0 < y1:
            if best is None or abs(b.y0 - y0) < abs(best.y0 - y0):
                best = b
    return best


def fix_hits(page, query, rects):
    """Replace zero-width search results with estimated boxes. Rects are in unturned page space."""
    if all(r.width > 0.5 for r in rects):
        return rects
    groups = _groups(page)
    used = {}  # group index -> how many of its matches are placed already
    out = []
    q = query.lower()
    for r in rects:
        if r.width > 0.5:
            out.append(r)
            continue
        box = None
        for gi, (x, y0, y1, text) in enumerate(groups):
            if abs(x - r.x0) > 0.5 or abs(y0 - r.y0) > 0.5:
                continue
            starts, s = [], text.lower().find(q)
            while s >= 0:
                starts.append(s)
                s = text.lower().find(q, s + 1)
            n = used.get(gi, 0)
            if n >= len(starts):
                continue
            used[gi] = n + 1
            pic = _picture_at(page, x, y0, y1)
            whole = _length(text.rstrip()) or 1
            if pic is not None:
                a = pic.x0 + pic.width * _length(text[:starts[n]]) / whole
                b = pic.x0 + pic.width * _length(text[:starts[n] + len(q)]) / whole
                box = pymupdf.Rect(max(pic.x0, a - 3), pic.y0, min(b + 1, pic.x1), pic.y1)
            break
        if box is None:  # can't place it: at least mark the start of the line
            box = pymupdf.Rect(r.x0, r.y0, r.x0 + max(6, r.height * 2), r.y1)
        out.append(box)
    return out
