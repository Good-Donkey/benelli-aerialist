"""Benelli Aerialist main window."""
import os
import shutil
import subprocess
import sys
import tempfile

import pymupdf
from PySide6.QtCore import Qt, QSize, QTimer, QSettings, QItemSelectionModel, QUrl
from PySide6.QtGui import QAction, QActionGroup, QKeySequence, QIcon, QPixmap, QCursor, QDoubleValidator, QImage, QImageReader, QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QMessageBox, QListWidgetItem, QSpinBox, QLabel,
    QStackedWidget, QMenu, QSplitter, QLineEdit, QTextEdit, QPlainTextEdit,
    QAbstractItemView, QComboBox, QToolButton, QWidget, QHBoxLayout,
)

from .organizer import PageGrid, PagesScreen, PreviewDialog, pdf_paths, IMAGE_EXTS
from .export import ExportDialog, export_pages, image_to_pdf
from .viewer import PageView
from .comments import CommentsPanel, Editor as CommentEditor
from .prepare import FormPrep
from .sign import SignTools, SignSession, SignatureStore
from .edit import EditTools, EditSession, HINTS, SIZES, TextItem, next_size, _letter_icon as letter_icon
from .overlay import apply_items
from .chrome import TopBar, BarTools, PagePill, SideTab, FindBar, MatchTicks, Toast, MiniBar, tool_button, separator
from .home import HomeScreen
from .snip import Snipper
from .textselect import Selector
from .features import FeaturesDialog
from .icons import icon
from .popups import APP_NAME, ask, cant_open, choose
from . import convert, fonts, default_app, pdfio, shell, stamps, textfix, theme, version

ICON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "icon.png")
THUMB_RENDER = 240  # thumbnails are drawn once at this width and scaled for the sidebar or the Pages grid
MAX_UNDO = 30
SIDEBAR_MAX = 480
MODE_TITLES = {"pages": "Organize & Merge", "edit": "Edit", "sign": "Fill & Sign", "form": "Prepare Form"}
SIGN_TIPS = {"signature": "Click on the page where the signature goes (or click and drag to the right to size it). "
                           "Ctrl+scroll resizes it before you click.",
             "initials": "Click on the page where the initials go. Ctrl+scroll resizes them before you click.",
             "date": "Click on the page where the date goes. Ctrl+scroll changes its size. Double-click it later to "
                     "change it.",
             "text": "Click on the page and type. Ctrl+scroll changes the text size. Click outside the box when done.",
             "stamp": "Click on the page where the stamp goes (or click and drag to the right to size it). "
                      "Ctrl+scroll resizes it before you click."}
PAGES_TIP = ("Drag pages to re-order. Select pages to rotate, delete or save them as a new PDF. "
             "Double-click a page for a closer look.")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.doc = None
        self.path = None
        self.settings = QSettings("Aerialist", "Aerialist")
        self.selftest = "--selftest" in sys.argv
        self.setWindowTitle(APP_NAME)
        self.resize(1200, 850)
        self.setAcceptDrops(True)
        # Tool names show on hover even when another window has the focus (Windows otherwise hides them).
        self.setAttribute(Qt.WA_AlwaysShowToolTips)
        self.mode = "read"  # "read"; "pages"; "edit" / "sign" (things placed on pages until Done); "form"

        self.top = TopBar()
        self.setMenuWidget(self.top)
        self.view = PageView()
        self.view.current_page_changed.connect(self._on_page_changed)
        self.view.zoom_changed.connect(self._on_zoom_changed)
        self.view.thumb_ready.connect(self._on_thumb_ready)

        # Page thumbnails: a resizable sidebar while reading, the full-window grid in Pages.
        self.thumbs = PageGrid()
        self.thumbs.currentRowChanged.connect(self._on_thumb_clicked)
        self.thumbs.reordered.connect(self._reorder)
        self.thumbs.files_dropped.connect(self.insert_files)
        self.thumbs.browse.connect(self.add_pdfs_dialog)
        self.thumbs.itemDoubleClicked.connect(self._thumb_double_clicked)
        self.thumbs.itemSelectionChanged.connect(self._selection_changed)
        self.thumbs.setContextMenuPolicy(Qt.CustomContextMenu)
        self.thumbs.customContextMenuRequested.connect(self._thumb_menu)
        self.thumbs.setMinimumWidth(80)
        self.thumbs.setMaximumWidth(SIDEBAR_MAX)
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setHandleWidth(4)
        self.splitter.addWidget(self.thumbs)
        # The pages, with the comments list beside them on the right when it's open.
        self.reading = QWidget()
        rl = QHBoxLayout(self.reading)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        rl.addWidget(self.view, 1)
        self.comments = CommentsPanel(self)
        self.comments.hide()
        self.comments.closed.connect(lambda: self.toggle_comments(False))
        rl.addWidget(self.comments)
        self.prep = FormPrep(self)  # Prepare Form's list of fields and their settings
        self.prep.hide()
        rl.addWidget(self.prep)
        self.view.annot_clicked.connect(self._annot_clicked)
        self.splitter.addWidget(self.reading)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, False)
        self.splitter.setSizes([self._sidebar_width(), 1000])
        self.splitter.splitterMoved.connect(lambda *_: self._sidebar_timer.start())
        self._sidebar_timer = QTimer(self, singleShot=True, interval=60)
        self._sidebar_timer.timeout.connect(self._fit_sidebar)

        self.home = HomeScreen(ICON_PATH)
        self.home.show_features.connect(lambda: self.show_features())
        self.pages_screen = PagesScreen()
        self.pages_screen.size_changed.connect(self._set_grid_size)
        self.stack = QStackedWidget()
        for w in (self.home, self.splitter, self.pages_screen):
            self.stack.addWidget(w)
        self.setCentralWidget(self.stack)

        # Floating over the pages.
        self.pill = PagePill(self.view)
        self.side_tab = SideTab(self.view)
        self.side_tab.clicked.connect(self.toggle_sidebar)
        self.pill.go_page.connect(lambda i: self.doc and self.view.go_to_page(max(0, min(i, len(self.doc) - 1))))
        self.pill.prev_page.connect(lambda: self.view.go_to_page(self.view.current_page() - 1))
        self.pill.next_page.connect(lambda: self.view.go_to_page(self.view.current_page() + 1))
        self.pill.zoom_in.connect(lambda: self.view.set_zoom(self.view.zoom * 1.25))
        self.pill.zoom_out.connect(lambda: self.view.set_zoom(self.view.zoom / 1.25))
        self.pill.zoom_preset.connect(self._on_zoom_text)
        self.find_bar = FindBar(self.view)
        self.find_bar.box.returnPressed.connect(self._on_find_enter)
        self.find_bar.box.textChanged.connect(self._on_find_text)
        self.find_bar.prev_btn.clicked.connect(lambda: self.find_step(-1))
        self.find_bar.next_btn.clicked.connect(lambda: self.find_step(1))
        self.find_bar.prev_page_btn.clicked.connect(lambda: self.find_page_step(-1))
        self.find_bar.next_page_btn.clicked.connect(lambda: self.find_page_step(1))
        self.find_bar.closed.connect(self._find_closed)
        self._find_timer = QTimer(self, singleShot=True, interval=350)  # search as you type
        self._find_timer.timeout.connect(lambda: self.find_step(1))
        self.ticks = MatchTicks(self.view)
        self.toast = Toast(self)
        self.snipper = Snipper(self)
        self.selector = self.view.selector = Selector(self)

        self.password = None
        self.save_password = None
        self.hits, self.hit_index, self.hit_query = [], -1, ""
        self.thumb_raw = []  # undecorated thumbnail per page (None until drawn)
        self._thumb_sizes = {}  # (page, width, height) -> (thumbnail it came from, that thumbnail scaled)
        self.undo_stack, self.redo_stack = [], []
        self.cur_bytes = None  # the document as last loaded/edited
        self.dirty = False
        self.workdir = tempfile.mkdtemp(prefix="aerialist-")
        self._work_n = 0
        self._ws_entry, self._ws_changed = None, False
        self._grid_size = int(self.settings.value("grid_size", 2))

        self._build_actions()
        self._build_modes()
        self._connect_top()
        self.home.open_clicked.connect(self.open_dialog)
        self.home.combine.connect(self.combine_pdfs)
        self.home.pictures.connect(self.convert)
        self.home.fill_sign.connect(self.open_to_sign)
        self.home.open_path.connect(self.open_file)
        self.home.clear_recent.connect(self._clear_recent)
        self.home.make_default.connect(self._make_default)
        self.home.not_now.connect(self._not_now)
        self._refresh_recent()
        self._apply_mode_ui()
        self._update_enabled()

    # ---- UI setup -------------------------------------------------------
    def _build_actions(self):
        self.key_actions = []  # (id, group, action, default keys): the ones in Settings > Shortcuts
        self.tool_actions = {}  # (group, tool) -> its shortcut's action

        def act(text, slot, shortcut=None, group="General"):
            a = QAction(text, self)
            a.triggered.connect(slot)
            if shortcut:
                a.setShortcut(shortcut)
            self.addAction(a)  # shortcuts work without a menu bar
            key = "".join(c for c in text.replace("&&", "and").replace("…", "") if c.isalnum() or c == " ")
            self.key_actions.append((group + "/" + key.strip().replace(" ", "_").lower(), group, a,
                                     a.shortcuts()))
            return a

        self.act_open = act("Open…", self.open_dialog, QKeySequence.Open)
        self.act_close = act("Close", self.close_document, QKeySequence.Close)
        self.act_quit = act("Exit", self.close, QKeySequence.Quit)
        self.act_prev = act("Previous page", lambda: self.view.go_to_page(self.view.current_page() - 1), "PgUp")
        self.act_next = act("Next page", lambda: self.view.go_to_page(self.view.current_page() + 1), "PgDown")
        self.act_first = act("First page", lambda: self.view.go_to_page(0), "Ctrl+Home")
        self.act_last = act("Last page", lambda: self.view.go_to_page(len(self.doc) - 1), "Ctrl+End")
        self.act_zoom_in = act("Zoom in", lambda: self.view.set_zoom(self.view.zoom * 1.25), QKeySequence.ZoomIn)
        self.act_zoom_out = act("Zoom out", lambda: self.view.set_zoom(self.view.zoom / 1.25), QKeySequence.ZoomOut)
        self.act_fit_width = act("Fit width", self.view.fit_width, "Ctrl+1")
        self.act_fit_page = act("Fit page", self.view.fit_page, "Ctrl+2")
        self.act_find = act("Find…", self.show_find, QKeySequence.Find)
        self.act_find_next = act("Find next", lambda: self.find_step(1), QKeySequence.FindNext)
        self.act_find_prev = act("Find previous", lambda: self.find_step(-1), QKeySequence.FindPrevious)
        self.act_sidebar = act("Page thumbnails", self.toggle_sidebar, "Ctrl+B")
        self.act_save = act("Save", self.save, QKeySequence.Save)
        self.act_save_as = act("Save as…", self.save_as, QKeySequence.SaveAs)
        self.act_combine = act("Merge PDFs…", self.combine_pdfs, "Ctrl+M")
        self.act_pages = act("Organize && Merge…", lambda: self.enter_pages(), "Ctrl+Shift+O")
        self.act_add_pdfs = act("Add PDFs or images…", self.add_pdfs_dialog)
        self.act_sign = act("Fill && Sign", lambda: self.enter_overlay("sign"), "Ctrl+Shift+G")
        self.act_edit_pdf = act("Edit", lambda: self.enter_overlay("edit"), "Ctrl+E")
        self.act_export_images = act("Save pages as images…", self.export_images, "Ctrl+Shift+E")
        self.act_images_to_pdf = act("Convert…", self.convert)
        self.act_resize = act("Resize pictures…", self.resize_pictures)
        self.act_undo = act("Undo", self.undo, QKeySequence.Undo)
        self.act_redo = act("Redo", self.redo, QKeySequence.Redo)
        self.act_rot_left = act("Rotate left", lambda: self.rotate_pages(-90), "Ctrl+Shift+L")
        self.act_rot_right = act("Rotate right", lambda: self.rotate_pages(90), "Ctrl+Shift+R")
        self.act_delete = act("Delete pages", self._delete, QKeySequence.Delete)
        self.act_move_up = act("Move pages earlier", lambda: self.move_pages(-1), "Ctrl+Up")
        self.act_move_down = act("Move pages later", lambda: self.move_pages(1), "Ctrl+Down")
        self.act_extract = act("Save selected pages as new PDF…", self.extract_pages)
        self.act_escape = act("Leave", self._escape, "Esc")
        self.act_settings = act("Settings…", lambda: self.open_settings(), "Ctrl+,")
        self.act_default = act("Make default PDF app…",
                               lambda: default_app.ask(self, self.settings, APP_NAME, forced=True))
        self.act_comments = act("Comments", lambda: self.toggle_comments())
        self.act_snip = act("Snip", lambda: self.toggle_snip(), "Ctrl+Shift+X")
        self.act_copy = act("Copy chosen text or picture", lambda: self.selector.copy(), QKeySequence.Copy)
        self.act_features = act("What it can do…", lambda: self.show_features())
        self.act_show_folder = act("Show in File Explorer", lambda: self.show_in_folder())
        self.act_password = act("Password protect…", lambda: self.set_password())
        self.act_prepare = act("Prepare Form", lambda: self.enter_form(), "Ctrl+Shift+F")
        # Tools, for anyone who wants a key for them (none set at first).
        for tool, label in (("select", "Select"), ("move", "Move"), ("text", "Text"), ("image", "Image"),
                            ("rect", "Rectangle"), ("ellipse", "Ellipse"), ("line", "Line"), ("arrow", "Arrow"),
                            ("pen", "Pen"), ("marker", "Highlighter pen"), ("highlight", "Highlight"),
                            ("whiteout", "White-out box"), ("wpen", "White-out pen"), ("link", "Link")):
            self.tool_actions[("Edit", tool)] = act(label, lambda _=False, t=tool: self._hotkey_tool("edit", t),
                                                   group="Edit")
        for tool, label in (("signature", "Signature"), ("initials", "Initials"), ("date", "Date"),
                            ("text", "Text"), ("next", "Next field")):
            self.tool_actions[("Fill & Sign", tool)] = act(label, lambda _=False, t=tool: self._hotkey_tool("sign", t),
                                                   group="Fill & Sign")
        for tool, label in (("note", "Sticky note"), ("highlight", "Highlight text"),
                            ("underline", "Underline text"), ("strike", "Strike through text")):
            self.tool_actions[("Comments", tool)] = act(label, lambda _=False, t=tool: self._hotkey_tool("comments", t),
                                                   group="Comments")
        for tool, label in (("text", "Text box"), ("check", "Tick box")):
            self.tool_actions[("Prepare Form", tool)] = act(label, lambda _=False, t=tool: self._hotkey_tool("form", t),
                                                   group="Prepare Form")
        self.sync_stamp_keys()
        # Page edits only work inside the Pages mode, so a stray key can't change a PDF.
        self.page_actions = [self.act_rot_left, self.act_rot_right, self.act_delete, self.act_move_up,
                             self.act_move_down]
        self.doc_actions = self.page_actions + [
            self.act_save, self.act_save_as, self.act_find, self.act_find_next, self.act_find_prev, self.act_close,
            self.act_prev, self.act_next, self.act_first, self.act_last, self.act_zoom_in, self.act_zoom_out,
            self.act_fit_width, self.act_fit_page, self.act_extract, self.act_export_images, self.act_sidebar]

        # ☰ menu: files.
        m = QMenu(self)
        m.addAction(self.act_open)
        self.recent_menu = m.addMenu("Open recent")
        m.addSeparator()
        m.addAction(self.act_save)
        m.addAction(self.act_save_as)
        m.addAction(self.act_show_folder)
        m.addAction(self.act_password)
        m.addSeparator()
        m.addAction(self.act_combine)
        m.addAction(self.act_images_to_pdf)
        m.addAction(self.act_resize)
        m.addAction(self.act_prepare)
        m.addAction(self.act_export_images)
        m.addSeparator()
        look = m.addMenu("Dark/Light Mode")
        group = QActionGroup(self)
        self.theme_actions = {}
        for mode, label in (("auto", "Match Windows"), ("light", "Light"), ("dark", "Dark")):
            a = look.addAction(label, lambda md=mode: self.set_theme(md))
            a.setCheckable(True)
            a.setChecked(mode == theme.MODE)
            group.addAction(a)
            self.theme_actions[mode] = a
        m.addAction(self.act_settings)
        m.addAction(self.act_features)
        m.addSeparator()
        m.addAction(self.act_close)
        m.addAction(self.act_quit)
        self.top.menu_btn.setMenu(m)
        # ⋯ menu: viewing.
        more = QMenu(self)
        for a in (self.act_zoom_in, self.act_zoom_out, self.act_fit_width, self.act_fit_page, None,
                  self.act_first, self.act_last, None, self.act_find_next, self.act_find_prev, None,
                  self.act_sidebar, None, self.act_extract):
            more.addAction(a) if a else more.addSeparator()
        self.top.more_btn.setMenu(more)

    def set_theme(self, mode):
        """☰ > Dark/Light Mode: light, dark, or the same as Windows (the usual)."""
        self.settings.setValue("theme", mode)
        theme.set_mode(mode)
        self.theme_actions[mode].setChecked(True)
        self.update()

    def sync_stamp_keys(self):
        """A shortcut for each stamp, your own ones included (kept up to date as stamps are added or removed)."""
        have = {key: entry for key, entry in ((e[0], e) for e in self.key_actions) if key.startswith("Stamps/")}
        wanted = {f"Stamps/{k}": (k, label) for k, label, _ in stamps.all_stamps()}
        for key, entry in have.items():
            if key not in wanted:
                self.removeAction(entry[2])
                self.key_actions.remove(entry)
        for key, (stamp, label) in wanted.items():
            if key not in have:
                a = QAction(label + " stamp", self)
                a.triggered.connect(lambda _=False, k=stamp: self._hotkey_stamp(k))
                self.addAction(a)
                self.key_actions.append((key, "Stamps", a, []))
        self.apply_keys()

    def _hotkey_stamp(self, key):
        """A stamp's shortcut: pick it up in Fill & Sign, or in Edit (opening Edit from reading)."""
        if not self.doc:
            return
        if self.mode == "read":
            self.enter_overlay("edit")
        if self.mode == "edit":
            self.edit_tools._pick_stamp(key)
        elif self.mode == "sign":
            self.sign_tools.stamp_group.picked.emit(key)

    def apply_keys(self):
        """Shortcuts: the ones changed in Settings, else the usual ones."""
        for key, _, a, default in self.key_actions:
            mine = self.settings.value(f"keys/{key}")
            if mine is None:
                a.setShortcuts(default)
            else:
                a.setShortcut(QKeySequence(str(mine)))
        self._tool_tips()

    def _tool_tips(self):
        """Hovering a tool shows its name, and its key if it has one."""
        if not hasattr(self, "form_buttons"):
            return  # (the tools aren't made yet)
        buttons = {("Edit", t): b for t, b in self.edit_tools.buttons.items() if self.edit_tools.group_of.get(t) == t}
        buttons.update({("Prepare Form", t): b for t, b in self.form_buttons.items()})
        buttons.update({("Comments", t): b for t, b in self.comments.tool_buttons.items()})
        buttons.update({("Fill & Sign", "signature"): self.sign_tools.sig_btn,
                        ("Fill & Sign", "initials"): self.sign_tools.ini_btn,
                        ("Fill & Sign", "next"): self.sign_tools.next_btn})
        for key, b in buttons.items():
            a = self.tool_actions.get(key)
            if a is None:
                continue
            keys = a.shortcut().toString(QKeySequence.NativeText)
            b.setToolTip(a.text() + (f" ({keys})" if keys else ""))

    def _hotkey_tool(self, where, tool):
        """A shortcut for a tool: opens its mode first if need be (from reading)."""
        if not self.doc:
            return
        if where == "comments":
            if self.mode != "read":
                return
            self.toggle_comments(True)
            self.comments.pick(tool)
            return
        if where == "form":
            if self.mode == "read":
                self.enter_form()
            if self.mode == "form":
                self.prep.pick(tool)
            return
        if self.mode != where:
            if self.mode != "read":
                return
            self.enter_overlay(where)
        if where == "edit":
            t = self.edit_tools
            group = t.group_of.get(tool)
            b = t.buttons.get(tool)
            if b is not None and group != tool:
                t._pick_sub(b, tool)
            else:
                t._pick_tool(tool)
        else:
            s = self.sign_tools
            if tool in ("signature", "initials"):
                (s.sig_btn if tool == "signature" else s.ini_btn).showMenu()
            elif tool == "next":
                s.next_btn.click()
            else:
                s.pick.emit(tool, tool, QImage())

    def _build_modes(self):
        # Pages mode tools.
        pt = BarTools()
        add = pt.add(tool_button("plus", "Add files"))
        add.clicked.connect(self.add_pdfs_dialog)
        self.sel_sep = pt.add(separator())
        self.sel_chip = pt.add(QLabel())
        self.sel_chip.setObjectName("chip")
        self.sel_chip.setFixedHeight(24)
        self.sel_buttons = []
        for name, text, tip, a in (("rot_left", "", "Rotate left (Ctrl+Shift+L)", self.act_rot_left),
                                   ("rot_right", "", "Rotate right (Ctrl+Shift+R)", self.act_rot_right),
                                   ("delete", "", "Delete (Del)", self.act_delete),
                                   ("save_copy", "Save as new PDF", "Save as new PDF",
                                    self.act_extract)):
            b = pt.add(tool_button(name, text, tip))
            b.clicked.connect(a.trigger)
            self.sel_buttons.append(b)
        self.pages_tools = pt

        # Edit mode.
        self.edit_session = EditSession(self.view, self._overlay_changed)
        self.edit_tools = EditTools(self.edit_session, self.view, self._tool_tip)

        # Fill & Sign mode.
        self.sign_store = SignatureStore()
        self.sign_session = SignSession(self.view, self.sign_store, self._overlay_changed)
        self.sign_session.on_select = self._sign_selected
        self.sign_session.on_armed = lambda a: self.sign_tools.stamp_group.set_active(
            a[0] if a and a[1] == "stamp" else None)
        self.sign_tools = SignTools(self.sign_store)
        self.sign_tools.pick.connect(self._sign_pick)
        self.sign_tools.next_field.connect(self._next_field)
        self.sign_mini = MiniBar(self.view)
        self.sign_size = QComboBox()
        self.sign_size.setEditable(True)
        self.sign_size.addItems([str(n) for n in SIZES])
        self.sign_size.setMaxVisibleItems(len(SIZES))
        self.sign_size.setFixedWidth(64)
        self.sign_size.setValidator(QDoubleValidator(4, 400, 1, self.sign_size))
        self.sign_size.setEditText(str(self.sign_session.text_size()))
        self.sign_size.textActivated.connect(self._sign_size_typed)
        self.sign_size.lineEdit().editingFinished.connect(lambda: self._sign_size_typed(self.sign_size.currentText()))
        self.sign_size.setToolTip("Text size")
        self.sign_mini.lay.addWidget(self.sign_size)
        for step in (1, -1):  # bigger / smaller, as in Edit's text bar
            b = QToolButton(toolTip="Bigger text" if step > 0 else "Smaller text")
            b.setIcon(letter_icon("A", up=step > 0))
            b.setIconSize(QSize(22, 22))
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(lambda _=False, st=step: self._sign_size_step(st))
            self.sign_mini.lay.addWidget(b)

        self.overlays = {"sign": (self.sign_tools, self.sign_session), "edit": (self.edit_tools, self.edit_session)}
        QTimer.singleShot(0, self._tool_tips)

        # Prepare Form: its two tools in the top bar (the rest is in the panel beside the pages).
        ft = BarTools()
        self.form_buttons = {}
        for key, ic, label, tip in (("text", "textfield", "Text box", "Text box"),
                                    ("check", "checkbox", "Tick box", "Tick box")):
            b = ft.add(tool_button(ic, label, tip, checkable=True))
            b.clicked.connect(lambda on, k=key: self.prep.pick(k if on else None))
            self.form_buttons[key] = b
        self.form_tools = ft
        self.prep.on_tool = lambda kind: [b.setChecked(k == kind) for k, b in self.form_buttons.items()]
        # Edit's way in to it.
        self.edit_tools.add(separator())
        form_btn = self.edit_tools.add(tool_button("textfield", "Form fields"))
        form_btn.clicked.connect(self._edit_to_form)

    def _connect_top(self):
        t = self.top
        t.find_btn.clicked.connect(lambda on: self.show_find() if on else self.find_bar.close_bar())
        t.comments_btn.clicked.connect(self.toggle_comments)
        t.snip_btn.clicked.connect(self.toggle_snip)
        t.save_btn.clicked.connect(self.save)
        t.tab_clicked.connect(self._tab_clicked)
        t.cancel_btn.clicked.connect(self._cancel_mode)
        t.done_btn.clicked.connect(self._done_mode)
        t.undo_btn.clicked.connect(self.undo)
        t.redo_btn.clicked.connect(self.redo)

    def _tab_clicked(self, key):
        self.top.show_main()  # the tab only lights up once its mode is really open
        if key == "pages":
            self.enter_pages()
        elif key in self.overlays:
            self.enter_overlay(key)

    def _cancel_mode(self):
        if self.mode == "pages":
            self.cancel_pages()
        elif self.mode == "form":
            self.cancel_form()
        elif self.mode in self.overlays:
            self.cancel_overlay()

    def _done_mode(self):
        if self.mode == "pages":
            self.exit_pages()
        elif self.mode == "form":
            self.exit_form()
        elif self.mode in self.overlays:
            self.exit_overlay(apply=True)

    def _escape(self):
        focus = QApplication.focusWidget()
        if isinstance(focus, QPlainTextEdit) and isinstance(focus.parent(), CommentEditor):
            focus.parent().cancelled.emit()  # stop writing a comment
            return
        if isinstance(focus, (QLineEdit, QTextEdit, QPlainTextEdit)) and focus is not self.find_bar.box:
            focus.clearFocus()  # finishes typing (text on the page, a form field)
            return
        if self.find_bar.isVisible():
            self.find_bar.close_bar()
        elif self.mode == "read" and self.snipper.on:
            self.snipper.set_on(False)
        elif self.mode == "read" and self.selector.active():
            self.selector.clear()
        elif self.mode == "read" and self.comments.armed():
            self.comments.pick(None)
        elif self.mode == "form" and self.prep.armed():
            self.prep.put_down()
        elif self.mode in self.overlays and self.overlays[self.mode][1].armed_or_tool():
            self.overlays[self.mode][1].cancel_tool()
        elif self.mode != "read":
            self._cancel_mode()

    def _tool_tip(self, tool):
        """Show a tool's hint the first few times it is picked."""
        key = f"tips/{self.mode}/{tool}"
        n = int(self.settings.value(key, 0))
        text = HINTS.get(tool) if self.mode == "edit" else SIGN_TIPS.get(tool) if self.mode == "sign" else PAGES_TIP
        if text and n < 2 and not self.selftest:
            self.settings.setValue(key, n + 1)
            self.toast.show_message(text, 5000)

    def _update_enabled(self):
        has = self.doc is not None
        for a in self.doc_actions:
            a.setEnabled(has)
        reading = self.mode == "read"
        self.act_undo.setEnabled(has and bool(self.undo_stack))
        self.act_redo.setEnabled(has and bool(self.redo_stack))
        self.act_save.setEnabled(has and (self.dirty or self.path is None))
        self.act_show_folder.setEnabled(has and bool(self.path))
        self.act_password.setEnabled(has and self.mode == "read")
        for a in self.page_actions:
            a.setEnabled(has and self.mode == "pages")
        self.act_add_pdfs.setEnabled(self.mode == "pages")
        for a in (self.act_pages, self.act_sign, self.act_edit_pdf, self.act_prepare):
            a.setEnabled(has and reading)
        if self.mode == "form":  # Del deletes the selected field
            self.act_delete.setEnabled(has)
        for a in (self.act_combine, self.act_images_to_pdf, self.act_open, self.act_close):
            a.setEnabled(reading and (a is not self.act_close or has))
        if self.mode in self.overlays:  # Ctrl+Z takes back the last change on this screen
            self.act_undo.setEnabled(self.overlays[self.mode][1].can_undo())
            self.act_redo.setEnabled(self.overlays[self.mode][1].can_redo())
        self.top.undo_btn.setEnabled(self.act_undo.isEnabled())
        self.top.redo_btn.setEnabled(self.act_redo.isEnabled())
        self.top.done_btn.setEnabled(has or self.mode != "pages")
        name = (os.path.basename(self.path) if self.path else "Untitled") if has else ""
        self.top.set_document(name, self.dirty, has)
        # Save is usable whenever there is something to keep, including changes still on a mode's screen.
        unsaved = has and (self.dirty or (self.mode in self.overlays and self.overlays[self.mode][1].pending() > 0)
                            or (self.mode in ("pages", "form") and getattr(self, "_ws_changed", False)))
        self.act_save.setEnabled(has and (unsaved or self.path is None))
        self.top.save_btn.setEnabled(self.act_save.isEnabled())
        self.top.save_btn.setProperty("toggleOn", bool(unsaved))  # tinted green: there is something to save
        self.top.save_btn.style().unpolish(self.top.save_btn)
        self.top.save_btn.style().polish(self.top.save_btn)
        self.side_tab.set_open(self._sidebar_on())
        self.side_tab.setVisible(has and self.mode != "pages")
        self.top.comments_btn.setChecked(self.comments.isVisible())
        n = self.comments.count_comments() if self.comments.isVisible() else None
        self.top.comments_btn.setToolTip("Comments" + (f" ({n})" if n else ""))
        if self.mode == "pages":
            self._selection_changed()

    # ---- open / close ---------------------------------------------------
    def open_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open PDF", self._start_dir(), "PDF files (*.pdf);;All files (*)")
        if path:
            self.open_file(path)
        return bool(path)

    def open_to_sign(self):
        """Home's "Fill & sign a form": pick a PDF and go straight to Fill & Sign."""
        if self.open_dialog() and self.doc:
            self.enter_overlay("sign")

    def open_file(self, path):
        if self.mode != "read" or not self._confirm_discard():
            return
        password = None
        try:
            doc = pymupdf.open(path)
            if doc.needs_pass:
                password = self._ask_password(doc)
                if password is None:
                    return
        except Exception as e:
            cant_open(self, path, e)
            return
        self._show(doc, path, render_path=path, password=password)
        if not self.selftest:
            self.settings.setValue("last_dir", os.path.dirname(path))
            self._add_recent(path)

    def _show(self, doc, path, render_path, password=None, dirty=False):
        """Display a newly opened (or newly combined, unsaved) document."""
        self.close_document(confirm=False)
        self.doc, self.path, self.password = doc, path, password
        self.save_password = password  # what the saved file will ask for (☰ > Password protect… changes it)
        self.cur_bytes = None
        self.dirty = dirty
        self.view.set_document(doc, render_path, password)
        self._apply_mode_ui()
        self.thumb_raw = [None] * len(doc)
        self._load_thumbs()
        self._after_change()
        self._on_zoom_changed(self.view.zoom)
        self._on_page_changed(0)
        if self.comments.isVisible():
            self.comments.refresh()

    def _after_change(self):
        name = os.path.basename(self.path) if self.path else "Untitled"
        self.setWindowTitle(f"{'*' if self.dirty else ''}{name} - {APP_NAME}")
        self.pill.set_page(self.view.current_page(), len(self.doc))
        self._update_enabled()

    def set_password(self):
        """☰ > Password protect…: lock the PDF with a password, change it or take it off (from the next save)."""
        if not self.doc or self.mode != "read":
            return
        from .protect import PasswordDialog
        dlg = PasswordDialog(self, bool(self.save_password))
        if not dlg.exec() or dlg.result_password is None:
            return
        self.save_password = dlg.result_password or None
        self.dirty = True
        self._after_change()
        self.toast.show_message("Password set. Save (Ctrl+S) to lock the file with it." if self.save_password else
                                "Password removed. Save (Ctrl+S) to unlock the file.", 5000)

    def _ask_password(self, doc):
        from PySide6.QtWidgets import QInputDialog, QLineEdit
        while True:
            pw, ok = QInputDialog.getText(self, APP_NAME, "This PDF is password protected:", QLineEdit.Password)
            if not ok:
                return None
            if doc.authenticate(pw):
                return pw

    def close_document(self, confirm=True):
        if confirm and not self._confirm_discard():
            return False
        self._clear_find()
        self.find_bar.hide()
        self.comments.pick(None)
        self.comments.hide()
        self.snipper.set_on(False)
        self.selector.clear()
        self.thumbs.clear()
        self.thumbs.set_tile(self.mode == "pages")
        self.view.set_document(None)
        if self.doc:
            self.doc.close()
        self.doc = self.path = None
        self.dirty = False
        self.undo_stack, self.redo_stack = [], []
        self.setWindowTitle(APP_NAME)
        self._apply_mode_ui()
        self._update_enabled()
        return True

    # ---- which screen shows --------------------------------------------
    def _sidebar_on(self):
        """Thumbnails beside the pages: the user's choice, else on for documents of 2+ pages."""
        choice = self.settings.value("sidebar")
        if choice is None:
            return bool(self.doc) and len(self.doc) > 1
        return str(choice).lower() == "true"

    def _sidebar_width(self):
        try:
            return max(80, min(SIDEBAR_MAX, int(self.settings.value("sidebar_w3", 118))))
        except (TypeError, ValueError):
            return 118

    def toggle_sidebar(self):
        if not self.doc or self.mode == "pages":
            return
        self.settings.setValue("sidebar", not self._sidebar_on())
        self._apply_mode_ui()
        self._update_enabled()

    def _apply_mode_ui(self):
        """Show the right screen for the current mode and whether a document is open."""
        if self.mode != "read":
            self.snipper.set_on(False)
            self.selector.clear()
        if self.mode == "pages":
            self.stack.setCurrentWidget(self.pages_screen)
        elif self.doc:
            self.stack.setCurrentWidget(self.splitter)
            self.thumbs.setVisible(self._sidebar_on())
            self.pill.setVisible(True)
            self.pill.reposition()
            self._sidebar_timer.start()
        else:
            self.stack.setCurrentWidget(self.home)
            self._update_banner()

    def _fit_sidebar(self):
        """Thumbnail size follows the sidebar's width: one column, or two when it's wide."""
        if self.mode == "pages" or not self.thumbs.isVisible():
            return
        width = self.thumbs.viewport().width() - 6
        self.settings.setValue("sidebar_w3", self.thumbs.width())
        cols = 2 if width >= 200 else 1
        w = max(50, min(320, width // cols - 10))
        if w != self.thumbs.iconSize().width():
            self.thumbs.setIconSize(QSize(w, int(w * 1.4)))
            self._refresh_thumb_icons()

    def _set_grid_size(self, w):
        self._grid_size = self.pages_screen.SIZES.index(w)
        self.settings.setValue("grid_size", self._grid_size)
        self.thumbs.setIconSize(QSize(w, int(w * 1.4)))
        self._refresh_thumb_icons()

    # ---- Pages mode -----------------------------------------------------
    def enter_pages(self):
        if self.mode != "read":
            return
        # Remember how things were, so Cancel can put them back.
        self._ws_entry = None
        if self.doc:
            data = self.cur_bytes if self.cur_bytes is not None else pdfio.to_bytes(self.doc)
            self._ws_entry = (data, self.thumb_raw, self.view.current_page(), self.path, self.dirty,
                              list(self.undo_stack), list(self.redo_stack))
        self._ws_changed = False
        self._splitter_sizes = self.splitter.sizes()
        self._park_comments()
        self.mode = "pages"
        self.find_bar.close_bar()
        self.thumbs.set_editing(True, accept_files=True)
        self.thumbs.setMaximumWidth(16777215)
        self.pages_screen.attach(self.thumbs, self._grid_size)
        w = self.pages_screen.SIZES[self._grid_size]
        self.thumbs.setIconSize(QSize(w, int(w * 1.4)))
        self._refresh_thumb_icons()
        self.top.show_mode(MODE_TITLES["pages"], self.pages_tools)
        self._apply_mode_ui()
        self._update_enabled()
        self.thumbs.setFocus()
        if self.doc:
            QTimer.singleShot(0, lambda: self.thumbs.scrollToItem(self.thumbs.item(self.view.current_page()),
                                                                  QAbstractItemView.PositionAtCenter))
        self._tool_tip("pages")

    def exit_pages(self):
        self.mode = "read"
        self.pages_screen.detach()
        self.thumbs.set_editing(False)
        self.thumbs.setMaximumWidth(SIDEBAR_MAX)
        self.splitter.insertWidget(0, self.thumbs)
        sizes = getattr(self, "_splitter_sizes", None)
        if not sizes or sizes[0] < 80:
            sizes = [self._sidebar_width(), max(400, self.width() - 118)]
        self.splitter.setSizes(sizes)
        self.top.show_main()
        if self.doc:
            self._on_page_changed(self.view.current_page())
        self._unpark_comments()
        self._apply_mode_ui()
        self._update_enabled()

    def cancel_pages(self):
        if self._ws_changed and not self.selftest:
            if not ask(self, "Undo the changes made to the pages?", "Undo changes", "Keep editing"):
                return
        if self._ws_changed:
            if self._ws_entry is None:
                self.close_document(confirm=False)
            else:
                data, thumbs, page, path, dirty, undo, redo = self._ws_entry
                self._load_state(data, thumbs, page=page)
                self.path, self.dirty, self.undo_stack, self.redo_stack = path, dirty, undo, redo
                self._after_change()
        self.exit_pages()

    def _selection_changed(self):
        if self.mode != "pages":
            return
        n = len({i.row() for i in self.thumbs.selectedIndexes()})
        self.sel_chip.setText(f"{n} selected")
        for w in [self.sel_sep, self.sel_chip] + self.sel_buttons:
            w.setVisible(n > 0 and self.doc is not None)

    def _thumb_double_clicked(self, item):
        if item is self.thumbs.tile:
            return
        row = self.thumbs.row(item)
        if self.mode == "pages":
            PreviewDialog(self, self.doc, row).exec()
        else:
            self.view.go_to_page(row)

    # ---- Prepare Form ----------------------------------------------------
    def enter_form(self):
        if not self.doc or self.mode != "read":
            return
        # Changes go straight into the document; remember how it was, so Cancel can put it back.
        data = self.cur_bytes if self.cur_bytes is not None else pdfio.to_bytes(self.doc)
        self._ws_entry = (data, self.thumb_raw, self.view.current_page(), self.path, self.dirty,
                          list(self.undo_stack), list(self.redo_stack))
        self._ws_changed = False
        self._park_comments()
        self.mode = "form"
        self.find_bar.close_bar()
        self.top.show_mode(MODE_TITLES["form"], self.form_tools)
        self.prep.start()
        self._apply_mode_ui()
        self._update_enabled()
        QTimer.singleShot(0, self.pill.reposition)

    def exit_form(self):
        self.prep.stop()
        self.mode = "read"
        self.top.show_main()
        self._unpark_comments()
        self._apply_mode_ui()
        self._update_enabled()
        QTimer.singleShot(0, self.pill.reposition)

    def cancel_form(self):
        self.prep.flush()
        if self._ws_changed and not self.selftest:
            if not ask(self, "Undo the changes made to the form?", "Undo changes", "Keep editing"):
                return
        if self._ws_changed and self._ws_entry is not None:
            data, thumbs, page, path, dirty, undo, redo = self._ws_entry
            self._load_state(data, thumbs, page=page)
            self.path, self.dirty, self.undo_stack, self.redo_stack = path, dirty, undo, redo
            self._after_change()
        self.exit_form()

    def _edit_to_form(self):
        """Edit's Form fields button: keep what was done in Edit and go to Prepare Form."""
        self.exit_overlay(apply=True)
        self.enter_form()

    def _delete(self):
        if self.mode == "form":
            self.prep.delete_selected()
        else:
            self.delete_pages()

    # ---- Edit and Fill & Sign -------------------------------------------
    def enter_overlay(self, mode):
        if not self.doc or self.mode != "read":
            return
        self._park_comments()
        self.mode = mode
        tools, session = self.overlays[mode]
        self.find_bar.close_bar()
        session.start()
        self.top.show_mode(MODE_TITLES[mode], tools)
        if mode == "edit":
            self.edit_tools.setup()
        else:
            self.sign_tools.refresh()
            self._sign_count()
            if self.sign_session.form.fields and not self.selftest:
                self.toast.show_message(f"This PDF has {len(self.sign_session.form.fields)} form fields (green "
                                        "outlines): click one to fill it in. Tab goes to the next.", 5000)
        self._apply_mode_ui()
        self._update_enabled()

    def exit_overlay(self, apply=True):
        if apply:
            self._overlay_apply()
        self.overlays[self.mode][1].stop()
        self.edit_tools.hide_mini()
        self.sign_mini.hide()
        self.mode = "read"
        self.top.show_main()
        self._unpark_comments()
        self._apply_mode_ui()
        self._update_enabled()

    def cancel_overlay(self):
        n = self.overlays[self.mode][1].pending()
        if n and not self.selftest:
            if not ask(self, f"Throw away the {n} change{'s' if n != 1 else ''} made here?", "Throw away",
                       "Keep editing"):
                return
        self.exit_overlay(apply=False)

    def _sign_pick(self, key, kind, image):
        self.view.setFocus()  # out of the Find box, if it's open, so the page gets the clicks and keys
        self.sign_session.arm(key, kind, image)
        self._tool_tip(kind)
        if kind in ("text", "date"):
            self.sign_mini.follow(None)
        else:
            self.sign_mini.hide()

    def _sign_selected(self, item):
        if isinstance(item, TextItem):
            self.sign_size.blockSignals(True)
            self.sign_size.setEditText(f"{float(item.font_size):g}")
            self.sign_size.blockSignals(False)
            self.sign_mini.follow(self.edit_tools._anchor(item))
        elif self.sign_session.armed and self.sign_session.armed[1] in ("text", "date"):
            self.sign_size.blockSignals(True)
            self.sign_size.setEditText(f"{float(self.sign_session.text_size()):g}")
            self.sign_size.blockSignals(False)
        else:
            self.sign_mini.hide()

    def _sign_size_typed(self, text):
        try:
            v = float(text)
        except ValueError:
            return
        if 4 <= v <= 400:
            self.sign_session.set_text_size(v)

    def _sign_size_step(self, step):
        try:
            v = float(self.sign_size.currentText())
        except ValueError:
            v = self.sign_session.text_size()
        new = next_size(v, step)
        self.sign_size.setEditText(f"{new:g}")
        self.sign_session.set_text_size(float(new))

    def _next_field(self):
        if not self.sign_session.form.next_empty():
            self.toast.show_message("This PDF has no form fields.")

    def _sign_count(self):
        self.sign_tools.set_fields(*self.sign_session.form.counts())

    def _overlay_changed(self):
        if self.mode == "sign":
            self._sign_count()
        self._update_enabled()

    def _overlay_apply(self):
        """Write the placed items into the document (one Undo step)."""
        if self.mode not in self.overlays or not self.overlays[self.mode][1].pending():
            return
        session = self.overlays[self.mode][1]
        self.setFocus()  # finishes any text being typed
        specs = session.take()
        if not specs:
            return
        pages = {i for i, _ in specs}
        # Form values can show on other pages too (fields with the same name), so redraw all for those.
        mapping = [None if i in pages or self.mode == "sign" else i for i in range(len(self.doc))]
        self._edit(lambda doc: apply_items(doc, specs), mapping,
                   message=f"Added {len(specs)} change{'s' if len(specs) != 1 else ''} to {self._n(pages)}")
        session.stop()
        session.start()  # back on the redrawn pages (form fields show their new values)
        if self.mode == "sign":
            self._sign_count()

    # ---- files in and out -------------------------------------------------
    def add_pdfs_dialog(self):
        images = " ".join("*" + e for e in IMAGE_EXTS)
        other = " ".join("*" + e for e in convert.CONVERTIBLE)
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Choose files to add (hold Ctrl to pick several)", self._start_dir(),
            f"PDFs, images and documents (*.pdf {images} {other});;PDF files (*.pdf);;Images ({images});;"
            f"Word, Excel, PowerPoint and text ({other})")
        if paths:
            self.insert_files(paths, self.thumbs.pages() if self.doc else 0)

    def combine_pdfs(self):
        """Home's "Combine PDFs": an empty Pages screen to add files to."""
        if self.mode != "read" or not self._confirm_discard():
            return
        self.close_document(confirm=False)
        self.enter_pages()
        self.add_pdfs_dialog()

    def convert(self):
        """Home's "Convert": images, Word, Excel, PowerPoint and text files become a PDF; a PDF becomes a Word
        document or images."""
        if self.mode != "read":
            return
        pattern = lambda exts: " ".join("*" + e for e in exts)
        images, office, text = pattern(IMAGE_EXTS), pattern(convert.OFFICE), pattern(convert.TEXT)
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Choose files to make into a PDF, or a PDF to convert", self._start_dir(),
            f"Files to convert (*.pdf {images} {office} {text});;PDF files (*.pdf);;Images ({images});;"
            f"Word, Excel and PowerPoint ({office});;Text files ({text})")
        if not paths:
            return
        others = [p for p in paths if not p.lower().endswith(".pdf")]
        if others:
            self.images_to_pdf(paths)  # everything (PDFs included) goes into one PDF, in Organize & Merge
            return
        dlg = convert.PdfChoice(self, os.path.basename(paths[0]))
        if not dlg.exec():
            return
        if dlg.choice == "word":
            self.pdf_to_word(paths[0])
            return
        self.open_file(paths[0])
        if self.doc and self.path == paths[0]:
            self.export_images()

    def resize_pictures(self):
        """☰ > Resize pictures: smaller copies of pictures on the PC (the same as in Explorer's right-click menu)."""
        from .resize import resize_files
        images = " ".join("*" + e for e in shell.IMAGES)
        paths, _ = QFileDialog.getOpenFileNames(self, "Choose pictures to resize (hold Ctrl to pick several)",
                                                self._start_dir(), f"Pictures ({images})")
        if not paths:
            return
        made = resize_files(sorted(paths, key=shell.natural), self.settings,
                            int(self.settings.value("convert/jpg_quality", shell.JPG_QUALITY)), self)
        if made and sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", os.path.normpath(made[0])])

    def pdf_to_word(self, path):
        src = pymupdf.open(path)
        password = None
        if src.needs_pass:
            password = self._ask_password(src)
            if password is None:
                return
        if src.is_pdf and not any(page.get_text("words") for page in src.pages(0, min(len(src), 5))):
            src.close()
            if not ask(self, "This PDF looks like a scan (pictures of pages, no text), so the Word document would "
                             "only hold pictures. Convert anyway?", "Convert anyway"):
                return
        else:
            src.close()
        start = os.path.splitext(path)[0] + ".docx"
        dst, _ = QFileDialog.getSaveFileName(self, "Save as a Word document", start, "Word documents (*.docx)")
        if not dst:
            return
        if not dst.lower().endswith(".docx"):
            dst += ".docx"
        error = convert.run(self, "word_out", path, dst, f"Converting {os.path.basename(path)} to Word…",
                            password)
        if error:
            QMessageBox.warning(self, APP_NAME, f"Couldn't make the Word document:\n{error}\n\n"
                                "If it's open in Word, close it and try again.")
            return
        if error is None:
            self.toast.show_message(f"Saved {os.path.basename(dst)}", 3000)
            if sys.platform == "win32":
                subprocess.Popen(["explorer", "/select,", os.path.normpath(dst)])

    def images_to_pdf(self, paths=None):
        """Pictures (and other files to make into a PDF) open in Organize & Merge to put in order, then Done and
        Save."""
        if self.mode != "read" or not self._confirm_discard():
            return
        if not paths:
            images = " ".join("*" + e for e in IMAGE_EXTS)
            paths, _ = QFileDialog.getOpenFileNames(
                self, "Choose images to turn into a PDF (hold Ctrl to pick several)", self._start_dir(),
                f"Images ({images})")
        if paths:
            self.close_document(confirm=False)
            self.enter_pages()
            self.insert_files(paths, 0)

    def export_images(self):
        if not self.doc:
            return
        selected = self.selected_pages() if self.thumbs.selectedItems() else []
        dlg = ExportDialog(self, len(self.doc), self.view.current_page(), selected,
                           self.settings.value("export_dir", self._start_dir()))
        if not dlg.exec():
            return
        pages, fmt, dpi, folder = dlg.result_values()
        self.settings.setValue("export_dir", folder)
        base = os.path.splitext(os.path.basename(self.path))[0] if self.path else "Untitled"
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            files = export_pages(self.doc, pages, fmt, dpi, folder, base)
        except Exception as e:
            QMessageBox.critical(self, APP_NAME, f"Could not save the images:\n{e}")
            return
        finally:
            QApplication.restoreOverrideCursor()
        self.toast.show_message(f"Saved {len(files)} image(s) to {folder}")
        if sys.platform == "win32" and files:  # show the result
            subprocess.Popen(["explorer", "/select,", os.path.normpath(files[0])])

    def _open_new_window(self, path):
        """Open a file just created in its own window, leaving this one as it is."""
        win = MainWindow()
        _windows.append(win)
        win.show()
        win.open_file(path)

    def _confirm_discard(self):
        """Ask before throwing away unsaved changes. Returns False if the user cancels."""
        self._overlay_apply()  # items placed but not yet written count as changes
        if not (self.doc and self.dirty) or self.selftest:
            return True
        name = os.path.basename(self.path) if self.path else "this new document"
        r = choose(self, f"Save changes to {name}?", ["Save", "Don't save", "Cancel"])
        if r == 0:
            return self.save()
        return r == 1

    def closeEvent(self, e):
        if not self._confirm_discard():
            e.ignore()
            return
        self.view.set_document(None)
        self.view.shutdown()
        shutil.rmtree(self.workdir, ignore_errors=True)
        e.accept()

    # ---- editing pages --------------------------------------------------
    def _edit(self, change, mapping, page=None, message="", keep_view=False):
        """Apply change(doc) and refresh the display.

        mapping[i] = old index of new page i, or None for new/altered pages (redrawn).
        """
        before = self.cur_bytes if self.cur_bytes is not None else pdfio.to_bytes(self.doc)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            change(self.doc)
            after = pdfio.to_bytes(self.doc)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, APP_NAME, f"That didn't work:\n{e}")
            self._load_state(before, self.thumb_raw, page=self.view.current_page())
            return
        self.undo_stack = (self.undo_stack + [(before, self.thumb_raw, self.view.current_page())])[-MAX_UNDO:]
        self.redo_stack = []
        thumbs = [self.thumb_raw[m] if m is not None else None for m in mapping]
        if keep_view:
            scroll = (self.view.verticalScrollBar().value(), self.view.horizontalScrollBar().value())
            self._load_state(after, thumbs, None, self.view.current_page())
            if self.mode != "read":  # (only read mode keeps the view by itself)
                self.view.verticalScrollBar().setValue(scroll[0])
        else:
            self._load_state(after, thumbs, mapping, self.view.current_page() if page is None else page)
        QApplication.restoreOverrideCursor()
        self.dirty = True
        self._ws_changed = True
        self._after_change()
        if message:
            self.toast.show_message(message, 2500)

    def edit_page(self, change, page, message=""):
        """A small undoable change to one page (a comment): the view stays where it is."""
        n = len(self.doc)
        thumbs = list(self.thumb_raw)
        self._edit(change, list(range(n)), page=self.view.current_page(), message=message, keep_view=True)
        if len(self.thumb_raw) == n:
            self.thumb_raw[page] = None  # its thumbnail is drawn again too
            self._load_thumbs()

    def _load_state(self, data, thumbs, mapping=None, page=0):
        """Swap in a new version of the document (after an edit, undo or redo)."""
        old_rects = [p.rect for p in self.doc]
        self.doc.close()
        self.doc = pymupdf.open("pdf", data)
        scroll = None
        if mapping is None and self.mode in ("read", "form") and old_rects == [p.rect for p in self.doc]:
            # The same pages (a comment or a Done in Edit undone): stay put, and keep showing each page
            # until it has been drawn again rather than flashing "Loading".
            mapping = list(range(len(self.doc)))
            scroll = (self.view.verticalScrollBar().value(), self.view.horizontalScrollBar().value())
        if self.doc.needs_pass and self.password:
            self.doc.authenticate(self.password)
        self.cur_bytes = data
        self._work_n += 1
        work = os.path.join(self.workdir, f"work{self._work_n}.pdf")
        with open(work, "wb") as f:
            f.write(data)
        self._clear_find()
        page = max(0, min(page, len(self.doc) - 1))
        self.view.reload(self.doc, work, self.password, mapping, page, scroll)
        if scroll is not None:
            self.view.redraw(range(len(self.doc)))
        self.thumb_raw = list(thumbs)
        self._load_thumbs()
        self._on_page_changed(self.view.current_page() if scroll is not None else page)
        if self.comments.isVisible():
            self.comments.refresh()
        if self.mode == "form":
            self.prep.refresh()
        # Tidy old working copies, keeping the last few in case the renderer hasn't switched yet.
        # (Files still open can't be deleted on Windows; they're retried next time and on exit.)
        for name in os.listdir(self.workdir):
            n = name[4:-4]
            if n.isdigit() and int(n) < self._work_n - 3:
                try:
                    os.remove(os.path.join(self.workdir, name))
                except OSError:
                    pass

    def undo(self):
        if self.mode in self.overlays:  # changes not yet written in: the screen's own Undo
            self.overlays[self.mode][1].undo()
            return
        if self.undo_stack:
            data, thumbs, page = self.undo_stack.pop()
            self.redo_stack.append((self.cur_bytes, self.thumb_raw, self.view.current_page()))
            self._load_state(data, thumbs, page=page)
            self.dirty = True
            self._after_change()

    def redo(self):
        if self.mode in self.overlays:
            self.overlays[self.mode][1].redo()
            return
        if self.redo_stack:
            data, thumbs, page = self.redo_stack.pop()
            self.undo_stack.append((self.cur_bytes, self.thumb_raw, self.view.current_page()))
            self._load_state(data, thumbs, page=page)
            self.dirty = True
            self._after_change()

    def selected_pages(self):
        rows = sorted({i.row() for i in self.thumbs.selectedIndexes()} - {self.thumbs.pages()})
        return rows or [self.view.current_page()]

    def rotate_pages(self, degrees):
        pages = self.selected_pages()

        def change(doc):
            for i in pages:
                doc[i].set_rotation((doc[i].rotation + degrees) % 360)
        mapping = [None if i in pages else i for i in range(len(self.doc))]
        self._edit(change, mapping, message=f"Rotated {self._n(pages)}")
        self._select(pages)

    def delete_pages(self):
        pages = self.selected_pages()
        if len(pages) >= len(self.doc):
            QMessageBox.information(self, APP_NAME, "A PDF needs at least one page, so not all pages can be deleted.")
            return
        keep = [i for i in range(len(self.doc)) if i not in pages]
        self._edit(lambda doc: doc.select(keep), keep, page=pages[0],
                   message=f"Deleted {self._n(pages)} (Ctrl+Z to undo)")

    def move_pages(self, step):
        pages = self.selected_pages()
        n = len(self.doc)
        if (step < 0 and pages[0] == 0) or (step > 0 and pages[-1] == n - 1):
            return
        order = list(range(n))
        for i in (pages if step < 0 else reversed(pages)):
            order[i], order[i + step] = order[i + step], order[i]
        self._reorder(order)
        self._select([i + step for i in pages])

    def _reorder(self, order):
        selected = self.selected_pages()  # the pages being moved
        page = order.index(self.view.current_page())
        self._edit(lambda doc: doc.select(order), order, page=page, message="Pages reordered")
        self._select([order.index(i) for i in selected])  # keep just those pages selected

    def insert_files(self, paths, at):
        """Insert whole PDFs (and pictures, as pages) into the open document before page index `at`."""
        paths = convert.to_pdfs(self, self.settings, paths, self.workdir)  # Word, Excel… become PDFs first
        sources = []
        for p in paths:
            try:
                if p.lower().endswith(IMAGE_EXTS):
                    sources.append(image_to_pdf(p))
                    continue
                src = pymupdf.open(p)
                if src.needs_pass and self._ask_password(src) is None:
                    continue
                sources.append(src)
            except Exception as e:
                cant_open(self, p, e)  # the others are still added
        if not sources:
            return
        added = sum(len(s) for s in sources)
        if not self.doc:  # first files added to an empty Pages screen: they become the document
            merged = pymupdf.open()
            for src in sources:
                merged.insert_pdf(src)
            self._work_n += 1
            work = os.path.join(self.workdir, f"work{self._work_n}.pdf")
            merged.save(work)
            self._show(merged, None, render_path=work, dirty=True)
            self._ws_changed = True
            self.toast.show_message(f"{len(merged)} pages from {len(sources)} file(s)")
            return

        def change(doc):
            pos = at
            for src in sources:
                doc.insert_pdf(src, start_at=pos)
                pos += len(src)
        old = list(range(len(self.doc)))
        mapping = old[:at] + [None] * added + old[at:]
        self._edit(change, mapping, page=at,
                   message=f"Added {added} page{'s' if added != 1 else ''} from {len(sources)} file(s)")
        self._select(list(range(at, at + added)))

    def extract_pages(self):
        pages = self.selected_pages()
        path, _ = QFileDialog.getSaveFileName(self, "Save selected pages as", self._start_dir(), "PDF files (*.pdf)")
        if not path:
            return
        out = pymupdf.open()
        for i in pages:
            out.insert_pdf(self.doc, from_page=i, to_page=i)
        try:
            out.save(path, garbage=3, deflate=True)
        except Exception as e:
            QMessageBox.critical(self, APP_NAME, f"Could not save:\n{e}")
            return
        self.toast.show_message(f"Saved {self._n(pages)} to {os.path.basename(path)} (opened in a new window)")
        self._open_new_window(path)

    def _select(self, rows):
        self.thumbs.clearSelection()
        for r in rows:
            if 0 <= r < self.thumbs.pages():
                self.thumbs.item(r).setSelected(True)

    @staticmethod
    def _n(pages):
        return f"{len(pages)} page{'s' if len(pages) != 1 else ''}"

    def _start_dir(self):
        return os.path.dirname(self.path) if self.path else self.settings.value("last_dir", "")

    def _thumb_menu(self, pos):
        if not self.doc:
            return
        item = self.thumbs.itemAt(pos)
        if item is None or item is self.thumbs.tile:
            return
        if not item.isSelected():
            self.thumbs.clearSelection()
            item.setSelected(True)
        menu = QMenu(self)
        if self.mode == "pages":
            for a in (self.act_rot_left, self.act_rot_right, None, self.act_move_up, self.act_move_down,
                      self.act_delete, None, self.act_extract, self.act_export_images):
                menu.addAction(a) if a else menu.addSeparator()
        else:
            for a in (self.act_extract, self.act_export_images, None, self.act_pages):
                menu.addAction(a) if a else menu.addSeparator()
        menu.exec(self.thumbs.mapToGlobal(pos))

    # ---- saving ---------------------------------------------------------
    def save(self):
        if self.mode == "pages" and self.doc:  # keep what was done in Organize & Merge, save, and carry on there
            self.exit_pages()
            ok = self.save()
            self.enter_pages()
            return ok
        self._overlay_apply()
        if self.mode == "form":
            self.prep.flush()
        if not self.doc:
            return False
        if not self.path:
            return self.save_as()
        return self._write(self.path)

    def save_as(self, new=False):
        self._overlay_apply()
        if not self.doc:
            return False
        if self.path and not new:
            start = self.path
        else:
            base = os.path.splitext(os.path.basename(self.path))[0] + " (edited).pdf" if self.path else "Merged.pdf"
            start = os.path.join(self._start_dir() or "", base)
        path, _ = QFileDialog.getSaveFileName(self, "Save as new PDF" if new else "Save PDF as", start,
                                              "PDF files (*.pdf)")
        if not path:
            return False
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        return self._write(path)

    def _write(self, path):
        tmp = path + ".aerialist-tmp"
        try:
            fonts.save_copy(self.doc, tmp, self.save_password)
            os.replace(tmp, path)  # only replace the original once the new file is fully written
        except Exception as e:
            try:
                os.remove(tmp)
            except OSError:
                pass
            QMessageBox.critical(self, APP_NAME, f"Could not save to {path}:\n{e}\n\n"
                                 "If the file is open in another program, close it or use Save as.")
            return False
        self.path, self.dirty = path, False
        self._add_recent(path)
        self._after_change()
        self.toast.show_message(f"Saved {os.path.basename(path)}", 2500)
        return True

    # ---- recent files and the default-app offer -------------------------
    def _recent(self):
        recent = self.settings.value("recent", []) or []
        if isinstance(recent, str):  # QSettings returns a lone string for a one-item list on Windows
            recent = [recent]
        return [p for p in recent if os.path.isfile(p)]

    def _add_recent(self, path):
        recent = [path] + [p for p in self._recent() if p != path]
        self.settings.setValue("recent", recent[:10])
        self._refresh_recent()

    def open_settings(self, page="general"):
        from .settings import SettingsDialog
        self.sync_stamp_keys()
        SettingsDialog(self, page).exec()
        self.sync_stamp_keys()  # stamps added or removed there

    def _clear_recent(self):
        self.settings.setValue("recent", [])
        self._refresh_recent()

    def _refresh_recent(self):
        self.recent_menu.clear()
        recent = self._recent()
        for p in recent:
            a = self.recent_menu.addAction(os.path.basename(p))
            a.setToolTip(p)
            a.triggered.connect(lambda _=False, p=p: self.open_file(p))
        self.recent_menu.setEnabled(bool(recent))
        self.home.set_recent(recent)

    def _update_banner(self):
        offer = (sys.platform == "win32" and default_app.installed() and not self.selftest
                 and not self.settings.value("default_app/dont_ask", False, type=bool)
                 and not getattr(self, "_banner_dismissed", False) and not default_app.is_default())
        self.home.banner.setVisible(offer)

    def _make_default(self):
        default_app.open_settings()
        self._banner_dismissed = True
        self.home.banner.hide()
        self.toast.show_message("In Settings, click “Set default” at the top of the Benelli Aerialist page.", 7000)

    def _not_now(self):
        # Asked again next time the app starts, up to three times, then not again (the ☰ menu still has it).
        n = int(self.settings.value("default_app/declined", 0)) + 1
        self.settings.setValue("default_app/declined", n)
        if n >= 3:
            self.settings.setValue("default_app/dont_ask", True)
        self._banner_dismissed = True
        self.home.banner.hide()

    # ---- thumbnails -----------------------------------------------------
    # ---- comments -------------------------------------------------------
    def show_in_folder(self):
        """Open the PDF's folder in File Explorer with the file selected."""
        if not self.path:
            return
        if not os.path.exists(self.path):
            self.toast.show_message("The file isn't in its folder any more (moved, renamed or deleted).")
            return
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", os.path.normpath(self.path)])
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(self.path)))

    def show_features(self):
        FeaturesDialog(self).exec()

    def features_after_update(self):
        """The feature list, once after each install or update (not for a copy run from source)."""
        if version.VERSION == "dev" or self.selftest or self.settings.value("features/seen", "") == version.VERSION:
            return
        self.settings.setValue("features/seen", version.VERSION)
        QTimer.singleShot(700, self.show_features)

    def toggle_snip(self, on=None):
        on = (not self.snipper.on) if on is None else bool(on)
        self.snipper.set_on(on and bool(self.doc) and self.mode == "read")

    def toggle_comments(self, on=None):
        on = (not self.comments.isVisible()) if on is None else bool(on)
        if on and (not self.doc or self.mode != "read"):
            on = False
        if not on:
            self.comments.pick(None)
        self.comments.setVisible(on)
        if on:
            self.comments.refresh()
        QTimer.singleShot(0, self.pill.reposition)
        self._update_enabled()

    def _annot_clicked(self, page, xref):
        if self.mode != "read":
            return
        if not self.comments.isVisible():
            self.toggle_comments(True)
        self.comments.select_xref(page, xref)

    def _park_comments(self):
        """Other modes use the mouse on the pages themselves: put the comment tool down and the list away."""
        self._comments_were_open = self.comments.isVisible()
        self.comments.pick(None)
        self.comments.hide()

    def _unpark_comments(self):
        if getattr(self, "_comments_were_open", False) and self.doc:
            self.toggle_comments(True)
        self._comments_were_open = False

    def _load_thumbs(self):
        self._thumb_sizes = {}
        self.thumbs.blockSignals(True)
        self.thumbs.clear()
        for i in range(len(self.doc)):
            item = QListWidgetItem()
            item.setData(Qt.DecorationRole, self._thumb_pixmap(i))
            item.setToolTip(f"Page {i + 1}")
            self.thumbs.addItem(item)
        self.thumbs.set_tile(self.mode == "pages")
        self.thumbs.blockSignals(False)
        self.view.request_thumbnails(THUMB_RENDER, [i for i, t in enumerate(self.thumb_raw) if t is None])

    def _refresh_thumb_icons(self):
        if not self.doc:
            return
        for i in range(min(self.thumbs.pages(), len(self.doc))):
            self.thumbs.item(i).setData(Qt.DecorationRole, self._thumb_pixmap(i))
        self.thumbs.doItemsLayout()

    def _on_thumb_ready(self, i, img):
        if i < self.thumbs.pages() and i < len(self.thumb_raw):
            pix = QPixmap.fromImage(img)
            pix.setDevicePixelRatio(self.devicePixelRatioF())
            self.thumb_raw[i] = pix
            self.thumbs.item(i).setData(Qt.DecorationRole, self._thumb_pixmap(i))

    def _thumb_pixmap(self, i):
        """The page picture at the thumbnail size (white while it's being drawn)."""
        page = self.doc[i]
        w = self.thumbs.iconSize().width()
        h = max(1, int(w * page.rect.height / page.rect.width))
        dpr = self.devicePixelRatioF()
        raw = self.thumb_raw[i] if i < len(self.thumb_raw) else None
        key = (i, w, h) if raw is not None else None
        if key in self._thumb_sizes and self._thumb_sizes[key][0] == raw.cacheKey():
            return self._thumb_sizes[key][1]  # scaled before (sidebar and Organize & Merge sizes): reuse
        if raw is not None and raw.size() == QSize(int(w * dpr), int(h * dpr)):
            pix = QPixmap(raw)  # already the right size: no need to scale (slow with hundreds of pages)
        elif raw is not None:
            pix = raw.scaled(QSize(int(w * dpr), int(h * dpr)), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        else:
            pix = QPixmap(int(w * dpr), int(h * dpr))
            pix.fill(Qt.white)
        pix.setDevicePixelRatio(dpr)
        if key is not None:
            self._thumb_sizes[key] = (raw.cacheKey(), pix)
        return pix

    def _on_thumb_clicked(self, row):
        if self.mode == "pages" or row < 0 or row >= self.thumbs.pages():
            return
        if row != self.view.current_page():
            # The click itself already set the selection; don't let the page change echo back
            # into the list (that would wipe a Ctrl+click multi-selection).
            self._from_thumb = True
            try:
                self.view.go_to_page(row)
            finally:
                self._from_thumb = False

    # ---- status sync ----------------------------------------------------
    def _on_page_changed(self, i):
        if self.doc:
            self.pill.set_page(i, len(self.doc))
        if self.mode == "form":
            self.prep.follow_page(i)
        if getattr(self, "_from_thumb", False) or self.mode == "pages":
            return
        self.thumbs.blockSignals(True)
        if len(self.thumbs.selectedItems()) > 1:
            # Keep a multi-page selection; just move the "current" marker.
            self.thumbs.setCurrentRow(i, QItemSelectionModel.NoUpdate)
        else:
            self.thumbs.setCurrentRow(i)
        self.thumbs.blockSignals(False)
        self.thumbs.viewport().update()

    def _on_zoom_changed(self, zoom):
        self.pill.set_zoom(zoom)

    def _on_zoom_text(self, text):
        if text == "Fit width":
            self.view.fit_width()
        elif text == "Fit page":
            self.view.fit_page()
        else:
            try:
                self.view.set_zoom(float(text.strip().rstrip("%")) / 100)
            except ValueError:
                self._on_zoom_changed(self.view.zoom)

    # ---- find -------------------------------------------------------------
    def show_find(self):
        if not self.doc or self.mode == "pages":
            return
        self.find_bar.open_bar()
        self.top.find_btn.setChecked(True)

    def _find_closed(self):
        self.top.find_btn.setChecked(False)
        self._clear_find()
        self.view.setFocus()

    def _on_find_enter(self):
        shift = QApplication.keyboardModifiers() & Qt.ShiftModifier
        self.find_step(-1 if shift else 1)

    def _on_find_text(self, text):
        self._clear_find()
        if text.strip():
            self._find_timer.start()

    def _clear_find(self, *_):
        self.hits, self.hit_index, self.hit_query = [], -1, ""
        self.find_bar.set_count("")
        self.ticks.set_marks([])
        self.view.set_highlights([])

    def _search(self, direction):
        """Make sure self.hits is for the text in the box. False if there's nothing to show."""
        query = self.find_bar.box.text().strip()
        if not self.doc or not query:
            self.show_find()
            return False
        self._find_timer.stop()
        if query != self.hit_query:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                # search_for gives positions on the unturned page; turned pages (common for drawings)
                # are shown turned, so the highlight has to be turned the same way.
                self.hits = [(i, (r * page.rotation_matrix).normalize())
                             for i, page in enumerate(self.doc)
                             for r in textfix.fix_hits(page, query, page.search_for(query))]
            finally:
                QApplication.restoreOverrideCursor()
            self.hit_query = query
            self.ticks.set_marks([(i, r.y0) for i, r in self.hits])
            # Start from the first hit at or after the page being viewed.
            start = next((n for n, (i, _) in enumerate(self.hits) if i >= self.view.current_page()), 0)
            self.hit_index = start - 1 if direction > 0 else start
        if not self.hits:
            if any(p.get_text().strip() for p in self.doc):
                self.find_bar.set_count("No matches")
            else:
                self.find_bar.set_count("No text", "No searchable text: this looks like a scanned PDF")
            self.view.set_highlights([])
            return False
        return True

    def find_step(self, direction):
        if self._search(direction):
            self._show_hit((self.hit_index + direction) % len(self.hits))

    def find_page_step(self, direction):
        """Jump to the first match on the next (or previous) page that has one."""
        fresh = self.find_bar.box.text().strip() != self.hit_query
        if not self._search(direction):
            return
        here = self.hits[self.hit_index][0] if 0 <= self.hit_index < len(self.hits) and not fresh \
            else self.view.current_page() - (1 if direction > 0 else -1)
        pages = sorted({i for i, _ in self.hits})
        if direction > 0:
            target = next((i for i in pages if i > here), pages[0])
        else:
            target = next((i for i in reversed(pages) if i < here), pages[-1])
        self._show_hit(next(n for n, (i, _) in enumerate(self.hits) if i == target))

    def _show_hit(self, index):
        self.hit_index = index
        page, rect = self.hits[index]
        on_page = sum(1 for i, _ in self.hits if i == page)
        self.find_bar.set_count(f"{index + 1} of {len(self.hits)} · {on_page} on page",
                                f"Match {index + 1} of {len(self.hits)}; page {page + 1} has {on_page}")
        self.view.set_highlights(self.hits, index)
        self.view.show_rect(page, rect)

    # ---- drag and drop --------------------------------------------------
    def dragEnterEvent(self, e):
        if pdf_paths(e.mimeData(), images=True) and self.mode in ("read", "pages", "edit"):
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = pdf_paths(e.mimeData(), images=True)
        if not paths:
            return
        if self.mode == "pages":
            self.insert_files(paths, self.thumbs.pages() if self.doc else 0)
        elif self.mode == "edit":
            images = [p for p in paths if p.lower().endswith(IMAGE_EXTS)]
            if images:
                self.edit_session.drop_image(images[0], QCursor.pos())
        elif self.mode == "read":
            if any(not p.lower().endswith(".pdf") for p in paths):
                what = "these images" if all(p.lower().endswith(IMAGE_EXTS) for p in paths) else \
                    ("this file" if len(paths) == 1 else "these files")
                if ask(self, f"Turn {what} into a PDF?", "Make PDF") and self._confirm_discard():
                    self.close_document(confirm=False)
                    self.enter_pages()
                    self.insert_files(paths, 0)
                return
            if len(paths) > 1 and not self.doc:
                if ask(self, f"Merge these {len(paths)} PDFs into one?", "Merge", "Open first only"):
                    self.enter_pages()
                    self.insert_files(paths, 0)
                    return
            self.open_file(paths[0])

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.toast.isVisible():
            self.toast.show_message(self.toast.text(), 2000)


_windows = []  # extra windows opened for newly created files


def _selftest(app, win):
    import tempfile
    try:
        import pdf2docx  # noqa: F401 (PDF to Word must be inside the packaged app)
    except Exception:
        QTimer.singleShot(0, lambda: app.exit(3))
        return
    path = os.path.join(tempfile.mkdtemp(), "selftest.pdf")
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "Aerialist self-test")
    doc.save(path)
    win.open_file(path)
    QTimer.singleShot(8000, lambda: app.exit(0 if win.view.rendered else 1))


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(QIcon(ICON_PATH))
    QImageReader.setAllocationLimit(4096)  # MB: Qt's usual 256 turns away big photos and drawings
    theme.apply(app, str(QSettings("Aerialist", "Aerialist").value("theme", "auto")))
    if sys.platform == "win32":  # show the app's own icon on the taskbar, not Python's
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("BenelliAerialist.PDF")
    action = next((a for a in sys.argv[1:] if a in shell.ACTIONS), None)
    if action:  # from File Explorer's right-click menu
        paths = [shell.long_path(a) for a in sys.argv[1:] if a not in shell.ACTIONS and os.path.exists(a)]
        paths = shell.gather(action, paths)
        if not paths:
            return  # another copy of the app has our files
        paths.sort(key=shell.natural)
        if action == "--resize":  # no window: just the Resize box
            from .resize import resize_files
            settings = QSettings("Aerialist", "Aerialist")
            made = resize_files([p for p in paths if shell.kind(p) == "image"], settings,
                                int(settings.value("convert/jpg_quality", shell.JPG_QUALITY)))
            if made and sys.platform == "win32":
                subprocess.Popen(["explorer", "/select,", os.path.normpath(made[0])])
            return
        win = MainWindow()
        if action == "--merge":
            win.show()
            win.images_to_pdf(paths)
        else:
            to = action[len("--convert-"):] if action.startswith("--convert-") else None
            made = shell.convert_files(win, paths, to)
            pdfs = [m for m in made if m.lower().endswith(".pdf")]
            if not pdfs:  # nothing to show here: point at the new files in Explorer and finish
                if made and sys.platform == "win32":
                    subprocess.Popen(["explorer", "/select,", os.path.normpath(made[0])])
                return
            win.show()
            win.open_file(pdfs[0])
            win.toast.show_message(f"Saved {os.path.basename(pdfs[0])} next to the original" if len(made) == 1
                                   else f"Made {len(made)} PDFs next to the originals (showing the first)", 4000)
        sys.exit(app.exec())
    win = MainWindow()
    win.show()
    win.features_after_update()
    QTimer.singleShot(400, win.view.warm_up)  # start the page-drawing processes while Home is showing
    if "--selftest" in sys.argv:  # used by the automated build: open a PDF, exit 0 once a page renders
        _selftest(app, win)
    elif len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        win.open_file(shell.long_path(sys.argv[1]))  # supports "Open with…" / file associations
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
