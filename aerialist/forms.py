"""Filling in PDF forms: the PDF's own fields (text boxes, tick boxes, option buttons, lists)
get a see-through box with a glowing green edge to type into or click. While the screen is open
the pages are drawn without the PDF's own field boxes, so nothing shows twice. Values are
written into the PDF when the Fill & Sign screen is finished (Done or Save)."""
import pymupdf
from PySide6.QtCore import Qt, QEvent, QObject, QPointF, QRectF
from PySide6.QtGui import QColor, QPainter, QPen, QPainterPath
from PySide6.QtWidgets import (QLineEdit, QPlainTextEdit, QComboBox, QAbstractButton,
                               QGraphicsDropShadowEffect)

EDGE = "#107C41"
EDGE_SOFT = "rgba(16, 124, 65, 128)"  # half see-through
FIELD_STYLE = (f"background: transparent; border: 1px solid {EDGE_SOFT}; border-radius: 2px;"
               " color: black; padding: 0px 2px;")
COMBO_STYLE = FIELD_STYLE.replace("transparent", "rgba(255, 255, 255, 140)")
READ_ONLY = 1
MULTILINE = 4096


def tab_order(page, widgets=None):
    """The page's form fields (widget xrefs) in the order Tab goes through them, as Adobe does it: row by row
    or column by column if the page asks for that, otherwise the order they're listed in the page."""
    widgets = list(page.widgets()) if widgets is None else widgets
    tabs = page.parent.xref_get_key(page.xref, "Tabs")[1]
    if tabs in ("/R", "/C"):
        m = page.rotation_matrix
        rects = {w.xref: pymupdf.Rect(w.rect) * m for w in widgets}
        key = (lambda r: (round(r.y0 / 4), r.x0)) if tabs == "/R" else (lambda r: (round(r.x0 / 4), r.y0))
        return [w.xref for w in sorted(widgets, key=lambda w: key(rects[w.xref]))]
    listed = [x for x, *_ in page.annot_xrefs()]
    rank = {x: n for n, x in enumerate(listed)}
    return [w.xref for w in sorted(widgets, key=lambda w: rank.get(w.xref, len(rank)))]


class TickBox(QAbstractButton):
    """A tick box or option button drawn over the page: just the edge, and the tick or dot."""

    def __init__(self, parent, round_):
        super().__init__(parent)
        self.round_ = round_
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor(16, 124, 65, 170), 1.5))  # emerald edge, like the text boxes
        if self.underMouse() or self.hasFocus():
            p.setBrush(QColor(16, 124, 65, 35))
        if self.round_:
            p.drawEllipse(r)
        else:
            p.drawRoundedRect(r, 2, 2)
        if self.isChecked():
            s = min(r.width(), r.height())
            if self.round_:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor("black"))
                p.drawEllipse(r.center(), s * 0.25, s * 0.25)
            else:
                c = r.center()
                path = QPainterPath(QPointF(c.x() - s * 0.3, c.y()))
                path.lineTo(c.x() - s * 0.08, c.y() + s * 0.24)
                path.lineTo(c.x() + s * 0.32, c.y() - s * 0.26)
                p.setPen(QPen(QColor("black"), max(1.5, s * 0.12), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                p.setBrush(Qt.NoBrush)
                p.drawPath(path)
        p.end()

    def enterEvent(self, e):
        self.update()

    def leaveEvent(self, e):
        self.update()


def glow(widget):
    effect = QGraphicsDropShadowEffect(widget)
    effect.setOffset(0, 0)
    effect.setBlurRadius(8)
    effect.setColor(QColor(16, 124, 65, 85))
    widget.setGraphicsEffect(effect)


class Field(QObject):
    """One form field on one page, with the editor that sits on top of it."""

    def __init__(self, layer, label, w, page):
        super().__init__(label)
        self.layer, self.label = layer, label
        self.xref, self.name, self.type = w.xref, w.field_name, w.field_type
        self.rect = pymupdf.Rect(w.rect) * page.rotation_matrix  # as shown on screen
        self.font_size = w.text_fontsize or 0
        t = self.type
        if t == pymupdf.PDF_WIDGET_TYPE_TEXT:
            multi = bool(w.field_flags & MULTILINE)
            self.editor = QPlainTextEdit(label) if multi else QLineEdit(label)
            value = w.field_value or ""
            if multi:
                self.editor.setPlainText(value)
                self.editor.textChanged.connect(lambda: layer.changed(self))
            else:
                self.editor.setText(value)
                if w.text_maxlen:
                    self.editor.setMaxLength(w.text_maxlen)
                self.editor.textEdited.connect(lambda *_: layer.changed(self))
        elif t in (pymupdf.PDF_WIDGET_TYPE_CHECKBOX, pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON):
            self.editor = TickBox(label, t == pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON)
            on = w.on_state()
            v = w.field_value
            self.editor.setChecked(v == on if on not in (None, False, "") else v not in (None, "", "Off", False))
            self.editor.toggled.connect(self._toggled)
        elif t in (pymupdf.PDF_WIDGET_TYPE_COMBOBOX, pymupdf.PDF_WIDGET_TYPE_LISTBOX):
            self.editor = QComboBox(label)
            choices = [c[1] if isinstance(c, (list, tuple)) else c for c in (w.choice_values or [])]
            self.editor.addItems([""] + choices)
            if t == pymupdf.PDF_WIDGET_TYPE_COMBOBOX and w.field_flags & (1 << 18):  # "Edit" flag: may type
                self.editor.setEditable(True)
            value = w.field_value if isinstance(w.field_value, str) else ""
            i = self.editor.findText(value)
            if i < 0 and value:
                self.editor.addItem(value)
                i = self.editor.count() - 1
            self.editor.setCurrentIndex(max(i, 0))
            self.editor.currentTextChanged.connect(lambda *_: layer.changed(self))
        else:
            self.editor = None
            return
        self.editor.setToolTip(w.field_label or w.field_name or "")
        if not isinstance(self.editor, TickBox):
            self.editor.setStyleSheet(COMBO_STYLE if isinstance(self.editor, QComboBox) else FIELD_STYLE)
        glow(self.editor)
        self.editor.setEnabled(not (w.field_flags & READ_ONLY))
        self.start = self.value()
        label.installEventFilter(self)  # follow the page when zooming
        self.place()
        self.editor.show()

    def eventFilter(self, obj, e):
        if e.type() == QEvent.Resize:
            self.place()
        return False

    def place(self):
        z, r = self.layer.view.zoom, self.rect
        self.editor.setGeometry(int(r.x0 * z), int(r.y0 * z), max(8, int(r.width * z)), max(8, int(r.height * z)))
        f = self.editor.font()
        size = self.font_size or min(r.height * 0.65, 12)  # 0 means "auto" in PDF forms
        f.setPixelSize(max(6, int(size * z)))
        self.editor.setFont(f)

    def _toggled(self, on):
        if on and self.type == pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON:
            for other in self.layer.fields:  # only one option of a group can be chosen
                if other is not self and other.name == self.name and other.type == self.type:
                    other.editor.blockSignals(True)
                    other.editor.setChecked(False)
                    other.editor.blockSignals(False)
        self.layer.changed(self)

    def set_value(self, v):
        e = self.editor
        e.blockSignals(True)
        if isinstance(e, QLineEdit):
            e.setText(v)
        elif isinstance(e, QPlainTextEdit):
            e.setPlainText(v)
        elif isinstance(e, TickBox):
            e.setChecked(bool(v))
        else:
            i = e.findText(v)
            if i < 0 and v:
                e.addItem(v)
                i = e.count() - 1
            e.setCurrentIndex(max(i, 0))
            if e.isEditable():
                e.setEditText(v)
        e.blockSignals(False)
        e.update()

    def value(self):
        e = self.editor
        if isinstance(e, QLineEdit):
            return e.text()
        if isinstance(e, QPlainTextEdit):
            return e.toPlainText()
        if isinstance(e, TickBox):
            return e.isChecked()
        return e.currentText()

    def writer(self):
        xref, name, kind, value = self.xref, self.name, self.type, self.value()

        def write(page):
            doc = page.parent
            for p in doc:
                for w in p.widgets():
                    if w.xref == xref:
                        w.field_value = value
                        w.update()
                    elif kind == pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON and value and w.field_name == name \
                            and w.field_type == kind:
                        w.field_value = False
                        w.update()
        return write


class FormLayer:
    """All the form fields of the open document, while the Sign screen is showing."""

    def __init__(self, view, on_change, checkpoint=lambda tag=None: None):
        self.view, self.on_change, self.checkpoint = view, on_change, checkpoint
        self.fields = []
        self.values = {}  # field -> value before the change being made (for Undo)
        self.rank = {}  # widget xref -> its place in the Tab order

    def build(self):
        self.clear()
        doc = self.view.doc
        if not doc or not doc.is_form_pdf:
            return
        self.rank = {}
        for i, page in enumerate(doc):
            if i >= len(self.view.labels):
                break
            for n, x in enumerate(tab_order(page)):
                self.rank[x] = (i, n)
            for w in page.widgets():
                if w.field_type in (pymupdf.PDF_WIDGET_TYPE_SIGNATURE, pymupdf.PDF_WIDGET_TYPE_BUTTON,
                                    pymupdf.PDF_WIDGET_TYPE_UNKNOWN):
                    continue
                f = Field(self, self.view.labels[i], w, page)
                if f.editor is not None:
                    self.fields.append(f)
        # Tab goes through the fields in reading order.
        self.view.set_hide_fields(bool(self.fields))
        order = self.ordered()
        for a, b in zip(order, order[1:]):
            a.editor.setTabOrder(a.editor, b.editor)
        self.values = {f: f.value() for f in self.fields}

    def clear(self):
        if self.fields:
            self.view.set_hide_fields(False)
        for f in self.fields:
            try:
                f.label.removeEventFilter(f)
                f.editor.deleteLater()
                f.deleteLater()
            except RuntimeError:
                pass  # went with its page
        self.fields = []
        self.values = {}

    def set_mouse_through(self, on):
        """While a signature, date or text is being placed, the mouse passes through the fields to the page
        (otherwise the see-through copy stops following it over a field, and it can't be dropped there)."""
        for f in self.fields:
            try:
                f.editor.setAttribute(Qt.WA_TransparentForMouseEvents, on)
            except RuntimeError:
                pass

    def changed(self, field=None):
        # Typing in one field is one Undo step; the snapshot is of the values before this change.
        self.checkpoint(("field", field))
        self.values = {f: f.value() for f in self.fields}
        self.on_change()

    def snapshot(self):
        return [(f, self.values.get(f)) for f in self.fields]

    def set_values(self, snapshot):
        for f, v in snapshot:
            if f in self.fields and f.value() != v:
                f.set_value(v)
        self.values = {f: f.value() for f in self.fields}

    def edited(self):
        return [f for f in self.fields if f.value() != f.start]

    def ordered(self):
        return sorted(self.fields, key=lambda f: self.rank.get(f.xref, (f.label.index, 0)))

    def counts(self):
        """(filled in, total) over the fields that can be changed."""
        usable = [f for f in self.fields if f.editor.isEnabled()]
        return sum(1 for f in usable if f.value() not in ("", False)), len(usable)

    def next_empty(self):
        """Go to the next empty field after the one being typed in (or the first), and focus it."""
        order = [f for f in self.ordered() if f.editor.isEnabled()]
        if not order:
            return None
        here = next((n for n, f in enumerate(order) if f.editor.hasFocus()), -1)
        rest = order[here + 1:] + order[:here + 1]
        target = next((f for f in rest if f.value() in ("", False)), rest[0])
        self.view.show_rect(target.label.index, target.rect)
        target.editor.setFocus()
        return target

    def take(self):
        """Writers for the fields that were changed, as (page index, writer)."""
        return [(f.label.index, f.writer()) for f in self.edited()]
