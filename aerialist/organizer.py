"""Page thumbnails: the sidebar beside the pages, and the full-window grid of the Pages mode."""
from PySide6.QtCore import Qt, Signal, QTimer, QSize, QPoint, QRect, QRectF, QEvent
from PySide6.QtGui import QColor, QPainter, QPen, QCursor, QFont
from PySide6.QtWidgets import (
    QApplication, QListWidget, QListWidgetItem, QAbstractItemView, QLabel, QWidget, QPushButton,
    QStyledItemDelegate, QStyle, QVBoxLayout, QSlider, QDialog, QScrollArea, QRubberBand,
)

from . import theme
from .chrome import Floating
from .convert import CONVERTIBLE  # Word, Excel, PowerPoint and text files are made into PDFs

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp")
TILE_ROLE = Qt.UserRole + 1
NUMBER_H = 24  # room under each thumbnail for its page number
PAD = 10


def pdf_paths(mime, images=False):
    """Local PDF files (and, if asked, image files and documents to make into PDFs) in a drag-and-drop payload."""
    exts = (".pdf",) + ((IMAGE_EXTS + CONVERTIBLE) if images else ())
    return [u.toLocalFile() for u in mime.urls() if u.toLocalFile().lower().endswith(exts)]


class ThumbDelegate(QStyledItemDelegate):
    """One look for every page thumbnail: thin grey edge; grey ring on hover; emerald ring and number
    for the current page; ring, pale tint and a tick for selected pages in the Pages mode."""

    def __init__(self, grid):
        super().__init__(grid)
        self.grid = grid

    def _pad(self):
        return PAD if self.grid.editing else 4  # the sidebar packs pages closer

    def _num(self):
        return NUMBER_H if self.grid.editing else 0  # the sidebar puts the number on the page itself

    def sizeHint(self, option, index):
        PAD, NUMBER_H = self._pad(), self._num()
        if index.data(TILE_ROLE):
            w = self.grid.iconSize().width()
            return QSize(w + 2 * PAD, int(w * 1.3) + 2 * PAD + NUMBER_H)
        pix = index.data(Qt.DecorationRole)
        size = pix.size() / pix.devicePixelRatio() if pix is not None and not pix.isNull() else self.grid.iconSize()
        return QSize(max(size.width(), self.grid.iconSize().width()) + 2 * PAD, size.height() + 2 * PAD + NUMBER_H)

    def paint(self, p, option, index):
        PAD = self._pad()
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        r = option.rect
        if index.data(TILE_ROLE):
            self._paint_tile(p, r, bool(option.state & QStyle.State_MouseOver))
            p.restore()
            return
        pix = index.data(Qt.DecorationRole)
        size = pix.size() / pix.devicePixelRatio() if pix is not None and not pix.isNull() else self.grid.iconSize()
        x = r.x() + (r.width() - size.width()) // 2
        page = QRect(x, r.y() + PAD, size.width(), size.height())
        editing = self.grid.editing
        selected = bool(option.state & QStyle.State_Selected)
        current = index.row() == self.grid.currentRow()
        hover = bool(option.state & QStyle.State_MouseOver)
        on = selected if editing else current
        if on and editing:  # pale halo behind the ring
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.TINT))
            p.drawRoundedRect(QRectF(page).adjusted(-8, -8, 8, 8), 6, 6)
        p.fillRect(page, Qt.white)
        if pix is not None and not pix.isNull():
            p.drawPixmap(page, pix)
        if on:
            p.setPen(QPen(QColor(theme.ACCENT), 3))
        elif hover:
            p.setPen(QPen(QColor(theme.SCROLL_HOVER), 2))
        else:
            p.setPen(QPen(QColor(theme.LINE), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRectF(page).adjusted(-0.5, -0.5, 0.5, 0.5) if not on and not hover else QRectF(page).adjusted(-1, -1, 1, 1))
        if on and editing:  # tick badge, top right
            c = QRectF(page.right() - 10, page.top() - 10, 20, 20)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.ACCENT_FILL))
            p.drawEllipse(c)
            p.setPen(QPen(Qt.white, 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.drawPolyline([c.center() + d for d in (QPoint(-5, 0), QPoint(-1, 4), QPoint(5, -4))])
        # Page number (or the file and page while merging), under the page.
        label = index.data(Qt.DisplayRole) or str(index.row() + 1)
        f = QFont(option.font)
        f.setPointSizeF(f.pointSizeF() * 0.9)
        f.setBold(on and not editing)
        p.setFont(f)
        fm = p.fontMetrics()
        text = fm.elidedText(label, Qt.ElideMiddle, r.width() - 8)
        tw = fm.horizontalAdvance(text) + (14 if editing else 10)
        if not editing:  # sidebar: a small circle in the page's bottom-right corner
            d = max(18, tw - 6)
            num = QRect(page.right() - d - 3, page.bottom() - 18 - 3, d, 18)
            p.setPen(QPen(QColor(theme.DASH), 1) if not on else Qt.NoPen)
            p.setBrush(QColor(theme.ACCENT_FILL) if on else QColor(255, 255, 255, 235))
            p.drawRoundedRect(QRectF(num), 9, 9)
            p.setPen(Qt.white if on else QColor("#3A3A3F"))
            p.drawText(num, Qt.AlignCenter, text)
            p.restore()
            return
        num = QRect(r.x() + (r.width() - tw) // 2, page.bottom() + 6, tw, 18)
        if on and not editing:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.ACCENT_FILL))
            p.drawRoundedRect(num, 9, 9)
            p.setPen(Qt.white)
        else:
            p.setPen(QColor(theme.MUTED))
        p.drawText(num, Qt.AlignCenter, text)
        # Keyboard focus box, only when the page isn't already marked as selected.
        if (option.state & QStyle.State_HasFocus and not option.state & QStyle.State_Selected and editing
                and self.grid.hasFocus()):
            p.setPen(QPen(QColor(theme.TEXT), 1, Qt.DotLine))
            p.setBrush(Qt.NoBrush)
            p.drawRect(QRectF(page).adjusted(-5, -5, 5, 5))
        p.restore()

    def _paint_tile(self, p, r, hover):
        w = self.grid.iconSize().width()
        box = QRect(r.x() + (r.width() - w) // 2, r.y() + PAD, w, int(w * 1.3))
        p.setPen(QPen(QColor(theme.ACCENT if hover else theme.SCROLL_HOVER), 2, Qt.DashLine))
        p.setBrush(QColor(theme.TINT) if hover else Qt.NoBrush)
        p.drawRoundedRect(QRectF(box), 4, 4)
        from .icons import pixmap
        icon = pixmap("plus", 24, "ACCENT" if hover else "MUTED")
        p.drawPixmap(box.center().x() - 12, box.center().y() - 30, icon)
        p.setPen(QColor(theme.MUTED))
        p.drawText(box.adjusted(8, 10, -8, 0), Qt.AlignCenter | Qt.TextWordWrap, "Add PDFs\nor images")
        p.drawText(QRect(r.x(), box.bottom() + 6, r.width(), 18), Qt.AlignCenter, "or drop them anywhere")


class PageGrid(QListWidget):
    """Page thumbnails. A column (two when wide) beside the pages while reading; a reorderable
    grid with an "add files" tile in the Pages mode.

    Reordering uses its own mouse handling rather than Qt/Windows drag-and-drop, which
    proved unreliable for moving items inside a wrapping grid.
    """
    reordered = Signal(list)  # new order, as a list of old page indices
    files_dropped = Signal(list, int)  # PDF paths, page index to insert at
    browse = Signal()  # the "add files" tile was clicked

    def __init__(self):
        super().__init__()
        self.editing = False
        self.accept_files = False
        self.tile = None
        self._drop_row = None
        self._press = None  # (position, item) of a left-button press
        self._dragging = False
        self._scroll_dir = 0
        self._scroll_timer = QTimer(self, interval=30)
        self._scroll_timer.timeout.connect(self._auto_scroll)
        self.setItemDelegate(ThumbDelegate(self))
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QListWidget.NoFrame)
        self.setMouseTracking(True)
        self.viewport().setAttribute(Qt.WA_Hover)
        self.setViewMode(QListWidget.IconMode)
        self.setFlow(QListWidget.LeftToRight)
        self.setWrapping(True)
        self.setResizeMode(QListWidget.Adjust)
        self.setMovement(QListWidget.Static)
        self.setUniformItemSizes(False)
        # Qt's own selection box could be left behind on screen after moving pages; draw our own instead.
        self.setSelectionRectVisible(False)
        self._band = QRubberBand(QRubberBand.Rectangle, self.viewport())
        self._band_from = None
        self.set_editing(False)

    def set_editing(self, editing, accept_files=False):
        self.editing, self.accept_files = editing, accept_files
        self.setObjectName("pagesGrid" if editing else "sidebar")
        theme.style(self, "QListWidget {{ background: {%s}; border: none; }}" % ("CANVAS" if editing else "SOFT"))
        self.setSpacing(14 if editing else 0)
        self.setDragEnabled(False)
        self.setDragDropMode(QAbstractItemView.DropOnly if accept_files else QAbstractItemView.NoDragDrop)
        self.setAcceptDrops(accept_files)
        self.viewport().setAcceptDrops(accept_files)
        self.verticalScrollBar().setSingleStep(40)
        self.set_tile(editing)

    def pages(self):
        return self.count() - (1 if self.tile is not None else 0)

    def set_tile(self, show):
        """The "Add PDFs or pictures" tile at the end of the Pages grid."""
        if self.tile is not None:
            self.takeItem(self.row(self.tile))
            self.tile = None
        if show:
            self.tile = QListWidgetItem()
            self.tile.setData(TILE_ROLE, True)
            self.tile.setFlags(Qt.ItemIsEnabled)
            self.tile.setToolTip("Add PDFs or images (or drop them anywhere)")
            self.addItem(self.tile)

    def clear(self):
        self.tile = None
        super().clear()

    # ---- clicking and dragging pages ------------------------------------
    def mousePressEvent(self, e):
        pos = e.position().toPoint()
        item = self.itemAt(pos)
        if item is not None and item is self.tile:
            if e.button() == Qt.LeftButton:
                self.browse.emit()
            e.accept()
            return
        if e.button() == Qt.RightButton and item and item.isSelected():
            e.accept()  # right-clicking a selected page keeps the whole selection
            return
        if e.button() == Qt.LeftButton:
            self._press = (pos, item)
            self._band_from = pos + QPoint(self.horizontalOffset(), self.verticalOffset()) if item is None else None
            if item and item.isSelected() and not (e.modifiers() & (Qt.ControlModifier | Qt.ShiftModifier)):
                # Might be the start of dragging several selected pages: decide on release.
                e.accept()
                return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        pos = e.position().toPoint()
        if self.editing and self._press and self._press[1] is not None and (e.buttons() & Qt.LeftButton):
            if not self._dragging and (pos - self._press[0]).manhattanLength() >= QApplication.startDragDistance():
                if not self._press[1].isSelected():
                    self.setCurrentItem(self._press[1])
                self._dragging = True
                self.viewport().setCursor(Qt.ClosedHandCursor)
            if self._dragging:
                self._drop_row = self._row_at(pos)
                margin = 40
                h = self.viewport().height()
                self._scroll_dir = -1 if pos.y() < margin else (1 if pos.y() > h - margin else 0)
                if self._scroll_dir and not self._scroll_timer.isActive():
                    self._scroll_timer.start()
                self.viewport().update()
                return
        if self._dragging:
            return
        if self._band_from is not None and e.buttons() & Qt.LeftButton:
            start = self._band_from - QPoint(self.horizontalOffset(), self.verticalOffset())
            self._band.setGeometry(QRect(start, pos).normalized())
            self._band.show()
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        press, self._press = self._press, None
        self._band_from = None
        self._band.hide()
        if self._dragging:
            self._dragging = False
            self._scroll_timer.stop()
            self.viewport().unsetCursor()
            row = self._drop_row if self._drop_row is not None else self._row_at(e.position().toPoint())
            self._drop_row = None
            self.viewport().update()
            moving = sorted(i.row() for i in self.selectedIndexes())
            rest = [i for i in range(self.pages()) if i not in moving]
            k = sum(1 for i in rest if i < row)
            order = rest[:k] + moving + rest[k:]
            if order != list(range(self.pages())):
                QTimer.singleShot(0, lambda: self.reordered.emit(order))
            return
        if press and press[1] is not None and e.button() == Qt.LeftButton and press[1].isSelected() \
                and not (e.modifiers() & (Qt.ControlModifier | Qt.ShiftModifier)):
            self.setCurrentItem(press[1])  # plain click on a selected page: select just that page
            return
        super().mouseReleaseEvent(e)

    def _auto_scroll(self):
        if not self._dragging or not self._scroll_dir:
            self._scroll_timer.stop()
            return
        bar = self.verticalScrollBar()
        bar.setValue(bar.value() + self._scroll_dir * 20)
        pos = self.viewport().mapFromGlobal(QCursor.pos())
        self._drop_row = self._row_at(pos)
        self.viewport().update()

    def _row_at(self, pos):
        n = self.pages()
        item = self.itemAt(pos)
        if item is None or item is self.tile:  # in a gap or past the end: before the next thumbnail
            for i in range(n):
                r = self.visualItemRect(self.item(i))
                if r.top() > pos.y() or (r.top() <= pos.y() <= r.bottom() and r.left() > pos.x()):
                    return i
            return n
        r = self.visualItemRect(item)
        wide = r.width() * 1.6 < self.viewport().width()  # several per row: before/after goes by x
        after = pos.x() > r.center().x() if wide else pos.y() > r.center().y()
        return min(n, self.row(item) + after)

    # ---- PDF files dropped in from Explorer (Pages mode) -----------------
    def dragEnterEvent(self, e):
        if self.accept_files and pdf_paths(e.mimeData(), images=True):
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragMoveEvent(self, e):
        if not (self.accept_files and pdf_paths(e.mimeData(), images=True)):
            e.ignore()
            return
        self._drop_row = self._row_at(self._cursor_pos())
        self.viewport().update()
        e.acceptProposedAction()

    def dragLeaveEvent(self, e):
        self._drop_row = None
        self.viewport().update()

    def _cursor_pos(self):
        # Drops from Explorer can report positions in the wrong scale on high-DPI Windows
        # displays; the real cursor position is always right.
        return self.viewport().mapFromGlobal(QCursor.pos())

    def dropEvent(self, e):
        row = self._row_at(self._cursor_pos())
        self._drop_row = None
        self.viewport().update()
        paths = pdf_paths(e.mimeData(), images=True) if self.accept_files else []
        if not paths:
            e.ignore()
            return
        e.setDropAction(Qt.CopyAction)
        e.accept()
        QTimer.singleShot(0, lambda: self.files_dropped.emit(paths, row))

    def paintEvent(self, e):
        super().paintEvent(e)
        n = self.pages()
        if self._drop_row is None or not self.count():
            return
        p = QPainter(self.viewport())
        p.setPen(QPen(QColor(theme.ACCENT), 4, Qt.SolidLine, Qt.RoundCap))
        if self._drop_row < self.count():
            r = self.visualItemRect(self.item(self._drop_row))
            a, b = r.topLeft() + QPoint(-5, PAD - 4), r.bottomLeft() - QPoint(5, NUMBER_H)
        else:
            r = self.visualItemRect(self.item(n - 1))
            a, b = r.topRight() + QPoint(5, PAD - 4), r.bottomRight() + QPoint(5, -NUMBER_H)
        p.drawLine(a, b)
        p.end()


def _button(text, primary=False, big=False):
    b = QPushButton(text)
    b.setCursor(Qt.PointingHandCursor)
    if primary:
        b.setProperty("primary", True)
    return b


class PagesScreen(QWidget):
    """The Pages mode: every page in a full-window grid, with a size slider floating at the bottom right.
    The main window moves its page grid in here while the mode is open."""
    size_changed = Signal(int)
    SIZES = [90, 120, 150, 190, 240]

    def __init__(self):
        super().__init__()
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.grid = None
        self.pill = None

    def attach(self, grid, size_index):
        self.grid = grid
        self.lay.addWidget(grid)
        grid.show()
        if self.pill is None:
            self.pill = Floating(grid, "sizePill", lambda w: QPoint(grid.width() - w.width() - 22,
                                                                     grid.height() - w.height() - 16))
            self.pill.lay.setContentsMargins(14, 6, 14, 6)
            self.pill.lay.setSpacing(10)
            lbl = QLabel("Size")
            lbl.setObjectName("muted")
            self.slider = QSlider(Qt.Horizontal)
            self.slider.setRange(0, len(self.SIZES) - 1)
            self.slider.setFixedWidth(110)
            self.slider.setFocusPolicy(Qt.NoFocus)
            self.slider.valueChanged.connect(lambda v: self.size_changed.emit(self.SIZES[v]))
            self.pill.lay.addWidget(lbl)
            self.pill.lay.addWidget(self.slider)
        self.slider.blockSignals(True)
        self.slider.setValue(size_index)
        self.slider.blockSignals(False)
        self.pill.show()
        self.pill.reposition()

    def detach(self):
        if self.pill:
            self.pill.hide()
        if self.grid:
            self.lay.removeWidget(self.grid)
        self.grid = None


class PreviewDialog(QDialog):
    """A big look at one page (double-click in the Pages grid)."""

    def __init__(self, parent, doc, index):
        super().__init__(parent)
        self.setWindowTitle(f"Page {index + 1}")
        page = doc[index]
        screen = parent.screen().availableGeometry()
        h = screen.height() * 0.8
        zoom = min(h / page.rect.height, screen.width() * 0.8 / page.rect.width)
        dpr = parent.devicePixelRatioF()
        import pymupdf
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom * dpr, zoom * dpr), alpha=False)
        from PySide6.QtGui import QImage, QPixmap
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888).copy()
        qp = QPixmap.fromImage(img)
        qp.setDevicePixelRatio(dpr)
        label = QLabel()
        label.setPixmap(qp)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.addWidget(label, 0, Qt.AlignCenter)
        theme.style(self, "QDialog {{ background: {CANVAS}; }}")
