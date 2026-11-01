"""The page-drawing process itself (see renderer.py). Kept apart, with nothing but PyMuPDF, so each drawing
process starts quickly and small: it doesn't load Qt or the rest of the app."""
import pymupdf


def _open(path, password):
    if path is None:  # started ahead of time, or the document was closed: nothing to draw yet
        return None
    doc = pymupdf.open(path)
    if password and doc.needs_pass:
        doc.authenticate(password)
    return doc


def _worker(path, password, conn):
    try:
        _serve(path, password, conn)
    except (EOFError, OSError):
        pass  # the window closed while a page was being drawn


def _serve(path, password, conn):
    def safe_open(p, pw):
        try:
            return _open(p, pw)
        except Exception:
            return None  # e.g. an outdated working copy already tidied away; a newer one follows

    doc = safe_open(path, password)
    streams = {}  # page index -> the stand-in content stream given by "patch"
    while True:
        msg = conn.recv()
        if msg is None:
            return
        if msg[0] == "open":  # switch to an edited copy of the document
            if doc:
                doc.close()
            doc = safe_open(msg[1], msg[2])
            streams = {}
            continue
        if msg[0] == "patch":  # a page's drawing instructions changed (moving things in Edit)
            _, index, data = msg
            try:
                if index not in streams:
                    streams[index] = doc.get_new_xref()
                    doc.update_object(streams[index], "<<>>")
                    doc.update_stream(streams[index], data)
                    doc[index].set_contents(streams[index])
                else:
                    doc.update_stream(streams[index], data)
            except Exception:
                pass
            continue
        if doc is None:
            conn.send(None)
            continue
        _, index, zoom, hide_fields, clip = msg
        try:
            page = doc[index]
            hidden = _hide_fields(doc, page) if hide_fields else []
            try:
                pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False,
                                      clip=pymupdf.Rect(clip) if clip else None)
            finally:
                for xref, flags in hidden:
                    doc.xref_set_key(xref, "F", flags)
            conn.send((pix.width, pix.height, pix.stride, pix.samples))
        except Exception:
            conn.send(None)


# Form fields the Fill & Sign screen puts its own boxes over (signature fields and buttons stay).
FILLABLE = (pymupdf.PDF_WIDGET_TYPE_TEXT, pymupdf.PDF_WIDGET_TYPE_CHECKBOX, pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON,
            pymupdf.PDF_WIDGET_TYPE_COMBOBOX, pymupdf.PDF_WIDGET_TYPE_LISTBOX)


def _hide_fields(doc, page):
    """Mark the page's fillable fields hidden for one drawing; returns what to put back."""
    hidden = []
    for w in page.widgets():
        if w.field_type in FILLABLE:
            kind, value = doc.xref_get_key(w.xref, "F")
            flags = int(value) if kind == "int" else 0
            hidden.append((w.xref, value if kind != "null" else "null"))
            doc.xref_set_key(w.xref, "F", str(flags | 2))  # 2 = hidden
    return hidden
