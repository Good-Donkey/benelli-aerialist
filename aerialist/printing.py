"""Print: our own Print window (not the Windows print box) with a preview of each sheet beside the printer,
pages, copies, paper, size, two-sided and black-and-white settings. Pages are drawn fresh from the PDF at the
printer's quality (up to 300 dpi) with everything on them (added items, form entries, comments). Works the same with a real printer and with
Microsoft Print to PDF."""
import re

import pymupdf
from PySide6.QtCore import QRectF, QSettings, QSize, Qt
from PySide6.QtGui import QColor, QImage, QPageLayout, QPageSize, QPainter, QPen
from PySide6.QtPrintSupport import QPrinter, QPrinterInfo
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QProgressDialog, QPushButton, QRadioButton, QSizePolicy, QSpinBox, QToolButton, QVBoxLayout,
    QWidget,
)

from . import theme
from .icons import icon
from .popups import APP_NAME

MAX_DPI = 300  # sharp text on paper; more only makes the job slower and bigger
FITS = [("shrink", "Shrink large pages"), ("fit", "Fit to paper"), ("actual", "Actual size")]


# ---- laying a page on the paper ---------------------------------------------
def place(page_rect, area, fit="shrink"):
    """Where a page goes in the printable `area` (QRectF, in points). Returns (turn, target QRectF, scale):
    wide pages go on tall paper turned a quarter (and the other way), centred; "shrink" only makes pages
    smaller when they don't fit, "fit" makes them fill the area, "actual" keeps them at their size."""
    w, h = page_rect.width, page_rect.height
    turn = (w > h) != (area.width() > area.height()) and abs(w - h) > 1
    if turn:
        w, h = h, w
    best = min(area.width() / w, area.height() / h)
    scale = {"fit": best, "actual": 1.0}.get(fit, min(1.0, best))
    tw, th = w * scale, h * scale
    return turn, QRectF(area.x() + (area.width() - tw) / 2, area.y() + (area.height() - th) / 2, tw, th), scale


def page_image(page, zoom, turn, gray=False):
    """The page as a QImage at `zoom` (1 = 72 dpi), turned if asked."""
    matrix = pymupdf.Matrix(zoom, zoom).prerotate(90 if turn else 0)
    pix = page.get_pixmap(matrix=matrix, alpha=False, annots=True,
                          colorspace=pymupdf.csGRAY if gray else pymupdf.csRGB)
    fmt = QImage.Format_Grayscale8 if gray else QImage.Format_RGB888
    return QImage(pix.samples, pix.width, pix.height, pix.stride, fmt).copy()  # copy: pix goes away


def parse_pages(text, count):
    """"1-3, 5" -> [0, 1, 2, 4]. None if it doesn't make sense or names a page that isn't there."""
    pages = []
    for part in re.split(r"[,;\s]+", text.strip()):
        if not part:
            continue
        m = re.fullmatch(r"(\d+)(?:-(\d*))?", part)
        if not m:
            return None
        a = int(m.group(1))
        b = a if m.group(2) is None else (int(m.group(2)) if m.group(2) else count)
        if not (1 <= a <= count and 1 <= b <= count) or b < a:
            return None
        pages.extend(range(a - 1, b))
    return pages or None


def print_pages(parent, doc, printer, pages, fit="shrink", gray=False, copies=1):
    """Draw `pages` onto the printer. Copies the printer can't make itself are sent again, in order.
    Returns the number of sheets sent, 0 if cancelled or the printer refused."""
    if not pages:
        return 0
    if copies > 1 and printer.outputFormat() == QPrinter.NativeFormat and printer.supportsMultipleCopies():
        printer.setCopyCount(copies)
        printer.setCollateCopies(True)
        copies = 1
    jobs = pages * copies
    painter = QPainter()
    if not painter.begin(printer):  # no printer, or Print to PDF's Save box was cancelled
        return 0
    progress = None
    if parent is not None and len(jobs) > 1:
        progress = QProgressDialog("Getting the pages ready…", "Cancel", 0, len(jobs), parent)
        progress.setWindowTitle(APP_NAME)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(400)
    dpi = min(printer.resolution(), MAX_DPI)
    sent = 0
    try:
        for n, index in enumerate(jobs):
            if progress is not None:
                progress.setLabelText(f"Printing page {n + 1} of {len(jobs)}…")
                progress.setValue(n)
                QApplication.processEvents()
                if progress.wasCanceled():
                    printer.abort()
                    return 0
            if n:
                printer.newPage()
            _draw_page(painter, printer, doc[index], dpi, fit, gray)
            sent += 1
    finally:
        if painter.isActive():
            painter.end()
        if progress is not None:
            progress.close()
    return sent


def _draw_page(painter, printer, page, dpi, fit, gray):
    res = printer.resolution()
    area = printer.pageLayout().paintRect(QPageLayout.Point)  # the part of the paper it can print on
    area = QRectF(0, 0, area.width(), area.height())  # the painter's (0, 0) is already that part's corner
    turn, target, scale = place(page.rect, area, fit)
    k = res / 72
    target = QRectF(target.x() * k, target.y() * k, target.width() * k, target.height() * k)
    # Drawn at the size it will be on paper (up to MAX_DPI), so big drawings don't make huge pictures.
    image = page_image(page, dpi / 72 * scale, turn, gray)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
    painter.drawImage(target, image)


def print_to_pdf(doc, path, pages=None, fit="shrink", gray=False):
    """For the self-checks: print to a PDF file without any window."""
    printer = QPrinter(QPrinter.HighResolution)
    printer.setOutputFormat(QPrinter.PdfFormat)
    printer.setOutputFileName(path)
    return print_pages(None, doc, printer, list(range(len(doc))) if pages is None else pages, fit, gray)


# ---- the Print window ---------------------------------------------------------
class Preview(QWidget):
    """One sheet of paper as it will print: the printable part, and the page on it."""

    def __init__(self, dialog):
        super().__init__()
        self.dialog = dialog
        self.setMinimumSize(360, 420)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._cache = {}

    def clear(self):
        self._cache = {}
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.fillRect(self.rect(), QColor(theme.CANVAS))
        d = self.dialog
        layout = d.layout_for_preview()
        if layout is None or not d.pages:
            p.setPen(QColor(theme.MUTED))
            p.drawText(self.rect(), Qt.AlignCenter, "Nothing to print" if layout is not None else "No printer")
            return
        paper = layout.fullRect(QPageLayout.Point)
        area = layout.paintRect(QPageLayout.Point)
        room = self.rect().adjusted(24, 24, -24, -24)
        s = min(room.width() / paper.width(), room.height() / paper.height())
        sheet = QRectF(0, 0, paper.width() * s, paper.height() * s)
        sheet.moveCenter(QRectF(self.rect()).center())
        for i in range(3, 0, -1):  # a soft shadow
            p.fillRect(sheet.adjusted(-i, -i + 2, i, i + 2), QColor(0, 0, 0, 12))
        p.fillRect(sheet, QColor("white"))
        page = d.doc[d.pages[d.at]]
        turn, target, scale = place(page.rect, QRectF(0, 0, area.width(), area.height()), d.fit())
        box = QRectF(sheet.x() + (area.x() + target.x()) * s, sheet.y() + (area.y() + target.y()) * s,
                     target.width() * s, target.height() * s)
        key = (d.pages[d.at], turn, d.gray.isChecked(), round(box.width()), round(box.height()))
        img = self._cache.get(key)
        if img is None:
            zoom = min(4.0, box.width() * self.devicePixelRatioF() / (page.rect.height if turn else page.rect.width))
            img = page_image(page, zoom, turn, d.gray.isChecked())
            self._cache = {key: img}
        p.save()
        p.setClipRect(sheet)  # actual size can run off the paper
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        p.drawImage(box, img)
        p.restore()
        p.setPen(QPen(QColor(theme.PAGE_EDGE), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRect(sheet)


class PrintDialog(QDialog):
    def __init__(self, parent, doc, name, current=0, selected=None):
        super().__init__(parent)
        self.doc, self.name, self.current, self.selected = doc, name, current, selected or []
        self.settings = QSettings("Aerialist", "Aerialist")
        self.pages, self.at, self.sent = [], 0, 0
        self.setWindowTitle("Print")
        self._printer = None

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(0)
        self.preview = Preview(self)
        left.addWidget(self.preview, 1)
        nav_bar = QFrame()
        theme.style(nav_bar, "QFrame {{ background: {CANVAS}; }}")
        nav = QHBoxLayout(nav_bar)
        nav.setContentsMargins(8, 0, 8, 10)
        self.prev_btn, self.next_btn = QToolButton(), QToolButton()
        for b, tip, step in ((self.prev_btn, "Previous sheet (Page Up)", -1),
                             (self.next_btn, "Next sheet (Page Down)", 1)):
            b.setIcon(icon("chev_left" if step < 0 else "chev_right"))
            b.setIconSize(QSize(18, 18))
            b.setToolTip(tip)
            b.setAutoRaise(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, st=step: self._step(st))
        self.where = QLabel()
        nav.addStretch(1)
        nav.addWidget(self.prev_btn)
        nav.addWidget(self.where)
        nav.addWidget(self.next_btn)
        nav.addStretch(1)
        left.addWidget(nav_bar)
        outer.addLayout(left, 1)

        side = QWidget()
        side.setFixedWidth(320)
        form = QVBoxLayout(side)
        form.setContentsMargins(20, 18, 20, 18)
        form.setSpacing(6)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)

        self.printer_box = QComboBox()
        names = QPrinterInfo.availablePrinterNames()
        self.printer_box.addItems(names)
        last = self.settings.value("print/printer", "")
        pick = last if last in names else QPrinterInfo.defaultPrinterName()
        if pick in names:
            self.printer_box.setCurrentText(pick)
        grid.addWidget(QLabel("Printer"), 0, 0)
        grid.addWidget(self.printer_box, 0, 1)

        self.copies = QSpinBox()
        self.copies.setRange(1, 99)
        grid.addWidget(QLabel("Copies"), 1, 0)
        grid.addWidget(self.copies, 1, 1, Qt.AlignLeft)

        self.paper = QComboBox()
        grid.addWidget(QLabel("Paper"), 2, 0)
        grid.addWidget(self.paper, 2, 1)

        self.size_box = QComboBox()
        for key, label in FITS:
            self.size_box.addItem(label, key)
        self.size_box.setCurrentIndex(max(0, self.size_box.findData(self.settings.value("print/fit", "shrink"))))
        grid.addWidget(QLabel("Size"), 3, 0)
        grid.addWidget(self.size_box, 3, 1)

        self.sides = QComboBox()  # only shown for printers that can print on both sides
        for mode, label in ((QPrinter.DuplexNone, "One side"), (QPrinter.DuplexLongSide, "Both sides (flip on long edge)"),
                            (QPrinter.DuplexShortSide, "Both sides (flip on short edge)")):
            self.sides.addItem(label, int(mode.value))
        self.sides_label = QLabel("Sides")
        grid.addWidget(self.sides_label, 4, 0)
        grid.addWidget(self.sides, 4, 1)
        grid.setColumnStretch(1, 1)
        form.addLayout(grid)

        form.addSpacing(10)
        form.addWidget(QLabel("<b>Pages</b>"))
        self.which = QButtonGroup(self)
        n = len(doc)
        self.all_btn = QRadioButton(f"All ({n} page{'s' if n != 1 else ''})")
        self.cur_btn = QRadioButton(f"Current page ({current + 1})")
        self.sel_btn = QRadioButton(f"Selected pages ({len(self.selected)})")
        self.range_btn = QRadioButton("Pages")
        self.range_box = QLineEdit()
        self.range_box.setPlaceholderText("e.g. 1-3, 5")
        self.range_box.textEdited.connect(lambda: (self.range_btn.setChecked(True), self._update()))
        for b in (self.all_btn, self.cur_btn, self.sel_btn):
            self.which.addButton(b)
            form.addWidget(b)
        self.sel_btn.setVisible(bool(self.selected))
        row = QHBoxLayout()
        self.which.addButton(self.range_btn)
        row.addWidget(self.range_btn)
        row.addWidget(self.range_box, 1)
        form.addLayout(row)
        self.range_note = QLabel()
        theme.style(self.range_note, "color: {ERROR};")
        self.range_note.hide()
        form.addWidget(self.range_note)
        (self.sel_btn if self.selected else self.all_btn).setChecked(True)

        form.addSpacing(10)
        self.gray = QCheckBox("Black and white (saves colour ink)")
        self.gray.setChecked(self.settings.value("print/gray", False, type=bool))
        form.addWidget(self.gray)
        form.addStretch(1)

        self.sheets = QLabel()
        theme.style(self.sheets, "color: {SUBTLE};")
        form.addWidget(self.sheets)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        self.print_btn = QPushButton("Print")
        self.print_btn.setProperty("primary", True)
        self.print_btn.setDefault(True)
        self.print_btn.clicked.connect(self._print)
        buttons.addWidget(cancel)
        buttons.addWidget(self.print_btn)
        form.addLayout(buttons)
        outer.addWidget(side)

        self.printer_box.currentTextChanged.connect(self._printer_changed)
        self.paper.currentIndexChanged.connect(self._update)
        self.size_box.currentIndexChanged.connect(self._update)
        self.copies.valueChanged.connect(self._update)
        self.gray.toggled.connect(lambda: (self.preview.clear(), self._update()))
        self.which.buttonToggled.connect(lambda *_: self._update())
        self._printer_changed(self.printer_box.currentText())
        self.resize(940, 640)

    # -- the printer and its paper
    def _printer_changed(self, name):
        info = QPrinterInfo.printerInfo(name) if name else QPrinterInfo()
        self._printer = QPrinter(info, QPrinter.HighResolution) if not info.isNull() else None
        self.paper.blockSignals(True)
        self.paper.clear()
        if self._printer is not None:
            sizes = info.supportedPageSizes() or [info.defaultPageSize()]
            want = self.settings.value(f"print/paper/{name}", "")
            default = info.defaultPageSize().id()
            for ps in sizes:
                if ps.isValid():
                    self.paper.addItem(ps.name(), ps)
            pick = next((i for i in range(self.paper.count()) if self.paper.itemData(i).key() == want), None)
            if pick is None:
                pick = next((i for i in range(self.paper.count()) if self.paper.itemData(i).id() == default), 0)
            self.paper.setCurrentIndex(pick)
        self.paper.blockSignals(False)
        duplex = self._printer is not None and any(
            m in info.supportedDuplexModes() for m in (QPrinter.DuplexLongSide, QPrinter.DuplexShortSide))
        self._duplex = duplex
        self.sides.setVisible(duplex)
        self.sides_label.setVisible(duplex)
        if duplex:
            want = int(self.settings.value(f"print/sides/{name}", 0))
            self.sides.setCurrentIndex(max(0, self.sides.findData(want)))
        else:
            self.sides.setCurrentIndex(0)
        self.paper.setEnabled(self.paper.count() > 0)
        self.preview.clear()
        self._update()

    def _configured(self):
        """The chosen printer set up with the chosen paper, or None."""
        pr = self._printer
        if pr is None:
            return None
        ps = self.paper.currentData()
        if isinstance(ps, QPageSize) and ps.isValid():
            pr.setPageSize(ps)
        pr.setPageOrientation(QPageLayout.Portrait)  # wide pages are turned for us, sheet by sheet
        pr.setDuplex(QPrinter.DuplexMode(self.sides.currentData()) if self._duplex else QPrinter.DuplexNone)
        return pr

    def layout_for_preview(self):
        pr = self._configured()
        return pr.pageLayout() if pr is not None else None

    def fit(self):
        return self.size_box.currentData()

    # -- which pages
    def _chosen(self):
        n = len(self.doc)
        if self.cur_btn.isChecked():
            return [self.current]
        if self.sel_btn.isChecked() and self.selected:
            return sorted(self.selected)
        if self.range_btn.isChecked():
            return parse_pages(self.range_box.text(), n) or []
        return list(range(n))

    def _update(self):
        old = self.pages[self.at] if self.pages else None
        self.pages = self._chosen()
        self.at = self.pages.index(old) if old in self.pages else 0
        bad = self.range_btn.isChecked() and bool(self.range_box.text().strip()) and not self.pages
        self.range_note.setText(f"Use page numbers from 1 to {len(self.doc)}, like 1-3, 5")
        self.range_note.setVisible(bad)
        n = len(self.pages)
        self.where.setText(f"Sheet {self.at + 1} of {n}" if n else "")
        self.prev_btn.setEnabled(self.at > 0)
        self.next_btn.setEnabled(self.at < n - 1)
        sheets = n * self.copies.value()
        self.sheets.setText(f"{sheets} sheet{'s' if sheets != 1 else ''} of paper" if n else "")
        self.print_btn.setEnabled(bool(n) and self._printer is not None)
        self.preview.update()

    def _step(self, step):
        self.at = max(0, min(len(self.pages) - 1, self.at + step))
        self._update()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_PageDown, Qt.Key_PageUp) and not self.range_box.hasFocus():
            self._step(1 if e.key() == Qt.Key_PageDown else -1)
            return
        super().keyPressEvent(e)

    def wheelEvent(self, e):
        if self.preview.underMouse():
            self._step(-1 if e.angleDelta().y() > 0 else 1)
            return
        super().wheelEvent(e)

    # -- printing
    def _remember(self):
        name = self.printer_box.currentText()
        self.settings.setValue("print/printer", name)
        self.settings.setValue("print/fit", self.fit())
        self.settings.setValue("print/gray", self.gray.isChecked())
        ps = self.paper.currentData()
        if isinstance(ps, QPageSize):
            self.settings.setValue(f"print/paper/{name}", ps.key())
        if self._duplex:
            self.settings.setValue(f"print/sides/{name}", self.sides.currentData())

    def _print(self):
        pr = self._configured()
        if pr is None or not self.pages:
            return
        self._remember()
        pr.setDocName(self.name)
        self.hide()
        self.sent = print_pages(self.parent(), self.doc, pr, self.pages, self.fit(), self.gray.isChecked(),
                                self.copies.value())
        self.accept()


def ask_and_print(parent, doc, name, current=0, selected=None):
    """Show the Print window. Returns the number of sheets sent, 0 if nothing was printed."""
    d = PrintDialog(parent, doc, name, current, selected)
    d.exec()
    return d.sent
