"""Comments: sticky notes, highlight / underline / strikethrough on text, and replies.

They are saved as standard PDF annotations (the kind Adobe Acrobat and Nitro make and read), so comments made
here show in their comment lists and theirs show here. Replies are notes that point at the comment they
answer (/IRT); their own icon is left blank so it doesn't sit on top of the page twice."""
import getpass
import os
from datetime import datetime

import pymupdf
from PySide6.QtCore import Qt, QRectF, QTimer, Signal
from PySide6.QtGui import QColor, QTextCursor
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMenu, QPlainTextEdit, QPushButton, QScrollArea, QToolButton, QVBoxLayout,
    QWidget,
)

from . import theme
from .icons import icon, pixmap

A = pymupdf
KINDS = {  # annotation type -> how it's named in the list (others, like links and form fields, aren't comments)
    A.PDF_ANNOT_TEXT: "Note", A.PDF_ANNOT_HIGHLIGHT: "Highlight", A.PDF_ANNOT_UNDERLINE: "Underline",
    A.PDF_ANNOT_STRIKE_OUT: "Strikethrough", A.PDF_ANNOT_SQUIGGLY: "Squiggly underline",
    A.PDF_ANNOT_FREE_TEXT: "Text box", A.PDF_ANNOT_SQUARE: "Rectangle", A.PDF_ANNOT_CIRCLE: "Oval",
    A.PDF_ANNOT_LINE: "Line", A.PDF_ANNOT_POLYGON: "Shape", A.PDF_ANNOT_POLY_LINE: "Lines",
    A.PDF_ANNOT_INK: "Drawing", A.PDF_ANNOT_STAMP: "Stamp", A.PDF_ANNOT_CARET: "Insert text",
    A.PDF_ANNOT_FILE_ATTACHMENT: "Attached file", A.PDF_ANNOT_SOUND: "Sound",
}
MARKUP = {"highlight": A.PDF_ANNOT_HIGHLIGHT, "underline": A.PDF_ANNOT_UNDERLINE, "strike": A.PDF_ANNOT_STRIKE_OUT}
COLORS = {  # Acrobat's defaults
    A.PDF_ANNOT_TEXT: (1, 0.82, 0.0), A.PDF_ANNOT_HIGHLIGHT: (1, 0.9, 0.0),
    A.PDF_ANNOT_UNDERLINE: (0.0, 0.6, 0.25), A.PDF_ANNOT_STRIKE_OUT: (0.85, 0.1, 0.1),
}
ICONS = {A.PDF_ANNOT_TEXT: "note", A.PDF_ANNOT_HIGHLIGHT: "highlight", A.PDF_ANNOT_UNDERLINE: "underline",
         A.PDF_ANNOT_STRIKE_OUT: "strike"}
TOOLS = [("note", "note", "Sticky note"), ("highlight", "highlight", "Highlight text"),
         ("underline", "underline", "Underline text"), ("strike", "strike", "Strike through text")]
HINTS = {"note": "Click on the page where the note goes.",
         "highlight": "Drag across text to highlight it.", "underline": "Drag across text to underline it.",
         "strike": "Drag across text to strike it through."}


def author(settings):
    name = str(settings.value("comments/author", "") or "").strip()
    return name or os.environ.get("USERNAME") or getpass.getuser() or "Me"


def _shown_date(pdf_date):
    """'D:20261024152233-07'00'' -> 'Oct 24, 3:22 PM' (or with the year when it isn't this year)."""
    digits = "".join(c for c in (pdf_date or "")[2:16] if c.isdigit())
    try:
        d = datetime.strptime(digits[:14].ljust(14, "0"), "%Y%m%d%H%M%S")
    except ValueError:
        return ""
    day = f"{d:%b} {d.day}" + (f", {d.year}" if d.year != datetime.now().year else "")
    return f"{day}, {d.hour % 12 or 12}:{d:%M} {'AM' if d.hour < 12 else 'PM'}"


def _marked_text(page, annot):
    """The words a highlight (or underline, strikethrough) covers."""
    v = annot.vertices or []
    boxes = [pymupdf.Quad(v[i:i + 4]).rect for i in range(0, len(v) - 3, 4)] or [annot.rect]
    words = []
    for w in page.get_text("words", clip=annot.rect):
        mid = pymupdf.Point((w[0] + w[2]) / 2, (w[1] + w[3]) / 2)
        if any(mid in b for b in boxes):
            words.append(w[4])
    return " ".join(words)[:200]


def shown_rect(annot):
    """Where an annotation is on screen (page points)."""
    return annot.rect * annot.parent.rotation_matrix


class Comment:
    def __init__(self, page_index, annot, quote=""):
        info = annot.info
        self.page, self.xref, self.type = page_index, annot.xref, annot.type[0]
        self.kind = KINDS.get(self.type, annot.type[1])
        self.author = info.get("title", "") or ""
        self.text = info.get("content", "") or ""
        self.date = _shown_date(info.get("modDate") or info.get("creationDate"))
        self.rect = shown_rect(annot)
        self.quote = quote
        self.parent_xref = annot.irt_xref
        self.replies = []


def list_comments(doc):
    """Every comment in the document, in page order, each with its replies (oldest first)."""
    out = []
    for page in doc:
        if not page.first_annot:
            continue
        found, parent = {}, {}
        for annot in page.annots():
            if annot.type[0] not in KINDS:
                continue
            quote = ""
            if annot.type[0] in MARKUP.values():
                quote = _marked_text(page, annot)
            c = Comment(page.number, annot, quote)
            found[c.xref] = c
            if annot.irt_xref:
                parent[c.xref] = annot.irt_xref

        def root(x):  # a reply to a reply belongs to the same thread
            seen = set()
            while x in parent and parent[x] in found and x not in seen:
                seen.add(x)
                x = parent[x]
            return x
        tops = []
        for x, c in found.items():
            if x in parent and parent[x] in found:
                found[root(x)].replies.append(c)
            else:
                tops.append(c)
        tops.sort(key=lambda c: (round(c.rect.y0), c.rect.x0))
        out.extend(tops)
    return out


def _stamp(annot, who, text=None, new=False):
    now = pymupdf.get_pdf_now()
    info = {"modDate": now}
    if new:
        info.update(title=who, creationDate=now)
    if text is not None:
        info["content"] = text
    annot.set_info(**info)


def _blank_icon(doc, annot):
    """A reply has no icon of its own on the page: it shows inside its comment's thread."""
    kind, ref = doc.xref_get_key(annot.xref, "AP/N")
    if kind == "xref":
        doc.update_stream(int(ref.split()[0]), b" ")


def add_note(doc, page_index, point, text, who):
    page = doc[page_index]
    # The icon's tail is at its bottom right: that corner goes where you clicked.
    # A note's icon stays upright on a turned page, hanging from the corner its rectangle starts at.
    at = note_rect(point).tl * page.derotation_matrix
    annot = page.add_text_annot(at, text, icon="Comment")
    annot.set_rect(pymupdf.Rect(at.x, at.y, at.x + 16, at.y + 16))
    annot.set_colors(stroke=COLORS[A.PDF_ANNOT_TEXT])
    _stamp(annot, who, new=True)
    annot.update()
    return annot.xref


def note_rect(point):
    """Where a note's 16-point icon goes for a click (as shown on screen): just above and left of it."""
    return pymupdf.Rect(point.x - 16, point.y - 16, point.x, point.y)


def add_markup(doc, page_index, kind, rects, text, who):
    """rects: one rectangle per line of the chosen words, as shown on screen."""
    page = doc[page_index]
    quads = [(pymupdf.Rect(r) * page.derotation_matrix).quad for r in rects]
    adder = {"highlight": page.add_highlight_annot, "underline": page.add_underline_annot,
             "strike": page.add_strikeout_annot}[kind]
    annot = adder(quads=quads)
    annot.set_colors(stroke=COLORS[MARKUP[kind]])
    _stamp(annot, who, text, new=True)
    annot.update()
    return annot.xref


def set_text(doc, page_index, xref, text):
    page = doc[page_index]  # (kept: an annotation needs its page alive)
    annot = page.load_annot(xref)
    _stamp(annot, None, text)
    annot.update()
    if annot.irt_xref:
        _blank_icon(doc, annot)


def add_reply(doc, page_index, parent_xref, text, who):
    page = doc[page_index]
    parent = page.load_annot(parent_xref)
    reply = page.add_text_annot(parent.rect.tl, text, icon="Comment")
    reply.set_irt_xref(parent_xref)
    _stamp(reply, who, new=True)
    reply.update()
    _blank_icon(doc, reply)
    return reply.xref


def delete(doc, page_index, xref):
    """Delete a comment and every reply under it."""
    page = doc[page_index]
    doomed, grew = {xref}, True
    while grew:
        grew = False
        for annot in page.annots():
            if annot.irt_xref in doomed and annot.xref not in doomed:
                doomed.add(annot.xref)
                grew = True
    for x in doomed:
        annot = page.load_annot(x)
        if annot is not None:
            page.delete_annot(annot)


def word_rects(page):
    """The page's words in reading order, as shown on screen: [(Rect, (block, line))]."""
    m = page.rotation_matrix
    return [(pymupdf.Rect(w[:4]) * m, (w[5], w[6])) for w in page.get_text("words", sort=False)]


def line_rects(words):
    """Join chosen words into one rectangle per line."""
    lines = {}
    for r, key in words:
        lines[key] = lines[key] | r if key in lines else pymupdf.Rect(r)
    return list(lines.values())


class CommentTool:
    """Placing a comment: the page view's mouse goes here while a comment tool is picked."""
    SELECT = QColor(16, 124, 65, 60)

    def __init__(self, panel):
        self.panel, self.view = panel, panel.view
        self.kind = None
        self._words, self._start, self._chosen, self._label = [], None, [], None

    # The page view's hook interface.
    def press(self, label, pos):
        z = self.view.zoom
        point = pymupdf.Point(pos.x() / z, pos.y() / z)
        if self.kind == "note":
            self.panel.start_note(label.index, point)
            return
        self._label = label
        self._words = word_rects(self.view.doc[label.index])
        self._start = self._nearest(point)
        self._update(point)

    def move(self, label, pos):
        if self.kind != "note" and self._label is label and self._start is not None:
            z = self.view.zoom
            self._update(pymupdf.Point(pos.x() / z, pos.y() / z))
        label.setCursor(Qt.CrossCursor if self.kind == "note" else Qt.IBeamCursor)

    def release(self, label, pos):
        if self._label is None:
            return
        chosen, index = self._chosen, self._label.index
        self._clear()
        if chosen:
            self.panel.add_markup(index, self.kind, line_rects(chosen))
        elif self.view.doc[index].get_text("words") == []:
            self.panel.win.toast.show_message("This page has no text to mark (it may be a scan). "
                                              "Use a sticky note instead.", 3500)

    def leave(self, label):
        pass

    def wheel(self, event):
        return False

    def scrolled(self):
        pass

    def _nearest(self, point):
        if not self._words:
            return None
        for i, (r, _) in enumerate(self._words):
            if point in r:
                return i
        return min(range(len(self._words)),
                   key=lambda i: abs(self._words[i][0].y0 + self._words[i][0].y1 - 2 * point.y) * 3
                   + abs(self._words[i][0].x0 + self._words[i][0].x1 - 2 * point.x))

    def _update(self, point):
        if self._start is None:
            return
        end = self._nearest(point)
        a, b = sorted((self._start, end))
        # A click without dragging over a word marks nothing.
        start_rect = self._words[self._start][0]
        if a == b and point not in start_rect:
            self._chosen = []
        else:
            self._chosen = self._words[a:b + 1]
        self._label.marks = [(r, self.SELECT) for r in line_rects(self._chosen)]
        self._label.update()

    def _clear(self):
        if self._label is not None:
            try:
                self._label.marks = []
                self._label.update()
            except RuntimeError:
                pass
        self._label, self._start, self._chosen, self._words = None, None, [], []


class Editor(QFrame):
    """Typing box for a new comment, a reply or a change: Post / Cancel (Ctrl+Enter posts)."""
    posted = Signal(str)
    cancelled = Signal()

    def __init__(self, text="", button="Post", placeholder="Add a comment…"):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 0)
        lay.setSpacing(6)
        self.box = QPlainTextEdit(text)
        self.box.setPlaceholderText(placeholder)
        self.box.setFixedHeight(76)
        self.box.setTabChangesFocus(True)
        self.box.keyPressEvent = self._key
        lay.addWidget(self.box)
        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.cancelled.emit)
        self.post = QPushButton(button)
        self.post.setProperty("primary", True)
        self.post.clicked.connect(lambda: self.posted.emit(self.box.toPlainText().strip()))
        row.addWidget(cancel)
        row.addWidget(self.post)
        lay.addLayout(row)
        QTimer.singleShot(0, self._focus)

    def _focus(self):
        self.box.setFocus()
        self.box.moveCursor(QTextCursor.End)

    def _key(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter) and e.modifiers() & Qt.ControlModifier:
            self.posted.emit(self.box.toPlainText().strip())
            return
        if e.key() == Qt.Key_Escape:
            self.cancelled.emit()
            return
        QPlainTextEdit.keyPressEvent(self.box, e)


def _small(text, color="{SUBTLE}"):
    l = QLabel(text)
    theme.style(l, f"color: {color}; font-size: 11px;")
    return l


class Card(QFrame):
    """One comment and its replies."""
    clicked = Signal(object)

    def __init__(self, panel, c):
        super().__init__()
        self.panel, self.c = panel, c
        self.setObjectName("commentCard")
        self.setProperty("selected", False)
        self.setCursor(Qt.PointingHandCursor)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(lambda pos: self.panel.card_menu(self, self.c, pos))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(3)
        top = QHBoxLayout()
        top.setSpacing(6)
        mark = QLabel()
        rgb = COLORS.get(c.type, (0.42, 0.42, 0.44))
        mark.setPixmap(pixmap(ICONS.get(c.type, "comment"), 14, QColor.fromRgbF(*rgb).darker(115).name()))
        top.addWidget(mark)
        who = QLabel(c.author or "Unknown")
        who.setStyleSheet("font-weight: 600;")
        top.addWidget(who)
        top.addStretch(1)
        top.addWidget(_small(f"p. {c.page + 1}"))
        lay.addLayout(top)
        lay.addWidget(_small(f"{c.kind}{' · ' + c.date if c.date else ''}"))
        if c.quote:
            q = QLabel(f"“{c.quote}”")
            q.setWordWrap(True)
            theme.style(q, "color: {MUTED}; font-style: italic;")
            lay.addWidget(q)
        self.body = QLabel(c.text)
        self.body.setWordWrap(True)
        self.body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.body.setVisible(bool(c.text))
        lay.addWidget(self.body)
        for r in c.replies:
            lay.addWidget(self._reply(r))
        self.actions = QWidget()
        row = QHBoxLayout(self.actions)
        row.setContentsMargins(0, 4, 0, 0)
        row.setSpacing(4)
        for text, slot in (("Reply", lambda: panel.open_editor(self, "reply")),
                           ("Edit" if c.text else "Add comment", lambda: panel.open_editor(self, "edit")),
                           ("Delete", lambda: panel.delete(self.c))):
            b = QPushButton(text)
            b.setObjectName("link")
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch(1)
        self.actions.hide()
        lay.addWidget(self.actions)
        self.editor_slot = QVBoxLayout()
        lay.addLayout(self.editor_slot)

    def _reply(self, r):
        w = QFrame()
        w.setObjectName("commentReply")
        w.setContextMenuPolicy(Qt.CustomContextMenu)
        w.customContextMenuRequested.connect(lambda pos: self.panel.card_menu(w, r, pos))
        l = QVBoxLayout(w)
        l.setContentsMargins(10, 4, 0, 2)
        l.setSpacing(1)
        head = QHBoxLayout()
        who = QLabel(r.author or "Unknown")
        who.setStyleSheet("font-weight: 600;")
        head.addWidget(who)
        head.addStretch(1)
        head.addWidget(_small(r.date))
        l.addLayout(head)
        t = QLabel(r.text)
        t.setWordWrap(True)
        t.setTextInteractionFlags(Qt.TextSelectableByMouse)
        l.addWidget(t)
        w.setToolTip("Right-click to change or delete this reply")
        return w

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit(self)
        super().mousePressEvent(e)

    def set_selected(self, on):
        self.setProperty("selected", on)
        self.style().unpolish(self)
        self.style().polish(self)
        self.actions.setVisible(on)


class CommentsPanel(QFrame):
    """The comments list beside the pages, with the comment tools at its top."""
    closed = Signal()

    def __init__(self, win):
        super().__init__()
        self.win, self.view = win, win.view
        self.setObjectName("commentsPanel")
        self.setFixedWidth(300)
        self.tool = CommentTool(self)
        self.cards, self.selected, self._pending, self._comments = [], None, None, []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        head = QHBoxLayout()
        head.setContentsMargins(14, 10, 8, 4)
        title = QLabel("Comments")
        title.setStyleSheet("font-size: 14px; font-weight: 600;")
        head.addWidget(title)
        head.addSpacing(6)
        self.count = QLabel("")
        self.count.setObjectName("chip")
        head.addWidget(self.count)
        head.addStretch(1)
        close = QToolButton()
        close.setIcon(icon("close", size=16))
        close.setToolTip("Hide comments")
        close.setAutoRaise(True)
        close.clicked.connect(self.closed.emit)
        head.addWidget(close)
        lay.addLayout(head)

        tools = QHBoxLayout()
        tools.setContentsMargins(10, 2, 10, 6)
        tools.setSpacing(4)
        self.tool_buttons = {}
        for key, name, tip in TOOLS:
            b = QToolButton()
            b.setIcon(icon(name))
            b.setToolTip(tip)
            b.setCheckable(True)
            b.setObjectName("commentTool")
            b.setFixedSize(38, 34)
            b.clicked.connect(lambda on, k=key: self.pick(k if on else None))
            tools.addWidget(b)
            self.tool_buttons[key] = b
        tools.addStretch(1)
        lay.addLayout(tools)
        self.hint = QLabel("")
        self.hint.setWordWrap(True)
        theme.style(self.hint, "color: {ACCENT}; padding: 0 14px 6px 14px;")
        self.hint.hide()
        lay.addWidget(self.hint)
        line = QFrame()
        line.setFixedHeight(1)
        theme.style(line, "background: {LINE_SOFT};")
        lay.addWidget(line)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.list = QWidget()
        self.list.setObjectName("commentList")
        self.list_lay = QVBoxLayout(self.list)
        self.list_lay.setContentsMargins(10, 10, 10, 10)
        self.list_lay.setSpacing(8)
        self.scroll.setWidget(self.list)
        lay.addWidget(self.scroll, 1)

    # ---- tools ----------------------------------------------------------
    def pick(self, kind):
        """Pick a comment tool (None puts it down)."""
        self._cancel_pending()
        if kind and getattr(self.window(), "snipper", None):
            self.window().snipper.set_on(False)  # one page tool at a time
        if kind and getattr(self.window(), "selector", None):
            self.window().selector.clear()
        self.tool.kind = kind
        for k, b in self.tool_buttons.items():
            b.setChecked(k == kind)
        self.view.page_mouse = self.tool if kind else None
        self.hint.setText(HINTS.get(kind, ""))
        self.hint.setVisible(bool(kind))
        if not kind:
            for lbl in self.view.labels:
                lbl.unsetCursor()

    def armed(self):
        return self.tool.kind is not None or self._pending is not None

    # ---- the list -------------------------------------------------------
    def refresh(self, keep=None):
        """Rebuild the list from the document. keep: (page, xref) of the comment to select afterwards."""
        if keep is None and self.selected is not None:
            keep = (self.selected.c.page, self.selected.c.xref)
        self._pending = None
        while self.list_lay.count():
            w = self.list_lay.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        self.cards, self.selected = [], None
        doc = self.win.doc
        self._comments = list_comments(doc) if doc else []
        n = len(self._comments)
        self.count.setText(str(n) if n else "")
        self.count.setVisible(bool(n))
        if not n:
            empty = QLabel("No comments yet.\n\nPick a tool above: a sticky note goes wherever you click, and "
                           "highlight, underline and strikethrough go on text you drag across.")
            empty.setWordWrap(True)
            theme.style(empty, "color: {SUBTLE};")
            self.list_lay.addWidget(empty)
        for c in self._comments:
            card = Card(self, c)
            card.clicked.connect(self.select)
            self.list_lay.addWidget(card)
            self.cards.append(card)
        self.list_lay.addStretch(1)
        if keep is not None:
            for card in self.cards:
                if (card.c.page, card.c.xref) == keep or keep[1] in {r.xref for r in card.c.replies} \
                        and card.c.page == keep[0]:
                    self.select(card, scroll_page=False)
                    break

    def count_comments(self):
        return len(self._comments)

    def select(self, card, scroll_page=True):
        if self.selected is not None and self.selected is not card:
            try:
                self.selected.set_selected(False)
                self._close_editor(self.selected)
            except RuntimeError:
                pass
        self.selected = card
        card.set_selected(True)
        QTimer.singleShot(0, lambda: self._ensure_visible(card))
        if scroll_page:
            self.view.show_rect(card.c.page, card.c.rect)
            self.flash(card.c.page, card.c.rect)

    def _ensure_visible(self, card):
        try:
            self.scroll.ensureWidgetVisible(card, 0, 10)
        except RuntimeError:
            pass

    def select_xref(self, page, xref):
        for card in self.cards:
            if card.c.page == page and (card.c.xref == xref or xref in {r.xref for r in card.c.replies}):
                self.select(card, scroll_page=False)
                self.flash(page, card.c.rect)
                return True
        return False

    def flash(self, page, rect):
        if not 0 <= page < len(self.view.labels):
            return
        lbl = self.view.labels[page]
        r = pymupdf.Rect(rect)
        if r.width < 20:  # a note's icon: ring it, not just its 16-point square
            r = pymupdf.Rect(r.x0 - 4, r.y0 - 4, r.x1 + 4, r.y1 + 4)
        lbl.marks = [(r, QColor(16, 124, 65, 70))]
        lbl.update()

        def off():
            try:
                lbl.marks = []
                lbl.update()
            except RuntimeError:
                pass
        QTimer.singleShot(1200, off)

    # ---- changes (each one can be undone) -------------------------------
    def _change(self, page, fn, message="", select=True):
        """Run fn(doc) -> xref to select, as one undoable change to the document."""
        result = {}

        def change(doc):
            result["xref"] = fn(doc)
        self.win.edit_page(change, page, message)
        x = result.get("xref")
        self.refresh(keep=(page, x) if select and x else None)

    def start_note(self, page, point):
        """A click with the note tool: write its text in the list, then Post puts it on the page."""
        self._cancel_pending()
        lbl = self.view.labels[page]
        lbl.marks = [(note_rect(point), QColor(255, 209, 0, 200))]
        lbl.update()
        box = QFrame()
        box.setObjectName("commentCard")
        box.setProperty("selected", True)
        bl = QVBoxLayout(box)
        bl.setContentsMargins(10, 8, 10, 8)
        who = QLabel(author(self.win.settings))
        who.setStyleSheet("font-weight: 600;")
        bl.addWidget(who)
        bl.addWidget(_small(f"New note · page {page + 1}"))
        ed = Editor(placeholder="Type your note…")
        bl.addWidget(ed)
        self._pending = (page, point, box, lbl)
        ed.posted.connect(lambda text: self._post_note(text))
        ed.cancelled.connect(self._cancel_pending)
        self.list_lay.insertWidget(0, box)
        self.scroll.verticalScrollBar().setValue(0)
        self.pick_after_note()

    def pick_after_note(self):
        # The note tool is put down after one note (like Acrobat); the typing box has the focus.
        self.tool.kind = None
        self.view.page_mouse = None
        for b in self.tool_buttons.values():
            b.setChecked(False)
        self.hint.hide()

    def _post_note(self, text):
        if self._pending is None:
            return
        page, point, box, lbl = self._pending
        self._cancel_pending()
        if not text:
            return
        who = author(self.win.settings)
        self._change(page, lambda doc: add_note(doc, page, point, text, who), "Note added")

    def _cancel_pending(self):
        if self._pending is None:
            return
        page, point, box, lbl = self._pending
        self._pending = None
        try:
            lbl.marks = []
            lbl.update()
        except RuntimeError:
            pass
        box.deleteLater()

    def add_markup(self, page, kind, rects):
        who = author(self.win.settings)
        self._change(page, lambda doc: add_markup(doc, page, kind, rects, "", who))

    def open_editor(self, card, what, target=None):
        self._close_editor(card)
        c = target or card.c
        if what == "reply":
            ed = Editor(button="Reply", placeholder="Write a reply…")
            ed.posted.connect(lambda text: text and self._change(
                card.c.page, lambda doc: (add_reply(doc, card.c.page, c.xref, text, author(self.win.settings)),
                                          card.c.xref)[1]))
        else:
            ed = Editor(c.text, button="Save")
            ed.posted.connect(lambda text: self._change(
                card.c.page, lambda doc: (set_text(doc, card.c.page, c.xref, text), card.c.xref)[1]))
        ed.cancelled.connect(lambda: self._close_editor(card))
        card.editor_slot.addWidget(ed)
        card.actions.hide()

    def _close_editor(self, card):
        try:
            while card.editor_slot.count():
                w = card.editor_slot.takeAt(0).widget()
                if w is not None:
                    w.deleteLater()
            card.actions.setVisible(card is self.selected)
        except RuntimeError:
            pass

    def delete(self, c):
        what = "this comment and its replies" if c.replies else "this reply" if c.parent_xref \
            else "this comment"
        self._change(c.page, lambda doc: delete(doc, c.page, c.xref), f"Deleted {what}", select=False)

    def card_menu(self, widget, c, pos):
        card = widget if isinstance(widget, Card) else widget.parent()
        while card is not None and not isinstance(card, Card):
            card = card.parent()
        menu = QMenu(self)
        if card is not None and c is card.c:
            menu.addAction("Reply", lambda: (self.select(card, False), self.open_editor(card, "reply")))
        menu.addAction("Edit text", lambda: (self.select(card, False), self.open_editor(card, "edit", c)))
        menu.addAction("Delete", lambda: self.delete(c))
        menu.exec(widget.mapToGlobal(pos))
