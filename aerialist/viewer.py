"""Continuous-scroll PDF page view: background rendering, links, search highlights."""
import html
from bisect import bisect_left

import pymupdf
from PySide6.QtCore import Qt, Signal, QTimer, QPropertyAnimation, QEasingCurve, QRectF, QUrl, QObject, QEvent, QPoint, QPointF
from PySide6.QtGui import QPixmap, QPainter, QColor, QDesktopServices, QImage, QPolygonF, QCursor
from PySide6.QtWidgets import QScrollArea, QWidget, QVBoxLayout, QLabel, QApplication, QMessageBox

from .renderer import Renderer
from . import theme
from .popups import APP_NAME, ask

PAGE_GAP = 12
MIN_ZOOM, MAX_ZOOM = 0.25, 5.0
# Biggest whole-page picture, in pixels. A big drawing zoomed right in would otherwise be drawn as one picture of
# hundreds of megabytes; past this the page is drawn whole at a lower sharpness, plus a sharp piece of the part
# on screen (redrawn as you scroll).
LIMIT_PX = 8_000_000
HIGHLIGHT = QColor(255, 210, 0, 110)
CURRENT_HIGHLIGHT = QColor(255, 120, 0, 140)


class PageLabel(QLabel):
    """One page. Draws search highlights on top and reports clicks/hover in PDF coordinates."""

    def __init__(self, view, index):
        super().__init__()
        self.view, self.index = view, index
        self.highlights = []  # list of (pymupdf.Rect, is_current)
        self.marks = []  # list of (pymupdf.Rect, QColor): words being chosen, a comment just picked
        self.setStyleSheet("background: white;")
        self.setMouseTracking(True)

    # The canvas draws each page's edge and shadow, so it must redraw when pages move or change size
    # (otherwise old edges stay behind after zooming out).
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.parentWidget():
            self.parentWidget().update()

    def moveEvent(self, event):
        super().moveEvent(event)
        if self.parentWidget():
            self.parentWidget().update()

    def paintEvent(self, event):
        super().paintEvent(event)
        detail = self.view.details.get(self.index)
        if detail is not None and not self.pixmap().isNull():  # the sharp piece of a big page, over the rest
            _, (x0, y0, x1, y1), pix, _ = detail
            z = self.view.zoom
            p = QPainter(self)
            p.drawPixmap(QRectF(x0 * z, y0 * z, (x1 - x0) * z, (y1 - y0) * z), pix, QRectF(pix.rect()))
            p.end()
        preview = self.view.previews.get(self.index) if self.pixmap().isNull() else None
        if preview is not None:  # not drawn sharp yet: show the small thumbnail picture stretched
            p = QPainter(self)
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            p.drawImage(self.rect(), preview)
            p.end()
        elif self.pixmap().isNull():  # not drawn at all yet: say so instead of showing a blank page
            p = QPainter(self)
            p.setPen(QColor("#888888"))  # on the white page
            f = p.font()
            f.setPointSizeF(f.pointSizeF() * 1.4)
            p.setFont(f)
            # Near the top, so it's visible even when only the start of a tall page is on screen.
            p.drawText(self.rect().adjusted(0, 0, 0, -max(0, self.height() - 240)), Qt.AlignCenter,
                       f"Loading page {self.index + 1}…")
            p.end()
        if self.highlights:
            p = QPainter(self)
            z = self.view.zoom
            for r, current in self.highlights:
                p.fillRect(QRectF(r.x0 * z, r.y0 * z, r.width * z, r.height * z),
                           CURRENT_HIGHLIGHT if current else HIGHLIGHT)
            p.end()
        if self.marks:
            p = QPainter(self)
            z = self.view.zoom
            for r, color in self.marks:
                p.fillRect(QRectF(r.x0 * z, r.y0 * z, r.width * z, r.height * z), color)
            p.end()
        if self.view.selector is not None and self.view.page_mouse is None:  # words or a picture chosen in Read
            p = QPainter(self)
            self.view.selector.paint(self, p)
            p.end()
        if self.view.page_paint is not None:  # a screen's own drawing on top (Prepare Form's field outlines)
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            self.view.page_paint(self, p)
            p.end()

    def _pdf_point(self, event):
        z = self.view.zoom
        return pymupdf.Point(event.position().x() / z, event.position().y() / z)

    def mousePressEvent(self, event):
        hook = self.view.page_mouse
        if hook and event.button() == Qt.LeftButton:
            hook.press(self, event.position())
        elif not hook and event.button() == Qt.LeftButton and self.view.selector:
            self.view.selector.press(self, event.position())

    def mouseDoubleClickEvent(self, event):
        if not self.view.page_mouse and event.button() == Qt.LeftButton and self.view.selector:
            self.view.selector.double_click(self, event.position())
        else:
            super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event):
        hook = self.view.page_mouse
        if hook:  # signing: the Sign screen handles the mouse, links are off
            hook.move(self, event.position())
            return
        selector = self.view.selector
        if selector and selector.dragging() and event.buttons() & Qt.LeftButton:
            selector.move(self, event.position())
            self.setCursor(Qt.IBeamCursor)
            return
        point = self._pdf_point(event)
        note = self.view.annot_at(self.index, point)
        if note is not None:  # a comment: its text shows on hover, a click opens it in the comments list
            self.setCursor(Qt.PointingHandCursor)
            self.setToolTip(note[2])
            return
        link = self.view.link_at(self.index, point)
        text = selector is not None and selector.over_text(self.index, point)
        self.setCursor(Qt.PointingHandCursor if link else Qt.IBeamCursor if text else Qt.ArrowCursor)
        self.setToolTip(link.get("uri", "") if link else "")

    def leaveEvent(self, event):
        hook = self.view.page_mouse
        if hook and hasattr(hook, "leave"):
            hook.leave(self)

    def mouseReleaseEvent(self, event):
        hook = self.view.page_mouse
        if hook:
            hook.release(self, event.position())
            return
        if event.button() == Qt.LeftButton:
            selector = self.view.selector
            if selector and selector.release(self, event.position()):
                return  # chose some words
            note = self.view.annot_at(self.index, self._pdf_point(event))
            if note is not None:
                self.view.annot_clicked.emit(self.index, note[1])
                return
            link = self.view.link_at(self.index, self._pdf_point(event))
            if link:
                self.view.follow_link(link)
            elif selector:
                selector.click(self, event.position())


class PageContainer(QWidget):
    """Light grey canvas behind the pages, with a thin edge and soft shadow round each page."""

    def __init__(self, view):
        super().__init__()
        self.view = view
        self.setObjectName("pageContainer")
        self.setAttribute(Qt.WA_StyledBackground, True)

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        clip = e.rect()
        labels = self.view.labels
        for i in range(self.view.first_page_below(clip.top() - 4), len(labels)):
            g = labels[i].geometry()
            if g.top() - 4 > clip.bottom():
                break
            for d, a in ((3, 10), (2, 16), (1, 24)):
                p.fillRect(g.adjusted(-d, -d + 1, d, d + 1), QColor(0, 0, 0, a))
            p.fillRect(g.adjusted(-1, -1, 1, 1), QColor(theme.PAGE_EDGE))
        p.end()


class AutoScroll(QObject):
    """Middle-click scrolling like in Windows browsers: click the wheel, move the mouse away from the
    marker to glide (faster the further away), click again to stop. Holding the wheel down while
    moving works too, stopping when it's let go."""
    DEAD = 12  # pixels round the marker that don't scroll

    def __init__(self, view):
        super().__init__(view)
        self.view = view
        self.origin = None
        self.held = False  # wheel kept down and dragged, rather than clicked
        self.marker = _Marker(view)
        self.timer = QTimer(self, interval=16)
        self.timer.timeout.connect(self._step)
        self._carry = [0.0, 0.0]
        QApplication.instance().installEventFilter(self)

    def _inside(self, obj):
        vp = self.view.viewport()
        return isinstance(obj, QWidget) and (obj is vp or vp.isAncestorOf(obj))

    def eventFilter(self, obj, e):
        t = e.type()
        if self.origin is None:
            if (t == QEvent.MouseButtonPress and e.button() == Qt.MiddleButton and self._inside(obj)
                    and self.view.doc):
                self.start(self.view.mapFromGlobal(e.globalPosition().toPoint()))
                return True
            return False
        if t == QEvent.MouseMove:
            if e.buttons() & Qt.MiddleButton and (self._offset() - QPoint()).manhattanLength() > self.DEAD:
                self.held = True
            return False
        if t == QEvent.MouseButtonRelease and e.button() == Qt.MiddleButton:
            if self.held:
                self.stop()
            return True
        if t in (QEvent.MouseButtonPress, QEvent.MouseButtonDblClick, QEvent.Wheel, QEvent.KeyPress):
            self.stop()  # any click, wheel or key ends it, and is used up doing so
            return True
        if t in (QEvent.WindowDeactivate, QEvent.Hide) and obj is self.view.window():
            self.stop()
        return False

    def start(self, pos):
        self.origin, self.held, self._carry = pos, False, [0.0, 0.0]
        self.marker.move(pos.x() - self.marker.width() // 2, pos.y() - self.marker.height() // 2)
        self.marker.horizontal = self.view.horizontalScrollBar().maximum() > 0
        self.marker.show()
        self.marker.raise_()
        QApplication.setOverrideCursor(Qt.SizeAllCursor)
        self.timer.start()

    def stop(self):
        if self.origin is None:
            return
        self.origin = None
        self.timer.stop()
        self.marker.hide()
        QApplication.restoreOverrideCursor()
        self.view._on_scroll()

    def _offset(self):
        return self.view.mapFromGlobal(QCursor.pos()) - self.origin

    def _step(self):
        off = self._offset()
        for n, (d, bar) in enumerate(((off.x(), self.view.horizontalScrollBar()),
                                      (off.y(), self.view.verticalScrollBar()))):
            if abs(d) <= self.DEAD:
                continue
            d = d - self.DEAD if d > 0 else d + self.DEAD
            # Gentle near the marker, quick further away (pixels per frame).
            speed = (abs(d) / 8) ** 1.3 * (1 if d > 0 else -1)
            self._carry[n] += speed
            whole = int(self._carry[n])
            if whole:
                self._carry[n] -= whole
                bar.setValue(bar.value() + whole)


class _Marker(QWidget):
    """The round marker showing where middle-click scrolling started."""

    def __init__(self, parent):
        super().__init__(parent)
        self.horizontal = False
        self.setFixedSize(30, 30)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.hide()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QColor(0, 0, 0, 90))
        p.setBrush(QColor(255, 255, 255, 235))
        p.drawEllipse(1, 1, 28, 28)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.ACCENT_FILL))
        c = 15
        arrows = [((c, 5), (c - 4, 10), (c + 4, 10)), ((c, 25), (c - 4, 20), (c + 4, 20))]
        if self.horizontal:
            arrows += [((5, c), (10, c - 4), (10, c + 4)), ((25, c), (20, c - 4), (20, c + 4))]
        for tri in arrows:
            p.drawPolygon(QPolygonF([QPointF(*pt) for pt in tri]))
        p.drawEllipse(c - 2, c - 2, 4, 4)
        p.end()


class PageView(QScrollArea):
    current_page_changed = Signal(int)
    zoom_changed = Signal(float)
    thumb_ready = Signal(int, QImage)
    page_drawn = Signal(int)  # a page's sharp drawing arrived
    annot_clicked = Signal(int, int)  # page, comment's xref

    def __init__(self, parent=None):
        super().__init__(parent)
        self.doc = None
        self.renderer = None
        self.zoom = 1.25
        self.labels = []
        self.rendered = {}  # page index -> render scale (zoom x screen scaling) it was drawn at
        self.previews = {}  # page index -> small QImage (the thumbnail), shown until the sharp drawing arrives
        self.details = {}  # page index -> (scale, clip, QPixmap, up to date): sharp piece of a big page (LIMIT_PX)
        self._links = {}  # page index -> list of link dicts (cached)
        self._annots = {}  # page index -> list of (Rect on screen, xref, hover text) for comments (cached)
        self._current = 0
        self.page_mouse = None  # set while signing: gets press/move/release on pages first
        self.page_paint = None  # page_paint(label, painter): drawn over each page
        self.selector = None  # chooses words and pictures in Read when no tool has the mouse (textselect.py)

        self.container = PageContainer(self)
        theme.style(self.container, "#pageContainer {{ background: {CANVAS}; }}")
        self.layout_ = QVBoxLayout(self.container)
        self.layout_.setSpacing(PAGE_GAP)
        self.layout_.setContentsMargins(PAGE_GAP, PAGE_GAP, PAGE_GAP, PAGE_GAP)
        self.layout_.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.setWidget(self.container)
        self.setWidgetResizable(True)

        # Debounce render requests while scrolling/zooming.
        self._timer = QTimer(self, singleShot=True, interval=30)
        self._timer.timeout.connect(self._request_visible)
        self.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self.horizontalScrollBar().valueChanged.connect(self._on_scroll)
        self._anim = QPropertyAnimation(self.verticalScrollBar(), b"value", self)
        self._anim.setDuration(350)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.finished.connect(self._on_scroll)
        self.autoscroll = AutoScroll(self)

    # ---- document -------------------------------------------------------
    def warm_up(self):
        """Start the drawing processes before any file is opened. Starting them takes a second or two in the
        installed app (each is a fresh copy of it), so doing it while the Home screen is up makes the first
        file's later pages appear at once. They're kept for every file after that."""
        if self.renderer is None:
            self.renderer = Renderer(None)
            self.renderer.rendered.connect(self._on_rendered)
            self.renderer.detailed.connect(self._on_detailed)

    def shutdown(self):
        """Stop the drawing processes (the window is closing)."""
        if self.renderer:
            self.renderer.stop()
            self.renderer = None

    def set_document(self, doc, path=None, password=None):
        if self.renderer:  # the same drawing processes switch to the new file (or let go of the old one)
            self.renderer.reload(path if doc else None, password)
            self.renderer.hide_fields = False
        elif doc:
            self.warm_up()
            self.renderer.reload(path, password)
        self.doc = doc
        self.render_path, self.render_password = path, password
        self._links = {}
        self._annots = {}
        self.previews = {}
        self._current = 0
        self._rebuild()
        self.verticalScrollBar().setValue(0)
        if doc and len(doc):
            self._draw_now(0)

    def _draw_now(self, index):
        """Draw one page right here (a few hundredths of a second), so a newly opened file shows at once
        instead of waiting for the background drawing to start up."""
        try:
            scale = self._page_scale(index)
            pix = self.doc[index].get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
        except Exception:
            return
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888).copy()
        qp = QPixmap.fromImage(img)
        qp.setDevicePixelRatio(scale / self.zoom)
        self.labels[index].setPixmap(qp)
        self.rendered[index] = scale

    def reload(self, doc, path, password=None, mapping=None, page=0, scroll=None):
        """Show an edited version of the document.

        mapping[i] is the old index of new page i (None for new or changed pages); their
        already-drawn images are kept so unchanged pages don't flash while re-rendering.
        """
        keep, sharp = {}, {}
        for new_i, old_i in enumerate(mapping or []):
            # A page waiting to be drawn again keeps its last picture meanwhile (no flash of "Loading").
            if old_i is not None and old_i < len(self.labels) and not self.labels[old_i].pixmap().isNull():
                keep[new_i] = self.labels[old_i].pixmap()
                if self.rendered.get(old_i) == self._page_scale(old_i):
                    sharp[new_i] = self.rendered[old_i]
        self.previews = {new_i: self.previews[old_i] for new_i, old_i in enumerate(mapping or [])
                         if old_i is not None and old_i in self.previews}
        self.doc = doc
        self.render_path, self.render_password = path, password
        self._links = {}
        self._annots = {}
        self.renderer.reload(path, password)
        self._rebuild()
        for i, pix in keep.items():
            self.labels[i].setPixmap(pix)
            if i in sharp and sharp[i] == self._page_scale(i):
                self.rendered[i] = sharp[i]
        self._current = min(page, len(self.labels) - 1)
        self.container.layout().activate()
        if scroll is not None:  # the same pages, changed a little: stay exactly where you were
            self.verticalScrollBar().setValue(scroll[0])
            self.horizontalScrollBar().setValue(scroll[1])
        else:
            QTimer.singleShot(0, lambda: self.go_to_page(self._current, animate=False))

    def redraw(self, indices):
        """Draw pages again from the document (their old pictures stay until the new ones are ready)."""
        for i in indices:
            self.rendered.pop(i, None)
            self._stale_detail(i)
        self._schedule_render()

    def _rebuild(self):
        for lbl in self.labels:
            lbl.deleteLater()
        self.labels, self.rendered, self.details = [], {}, {}
        if not self.doc:
            return
        for i, page in enumerate(self.doc):
            lbl = PageLabel(self, i)
            lbl.setFixedSize(int(page.rect.width * self.zoom), int(page.rect.height * self.zoom))
            self.layout_.addWidget(lbl, 0, Qt.AlignHCenter)
            self.labels.append(lbl)
        self._schedule_render()

    def patch_page(self, index, data):
        """Redraw a page from new drawing instructions (its old picture stays until the new one is ready)."""
        if self.renderer:
            self.renderer.patch(index, data)
            self.rendered.pop(index, None)  # keep its old picture until the new one arrives
            self._stale_detail(index)
            self._schedule_render()

    def set_hide_fields(self, hide):
        """Redraw the pages with or without their form fields (kept until the new drawing arrives)."""
        if self.renderer and self.renderer.hide_fields != hide:
            self.renderer.set_hide_fields(hide)
            self.rendered = {}
            for i in list(self.details):
                self._stale_detail(i)
            self._schedule_render()

    def request_thumbnails(self, width, indices=None):
        if self.renderer:
            dpr = self.devicePixelRatioF()
            indices = range(len(self.doc)) if indices is None else indices
            self.renderer.set_thumb_jobs([(i, width * dpr / self.doc[i].rect.width) for i in indices])

    def _scale(self):
        # Render at the screen's real pixel density so text is sharp on 125%/150% Windows scaling.
        return self.zoom * self.devicePixelRatioF()

    def _page_scale(self, index):
        """The scale a page is drawn whole at: the screen's, unless that would make too big a picture."""
        scale = self._scale()
        lbl = self.labels[index]  # its size, not the document's page: this also works while swapping documents
        w, h = lbl.width() / self.zoom, lbl.height() / self.zoom
        return scale if w * h * scale * scale <= LIMIT_PX else (LIMIT_PX / max(1.0, w * h)) ** 0.5

    def _stale_detail(self, index):
        """The page changed: its sharp piece stays on show until the new one arrives."""
        if index in self.details:
            self.details[index] = self.details[index][:3] + (False,)

    def _on_detailed(self, index, scale, clip, img, gen):
        if self.renderer is None or self.sender() is not self.renderer or not self.renderer.current(gen):
            return
        if index < len(self.labels) and abs(scale - self._scale()) < 1e-6:
            self.details[index] = (scale, clip, QPixmap.fromImage(img), True)
            self.labels[index].update()

    def _on_rendered(self, kind, index, scale, img, gen):
        if self.renderer is None or self.sender() is not self.renderer or not self.renderer.current(gen):
            return  # drawn for a document (or version of it) that is no longer showing
        if kind == "thumb":
            if index < len(self.labels):
                self.previews[index] = img
                if index not in self.rendered:
                    self.labels[index].update()
            self.thumb_ready.emit(index, img)
        elif index < len(self.labels) and abs(scale - self._page_scale(index)) < 1e-6:
            pix = QPixmap.fromImage(img)
            pix.setDevicePixelRatio(scale / self.zoom)
            self.labels[index].setPixmap(pix)
            self.rendered[index] = scale
            self.page_drawn.emit(index)

    def _schedule_render(self):
        # Run after the layout has placed the pages, so visibility is computed on real positions.
        QTimer.singleShot(0, self._timer.start)

    # ---- zoom -----------------------------------------------------------
    def set_zoom(self, zoom):
        zoom = max(MIN_ZOOM, min(MAX_ZOOM, zoom))
        if not self.doc or abs(zoom - self.zoom) < 1e-3:
            return
        page = self._current
        bar = self.verticalScrollBar()
        # Keep the same spot of the current page in view after resizing.
        lbl = self.labels[page]
        offset = (bar.value() - lbl.y()) / max(1, lbl.height())
        self.zoom = zoom
        for i, (lbl, p) in enumerate(zip(self.labels, self.doc)):
            size = (int(p.rect.width * zoom), int(p.rect.height * zoom))
            old = lbl.pixmap()
            if i in self.rendered:
                # Its picture is about to be a stretched copy: not sharp at any size, even if the zoom
                # comes back to where it was (otherwise it stays blurry until the next zoom).
                self.rendered[i] = -1
            if old and not old.isNull():
                # Show the old picture stretched until the sharp one arrives (no white flash). Changing its
                # pixel ratio stretches it as it's drawn, without making a big new copy first.
                quick = QPixmap(old)
                quick.setDevicePixelRatio(old.width() / max(1, size[0]))
                lbl.setPixmap(quick)
            self._stale_detail(i)
            lbl.setFixedSize(*size)
        self.zoom_changed.emit(zoom)

        def restore():
            l = self.labels[page]
            bar.setValue(int(l.y() + offset * l.height()))
            self._timer.start()
        self.container.layout().activate()
        QTimer.singleShot(0, restore)

    def fit_width(self):
        if self.doc:
            avail = self.viewport().width() - 2 * PAGE_GAP - 4
            self.set_zoom(avail / self.doc[self._current].rect.width)

    def fit_page(self):
        if self.doc:
            r = self.doc[self._current].rect
            vp = self.viewport()
            self.set_zoom(min((vp.width() - 2 * PAGE_GAP) / r.width,
                              (vp.height() - 2 * PAGE_GAP) / r.height))

    def wheelEvent(self, event):
        hook = self.page_mouse
        if event.modifiers() & Qt.ControlModifier:
            if hook is not None and hook.wheel(event):
                event.accept()  # Ctrl+scroll resizes what is being placed instead of zooming
                return
            step = 1.1 if event.angleDelta().y() > 0 else 1 / 1.1
            self.set_zoom(self.zoom * step)
            event.accept()
        else:
            super().wheelEvent(event)
            if hook is not None:
                hook.scrolled()

    # ---- navigation -----------------------------------------------------
    def go_to_page(self, index, y=0.0, animate=True):
        """Scroll to a page; y is a PDF-coordinate offset within the page."""
        if not 0 <= index < len(self.labels):
            return
        target = int(self.labels[index].y() + y * self.zoom - PAGE_GAP)
        target = max(0, min(target, self.verticalScrollBar().maximum()))
        self._anim.stop()
        if animate:
            self._anim.setStartValue(self.verticalScrollBar().value())
            self._anim.setEndValue(target)
            self._anim.start()
        else:
            self.verticalScrollBar().setValue(target)
        if index != self._current:  # update the page box right away, not at the end of the animation
            self._current = index
            self.current_page_changed.emit(index)

    def show_rect(self, index, rect):
        """Scroll so a PDF rect on a page is comfortably in view (used by search)."""
        lbl = self.labels[index]
        top = lbl.y() + rect.y0 * self.zoom
        bar = self.verticalScrollBar()
        if not (bar.value() + 40 <= top <= bar.value() + self.viewport().height() - 80):
            self.go_to_page(index, max(0, rect.y0 - self.viewport().height() / 3 / self.zoom))

    def current_page(self):
        return self._current

    def first_page_below(self, y):
        """Index of the first page whose bottom edge is at or below y (pages are in order, so a quick search)."""
        return bisect_left(self.labels, y, key=lambda l: l.y() + l.height())

    def _on_scroll(self):
        # Ask for drawings while the scrolling is still going (not only once it stops).
        if not self._timer.isActive():
            self._timer.start()
        if not self.labels or self._anim.state() == QPropertyAnimation.Running:
            return
        mid = self.verticalScrollBar().value() + self.viewport().height() // 3
        i = min(self.first_page_below(mid - PAGE_GAP), len(self.labels) - 1)
        if i != self._current:
            self._current = i
            self.current_page_changed.emit(i)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._timer.start()

    def _request_visible(self):
        if not self.renderer:
            return
        top = self.verticalScrollBar().value()
        height = self.viewport().height()

        def pages(y0, y1):
            i, out = self.first_page_below(y0), []
            while i < len(self.labels) and self.labels[i].y() <= y1:
                out.append(i)
                i += 1
            return out
        visible = pages(top, top + height)
        nearby = [i for i in pages(top - height, top + 2 * height) if i not in visible]  # about a screen each way
        keep = set(pages(top - 4 * height, top + 5 * height))  # drawn pages kept for scrolling back
        details = [job for job in map(self._detail_job, visible) if job]
        jobs = [(i, self._page_scale(i)) for i in visible + nearby if self.rendered.get(i) != self._page_scale(i)]
        self.renderer.set_view_jobs(details + jobs)
        # Free memory for pages far off screen.
        for i in list(self.rendered):
            if i not in keep:
                self.labels[i].clear()
                del self.rendered[i]
        for i in list(self.details):
            if i not in visible:
                del self.details[i]

    def _detail_job(self, index):
        """(index, scale, clip) to draw the part of a big page that's on screen sharp, or None if not needed."""
        scale = self._scale()
        if self._page_scale(index) >= scale - 1e-6:
            return None
        lbl, vp, z = self.labels[index], self.viewport(), self.zoom
        at = lbl.mapTo(vp, QPoint(0, 0))
        seen = QRectF(vp.rect()).translated(-at.x(), -at.y()).intersected(QRectF(lbl.rect()))
        if seen.isEmpty():
            return None
        seen = QRectF(seen.x() / z, seen.y() / z, seen.width() / z, seen.height() / z)
        have = self.details.get(index)
        if have and have[3] and abs(have[0] - scale) < 1e-6:
            x0, y0, x1, y1 = have[1]
            if QRectF(x0, y0, x1 - x0, y1 - y0).contains(seen):
                return None
        # A quarter of a screen extra all round, so scrolling a little doesn't need a new piece.
        pad_x, pad_y = vp.width() / 4 / z, vp.height() / 4 / z
        r = self.doc[index].rect
        clip = (max(0.0, seen.left() - pad_x), max(0.0, seen.top() - pad_y),
                min(r.width, seen.right() + pad_x), min(r.height, seen.bottom() + pad_y))
        return (index, scale, clip)

    # ---- links ----------------------------------------------------------
    def link_at(self, index, point):
        if index not in self._links:
            self._links[index] = [l for l in self.doc[index].get_links()
                                  if l["kind"] in (pymupdf.LINK_GOTO, pymupdf.LINK_URI, pymupdf.LINK_NAMED)]
        for link in self._links[index]:
            if link["from"].contains(point):
                return link
        return None

    def annot_at(self, index, point):
        """The comment under a point on a page, as (Rect, xref, hover text), or None."""
        if index not in self._annots:
            from .comments import KINDS, shown_rect  # (here, so the viewer doesn't need the comments module to start)
            found = []
            page = self.doc[index]
            for a in page.annots() if page.first_annot else []:
                if a.type[0] not in KINDS or a.irt_xref:
                    continue
                info = a.info
                text = info.get("content", "") or ""
                who = info.get("title", "") or ""
                tip = (f"<b>{html.escape(who)}</b><br>" if who else "") + html.escape(text[:600]).replace("\n", "<br>")
                found.append((shown_rect(a), a.xref, tip or KINDS[a.type[0]]))
            self._annots[index] = found
        for rect, xref, tip in reversed(self._annots[index]):  # the one drawn on top first
            if pymupdf.Rect(rect.x0 - 2, rect.y0 - 2, rect.x1 + 2, rect.y1 + 2).contains(point):
                return rect, xref, tip
        return None

    def open_web_link(self, uri):
        """A link in the PDF to somewhere outside it. Only web pages and email addresses are opened, and only
        after asking: a PDF can't start programs or open files on this computer by being clicked."""
        url = QUrl(uri.strip())
        if url.scheme().lower() not in ("http", "https", "mailto") or not url.isValid():
            QMessageBox.information(self.window(), APP_NAME, "This link isn't a web page or email address, so it "
                                    f"wasn't opened for safety:\n\n{uri[:300]}")
            return False
        if url.scheme().lower() == "mailto":
            question, button = f"Write an email to {url.path()[:200]}?", "Write email"
        else:
            question, button = f"Open this website?\n\n{url.toDisplayString()[:300]}", "Open website"
        if not ask(self.window(), question, button):
            return False
        QDesktopServices.openUrl(url)
        return True

    def follow_link(self, link):
        if link["kind"] == pymupdf.LINK_URI:
            self.open_web_link(link.get("uri", ""))
            return
        page = link.get("page", -1)
        if link["kind"] == pymupdf.LINK_NAMED and page < 0:
            dest = self.doc.resolve_names().get(link.get("nameddest") or link.get("name"), {})
            page = dest.get("page", -1)
        if page >= 0:
            to = link.get("to")
            self.go_to_page(page, max(0, to.y - 20) if to else 0)

    # ---- search highlights ----------------------------------------------
    def set_highlights(self, hits, current=None):
        """hits: list of (page index, Rect); current: index into hits."""
        for lbl in self.labels:
            if lbl.highlights:
                lbl.highlights = []
                lbl.update()
        for n, (i, r) in enumerate(hits):
            self.labels[i].highlights.append((r, n == current))
        for i in {i for i, _ in hits}:
            self.labels[i].update()
