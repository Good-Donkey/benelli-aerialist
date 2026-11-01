"""Signatures: saved signatures and initials for several people, and placing them on pages.

People are kept in %APPDATA%\\Aerialist\\signatures (people.json plus one PNG per signature),
so they're still there after updates. Placed signatures float over the page as movable,
resizable boxes until the Sign screen is finished; only then are they written into the PDF.
"""
import json
import os
import uuid

import pymupdf
from PySide6.QtCore import Qt, Signal, QPointF, QRect, QRectF, QSize, QDate, QLocale
from PySide6.QtGui import QImage, QPainter, QPen, QColor, QFont, QFontDatabase, QFontMetrics, QFontMetricsF, QPainterPath, QPixmap, QIcon
from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTabWidget, QComboBox,
    QDialogButtonBox, QFileDialog, QFrame, QToolButton, QMenu, QScrollArea, QRadioButton, QButtonGroup,
    QMessageBox, QCheckBox, QSizePolicy, QWidgetAction,
)

from .organizer import IMAGE_EXTS
from .chrome import BarTools, tool_button, separator
from .icons import icon
from . import fonts as app_fonts
from .forms import FormLayer
from . import overlay
from .overlay import ImageItem, OverlaySession, read_image, next_size, line_image
from .edit import TextItem, fit_size
from .stamps import stamp_image
from .stamp_bar import StampGroup
from . import stamps as stamp_sizes
from .popups import APP_NAME, ask

TEXT_STYLE = {"color": "#000000", "font": "helv", "size": 11}

INK = {"Black": QColor(20, 20, 20), "Blue": QColor(16, 52, 166)}
SCRIPT_FONTS = ["Segoe Script", "Ink Free", "Lucida Handwriting", "Segoe Print", "Brush Script MT", "Freestyle Script"]
# Starting height on the page (points; 72 = 1 inch) the first time each kind is placed.
DEFAULT_HEIGHT = {"signature": 36, "initials": 24, "date": 12, "text": 12}


def data_dir():
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "Aerialist", "signatures")


# ---- image helpers --------------------------------------------------------
def crop_to_ink(img, pad=6):
    """Trim transparent edges so the box on the page hugs the signature."""
    img = img.convertToFormat(QImage.Format_ARGB32)
    alpha = img.convertToFormat(QImage.Format_Alpha8)
    data, bpl = bytes(alpha.constBits()), alpha.bytesPerLine()
    w, h = alpha.width(), alpha.height()
    top = bottom = None
    left, right = w, -1
    for y in range(h):
        row = data[y * bpl:y * bpl + w].translate(_FAINT)  # ignore nearly invisible pixels
        stripped = row.lstrip(b"\0")
        if not stripped:
            continue
        top = y if top is None else top
        bottom = y
        left = min(left, w - len(stripped))
        right = max(right, len(row.rstrip(b"\0")) - 1)
    if top is None:
        return None
    r = QRect(left, top, right - left + 1, bottom - top + 1).adjusted(-pad, -pad, pad, pad)
    return img.copy(r.intersected(img.rect()))


_FAINT = bytes(0 if a < 24 else a for a in range(256))
# Grey level -> opacity for scanned/photographed signatures: paper vanishes, ink stays solid.
_PAPER = bytes(0 if g >= 200 else 255 if g <= 110 else int((200 - g) * 255 / 90) for g in range(256))


def remove_paper(img):
    """Make a white or light-grey background transparent, keeping the ink's own colour."""
    img = img.convertToFormat(QImage.Format_ARGB32)
    grey = img.convertToFormat(QImage.Format_Grayscale8)
    bpl = grey.bytesPerLine()
    alpha_bytes = bytes(grey.constBits()).translate(_PAPER)
    alpha = QImage(alpha_bytes, grey.width(), grey.height(), bpl, QImage.Format_Grayscale8).copy()
    img.setAlphaChannel(alpha)
    return img


def text_image(text, family, color, px=110, italic=False):
    font = QFont(family)
    font.setPixelSize(px)
    font.setItalic(italic)
    fm = QFontMetrics(font)
    w = fm.horizontalAdvance(text) + px  # script fonts overhang their advance; leave room
    h = fm.height() + px // 2
    img = QImage(max(w, 1), max(h, 1), QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    p.setFont(font)
    p.setPen(color)
    p.drawText(px // 2, px // 4 + fm.ascent(), text)
    p.end()
    return crop_to_ink(img, pad=4)


def on_paper(img, size):
    """A saved signature shown on a small white card, as it will look on the page: dark ink on a see-through
    background would vanish on the dark theme's grey."""
    dpr = 2
    pix = QPixmap(size.width() * dpr, size.height() * dpr)
    pix.setDevicePixelRatio(dpr)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QColor(0, 0, 0, 40))
    p.setBrush(Qt.white)
    p.drawRoundedRect(QRectF(0.5, 0.5, size.width() - 1, size.height() - 1), 4, 4)
    pad = 3
    ink = QPixmap.fromImage(img).scaled((size - QSize(2 * pad, 2 * pad)) * dpr, Qt.KeepAspectRatio,
                                        Qt.SmoothTransformation)
    ink.setDevicePixelRatio(dpr)
    w, h = ink.width() / dpr, ink.height() / dpr
    p.drawPixmap(QPointF((size.width() - w) / 2, (size.height() - h) / 2), ink)
    p.end()
    return pix


def today_text():
    """Today's date, written like "Jan 5, 2026"."""
    return QLocale(QLocale.English, QLocale.UnitedStates).toString(QDate.currentDate(), "MMM d, yyyy")


def initials_of(name):
    return "".join(part[0].upper() for part in name.split() if part[:1].isalpha())


# ---- saved people ---------------------------------------------------------
class SignatureStore:
    """people.json: [{"id", "name", "signature": file, "initials": file, "heights": {kind: pt}}]"""

    def __init__(self, folder=None):
        self.folder = folder or data_dir()
        self.people = []
        try:
            with open(os.path.join(self.folder, "people.json"), encoding="utf-8") as f:
                self.people = json.load(f)
        except (OSError, ValueError):
            pass

    def save(self):
        os.makedirs(self.folder, exist_ok=True)
        tmp = os.path.join(self.folder, "people.json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.people, f, indent=1)
        os.replace(tmp, os.path.join(self.folder, "people.json"))

    def image(self, person, kind):
        name = person.get(kind)
        if not name:
            return None
        img = QImage(os.path.join(self.folder, name))
        return None if img.isNull() else img

    def put(self, person, name, images):
        """Add (person None) or update someone. images: {kind: QImage or None (keep)}."""
        if person is None:
            person = {"id": uuid.uuid4().hex[:12], "heights": {}}
            self.people.append(person)
        person["name"] = name
        os.makedirs(self.folder, exist_ok=True)
        for kind, img in images.items():
            if img is None:
                continue
            old = person.get(kind)
            fname = f"{person['id']}-{kind}-{uuid.uuid4().hex[:6]}.png"
            img.save(os.path.join(self.folder, fname), "PNG")
            person[kind] = fname
            if old:
                _remove(os.path.join(self.folder, old))
        self.save()
        return person

    def remove(self, person):
        for kind in ("signature", "initials"):
            if person.get(kind):
                _remove(os.path.join(self.folder, person[kind]))
        self.people.remove(person)
        self.save()

    def remember_height(self, person_id, kind, height):
        for p in self.people:
            if p["id"] == person_id:
                p.setdefault("heights", {})[kind] = round(height, 1)
                self.save()

    def height(self, person_id, kind):
        for p in self.people:
            if p["id"] == person_id:
                return p.get("heights", {}).get(kind)
        return None


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


# ---- creating a signature ------------------------------------------------
class InkCanvas(QWidget):
    """Draw with the mouse, pen or finger."""
    changed = Signal()

    def __init__(self, size):
        super().__init__()
        self.setFixedSize(size)
        self.strokes = []
        self.color = INK["Black"]
        self.setCursor(Qt.CrossCursor)
        self.setAttribute(Qt.WA_StaticContents)

    def clear(self):
        self.strokes = []
        self.update()
        self.changed.emit()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.strokes.append([e.position()])
            self.update()

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.LeftButton and self.strokes:
            self.strokes[-1].append(e.position())
            self.update()

    def mouseReleaseEvent(self, e):
        self.changed.emit()

    def _paint(self, p, scale):
        pen = QPen(self.color, 2.6 * scale, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        for s in self.strokes:
            pts = [QPointF(pt.x() * scale, pt.y() * scale) for pt in s]
            if len(pts) == 1:
                p.drawPoint(pts[0])
                continue
            path = QPainterPath(pts[0])
            for a, b in zip(pts[1:], pts[2:]):  # smooth curve through midpoints
                path.quadTo(a, (a + b) / 2)
            path.lineTo(pts[-1])
            p.drawPath(path)

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), Qt.white)
        p.setPen(QPen(QColor("#bbb"), 1, Qt.DashLine))
        base = int(self.height() * 0.72)
        p.drawLine(16, base, self.width() - 16, base)  # a line to sign on
        p.setRenderHint(QPainter.Antialiasing)
        self._paint(p, 1)
        p.end()

    def image(self):
        if not self.strokes:
            return None
        scale = 3  # stored sharper than on screen so it prints crisply
        img = QImage(self.width() * scale, self.height() * scale, QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        self._paint(p, scale)
        p.end()
        return crop_to_ink(img)


class SignatureEditor(QWidget):
    """Draw / Type / Image tabs for one signature (or one set of initials)."""

    def __init__(self, kind, existing=None):
        super().__init__()
        self.kind = kind
        lay = QVBoxLayout(self)
        color_row = QHBoxLayout()
        color_row.addWidget(QLabel("Ink:"))
        self.color_group = QButtonGroup(self)
        for i, name in enumerate(INK):
            r = QRadioButton(name)
            r.setChecked(i == 0)
            self.color_group.addButton(r, i)
            color_row.addWidget(r)
        color_row.addStretch()
        self.color_group.idToggled.connect(self._color_changed)
        lay.addLayout(color_row)

        self.tabs = QTabWidget()
        lay.addWidget(self.tabs)

        # Draw
        draw = QWidget()
        dl = QVBoxLayout(draw)
        self.canvas = InkCanvas(QSize(560, 180) if kind == "signature" else QSize(260, 180))
        dl.addWidget(self.canvas, 0, Qt.AlignHCenter)
        row = QHBoxLayout()
        row.addWidget(QLabel("Sign above the line with your mouse, pen or finger."))
        row.addStretch()
        clear = QPushButton("Clear")
        clear.clicked.connect(self.canvas.clear)
        row.addWidget(clear)
        dl.addLayout(row)
        self.tabs.addTab(draw, "Draw")

        # Type
        typ = QWidget()
        tl = QVBoxLayout(typ)
        self.text = QLineEdit()
        self.text.setPlaceholderText("Your name" if kind == "signature" else "Your initials")
        self.font_box = QComboBox()
        app_fonts.all_fonts()  # makes the handwriting fonts shipped with the app available
        have = set(QFontDatabase.families())
        choices = [f for f in app_fonts.HANDWRITING + SCRIPT_FONTS if f in have] or [QFont().family()]
        self.font_box.addItems(choices)
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumHeight(120)
        self.preview.setStyleSheet("background: white; border: 1px solid #ccc;")
        tl.addWidget(self.text)
        tl.addWidget(self.font_box)
        tl.addWidget(self.preview)
        self.text.textChanged.connect(self._update_preview)
        self.font_box.currentIndexChanged.connect(self._update_preview)
        self._typed_by_user = False
        self.text.textEdited.connect(lambda: setattr(self, "_typed_by_user", True))
        self.tabs.addTab(typ, "Type")

        # Image
        imgw = QWidget()
        il = QVBoxLayout(imgw)
        self.loaded = existing
        self.raw = None  # picture as chosen, before removing the background
        self.img_label = QLabel()
        self.img_label.setAlignment(Qt.AlignCenter)
        self.img_label.setMinimumHeight(140)
        self.setAcceptDrops(True)
        self.img_label.setStyleSheet("background: white; border: 1px solid #ccc;")
        row = QHBoxLayout()
        browse = QPushButton("Choose an image…")
        browse.clicked.connect(self._browse)
        self.paper = QCheckBox("Remove white background")
        self.paper.setChecked(True)
        self.paper.toggled.connect(self._process_raw)
        row.addWidget(browse)
        row.addWidget(self.paper)
        row.addStretch()
        il.addWidget(QLabel("Drag an image here, or choose one. A photo or scan on white paper works well."
                            if existing is None
                            else "Current one shown. Choose an image, or use Draw or Type, to replace it."))
        il.addWidget(self.img_label)
        il.addLayout(row)
        self.tabs.addTab(imgw, "Current" if existing is not None else "Image")
        if existing is not None:
            self.tabs.setCurrentWidget(imgw)
        self._show_loaded()

    def set_name(self, name):
        if not self._typed_by_user:
            self.text.setText(name if self.kind == "signature" else initials_of(name))

    def _color(self):
        return list(INK.values())[self.color_group.checkedId()]

    def _color_changed(self, *_):
        self.canvas.color = self._color()
        self.canvas.update()
        self._update_preview()

    def _typed(self):
        t = self.text.text().strip()
        return text_image(t, self.font_box.currentText(), self._color()) if t else None

    def _update_preview(self):
        img = self._typed()
        self._set_pix(self.preview, img)

    def _set_pix(self, label, img):
        if img is None:
            label.setPixmap(QPixmap())
            return
        pix = QPixmap.fromImage(img)
        label.setPixmap(pix.scaled(QSize(520, 110), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _browse(self):
        exts = " ".join("*" + e for e in IMAGE_EXTS)
        path, _ = QFileDialog.getOpenFileName(self, "Choose an image of the signature", "", f"Images ({exts})")
        if path:
            self.load_picture(path)

    def load_picture(self, path):
        img = read_image(path, max_side=1600)
        if img is None:
            QMessageBox.warning(self, APP_NAME, f"That image couldn't be opened.\n\nDetails: {overlay.read_error}")
            return
        if img.width() > 1600:
            img = img.scaledToWidth(1600, Qt.SmoothTransformation)
        self.raw = img
        self._process_raw()
        self.tabs.setCurrentIndex(2)

    # A picture can be dragged in from File Explorer anywhere on this tab set.
    def _dropped(self, e):
        urls = [u.toLocalFile() for u in e.mimeData().urls()]
        return next((u for u in urls if u.lower().endswith(IMAGE_EXTS)), None)

    def dragEnterEvent(self, e):
        if self._dropped(e):
            e.acceptProposedAction()

    def dropEvent(self, e):
        path = self._dropped(e)
        if path:
            e.acceptProposedAction()
            self.load_picture(path)

    def _process_raw(self):
        if self.raw is None:
            return
        img = remove_paper(self.raw) if self.paper.isChecked() else self.raw.convertToFormat(QImage.Format_ARGB32)
        self.loaded = crop_to_ink(img) or img
        self.tabs.setTabText(2, "Image")
        self._show_loaded()

    def _show_loaded(self):
        self._set_pix(self.img_label, self.loaded)

    def result(self):
        """(image, changed): the chosen picture, and whether it differs from the saved one."""
        tab = self.tabs.currentIndex()
        if tab == 0:
            img = self.canvas.image()
            if img is not None:
                return img, True
        elif tab == 1:
            img = self._typed()
            if img is not None:
                return img, True
        return self.loaded, self.raw is not None


class PersonDialog(QDialog):
    def __init__(self, parent, store, person=None):
        super().__init__(parent)
        self.store, self.person = store, person
        self.setWindowTitle("Edit signature" if person else "Add a person's signature")
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel("Name:"))
        self.name = QLineEdit(person["name"] if person else "")
        self.name.setPlaceholderText("e.g. Sam Taylor")
        row.addWidget(self.name)
        lay.addLayout(row)
        self.tabs = QTabWidget()
        self.editors = {}
        for kind, title in (("signature", "Signature"), ("initials", "Initials")):
            ed = SignatureEditor(kind, store.image(person, kind) if person else None)
            self.editors[kind] = ed
            self.tabs.addTab(ed, title)
        lay.addWidget(self.tabs)
        self.name.textChanged.connect(lambda t: [ed.set_name(t) for ed in self.editors.values()])
        if person:
            for ed in self.editors.values():
                ed.set_name(person["name"])
        self.error = QLabel()
        self.error.setObjectName("error")
        lay.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _accept(self):
        name = self.name.text().strip()
        if not name:
            self.error.setText("Enter a name, so you can tell whose signature this is.")
            return
        images = {}
        for kind, ed in self.editors.items():
            img, changed = ed.result()
            images[kind] = img if (changed or not (self.person and self.person.get(kind))) else None
        if images["signature"] is None and not (self.person and self.person.get("signature")):
            self.tabs.setCurrentIndex(0)
            self.error.setText("Draw, type or choose an image for the signature.")
            return
        self.person = self.store.put(self.person, name, images)
        self.accept()


# ---- the Fill & Sign tools in the top bar ---------------------------------------
class SignTools(BarTools):
    """Signature ▾, Initials ▾ (saved people), Date, Text, Stamps ▾, Next field, and how many fields are filled."""
    pick = Signal(str, str, QImage)  # key (person id, stamp, or "date"/"text"), kind, image
    next_field = Signal()

    def __init__(self, store):
        super().__init__()
        self.store = store
        self.sig_btn = tool_button("sign", "Signature")
        self.ini_btn = tool_button("initials", "Initials")
        for b in (self.sig_btn, self.ini_btn):
            b.setPopupMode(QToolButton.InstantPopup)
            b.setProperty("dropdown", True)  # shows a small arrow, like Edit's Shape and Draw
            b.setMenu(QMenu(b))
            self.add(b)
        self.add(separator())
        date = self.add(tool_button("date", "Date"))
        date.clicked.connect(lambda: self.pick.emit("date", "date", QImage()))
        text = self.add(tool_button("text", "Text"))
        text.clicked.connect(lambda: self.pick.emit("text", "text", QImage()))
        self.stamp_group = self.add(StampGroup())
        self.stamp_group.picked.connect(lambda k: self.pick.emit(k, "stamp", stamp_image(k)))
        self.field_sep = self.add(separator())
        self.next_btn = self.add(tool_button("next_field", "Next field"))
        self.next_btn.clicked.connect(self.next_field)
        self.count = self.add(QLabel())
        self.count.setObjectName("chip")
        self.count.setFixedHeight(24)
        self.refresh()

    def set_fields(self, filled, total):
        for w in (self.field_sep, self.next_btn, self.count):
            w.setVisible(total > 0)
        self.count.setText(f"{filled} of {total} filled")

    def refresh(self):
        for btn, kind in ((self.sig_btn, "signature"), (self.ini_btn, "initials")):
            menu = btn.menu()
            menu.clear()
            for person in self.store.people:
                img = self.store.image(person, kind)
                if img is None:
                    menu.addAction(f"{person['name']}: add {kind}…", lambda p=person, k=kind: self.edit_person(p, k))
                    continue
                menu.addAction(self._person_action(menu, person, kind, img))
            if self.store.people:
                menu.addSeparator()
            menu.addAction(icon("plus"), "Add a person…", self.add_person)
            if self.store.people:
                manage = menu.addMenu("Change or delete")
                for person in self.store.people:
                    sub = manage.addMenu(person["name"])
                    sub.addAction("Change…", lambda p=person: self.edit_person(p))
                    sub.addAction("Delete", lambda p=person: self.delete_person(p))

    def _person_action(self, menu, person, kind, img):
        """A menu row showing the signature itself next to the name."""
        b = QToolButton()
        b.setIcon(QIcon(on_paper(img, QSize(130, 34))))
        b.setIconSize(QSize(130, 34))
        b.setText(person["name"])
        b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        b.setCursor(Qt.PointingHandCursor)
        b.setObjectName("menuRow")
        b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        act = QWidgetAction(menu)
        act.setDefaultWidget(b)
        b.clicked.connect(lambda: (menu.close(), self.pick.emit(person["id"], kind, img)))
        return act

    def add_person(self):
        dlg = PersonDialog(self, self.store)
        if dlg.exec():
            self.refresh()

    def edit_person(self, person, kind="signature"):
        dlg = PersonDialog(self, self.store, person)
        dlg.tabs.setCurrentIndex(1 if kind == "initials" else 0)
        if dlg.exec():
            self.refresh()

    def delete_person(self, person):
        if ask(self, f"Delete {person['name']}'s saved signature and initials?", "Delete"):
            self.store.remove(person)
            self.refresh()


# ---- signatures placed on the page ---------------------------------------
class Stamp(ImageItem):
    """A placed signature: keeps its shape when resized."""

    def __init__(self, session, label, rect, image, key, kind):
        self.key, self.kind = key, kind
        super().__init__(session, label, rect, image)


class SignSession(OverlaySession):
    def __init__(self, view, store, on_change):
        super().__init__(view, on_change)
        self.store = store
        self.armed = None  # (key, kind, image) waiting to be placed
        self._placing = None
        self._typing = None  # [text item, x, y, dragged] while a date or text box is being placed
        self.form = FormLayer(view, on_change, self.checkpoint)
        self.on_select = lambda item: None
        self.on_armed = lambda armed: None  # the toolbar lights up the stamp picked up

    def selection_changed(self, item):
        self.on_select(item)

    def start(self):
        super().start()
        self.form.build()

    def stop(self):
        self.form.clear()
        super().stop()
        self._disarm()

    def pending(self):
        return len(self.stamps) + len(self.form.edited())

    def finish_typing(self):
        for s in list(self.stamps):
            if isinstance(s, TextItem):
                s.finish_edit()

    def extra_state(self):
        return self.form.snapshot()

    def set_extra_state(self, extra):
        self.form.set_values(extra or {})

    def take(self):
        filled = self.form.take()  # before the fields are cleared away
        return filled + super().take()

    def arm(self, key, kind, image):
        self.armed = (key, kind, image)
        self.on_armed(self.armed)
        self.set_cursor(Qt.CrossCursor)
        self.select(None)
        self._mouse_through(True)

    def _mouse_through(self, on):
        """Fields and things already placed let the mouse through to the page while something is picked up."""
        self.form.set_mouse_through(on)
        for s in self.stamps:
            s.setAttribute(Qt.WA_TransparentForMouseEvents, on)

    def add(self, item):
        item.setAttribute(Qt.WA_TransparentForMouseEvents, bool(self.armed))
        super().add(item)

    def armed_or_tool(self):
        return self.armed is not None

    def cancel_tool(self):
        self._disarm()

    def _disarm(self):
        self.armed = None
        self.on_armed(None)
        self.set_cursor(None)
        self.hide_ghost()
        self._mouse_through(False)

    def armed_preview(self, label, pos):
        if not self.armed or self._placing or self._typing:
            return None
        key, kind, image = self.armed
        if kind == "stamp":
            return image, self.stamp_rect(label, pos, key, image)
        if kind in ("signature", "initials"):
            return image, self._sig_rect(label, pos, key, kind, image)
        size = self.text_size()
        img, w, h = line_image(today_text() if kind == "date" else "Text",
                               app_fonts.qfont(TEXT_STYLE["font"], size * 4), TEXT_STYLE["color"])
        z = self.view.zoom
        x, y = pos.x() / z, pos.y() / z
        return img, pymupdf.Rect(x, y - size, x + w, y - size + h)

    def wheel_armed(self, delta):
        if not self.armed:
            return False
        key, kind, image = self.armed
        if kind == "stamp":
            stamp_sizes.grow(delta / 120)
        elif kind in ("signature", "initials"):
            label, pos = self._ghost_at
            h = self._sig_rect(label, pos, key, kind, image).height * 1.1 ** (delta / 120)
            self.store.remember_height(key, kind, max(6, min(h, 600)))
        else:
            n = self.wheel_steps(delta)
            if n:
                self._text_size = next_size(self.text_size(), n)
                self.selection_changed(None)  # the size box shows the new size
        return True

    def set_item_size(self, item, size):
        self.select(item)
        self.set_text_size(size)
        if item.kind == "date":
            self._fit_date(item)
        self.selection_changed(item)

    def placing_item(self):
        return self._placing[0] if self._placing else None

    def text_size(self):
        return getattr(self, "_text_size", TEXT_STYLE["size"])

    def set_text_size(self, size):
        self._text_size = size
        item = self.selected()
        if isinstance(item, TextItem):
            self.checkpoint(("size", item))
            item.apply_style(dict(TEXT_STYLE, size=size))

    def remember_size(self, stamp):
        if stamp.kind in ("signature", "initials"):
            self.store.remember_height(stamp.key, stamp.kind, stamp.rect_pt.height)
        elif stamp.kind == "stamp":
            stamp_sizes.remember(stamp.key, stamp.rect_pt.height)

    def _default_height(self, key, kind):
        if kind in ("signature", "initials"):
            h = self.store.height(key, kind)
            if h:
                return h
        last = getattr(self, "_last_" + kind, None)  # dates and text: size used last time this session
        return last or DEFAULT_HEIGHT[kind]

    # ---- page mouse hooks (called by PageLabel) ----
    def press(self, label, pos):
        for s in list(self.stamps):  # clicking elsewhere ends typing
            if isinstance(s, TextItem):
                s.finish_edit()
        self.hide_ghost()
        if not self.armed:
            self.select(None)
            return True  # no links followed while signing
        key, kind, image = self.armed
        page = self.view.doc[label.index].rect
        z = self.view.zoom
        if kind in ("date", "text"):
            # Typed straight onto the page, like Text in Edit. A click puts it on the line clicked;
            # dragging a box sets its size, and the text size is fitted to the box's height.
            x, y = pos.x() / z, pos.y() / z
            size = self.text_size()
            w = min(200 if kind == "text" else 90, page.width - x)
            top = max(0, y - size)
            item = TextItem(self, label, pymupdf.Rect(x, top, x + max(w, 20), top + 16), dict(TEXT_STYLE, size=size))
            item.kind = kind
            if kind == "date":
                item.text = today_text()
            item.fit_height()
            self._disarm()
            self.add(item)
            self._typing = [item, x, y, False]
            return True
        if kind == "stamp":  # where the see-through copy was showing, at the size scrolled to
            stamp = Stamp(self, label, self.stamp_rect(label, pos, key, image), image, key, kind)
            stamp.stamp_key = key
            self._placing = (stamp, pos.x() / z, pos.y() / z)
            self.add(stamp)  # the stamp stays picked up for the next one (Esc puts it down)
            return True
        stamp = Stamp(self, label, self._sig_rect(label, pos, key, kind, image), image, key, kind)
        self._placing = (stamp, pos.x() / z, pos.y() / z)
        self._disarm()
        self.add(stamp)
        return True

    def _sig_rect(self, label, pos, key, kind, image):
        """Where a signature clicked at pos goes: its lower-left near the pointer, like signing on a line."""
        page = self.view.doc[label.index].rect
        aspect = image.width() / max(1, image.height())
        h = self._default_height(key, kind)
        w = h * aspect
        cap = page.width * 0.9 if self.store.height(key, kind) else min(page.width * 0.9, 216)  # 3 inches
        if w > cap:
            w = cap
            h = w / aspect
        if h > page.height * 0.9:
            h = page.height * 0.9
            w = h * aspect
        z = self.view.zoom
        x, y = pos.x() / z, pos.y() / z
        x0 = max(0, min(x - w * 0.05, page.width - w))
        y0 = max(0, min(y - h * 0.8, page.height - h))
        return pymupdf.Rect(x0, y0, x0 + w, y0 + h)

    def _fit_date(self, item):
        """One line: widen the box so the whole date shows."""
        page = item.page_rect()
        need = QFontMetricsF(item.qfont(4)).horizontalAdvance(item.text) / 4 + item.font_size * 0.4
        x0 = min(item.rect_pt.x0, max(0, page.width - need))
        item.rect_pt = pymupdf.Rect(x0, item.rect_pt.y0, max(item.rect_pt.x1, min(page.width, x0 + need)),
                                    item.rect_pt.y1)
        item.fit_height()

    def move(self, label, pos):
        if self.armed and not self._placing and not self._typing:
            self.follow(label, pos)
            return True
        if self._typing:
            item, x, y, _ = self._typing
            z = self.view.zoom
            page = self.view.doc[label.index].rect
            cx, cy = max(0, min(pos.x() / z, page.width)), max(0, min(pos.y() / z, page.height))
            if item.label is label and (abs(cx - x) * z >= 6 or abs(cy - y) * z >= 6):
                self._typing[3] = True
                item.rect_pt = pymupdf.Rect(min(x, cx), min(y, cy), max(x, cx, min(x, cx) + 20),
                                            max(y, cy, min(y, cy) + 6))
                item.relayout()
            return True
        if not self._placing:
            return False
        stamp, x, y = self._placing
        if stamp.label is not label or stamp.kind == "stamp":
            return True  # stamps are sized with the scroll wheel
        z = self.view.zoom
        page = self.view.doc[label.index].rect
        w = pos.x() / z - x
        if w * z < 8:
            return True  # just a click so far: keep the default size
        # Dragging while placing sets the width (from the click point to the right).
        w = min(w, page.width - x)
        h = w / stamp.aspect
        y0 = max(0, min(y - h * 0.8, page.height - h))
        stamp.rect_pt = pymupdf.Rect(x, y0, x + w, y0 + h)
        stamp.relayout()
        return True

    def release(self, label, pos):
        if self._typing:
            item, _, _, dragged = self._typing
            self._typing = None
            if dragged and item.rect_pt.height >= 6:
                size = fit_size(item.rect_pt.height)
                self._text_size = size
                item.apply_style(dict(TEXT_STYLE, size=size))
            if item.kind == "date":
                self._fit_date(item)
            item.fit_height()
            self.selection_changed(item)  # the size box shows the new size
            if item.kind == "text":
                item.edit()
            return True
        if not self._placing:
            return False
        stamp = self._placing[0]
        self._placing = None
        self.remember_size(stamp)
        return True
