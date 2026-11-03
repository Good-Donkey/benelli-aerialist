"""Things placed on top of the pages (signatures, text boxes, shapes, pictures) before they are
written into the PDF. Each one is a small widget on its page: drag to move, drag a corner to
resize, the red x or Delete removes it. Positions are kept in page points as seen on screen."""
import pymupdf
from PySide6.QtCore import Qt, QPointF, QRectF, QBuffer, QByteArray, QIODevice, QEvent
from PySide6.QtGui import QPainter, QPen, QColor, QImage, QImageReader, QImageIOHandler, QCursor
from PySide6.QtWidgets import QApplication, QWidget

from . import theme

HANDLE = 9
MARGIN = 12  # room around the box for the handles and the delete button
MIN_PT = 6


def png_bytes(img):
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    return bytes(ba)


def jpeg_or_png(img):
    """Compact bytes for a picture going into the PDF: JPEG for photos, PNG if it has see-through parts."""
    if img.hasAlphaChannel():
        return png_bytes(img)
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "JPEG", 90)
    return bytes(ba)


def read_image(path, max_side=None):
    """Open a picture file as a QImage, or None. Big photos are scaled down while reading
    (Qt refuses to open anything over 256 MB of pixels, e.g. a 9000 x 8000 scan). Falls back
    to PyMuPDF's decoder for files Qt's image plugins can't read."""
    global read_error
    reader = QImageReader(path)
    reader.setAutoTransform(True)  # phone photos: turn them the right way up
    size = reader.size()
    if max_side and size.isValid() and max(size.width(), size.height()) > max_side:
        reader.setScaledSize(size.scaled(max_side, max_side, Qt.KeepAspectRatio))
    img = reader.read()
    if not img.isNull():
        return img
    read_error = f"Qt: {reader.errorString()}"
    try:
        pix = pymupdf.Pixmap(path)
        if pix.colorspace and pix.colorspace.n not in (1, 3):  # e.g. CMYK JPEGs
            pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
        if max_side and max(pix.width, pix.height) > max_side:
            pix.shrink(max(0, (max(pix.width, pix.height) // max_side).bit_length() - 1))
        img = QImage.fromData(pix.tobytes("png"))
    except Exception as e:
        read_error += f"; PyMuPDF: {e}"
        return None
    if img.isNull():
        read_error += "; PyMuPDF opened it but the picture could not be shown"
        return None
    return img


def file_needs_reencode(path):
    """True if the file's own bytes can't go into the PDF as they are (rotated photo, odd format)."""
    reader = QImageReader(path)
    reader.setAutoTransform(True)
    return reader.transformation() != QImageIOHandler.Transformation.TransformationNone or \
        bytes(reader.format()).decode().lower() not in ("png", "jpeg", "jpg")


read_error = ""  # why read_image last failed, shown to the user to help track down picture problems


# What an item looks like and where it is: saved before each change so Undo can put it back.
STATE_ATTRS = ("rect_pt", "aspect", "text", "color", "fill", "lw", "opacity", "font_key", "font_size", "bold",
               "italic", "underline", "p1", "p2", "pts", "link")


def _copy(v):
    if isinstance(v, (pymupdf.Rect, pymupdf.Point)):
        return type(v)(v)
    if isinstance(v, QColor):
        return QColor(v)
    if isinstance(v, list):
        return [_copy(x) for x in v]
    return v


def item_state(item):
    return {a: _copy(getattr(item, a)) for a in STATE_ATTRS if hasattr(item, a)}


def to_page(page, rect):
    """On-screen page coordinates -> the page's own coordinates (they differ on rotated pages)."""
    return rect * page.derotation_matrix


def link_spec(link, rect):
    """What page.insert_link needs for a link typed in the Link box ("page:5" or a web or email address)."""
    if link.startswith("page:"):
        return {"kind": pymupdf.LINK_GOTO, "from": rect, "page": int(link[5:]) - 1, "to": pymupdf.Point(0, 0)}
    return {"kind": pymupdf.LINK_URI, "from": rect, "uri": link}


def with_link(write, link, rect):
    """The item's writer, plus its link over the same area."""
    def write_both(page):
        write(page)
        spec = link_spec(link, to_page(page, rect))
        if spec["kind"] == pymupdf.LINK_URI or 0 <= spec["page"] < len(page.parent):
            page.insert_link(spec)
    return write_both


class Item(QWidget):
    keep_aspect = False
    link = None  # set by Edit's Link button: a web or email address, or "page:N"

    def __init__(self, session, label, rect):
        super().__init__(label)
        self.session, self.label = session, label
        self.rect_pt = rect  # pymupdf.Rect in page points, as shown on screen
        self.aspect = rect.width / max(1e-6, rect.height)
        self.selected = False
        self._drag = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.ClickFocus)
        label.installEventFilter(self)  # follow the page when zooming
        self.relayout()
        self.show()

    # ---- to override ----
    def draw(self, p, box):
        """Paint the item into box (widget pixels)."""

    def writer(self):
        """A function(page) that writes this item into a pymupdf page."""
        raise NotImplementedError

    def edit(self):
        """Double-click."""

    # ---- geometry ----
    @property
    def page_index(self):
        return self.label.index

    def eventFilter(self, obj, e):
        if e.type() == QEvent.Resize:
            self.relayout()
        return False

    def zoom(self):
        return self.session.view.zoom

    def page_rect(self):
        return self.session.view.doc[self.page_index].rect

    def box(self):
        """The item's box in this widget's coordinates."""
        return QRectF(MARGIN, MARGIN, self.width() - 2 * MARGIN, self.height() - 2 * MARGIN)

    def relayout(self):
        z, r = self.zoom(), self.rect_pt
        self.setGeometry(int(r.x0 * z) - MARGIN, int(r.y0 * z) - MARGIN,
                         int(r.width * z) + 2 * MARGIN, int(r.height * z) + 2 * MARGIN)
        self.update()

    def _delete_rect(self):
        return QRectF(self.width() - 22, 0, 22, 22)

    def handles(self):
        b = self.box()
        return {"tl": b.topLeft(), "tr": b.topRight(), "bl": b.bottomLeft(), "br": b.bottomRight()}

    def body_hit(self, pos):
        return self.box().adjusted(-4, -4, 4, 4).contains(pos)

    def _hit(self, pos):
        if self.selected and self._delete_rect().contains(pos):
            return "delete"
        if self.selected:
            for name, c in self.handles().items():
                if abs(pos.x() - c.x()) <= HANDLE and abs(pos.y() - c.y()) <= HANDLE:
                    return name
        return "move" if self.body_hit(pos) else None

    # ---- painting ----
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.setRenderHint(QPainter.Antialiasing)
        self.draw(p, self.box())
        if self.link and getattr(self, "kind", "") != "link":  # a small chain at the corner: it's a link
            from .icons import pixmap
            p.drawPixmap(QPointF(self.box().right() + 1, self.box().center().y() - 6), pixmap("link", 12, "ACCENT"))
        if self.selected:
            self.draw_outline(p)
            p.setPen(QPen(QColor(theme.ACCENT_FILL), 1.5))
            p.setBrush(Qt.white)
            for c in self.handles().values():
                p.drawRect(QRectF(c.x() - HANDLE / 2, c.y() - HANDLE / 2, HANDLE, HANDLE))
            d = self._delete_rect().adjusted(3, 3, -3, -3)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#d93025"))
            p.drawEllipse(d)
            p.setPen(QPen(Qt.white, 2))
            c, s = d.center(), 3.5
            p.drawLine(QPointF(c.x() - s, c.y() - s), QPointF(c.x() + s, c.y() + s))
            p.drawLine(QPointF(c.x() - s, c.y() + s), QPointF(c.x() + s, c.y() - s))
        p.end()

    def draw_outline(self, p):
        p.setPen(QPen(QColor(theme.ACCENT_FILL), 1.5, Qt.DashLine))
        p.setBrush(Qt.NoBrush)
        p.drawRect(self.box())

    # ---- mouse ----
    def mouseMoveEvent(self, e):
        pos = e.position()
        if self._drag is None:
            hit = self._hit(pos)
            self.setCursor({"delete": Qt.PointingHandCursor, "move": Qt.SizeAllCursor,
                            "tl": Qt.SizeFDiagCursor, "br": Qt.SizeFDiagCursor,
                            "tr": Qt.SizeBDiagCursor, "bl": Qt.SizeBDiagCursor}.get(hit, Qt.CrossCursor))
            return
        mode, start, rect = self._drag
        z = self.zoom()
        cur = self.mapToParent(pos.toPoint())
        self.drag_to(mode, rect, (cur.x() - start.x()) / z, (cur.y() - start.y()) / z)
        self.relayout()

    def drag_to(self, mode, rect, dx, dy):
        page = self.page_rect()
        if mode == "move":
            dx = max(-rect.x0, min(dx, page.width - rect.x1))
            dy = max(-rect.y0, min(dy, page.height - rect.y1))
            self.rect_pt = pymupdf.Rect(rect.x0 + dx, rect.y0 + dy, rect.x1 + dx, rect.y1 + dy)
            return
        right, bottom = "r" in mode, "b" in mode
        if self.keep_aspect:
            # The opposite corner stays put and the shape is kept.
            w = rect.width + (dx if right else -dx)
            h = rect.height + (dy if bottom else -dy)
            w = max(w, h * self.aspect, MIN_PT * self.aspect)
            ax = rect.x0 if right else rect.x1
            ay = rect.y0 if bottom else rect.y1
            w = min(w, (page.width - ax) if right else ax, ((page.height - ay) if bottom else ay) * self.aspect)
            h = w / self.aspect
            x0 = ax if right else ax - w
            y0 = ay if bottom else ay - h
            self.rect_pt = pymupdf.Rect(x0, y0, x0 + w, y0 + h)
            return
        x0, y0, x1, y1 = rect
        if right:
            x1 = max(x0 + MIN_PT, min(x1 + dx, page.width))
        else:
            x0 = min(x1 - MIN_PT, max(x0 + dx, 0))
        if bottom:
            y1 = max(y0 + MIN_PT, min(y1 + dy, page.height))
        else:
            y0 = min(y1 - MIN_PT, max(y0 + dy, 0))
        self.rect_pt = pymupdf.Rect(x0, y0, x1, y1)

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        hit = self._hit(e.position())
        if hit is None:
            e.ignore()
            return
        if hit == "delete":
            self.session.remove(self)
            return
        self.session.checkpoint()  # moving or resizing can be undone (nothing is kept if it doesn't change)
        self.session.select(self)
        self._drag = (hit, self.mapToParent(e.position().toPoint()), self.drag_state())

    def drag_state(self):
        return pymupdf.Rect(self.rect_pt)

    def mouseReleaseEvent(self, e):
        if self._drag and self._drag[0] != "move":
            self.session.remember_size(self)
        self._drag = None

    def mouseDoubleClickEvent(self, e):
        if self._hit(e.position()) == "move":
            self.edit()

    def keyPressEvent(self, e):
        steps = {Qt.Key_Left: (-1, 0), Qt.Key_Right: (1, 0), Qt.Key_Up: (0, -1), Qt.Key_Down: (0, 1)}
        if e.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.session.remove(self)
        elif e.key() in steps:  # nudge 1 pt, or 10 pt with Shift
            self.session.checkpoint(("nudge", self))
            n = 10 if e.modifiers() & Qt.ShiftModifier else 1
            self.drag_to("move", self.drag_state(), steps[e.key()][0] * n, steps[e.key()][1] * n)
            self.relayout()
        else:
            super().keyPressEvent(e)

    def event(self, e):
        if e.type() == QEvent.ShortcutOverride and e.key() in (Qt.Key_Delete, Qt.Key_Backspace, Qt.Key_Left,
                                                               Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
            e.accept()  # the Delete key removes this item, not pages
            return True
        return super().event(e)


class ImageItem(Item):
    keep_aspect = True

    def __init__(self, session, label, rect, image, data=None):
        self.image = image
        self.data = data  # original file bytes, if any (keeps photos as compact JPEGs)
        super().__init__(session, label, rect)
        self.aspect = image.width() / max(1, image.height())

    def draw(self, p, box):
        p.drawImage(box, self.image)

    def writer(self):
        rect, data = pymupdf.Rect(self.rect_pt), self.data or png_bytes(self.image)

        def write(page):
            page.insert_image(to_page(page, rect), stream=data, rotate=page.rotation)
        return write


_blank = False


def hide_pointer(on):
    """While a see-through copy follows the mouse, the pointer itself is hidden so the copy is easy to see."""
    global _blank
    if on and not _blank:
        QApplication.setOverrideCursor(Qt.BlankCursor)
    elif not on and _blank:
        QApplication.restoreOverrideCursor()
    _blank = on


class Ghost(QWidget):
    """A see-through copy of a stamp that follows the mouse until it is clicked onto the page."""

    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.image = None

    def show_at(self, label, rect, image, zoom):
        if self.parentWidget() is not label:
            self.setParent(label)
        self.image = image
        self.setGeometry(int(rect.x0 * zoom), int(rect.y0 * zoom), max(1, int(rect.width * zoom)),
                         max(1, int(rect.height * zoom)))
        self.show()
        hide_pointer(True)
        self.raise_()
        self.update()

    def paintEvent(self, e):
        if self.image is not None:
            p = QPainter(self)
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            p.setOpacity(0.6)
            p.drawImage(self.rect(), self.image)
            p.end()


def resize_about_center(item, factor):
    """Make an item bigger or smaller around its middle, keeping its shape and staying on the page."""
    r, page = item.rect_pt, item.page_rect()
    w = max(MIN_PT * item.aspect, min(r.width * factor, page.width, page.height * item.aspect))
    h = w / item.aspect
    cx, cy = (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2
    x0 = max(0, min(cx - w / 2, page.width - w))
    y0 = max(0, min(cy - h / 2, page.height - h))
    item.rect_pt = pymupdf.Rect(x0, y0, x0 + w, y0 + h)
    item.relayout()


# Text sizes offered in the size boxes; the bigger/smaller buttons and the scroll wheel step through them.
SIZES = [6, 7, 8, 9, 10, 11, 12, 14, 16, 18, 20, 22, 24, 26, 28, 32, 36, 40, 48, 60, 72, 96]


def next_size(v, steps):
    """steps sizes up (or down, if negative) the list, like Word's bigger/smaller buttons."""
    for _ in range(abs(steps)):
        if steps > 0:
            v = next((n for n in SIZES if n > v + 0.01), min(400, v + 12))
        else:
            v = next((n for n in reversed(SIZES) if n < v - 0.01), max(4, v - 1))
    return float(v)


def line_image(text, font, color="#000000"):
    """A line of text drawn 4x large on a see-through background, and its size in points."""
    from PySide6.QtGui import QFontMetricsF
    fm = QFontMetricsF(font)
    w, h = fm.horizontalAdvance(text) + font.pixelSize() * 0.4, fm.height()
    img = QImage(max(1, int(w)), max(1, int(h)), QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.TextAntialiasing)
    p.setFont(font)
    p.setPen(QColor(color))
    p.drawText(QRectF(0, 0, w, h), Qt.AlignLeft | Qt.AlignVCenter, text)
    p.end()
    return img, w / 4, h / 4


class OverlaySession:
    """Items placed on the pages of a PageView. Hooks into the view's page mouse events."""

    def __init__(self, view, on_change):
        self.view, self.on_change = view, on_change
        self.stamps = []
        self._gone = []  # removed items, kept (hidden) so Undo can bring them back
        self._undo, self._redo = [], []
        self._last_tag = None
        self._ghost = None

    # ---- a see-through copy follows the mouse; the scroll wheel resizes ----
    def armed_preview(self, label, pos):
        """(image, rect in page points) of what a click at pos would put down, or None."""
        return None

    def wheel_armed(self, delta):
        """Scroll wheel while something is picked up but not yet placed: change its size. True if used."""
        return False

    def resize_item(self, item, delta):
        """Scroll wheel while an item is being placed or dragged: change its size. True if used."""
        if getattr(item, "font_size", None) is not None:
            n = self.wheel_steps(delta)
            if n:
                self.set_item_size(item, next_size(item.font_size, n))
            return True
        if item.keep_aspect:
            resize_about_center(item, 1.1 ** (delta / 120))
            if getattr(item, "default_rect", None) is not None:
                item.default_rect = pymupdf.Rect(item.rect_pt)
            self.remember_size(item)
            return True
        return False

    def set_item_size(self, item, size):
        """Text size of a text item (and of the next one)."""

    def wheel_steps(self, delta):
        """Whole notches of the wheel (touchpads send small amounts, which add up)."""
        self._wheel_acc = getattr(self, "_wheel_acc", 0) + delta
        n = int(self._wheel_acc / 120)
        self._wheel_acc -= n * 120
        return n

    def follow(self, label, pos):
        preview = self.armed_preview(label, pos)
        if not preview:
            self.hide_ghost()
            return
        self._ghost_at = (label, pos)
        image, rect = preview
        try:
            self._ghost.show_at(label, rect, image, self.view.zoom)
        except (AttributeError, RuntimeError):  # none yet, or it went away with a page that was rebuilt
            self._ghost = Ghost()
            self._ghost.show_at(label, rect, image, self.view.zoom)

    def ghost_showing(self):
        try:
            showing = self._ghost is not None and self._ghost.isVisible()
        except RuntimeError:  # it went away with a page that was rebuilt
            self._ghost, showing = None, False
        if not showing:
            hide_pointer(False)
        return showing

    def hide_ghost(self):
        hide_pointer(False)
        if self._ghost is not None:
            try:
                self._ghost.hide()
            except RuntimeError:
                self._ghost = None

    def leave(self, label):
        """The pointer left a page."""
        hide_pointer(False)
        try:
            if self._ghost is not None and self._ghost.parentWidget() is label:
                self._ghost.hide()
        except RuntimeError:
            self._ghost = None

    def scrolled(self):
        """The pages moved under the pointer: keep the see-through copy under it."""
        if not self.ghost_showing():
            return
        for lbl in self.view.labels:
            p = lbl.mapFromGlobal(QCursor.pos())
            if lbl.isVisible() and lbl.rect().contains(p):
                self.follow(lbl, QPointF(p))
                return
        self.hide_ghost()

    def wheel(self, event):
        """Ctrl+scroll over the pages: resizes what is being placed or moved, or the thing picked up.
        Otherwise (or with the pointer off the pages) it zooms as usual."""
        delta = event.angleDelta().y()
        if not delta:
            return False
        item = self.placing_item() or next((s for s in self.stamps if s._drag), None)
        if item is not None:
            if not self.resize_item(item, delta):
                return False
            if item._drag:  # carry on dragging from here
                mode, _, _ = item._drag
                item._drag = (mode, item.label.mapFromGlobal(QCursor.pos()), item.drag_state())
            return True
        if self.ghost_showing() and self.wheel_armed(delta):
            if getattr(self, "_ghost_at", None):
                try:
                    self.follow(*self._ghost_at)
                except RuntimeError:
                    pass
            return True
        return False

    def stamp_rect(self, label, pos, key, image):
        """Where a stamp clicked at pos goes: centred on the pointer, kept on the page."""
        from . import stamps
        h = stamps.height(key)
        return self.centred_rect(label, pos, h * image.width() / max(1, image.height()), h)

    def centred_rect(self, label, pos, w, h):
        z = self.view.zoom
        page = self.view.doc[label.index].rect
        x, y = pos.x() / z, pos.y() / z
        x0, y0 = max(0, min(x - w / 2, page.width - w)), max(0, min(y - h / 2, page.height - h))
        return pymupdf.Rect(x0, y0, x0 + w, y0 + h)

    def placing_item(self):
        """The item being placed right now (mouse still down), or None."""
        return None

    def start(self):
        self.view.page_mouse = self

    def stop(self):
        self.view.page_mouse = None
        self.hide_ghost()
        self._ghost_at = None
        for s in self.stamps + self._gone:
            s.deleteLater()
        self.stamps, self._gone = [], []
        self._undo, self._redo, self._last_tag = [], [], None

    # ---- undo / redo ----
    def finish_typing(self):
        """End any typing in progress (so it is part of the state)."""

    def state(self):
        """Everything Undo puts back. Sessions add their own parts (see extra_state)."""
        return {"items": [(s, item_state(s)) for s in self.stamps], "extra": self.extra_state()}

    def extra_state(self):
        return None

    def set_extra_state(self, extra):
        pass

    def _same(self, a, b):
        return repr(a) == repr(b)

    def checkpoint(self, tag=None):
        """Call before a change. Changes with the same tag in a row (typing in one form field,
        nudging one item) are one Undo step."""
        if tag is not None and tag == self._last_tag and self._undo:
            return
        self._last_tag = tag
        self._undo.append(self.state())
        self._redo = []
        if len(self._undo) > 200:
            self._undo.pop(0)
        self.on_change()  # Undo becomes available

    def can_undo(self):
        return bool(self._undo)

    def can_redo(self):
        return bool(self._redo)

    def undo(self):
        self._step(self._undo, self._redo)

    def redo(self):
        self._step(self._redo, self._undo)

    def _step(self, source, target):
        self.finish_typing()
        now = self.state()
        while source:
            old = source.pop()
            if not self._same(old, now):  # skip steps that changed nothing (a click on an item)
                target.append(now)
                self.restore(old)
                break
        self._last_tag = None
        self.on_change()

    def restore(self, state):
        keep = [item for item, _ in state["items"]]
        for item in self.stamps + self._gone:
            if item not in keep:
                item.selected = False
                item.hide()
        for item, st in state["items"]:
            for a, v in st.items():
                setattr(item, a, _copy(v))
            item.show()
            item.relayout()
            item.update()
        self._gone = [i for i in self.stamps + self._gone if i not in keep]
        self.stamps = keep
        self.set_extra_state(state["extra"])
        self.selection_changed(self.selected())

    def pending(self):
        """How many changes are waiting to be written into the PDF."""
        return len(self.stamps)

    def add(self, item):
        self.checkpoint()
        self.stamps.append(item)
        self.select(item)
        self.on_change()

    def selected(self):
        return next((s for s in self.stamps if s.selected), None)

    def select(self, item):
        for s in self.stamps:
            if s.selected != (s is item):
                s.selected = s is item
                s.update()
        if item:
            item.raise_()
            item.setFocus()
        self.selection_changed(item)

    def selection_changed(self, item):
        pass

    def remove(self, item, record=True):
        if item not in self.stamps:
            return
        if record:
            self.checkpoint()
        self.stamps.remove(item)
        item.selected = False
        item.hide()
        self._gone.append(item)
        self.selection_changed(None)
        self.on_change()

    def drop_checkpoint(self):
        """Forget the last checkpoint (the change it was for didn't happen after all)."""
        if self._undo:
            self._undo.pop()
        self._last_tag = None

    def remember_size(self, item):
        pass

    def armed_or_tool(self):
        """True while a tool is picked up (Esc puts it down)."""
        return False

    def cancel_tool(self):
        pass

    def set_cursor(self, cursor):
        for lbl in self.view.labels:
            if cursor is None:
                lbl.unsetCursor()
            else:
                lbl.setCursor(cursor)

    def peek(self):
        """The placed items as (page index, writer), left where they are (for printing them)."""
        # White-out goes first, so it never wipes out something placed on top of it.
        items = sorted(self.stamps, key=lambda s: getattr(s, "kind", "") not in ("whiteout", "wpen"))
        return [(s.page_index, with_link(s.writer(), s.link, pymupdf.Rect(s.rect_pt)) if s.link else s.writer())
                for s in items]

    def take(self):
        """Hand over the placed items as (page index, writer) and clear them off the pages."""
        specs = self.peek()
        self.stop()
        self.start()
        return specs


def apply_items(doc, specs):
    for index, write in specs:
        write(doc[index])
