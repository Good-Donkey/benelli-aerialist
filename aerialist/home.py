"""The Home screen shown when no PDF is open: Open, a few ways to start, and recent files as cards."""
import hashlib
import os
import time

import pymupdf
from PySide6.QtCore import Qt, Signal, QTimer, QSize
from PySide6.QtGui import QImage, QPixmap, QIcon
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, QFrame, QScrollArea, QSizePolicy,
)

from . import theme
from .chrome import primary_button, shadow
from .filecheck import online_only
from .icons import icon, pixmap

CARD_W = 150
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
PREVIEW_H = 120


_PREVIEWS = {}  # preview key -> QPixmap, for this run


def _preview_dir():
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "Aerialist", "previews")


def _preview_key(path, dpr):
    """Names a first-page picture by the file, its size and when it was last changed, so an edited file gets
    a new one."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    raw = f"{os.path.normcase(os.path.abspath(path))}|{st.st_size}|{int(st.st_mtime)}|{dpr:.2f}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def prune_previews(paths, dpr):
    """Delete saved first-page pictures of files no longer in the recent list (or since changed)."""
    keep = {_preview_key(p, dpr) for p in paths}
    try:
        for name in os.listdir(_preview_dir()):
            if name.endswith(".png") and name[:-4] not in keep:
                os.remove(os.path.join(_preview_dir(), name))
    except OSError:
        pass


def _when(t):
    days = int((time.time() - t) // 86400)
    if days <= 0:
        return "today"
    if days == 1:
        return "yesterday"
    if days < 7:
        return f"{days} days ago"
    lt = time.localtime(t)  # "Jan 5, 2026", the same style as dates added in Fill & Sign
    return f"{MONTHS[lt.tm_mon - 1]} {lt.tm_mday}, {lt.tm_year}"


def _where(path):
    parts = [p for p in os.path.normpath(os.path.dirname(path)).replace("\\", "/").split("/") if p]
    return " › ".join(parts[-2:]) if parts else ""


class Card(QFrame):
    """A recent file: first-page preview, name, where it is and when it was changed."""
    clicked = Signal(str)

    def __init__(self, path):
        super().__init__()
        self.path = path
        self.setObjectName("card")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedWidth(CARD_W)
        self.setToolTip(path)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(4)
        self.preview = QLabel()
        self.preview.setFixedSize(CARD_W - 20, PREVIEW_H)
        self.preview.setAlignment(Qt.AlignCenter)
        theme.style(self.preview, "background: {CANVAS}; border-radius: 4px;")
        lay.addWidget(self.preview)
        lay.addSpacing(4)
        name = QLabel()
        name.setObjectName("cardName")
        fm = name.fontMetrics()
        name.setText(fm.elidedText(os.path.basename(path), Qt.ElideMiddle, CARD_W - 24))
        lay.addWidget(name)
        try:
            when = _when(os.path.getmtime(path))
        except OSError:
            when = ""
        where = QLabel()
        where.setObjectName("cardWhere")
        text = " · ".join(t for t in (_where(path), when) if t)
        where.setText(where.fontMetrics().elidedText(text, Qt.ElideLeft, CARD_W - 24))
        lay.addWidget(where)

    def load_preview(self, dpr):
        key = _preview_key(self.path, dpr)
        cached = _PREVIEWS.get(key)
        if cached is None and key:
            disk = QPixmap(os.path.join(_preview_dir(), key + ".png"))
            if not disk.isNull():
                disk.setDevicePixelRatio(dpr)
                cached = _PREVIEWS[key] = disk
        if cached is not None:
            self.preview.setPixmap(cached)
            return
        if online_only(self.path):  # drawing it would download the whole file from the cloud first
            self.preview.setPixmap(pixmap("pages", 32, "DISABLED"))
            return
        try:
            doc = pymupdf.open(self.path)
            if doc.needs_pass:
                raise ValueError
            page = doc[0]
            w, h = CARD_W - 20, PREVIEW_H
            zoom = min(w / page.rect.width, h / page.rect.height) * dpr
            pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
            img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888).copy()
            qp = QPixmap.fromImage(img)
            qp.setDevicePixelRatio(dpr)
            self.preview.setPixmap(qp)
            doc.close()
            if key:  # kept, so Home shows it at once next time instead of opening the PDF again
                _PREVIEWS[key] = qp
                os.makedirs(_preview_dir(), exist_ok=True)
                img.save(os.path.join(_preview_dir(), key + ".png"))
        except Exception:
            self.preview.setPixmap(pixmap("pages", 32, "DISABLED"))

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit(self.path)


class HomeScreen(QScrollArea):
    open_clicked = Signal()
    combine = Signal()
    pictures = Signal()
    fill_sign = Signal()
    open_path = Signal(str)
    clear_recent = Signal()
    make_default = Signal()
    not_now = Signal()
    show_features = Signal()

    def __init__(self, icon_path):
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        page = QWidget()
        page.setObjectName("home")
        self.setWidget(page)
        outer = QHBoxLayout(page)
        outer.addStretch(1)
        col = QVBoxLayout()
        col.setSpacing(14)
        outer.addLayout(col, 0)
        outer.addStretch(1)
        body = QWidget()
        body.setFixedWidth(680)
        col.addSpacing(36)
        col.addWidget(body)
        col.addStretch(1)
        lay = QVBoxLayout(body)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)

        head = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(QIcon(icon_path).pixmap(40, 40))
        title = QLabel("Benelli Aerialist")
        title.setObjectName("homeTitle")
        head.addWidget(logo)
        head.addSpacing(6)
        head.addWidget(title)
        head.addStretch(1)
        tour = QPushButton("What can it do?")
        tour.setObjectName("link")
        tour.setCursor(Qt.PointingHandCursor)
        tour.clicked.connect(self.show_features)
        head.addWidget(tour)
        lay.addLayout(head)

        # Offer to become the default PDF app (instead of a pop-up).
        self.banner = QFrame()
        self.banner.setObjectName("banner")
        bl = QHBoxLayout(self.banner)
        bl.setContentsMargins(14, 10, 10, 10)
        star = QLabel()
        star.setPixmap(pixmap("star", 20, "ACCENT"))
        theme.on_change(lambda: star.setPixmap(pixmap("star", 20, "ACCENT")))
        text = QLabel("Set Benelli Aerialist as the default program for PDFs?")
        text.setWordWrap(True)
        yes = primary_button("Make default")
        no = QPushButton("Not now")
        no.setCursor(Qt.PointingHandCursor)
        yes.clicked.connect(self.make_default)
        no.clicked.connect(self.not_now)
        bl.addWidget(star)
        bl.addSpacing(6)
        bl.addWidget(text, 1)
        bl.addWidget(yes)
        bl.addWidget(no)
        self.banner.hide()
        lay.addWidget(self.banner)

        row = QHBoxLayout()
        row.setSpacing(12)
        open_btn = QPushButton(" Open")
        open_btn.setObjectName("openBig")
        open_btn.setIcon(icon("open", "white", "white", 22))
        open_btn.setIconSize(QSize(22, 22))
        open_btn.setCursor(Qt.PointingHandCursor)
        open_btn.setToolTip("Open a PDF (Ctrl+O)")
        open_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        open_btn.clicked.connect(self.open_clicked)
        shadow(open_btn, 12, 40, 2)
        row.addWidget(open_btn)
        for ic, label, sig in (("merge", "Merge PDFs", self.combine), ("convert", "Convert", self.pictures),
                               ("sign", "Fill && Sign", self.fill_sign)):
            b = QPushButton(" " + label)
            b.setObjectName("startBtn")
            b.setIcon(icon(ic, "ACCENT", "ACCENT", 22))
            b.setIconSize(QSize(22, 22))
            b.setCursor(Qt.PointingHandCursor)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            b.clicked.connect(sig)
            row.addWidget(b)
        lay.addLayout(row)
        hint = QLabel("Drag a PDF or image here to view it. Drag several to merge them.\n"
                      "Or paste a screenshot (Ctrl+V) to blur, mark up or convert it.")
        hint.setObjectName("dropHint")
        hint.setAlignment(Qt.AlignCenter)
        lay.addWidget(hint)

        lay.addSpacing(10)
        rh = QHBoxLayout()
        self.recent_title = QLabel("Recent")
        self.recent_title.setStyleSheet("font-weight: 600; font-size: 15px;")
        self.clear_btn = QPushButton("Clear list")
        self.clear_btn.setObjectName("link")
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        self.clear_btn.clicked.connect(self.clear_recent)
        rh.addWidget(self.recent_title)
        rh.addStretch(1)
        rh.addWidget(self.clear_btn)
        lay.addLayout(rh)
        self.grid = QGridLayout()
        self.grid.setSpacing(14)
        self.grid.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        lay.addLayout(self.grid)
        self.cards = []
        self._queue = []
        self._timer = QTimer(self, interval=0)
        self._timer.timeout.connect(self._next_preview)

    def set_recent(self, paths):
        for c in self.cards:
            c.deleteLater()
        self.cards = []
        for n, p in enumerate(paths[:8]):
            card = Card(p)
            card.clicked.connect(self.open_path)
            self.grid.addWidget(card, n // 4, n % 4)
            self.cards.append(card)
        for w in (self.recent_title, self.clear_btn):
            w.setVisible(bool(paths))
        self._queue = list(self.cards)  # first-page pictures are drawn one at a time, after showing
        self._timer.start()
        prune_previews(paths[:8], self.devicePixelRatioF())

    def _next_preview(self):
        if not self._queue:
            self._timer.stop()
            return
        card = self._queue.pop(0)
        try:
            card.load_preview(self.devicePixelRatioF())
        except RuntimeError:  # card was replaced meanwhile
            pass
