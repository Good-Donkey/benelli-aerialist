"""The stamps on the Fill & Sign and Edit toolbars: a few favourites (check mark and X to start
with) right on the bar, grouped with the Stamps menu that has the rest. The menu's last item
opens a small window to choose the favourites and add your own stamp pictures."""
import os

from PySide6.QtCore import Qt, Signal, QObject, QSize
from PySide6.QtGui import QIcon, QPixmap, QPainter
from PySide6.QtWidgets import (
    QWidget, QFrame, QHBoxLayout, QVBoxLayout, QToolButton, QMenu, QListWidget, QListWidgetItem, QPushButton,
    QLabel, QFileDialog, QMessageBox, QInputDialog, QSizePolicy, QWidgetAction,
)

from . import stamps
from .chrome import tool_button
from .organizer import IMAGE_EXTS
from .popups import APP_NAME, ask


class _Hub(QObject):
    changed = Signal()  # favourites or your own stamps changed: every stamp bar redraws


hub = _Hub()


def stamp_icon(key, w=44, h=22):
    pix = QPixmap.fromImage(stamps.stamp_image(key)).scaled(QSize(w * 2, h * 2), Qt.KeepAspectRatio,
                                                             Qt.SmoothTransformation)
    pix.setDevicePixelRatio(2)
    return QIcon(pix)


def boxed_icon(key, w=76, h=26):
    """The stamp fitted and centred in a w x h box: a check mark and a long rubber stamp take the same room."""
    img = stamps.stamp_image(key)
    pix = QPixmap(w * 2, h * 2)
    pix.fill(Qt.transparent)
    fit = QPixmap.fromImage(img).scaled(QSize(w * 2, h * 2), Qt.KeepAspectRatio, Qt.SmoothTransformation)
    p = QPainter(pix)
    p.drawPixmap((pix.width() - fit.width()) // 2, (pix.height() - fit.height()) // 2, fit)
    p.end()
    pix.setDevicePixelRatio(2)
    return QIcon(pix)


class StampGroup(QFrame):
    """Favourite stamps and the Stamps ▾ menu, on a shaded strip so they read as one group."""
    picked = Signal(str)  # stamp key

    def __init__(self):
        super().__init__()
        self.setObjectName("stampGroup")
        self.setFixedHeight(38)
        self.lay = QHBoxLayout(self)
        self.lay.setContentsMargins(3, 2, 3, 2)
        self.lay.setSpacing(1)
        self.quick_buttons = []
        self.menu_btn = tool_button("stamp", "Stamps")
        self.menu_btn.setPopupMode(QToolButton.InstantPopup)
        self.menu_btn.setProperty("dropdown", True)
        self.menu = QMenu(self.menu_btn)
        self.menu.aboutToShow.connect(self._fill_menu)
        self.menu_btn.setMenu(self.menu)
        self.lay.addWidget(self.menu_btn)
        self.show_quick = True
        self.refresh()
        hub.changed.connect(self.refresh)

    def refresh(self):
        for b in self.quick_buttons:
            b.deleteLater()
        self.quick_buttons = []
        for n, key in enumerate(stamps.quick()):
            # Smaller than the main tools and close together, after the Stamps button: shortcuts within it.
            b = QToolButton()
            b.setIcon(stamp_icon(key, 32, 16))
            b.setIconSize(QSize(16, 16) if key in ("check", "x") else QSize(32, 16))
            b.setProperty("mini", True)
            b.setToolTip(f"{stamps.label(key)} stamp")
            b.setProperty("key", key)
            b.setToolButtonStyle(Qt.ToolButtonIconOnly)
            b.setProperty("iconOnly", True)
            b.setCursor(Qt.PointingHandCursor)
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(lambda _=False, k=key: self.picked.emit(k))
            self.lay.insertWidget(n + 1, b)
            self.quick_buttons.append(b)
        self.set_show_quick(self.show_quick)

    def set_active(self, key):
        """Light up the stamp picked up (its own button, or the menu's), or none."""
        self.active = key
        target = next((b for b in self.quick_buttons if b.property("key") == key and b.isVisible()),
                      self.menu_btn if key else None)
        for b in self.quick_buttons + [self.menu_btn]:
            on = b is target
            if bool(b.property("toggleOn")) != on:
                b.setProperty("toggleOn", on)
                b.style().unpolish(b)
                b.style().polish(b)

    def set_show_quick(self, on):
        """The favourites go when the bar is short of room; the menu still has them."""
        self.show_quick = on
        for b in self.quick_buttons:
            b.setVisible(on)
        self.setProperty("grouped", bool(on and self.quick_buttons))
        self.style().unpolish(self)
        self.style().polish(self)
        self.set_active(getattr(self, "active", None))

    def _fill_menu(self):
        self.menu.clear()
        for key, label, _ in stamps.all_stamps():
            self.menu.addAction(self._row(key, label))
        self.menu.addSeparator()
        self.menu.addAction("Stamp settings…", self._settings)

    def _row(self, key, label):
        """A menu row: the stamp in a box of its own (so marks and wide rubber stamps line up), then its name."""
        b = QToolButton()
        b.setIcon(boxed_icon(key))
        b.setIconSize(QSize(76, 26))
        b.setText(label)
        b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        b.setCursor(Qt.PointingHandCursor)
        b.setObjectName("menuRow")
        b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        act = QWidgetAction(self.menu)
        act.setText(label)
        act.setDefaultWidget(b)
        act.triggered.connect(lambda: self.picked.emit(key))
        b.clicked.connect(lambda: (self.menu.close(), act.trigger()))
        return act

    def _settings(self):
        win = self.parentWidget()
        while win is not None and not hasattr(win, "open_settings"):  # the document this toolbar is in
            win = win.parentWidget()
        if win is not None:
            win.open_settings("stamps")


class StampSettings(QWidget):
    """Settings page: tick the stamps to keep on the toolbar; add or remove your own stamp pictures."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        note = QLabel("Ticked stamps sit on the toolbar, next to the Stamps menu.")
        note.setWordWrap(True)
        lay.addWidget(note)
        self.list = QListWidget()
        self.list.setIconSize(QSize(64, 26))
        self.list.itemChanged.connect(self._ticked)
        self.list.currentItemChanged.connect(lambda *_: self._update_buttons())
        lay.addWidget(self.list, 1)
        row = QHBoxLayout()
        add = QPushButton("Add your own stamp…")
        add.clicked.connect(self.add_stamp)
        self.rename_btn = QPushButton("Rename")
        self.rename_btn.clicked.connect(self.rename)
        self.remove_btn = QPushButton("Remove")
        self.remove_btn.clicked.connect(self.remove)
        row.addWidget(add)
        row.addWidget(self.rename_btn)
        row.addWidget(self.remove_btn)
        row.addStretch(1)
        lay.addLayout(row)
        self.fill()

    def fill(self, select=None):
        self.list.blockSignals(True)
        self.list.clear()
        on = stamps.quick()
        for key, label, _ in stamps.all_stamps():
            it = QListWidgetItem(boxed_icon(key, 64, 26), label + ("  (yours)" if stamps.is_custom(key) else ""))
            it.setData(Qt.UserRole, key)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if key in on else Qt.Unchecked)
            self.list.addItem(it)
            if key == select:
                self.list.setCurrentItem(it)
        self.list.blockSignals(False)
        self._update_buttons()

    def _key(self):
        it = self.list.currentItem()
        return it.data(Qt.UserRole) if it else None

    def _update_buttons(self):
        mine = bool(self._key()) and stamps.is_custom(self._key())
        self.rename_btn.setEnabled(mine)
        self.remove_btn.setEnabled(mine)

    def _ticked(self, item):
        keys = [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())
                if self.list.item(i).checkState() == Qt.Checked]
        stamps.set_quick(keys)
        hub.changed.emit()

    def add_stamp(self):
        from .overlay import read_image
        exts = " ".join("*" + e for e in IMAGE_EXTS)
        path, _ = QFileDialog.getOpenFileName(self, "Choose a picture for your stamp", "", f"Images ({exts})")
        if not path:
            return
        img = read_image(path, max_side=1200)
        if img is None:
            QMessageBox.warning(self, APP_NAME, f"Couldn't open the image:\n{path}")
            return
        if not img.hasAlphaChannel():
            if ask(self, "Make the picture's white background see-through?", "See-through", "Keep the background"):
                from .sign import remove_paper, crop_to_ink
                img = crop_to_ink(remove_paper(img), pad=4)
        name = os.path.splitext(os.path.basename(path))[0]
        key = stamps.add_custom(img, name)
        stamps.set_quick(stamps.quick() + [key])  # a new stamp starts on the toolbar
        hub.changed.emit()
        self.fill(select=key)

    def rename(self):
        key = self._key()
        if not key or not stamps.is_custom(key):
            return
        name, ok = QInputDialog.getText(self, "Rename stamp", "Name:", text=stamps.label(key))
        if ok and name.strip():
            for c in stamps.custom:
                if c["key"] == key:
                    c["label"] = name.strip()
            stamps._save_custom()
            hub.changed.emit()
            self.fill(select=key)

    def remove(self):
        key = self._key()
        if not key or not stamps.is_custom(key):
            return
        if ask(self, f"Remove the stamp \"{stamps.label(key)}\"?", "Remove"):
            stamps.remove_custom(key)
            hub.changed.emit()
            self.fill()


def quick_tools(group):
    """The choices of a drop-down tool shown beside it on the bar (none unless picked in Settings)."""
    from PySide6.QtCore import QSettings
    value = QSettings("Aerialist", "Aerialist").value(f"toolbar/quick/{group}", [])
    return [value] if isinstance(value, str) else list(value or [])


def set_quick_tools(group, tools):
    from PySide6.QtCore import QSettings
    QSettings("Aerialist", "Aerialist").setValue(f"toolbar/quick/{group}", list(tools))
    hub.changed.emit()


class ToolStrip(QFrame):
    """A drop-down tool with its favourite choices beside it, small, on the same shaded strip as the stamps."""

    def __init__(self, button, group, subs, pick):
        super().__init__()
        self.setObjectName("stampGroup")
        self.setFixedHeight(38)
        self.button, self.group, self.subs, self.pick = button, group, subs, pick
        self.lay = QHBoxLayout(self)
        self.lay.setContentsMargins(3, 2, 3, 2)
        self.lay.setSpacing(1)
        self.lay.addWidget(button)
        self.quick_buttons, self.show_quick, self.active = [], True, None
        self.refresh()
        hub.changed.connect(self.refresh)

    def refresh(self):
        from .icons import icon
        for b in self.quick_buttons:
            b.deleteLater()
        self.quick_buttons = []
        chosen = quick_tools(self.group)
        for tool, ic, label in self.subs:
            if tool not in chosen:
                continue
            b = QToolButton()
            b.setIcon(icon(ic, size=16))
            b.setIconSize(QSize(16, 16))
            b.setToolTip(label)
            b.setProperty("tool", tool)
            b.setProperty("mini", True)
            b.setToolButtonStyle(Qt.ToolButtonIconOnly)
            b.setCursor(Qt.PointingHandCursor)
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(lambda _=False, t=tool: self.pick(self.button, t))
            self.lay.addWidget(b)
            self.quick_buttons.append(b)
        self.set_show_quick(self.show_quick)

    def set_active(self, tool):
        self.active = tool
        for b in self.quick_buttons:
            on = b.property("tool") == tool
            if bool(b.property("toggleOn")) != on:
                b.setProperty("toggleOn", on)
                b.style().unpolish(b)
                b.style().polish(b)

    def set_show_quick(self, on):
        self.show_quick = on
        for b in self.quick_buttons:
            b.setVisible(on)
        self.setProperty("grouped", bool(on and self.quick_buttons))
        self.style().unpolish(self)
        self.style().polish(self)
        self.set_active(self.active)
