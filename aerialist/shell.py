"""Right-click in File Explorer: "Convert with Benelli Aerialist" and "Merge"
(the installer adds them for PDFs, pictures, Office and text files).

Explorer starts the app once for each selected file, so the first copy to start collects the others' files
for a moment (they hand theirs over and quit), then does the job once with all of them."""
import getpass
import os
import re
import sys
import tempfile
import time

import pymupdf
from PySide6.QtCore import QEventLoop, QLockFile, QTimer, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QPushButton, QVBoxLayout

from . import convert
from .export import export_pages, image_to_pdf
from .popups import APP_NAME

TARGETS = ("pdf", "png", "jpg", "word")
ACTIONS = ("--convert", "--merge", "--resize") + tuple(f"--convert-{t}" for t in TARGETS)  # --convert asks which
DPIS, DPI = (96, 150, 200, 300, 600), 300  # pages saved as pictures
JPG_QUALITIES, JPG_QUALITY = (70, 80, 90, 95, 100), 95
IMAGES = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp")
QUIET_MS = 700  # wait this long after the last file arrives
LONGEST_MS = 6000


def _name(action):
    user = re.sub(r"[^A-Za-z0-9]", "", getpass.getuser()) or "user"
    return f"BenelliAerialist{action.strip('-').title()}-{user}"


def _hand_over(name, paths):
    s = QLocalSocket()
    s.connectToServer(name)
    if not s.waitForConnected(150):
        return False
    s.write(("\n".join(paths) + "\n").encode("utf-8"))
    s.flush()
    s.waitForBytesWritten(2000)
    s.disconnectFromServer()
    if s.state() != QLocalSocket.UnconnectedState:
        s.waitForDisconnected(1000)
    return True


def gather(action, paths):
    """All the files Explorer sent for this action. None if another copy of the app took ours (then quit)."""
    name = _name(action)
    lock = QLockFile(os.path.join(tempfile.gettempdir(), name + ".lock"))
    lock.setStaleLockTime(20000)
    deadline = time.monotonic() + 4
    while not lock.tryLock(0):
        if _hand_over(name, paths):
            return None
        if time.monotonic() > deadline:  # couldn't reach it: just do our own
            return paths
        time.sleep(0.05)
    QLocalServer.removeServer(name)
    server = QLocalServer()
    server.listen(name)
    got = list(paths)
    loop = QEventLoop()
    quiet = QTimer(singleShot=True, interval=QUIET_MS)
    quiet.timeout.connect(loop.quit)
    QTimer.singleShot(LONGEST_MS, loop.quit)
    buffers = {}

    def read(sock):
        buffers[sock] = buffers.get(sock, b"") + bytes(sock.readAll())
        quiet.start()

    def done(sock):
        read(sock)
        got.extend(p for p in buffers.pop(sock, b"").decode("utf-8").split("\n") if p.strip())
        sock.deleteLater()

    def arrived():
        while server.hasPendingConnections():
            sock = server.nextPendingConnection()
            sock.readyRead.connect(lambda s=sock: read(s))
            sock.disconnected.connect(lambda s=sock: done(s))
            read(sock)

    server.newConnection.connect(arrived)
    quiet.start()
    loop.exec()
    server.close()
    lock.unlock()
    seen = set()
    return [p for p in got if not (p in seen or seen.add(p))]


def long_path(path):
    """The full name of a file Windows handed over in its old short form (PHOTO_~1.JPG), so names made from it
    read properly."""
    path = os.path.abspath(path)
    if sys.platform != "win32" or "~" not in path:
        return path
    import ctypes
    buf = ctypes.create_unicode_buffer(32768)
    n = ctypes.windll.kernel32.GetLongPathNameW(path, buf, len(buf))
    return buf.value if 0 < n < len(buf) else path


def natural(path):
    """File name order as Explorer shows it (Page 2 before Page 10)."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", os.path.basename(path))]


def free_path(path):
    """path, or "name (2).ext" and so on if that's taken."""
    base, ext = os.path.splitext(path)
    n = 2
    while os.path.exists(path):
        path = f"{base} ({n}){ext}"
        n += 1
    return path


def kind(path):
    ext = os.path.splitext(path)[1].lower()
    return "pdf" if ext == ".pdf" else "image" if ext in IMAGES else "office" if convert.kind_of(path) else None


class Choice(QDialog):
    """What to convert the files to."""

    def __init__(self, parent, title, options):
        super().__init__(parent)
        self.setWindowTitle("Convert")
        self.choice = None
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(title))
        for key, label, note in options:
            b = QPushButton(label)
            b.setMinimumHeight(34)
            b.clicked.connect(lambda _=False, k=key: self._pick(k))
            lay.addWidget(b)
            if note:
                n = QLabel(note)
                n.setWordWrap(True)
                n.setObjectName("choiceNote")
                lay.addWidget(n)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self.setMinimumWidth(420)

    def _pick(self, key):
        self.choice = key
        self.accept()


def options_for(paths):
    kinds = {kind(p) for p in paths}
    n = len(paths)
    if kinds == {"pdf"}:
        return [("word", "Word document (.docx)" if n == 1 else f"{n} Word documents (.docx)", convert.NOTES["word"]),
                ("png", "Images: PNG, one per page", "Sharp, larger files."),
                ("jpg", "Images: JPG, one per page", "Smaller files.")]
    out = [("pdf", "PDF" if n == 1 else f"{n} PDFs, one for each file", "")]
    if kinds == {"image"}:
        out += [("png", "PNG picture" + ("s" if n > 1 else ""), ""), ("jpg", "JPG picture" + ("s" if n > 1 else ""), "")]
    return out


def _save_image(src, dst, fmt, quality):
    img = QImage(src)
    if img.isNull():
        raise RuntimeError("The picture couldn't be read.")
    if fmt == "jpg" and img.hasAlphaChannel():  # JPG has no see-through parts: put it on white
        flat = QImage(img.size(), QImage.Format_RGB32)
        flat.fill(QColor("white"))
        p = QPainter(flat)
        p.drawImage(0, 0, img)
        p.end()
        img = flat
    if not img.save(dst, "JPG" if fmt == "jpg" else "PNG", quality if fmt == "jpg" else -1):
        raise RuntimeError("The picture couldn't be saved there.")


def convert_files(win, paths, to=None):
    """Explorer's Convert: each file becomes the chosen type (asked if to is None), saved beside it. Returns the
    files made."""
    paths = [p for p in paths if kind(p)]
    if not paths:
        return []
    names = os.path.basename(paths[0]) if len(paths) == 1 else f"{len(paths)} files"
    skipped = []
    if {kind(p) for p in paths} - {"pdf"} and any(kind(p) == "pdf" for p in paths):
        skipped = [p for p in paths if kind(p) == "pdf"]  # already PDFs
        paths = [p for p in paths if kind(p) != "pdf"]
        names = f"{len(paths)} files" if len(paths) > 1 else os.path.basename(paths[0])
    if to is None:
        dlg = Choice(win, f"Convert <b>{names}</b> to:", options_for(paths))
        if not dlg.exec():
            return []
        to = dlg.choice
    elif to not in {k for k, _, _ in options_for(paths)}:
        return []
    dpi = int(win.settings.value("convert/dpi", DPI))
    quality = int(win.settings.value("convert/jpg_quality", JPG_QUALITY))
    same = {"png": (".png",), "jpg": (".jpg", ".jpeg")}.get(to, ())
    paths = [p for p in paths if not p.lower().endswith(same)]  # already that type
    if not paths:
        return []
    if to == "pdf" and any(kind(p) == "office" for p in paths):
        office = [p for p in paths if convert.kind_of(p) in ("word", "excel", "powerpoint")]
        if office and not convert.show_note(win, win.settings, "office"):
            return []
        if any(convert.kind_of(p) == "excel" for p in paths) and not convert.show_note(win, win.settings, "excel"):
            return []
        if any(convert.kind_of(p) == "text" for p in paths) and not convert.show_note(win, win.settings, "text"):
            return []
    made, failed = [], []
    for src in paths:
        base = os.path.splitext(src)[0]
        try:
            if to == "word":
                dst = free_path(base + ".docx")
                error = convert.run(win, "word_out", src, dst, f"Converting {os.path.basename(src)} to Word…")
                if error == "":
                    break
                if error:
                    raise RuntimeError(error)
                made.append(dst)
            elif to in ("png", "jpg") and kind(src) == "pdf":
                doc = pymupdf.open(src)
                if doc.needs_pass:
                    raise RuntimeError("It's password protected: open it in Benelli Aerialist to save its pages.")
                win.setCursor(Qt.WaitCursor)
                try:
                    made += export_pages(doc, range(len(doc)), to, dpi, os.path.dirname(src),
                                         os.path.basename(base), quality)
                finally:
                    win.unsetCursor()
            elif to in ("png", "jpg"):
                dst = free_path(base + "." + to)
                _save_image(src, dst, to, quality)
                made.append(dst)
            elif kind(src) == "image":
                dst = free_path(base + ".pdf")
                image_to_pdf(src).save(dst, garbage=3, deflate=True)
                made.append(dst)
            else:
                dst = free_path(base + ".pdf")
                error = convert.run(win, "pdf", os.path.abspath(src), dst,
                                    f"Converting {os.path.basename(src)} to PDF…")
                if error == "":
                    break
                if error:
                    raise RuntimeError(error)
                made.append(dst)
        except Exception as e:
            failed.append(f"{os.path.basename(src)}: {e}")
    if failed:
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.warning(win, APP_NAME, "Some files couldn't be converted:\n\n" + "\n".join(failed))
    if skipped:
        win.toast.show_message(f"{len(skipped)} file(s) were already PDFs and were left as they are.", 4000)
    return made
