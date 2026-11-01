"""Snip: drag a box on a page to copy that part as a sharp picture, drawn fresh from the PDF at print quality
however far you're zoomed out (a screen snip only gets the pixels on screen)."""
import os

import pymupdf
from PySide6.QtCore import Qt, QRect, QRectF, QPointF, QSettings, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPen
from PySide6.QtWidgets import QFileDialog

from . import theme
from .chrome import MiniBar, tool_button

DPI = 300  # the picture's sharpness: print quality
MAX_SIDE = 8000  # pixels: a whole poster-size page at 300 dpi would be too big to paste anywhere
HINT = "Drag a box around what you want. It's copied as a sharp picture, ready to paste. Esc to stop."


class Snipper:
    """The Snip tool in Read: takes the page mouse while it's on."""

    def __init__(self, win):
        self.win, self.view = win, win.view
        self.on = False
        self.page = None  # page index of the box
        self.start = self.end = None  # box corners, in PDF points
        self.image = None  # the last picture made
        self.bar = MiniBar(self.view)
        copy = tool_button("save_copy", "Copy again", tip="Copy the picture again")
        copy.clicked.connect(self.copy)
        save = tool_button("save_images", "Save as picture…", tip="Save the picture as a PNG or JPG file")
        save.clicked.connect(self.save)
        self.bar.lay.addWidget(copy)
        self.bar.lay.addWidget(save)

    # ---- on and off -------------------------------------------------------
    def set_on(self, on):
        if on == self.on:
            return
        self.on = on
        self.win.top.snip_btn.setChecked(on)
        if on:
            self.win.comments.pick(None)  # one page tool at a time
            self.win.selector.clear()
            self.view.page_mouse = self
            self.view.page_paint = self.paint
            for lbl in self.view.labels:
                lbl.setCursor(Qt.CrossCursor)
            self.win.toast.show_message(HINT, 5000)
        else:
            if self.view.page_mouse is self:
                self.view.page_mouse = None
            if self.view.page_paint == self.paint:
                self.view.page_paint = None
            for lbl in self.view.labels:
                lbl.unsetCursor()
            self.page = self.start = self.end = None
            self.bar.hide()
            self._repaint()

    # ---- mouse on a page --------------------------------------------------
    def _point(self, label, pos):
        z = self.view.zoom
        r = self.view.doc[label.index].rect
        return pymupdf.Point(min(max(pos.x() / z, 0), r.width), min(max(pos.y() / z, 0), r.height))

    def press(self, label, pos):
        self._repaint()
        self.page = label.index
        self.start = self.end = self._point(label, pos)
        self.bar.hide()

    def move(self, label, pos):
        label.setCursor(Qt.CrossCursor)
        if self.start is None or self.bar.isVisible() or label.index != self.page:
            return
        self.end = self._point(label, pos)
        self._repaint()

    def release(self, label, pos):
        if self.start is None or self.bar.isVisible():
            return
        if label.index == self.page:
            self.end = self._point(label, pos)
        box = self.rect()
        if box.width < 4 or box.height < 4:  # a click, not a box
            self.page = self.start = self.end = None
            self._repaint()
            return
        self.image = self.make(self.page, box)
        self.copy()
        self.bar.follow(self._screen_rect)
        self._repaint()

    def rect(self):
        return pymupdf.Rect(self.start, self.end).normalize()

    # ---- drawing ----------------------------------------------------------
    def paint(self, label, p):
        if self.start is None or label.index != self.page:
            return
        z = self.view.zoom
        r = self.rect()
        box = QRectF(r.x0 * z, r.y0 * z, r.width * z, r.height * z)
        tint = QColor(theme.ACCENT_FILL)
        tint.setAlpha(28)
        p.fillRect(box, tint)
        pen = QPen(QColor(theme.ACCENT_FILL), 2, Qt.DashLine)
        p.setPen(pen)
        p.drawRect(box)

    def _repaint(self):
        for lbl in self.view.labels:
            lbl.update()

    def _screen_rect(self):
        """The box in the view's coordinates, for the bar to sit beside."""
        if self.start is None or self.page is None or self.page >= len(self.view.labels):
            return None
        label = self.view.labels[self.page]
        z = self.view.zoom
        r = self.rect()
        top_left = label.mapTo(self.view.viewport(), QPointF(r.x0 * z, r.y0 * z).toPoint())
        return QRect(top_left.x(), top_left.y(), int(r.width * z), int(r.height * z))

    # ---- the picture --------------------------------------------------------
    def make(self, index, box):
        """The box drawn from the PDF itself: sharp at any zoom, with comments and filled-in fields."""
        dpi = DPI
        longest = max(box.width, box.height) / 72 * dpi
        if longest > MAX_SIDE:
            dpi = int(dpi * MAX_SIDE / longest)
        pix = self.win.doc[index].get_pixmap(clip=box, dpi=dpi, alpha=False, annots=True)
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888).copy()
        dpm = round(dpi / 0.0254)  # lets Word and others paste it at its real size on the page
        img.setDotsPerMeterX(dpm)
        img.setDotsPerMeterY(dpm)
        return img

    def copy(self):
        if self.image is None:
            return
        QGuiApplication.clipboard().setImage(self.image)
        self.win.toast.show_message(f"Copied ({self.image.width()} × {self.image.height()} pixels). Paste it into an "
                                    "email or document with Ctrl+V.", 4000)

    def save(self):
        if self.image is None:
            return
        settings = QSettings("Aerialist", "Aerialist")
        name = os.path.splitext(os.path.basename(self.win.path or "Snip"))[0]
        folder = str(settings.value("snip/dir", "") or settings.value("last_dir", "") or os.path.expanduser("~"))
        path, chosen = QFileDialog.getSaveFileName(self.win, "Save as picture",
                                                   os.path.join(folder, f"{name} snip.png"),
                                                   "PNG picture (*.png);;JPG picture (*.jpg)")
        if not path:
            return
        if not os.path.splitext(path)[1]:
            path += ".jpg" if "JPG" in chosen else ".png"
        jpg = path.lower().endswith((".jpg", ".jpeg"))
        quality = int(settings.value("convert/jpg_quality", 95)) if jpg else -1
        if self.image.save(path, "JPG" if jpg else "PNG", quality):
            settings.setValue("snip/dir", os.path.dirname(path))
            self.win.toast.show_message(f"Saved {os.path.basename(path)}")
        else:
            self.win.toast.show_message(f"Couldn't save {os.path.basename(path)}")
        QTimer.singleShot(0, self.bar.raise_)
