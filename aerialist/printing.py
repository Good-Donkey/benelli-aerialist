"""Print: the Windows print dialog (printer, pages, copies), then each page drawn fresh from the PDF at the
printer's quality, with everything on it (added items, form entries, comments).
Works the same with a real printer and with Microsoft Print to PDF."""
import pymupdf
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPageLayout, QPainter
from PySide6.QtPrintSupport import QAbstractPrintDialog, QPrintDialog, QPrinter
from PySide6.QtWidgets import QApplication, QProgressDialog

from .popups import APP_NAME

MAX_DPI = 300  # sharp text on paper; more only makes the job slower and bigger


def ask_and_print(parent, doc, name, current=0, selected=None):
    """Show the print dialog and print what is chosen. `selected` (page indexes) offers "Selection".
    Returns the number of pages sent, or 0 if nothing was printed."""
    printer = QPrinter(QPrinter.HighResolution)
    printer.setDocName(name)
    printer.setFromTo(1, len(doc))
    dialog = QPrintDialog(printer, parent)
    dialog.setWindowTitle("Print")
    dialog.setMinMax(1, len(doc))
    options = QAbstractPrintDialog.PrintPageRange | QAbstractPrintDialog.PrintCurrentPage | \
        QAbstractPrintDialog.PrintCollateCopies | QAbstractPrintDialog.PrintShowPageSize
    if selected:
        options |= QAbstractPrintDialog.PrintSelection
    dialog.setOptions(options)
    if dialog.exec() != QPrintDialog.Accepted:
        return 0
    pages = chosen_pages(printer, len(doc), current, selected)
    return print_pages(parent, doc, printer, pages)


def chosen_pages(printer, count, current=0, selected=None):
    r = printer.printRange()
    if r == QPrinter.CurrentPage:
        return [current]
    if r == QPrinter.Selection and selected:
        return sorted(selected)
    if r == QPrinter.PageRange and printer.fromPage() > 0:
        first, last = max(1, printer.fromPage()), min(count, printer.toPage() or count)
        return list(range(first - 1, last))
    return list(range(count))


def print_pages(parent, doc, printer, pages):
    """Draw `pages` onto the printer: each page fitted to the paper (turned if that fits better), centred,
    never enlarged. Returns the number of pages sent, 0 if cancelled or the printer refused."""
    if not pages:
        return 0
    painter = QPainter()
    if not painter.begin(printer):  # no printer, or Print to PDF's Save box was cancelled
        return 0
    progress = None
    if parent is not None and len(pages) > 1:
        progress = QProgressDialog("Getting the pages ready…", "Cancel", 0, len(pages), parent)
        progress.setWindowTitle(APP_NAME)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(400)
    dpi = min(printer.resolution(), MAX_DPI)
    sent = 0
    try:
        for n, index in enumerate(pages):
            if progress is not None:
                progress.setLabelText(f"Printing page {n + 1} of {len(pages)}…")
                progress.setValue(n)
                QApplication.processEvents()
                if progress.wasCanceled():
                    printer.abort()
                    return 0
            if n:
                printer.newPage()
            _draw_page(painter, printer, doc[index], dpi)
            sent += 1
    finally:
        if painter.isActive():
            painter.end()
        if progress is not None:
            progress.close()
    return sent


def _draw_page(painter, printer, page, dpi):
    area = printer.pageLayout().paintRectPixels(printer.resolution())  # the part of the paper it can print on
    area = QRectF(0, 0, area.width(), area.height())  # the painter's (0, 0) is already the area's corner
    w_pt, h_pt = page.rect.width, page.rect.height  # as shown, after any rotation
    # Turn the page a quarter if it's wide and the paper is tall (or the other way), like other PDF programs.
    turn = (w_pt > h_pt) != (area.width() > area.height()) and abs(w_pt - h_pt) > 1
    if turn:
        w_pt, h_pt = h_pt, w_pt
    px_per_pt = printer.resolution() / 72
    scale = min(1.0, area.width() / (w_pt * px_per_pt), area.height() / (h_pt * px_per_pt))
    w, h = w_pt * px_per_pt * scale, h_pt * px_per_pt * scale
    target = QRectF(area.x() + (area.width() - w) / 2, area.y() + (area.height() - h) / 2, w, h)
    # Drawn at the size it will be on paper (up to MAX_DPI), so big drawings don't make huge pictures.
    zoom = dpi / 72 * scale
    matrix = pymupdf.Matrix(zoom, zoom).prerotate(90 if turn else 0)
    pix = page.get_pixmap(matrix=matrix, alpha=False, annots=True)
    image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
    painter.drawImage(target, image)
    del pix


def print_to_pdf(doc, path, pages=None):
    """For the self-checks: print to a PDF file without any dialog."""
    printer = QPrinter(QPrinter.HighResolution)
    printer.setOutputFormat(QPrinter.PdfFormat)
    printer.setOutputFileName(path)
    printer.setPageOrientation(QPageLayout.Portrait)
    return print_pages(None, doc, printer, list(range(len(doc))) if pages is None else pages)
