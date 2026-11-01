"""The Settings window (☰ menu > Settings, Ctrl+,): general options, saved signatures, and stamps."""
from PySide6.QtCore import Qt, QSize, QUrl
from PySide6.QtGui import QIcon, QPixmap, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (
    QDialog, QWidget, QHBoxLayout, QVBoxLayout, QListWidget, QListWidgetItem, QStackedWidget, QLabel,
    QPushButton, QRadioButton, QButtonGroup, QMessageBox, QScrollArea, QFrame, QLineEdit, QCheckBox, QKeySequenceEdit, QToolButton,
    QComboBox,
)

from .stamp_bar import StampSettings
from . import comments, shell, theme, version
from .popups import ask

PAGES = [("general", "General"), ("signatures", "Signatures"), ("stamps", "Toolbar & stamps"), ("keys", "Shortcuts")]


def _heading(text):
    h = QLabel(text)
    h.setObjectName("settingsHeading")
    h.setStyleSheet("font-size: 15px; font-weight: 600; margin-top: 4px;")
    return h


def _note(text):
    n = QLabel(text)
    n.setWordWrap(True)
    n.setObjectName("subtle")
    return n


class GeneralSettings(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        lay.addWidget(_heading("Page thumbnails"))
        lay.addWidget(_note("The small pictures of the pages down the left side (Ctrl+B shows or hides them)."))
        self.thumbs = QButtonGroup(self)
        choice = win.settings.value("sidebar")
        choice = None if choice is None else str(choice).lower() == "true"
        for value, text in ((None, "Automatic: show them for files with more than one page"),
                            (True, "Always show them"), (False, "Never show them")):
            r = QRadioButton(text)
            r.setChecked(choice is value)
            r.toggled.connect(lambda on, v=value: on and self._set_thumbs(v))
            self.thumbs.addButton(r)
            lay.addWidget(r)

        lay.addSpacing(10)
        lay.addWidget(_heading("Default PDF app"))
        lay.addWidget(_note("Open PDFs in Benelli Aerialist when you double-click them in File Explorer."))
        default = QPushButton("Make it the default PDF app…")
        default.clicked.connect(win.act_default.trigger)
        lay.addWidget(default, 0, Qt.AlignLeft)

        lay.addSpacing(10)
        lay.addWidget(_heading("Your name on comments"))
        lay.addWidget(_note("Shown with each comment you add, here and in Adobe or Nitro."))
        self.name = QLineEdit(str(win.settings.value("comments/author", "") or ""))
        self.name.setPlaceholderText(comments.author(win.settings))
        self.name.setMaximumWidth(280)
        self.name.textChanged.connect(lambda t: win.settings.setValue("comments/author", t.strip()))
        lay.addWidget(self.name)

        lay.addSpacing(10)
        lay.addWidget(_heading("Converting"))
        lay.addWidget(_note("Used by Convert in File Explorer's right-click menu."))
        for key, label, choices, default in (
                ("convert/dpi", "Pages saved as pictures", [(f"{d} dpi" + (" (best)" if d == 300 else ""), d)
                                                            for d in shell.DPIS], shell.DPI),
                ("convert/jpg_quality", "JPG quality", [(f"{q}%" + (" (best)" if q == 95 else ""), q)
                                                        for q in shell.JPG_QUALITIES], shell.JPG_QUALITY)):
            row = QHBoxLayout()
            caption = QLabel(label)
            caption.setFixedWidth(150)
            row.addWidget(caption)
            box = QComboBox()
            for text, value in choices:
                box.addItem(text, value)
            box.setCurrentIndex(max(0, box.findData(int(win.settings.value(key, default)))))
            box.activated.connect(lambda i, b=box, k=key: win.settings.setValue(k, b.itemData(i)))
            box.setFixedWidth(130)
            row.addWidget(box)
            row.addStretch(1)
            lay.addLayout(row)

        lay.addSpacing(10)
        lay.addWidget(_heading("Tidy up"))
        row = QHBoxLayout()
        tips = QPushButton("Show tool hints again")
        tips.setToolTip("The short hints that show the first couple of times you pick a tool")
        tips.clicked.connect(self._reset_tips)
        recent = QPushButton("Clear recent files")
        recent.clicked.connect(self._clear_recent)
        row.addWidget(tips)
        row.addWidget(recent)
        row.addStretch(1)
        lay.addLayout(row)

        lay.addSpacing(10)
        lay.addWidget(_heading("About"))
        about = QLabel(f"Benelli Aerialist<br>{version.describe()}")
        about.setTextInteractionFlags(Qt.TextSelectableByMouse)
        if version.COMMIT:
            about.setToolTip(f"Build {version.COMMIT}")
        lay.addWidget(about)
        licence = QLabel(f'Free software under the GNU AGPL-3.0, with no warranty. '
                         f'<a href="{version.SOURCE_URL}">Source code and licences</a>')
        licence.setOpenExternalLinks(True)
        licence.setWordWrap(True)
        lay.addWidget(licence)
        lay.addWidget(_note("The download page shows the newest version number. If it's higher than yours, "
                            "download it and run it to update; your settings and signatures are kept."))
        updates = QPushButton("Check for updates…")
        updates.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(version.UPDATES_URL)))
        lay.addWidget(updates, 0, Qt.AlignLeft)
        lay.addStretch(1)

    def _set_thumbs(self, value):
        s = self.win.settings
        if value is None:
            s.remove("sidebar")
        else:
            s.setValue("sidebar", value)
        if self.win.mode != "pages":
            self.win._apply_mode_ui()
            self.win._update_enabled()

    def _reset_tips(self):
        s = self.win.settings
        s.beginGroup("tips")
        s.remove("")
        s.endGroup()
        self.win.toast.show_message("Tool hints will show again.")

    def _clear_recent(self):
        self.win._clear_recent()
        self.win.toast.show_message("Recent files cleared.")


class SignatureSettings(QWidget):
    """The saved people, with their signature and initials: add, change or delete."""

    def __init__(self, win):
        super().__init__()
        self.tools = win.sign_tools
        self.store = self.tools.store
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(_note("Saved signatures and initials, ready to place from Fill & Sign."))
        self.list = QListWidget()
        self.list.setIconSize(QSize(150, 40))
        self.list.itemDoubleClicked.connect(lambda *_: self.change())
        self.list.currentItemChanged.connect(lambda *_: self._update_buttons())
        lay.addWidget(self.list, 1)
        row = QHBoxLayout()
        add = QPushButton("Add a person…")
        add.clicked.connect(self.add)
        self.change_btn = QPushButton("Change…")
        self.change_btn.clicked.connect(self.change)
        self.delete_btn = QPushButton("Delete")
        self.delete_btn.clicked.connect(self.delete)
        for b in (add, self.change_btn, self.delete_btn):
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        self.fill()

    def fill(self, select=None):
        self.list.clear()
        for person in self.store.people:
            img = self.store.image(person, "signature") or self.store.image(person, "initials")
            it = QListWidgetItem(person["name"])
            if img is not None:
                from .sign import on_paper
                it.setIcon(QIcon(on_paper(img, QSize(150, 40))))
            it.setData(Qt.UserRole, person["id"])
            self.list.addItem(it)
            if person["id"] == select:
                self.list.setCurrentItem(it)
        if not self.store.people:
            empty = QListWidgetItem("No signatures saved yet. Click “Add a person…” to save one.")
            empty.setFlags(Qt.NoItemFlags)
            self.list.addItem(empty)
        self._update_buttons()

    def _person(self):
        it = self.list.currentItem()
        pid = it.data(Qt.UserRole) if it else None
        return next((p for p in self.store.people if p["id"] == pid), None)

    def _update_buttons(self):
        on = self._person() is not None
        self.change_btn.setEnabled(on)
        self.delete_btn.setEnabled(on)

    def add(self):
        before = {p["id"] for p in self.store.people}
        self.tools.add_person()
        new = next((p["id"] for p in self.store.people if p["id"] not in before), None)
        self.fill(select=new)

    def change(self):
        person = self._person()
        if person:
            self.tools.edit_person(person)
            self.fill(select=person["id"])

    def delete(self):
        person = self._person()
        if person:
            self.tools.delete_person(person)
            self.fill()


class ToolbarSettings(QWidget):
    """Toolbar & stamps page, top half: tool names, and which drop-down choices also sit on the bar."""

    def __init__(self, win):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        words = QCheckBox("Show names next to the tool icons")
        words.setToolTip("When the window is too narrow they're hidden anyway; hover a tool to see its name.")
        words.setChecked(str(win.settings.value("toolbar/words", True)).lower() != "false")
        words.toggled.connect(lambda on: (win.settings.setValue("toolbar/words", on), win.top._fit()))
        lay.addWidget(words)
        lay.addWidget(_note("Edit: show these choices as small buttons beside their tool, like the favourite "
                            "stamps below (they're hidden when the bar is short of room):"))
        from .edit import TOOL_GROUPS
        from .stamp_bar import quick_tools, set_quick_tools
        for key, _, label, subs in TOOL_GROUPS:
            if not subs:
                continue
            row = QHBoxLayout()
            row.setSpacing(12)
            name = QLabel(label)
            name.setFixedWidth(80)
            row.addWidget(name)
            for tool, _, sub_label in subs:
                box = QCheckBox(sub_label)
                box.setChecked(tool in quick_tools(key))

                def toggled(on, key=key, tool=tool):
                    chosen = [t for t in quick_tools(key) if t != tool] + ([tool] if on else [])
                    order = [t for t, _, _ in next(g[3] for g in TOOL_GROUPS if g[0] == key)]
                    set_quick_tools(key, sorted(chosen, key=order.index))
                    win.top._fit()
                box.toggled.connect(toggled)
                row.addWidget(box)
            row.addStretch(1)
            lay.addLayout(row)



class KeySettings(QWidget):
    """Keyboard shortcuts: click a box and press the keys; × clears it."""

    def __init__(self, win):
        super().__init__()
        self.win = win
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lay.addWidget(_note("Click a box and press the keys you want. If the key is already used by something "
                            "else, you're asked before it moves. Tools and stamps with a key open their mode if "
                            "need be."))
        self.edits = {}
        group = None
        for key, grp, action, default in win.key_actions:
            if grp != group:
                group = grp
                lay.addSpacing(8)
                lay.addWidget(_heading(grp))
            row = QHBoxLayout()
            name = QLabel(action.text().replace("&&", "&"))
            name.setFixedWidth(200)
            row.addWidget(name)
            edit = QKeySequenceEdit(action.shortcut())
            edit.setMaximumSequenceLength(1) if hasattr(edit, "setMaximumSequenceLength") else None
            edit.setFixedWidth(160)
            edit.editingFinished.connect(lambda k=key, e=edit: self._set(k, e.keySequence(), e))
            row.addWidget(edit)
            clear = QToolButton(text="×")
            clear.setToolTip("No shortcut")
            clear.setAutoRaise(True)
            clear.clicked.connect(lambda _=False, k=key, e=edit: (e.clear(), self._set(k, QKeySequence())))
            row.addWidget(clear)
            row.addStretch(1)
            lay.addLayout(row)
            self.edits[key] = edit
        lay.addSpacing(10)
        reset = QPushButton("Put back the usual shortcuts")
        reset.clicked.connect(self._reset)
        lay.addWidget(reset, 0, Qt.AlignLeft)
        lay.addStretch(1)

    def _set(self, key, seq, edit=None):
        text = seq.toString()
        s = self.win.settings
        mine = next(a for k, _, a, _ in self.win.key_actions if k == key)
        if text == mine.shortcut().toString():
            return
        if text:  # one action per key: say which one has it, and only move it if that's OK
            for other, group, action, _ in self.win.key_actions:
                if other != key and action.shortcut().toString() == text:
                    shown = seq.toString(QKeySequence.NativeText)
                    name = action.text().replace("&&", "&")
                    use = ask(
                        self,
                        f"{shown} is already the shortcut for {name}{'' if group == 'General' else f' ({group})'}.\n\nUse it for "
                        f"{mine.text().replace('&&', '&')} instead? {name} will then have no shortcut.", "Use it here")
                    if not use:
                        if edit is not None:
                            edit.setKeySequence(mine.shortcut())  # put back what it was
                        return
                    s.setValue(f"keys/{other}", "")
                    self.edits[other].clear()
        s.setValue(f"keys/{key}", text)
        self.win.apply_keys()

    def _reset(self):
        s = self.win.settings
        s.beginGroup("keys")
        s.remove("")
        s.endGroup()
        self.win.apply_keys()
        for key, _, action, _ in self.win.key_actions:
            self.edits[key].setKeySequence(action.shortcut())


class SettingsDialog(QDialog):
    def __init__(self, win, page="general"):
        super().__init__(win)
        self.setWindowTitle("Settings")
        self.resize(660, 640)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.nav = QListWidget()
        self.nav.setObjectName("settingsNav")
        self.nav.setFixedWidth(150)
        theme.style(self.nav, "#settingsNav {{ border: none; background: {NAV}; padding: 10px 6px; outline: none; }}"
                    "#settingsNav::item {{ padding: 8px 10px; border-radius: 6px; color: {TEXT}; }}"
                    "#settingsNav::item:selected {{ background: {TINT}; color: {ACCENT}; font-weight: 600; }}")

        self.stack = QStackedWidget()
        self.pages = {"general": GeneralSettings(win), "signatures": SignatureSettings(win),
                      "stamps": self._toolbar_page(win), "keys": KeySettings(win)}
        for key, title in PAGES:
            self.nav.addItem(title)
            box = QWidget()
            bl = QVBoxLayout(box)
            bl.setContentsMargins(22, 18, 22, 12)
            bl.addWidget(_heading(title))
            if key in ("general", "keys", "stamps"):  # the longest pages: scroll rather than squash it on a small screen
                scroll = QScrollArea()
                scroll.setWidgetResizable(True)
                scroll.setFrameShape(QFrame.NoFrame)
                scroll.setWidget(self.pages[key])
                bl.addWidget(scroll, 1)
            else:
                bl.addWidget(self.pages[key], 1)
            self.stack.addWidget(box)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.addWidget(self.stack, 1)
        row = QHBoxLayout()
        row.setContentsMargins(22, 0, 22, 16)
        row.addStretch(1)
        close = QPushButton("Close")
        close.setDefault(True)
        close.clicked.connect(self.accept)
        row.addWidget(close)
        right.addLayout(row)
        lay.addWidget(self.nav)
        lay.addLayout(right, 1)
        self.show_page(page)

    @staticmethod
    def _toolbar_page(win):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lay.addWidget(_heading("Toolbar"))
        lay.addWidget(ToolbarSettings(win))
        lay.addSpacing(10)
        lay.addWidget(_heading("Stamps"))
        lay.addWidget(StampSettings(), 1)
        return page

    def show_page(self, page):
        self.nav.setCurrentRow(next((n for n, (k, _) in enumerate(PAGES) if k == page), 0))
