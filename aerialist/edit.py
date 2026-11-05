"""Edit PDF screen: add text boxes, pictures and shapes (pen, rectangle, ellipse, line, arrow,
highlight, white-out). Items float over the page until Done or Save writes
them into the PDF."""
import math

import pymupdf
from PySide6.QtCore import Qt, QPointF, QRectF, QEvent, QRect, QSize
from PySide6.QtGui import (QPainter, QPen, QColor, QFontMetricsF, QIcon, QPixmap, QPolygonF, QPainterPath, QImageReader,
                           QDoubleValidator)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QToolButton, QButtonGroup, QMenu, QColorDialog,
    QComboBox, QDoubleSpinBox, QTextEdit, QFrame, QFileDialog, QMessageBox, QInputDialog, QLineEdit,
)

from .organizer import IMAGE_EXTS
from .chrome import BarTools, MiniBar, tool_button, separator
from .icons import drawn, icon, pixmap as icon_pixmap
from . import theme
from . import blur, fonts, overlay
from .overlay import (Item, ImageItem, OverlaySession, to_page, read_image, jpeg_or_png, png_bytes, MARGIN,
                      SIZES, next_size, line_image)
from .mover import ContentMover
from .stamps import stamp_image
from .stamp_bar import StampGroup, ToolStrip
from . import stamps as stamp_sizes
from .popups import APP_NAME

COLORS = [("Black", "#000000"), ("Red", "#d93025"), ("Blue", "#1a56db"), ("Green", "#188038"),
          ("Yellow", "#fbbc04"), ("White", "#ffffff"), ("Grey", "#808080")]
HINTS = {
    "select": "Click an item to select it. Drag to move, drag a corner (or Ctrl+scroll while dragging) to resize, "
              "double-click text to edit it, arrow keys nudge. Nothing is written into the PDF until you click Done.",
    "move": "Click a line, shape or text that's already in the PDF to pick it up, or drag a box round "
            "several. Drag to move, arrow keys nudge, Delete removes. Ctrl+click or Shift+click adds to the "
            "selection.",
    "text": "Click on the page to start typing, or drag a box: the text size fits the box's height. "
            "Ctrl+scroll changes the size. Click outside the box when done.",
    "stamp": "Click on the page where the stamp goes, or drag to size it. Ctrl+scroll resizes it before you "
             "click. Drag a corner later to resize.",
    "image": "Click on the page to place the image, or click and drag to size it. Ctrl+scroll while dragging "
             "resizes it.",
    "pen": "Draw freehand on the page. The pen stays on until you pick another tool.",
    "marker": "Draw over text like a highlighter pen. It stays on until you pick another tool.",
    "wpen": "Paint over anything to white it out, like a correction pen (text underneath is removed). "
            "Stays on until you pick another tool.",
    "rect": "Drag on the page to draw a rectangle. The tool stays on for the next one; Select or Esc to stop.",
    "ellipse": "Drag on the page to draw an ellipse. The tool stays on for the next one; Select or Esc to stop.",
    "line": "Drag on the page to draw a line. The tool stays on for the next one; Select or Esc to stop.",
    "arrow": "Drag on the page to draw an arrow (it points to where you let go). Select or Esc to stop.",
    "highlight": "Drag over the area to highlight. The tool stays on; Select or Esc to stop.",
    "whiteout": "Drag over what you want to cover with white (then add Text on top). Select or Esc to stop.",
    "blur": "Drag over names, numbers or faces to blur them. When you click Done, what's underneath is removed "
            "from the PDF for good, so it can't be copied or uncovered. Select or Esc to stop.",
    "link": "Drag a box over what should be clickable, such as words already on the page, then type where it "
            "goes. To make text you add into a link, select it and click Link on its bar.",
}
# Which style settings each kind of item uses.
STYLE_KEYS = {"text": ("font", "size", "bold", "italic", "underline", "color"), "rect": ("color", "fill", "width"), "ellipse": ("color", "fill", "width"),
              "line": ("color", "width"), "arrow": ("color", "width"),
              "pen": ("color", "width"), "marker": ("color", "width"), "wpen": ("width",), "highlight": ("fill",), "whiteout": (),
              "blur": (),              "image": (), "link": ()}
ATTR = {"color": "color", "fill": "fill", "width": "lw", "font": "font_key", "size": "font_size",
        "bold": "bold", "italic": "italic", "underline": "underline"}  # item attribute
WIDTHS = [0.5, 1, 1.5, 2, 3, 4, 6, 8, 10, 12, 16, 20]
STICKY = {"rect", "ellipse", "line", "arrow", "highlight", "whiteout", "blur"}  # stay on until Select or Esc
GROUP = {"rect": "shape", "ellipse": "shape", "line": "line", "arrow": "line"}


def _rgb(c):
    return None if c is None else (c.redF(), c.greenF(), c.blueF())


def _spans(page, clip):
    """Text spans in an area of the page, as (origin, direction, length) for underlining."""
    out = set()
    for b in page.get_text("dict", clip=clip)["blocks"]:
        for line in b.get("lines", []):
            d = tuple(round(v, 3) for v in line["dir"])
            for sp in line["spans"]:
                if not sp["text"].strip():
                    continue
                x0, y0, x1, y1 = sp["bbox"]
                length = abs((x1 - x0) * d[0]) + abs((y1 - y0) * d[1])
                out.add((tuple(round(v, 2) for v in sp["origin"]), d, round(length, 2)))
    return out


def fit_size(height):
    """Text size (pt) whose one line fills a box this tall (pt)."""
    return max(6, min(96, round(height / 1.4)))


# ---- items ------------------------------------------------------------------
class TextItem(Item):
    def __init__(self, session, label, rect, style):
        self.text = ""
        self._set_style(style)
        self.editor = None
        super().__init__(session, label, rect)
        self.kind = "text"

    def _set_style(self, style):
        self.color, self.font_key, self.font_size = QColor(style["color"]), style["font"], style["size"]
        self.bold, self.italic = style.get("bold", False), style.get("italic", False)
        self.underline = style.get("underline", False)

    def pdf_args(self):
        return fonts.pdf_args(self.font_key, self.bold, self.italic)

    def qfont(self, scale=None):
        f = fonts.qfont(self.font_key, self.font_size * (self.zoom() if scale is None else scale),
                        self.bold, self.italic)
        f.setUnderline(bool(self.underline))
        return f

    def draw(self, p, box):
        if self.editor:
            return
        p.setPen(self.color)
        p.setFont(self.qfont())
        p.drawText(box, Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop, self.text)

    def apply_style(self, style):
        self._set_style(style)
        if self.editor:
            self._style_editor()
        self.fit_height()

    def fit_height(self):
        """Grow or shrink the box to fit the text."""
        fm = QFontMetricsF(self.qfont(4))  # measured large for accuracy, in points * 4
        w = self.rect_pt.width * 4
        r = fm.boundingRect(QRectF(0, 0, w, 1e6), Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop, self.text or "X")
        h = max(r.height(), fm.lineSpacing()) / 4 + self.font_size * 0.25
        page = self.page_rect()
        y0 = min(self.rect_pt.y0, max(0, page.height - h))
        self.rect_pt = pymupdf.Rect(self.rect_pt.x0, y0, self.rect_pt.x1, y0 + h)
        self.relayout()

    def relayout(self):
        super().relayout()
        if self.editor:
            self._style_editor()

    def drag_to(self, mode, rect, dx, dy):
        super().drag_to(mode, rect, dx, dy)
        if mode != "move":
            self.fit_height()

    # ---- typing in place ----
    def edit(self):
        if self.editor:
            return
        if self.text:
            self.session.checkpoint()  # changing text that was already there can be undone
        ed = QTextEdit(self)
        ed.setAcceptRichText(False)
        ed.setFrameShape(QFrame.NoFrame)
        ed.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        ed.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        ed.document().setDocumentMargin(0)
        ed.setPlainText(self.text)
        ed.textChanged.connect(self._typed)
        ed.installEventFilter(self)
        self.session.select(self)  # before focusing the editor: selecting focuses the item
        self.editor = ed
        self._style_editor()
        ed.show()
        ed.setFocus()
        ed.moveCursor(ed.textCursor().MoveOperation.End)
        self.update()

    def _style_editor(self):
        ed = self.editor
        ed.setGeometry(self.box().toRect())
        ed.setFont(self.qfont())
        ed.setStyleSheet(f"QTextEdit {{ background: rgba(255,255,255,140); color: {self.color.name()}; }}")

    def _typed(self):
        self.text = self.editor.toPlainText()
        self.fit_height()

    def finish_edit(self):
        if not self.editor:
            return
        self.text = self.editor.toPlainText().rstrip()
        self.editor.hide()
        self.editor.deleteLater()
        self.editor = None
        if not self.text.strip():
            self.session.remove(self, record=False)  # nothing was typed: as if it was never added
            return
        self.fit_height()
        self.session.on_change()

    def eventFilter(self, obj, e):
        if obj is self.editor:
            if e.type() == QEvent.FocusOut:
                self.finish_edit()
            elif e.type() == QEvent.KeyPress and e.key() == Qt.Key_Escape:
                self.finish_edit()
                return True
            return False
        return super().eventFilter(obj, e)

    def writer(self):
        rect, text, size, font = pymupdf.Rect(self.rect_pt), self.text, self.font_size, self.pdf_args()
        color, underline = _rgb(self.color), self.underline

        def write(page):
            r = pymupdf.Rect(rect)
            before = _spans(page, to_page(page, r)) if underline else set()
            for _ in range(5):  # PDF line spacing differs a little from the screen: give it room if needed
                rc = page.insert_textbox(to_page(page, r), text, fontsize=size, color=color, **font,
                                         rotate=page.rotation)
                if rc >= 0:
                    break
                r.y1 += -rc + size
            if underline:  # a line under each line of the new text
                shape = page.new_shape()
                for origin, d, length in _spans(page, to_page(page, r)) - before:
                    down = pymupdf.Point(-d[1], d[0]) * (size * 0.12)
                    a = pymupdf.Point(origin) + down
                    shape.draw_line(a, a + pymupdf.Point(d) * length)
                shape.finish(color=color, width=max(0.5, size * 0.06))
                shape.commit()
        return write


class ShapeItem(Item):
    """Rectangle, ellipse, highlight, white-out or blur."""

    def __init__(self, session, label, rect, kind, style):
        self.kind = kind
        self.apply_style(style, update=False)
        super().__init__(session, label, rect)

    def apply_style(self, style, update=True):
        k = self.kind
        self.color = QColor(style["color"]) if "color" in STYLE_KEYS[k] else None
        self.fill = (QColor(style["fill"]) if style.get("fill") else None) if "fill" in STYLE_KEYS[k] else None
        self.lw = style.get("width", 1) if "width" in STYLE_KEYS[k] else 0
        if k == "whiteout":
            self.fill = QColor("white")
        self.opacity = 0.35 if k == "highlight" else 1.0
        if update:
            self.update()

    def draw(self, p, box):
        if self.kind == "link":  # only an area to click: shown while editing, invisible in the PDF
            tint = QColor(theme.ACCENT_FILL)
            tint.setAlpha(30)
            p.fillRect(box, tint)
            p.setPen(QPen(QColor(theme.ACCENT_FILL), 1.5, Qt.DotLine))
            p.drawRect(box)
            p.drawPixmap(QPointF(box.right() - 18, box.top() + 2), icon_pixmap("link", 16, "ACCENT"))
            return
        if self.kind == "blur":
            self._draw_blur(p, box)
            return
        z = self.zoom()
        fill = QColor(self.fill) if self.fill else None
        if fill:
            fill.setAlphaF(self.opacity)
        p.setBrush(fill if fill else Qt.NoBrush)
        p.setPen(QPen(self.color, self.lw * z) if self.color and self.lw else Qt.NoPen)
        if self.kind == "ellipse":
            p.drawEllipse(box)
        else:
            p.drawRect(box)

    def _draw_blur(self, p, box):
        """A blurred copy of the page under the box (redrawn when it moves, resizes or zooms)."""
        scale = self.zoom() * self.devicePixelRatioF()
        key = (tuple(self.rect_pt), round(scale, 3))
        if getattr(self, "_blur_key", None) != key:
            try:
                self._blur_img = blur.render(self.session.view.doc[self.page_index], self.rect_pt, scale)
            except Exception:
                self._blur_img = None
            self._blur_key = key
        if self._blur_img is not None:
            p.drawImage(box, self._blur_img)
        else:
            p.fillRect(box, QColor("#9e9e9e"))

    def writer(self):
        rect, kind = pymupdf.Rect(self.rect_pt), self.kind
        if kind == "blur":
            return lambda page: blur.write(page, rect)
        color = _rgb(self.color) if self.lw else None
        fill, width, opacity = _rgb(self.fill), self.lw, self.opacity

        def write(page):
            r = to_page(page, rect)
            if kind == "link":
                return  # the link itself is added with every item's link (overlay.with_link)
            if kind == "whiteout":
                # Really removes the text and picture pixels underneath, not just paints over them.
                page.add_redact_annot(r, fill=(1, 1, 1))
                page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_PIXELS,
                                      graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)
                return
            shape = page.new_shape()
            shape.draw_oval(r) if kind == "ellipse" else shape.draw_rect(r)
            shape.finish(color=color, fill=fill, width=width or 0, fill_opacity=opacity)
            shape.commit()
        return write


class LineItem(Item):
    """Line or arrow, with a handle at each end."""

    def __init__(self, session, label, p1, p2, kind, style):
        self.p1, self.p2, self.kind = pymupdf.Point(p1), pymupdf.Point(p2), kind
        self.color, self.lw = QColor(style["color"]), style["width"]
        super().__init__(session, label, self._bounds())

    def apply_style(self, style):
        self.color, self.lw = QColor(style["color"]), style["width"]
        self.update()

    def _bounds(self):
        return pymupdf.Rect(self.p1, self.p2).normalize()

    def set_points(self, p1, p2):
        self.p1, self.p2 = p1, p2
        self.rect_pt = self._bounds()
        self.relayout()

    def _w(self, pt):
        """Page point -> widget coordinates."""
        z = self.zoom()
        return QPointF((pt.x - self.rect_pt.x0) * z + MARGIN, (pt.y - self.rect_pt.y0) * z + MARGIN)

    def handles(self):
        return {"p1": self._w(self.p1), "p2": self._w(self.p2)}

    def body_hit(self, pos):
        a, b = self._w(self.p1), self._w(self.p2)
        dx, dy = b.x() - a.x(), b.y() - a.y()
        t = 0 if dx == dy == 0 else max(0, min(1, ((pos.x() - a.x()) * dx + (pos.y() - a.y()) * dy) / (dx * dx + dy * dy)))
        return math.hypot(pos.x() - a.x() - t * dx, pos.y() - a.y() - t * dy) <= max(6, self.lw * self.zoom())

    def draw_outline(self, p):
        pass  # the end handles show it's selected

    def _head(self, p1, p2, scale=1.0):
        """Arrow head triangle at p2 (page points), and where the line should stop."""
        size = max(7.0, self.lw * 3.5)
        dx, dy = p2.x - p1.x, p2.y - p1.y
        n = math.hypot(dx, dy) or 1
        ux, uy = dx / n, dy / n
        base = pymupdf.Point(p2.x - ux * size, p2.y - uy * size)
        left = pymupdf.Point(base.x - uy * size * 0.5, base.y + ux * size * 0.5)
        right = pymupdf.Point(base.x + uy * size * 0.5, base.y - ux * size * 0.5)
        return [p2, left, right], base

    def draw(self, p, box):
        p.setPen(QPen(self.color, max(1.0, self.lw * self.zoom()), Qt.SolidLine, Qt.RoundCap))
        end = self.p2
        if self.kind == "arrow":
            tri, end = self._head(self.p1, self.p2)
            p.setBrush(self.color)
            p.drawPolygon(QPolygonF([self._w(t) for t in tri]))
        p.drawLine(self._w(self.p1), self._w(end))

    def drag_state(self):
        return (pymupdf.Point(self.p1), pymupdf.Point(self.p2))

    def drag_to(self, mode, state, dx, dy):
        p1, p2 = state
        page = self.page_rect()

        def clamp(pt):
            return pymupdf.Point(max(0, min(pt.x, page.width)), max(0, min(pt.y, page.height)))
        if mode == "move":
            r = pymupdf.Rect(p1, p2).normalize()
            dx = max(-r.x0, min(dx, page.width - r.x1))
            dy = max(-r.y0, min(dy, page.height - r.y1))
            self.set_points(p1 + (dx, dy), p2 + (dx, dy))
        elif mode == "p1":
            self.set_points(clamp(p1 + (dx, dy)), p2)
        else:
            self.set_points(p1, clamp(p2 + (dx, dy)))

    def writer(self):
        p1, p2, kind, width = pymupdf.Point(self.p1), pymupdf.Point(self.p2), self.kind, self.lw
        color = _rgb(self.color)
        tri, end = self._head(p1, p2) if kind == "arrow" else (None, p2)

        def write(page):
            m = page.derotation_matrix
            shape = page.new_shape()
            shape.draw_line(p1 * m, end * m)
            shape.finish(color=color, width=width, lineCap=1)
            if tri:
                shape.draw_polyline([t * m for t in tri])
                shape.finish(color=color, fill=color, width=0.5, closePath=True)
            shape.commit()
        return write


class FreehandItem(Item):
    """Pen or highlighter stroke."""

    def __init__(self, session, label, pt, kind, style):
        self.kind, self.pts = kind, [pymupdf.Point(pt)]
        self.color, self.lw = QColor(style.get("color", "#ffffff")), style["width"]
        self.opacity = 0.4 if kind == "marker" else 1.0
        super().__init__(session, label, self._bounds())

    def _bounds(self):
        pad = self.lw / 2 + 1
        xs, ys = [p.x for p in self.pts], [p.y for p in self.pts]
        return pymupdf.Rect(min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)

    def add_point(self, pt):
        self.pts.append(pymupdf.Point(pt))
        self.rect_pt = self._bounds()
        self.relayout()

    def apply_style(self, style):
        self.color, self.lw = QColor(style.get("color", "#ffffff")), style["width"]
        self.rect_pt = self._bounds()
        self.relayout()

    def _w(self, pt):
        z = self.zoom()
        return QPointF((pt.x - self.rect_pt.x0) * z + MARGIN, (pt.y - self.rect_pt.y0) * z + MARGIN)

    def draw(self, p, box):
        c = QColor(self.color)
        c.setAlphaF(self.opacity)
        p.setPen(QPen(c, max(1.0, self.lw * self.zoom()), Qt.SolidLine,
                      Qt.FlatCap if self.kind == "marker" else Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        pts = [self._w(t) for t in self.pts]
        if len(pts) == 1:
            p.drawPoint(pts[0])
            return
        path = QPainterPath(pts[0])
        for pt in pts[1:]:
            path.lineTo(pt)
        p.drawPath(path)

    def drag_state(self):
        return (pymupdf.Rect(self.rect_pt), [pymupdf.Point(t) for t in self.pts])

    def drag_to(self, mode, state, dx, dy):
        old, pts = state
        super().drag_to(mode, old, dx, dy)
        new = self.rect_pt
        sx, sy = new.width / max(old.width, 1e-6), new.height / max(old.height, 1e-6)
        self.pts = [pymupdf.Point(new.x0 + (t.x - old.x0) * sx, new.y0 + (t.y - old.y0) * sy) for t in pts]

    def writer(self):
        pts, width, opacity, kind = [pymupdf.Point(t) for t in self.pts], self.lw, self.opacity, self.kind
        color = _rgb(self.color)

        def write(page):
            m = page.derotation_matrix
            if kind == "wpen":
                # Remove the text under the stroke (like the White-out box), then paint it white.
                core = width * 0.3
                for a, b in zip(pts, pts[1:] + pts[-1:]):
                    n = max(1, int(abs(b - a) / max(core, 1)))
                    for k in range(n):
                        c = a + (b - a) * (k / n)
                        page.add_redact_annot(pymupdf.Rect(c.x - core, c.y - core, c.x + core, c.y + core) * m,
                                              fill=False)
                page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                                      graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)
            shape = page.new_shape()
            line = [t * m for t in pts]
            if len(line) == 1:
                line.append(line[0] + (0.01, 0))
            shape.draw_polyline(line)
            shape.finish(color=color, width=width, closePath=False, lineCap=0 if kind == "marker" else 1,
                         lineJoin=1, stroke_opacity=opacity)
            shape.commit()
        return write


# ---- placing items -------------------------------------------------------------
class EditSession(OverlaySession):
    tool_changed = None  # set by the screen: function(tool)

    def __init__(self, view, on_change):
        super().__init__(view, on_change)
        self.tool = "select"
        self.image = None  # (QImage, file bytes) for the Image tool
        self.stamp_key = None  # set when the "image" is one of the stamps
        self.styles = {"text": {"color": "#000000", "font": "helv", "size": 12, "bold": False, "italic": False,
                                "underline": False},
                       "shape": {"color": "#d93025", "fill": None, "width": 2},
                       "line": {"color": "#d93025", "width": 2},
                       "pen": {"color": "#1a56db", "width": 2}, "marker": {"color": "#fbbc04", "width": 12},
                       "wpen": {"color": "#ffffff", "width": 10},
                       "highlight": {"fill": "#fbbc04"}, "whiteout": {}, "blur": {}, "image": {}, "link": {}}
        self._placing = None
        self.on_select = lambda item: None
        self.mover = ContentMover(self)

    def style_for(self, kind):
        return self.styles[GROUP.get(kind, kind)]

    def set_tool(self, tool):
        self.tool = tool
        self.hide_ghost()
        self.set_cursor(None if tool in ("select", "move") else Qt.CrossCursor)
        self.mover.activate(tool == "move")
        # While drawing, clicks go to the page, not to things already placed (so they don't get
        # picked up and dragged by mistake). Select (or Esc) makes them movable again.
        for s in self.stamps:
            s.setAttribute(Qt.WA_TransparentForMouseEvents, tool != "select")
        if self.tool_changed:
            self.tool_changed(tool)

    def armed_or_tool(self):
        return self.tool != "select"

    def cancel_tool(self):
        if self.tool == "move" and self.mover.selection:
            self.mover.clear()  # Esc first lets go of what's selected
            return
        self.set_tool("select")

    def stop(self):
        for s in self.stamps + self._gone:
            if isinstance(s, TextItem):
                s.editor = None  # going away with its item
        super().stop()
        self.mover.stop()
        self.tool = "select"

    def pending(self):
        return super().pending() + self.mover.pending()

    def add(self, item):
        item.setAttribute(Qt.WA_TransparentForMouseEvents, self.tool not in ("select", "text", "image"))
        super().add(item)

    def armed_preview(self, label, pos):
        if self._placing:
            return None
        if self.tool == "image" and self.stamp_key and self.image:
            return self.image[0], self.stamp_rect(label, pos, self.stamp_key, self.image[0])
        if self.tool == "text":
            return self._text_preview(label, pos)
        return None

    def _text_preview(self, label, pos):
        style = self.style_for("text")
        item_font = fonts.qfont(style["font"], style["size"] * 4, style.get("bold"), style.get("italic"))
        img, w, h = line_image("Text", item_font, style["color"])
        z = self.view.zoom
        x, y = pos.x() / z, pos.y() / z
        return img, pymupdf.Rect(x, y, x + w, y + h)

    def wheel_armed(self, delta):
        if self.tool == "image" and self.stamp_key:
            stamp_sizes.grow(delta / 120)
            return True
        if self.tool == "text":
            n = self.wheel_steps(delta)
            if n:
                style = self.style_for("text")
                style["size"] = next_size(style["size"], n)
                self.selection_changed(None)  # the size box shows the new size
            return True
        return False

    def set_item_size(self, item, size):
        self.select(item)
        self.set_style("size", size)
        self.selection_changed(item)

    def remember_size(self, item):
        if getattr(item, "stamp_key", None):
            stamp_sizes.remember(item.stamp_key, item.rect_pt.height)

    def placing_item(self):
        return self._placing[0] if self._placing else None

    def finish_typing(self):
        for s in list(self.stamps):
            if isinstance(s, TextItem):
                s.finish_edit()

    def extra_state(self):
        return self.mover.state()

    def set_extra_state(self, extra):
        self.mover.restore(extra)

    def restore(self, state):
        super().restore(state)
        for s in self.stamps:
            s.setAttribute(Qt.WA_TransparentForMouseEvents, self.tool != "select")

    def selection_changed(self, item):
        self.on_select(item)

    def take(self):
        for s in list(self.stamps):
            if isinstance(s, TextItem):
                s.finish_edit()
        moved = self.mover.specs()  # first: placed items go on top of the page's own drawing
        self.mover.stop(revert=False)
        return moved + super().take()

    def set_style(self, key, value):
        """A style control changed: use it for new items, and for the selected one."""
        item = self.selected()
        kind = item.kind if item else self.tool
        if kind not in STYLE_KEYS:
            return
        self.style_for(kind)[key] = value
        if item and hasattr(item, "apply_style"):
            self.checkpoint(("style", item, key))
            # Change just this setting on the item, keeping its others.
            style = {}
            for k in STYLE_KEYS[item.kind]:
                if k not in ATTR:
                    continue
                v = getattr(item, ATTR[k], None)
                style[k] = v.name() if isinstance(v, QColor) else v
            style[key] = value
            item.apply_style(style)

    # ---- page mouse hooks ----
    def press(self, label, pos):
        if self.tool == "move":
            return self.mover.press(label, pos)
        self.hide_ghost()
        for s in list(self.stamps):  # clicking elsewhere ends typing
            if isinstance(s, TextItem):
                s.finish_edit()
        z = self.view.zoom
        x, y = pos.x() / z, pos.y() / z
        tool = self.tool
        if tool == "select":
            self.select(None)
            return True
        # With a shape tool on and a shape selected, a plain click just deselects (see release).
        self._click_off = tool in STICKY and self.selected() is not None
        page = self.view.doc[label.index].rect
        if tool == "image" and self.stamp_key:  # where the see-through copy was showing
            img, data = self.image
            item = ImageItem(self, label, self.stamp_rect(label, pos, self.stamp_key, img), img, data)
            item.kind = "image"
            item.stamp_key = self.stamp_key
            item.default_rect = pymupdf.Rect(item.rect_pt)
        elif tool == "image":
            img, data = self.image
            aspect = img.width() / max(1, img.height())
            w = min(page.width * 0.5, 200)
            h = w / aspect
            if h > page.height * 0.5:
                h = page.height * 0.5
                w = h * aspect
            x0, y0 = max(0, min(x - w / 2, page.width - w)), max(0, min(y - h / 2, page.height - h))
            item = ImageItem(self, label, pymupdf.Rect(x0, y0, x0 + w, y0 + h), img, data)
            item.kind = "image"
            item.default_rect = pymupdf.Rect(item.rect_pt)
        elif tool == "text":
            w = min(200, page.width - x)
            item = TextItem(self, label, pymupdf.Rect(x, y, x + max(w, 20), y + 16), self.style_for("text"))
            item.fit_height()
        elif tool in ("pen", "marker", "wpen"):
            item = FreehandItem(self, label, pymupdf.Point(x, y), tool, self.style_for(tool))
            item.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            self._placing = (item, x, y)
            self.checkpoint()
            self.stamps.append(item)  # added without selecting: keep drawing
            self.on_change()
            return True
        elif tool in ("line", "arrow"):
            item = LineItem(self, label, pymupdf.Point(x, y), pymupdf.Point(x, y), tool, self.style_for(tool))
        else:
            item = ShapeItem(self, label, pymupdf.Rect(x, y, x + 1, y + 1), tool, self.style_for(tool))
        self._placing = (item, x, y)
        self.add(item)
        return True

    def move(self, label, pos):
        if self.tool == "move":
            return self.mover.move(label, pos)
        if not self._placing:
            self.follow(label, pos)
            return False
        item, x, y = self._placing
        if item.label is not label:
            return True
        z = self.view.zoom
        page = self.view.doc[label.index].rect
        cx, cy = max(0, min(pos.x() / z, page.width)), max(0, min(pos.y() / z, page.height))
        if isinstance(item, FreehandItem):
            item.add_point(pymupdf.Point(cx, cy))
            return True
        if abs(cx - x) * z < 6 and abs(cy - y) * z < 6:
            return True  # still a click
        item._dragged = True
        if isinstance(item, LineItem):
            item.set_points(pymupdf.Point(x, y), pymupdf.Point(cx, cy))
        elif isinstance(item, ImageItem):
            # The picture fills the box dragged out from the click, in any direction, keeping its shape.
            dx, dy = cx - x, cy - y
            w = max(abs(dx), abs(dy) * item.aspect)
            w = min(w, (page.width - x) if dx >= 0 else x, ((page.height - y) if dy >= 0 else y) * item.aspect)
            h = w / item.aspect
            x0, y0 = (x if dx >= 0 else x - w), (y if dy >= 0 else y - h)
            item.rect_pt = pymupdf.Rect(x0, y0, x0 + w, y0 + h)
            item.relayout()
        elif isinstance(item, TextItem):
            # Dragging sets the box; on release the text size is fitted to its height.
            item.rect_pt = pymupdf.Rect(min(x, cx), min(y, cy), max(x, cx, min(x, cx) + 20), max(y, cy, min(y, cy) + 6))
            item.relayout()
        else:
            item.rect_pt = pymupdf.Rect(min(x, cx), min(y, cy), max(x, cx), max(y, cy))
            item.relayout()
        return True

    def release(self, label, pos):
        if self.tool == "move":
            return self.mover.release(label, pos)
        if not self._placing:
            return False
        item = self._placing[0]
        self._placing = None
        if isinstance(item, FreehandItem):
            return True  # the pen stays on for the next stroke
        dragged = getattr(item, "_dragged", False)
        if not dragged and getattr(self, "_click_off", False):
            self._click_off = False
            self.remove(item, record=False)  # clicking off a shape: deselect, don't add another
            self.drop_checkpoint()
            self.select(None)
            return True
        if isinstance(item, ImageItem) and dragged and item.rect_pt.width * self.view.zoom < 16:
            dragged = False  # barely moved: treat it as a click
        if isinstance(item, ImageItem) and not dragged:
            item.rect_pt = item.default_rect
            item.relayout()
        if isinstance(item, TextItem):
            if dragged and item.rect_pt.height >= 6:
                size = fit_size(item.rect_pt.height)
                self.styles["text"]["size"] = size
                item.apply_style(dict(self.styles["text"], size=size))
            else:
                item.fit_height()
        if not dragged:  # a plain click: a sensible default size
            page = item.page_rect()
            r = item.rect_pt
            if isinstance(item, LineItem):
                item.set_points(item.p1, pymupdf.Point(min(item.p1.x + 100, page.width), item.p1.y))
            elif isinstance(item, ShapeItem):
                w, h = {"highlight": (120, 16), "link": (120, 16), "blur": (120, 20)}.get(item.kind, (120, 60))
                x0, y0 = min(r.x0, page.width - w), min(r.y0, page.height - h)
                item.rect_pt = pymupdf.Rect(x0, y0, x0 + w, y0 + h)
                item.relayout()
        if item.kind in STICKY or getattr(item, "stamp_key", None):  # shapes and stamps stay on for the next one
            item.update()
            self.selection_changed(item)
            return True
        self.set_tool("select")
        if isinstance(item, TextItem):
            item.edit()
        if item.kind == "link":
            link = ask_link(self.view.window(), None)
            if not link:
                self.remove(item, record=False)
                self.drop_checkpoint()
                self.select(None)
                return True
            item.link = link
            item.update()
        self.selection_changed(item)
        return True

    def set_link(self, item):
        """The Link button: give the selected item a link, change it, or take it off."""
        link = ask_link(self.view.window(), item.link)
        if link is None or link == (item.link or ""):
            return
        self.checkpoint()
        if not link and item.kind == "link":
            self.remove(item, record=False)
            return
        item.link = link or None
        item.update()
        self.on_change()

    def drop_image(self, path, global_pos):
        """A picture dragged in from File Explorer: put it where it was dropped."""
        if not self.load_image(path):
            return
        for lbl in self.view.labels:
            p = lbl.mapFromGlobal(global_pos)
            if lbl.rect().contains(p):
                self.set_tool("image")
                self.press(lbl, QPointF(p))
                self.release(lbl, QPointF(p))
                return

    def load_image(self, path):
        img = read_image(path, max_side=3000)  # keeps the PDF a sensible size
        if img is None:
            QMessageBox.warning(self.view, APP_NAME, f"Couldn't open the image:\n{path}\n\nDetails: {overlay.read_error}")
            return False
        with open(path, "rb") as f:
            data = f.read()
        if overlay.file_needs_reencode(path) or img.size() != QImageReader(path).size():
            data = jpeg_or_png(img)
        self.image = (img, data)
        self.stamp_key = None
        return True

    def load_stamp(self, key):
        img = stamp_image(key)
        self.image = (img, png_bytes(img))
        self.stamp_key = key


# ---- the screen ------------------------------------------------------------
def _letter_icon(letter, up):
    """Word's bigger/smaller text buttons: a letter with a small arrow."""
    return drawn(lambda: _letter_pix(letter, up))


def _letter_pix(letter, up):
    pix = QPixmap(44, 44)
    pix.setDevicePixelRatio(2)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    f = p.font()
    f.setPixelSize(15 if up else 12)
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor(theme.ICON))
    p.drawText(QRectF(0, 4, 15, 18), Qt.AlignHCenter | Qt.AlignBottom, letter)
    p.setPen(QPen(QColor(theme.ICON), 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    y = 7 if up else 9
    pts = [QPointF(14.5, y + 3), QPointF(17, y), QPointF(19.5, y + 3)] if up else \
        [QPointF(14.5, y), QPointF(17, y + 3), QPointF(19.5, y)]
    p.drawPolyline(pts)
    p.end()
    return pix


def _bar_icon(base, color):
    """Word-style colour button: a letter (or icon) with a bar of the chosen colour under it."""
    return drawn(lambda: _bar_pix(base, color))


def _bar_pix(base, color):
    pix = QPixmap(44, 44)
    pix.setDevicePixelRatio(2)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    if base == "A":
        f = p.font()
        f.setPixelSize(15)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(theme.ICON))
        p.drawText(QRectF(0, 0, 22, 16), Qt.AlignCenter, "A")
    else:
        p.drawPixmap(4, 0, icon_pixmap(base, 15, "ICON"))
    bar = QRectF(3, 17, 16, 4)
    if color is None:  # no fill
        p.setPen(QPen(QColor(theme.DISABLED), 1))
        p.setBrush(QColor(theme.SURFACE))
        p.drawRect(bar)
        p.setPen(QPen(QColor(theme.DANGER), 1.2))
        p.drawLine(bar.bottomLeft(), bar.topRight())
    else:
        p.setPen(QPen(QColor(theme.DISABLED), 0.8) if abs(QColor(color).lightness() - QColor(theme.SURFACE).lightness()) < 25 else Qt.NoPen)
        p.setBrush(QColor(color))
        p.drawRect(bar)
    p.end()
    return pix


def _swatch(color, none=False):
    pix = QPixmap(16, 16)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setPen(QColor("#888"))
    if none:
        p.setBrush(Qt.white)
        p.drawRect(0, 0, 15, 15)
        p.setPen(QPen(QColor("#d93025"), 2))
        p.drawLine(2, 14, 14, 2)
    else:
        p.setBrush(QColor(color))
        p.drawRect(0, 0, 15, 15)
    p.end()
    return QIcon(pix)


def ask_link(parent, current):
    """Ask where a link goes. Returns "page:N", a web or email address, "" to remove it, or None if cancelled."""
    shown = (current[5:] if current.startswith("page:") else current.removeprefix("mailto:")) if current else ""
    text, ok = QInputDialog.getText(parent, APP_NAME, "Where should the link go?\n\nType a web address, an "
                                    "email address or a page number" + (" (leave it empty to remove the link)."
                                                                        if current else "."),
                                    QLineEdit.Normal, shown)
    if not ok:
        return None
    text = text.strip()
    if not text:
        return ""
    if text.isdigit():
        return f"page:{int(text)}"
    if "@" in text and "/" not in text and ":" not in text:
        return "mailto:" + text
    if "://" not in text and not text.startswith("mailto:"):
        return "https://" + text
    return text


TOOL_GROUPS = [  # (button key, icon, label, tools in its drop-down)
    ("select", "select", "Select", None),
    ("move", "move", "Move", None),
    ("text", "text", "Text", None),
    ("image", "image", "Image", None),
    ("shape", "shape", "Shape", [("rect", "rect", "Rectangle"), ("ellipse", "ellipse", "Ellipse"),
                                 ("line", "line", "Line"), ("arrow", "arrow", "Arrow")]),
    ("draw", "draw", "Draw", [("pen", "draw", "Pen"), ("marker", "marker", "Highlighter pen")]),
    ("highlight", "highlight", "Highlight", None),
    ("link", "link", "Link", None),
    ("whiteout", "whiteout", "White-out", [("whiteout", "whiteout", "White-out box"),
                                           ("wpen", "wpen", "White-out pen")]),
    ("blur", "blur", "Blur", None),
]


class EditTools(BarTools):
    """The Edit tools in the top bar, and a small floating bar with the settings of the selected
    item (or of the tool in use)."""

    def __init__(self, session, view, tip):
        super().__init__()
        self.session, self.tip = session, tip  # tip(tool): shows that tool's hint once
        session.tool_changed = self._tool_changed
        session.on_select = self._selected
        self.buttons = {}  # tool -> its button
        self.group_of = {}
        self.strips = []
        for key, ic, label, subs in TOOL_GROUPS:
            b = tool_button(ic, label, checkable=True)
            if subs:
                b.setPopupMode(QToolButton.MenuButtonPopup)
                menu = QMenu(b)
                for tool, sic, slabel in subs:
                    menu.addAction(icon(sic), slabel, lambda t=tool, b=b: self._pick_sub(b, t))
                    self.buttons[tool] = b
                    self.group_of[tool] = key
                b.setMenu(menu)
                b.tool = subs[0][0]
                b.clicked.connect(lambda _=False, b=b: self._pick_tool(b.tool))
                strip = ToolStrip(b, key, subs, self._pick_sub)  # with any favourites picked in Settings
                self.strips.append(strip)
                self.add(strip)
                continue
            self.buttons[key] = b
            self.group_of[key] = key
            b.clicked.connect(lambda _=False, k=key: self._pick_tool(k))
            self.add(b)
            if key == "image":
                self.stamp_group = StampGroup()
                self.stamp_group.picked.connect(self._pick_stamp)
                self.add(self.stamp_group)
                self.add(separator())

        # Settings for the selected item or tool, floating over the page.
        self.mini = MiniBar(view)
        self.color_btn = self._color_button("Colour", "color")
        self.fill_btn = self._color_button("Fill", "fill", allow_none=True)
        self.color_btn.setToolTip("Colour")
        self.fill_btn.setToolTip("Fill colour")
        # Line thickness: a list like the text size's (or type any), shown as "2 pt".
        self.width_box = QComboBox()
        self.width_box.setEditable(True)
        self.width_box.addItems([f"{w:g} pt" for w in WIDTHS])
        self.width_box.setMaxVisibleItems(len(WIDTHS))
        self.width_box.setFixedWidth(78)
        self.width_box.setToolTip("Line thickness")
        self.width_box.textActivated.connect(self._width_typed)
        self.width_box.lineEdit().editingFinished.connect(lambda: self._width_typed(self.width_box.currentText()))
        self.font_box = QComboBox()
        self.font_box.setMaxVisibleItems(25)
        source = "builtin"
        for f in fonts.all_fonts():
            if f.source != source:
                self.font_box.insertSeparator(self.font_box.count())
                source = f.source
            self.font_box.addItem(f.label, f.key)
            if f.source != "builtin":
                self.font_box.setItemData(self.font_box.count() - 1, fonts.qfont(f.key, 14), Qt.FontRole)
        self.font_box.currentIndexChanged.connect(lambda i: self.session.set_style("font", self.font_box.itemData(i)))
        self.font_box.setMinimumWidth(170)
        self.font_box.setToolTip("Font")
        # Size: a list like Word's (or type any size), with bigger/smaller buttons.
        self.size_box = QComboBox()
        self.size_box.setEditable(True)
        self.size_box.addItems([str(n) for n in SIZES])
        self.size_box.setMaxVisibleItems(len(SIZES))
        self.size_box.setFixedWidth(64)
        self.size_box.setToolTip("Text size")
        self.size_box.setValidator(QDoubleValidator(4, 400, 1, self.size_box))
        self.size_box.textActivated.connect(self._size_typed)
        self.size_box.lineEdit().editingFinished.connect(lambda: self._size_typed(self.size_box.currentText()))
        grow = QToolButton(toolTip="Bigger text")
        grow.setIcon(_letter_icon("A", up=True))
        shrink = QToolButton(toolTip="Smaller text")
        shrink.setIcon(_letter_icon("A", up=False))
        for b, step in ((grow, 1), (shrink, -1)):
            b.setIconSize(QSize(22, 22))
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(lambda _=False, st=step: self._size_step(st))
        self.size_steps = QWidget()
        sl = QHBoxLayout(self.size_steps)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(0)
        sl.addWidget(grow)
        sl.addWidget(shrink)
        self.bold_btn = QToolButton(text="B", toolTip="Bold")
        self.italic_btn = QToolButton(text="I", toolTip="Italic")
        self.under_btn = QToolButton(text="U", toolTip="Underline")
        for b, key in ((self.bold_btn, "bold"), (self.italic_btn, "italic"), (self.under_btn, "underline")):
            b.setCheckable(True)
            b.setFocusPolicy(Qt.NoFocus)
            b.setFixedWidth(30)
            f = b.font()
            f.setPointSizeF(f.pointSizeF() * 1.15)
            f.setBold(key == "bold")
            f.setItalic(key == "italic")
            f.setUnderline(key == "underline")
            f.setFamily("Georgia" if key == "italic" else f.family())
            b.setFont(f)
            b.toggled.connect(lambda v, k=key: self.session.set_style(k, v))
        self.style_widgets = {"font": self.font_box, "size": self.size_box, "size_steps": self.size_steps,
                              "bold": self.bold_btn, "italic": self.italic_btn, "underline": self.under_btn,
                              "color": self.color_btn, "fill": self.fill_btn,
                              "width": self.width_box}
        for w in self.style_widgets.values():
            self.mini.lay.addWidget(w)
        self.link_btn = tool_button("link", "Link…", tip="Make it a link to a web page, an email address or a page")
        self.link_btn.clicked.connect(lambda: self.session.selected() and self.session.set_link(self.session.selected()))
        self.mini.lay.addWidget(self.link_btn)

    def _width_typed(self, text):
        try:
            v = float(text.lower().replace("pt", "").strip())
        except ValueError:
            return
        if 0.25 <= v <= 50:
            self.width_box.setEditText(f"{v:g} pt")
            self.session.set_style("width", v)

    def _size_typed(self, text):
        try:
            v = float(text)
        except ValueError:
            return
        if 4 <= v <= 400:
            self.session.set_style("size", v)

    def _size_step(self, step):
        """Next size up or down the list, like Word's bigger/smaller buttons."""
        try:
            v = float(self.size_box.currentText())
        except ValueError:
            v = 12
        new = next_size(v, step)
        self.size_box.setEditText(f"{new:g}")
        self.session.set_style("size", float(new))

    def _color_button(self, text, key, allow_none=False):
        b = QToolButton()
        b.setToolButtonStyle(Qt.ToolButtonIconOnly)
        b.setIconSize(QSize(22, 22))
        b.setPopupMode(QToolButton.InstantPopup)
        b.setFocusPolicy(Qt.NoFocus)
        menu = QMenu(b)
        if allow_none:
            menu.addAction(_swatch(None, none=True), "No fill", lambda: self._set_color(key, None))
        for name, c in COLORS:
            menu.addAction(_swatch(c), name, lambda c=c: self._set_color(key, c))
        menu.addSeparator()
        menu.addAction("More colours…", lambda: self._more_color(key))
        b.setMenu(menu)
        return b

    def _more_color(self, key):
        c = QColorDialog.getColor(parent=self)
        if c.isValid():
            self._set_color(key, c.name())

    def _set_color(self, key, value):
        self.session.set_style(key, value)
        self._refresh_swatches(key, value)

    def _refresh_swatches(self, key, value):
        if key == "color":
            kind = self.session.selected().kind if self.session.selected() else self.session.tool
            self.color_btn.setIcon(_bar_icon("A" if kind == "text" else "draw", value))
        else:
            self.fill_btn.setIcon(_bar_icon("fill", value))

    def setup(self):
        self._tool_changed("select")

    def hide_mini(self):
        self.mini.hide()

    def _pick_sub(self, button, tool):
        button.tool = tool
        sub = next(s for _, _, _, subs in TOOL_GROUPS if subs for s in subs if s[0] == tool)
        button.setIcon(icon(sub[1]))
        self._pick_tool(tool)

    def _pick_tool(self, tool):
        if tool == "image":
            exts = " ".join("*" + e for e in IMAGE_EXTS)
            path, _ = QFileDialog.getOpenFileName(self, "Choose an image to add", "", f"Images ({exts})")
            if not path or not self.session.load_image(path):
                self.session.set_tool("select")
                return
        self.session.view.setFocus()  # out of the Find box, if it's open
        self.session.select(None)
        self.session.set_tool(tool)
        self.tip(tool)

    def paste_image(self, img):
        """Ctrl+V with a picture on the clipboard: pick it up to place, like the Image tool."""
        if max(img.width(), img.height()) > 3000:  # keeps the PDF a sensible size
            img = img.scaled(3000, 3000, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.session.image = (img, png_bytes(img))
        self.session.stamp_key = None
        self.session.view.setFocus()
        self.session.select(None)
        self.session.set_tool("image")
        self.tip("image")

    def _pick_stamp(self, key):
        self.session.load_stamp(key)
        self.session.view.setFocus()
        self.session.select(None)
        self.session.set_tool("image")
        self.tip("stamp")

    def _tool_changed(self, tool):
        stamp = self.session.stamp_key if tool == "image" else None
        for b in set(self.buttons.values()):
            b.setChecked(b is self.buttons[tool] and not stamp)  # a stamp lights up the stamps, not Image
        self.stamp_group.set_active(stamp)
        for strip in self.strips:
            strip.set_active(tool)
        if not self.session.selected():
            self._show_style(tool, None)

    def _selected(self, item):
        if item is not None:
            self._show_style(item.kind, item)
        else:
            self._show_style(self.session.tool, None)

    def _anchor(self, item):
        def rect():
            try:
                if item is None or not item.isVisible():
                    return None
                view = self.mini.view
                return QRect(item.mapTo(view, item.rect().topLeft()), item.size())
            except RuntimeError:  # the item went away
                return None
        return rect

    def _show_style(self, kind, item):
        keys = STYLE_KEYS.get(kind, ())
        for k, w in self.style_widgets.items():
            w.setVisible((k if k != "size_steps" else "size") in keys)
        self.link_btn.setVisible(item is not None)
        if item is not None:
            self.link_btn.setText("Change link…" if item.link else "Link…")
        if not keys and item is None:
            self.mini.hide()
            return
        style = dict(self.session.style_for(kind))
        if item is not None:  # show the selected item's own settings
            for k in keys:
                if k not in ATTR:
                    continue
                v = getattr(item, ATTR[k], None)
                style[k] = v.name() if isinstance(v, QColor) else v
        for k, w in self.style_widgets.items():
            w.blockSignals(True)
        if "color" in keys:
            self._refresh_swatches("color", style["color"])
        if "fill" in keys:
            self._refresh_swatches("fill", style.get("fill"))
        if "width" in keys:
            self.width_box.setEditText(f"{float(style['width']):g} pt")
        if "font" in keys:
            self.font_box.setCurrentIndex(self.font_box.findData(style["font"]))
        if "size" in keys:
            self.size_box.setEditText(f"{float(style['size']):g}")
        if "bold" in keys:
            self.bold_btn.setChecked(bool(style.get("bold")))
            self.italic_btn.setChecked(bool(style.get("italic")))
            self.under_btn.setChecked(bool(style.get("underline")))
        for k, w in self.style_widgets.items():
            w.blockSignals(False)
        self.mini.follow(self._anchor(item))
