"""Background page rendering so large or drawing-heavy PDFs never freeze the window.

Rendering runs in a separate process: PyMuPDF holds Python's GIL while drawing, so a
plain thread would still stall the window on heavy pages.
"""
import multiprocessing
import threading

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage

from .render_worker import _worker


class Renderer(QObject):
    """Renders pages in worker processes that each have their own copy of the document.

    Two job lists: "view" jobs (what is on screen, replaced on every scroll/zoom) always
    run before "thumb" jobs. Results arrive through the `rendered` signal on the GUI thread.
    """
    rendered = Signal(str, int, float, QImage, int)  # kind, page index, zoom, image, generation
    detailed = Signal(int, float, object, QImage, int)  # page index, zoom, clip (x0, y0, x1, y1), image, generation

    def __init__(self, path, password=None, workers=2):
        super().__init__()
        ctx = multiprocessing.get_context("spawn")
        self._view_jobs, self._thumb_jobs = [], []
        self._reload = {}  # worker number -> (path, password) it still has to switch to
        self._patches = {}  # worker number -> [(page index, content stream)] still to send
        self._gen = 0  # bumped on reload so results for the old document are dropped
        self.hide_fields = False
        self._cond = threading.Condition()
        self._stopped = False
        # Two workers, so the page on screen and the next one (or a thumbnail) draw at the same time.
        self._workers = []
        for n in range(workers):
            conn, child = ctx.Pipe()
            proc = ctx.Process(target=_worker, args=(path, password, child), daemon=True)
            proc.start()
            thread = threading.Thread(target=self._run, args=(n, conn), daemon=True)
            self._workers.append((conn, proc, thread))
            thread.start()

    def set_view_jobs(self, jobs):
        """jobs: list of (page index, zoom) or (page index, zoom, clip), most important first. A clip
        (x0, y0, x1, y1 in PDF points) draws just that part of the page, for big pages zoomed right in."""
        with self._cond:
            self._view_jobs = list(jobs)
            self._cond.notify_all()

    def set_thumb_jobs(self, jobs):
        with self._cond:
            self._thumb_jobs = list(jobs)
            self._cond.notify_all()

    def reload(self, path, password=None):
        """Point the worker at a new file (after an edit) without restarting it."""
        with self._cond:
            self._reload = {n: (path, password) for n in range(len(self._workers))}
            self._patches = {}
            self._view_jobs, self._thumb_jobs = [], []
            self._gen += 1
            self._cond.notify_all()

    def patch(self, index, data):
        """Draw page index with these drawing instructions from now on (until the next reload)."""
        with self._cond:
            for n in range(len(self._workers)):
                self._patches.setdefault(n, []).append((index, data))
            self._gen += 1
            self._view_jobs = []
            self._cond.notify_all()

    def current(self, gen):
        """False for a drawing made before the last reload or field switch (it may still be queued)."""
        return gen == self._gen

    def set_hide_fields(self, hide):
        """Draw pages without their form fields (Fill & Sign shows its own boxes there)."""
        with self._cond:
            self.hide_fields = hide
            self._view_jobs = []
            self._gen += 1

    def stop(self):
        with self._cond:
            self._stopped = True
            self._cond.notify_all()
        for conn, proc, thread in self._workers:
            thread.join(timeout=5)
            try:
                conn.send(None)
            except OSError:
                pass
        for conn, proc, thread in self._workers:
            proc.join(timeout=2)
            if proc.is_alive():
                proc.kill()

    def _run(self, n, conn):
        while True:
            with self._cond:
                while not (self._stopped or n in self._reload or self._patches.get(n) or self._view_jobs
                           or self._thumb_jobs):
                    self._cond.wait()
                if self._stopped:
                    return
                if n in self._reload:
                    msg = ("open",) + self._reload.pop(n)
                elif self._patches.get(n):
                    msg = ("patch",) + self._patches[n].pop(0)
                else:
                    kind, jobs = ("view", self._view_jobs) if self._view_jobs else ("thumb", self._thumb_jobs)
                    index, zoom, *clip = jobs.pop(0)
                    clip = clip[0] if clip else None
                    msg, gen = ("render", index, zoom, self.hide_fields and kind == "view", clip), self._gen
            try:
                conn.send(msg)
                if msg[0] in ("open", "patch"):
                    continue
                result = conn.recv()  # waits without holding the GIL
            except (EOFError, OSError):
                return  # worker went away (closing)
            if result is None:
                continue  # a broken page shouldn't stop the others
            w, h, stride, data = result
            img = QImage(data, w, h, stride, QImage.Format_RGB888).copy()
            with self._cond:
                if self._stopped:
                    return
                if gen != self._gen:
                    continue  # rendered from the document before an edit
            if clip:
                self.detailed.emit(index, zoom, clip, img, gen)
            else:
                self.rendered.emit(kind, index, zoom, img, gen)
