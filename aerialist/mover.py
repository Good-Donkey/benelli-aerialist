"""Edit PDF's Move tool: pick up lines, shapes and text that are already in the PDF and move, turn,
resize or delete them, like Nitro's object editing.

Click something to select it (Shift-click adds more), or drag a box round several things. Drag
the selection to move it, a corner handle to resize it, or the round handle above it to turn it
(Shift: in 15° steps); nudge it with the arrow keys, or press Delete. Changes show at once and are
written into the PDF with everything else on Done.
"""
import math

import pymupdf
from PySide6.QtCore import Qt, QObject, QEvent, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QImage, QTransform, QPolygonF
from PySide6.QtWidgets import QWidget, QApplication, QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox, QComboBox

from . import theme
from .content import PageContent, set_page_stream

MANY = 400  # above this many selected things, only the outline round them all is drawn
HANDLE = 7  # corner handle size, pixels
TURN_GAP = 22  # how far above the selection the turn handle sits, pixels
CORNERS = {"nw": ("x0", "y0", "x1", "y1"), "ne": ("x1", "y0", "x0", "y1"),
           "sw": ("x0", "y1", "x1", "y0"), "se": ("x1", "y1", "x0", "y0")}


def _qrect(r, z):
    return QRectF(r.x0 * z, r.y0 * z, r.width * z, r.height * z)


def _qt(m, z):
    """A change in page points as a painter transform in pixels."""
    return QTransform(m.a, m.b, m.c, m.d, m.e * z, m.f * z)


def handle_spots(u, z):
    """Where the handles of a selection box u sit (page points): corners, and the turn handle above."""
    pad = 4 / z
    r = pymupdf.Rect(u.x0 - pad, u.y0 - pad, u.x1 + pad, u.y1 + pad)
    spots = {k: pymupdf.Point(getattr(r, a), getattr(r, b)) for k, (a, b, _, _) in CORNERS.items()}
    spots["turn"] = pymupdf.Point((r.x0 + r.x1) / 2, r.y0 - TURN_GAP / z)
    return r, spots


class Layer(QWidget):
    """Drawn over one page: the selection, the box being dragged out, and the picture of what is
    being moved."""

    def __init__(self, mover, label):
        super().__init__(label)
        self.mover, self.label = mover, label
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setGeometry(label.rect())
        label.installEventFilter(self)
        self.show()

    def eventFilter(self, obj, e):
        if e.type() == QEvent.Resize:
            self.setGeometry(self.label.rect())
        return False

    def paintEvent(self, e):
        m = self.mover
        i = self.label.index
        z = m.view.zoom
        p = QPainter(self)
        accent = QColor(theme.ACCENT_FILL)
        preview = m.preview if m.preview and m.preview["page"] == i else None
        if preview:
            if preview["patch"] is not None:
                p.drawImage(_qrect(preview["box"], z), preview["patch"])
            if preview["ghost"] is not None:
                p.save()
                p.setRenderHint(QPainter.SmoothPixmapTransform)
                p.setTransform(_qt(preview.get("xform") or pymupdf.Matrix(1, 0, 0, 1, *preview["offset"]), z), True)
                p.drawImage(_qrect(preview["box"], z), preview["ghost"])
                p.restore()
        xform = m.live_xform()
        if m.page == i and m.selection and xform is not None:  # being turned or resized: its outline follows
            u = m.union()
            p.setPen(QPen(accent, 1.5, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            corners = [pt * xform for pt in (u.tl, u.tr, u.br, u.bl)]
            p.drawPolygon(QPolygonF([QPointF(c.x * z, c.y * z) for c in corners]))
        elif m.page == i and m.selection:
            dx, dy = m.drag_offset()
            boxes = [m.box(k) for k in m.selection]
            p.setBrush(Qt.NoBrush)
            if len(boxes) <= MANY:
                fill = QColor(accent)
                fill.setAlpha(28 if len(boxes) == 1 else 0)
                edge = QColor(accent)
                edge.setAlpha(255 if len(boxes) == 1 else 110)
                p.setPen(QPen(edge, 1))
                for b in boxes:
                    r = _qrect(b, z).translated(dx * z, dy * z).adjusted(-1, -1, 1, 1)
                    p.fillRect(r, fill)
                    p.drawRect(r)
            if len(boxes) > 1:
                u = boxes[0]
                for b in boxes[1:]:
                    u = u | b
                pen = QPen(accent, 1.5, Qt.DashLine)
                p.setPen(pen)
                p.drawRect(_qrect(u, z).translated(dx * z, dy * z).adjusted(-4, -4, 4, 4))
            if not (dx or dy):  # handles: corners resize, the round one above turns
                r, spots = handle_spots(m.union(), z)
                p.setPen(QPen(accent, 1))
                top = spots["turn"]
                p.drawLine(QPointF(top.x * z, top.y * z), QPointF(top.x * z, r.y0 * z))
                p.setBrush(QColor("white"))
                for k, pt in spots.items():
                    if k == "turn":
                        p.drawEllipse(QPointF(pt.x * z, pt.y * z), 5, 5)
                    else:
                        p.drawRect(QRectF(pt.x * z - HANDLE / 2, pt.y * z - HANDLE / 2, HANDLE, HANDLE))
        if m.hover is not None and m.hover[0] == i and not (m.page == i and m.hover[1] in m.selection):
            pen = QPen(accent, 1, Qt.DashLine)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawRect(_qrect(m.box(m.hover[1], m.hover[0]), z).adjusted(-2, -2, 2, 2))
        if m.band is not None and m.band[0] == i:
            r = m.band[1]
            fill = QColor(accent)
            fill.setAlpha(30)
            p.fillRect(_qrect(r, z), fill)
            p.setPen(QPen(accent, 1, Qt.DashLine))
            p.drawRect(_qrect(r, z))
        p.end()


class ContentMover(QObject):
    """The Move tool's state for one Edit session."""

    def __init__(self, session):
        super().__init__()
        self.session = session
        self.view = session.view
        self.work = None  # a private copy of the document, for drawing previews
        self.pages = {}  # page index -> PageContent
        self.layers = {}
        self.page, self.selection = None, set()
        self.hover = None  # (page, object) under the mouse
        self.band = None  # (page, Rect) being dragged out
        self.preview = None
        self._press = None
        self._active = False
        self.view.page_drawn.connect(self._page_drawn)

    # ---- lifecycle ----
    def activate(self, on):
        if on == self._active:
            return
        self._active = on
        if on:
            QApplication.instance().installEventFilter(self)
        else:
            QApplication.instance().removeEventFilter(self)
            self.hover = self.band = None
            self.clear()

    def stop(self, revert=True):
        """End the session; if revert, put the pages back as they were."""
        self.activate(False)
        if revert:
            for i, pc in self.pages.items():
                if pc.changed():
                    self.view.patch_page(i, pc.data)
        for layer in self.layers.values():
            try:
                layer.deleteLater()
            except RuntimeError:
                pass
        self.layers, self.pages = {}, {}
        self.preview = None
        self.page, self.selection = None, set()
        if self.work is not None:
            self.work.close()
            self.work = None

    def pending(self):
        return sum(len(pc.moves) + len(pc.removed) for pc in self.pages.values())

    def specs(self):
        """(page index, writer) for each changed page, for writing into the real document."""
        out = []
        for i, pc in self.pages.items():
            if pc.changed():
                data = pc.stream()
                out.append((i, lambda page, data=data: set_page_stream(page, data)))
        return out

    def state(self):
        """The moves and removals on each page (for Undo), in a fixed order so equal states compare equal."""
        return {i: (sorted(pc.moves.items()), sorted(pc.removed)) for i, pc in sorted(self.pages.items())}

    def restore(self, state):
        state = state or {}
        for i, pc in self.pages.items():
            moves, removed = state.get(i, ([], []))
            if (sorted(pc.moves.items()), sorted(pc.removed)) != (moves, removed):
                pc.set_state((dict(moves), set(removed)))
                self._commit(i)
        if self.page is not None:
            pc = self.pages[self.page]
            self.selection -= pc.removed
            self._update(self.page)

    # ---- pages ----
    def content(self, i):
        if i not in self.pages:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                if self.work is None:
                    self.work = pymupdf.open(self.view.render_path)
                    if self.work.needs_pass and self.view.render_password:
                        self.work.authenticate(self.view.render_password)
                self.pages[i] = PageContent(self.work[i])
                pc = self.pages[i]
                pc.stream_xref = None
                pc.cur = [pc.boxes[k] for k in range(len(pc.objs))]
            finally:
                QApplication.restoreOverrideCursor()
        return self.pages[i]

    def box(self, k, i=None):
        return self.pages[self.page if i is None else i].cur[k]

    def _refresh_boxes(self, i):
        pc = self.pages[i]
        pc.cur = [pc.view_box(k) for k in range(len(pc.objs))]

    def layer(self, i):
        lbl = self.view.labels[i]
        layer = self.layers.get(i)
        if layer is None or layer.label is not lbl:
            layer = self.layers[i] = Layer(self, lbl)
        layer.raise_()
        return layer

    def _update(self, i):
        if i is not None and 0 <= i < len(self.view.labels):
            self.layer(i).update()

    def _set_stream(self, i, data):
        """Point the private copy's page at these instructions (for preview pictures)."""
        pc = self.pages[i]
        page = self.work[i]
        if pc.stream_xref is None:
            pc.stream_xref = self.work.get_new_xref()
            self.work.update_object(pc.stream_xref, "<<>>")
            self.work.update_stream(pc.stream_xref, data)
            page.set_contents(pc.stream_xref)
        else:
            self.work.update_stream(pc.stream_xref, data)

    def _commit(self, i):
        """Show page i's current state: in the private copy and on screen."""
        pc = self.pages[i]
        data = pc.stream()
        self._set_stream(i, data)
        self._refresh_boxes(i)
        self.view.patch_page(i, data)
        self._update(i)

    def _page_drawn(self, i):
        if self.preview and self.preview["page"] == i and self.preview.get("done"):
            self.preview = None
            self._update(i)

    # ---- finding things ----
    def hit(self, i, x, y):
        """The smallest thing under a point (page points as shown), or None."""
        pc = self.content(i)
        tol = 3 / self.view.zoom
        best, area = None, None
        for k, b in enumerate(pc.cur):
            if k in pc.removed or pc.objs[k].hidden:
                continue
            if b.x0 - tol <= x <= b.x1 + tol and b.y0 - tol <= y <= b.y1 + tol:
                a = max(b.width, 0.5) * max(b.height, 0.5)
                if (area is None or a < area) and pc.touches(k, x, y, tol):
                    best, area = k, a
        return best

    def inside(self, i, rect):
        pc = self.content(i)
        return {k for k, b in enumerate(pc.cur) if k not in pc.removed and rect.contains(b)}

    def union(self):
        boxes = [self.box(k) for k in self.selection]
        if not boxes:
            return None
        u = pymupdf.Rect(boxes[0])
        for b in boxes[1:]:
            u |= b
        return u

    # ---- selection ----
    def clear(self):
        old = self.page
        self.page, self.selection = None, set()
        self._update(old)
        self.session.selection_changed(None)

    def select(self, i, keys, add=False):
        self.content(i)
        if self.page != i or not add:
            old = self.page
            self.page, self.selection = i, set()
            if old is not None and old != i:
                self._update(old)
        self.selection |= set(keys)
        self._update(i)

    # ---- mouse ----
    def press(self, label, pos):
        z = self.view.zoom
        i = label.index
        x, y = pos.x() / z, pos.y() / z
        add = bool(QApplication.keyboardModifiers() & (Qt.ShiftModifier | Qt.ControlModifier))  # add or take away
        grab = self.handle_at(i, x, y)
        if grab is not None:
            u = self.union()
            self._press = {"page": i, "x": x, "y": y, "mode": grab, "moved": False, "box": u,
                           "centre": pymupdf.Point((u.x0 + u.x1) / 2, (u.y0 + u.y1) / 2)}
            return True
        k = self.hit(i, x, y)
        if add:
            if k is not None:
                if self.page == i and k in self.selection:
                    self.selection.discard(k)
                    self._update(i)
                else:
                    self.select(i, [k], add=True)
                self._press = None
                return True
            self._press = {"page": i, "x": x, "y": y, "mode": "band", "add": True}
            return True
        on_selection = self.page == i and (k in self.selection or (
            k is None and len(self.selection) > 1 and self.union() is not None and self.union().contains((x, y))))
        if k is not None and not on_selection:
            self.select(i, [k])
            on_selection = True
        if on_selection:
            self._press = {"page": i, "x": x, "y": y, "mode": "drag", "moved": False}
        else:
            self.clear()
            self._press = {"page": i, "x": x, "y": y, "mode": "band", "add": False}
        return True

    def handle_at(self, i, x, y):
        """The handle under a point: a corner ("nw", …), "turn", or None."""
        if self.page != i or not self.selection:
            return None
        z = self.view.zoom
        _, spots = handle_spots(self.union(), z)
        reach = (HANDLE / 2 + 3) / z
        for k, pt in spots.items():
            if abs(pt.x - x) <= reach and abs(pt.y - y) <= reach:
                return k
        return None

    def live_xform(self):
        """While turning or resizing: the change so far (page points as shown), else None."""
        p = self._press
        return p.get("xform") if p and p["mode"] not in ("drag", "band") else None

    def _xform(self, p, x, y, snap):
        """The turn or resize for the pointer at (x, y)."""
        if p["mode"] == "turn":
            c = p["centre"]
            angle = math.atan2(y - c.y, x - c.x) - math.atan2(p["y"] - c.y, p["x"] - c.x)
            if snap:
                step = math.radians(15)
                angle = round(angle / step) * step
            cos, sin = math.cos(angle), math.sin(angle)
            rot = pymupdf.Matrix(cos, sin, -sin, cos, 0, 0)
            return pymupdf.Matrix(1, 0, 0, 1, -c.x, -c.y) * rot * pymupdf.Matrix(1, 0, 0, 1, c.x, c.y)
        u = p["box"]
        _, _, ax, ay = CORNERS[p["mode"]]
        a = pymupdf.Point(getattr(u, ax), getattr(u, ay))  # the opposite corner stays put
        start = abs(pymupdf.Point(p["x"], p["y"]) - a)
        scale = max(0.05, abs(pymupdf.Point(x, y) - a) / max(start, 1e-6))
        return pymupdf.Matrix(1, 0, 0, 1, -a.x, -a.y) * pymupdf.Matrix(scale, 0, 0, scale, 0, 0) * \
            pymupdf.Matrix(1, 0, 0, 1, a.x, a.y)

    def drag_offset(self):
        p = self._press
        if p and p["mode"] == "drag" and p.get("moved"):
            return p["dx"], p["dy"]
        return 0, 0

    def move(self, label, pos):
        z = self.view.zoom
        i = label.index
        x, y = pos.x() / z, pos.y() / z
        p = self._press
        if p is None:
            grab = self.handle_at(i, x, y)
            if grab is not None:
                label.setCursor(Qt.PointingHandCursor if grab == "turn" else
                                Qt.SizeFDiagCursor if grab in ("nw", "se") else Qt.SizeBDiagCursor)
                return True
            k = self.hit(i, x, y)
            new = (i, k) if k is not None else None
            if new != self.hover:
                old = self.hover
                self.hover = new
                if old:
                    self._update(old[0])
                if new:
                    self._update(i)
            label.setCursor(Qt.SizeAllCursor if k is not None else Qt.ArrowCursor)
            return True
        if i != p["page"]:
            return True
        page = self.view.doc[i].rect
        if p["mode"] == "band":
            r = pymupdf.Rect(min(p["x"], x), min(p["y"], y), max(p["x"], x), max(p["y"], y)) & page
            self.band = (i, r)
            self._update(i)
            return True
        if p["mode"] != "drag":  # turning or resizing
            if not p["moved"]:
                if abs(x - p["x"]) * z < 2 and abs(y - p["y"]) * z < 2:
                    return True
                p["moved"] = True
                self.hover = None
                self._start_preview(i)
            p["xform"] = self._xform(p, x, y, bool(QApplication.keyboardModifiers() & Qt.ShiftModifier))
            if self.preview:
                self.preview["xform"] = p["xform"]
            self._update(i)
            return True
        dx, dy = x - p["x"], y - p["y"]
        if not p["moved"] and abs(dx) * z < 3 and abs(dy) * z < 3:
            return True
        if not p["moved"]:
            p["moved"] = True
            self.hover = None
            self._start_preview(i)
        # Keep the selection on the page.
        u = self.union()
        if u is not None:
            dx = max(page.x0 - u.x0, min(dx, page.x1 - u.x1)) if u.width < page.width else dx
            dy = max(page.y0 - u.y0, min(dy, page.y1 - u.y1)) if u.height < page.height else dy
        p["dx"], p["dy"] = dx, dy
        if self.preview:
            self.preview["offset"] = (dx, dy)
        self._update(i)
        return True

    def release(self, label, pos):
        p, self._press = self._press, None
        if p is None:
            return True
        i = p["page"]
        if p["mode"] == "band":
            band, self.band = self.band, None
            if band is not None and band[1].width * self.view.zoom > 3:
                self.select(i, self.inside(i, band[1]), add=p.get("add"))
            self._update(i)
            return True
        if p["mode"] not in ("drag", "band"):
            if p.get("moved") and p.get("xform") is not None:
                self.transform(p["xform"])
            else:
                self.preview = None
                self._update(i)
            return True
        if p.get("moved"):
            self.shift(p["dx"], p["dy"], preview=True)
        else:
            self._update(i)
        return True

    # ---- changes ----
    def _remember(self, i):
        self.session.checkpoint()

    def shift(self, dx, dy, preview=False):
        """Move the selection by (dx, dy) page points as shown."""
        i = self.page
        if i is None or not self.selection or (abs(dx) < 1e-6 and abs(dy) < 1e-6):
            self.preview = None
            return
        pc = self.pages[i]
        self._remember(i)
        pc.add_view_change(self.selection, pymupdf.Matrix(1, 0, 0, 1, dx, dy))
        if preview and self.preview:
            self.preview["done"] = True  # keep showing it until the page is redrawn
        self._commit(i)
        self.session.on_change()

    def transform(self, m):
        """Turn or resize the selection by m (page points as shown)."""
        i = self.page
        if i is None or not self.selection:
            self.preview = None
            return
        pc = self.pages[i]
        self._remember(i)
        pc.add_view_change(self.selection, m)
        if self.preview:
            self.preview["done"] = True  # keep showing it until the page is redrawn
        self._commit(i)
        self.session.on_change()

    def delete(self):
        i = self.page
        if i is None or not self.selection:
            return
        pc = self.pages[i]
        self._remember(i)
        u = self.union()
        pc.removed |= self.selection
        self.selection = set()
        # Cover the old spot with a picture of the page without them until the redraw arrives.
        if u is not None:
            self.preview = {"page": i, "box": u, "patch": self._render(i, pc.stream(), u, alpha=False),
                            "ghost": None, "offset": (0, 0), "done": True}
        self._commit(i)
        self.session.on_change()

    def select_all(self):
        i = self.view.current_page()
        pc = self.content(i)
        self.select(i, [k for k in range(len(pc.objs)) if k not in pc.removed])

    # ---- previews ----
    def _render(self, i, data, box, alpha):
        self._set_stream(i, data)
        scale = self.view.zoom * self.view.devicePixelRatioF()
        try:
            pix = self.work[i].get_pixmap(matrix=pymupdf.Matrix(scale, scale), clip=box, alpha=alpha)
        except Exception:
            return None
        fmt = QImage.Format_RGBA8888 if alpha else QImage.Format_RGB888
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt).copy()
        return img

    def _start_preview(self, i):
        """Pictures for dragging: the page without the selection (under its old spot), and the
        selection on its own, which follows the mouse."""
        pc = self.pages[i]
        u = self.union()
        if u is None:
            return
        page = self.view.doc[i].rect
        box = pymupdf.Rect(u.x0 - 2, u.y0 - 2, u.x1 + 2, u.y1 + 2) & page
        others = {k for k in range(len(pc.objs)) if k not in self.selection} | pc.removed
        ghost = self._render(i, pc.stream(removed=others), box, alpha=True)
        patch = self._render(i, pc.stream(removed=pc.removed | self.selection), box, alpha=False)
        self._set_stream(i, pc.stream())
        self.preview = {"page": i, "box": box, "patch": patch, "ghost": ghost, "offset": (0, 0)}

    # ---- keys ----
    def eventFilter(self, obj, e):
        t = e.type()
        if t not in (QEvent.KeyPress, QEvent.ShortcutOverride) or self.page is None:
            return False
        focus = QApplication.focusWidget()
        if isinstance(focus, (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox, QComboBox)):
            return False
        if focus is not None and focus.window() is not self.view.window():
            return False
        steps = {Qt.Key_Left: (-1, 0), Qt.Key_Right: (1, 0), Qt.Key_Up: (0, -1), Qt.Key_Down: (0, 1)}
        key = e.key()
        if key not in steps and key not in (Qt.Key_Delete, Qt.Key_Backspace):
            return False
        if t == QEvent.ShortcutOverride:
            e.accept()  # these keys are for the selection, not for menu shortcuts
            return True
        if key in steps:
            n = 10 if e.modifiers() & Qt.ShiftModifier else 1
            self.shift(steps[key][0] * n, steps[key][1] * n)
        else:
            self.delete()
        return True
