"""Resize pictures, from File Explorer's right-click menu: pick a size and get smaller copies (or replace the
originals), with each file's size before and after."""
import os

from PySide6.QtCore import Qt, QBuffer, QIODevice, QSize
from PySide6.QtGui import QColor, QImage, QImageIOHandler, QImageReader, QPainter
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QMessageBox, QProgressDialog,
    QRadioButton, QSpinBox, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
)

from . import theme
from .shell import free_path
from .popups import APP_NAME

SIZES = [("small", "Small", 854, 480), ("medium", "Medium", 1366, 768), ("large", "Large", 1920, 1080), ("xlarge", "X Large", 2560, 1440),
         ("phone", "Phone", 320, 568)]  # fit inside width x height, as Windows' Image Resizer does
NO_WRITER = {".gif": ".png"}  # pictures that can't be saved in their own format are saved as PNG


def human(n):
    for unit in ("bytes", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "bytes" else f"{n:.1f} {unit}"
        n /= 1024


def read_size(path):
    r = QImageReader(path)
    r.setAutoTransform(True)  # phone photos stand the right way up
    s = r.size()
    if r.transformation() & QImageIOHandler.TransformationRotate90:  # turned a quarter: width and height swap
        s = QSize(s.height(), s.width())
    return s


def target(size, how, percent, box, enlarge):
    """The new size of a picture of `size`."""
    w, h = size.width(), size.height()
    if how == "percent":
        f = percent / 100
    else:
        bw, bh = box
        if w < h and bw > bh:  # an upright picture fits an upright box
            bw, bh = bh, bw
        f = min(bw / w, bh / h)
    if f > 1 and not enlarge:
        f = 1
    return QSize(max(1, round(w * f)), max(1, round(h * f)))


def out_ext(path):
    ext = os.path.splitext(path)[1].lower()
    return NO_WRITER.get(ext, ext)


def encode(img, ext, quality):
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    fmt = {".jpg": "JPG", ".jpeg": "JPG", ".jfif": "JPG"}.get(ext, ext.strip(".").upper())
    if fmt == "JPG" and img.hasAlphaChannel():
        flat = QImage(img.size(), QImage.Format_RGB32)
        flat.fill(QColor("white"))
        p = QPainter(flat)
        p.drawImage(0, 0, img)
        p.end()
        img = flat
    if not img.save(buf, fmt, quality if fmt in ("JPG", "WEBP") else -1):
        raise RuntimeError("This kind of picture can't be saved.")
    return bytes(buf.data())


class ResizeDialog(QDialog):
    def __init__(self, paths, settings, parent=None):
        super().__init__(parent)
        self.paths, self.settings = paths, settings
        self.sizes = {p: read_size(p) for p in paths}
        self.bytes = {p: os.path.getsize(p) for p in paths}
        n = len(paths)
        self.setWindowTitle("Resize pictures")
        lay = QVBoxLayout(self)
        total = sum(self.bytes.values())
        lay.addWidget(QLabel(f"<b>{n} picture{'s' if n != 1 else ''}</b> · {human(total)}"))
        self.files = QTreeWidget()
        self.files.setHeaderLabels(["Picture", "Now", "After"])
        self.files.setRootIsDecorated(False)
        self.files.setSelectionMode(QTreeWidget.NoSelection)
        self.files.setFocusPolicy(Qt.NoFocus)
        self.files.setColumnWidth(0, 200)
        self.files.setColumnWidth(1, 190)
        self.items = {}
        for p in paths:
            s = self.sizes[p]
            item = QTreeWidgetItem([os.path.basename(p), f"{s.width()} × {s.height()} · {human(self.bytes[p])}", ""])
            item.setToolTip(0, p)
            self.files.addTopLevelItem(item)
            self.items[p] = item
        self.total = None
        if n > 1:  # a grey Total row under the pictures
            self.total = QTreeWidgetItem(["Total", f"{human(total)}", ""])
            self.total.setFlags(Qt.NoItemFlags)
            self.files.addTopLevelItem(self.total)
        self.files.setMinimumHeight(min(220, 40 + 24 * (n + (n > 1))))
        lay.addWidget(self.files)

        lay.addWidget(QLabel("New size (maintains aspect ratio):"))
        self.group = QButtonGroup(self)
        last = settings.value("resize/how", "medium")
        for key, label, w, h in SIZES:
            b = QRadioButton(f"{label} (up to {w} × {h})")
            b.setProperty("key", key)
            self.group.addButton(b)
            lay.addWidget(b)
            b.setChecked(key == last)
        row = QHBoxLayout()
        self.pct_btn = QRadioButton("Percent")
        self.pct_btn.setProperty("key", "percent")
        self.group.addButton(self.pct_btn)
        self.pct = QSpinBox()
        self.pct.setRange(1, 400)
        self.pct.setSuffix(" %")
        self.pct.setValue(int(settings.value("resize/percent", 50)))
        row.addWidget(self.pct_btn)
        row.addWidget(self.pct)
        row.addStretch(1)
        lay.addLayout(row)
        row = QHBoxLayout()
        self.custom_btn = QRadioButton("Custom")
        self.custom_btn.setProperty("key", "custom")
        self.group.addButton(self.custom_btn)
        self.cw, self.ch = QSpinBox(), QSpinBox()
        for box, key, default in ((self.cw, "resize/w", 1600), (self.ch, "resize/h", 1200)):
            box.setRange(1, 20000)
            box.setSuffix(" px")
            box.setValue(int(settings.value(key, default)))
        row.addWidget(self.custom_btn)
        row.addWidget(self.cw)
        row.addWidget(QLabel("×"))
        row.addWidget(self.ch)
        row.addStretch(1)
        lay.addLayout(row)
        self.pct_btn.setChecked(last == "percent")
        self.custom_btn.setChecked(last == "custom")
        if self.group.checkedButton() is None:
            self.group.buttons()[1].setChecked(True)

        self.enlarge = QCheckBox("Enlarge smaller pictures")
        self.enlarge.setChecked(settings.value("resize/enlarge", False, type=bool))
        lay.addWidget(self.enlarge)
        self.replace = QCheckBox("Replace originals")
        self.replace.setToolTip("Otherwise copies are saved next to them, like \"photo (Medium).jpg\"")
        self.replace.setChecked(settings.value("resize/replace", False, type=bool))
        lay.addWidget(self.replace)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Resize")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self.setMinimumWidth(660)

        self.group.buttonToggled.connect(lambda *_: self._update())
        for w in (self.pct, self.cw, self.ch):
            w.valueChanged.connect(lambda *_: self._update())
        self.enlarge.toggled.connect(lambda *_: self._update())
        self._update()

    def choice(self):
        key = self.group.checkedButton().property("key")
        box = next(((w, h) for k, _, w, h in SIZES if k == key), (self.cw.value(), self.ch.value()))
        return key, self.pct.value(), box, self.enlarge.isChecked()

    def _update(self):
        key, pct, box, enlarge = self.choice()
        est = 0
        for p in self.paths:
            old = self.sizes[p]
            new = target(old, "percent" if key == "percent" else "box", pct, box, enlarge)
            # A guess from the number of pixels (the real size shows when it's done).
            if new == old:
                est += self.bytes[p]
                self.items[p].setText(2, "Unchanged")
                continue
            ratio = (new.width() * new.height()) / max(1, old.width() * old.height())
            guess = self.bytes[p] * ratio ** 0.8
            est += guess
            self.items[p].setText(2, f"{new.width()} × {new.height()} · about {human(guess)}")
        if self.total is not None:
            self.total.setText(2, f"about {human(est)}")
            for col in range(3):
                self.total.setForeground(col, QColor(theme.MUTED))

    def remember(self):
        key, pct, box, enlarge = self.choice()
        s = self.settings
        s.setValue("resize/how", key)
        s.setValue("resize/percent", pct)
        s.setValue("resize/w", self.cw.value())
        s.setValue("resize/h", self.ch.value())
        s.setValue("resize/enlarge", enlarge)
        s.setValue("resize/replace", self.replace.isChecked())


def label_for(key, box, pct):
    if key == "percent":
        return f"{pct}%"
    if key == "custom":
        return f"{box[0]}x{box[1]}"
    return next(label for k, label, _, _ in SIZES if k == key)


def resize_files(paths, settings, quality=95, parent=None):
    """Resize pictures (from Explorer's right-click menu, or ☰ > Resize pictures). Returns the files written."""
    dlg = ResizeDialog(paths, settings, parent)
    if not dlg.exec():
        return []
    dlg.remember()
    key, pct, box, enlarge = dlg.choice()
    replace = dlg.replace.isChecked()
    progress = QProgressDialog("Resizing pictures…", "Stop", 0, len(paths), parent)
    progress.setWindowModality(Qt.WindowModal)
    progress.setWindowTitle("Resize pictures")
    progress.setMinimumDuration(400)
    made, failed, same, before, after = [], [], 0, 0, 0
    for n, p in enumerate(paths):
        progress.setValue(n)
        if progress.wasCanceled():
            break
        try:
            r = QImageReader(p)
            r.setAutoTransform(True)
            img = r.read()
            if img.isNull():
                raise RuntimeError(r.errorString())
            new = target(img.size(), "percent" if key == "percent" else "box", pct, box, enlarge)
            if new == img.size():  # already that size (or smaller)
                same += 1
                continue
            img = img.scaled(new, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            ext = out_ext(p)
            data = encode(img, ext, quality)
            base = os.path.splitext(p)[0]
            if replace and ext == os.path.splitext(p)[1].lower():
                dst = p
            else:
                dst = free_path(base + ("" if replace else f" ({label_for(key, box, pct)})") + ext)
            tmp = dst + ".resizing"
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, dst)
            if replace and dst != p:
                os.remove(p)
            before += dlg.bytes[p]
            after += len(data)
            made.append(dst)
        except Exception as e:
            failed.append(f"{os.path.basename(p)}: {e}")
    progress.setValue(len(paths))
    text = (f"Resized {len(made)} picture{'s' if len(made) != 1 else ''}: {human(before)} → {human(after)}."
            if made else "No pictures were resized.")
    if same:
        text += (f"\n\n{same} picture{'s were' if same != 1 else ' was'} already that size or smaller and "
                 "left as it is." if same == 1 else
                 f"\n\n{same} pictures were already that size or smaller and left as they are.")
    if failed:
        text += "\n\nThese couldn't be resized:\n" + "\n".join(failed)
    (QMessageBox.warning if failed else QMessageBox.information)(parent, APP_NAME, text)
    return made
