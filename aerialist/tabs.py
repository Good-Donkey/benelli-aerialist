"""The app's window, and tabs: each open file is a document (main.MainWindow) inside an AppWindow.

Settings > General > Opening files picks how files open:
- "windows" (the usual): one file per window, as before. Each AppWindow holds one document and shows no tabs.
- "tabs": every file opens in one window, one tab each, with a slim row of tabs along the top. Files opened from
  File Explorer (double-click, right-click > Open) go to the window that's already open: the first copy of the app
  listens on a local socket (the Hub) and later copies hand their files to it and quit.
"""
import getpass
import os
import re
import sys
import tempfile
import time

from PySide6.QtCore import QLockFile, QSettings, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (
    QHBoxLayout, QMainWindow, QStackedWidget, QTabBar, QToolButton, QVBoxLayout, QWidget,
)

from .icons import icon
from .popups import APP_NAME

SETTING = "open/how"  # "windows" or "tabs"
TAB_WIDTH = 200  # longest a tab gets before its name is shortened with …

_hosts = []  # every AppWindow open, the most recently used last


def tabbed():
    return str(QSettings("Aerialist", "Aerialist").value(SETTING, "windows")) == "tabs"


def same_file(a, b):
    return bool(a and b) and os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def latest():
    """The window used most recently (where files from File Explorer go in tabs mode)."""
    return _hosts[-1] if _hosts else None


def new_window():
    host = AppWindow()
    host.show()
    return host


class TabStrip(QTabBar):
    """The row of tabs: one per open file, name only, a small ✕ on each."""
    close_clicked = Signal(int)

    def __init__(self):
        super().__init__()
        self.setObjectName("docTabs")
        self.setDocumentMode(True)
        self.setDrawBase(False)
        self.setExpanding(False)
        self.setMovable(True)
        self.setElideMode(Qt.ElideMiddle)
        self.setUsesScrollButtons(True)
        self.setFocusPolicy(Qt.NoFocus)

    def tabSizeHint(self, i):
        s = super().tabSizeHint(i)
        return QSize(min(s.width(), TAB_WIDTH), s.height())

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MiddleButton:  # middle-click closes a tab, as in a web browser
            i = self.tabAt(e.position().toPoint())
            if i >= 0:
                self.close_clicked.emit(i)
                return
        super().mouseReleaseEvent(e)


class AppWindow(QMainWindow):
    """A window with one or more documents in it."""

    def __init__(self):
        super().__init__()
        from .main import MainWindow  # (main imports this module)
        self._make = MainWindow
        self.setWindowTitle(APP_NAME)
        self.setAcceptDrops(False)  # each document takes its own drops
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.bar = QWidget()
        self.bar.setObjectName("docTabsBar")
        self.bar.setAttribute(Qt.WA_StyledBackground, True)
        bl = QHBoxLayout(self.bar)
        bl.setContentsMargins(6, 3, 6, 0)
        bl.setSpacing(2)
        self.strip = TabStrip()
        self.strip.currentChanged.connect(self._switched)
        self.strip.close_clicked.connect(lambda i: self.close_tab(self.strip.tabData(i)))
        bl.addWidget(self.strip, 0, Qt.AlignBottom)
        self.plus = QToolButton()
        self.plus.setObjectName("docTabsPlus")
        self.plus.setIcon(icon("plus", size=14))
        self.plus.setIconSize(QSize(14, 14))
        self.plus.setToolTip("New tab (Ctrl+T)")
        self.plus.setCursor(Qt.PointingHandCursor)
        self.plus.setFocusPolicy(Qt.NoFocus)
        self.plus.clicked.connect(lambda: self.new_tab())
        bl.addWidget(self.plus, 0, Qt.AlignVCenter)
        bl.addStretch(1)
        lay.addWidget(self.bar)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)
        self.setCentralWidget(body)
        for keys, slot in ((QKeySequence("Ctrl+Tab"), lambda: self.step(1)),
                           (QKeySequence("Ctrl+Shift+Tab"), lambda: self.step(-1)),
                           (QKeySequence("Ctrl+PgDown"), lambda: self.step(1)),
                           (QKeySequence("Ctrl+PgUp"), lambda: self.step(-1)),
                           (QKeySequence("Ctrl+T"), lambda: self.tabbed() and self.new_tab())):
            QShortcut(keys, self, slot)
        self.bar.hide()
        _hosts.append(self)
        self.new_tab()
        self._make.fit_to_screen(self)

    # ---- tabs -----------------------------------------------------------
    def tabbed(self):
        return tabbed()

    def current(self):
        return self.stack.currentWidget()

    def docs(self):
        return [self.strip.tabData(i) for i in range(self.strip.count())]

    def new_tab(self):
        """A new tab showing Home, made the current one."""
        doc = self._make(host=self)
        self.stack.addWidget(doc)
        i = self.strip.addTab(self._label(doc))
        self.strip.setTabData(i, doc)
        close = QToolButton()
        close.setObjectName("docTabClose")
        close.setIcon(icon("close", size=10))
        close.setIconSize(QSize(10, 10))
        close.setFixedSize(18, 18)
        close.setToolTip("Close (Ctrl+W)")
        close.setCursor(Qt.PointingHandCursor)
        close.setFocusPolicy(Qt.NoFocus)
        close.clicked.connect(lambda _=False, d=doc: self.close_tab(d))
        self.strip.setTabButton(i, QTabBar.RightSide, close)
        doc.windowTitleChanged.connect(lambda _t, d=doc: self._retitle(d))
        self.strip.setCurrentIndex(i)
        self._switched(i)
        self._update_bar()
        QTimer.singleShot(400, doc.view.warm_up)
        return doc

    def show_tab(self, doc):
        for i in range(self.strip.count()):
            if self.strip.tabData(i) is doc:
                self.strip.setCurrentIndex(i)

    def step(self, by):
        n = self.strip.count()
        if n > 1:
            self.strip.setCurrentIndex((self.strip.currentIndex() + by) % n)

    def _switched(self, i):
        doc = self.strip.tabData(i) if i >= 0 else None
        if doc is None:
            return
        self.stack.setCurrentWidget(doc)
        doc._refresh_recent()  # another tab may have opened a file since
        doc.view.setFocus()
        self._retitle(doc)

    @staticmethod
    def _label(doc):
        title = doc.windowTitle()
        if title == APP_NAME:
            return "Home"
        return title[:-len(" - " + APP_NAME)] if title.endswith(" - " + APP_NAME) else title

    def _retitle(self, doc):
        for i in range(self.strip.count()):
            if self.strip.tabData(i) is doc:
                self.strip.setTabText(i, self._label(doc))
                self.strip.setTabToolTip(i, doc.path or "")
        if doc is self.current():
            self.setWindowTitle(doc.windowTitle())
        self._update_bar()

    def _update_bar(self):
        """The tab row shows in tabs mode once a file is open (not for Home on its own), and whenever there's
        more than one tab."""
        n = self.strip.count()
        show = n > 1 or (self.tabbed() and n == 1 and bool(self.current() and self.current().doc))
        self.bar.setVisible(show)
        closable = n > 1 or bool(self.current() and self.current().doc)
        for i in range(n):
            b = self.strip.tabButton(i, QTabBar.RightSide)
            if b is not None:
                b.setVisible(closable)

    def close_tab(self, doc):
        """Close one tab (asking about unsaved changes first). The last tab goes back to Home instead."""
        if doc is None:
            return False
        if self.strip.count() == 1:
            return doc.close_document()
        self.show_tab(doc)
        if not doc.close():
            return False
        self._remove(doc)
        return True

    def _remove(self, doc):
        for i in range(self.strip.count()):
            if self.strip.tabData(i) is doc:
                self.strip.removeTab(i)
                break
        self.stack.removeWidget(doc)
        doc.deleteLater()
        self._update_bar()

    def drop_unused(self, doc):
        """Close a tab made for something that was then cancelled (nothing open in it)."""
        if doc is not None and not doc.doc and self.strip.count() > 1 and doc.close():
            self._remove(doc)

    def find(self, path):
        for doc in self.docs():
            if same_file(doc.path, path):
                return doc
        return None

    def open_path(self, path, asker=None):
        """Tabs mode: show the file in its own tab (the one it's already in, the asking tab if that's empty,
        or a new one). Returns the document showing it, or None."""
        doc = self.find(path)
        if doc is not None:
            self.show_tab(doc)
            return doc
        here = asker if asker is not None else self.current()
        fresh = here is None or here.doc or here.mode != "read"
        target = self.new_tab() if fresh else here
        target._open_here(path)
        if not target.doc and fresh:
            self.drop_unused(target)
            return None
        return target if target.doc else None

    def bring_forward(self):
        if self.isMinimized():
            self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()

    # ---- window ---------------------------------------------------------
    def changeEvent(self, e):
        super().changeEvent(e)
        if self.isActiveWindow() and self in _hosts and _hosts[-1] is not self:
            _hosts.remove(self)
            _hosts.append(self)

    def closeEvent(self, e):
        """Close every tab, asking about each one with unsaved changes (shown first, so you can see which)."""
        for doc in self.docs():
            if doc.doc and doc.dirty:
                self.show_tab(doc)
            if not doc.close():
                e.ignore()
                return
            self._remove(doc) if self.strip.count() > 1 else None
        if self in _hosts:
            _hosts.remove(self)
        e.accept()


class Hub:
    """Tabs mode: one copy of the app takes the files every later copy is started with (File Explorer starts a
    new copy for each file opened). A lock file says which copy that is."""

    def __init__(self):
        user = re.sub(r"[^A-Za-z0-9]", "", getpass.getuser()) or "user"
        self.name = f"BenelliAerialistTabs-{user}"
        self.lock = QLockFile(os.path.join(tempfile.gettempdir(), self.name + ".lock"))
        self.lock.setStaleLockTime(0)  # only stale if the copy holding it has gone
        self.server = None
        self.handler = None

    def join(self, command, paths, wait=5.0):
        """Become the hub (returns False: carry on here) or hand the job to the one running (True: quit)."""
        if self.lock.tryLock(0):
            self._listen()
            return False
        if sys.platform == "win32":  # let the other copy bring its window to the front
            try:
                import ctypes
                ctypes.windll.user32.AllowSetForegroundWindow(-1)
            except Exception:
                pass
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline:  # the hub may still be starting up
            if self._send(command, paths):
                return True
            if self.lock.tryLock(0):  # it went away
                self._listen()
                return False
            time.sleep(0.1)
        return False  # couldn't reach it: open here

    def start(self):
        """Settings switched to tabs: this copy takes later files, unless another already does."""
        if self.server is None and self.lock.tryLock(0):
            self._listen()

    def stop(self):
        if self.server is not None:
            self.server.close()
            self.server = None
            self.lock.unlock()

    def _listen(self):
        QLocalServer.removeServer(self.name)
        self.server = QLocalServer()
        self.server.listen(self.name)
        self.server.newConnection.connect(self._arrived)

    def _send(self, command, paths):
        s = QLocalSocket()
        s.connectToServer(self.name)
        if not s.waitForConnected(200):
            return False
        s.write(("\n".join([command] + list(paths)) + "\n").encode("utf-8"))
        s.flush()
        s.waitForBytesWritten(2000)
        s.disconnectFromServer()
        if s.state() != QLocalSocket.UnconnectedState:
            s.waitForDisconnected(1000)
        return True

    def _arrived(self):
        while self.server is not None and self.server.hasPendingConnections():
            sock = self.server.nextPendingConnection()
            sock.setProperty("got", b"")

            def read(s=sock):
                s.setProperty("got", bytes(s.property("got") or b"") + bytes(s.readAll()))

            def done(s=sock):
                read(s)
                lines = [p for p in bytes(s.property("got") or b"").decode("utf-8").split("\n") if p.strip()]
                s.deleteLater()
                if lines and self.handler:
                    QTimer.singleShot(0, lambda: self.handler(lines[0], lines[1:]))

            sock.readyRead.connect(read)
            sock.disconnected.connect(done)
            read()


hub = Hub()


def run(command, paths, toast=""):
    """Do a job from the command line in this copy of the app: "open" files, or "merge" them."""
    host = latest() if (tabbed() and latest()) else new_window()
    host.bring_forward()
    if command == "merge":
        doc = host.current()
        if doc.doc or doc.mode != "read":
            doc = host.new_tab()
        doc.images_to_pdf(paths)
        return
    shown = None
    for p in paths:
        if os.path.exists(p):
            shown = host.current().open_file(p) or shown
    if shown is not None and toast:
        shown.toast.show_message(toast, 4000)


hub.handler = run


def all_docs():
    return [doc for host in _hosts for doc in host.docs()]


def settings_changed(source):
    """After Settings closes: other tabs and windows pick up what changed there, and tabs mode starts or stops
    taking files from File Explorer."""
    for doc in all_docs():
        if doc is source:
            continue
        doc.sync_stamp_keys()
        doc._refresh_recent()
        doc.top._fit()
        if doc.mode == "read":
            doc._apply_mode_ui()
            doc._update_enabled()
    for host in _hosts:
        host._update_bar()
    if tabbed():
        hub.start()
    else:
        hub.stop()
