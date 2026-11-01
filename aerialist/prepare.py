"""Prepare Form: making a PDF's fillable fields. Text boxes and tick boxes are drawn on the page; the panel on
the right lists each page's fields in the order Tab goes through them (drag to change it) and has the
selected field's settings: its name, default text, whether it must be filled in, and so on.

Everything is a real PDF form field, so Adobe, Nitro and Fill & Sign fill them in. Each change is written
into the document straight away (Ctrl+Z takes it back); Cancel puts the form back as it was."""
import re

import pymupdf
from PySide6.QtCore import Qt, QRectF, QTimer
from PySide6.QtGui import QColor, QPen, QFont, QFontMetrics
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPushButton, QVBoxLayout, QWidget,
)

from . import theme
from .forms import tab_order
from .icons import icon

W = pymupdf
TEXT, CHECK = W.PDF_WIDGET_TYPE_TEXT, W.PDF_WIDGET_TYPE_CHECKBOX
KINDS = {"text": TEXT, "check": CHECK}
TYPE_NAMES = {TEXT: "Text box", CHECK: "Tick box", W.PDF_WIDGET_TYPE_RADIOBUTTON: "Option button",
              W.PDF_WIDGET_TYPE_COMBOBOX: "Drop-down list", W.PDF_WIDGET_TYPE_LISTBOX: "List",
              W.PDF_WIDGET_TYPE_SIGNATURE: "Signature box", W.PDF_WIDGET_TYPE_BUTTON: "Button"}
TYPE_ICONS = {TEXT: "textfield", CHECK: "checkbox", W.PDF_WIDGET_TYPE_RADIOBUTTON: "checkbox",
              W.PDF_WIDGET_TYPE_COMBOBOX: "chevron", W.PDF_WIDGET_TYPE_LISTBOX: "chevron",
              W.PDF_WIDGET_TYPE_SIGNATURE: "sign"}
BASE_NAMES = {"text": "Text", "check": "Check"}
DEFAULT_SIZES = {"text": (160, 22), "check": (14, 14)}  # a plain click makes one this size
MIN_SIZES = {TEXT: (16, 8), CHECK: (6, 6)}
FONT_SIZES = [8, 9, 10, 11, 12, 14, 16, 18, 20, 24]
REQUIRED, MULTILINE = 2, 4096
HANDLE = 8  # px: the resize handle at the selected field's corner
HINTS = {"text": "Drag a box where people should type (or click for a standard size). The tool stays on for "
                 "the next one; Esc to stop.",
         "check": "Click where a tick box goes (or drag to size it). The tool stays on for the next one; "
                  "Esc to stop."}


# ---- the PDF side ------------------------------------------------------------
def _ref(value):
    return int(value.split()[0])


def field_xref(doc, xref):
    """The field a box belongs to, which holds its name, flags and value: the box itself or its parent."""
    seen = set()
    while doc.xref_get_key(xref, "T")[0] == "null" and xref not in seen:
        seen.add(xref)
        kind, value = doc.xref_get_key(xref, "Parent")
        if kind != "xref":
            break
        xref = _ref(value)
    return xref


def _flags(doc, xref):
    value = doc.xref_get_key(field_xref(doc, xref), "Ff")[1]
    return int(value) if value.lstrip("-").isdigit() else 0


class Info:
    """One field box as the panel and the page show it."""

    def __init__(self, page_index, w, page):
        self.page, self.xref, self.type = page_index, w.xref, w.field_type
        self.name = w.field_name or ""
        self.rect = pymupdf.Rect(w.rect) * page.rotation_matrix  # as shown on screen
        self.flags = w.field_flags or 0
        self.size = w.text_fontsize or 0
        self.hint = w.field_label or ""
        v = w.field_value
        if self.type in (CHECK, W.PDF_WIDGET_TYPE_RADIOBUTTON):
            self.value = v not in (None, "", "Off", False)
        else:
            self.value = v if isinstance(v, str) else ""
        self.number = 0  # place in the Tab order, from 1 across the whole document


def list_fields(doc):
    out = []
    for i, page in enumerate(doc):
        widgets = {w.xref: w for w in page.widgets()}
        for x in tab_order(page, list(widgets.values())):
            out.append(Info(i, widgets[x], page))
    for n, f in enumerate(out):
        f.number = n + 1
    return out


def unique_name(doc, base):
    taken = {w.field_name for page in doc for w in page.widgets()}
    n = 1
    while f"{base}{n}" in taken:
        n += 1
    return f"{base}{n}"


def add_field(doc, pno, kind, shown):
    page = doc[pno]
    w = pymupdf.Widget()
    w.field_type = KINDS[kind]
    w.field_name = unique_name(doc, BASE_NAMES[kind])
    w.rect = pymupdf.Rect(shown) * page.derotation_matrix
    w.border_color = (0.55, 0.55, 0.58)
    w.border_width = 1
    if kind == "text":
        w.text_fontsize = 0  # fits the box
        w.field_value = ""
    else:
        w.field_value = False
    return page.add_widget(w).xref


def set_rect(doc, pno, xref, shown):
    page = doc[pno]
    w = page.load_widget(xref)
    w.rect = pymupdf.Rect(shown) * page.derotation_matrix
    w.update()


def set_name(doc, xref, name):
    doc.xref_set_key(field_xref(doc, xref), "T", pymupdf.get_pdf_str(name))


def _redraw(doc, pno, xref):
    """Draw the box again after its settings changed underneath (its look comes from them)."""
    page = doc[pno]  # (kept: a box can't be changed once its page has gone)
    page.load_widget(xref).update()


def set_default(doc, pno, xref, value):
    page = doc[pno]
    w = page.load_widget(xref)
    f = field_xref(doc, xref)
    if w.field_type == CHECK:
        on = w.on_state() or "Yes"
        w.field_value = on if value else False
        w.update()
        doc.xref_set_key(f, "DV", f"/{on}" if value else "/Off")
    else:
        w.field_value = value
        w.update()
        doc.xref_set_key(f, "DV", pymupdf.get_pdf_str(value) if value else "null")


def set_flag(doc, pno, xref, bit, on):
    flags = _flags(doc, xref)
    flags = flags | bit if on else flags & ~bit
    doc.xref_set_key(field_xref(doc, xref), "Ff", str(flags))
    _redraw(doc, pno, xref)


def set_font_size(doc, pno, xref, size):
    """Text size in the box (0: shrinks to fit). It lives in the box's /DA, or its field's, or the form's."""
    target, da = xref, None
    for x in (xref, field_xref(doc, xref)):
        kind, value = doc.xref_get_key(x, "DA")
        if kind == "string":
            target, da = x, value
            break
    if da is None:
        target = field_xref(doc, xref)
        acro = doc.xref_get_key(doc.pdf_catalog(), "AcroForm")
        if acro[0] == "xref":
            kind, value = doc.xref_get_key(_ref(acro[1]), "DA")
            da = value if kind == "string" else None
        da = da or "0 g /Helv 0 Tf"
    if re.search(r"/\S+\s+[-\d.]+\s+Tf", da):
        da = re.sub(r"(/\S+\s+)[-\d.]+(\s+Tf)", lambda m: f"{m.group(1)}{size:g}{m.group(2)}", da)
    else:
        da += f" /Helv {size:g} Tf"
    doc.xref_set_key(target, "DA", pymupdf.get_pdf_str(da))
    _redraw(doc, pno, xref)


def set_hint(doc, xref, text):
    doc.xref_set_key(field_xref(doc, xref), "TU", pymupdf.get_pdf_str(text) if text else "null")


def delete_field(doc, pno, xref):
    page = doc[pno]
    page.delete_widget(page.load_widget(xref))


def set_tab_order(doc, pno, xrefs):
    """Tab goes through the page's fields in this order: they're listed in the page in it, and the page's
    own "row by row" or "column by column" setting is taken off (as Adobe does when the order is set by hand)."""
    page = doc[pno]
    listed = [x for x, *_ in page.annot_xrefs()]
    order = iter(xrefs)
    wanted = set(xrefs)
    new = [next(order) if x in wanted else x for x in listed]
    array = "[" + " ".join(f"{x} 0 R" for x in new) + "]"
    kind, value = doc.xref_get_key(page.xref, "Annots")
    if kind == "xref":  # the list is an object of its own
        doc.update_object(_ref(value), array)
    else:
        doc.xref_set_key(page.xref, "Annots", array)
    doc.xref_set_key(page.xref, "Tabs", "null")


# ---- the screen --------------------------------------------------------------
class FormPrep(QFrame):
    """The panel beside the pages in Prepare Form, and what the mouse does on the pages there."""

    def __init__(self, win):
        super().__init__()
        self.win, self.view = win, win.view
        self.setObjectName("commentsPanel")
        self.setFixedWidth(300)
        self.fields, self.selected, self.tool = [], None, None
        self.list_page = 0
        self._drag = None  # ("new" | "move" | "size", page, start point, rect at the start, now)
        self.on_tool = lambda kind: None  # lets the top bar show which tool is on
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        head = QHBoxLayout()
        head.setContentsMargins(14, 12, 10, 4)
        title = QLabel("Form fields")
        title.setStyleSheet("font-size: 14px; font-weight: 600;")
        head.addWidget(title)
        head.addSpacing(6)
        self.count = QLabel("")
        self.count.setObjectName("chip")
        head.addWidget(self.count)
        head.addStretch(1)
        lay.addLayout(head)
        self.hint = QLabel("")
        self.hint.setWordWrap(True)
        theme.style(self.hint, "color: {ACCENT}; padding: 0 14px 6px 14px;")
        self.hint.hide()
        lay.addWidget(self.hint)

        row = QHBoxLayout()
        row.setContentsMargins(14, 6, 8, 0)
        self.page_title = QLabel("")
        self.page_title.setStyleSheet("font-weight: 600;")
        row.addWidget(self.page_title)
        row.addStretch(1)
        self.sort_btn = QPushButton("Sort by position")
        self.sort_btn.setFlat(True)
        self.sort_btn.setCursor(Qt.PointingHandCursor)
        self.sort_btn.setToolTip("Put this page's fields in reading order: row by row, left to right")
        theme.style(self.sort_btn, "QPushButton {{ color: {ACCENT}; border: none; background: transparent;"
                    " padding: 2px 4px; }} QPushButton:hover {{ text-decoration: underline; }}"
                    " QPushButton:disabled {{ color: {DISABLED}; }}")
        self.sort_btn.clicked.connect(self.sort_by_position)
        row.addWidget(self.sort_btn)
        lay.addLayout(row)
        self.order_note = QLabel("Tab goes through them in this order. Drag to change it.")
        self.order_note.setWordWrap(True)
        theme.style(self.order_note, "color: {MUTED}; font-size: 12px; padding: 0 14px 4px 14px;")
        lay.addWidget(self.order_note)

        self.list = QListWidget()
        self.list.setObjectName("fieldList")
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        self.list.setDefaultDropAction(Qt.MoveAction)
        self.list.setFrameShape(QFrame.NoFrame)
        self.list.setMinimumHeight(110)
        theme.style(self.list, "QListWidget {{ background: transparent; margin: 0 8px; }}"
                    " QListWidget::item {{ padding: 5px 4px; border-radius: 5px; color: {TEXT}; }}"
                    " QListWidget::item:selected {{ background: {TINT}; color: {TEXT}; }}"
                    " QListWidget::item:hover:!selected {{ background: {HOVER}; }}")
        self.list.currentItemChanged.connect(self._list_picked)
        self.list.model().rowsMoved.connect(lambda *_: QTimer.singleShot(0, self._list_reordered))
        lay.addWidget(self.list, 1)

        line = QFrame()
        line.setFixedHeight(1)
        theme.style(line, "background: {LINE_SOFT};")
        lay.addWidget(line)

        # The selected field's settings.
        self.props = QWidget()
        pl = QVBoxLayout(self.props)
        pl.setContentsMargins(14, 10, 14, 12)
        pl.setSpacing(4)
        self.kind_label = QLabel("")
        theme.style(self.kind_label, "color: {MUTED}; font-size: 12px;")
        pl.addWidget(self.kind_label)

        def caption(text):
            c = QLabel(text)
            c.setStyleSheet("font-size: 12px; margin-top: 4px;")
            pl.addWidget(c)
            return c
        caption("Name")
        self.name_box = QLineEdit()
        self.name_box.setToolTip("What the field is called inside the PDF (each field needs its own name)")
        self.name_box.editingFinished.connect(self.flush)
        pl.addWidget(self.name_box)
        self.default_caption = caption("Default text")
        self.default_box = QLineEdit()
        self.default_box.setPlaceholderText("Empty")
        self.default_box.setToolTip("Text already in the box when the form is opened (it can be typed over)")
        self.default_box.editingFinished.connect(self.flush)
        pl.addWidget(self.default_box)
        self.ticked_box = QCheckBox("Ticked to start with")
        self.ticked_box.toggled.connect(lambda on: self._change("ticked", on))
        pl.addWidget(self.ticked_box)
        self.required_box = QCheckBox("Must be filled in")
        self.required_box.setToolTip("Adobe and Nitro point it out if the form is sent without it")
        self.required_box.toggled.connect(lambda on: self._change("required", on))
        pl.addWidget(self.required_box)
        self.multi_box = QCheckBox("Several lines of text")
        self.multi_box.toggled.connect(lambda on: self._change("multiline", on))
        pl.addWidget(self.multi_box)
        size_row = QHBoxLayout()
        size_row.setContentsMargins(0, 4, 0, 0)
        self.size_caption = QLabel("Text size")
        self.size_caption.setStyleSheet("font-size: 12px;")
        size_row.addWidget(self.size_caption)
        size_row.addStretch(1)
        self.size_box = QComboBox()
        self.size_box.addItem("Fits the box", 0)
        for n in FONT_SIZES:
            self.size_box.addItem(f"{n} pt", n)
        self.size_box.setFixedWidth(120)
        self.size_box.activated.connect(lambda i: self._change("size", self.size_box.itemData(i)))
        size_row.addWidget(self.size_box)
        pl.addLayout(size_row)
        caption("Tip when hovering")
        self.hint_box = QLineEdit()
        self.hint_box.setPlaceholderText("None")
        self.hint_box.setToolTip("Shown when the mouse is over the field in Adobe, Nitro and here")
        self.hint_box.editingFinished.connect(self.flush)
        pl.addWidget(self.hint_box)
        pl.addSpacing(6)
        self.delete_btn = QPushButton("Delete field")
        self.delete_btn.setIcon(icon("delete", size=16))
        self.delete_btn.clicked.connect(self.delete_selected)
        pl.addWidget(self.delete_btn, 0, Qt.AlignLeft)
        lay.addWidget(self.props)
        self.empty = QLabel("Click a field on the page (or in the list) to change its name, default text and more.")
        self.empty.setWordWrap(True)
        theme.style(self.empty, "color: {MUTED}; padding: 12px 14px 16px 14px;")
        lay.addWidget(self.empty)

    # ---- starting and stopping ---------------------------------------------
    def start(self):
        self.selected, self._drag = None, None
        self.list_page = self.view.current_page()
        self.view.page_mouse = self
        self.view.page_paint = self.paint
        self.show()
        self.refresh()
        self.pick(None)

    def stop(self):
        self.flush()
        self.pick(None)
        self.selected, self._drag = None, None
        self.view.page_mouse = None
        self.view.page_paint = None
        self.hide()
        for label in self.view.labels:
            label.unsetCursor()
            label.setToolTip("")
            label.update()

    def pick(self, kind):
        """Pick the text box or tick box tool (None puts it down)."""
        self.tool = kind
        self.hint.setText(HINTS.get(kind, ""))
        self.hint.setVisible(bool(kind))
        self.on_tool(kind)

    def armed(self):
        return self.tool is not None or self.selected is not None

    def put_down(self):
        """Esc: the tool first, then the selection."""
        if self.tool:
            self.pick(None)
        else:
            self.select(None)

    # ---- the list ------------------------------------------------------------
    def refresh(self):
        """Read the fields from the document again (after any change, Undo or Redo)."""
        doc = self.win.doc
        self.fields = list_fields(doc) if doc else []
        if self.selected is not None and self._field(self.selected) is None:
            self.selected = None
        n = len(self.fields)
        self.count.setText(str(n) if n else "")
        self.count.setVisible(bool(n))
        if doc:
            self.list_page = max(0, min(self.list_page, len(doc) - 1))
        self._fill_list()
        self._show_props()
        for label in self.view.labels:
            label.update()

    def follow_page(self, index):
        """The list shows the page being looked at (or the one with the selected field)."""
        if self.selected is None and index != self.list_page:
            self.list_page = index
            self._fill_list()

    def _field(self, xref):
        return next((f for f in self.fields if f.xref == xref), None)

    def _on_page(self, index):
        return [f for f in self.fields if f.page == index]

    def _fill_list(self):
        self.list.blockSignals(True)
        self.list.clear()
        mine = self._on_page(self.list_page)
        doc = self.win.doc
        pages = len(doc) if doc else 0
        self.page_title.setText(f"Page {self.list_page + 1}" + (f" of {pages}" if pages > 1 else ""))
        for f in mine:
            item = QListWidgetItem(icon(TYPE_ICONS.get(f.type, "textfield"), size=16),
                                   f"{f.number}.  {f.name}" + ("  *" if f.flags & REQUIRED else ""))
            item.setData(Qt.UserRole, f.xref)
            item.setToolTip(TYPE_NAMES.get(f.type, "Field") + (" (must be filled in)" if f.flags & REQUIRED else ""))
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled)
            self.list.addItem(item)
            if f.xref == self.selected:
                self.list.setCurrentItem(item)
        if not mine:
            item = QListWidgetItem("No fields on this page yet. Pick Text box or Tick box above, then click or "
                                   "drag on the page.")
            item.setFlags(Qt.NoItemFlags)
            item.setForeground(QColor(theme.MUTED))
            self.list.addItem(item)
            self.list.setWordWrap(True)
        self.sort_btn.setEnabled(len(mine) > 1)
        self.order_note.setVisible(len(mine) > 1)
        self.list.blockSignals(False)

    def _list_picked(self, item, _old=None):
        if item is not None and item.data(Qt.UserRole) is not None:
            self.select(item.data(Qt.UserRole), scroll=True)

    def _list_reordered(self):
        order = [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())]
        order = [x for x in order if x is not None]
        if order != [f.xref for f in self._on_page(self.list_page)]:
            self._set_order(self.list_page, order)

    def sort_by_position(self):
        mine = self._on_page(self.list_page)
        order = [f.xref for f in sorted(mine, key=lambda f: (round(f.rect.y0 / 4), f.rect.x0))]
        if order != [f.xref for f in mine]:
            self._set_order(self.list_page, order)
        else:
            self.win.toast.show_message("These fields are already in reading order.", 2500)

    def _set_order(self, pno, order):
        self.win.edit_page(lambda doc: set_tab_order(doc, pno, order), pno, "Tab order changed")

    # ---- the selected field's settings ---------------------------------------------
    def select(self, xref, scroll=False):
        if xref != self.selected:
            self.flush()
        self.selected = xref
        f = self._field(xref)
        if f is not None and f.page != self.list_page:
            self.list_page = f.page
            self._fill_list()
        else:
            self.list.blockSignals(True)
            for i in range(self.list.count()):
                item = self.list.item(i)
                if item.data(Qt.UserRole) == xref:
                    self.list.setCurrentItem(item)
                    break
            else:
                self.list.setCurrentItem(None)
                self.list.clearSelection()
            self.list.blockSignals(False)
        self._show_props()
        if scroll and f is not None:
            self.view.show_rect(f.page, f.rect)
        for label in self.view.labels:
            label.update()

    def _show_props(self):
        f = self._field(self.selected)
        self.props.setVisible(f is not None)
        self.empty.setVisible(f is None)
        if f is None:
            return
        text = f.type == TEXT
        for w in (self.name_box, self.default_box, self.ticked_box, self.required_box, self.multi_box,
                  self.size_box, self.hint_box):
            w.blockSignals(True)
        self.kind_label.setText(f"{TYPE_NAMES.get(f.type, 'Field')} · number {f.number} in the Tab order")
        self.name_box.setText(f.name)
        self.default_box.setText(f.value if text else "")
        self.ticked_box.setChecked(bool(f.value) if f.type == CHECK else False)
        self.required_box.setChecked(bool(f.flags & REQUIRED))
        self.multi_box.setChecked(bool(f.flags & MULTILINE))
        i = self.size_box.findData(int(f.size) if f.size in FONT_SIZES or not f.size else -1)
        if i < 0:
            self.size_box.addItem(f"{f.size:g} pt", f.size)
            i = self.size_box.count() - 1
        self.size_box.setCurrentIndex(i)
        self.hint_box.setText(f.hint)
        for w in (self.default_caption, self.default_box, self.multi_box, self.size_caption, self.size_box):
            w.setVisible(text)
        self.ticked_box.setVisible(f.type == CHECK)
        for w in (self.name_box, self.default_box, self.ticked_box, self.required_box, self.multi_box,
                  self.size_box, self.hint_box):
            w.blockSignals(False)

    def flush(self):
        """Write in whatever was typed in the settings boxes (if it changed)."""
        f = self._field(self.selected)
        if f is None or not self.props.isVisible():
            return
        name = self.name_box.text().strip()
        if name != f.name:
            others = {g.name for g in self.fields if g.name != f.name}
            if not name or name in others:
                self.win.toast.show_message(f"Another field is already called {name}: each needs its own name."
                                            if name else "A field needs a name.", 3500)
                self.name_box.setText(f.name)
            else:
                self._change("name", name)
                f = self._field(self.selected)
                if f is None:
                    return
        if f.type == TEXT and self.default_box.text() != f.value:
            self._change("default", self.default_box.text())
            f = self._field(self.selected)
            if f is None:
                return
        if self.hint_box.text().strip() != f.hint:
            self._change("hint", self.hint_box.text().strip())

    def _change(self, what, value):
        f = self._field(self.selected)
        if f is None:
            return
        pno, xref = f.page, f.xref

        def change(doc):
            if what == "name":
                set_name(doc, xref, value)
            elif what in ("default", "ticked"):
                set_default(doc, pno, xref, value)
            elif what == "required":
                set_flag(doc, pno, xref, REQUIRED, value)
            elif what == "multiline":
                set_flag(doc, pno, xref, MULTILINE, value)
            elif what == "size":
                set_font_size(doc, pno, xref, value)
            elif what == "hint":
                set_hint(doc, xref, value)
        self.win.edit_page(change, pno)

    def delete_selected(self):
        f = self._field(self.selected)
        if f is None:
            return
        self.selected = None
        self.win.edit_page(lambda doc: delete_field(doc, f.page, f.xref), f.page,
                           f"Deleted {f.name} (Ctrl+Z to undo)")

    # ---- on the pages ------------------------------------------------------------
    def _point(self, pos):
        z = self.view.zoom
        return pymupdf.Point(pos.x() / z, pos.y() / z)

    def _handle_hit(self, label, pos):
        f = self._field(self.selected)
        if f is None or f.page != label.index:
            return None
        z = self.view.zoom
        if abs(pos.x() - f.rect.x1 * z) <= HANDLE and abs(pos.y() - f.rect.y1 * z) <= HANDLE:
            return f
        return None

    def _field_at(self, index, point):
        pad = 3 / self.view.zoom  # small boxes are easier to catch
        hits = [f for f in self._on_page(index) if point in f.rect + (-pad, -pad, pad, pad)]
        return min(hits, key=lambda f: f.rect.width * f.rect.height) if hits else None

    def press(self, label, pos):
        self.flush()
        point = self._point(pos)
        handle = self._handle_hit(label, pos)
        if handle is not None:
            self._drag = ["size", label.index, point, pymupdf.Rect(handle.rect), pymupdf.Rect(handle.rect)]
            return
        f = self._field_at(label.index, point)
        if f is not None:
            self.select(f.xref)
            self._drag = ["move", label.index, point, pymupdf.Rect(f.rect), pymupdf.Rect(f.rect)]
            return
        if self.tool:
            self._drag = ["new", label.index, point, pymupdf.Rect(point, point), pymupdf.Rect(point, point)]
            return
        self.select(None)

    def move(self, label, pos):
        point = self._point(pos)
        d = self._drag
        if d is not None:
            if label.index != d[1]:
                return
            d[4] = self._dragged(d, point, label)
            label.update()
            return
        if self._handle_hit(label, pos) is not None:
            label.setCursor(Qt.SizeFDiagCursor)
            label.setToolTip("")
            return
        f = self._field_at(label.index, point)
        if f is not None:
            label.setCursor(Qt.SizeAllCursor)
            label.setToolTip(f"{f.number}. {f.name}")
        else:
            label.setCursor(Qt.CrossCursor if self.tool else Qt.ArrowCursor)
            label.setToolTip("")

    def _dragged(self, d, point, label):
        kind, _, start, orig, _ = d
        page = self.view.doc[label.index].rect
        if kind == "new":
            r = pymupdf.Rect(start, point).normalize()
            return r & page
        if kind == "move":
            dx = max(-orig.x0, min(point.x - start.x, page.width - orig.x1))
            dy = max(-orig.y0, min(point.y - start.y, page.height - orig.y1))
            return orig + (dx, dy, dx, dy)
        f = self._field(self.selected)
        mw, mh = MIN_SIZES.get(f.type if f else TEXT, (8, 6))
        x1 = max(orig.x0 + mw, min(point.x, page.width))
        y1 = max(orig.y0 + mh, min(point.y, page.height))
        return pymupdf.Rect(orig.x0, orig.y0, x1, y1)

    def release(self, label, pos):
        d, self._drag = self._drag, None
        if d is None:
            return
        kind, pno, start, orig, rect = d
        label.update()
        if kind == "new":
            self._make(pno, start, rect)
            return
        if max(abs(rect.x0 - orig.x0), abs(rect.y0 - orig.y0), abs(rect.x1 - orig.x1), abs(rect.y1 - orig.y1)) < 0.5:
            return  # just a click: selected, nothing moved
        xref = self.selected
        self.win.edit_page(lambda doc: set_rect(doc, pno, xref, rect), pno)

    def _make(self, pno, start, rect):
        page = self.view.doc[pno].rect
        w, h = DEFAULT_SIZES[self.tool]
        if rect.width < 4 and rect.height < 4:  # a click: a standard size, from where it was clicked
            if self.tool == "check":
                x0, y0 = start.x - w / 2, start.y - h / 2
            else:
                x0, y0 = start.x, start.y - h / 2
            x0 = max(0, min(x0, page.width - w))
            y0 = max(0, min(y0, page.height - h))
            rect = pymupdf.Rect(x0, y0, x0 + w, y0 + h)
        elif self.tool == "check":  # tick boxes are square
            s = max(6, min(rect.width, rect.height))
            rect = pymupdf.Rect(rect.x0, rect.y0, rect.x0 + s, rect.y0 + s)
        else:
            rect = pymupdf.Rect(rect.x0, rect.y0, max(rect.x1, rect.x0 + 16), max(rect.y1, rect.y0 + 8))
        kind, made = self.tool, {}

        def change(doc):
            made["xref"] = add_field(doc, pno, kind, rect)
        self.win.edit_page(change, pno)
        if "xref" in made:
            self.select(made["xref"])

    def leave(self, label):
        pass

    def wheel(self, event):
        return False

    def scrolled(self):
        pass

    # ---- drawing over the pages ------------------------------------------------
    def paint(self, label, p):
        z = self.view.zoom
        accent = QColor(theme.ACCENT_FILL)
        font = QFont(p.font())
        font.setPixelSize(10)
        font.setBold(True)
        p.setFont(font)
        metrics = QFontMetrics(font)
        d = self._drag
        for f in self._on_page(label.index):
            r = d[4] if d is not None and d[0] in ("move", "size") and f.xref == self.selected else f.rect
            box = QRectF(r.x0 * z, r.y0 * z, r.width * z, r.height * z)
            chosen = f.xref == self.selected
            pen = QPen(accent, 2 if chosen else 1.2)
            if not chosen:
                pen.setStyle(Qt.DashLine)
            p.setPen(pen)
            p.setBrush(QColor(16, 124, 65, 45 if chosen else 16))
            p.drawRect(box)
            # Its number in the Tab order, at its top-left corner.
            text = str(f.number)
            bw, bh = max(16, metrics.horizontalAdvance(text) + 8), 16
            badge = QRectF(box.left() - bw + 4, box.top() - bh + 4, bw, bh)  # just off the corner
            badge.moveLeft(max(0, badge.left()))
            badge.moveTop(max(0, badge.top()))
            p.setPen(Qt.NoPen)
            p.setBrush(accent if chosen else QColor(16, 124, 65, 210))
            p.drawRoundedRect(badge, bh / 2, bh / 2)
            p.setPen(QColor("white"))
            p.drawText(badge, Qt.AlignCenter, text)
            if chosen:
                h = QRectF(box.right() - HANDLE / 2, box.bottom() - HANDLE / 2, HANDLE, HANDLE)
                p.setPen(QPen(accent, 1.5))
                p.setBrush(QColor("white"))
                p.drawRect(h)
        if d is not None and d[0] == "new" and d[1] == label.index:
            r = d[4]
            pen = QPen(accent, 1.2)
            pen.setStyle(Qt.DashLine)
            p.setPen(pen)
            p.setBrush(QColor(16, 124, 65, 28))
            p.drawRect(QRectF(r.x0 * z, r.y0 * z, r.width * z, r.height * z))
