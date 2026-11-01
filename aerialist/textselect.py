"""Choosing text and pictures in Read: drag over words or double-click one, or click a picture. The choice
shows in green (handy for pointing something out while presenting) and Ctrl+C or the Copy button copies it.
Nothing is changed in the PDF."""
import pymupdf
from PySide6.QtCore import QRect, QRectF, QPointF
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPen

from . import theme
from .chrome import MiniBar, tool_button
from .comments import line_rects

DRAG = 4  # pixels the mouse must move before a press becomes a drag
MAX_SIDE = 8000  # biggest copied picture, in pixels


class Selector:
    """The words or picture chosen on one page. The page view sends it the mouse when no tool has it."""

    def __init__(self, win):
        self.win, self.view = win, win.view
        self._doc, self._words, self._images = None, {}, {}  # per page, for the document now showing
        self.page = None
        self.chosen = []  # [(Rect, (block, line), word)] in reading order
        self.picture = None  # Rect of the chosen picture
        self._start = self._press = None  # word index the drag began at; mouse position of the press
        self.bar = MiniBar(self.view)
        copy = tool_button("save_copy", "Copy", tip="Copy (Ctrl+C)")
        copy.clicked.connect(self.copy)
        self.bar.lay.addWidget(copy)

    # ---- what's on the page ---------------------------------------------------
    def _fresh(self):
        if self.view.doc is not self._doc:  # another file, or the same one after an edit
            self._doc, self._words, self._images = self.view.doc, {}, {}
            self.page, self.chosen, self.picture = None, [], None
            self.bar.hide()

    def words(self, index):
        """The page's words in reading order, as shown on screen: [(Rect, (block, line), word)]."""
        self._fresh()
        if index not in self._words:
            try:
                page = self.view.doc[index]
                m = page.rotation_matrix
                self._words[index] = [(pymupdf.Rect(w[:4]) * m, (w[5], w[6]), w[4])
                                      for w in page.get_text("words", sort=False)]
            except Exception:
                self._words[index] = []
        return self._words[index]

    def images(self, index):
        """[(Rect on screen, pixels across)] for the pictures on a page, smallest first."""
        self._fresh()
        if index not in self._images:
            try:
                page = self.view.doc[index]
                m = page.rotation_matrix
                found = []
                for info in page.get_image_info():
                    r = pymupdf.Rect(info["bbox"]) * m
                    if r.is_valid and not r.is_empty and r.width > 2 and r.height > 2:
                        found.append((r & page.rect, max(info.get("width", 0), info.get("height", 0))))
                self._images[index] = sorted(found, key=lambda f: f[0].width * f[0].height)
            except Exception:
                self._images[index] = []
        return self._images[index]

    def word_at(self, index, point):
        for i, (r, _, _) in enumerate(self.words(index)):
            if point in r:
                return i
        return None

    def _nearest(self, index, point):
        words = self.words(index)
        hit = self.word_at(index, point)
        if hit is not None or not words:
            return hit
        return min(range(len(words)), key=lambda i: abs(words[i][0].y0 + words[i][0].y1 - 2 * point.y) * 3
                   + abs(words[i][0].x0 + words[i][0].x1 - 2 * point.x))

    def _reading(self):
        return self.win.mode == "read" and self.view.doc is not None

    def over_text(self, index, point):
        return self._reading() and self.word_at(index, point) is not None

    # ---- mouse --------------------------------------------------------------
    def _point(self, pos):
        z = self.view.zoom
        return pymupdf.Point(pos.x() / z, pos.y() / z)

    def press(self, label, pos):
        if not self._reading():
            return
        self._press = (label.index, QPointF(pos))
        self._start = None

    def dragging(self):
        return self._press is not None

    def move(self, label, pos):
        index, at = self._press
        if self._start is None:
            if (pos - at).manhattanLength() < DRAG:
                return
            start = self._nearest(index, self._point(at))
            if start is None:  # no text on this page (a scan): nothing to drag over
                return
            self._show(index, [], None)
            self._start = start
        end = self._nearest(index, self._point(pos))
        a, b = sorted((self._start, end))
        self._show(index, self.words(index)[a:b + 1], None)

    def release(self, label, pos):
        """True if the press made or changed a choice (so it isn't also a click on a link)."""
        dragged = self._start is not None
        self._press = self._start = None
        if dragged and self.chosen:
            self._offer()
        return dragged

    def click(self, label, pos):
        """A plain click (not on a link or comment): picks the picture under it, or clears the choice."""
        point = self._point(pos)
        if self._reading() and self.word_at(label.index, point) is None:
            for r, _ in self.images(label.index):
                if point in r:
                    if self.picture == r and self.page == label.index:  # a second click lets go of it
                        break
                    self._show(label.index, [], r)
                    self._offer()
                    return
        self.clear()

    def double_click(self, label, pos):
        i = self.word_at(label.index, self._point(pos)) if self._reading() else None
        if i is not None:
            self._show(label.index, [self.words(label.index)[i]], None)
            self._offer()

    # ---- showing -------------------------------------------------------------
    def _show(self, index, words, picture):
        self._repaint()
        self.page, self.chosen, self.picture = index, words, picture
        self._repaint()

    def _offer(self):
        self.bar.follow(self._screen_rect)

    def active(self):
        self._fresh()
        return bool(self.chosen or self.picture)

    def _forget(self):
        self.page, self.chosen, self.picture = None, [], None
        self._press = self._start = None
        self.bar.hide()

    def clear(self):
        if self.chosen or self.picture or self.bar.isVisible():
            self._repaint()
            self._forget()

    def _repaint(self):
        if self.page is not None and self.page < len(self.view.labels):
            self.view.labels[self.page].update()

    def _rects(self):
        return [self.picture] if self.picture is not None else line_rects([(r, key) for r, key, _ in self.chosen])

    def paint(self, label, p):
        if label.index != self.page or self.view.doc is not self._doc:
            return
        z = self.view.zoom
        fill = QColor(theme.ACCENT_FILL)
        fill.setAlpha(75)
        for r in self._rects():
            p.fillRect(QRectF(r.x0 * z, r.y0 * z, r.width * z, r.height * z), fill)
        if self.picture is not None:
            p.setPen(QPen(QColor(theme.ACCENT_FILL), 2))
            r = self.picture
            p.drawRect(QRectF(r.x0 * z, r.y0 * z, r.width * z, r.height * z))

    def _screen_rect(self):
        rects = self._rects() if self.page is not None and self.page < len(self.view.labels) else []
        if not rects:
            return None
        box = pymupdf.Rect(rects[0])
        for r in rects[1:]:
            box |= r
        label, z = self.view.labels[self.page], self.view.zoom
        top_left = label.mapTo(self.view.viewport(), QPointF(box.x0 * z, box.y0 * z).toPoint())
        return QRect(top_left.x(), top_left.y(), int(box.width * z), int(box.height * z))

    # ---- copying -------------------------------------------------------------
    def text(self):
        lines, key = [], None
        for _, k, word in self.chosen:
            if k != key:
                lines.append([])
                key = k
            lines[-1].append(word)
        return "\n".join(" ".join(line) for line in lines)

    def picture_image(self):
        """The chosen picture as it shows on the page, at its own sharpness (not the screen's)."""
        r = self.picture
        across = next((n for box, n in self.images(self.page) if box == r), 0)
        dpi = max(96, min(600, across / max(r.width, r.height) * 72)) if across else 300
        dpi = min(dpi, MAX_SIDE / max(r.width, r.height) * 72)
        pix = self.view.doc[self.page].get_pixmap(clip=r, dpi=int(dpi), alpha=False, annots=False)
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888).copy()
        dpm = round(int(dpi) / 0.0254)
        img.setDotsPerMeterX(dpm)
        img.setDotsPerMeterY(dpm)
        return img

    def copy(self):
        """Copy the chosen words or picture. False if nothing is chosen."""
        if not self.active():
            return False
        if self.picture is not None:
            img = self.picture_image()
            QGuiApplication.clipboard().setImage(img)
            self.win.toast.show_message(f"Picture copied ({img.width()} × {img.height()} pixels).")
        else:
            QGuiApplication.clipboard().setText(self.text())
            n = len(self.chosen)
            self.win.toast.show_message(f"Copied {n} word{'s' if n != 1 else ''}.")
        return True
