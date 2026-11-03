"""The window's furniture: the one top bar, the floating page/zoom pill, the find box,
match ticks, short messages (toasts) and the small floating style bar."""
from PySide6.QtCore import Qt, QTimer, QEvent, Signal, QPoint, QRect, QSize, QSettings
from PySide6.QtGui import QColor, QPainter, QIntValidator, QFont, QFontMetrics, QCursor
from PySide6.QtWidgets import (
    QApplication, QWidget, QFrame, QHBoxLayout, QLabel, QToolButton, QPushButton, QLineEdit, QMenu,
    QGraphicsDropShadowEffect, QStackedWidget, QSizePolicy,
)

from . import theme
from .icons import icon

BAR_HEIGHT = 48


class _ToolButton(QToolButton):
    """A checked tool's name turns bold; leave room for that so the end of the name isn't cut off."""

    def sizeHint(self):
        s = super().sizeHint()
        if self.isCheckable() and self.text() and self.toolButtonStyle() != Qt.ToolButtonIconOnly:
            bold = QFont(self.font())
            bold.setWeight(QFont.DemiBold)
            text = self.text().replace("&&", "&")
            s.setWidth(s.width() + max(0, QFontMetrics(bold).horizontalAdvance(text)
                                       - QFontMetrics(self.font()).horizontalAdvance(text)))
        return s

    def minimumSizeHint(self):
        return self.sizeHint()


def tool_button(name=None, text="", tip="", checkable=False, icon_only=False, size=20):
    b = _ToolButton()
    if name:
        b.setIcon(icon(name, size=size))
        b.setIconSize(QSize(size, size))
    if text:
        b.setText(text)
        b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon if name else Qt.ToolButtonTextOnly)
    else:
        b.setToolButtonStyle(Qt.ToolButtonIconOnly)
        b.setProperty("iconOnly", True)
    tip = tip or text.replace("&&", "&")  # hovering shows the tool's name
    if tip:
        b.setToolTip(tip)
    b.setCheckable(checkable)
    b.setCursor(Qt.PointingHandCursor)
    b.setFocusPolicy(Qt.NoFocus)
    return b


def set_compact(widget, on, snug=False):
    """Show the buttons inside widget as icons only (their words move to the tooltip), or icon and words."""
    for b in widget.findChildren(QToolButton):
        if not b.text() or b.icon().isNull():
            continue
        if not b.toolTip():
            b.setToolTip(b.text().replace("&&", "&"))
        b.setToolButtonStyle(Qt.ToolButtonIconOnly if on else Qt.ToolButtonTextBesideIcon)
        if on:
            # Room for the icon plus, on a drop-down, its little arrow (else the icon is squeezed small).
            b.setMinimumWidth(b.iconSize().width() + 22 if b.property("dropdown") else 0)
            b.setMaximumWidth(16777215)
        elif snug:
            # Qt pads icon-and-word buttons unevenly (more with a drop-down); size them to fit snugly so
            # the gaps between tools look even. Measured bold, as a picked tool's word is.
            f = QFont(b.font())
            f.setWeight(QFont.DemiBold)
            text = b.text().replace("&&", "&")
            w = b.iconSize().width() + 6 + QFontMetrics(f).horizontalAdvance(text) + 2 * 8 + 2
            if b.popupMode() == QToolButton.MenuButtonPopup:
                w += 16
            elif b.property("dropdown"):
                w += 12
            b.setFixedWidth(w)


def separator(height=22):
    s = QFrame()
    s.setObjectName("barSep")
    s.setFixedSize(1, height)
    return s


def shadow(widget, blur=14, alpha=45, dy=2):
    eff = QGraphicsDropShadowEffect(widget)
    eff.setBlurRadius(blur)
    eff.setOffset(0, dy)
    eff.setColor(QColor(0, 0, 0, alpha))
    widget.setGraphicsEffect(eff)
    return eff


def primary_button(text):
    b = QPushButton(text)
    b.setProperty("primary", True)
    b.setCursor(Qt.PointingHandCursor)
    b.setFocusPolicy(Qt.NoFocus)
    return b


# ---- top bar -----------------------------------------------------------------
class TopBar(QWidget):
    """48 px bar. Always at the left, like Word and Excel's quick access bar: menu, Save, Print, Undo, Redo.
    Main view then: file name | Read · Organize & Merge · Edit · Fill & Sign | find, more.
    Inside a mode: mode name, the mode's tools … Cancel, Done."""
    tab_clicked = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("topBar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(BAR_HEIGHT)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(10, 0, 10, 0)
        outer.setSpacing(0)

        # The same four buttons in the same place on every screen.
        self.left = QWidget()
        ll = QHBoxLayout(self.left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(2)
        self.menu_btn = tool_button("menu", tip="Menu")
        self.menu_btn.setPopupMode(QToolButton.InstantPopup)
        self.save_btn = tool_button("save", tip="Save (Ctrl+S)")
        self.print_btn = tool_button("print", tip="Print (Ctrl+P)")
        self.undo_btn = tool_button("undo", tip="Undo (Ctrl+Z)")
        self.redo_btn = tool_button("redo", tip="Redo (Ctrl+Y)")
        for w in (self.menu_btn, self.save_btn, self.print_btn, self.undo_btn, self.redo_btn):
            ll.addWidget(w)
        self.left_sep = separator()
        ll.addSpacing(8)
        ll.addWidget(self.left_sep)
        ll.addSpacing(6)
        outer.addWidget(self.left)
        self.stack = QStackedWidget()
        outer.addWidget(self.stack, 1)

        # Main bar.
        main = QWidget()
        lay = QHBoxLayout(main)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.logo = QLabel()
        self.file_name = QLabel()
        self.file_name.setObjectName("fileName")
        self.edited = QLabel("Edited")
        self.edited.setObjectName("edited")
        self.dot = QLabel()
        self.dot.setFixedSize(8, 8)
        theme.style(self.dot, "background: {ACCENT}; border-radius: 4px;")
        lay.addWidget(self.logo)
        lay.addWidget(self.dot)
        lay.addSpacing(2)
        lay.addWidget(self.file_name)
        lay.addSpacing(4)
        lay.addWidget(self.edited)
        lay.addStretch(1)
        self.snip_btn = tool_button("snip", tip="Snip: copy part of a page as a sharp picture (Ctrl+Shift+X)",
                                    checkable=True)
        self.comments_btn = tool_button("comment", tip="Comments", checkable=True)
        self.find_btn = tool_button("find", tip="Find text (Ctrl+F)", checkable=True)
        self.more_btn = tool_button("more", tip="More")
        self.more_btn.setPopupMode(QToolButton.InstantPopup)
        lay.addWidget(self.snip_btn)
        lay.addWidget(self.comments_btn)
        lay.addWidget(self.find_btn)
        lay.addWidget(self.more_btn)

        # Mode tabs, centred on the bar whatever the file name's length.
        self.tabs = QFrame(main)
        self.tabs.setObjectName("tabs")
        tl = QHBoxLayout(self.tabs)
        tl.setContentsMargins(3, 3, 3, 3)
        tl.setSpacing(2)
        self.tab_buttons = {}
        for key, label, ic in (("read", "Read", "read"), ("pages", "Organize && Merge", "pages"), ("edit", "Edit", "edit"),
                               ("sign", "Fill && Sign", "sign")):
            b = tool_button(ic, label, checkable=True, size=18)
            b.clicked.connect(lambda _=False, k=key: self.tab_clicked.emit(k))
            tl.addWidget(b)
            self.tab_buttons[key] = b
        self.tab_buttons["read"].setChecked(True)
        self.stack.addWidget(main)
        self.main = main

        # Mode bar.
        mode = QWidget()
        ml = QHBoxLayout(mode)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(2)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setToolTip("Leave and undo any changes (Esc)")
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.setFocusPolicy(Qt.NoFocus)
        self.mode_title = QLabel()
        self.mode_title.setObjectName("modeTitle")
        ml.addWidget(self.mode_title)
        ml.addSpacing(12)
        # When the tools don't fit beside the name they go to a row under the bar, which shows when the mouse
        # comes near (this button shows it too).
        self.row_btn = tool_button("chevron", "Tools")
        self.row_btn.clicked.connect(lambda: self.row.reveal())
        self.row_btn.hide()
        ml.addWidget(self.row_btn)
        self.row = ToolRow(self)
        self._in_row = False
        self.tools_holder = QHBoxLayout()
        self.tools_holder.setSpacing(2)
        ml.addLayout(self.tools_holder)
        ml.addStretch(1)
        self.done_btn = primary_button("Done")
        self.done_btn.setMinimumWidth(76)
        ml.addSpacing(8)
        ml.addWidget(self.cancel_btn)
        ml.addSpacing(4)
        ml.addWidget(self.done_btn)
        self.stack.addWidget(mode)
        self._tools = None

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit()

    def showEvent(self, e):
        super().showEvent(e)
        QTimer.singleShot(0, self._fit)

    def _fit(self):
        """Make everything fit the window's width: the tabs drop their words (icons only) when space is
        short, and a long file name is shortened in the middle rather than pushing buttons off the bar."""
        width = self.width() - self.stack.x() - 10  # the room right of Menu, Save, Undo and Redo
        right = sum(w.sizeHint().width() + 6 for w in (self.snip_btn, self.comments_btn, self.find_btn, self.more_btn)
                    if not w.isHidden()) + 16
        name_x = self.file_name.x() if self.file_name.x() > 0 else 20
        extra = (self.edited.sizeHint().width() + 10) if not self.edited.isHidden() else 0
        for compact in (False, True):
            set_compact(self.tabs, compact)
            self.tabs.adjustSize()
            x = (self.width() - self.tabs.width()) // 2 - self.stack.x()  # centred on the whole bar
            room = x - name_x - extra - 20
            if room >= 160 and x + self.tabs.width() <= width - right:
                break
        x = min(x, width - right - self.tabs.width())
        room = max(40, x - name_x - extra - 20)
        fm = self.file_name.fontMetrics()
        self.file_name.setText(fm.elidedText(self._full_name, Qt.ElideMiddle, room))
        self.file_name.setToolTip(self._full_name if self.file_name.text() != self._full_name else "")
        self.tabs.move(max(x, name_x), (self.height() - self.tabs.height()) // 2)
        # Mode bar: the stamp favourites go if the tools don't all fit, then the tools move to the row under
        # the bar (at full size; they only lose their words if even the whole window is too narrow).
        if self._tools is not None:
            page = self.stack.widget(1)

            def need():
                # Sizes are normally worked out later; make every level work them out again now.
                for w in reversed([self._tools] + self._tools.findChildren(QWidget)):
                    w.updateGeometry()
                    if w.layout() is not None:
                        w.layout().invalidate()
                self.tools_holder.invalidate()
                page.layout().invalidate()
                if self._in_row:  # as if they were in the bar
                    return page.layout().sizeHint().width() - self.row_btn.sizeHint().width() + \
                        self._tools.sizeHint().width()
                return page.layout().sizeHint().width()
            # Stamp favourites (shown beside the Stamps menu) go first when room is short.
            groups = [g for g in self._tools.findChildren(QWidget) if hasattr(g, "set_show_quick")]

            def quick(on):
                for g in groups:
                    g.set_show_quick(on)
            self.mode_title.show()
            quick(True)
            words = str(QSettings("Aerialist", "Aerialist").value("toolbar/words", True)).lower() != "false"
            set_compact(self._tools, not words, snug=True)
            in_row = False
            if need() > width:
                quick(False)
                in_row = need() > width
                if in_row:
                    # No room for them at full size: they go to the row under the bar instead of shrinking.
                    self._dock(True)
                    room = self.window().width() - 24

                    def row_need():
                        for w in reversed([self._tools] + self._tools.findChildren(QWidget)):
                            w.updateGeometry()
                            if w.layout() is not None:
                                w.layout().invalidate()
                        return self._tools.sizeHint().width()
                    quick(True)
                    if row_need() > room:
                        quick(False)
                        if words and row_need() > room:
                            set_compact(self._tools, True)
            if not in_row:
                self._dock(False)
            self.row.place()

    _full_name = ""

    def set_document(self, name, dirty, has_doc):
        self._full_name = name
        self.file_name.setText(name)
        self.file_name.setVisible(bool(name))
        self.dot.setVisible(has_doc and dirty)
        self.edited.setVisible(has_doc and dirty)
        self.tabs.setVisible(has_doc)
        self.find_btn.setVisible(has_doc)
        self.comments_btn.setVisible(has_doc)
        self.snip_btn.setVisible(has_doc)
        for w in (self.save_btn, self.print_btn, self.undo_btn, self.redo_btn, self.left_sep):
            w.setVisible(has_doc)
        self.logo.setVisible(not has_doc)
        QTimer.singleShot(0, self._fit)

    def show_main(self):
        self._set_tools(None)
        self.stack.setCurrentIndex(0)
        for k, b in self.tab_buttons.items():
            b.setChecked(k == "read")

    def show_mode(self, title, tools):
        self.mode_title.setText(title)
        self._set_tools(tools)
        self.stack.setCurrentIndex(1)
        QTimer.singleShot(0, self._fit)

    def _set_tools(self, tools):
        if self._tools is not None:
            self._dock(False)
            self.tools_holder.removeWidget(self._tools)
            self._tools.hide()
        self._tools = tools
        if tools is not None:
            self.tools_holder.addWidget(tools)
            tools.show()
            self._first_fit = True

    def _dock(self, in_row):
        """Put the mode's tools in the bar, or in the row under it."""
        if in_row == self._in_row or self._tools is None:
            return
        self._in_row = in_row
        if in_row:
            self.tools_holder.removeWidget(self._tools)
            self.row.lay.insertWidget(0, self._tools)
            self._tools.show()
            self.row_btn.show()
            self.row.start(flash=getattr(self, "_first_fit", False))
        else:
            self.row.stop()
            self.row.lay.removeWidget(self._tools)
            self.tools_holder.addWidget(self._tools)
            self._tools.show()
            self.row_btn.hide()
        self._first_fit = False

    def tools_in_row(self):
        return self._in_row


class ToolRow(QFrame):
    """The mode's tools in a second row under the top bar, for when the window is too narrow for them beside the
    mode's name. It floats over the pages and only shows while the mouse is near the top (or it's in use)."""
    NEAR = 28  # px under the bar that count as "near"
    HIDE_AFTER = 600  # ms

    def __init__(self, bar):
        super().__init__()
        self.bar = bar
        self.setObjectName("topBar")  # looks like the bar above
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.lay = QHBoxLayout(self)
        self.lay.setContentsMargins(12, 0, 12, 0)
        self.lay.addStretch(1)
        shadow(self, blur=16, alpha=50, dy=3)
        self.hide()
        self._active = False
        self._poll = QTimer(self, interval=80)
        self._poll.timeout.connect(self._check)
        self._away = QTimer(self, singleShot=True, interval=self.HIDE_AFTER)
        self._away.timeout.connect(self._maybe_hide)

    def place(self):
        win = self.bar.window()
        if self.parent() is not win:
            self.setParent(win)
            self.hide()
        top = self.bar.mapTo(win, QPoint(0, self.bar.height())).y()
        self.setGeometry(0, top, win.width(), BAR_HEIGHT - 4)

    def start(self, flash=False):
        self._active = True
        self.place()
        self._poll.start()
        if flash:  # show where the tools went for a moment
            self.reveal(2500)

    def stop(self):
        self._active = False
        self._poll.stop()
        self._away.stop()
        self.hide()

    def reveal(self, ms=None):
        if not self._active:
            return
        self.place()
        self.show()
        self.raise_()
        self._away.start(ms or self.HIDE_AFTER)

    def _near(self):
        pos = QCursor.pos()
        bar = QRect(self.bar.mapToGlobal(QPoint(0, 0)), self.bar.size())
        zone = QRect(bar.left(), bar.top(), bar.width(), bar.height() + (self.height() if self.isVisible() else 0)
                     + self.NEAR)
        return zone.contains(pos)

    def _busy(self):
        """A drop-down of one of the tools is open, or a button is held: stay."""
        popup = QApplication.activePopupWidget()
        return popup is not None and (self.isAncestorOf(popup) or isinstance(popup, QMenu)) or \
            (self.isVisible() and QApplication.mouseButtons() != Qt.NoButton and
             self.rect().contains(self.mapFromGlobal(QCursor.pos())))

    def _check(self):
        if not self.bar.window().isActiveWindow() and not self.isVisible():
            return
        if self._near() and (self.isVisible() or QApplication.mouseButtons() == Qt.NoButton):
            if not self.isVisible():
                self.reveal()
            self._away.stop()
        elif self.isVisible() and not self._away.isActive():
            self._away.start()

    def _maybe_hide(self):
        if self._busy() or self._near():
            self._away.start()
            return
        self.hide()


class BarTools(QWidget):
    """A row of tools for the mode bar."""

    def __init__(self):
        super().__init__()
        self.lay = QHBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(2)

    def add(self, w):
        self.lay.addWidget(w)
        return w


# ---- floating bits over the pages ---------------------------------------------
class SideTab(QToolButton):
    """A small tab sticking out from the left edge of the pages, beside the thumbnails: ‹ hides them, › shows them."""

    def __init__(self, view):
        super().__init__(view)
        self.setObjectName("sideTab")
        self.setFixedSize(15, 44)
        self.setIconSize(QSize(12, 12))
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.move(0, 56)
        self.set_open(True)

    def set_open(self, is_open):
        self.setIcon(icon("prev" if is_open else "next", size=12))
        self.setToolTip(("Hide" if is_open else "Show") + " page thumbnails (Ctrl+B)")
        self.raise_()


class Floating(QFrame):
    """A small panel that floats over the page view and keeps its place when the view resizes."""

    def __init__(self, view, name, place):
        super().__init__(view)
        self.setObjectName(name)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.view, self.place_fn = view, place
        self.lay = QHBoxLayout(self)
        self.lay.setContentsMargins(6, 4, 6, 4)
        self.lay.setSpacing(2)
        self.shadow = shadow(self, 16, 50, 3)
        view.installEventFilter(self)
        if hasattr(view, "viewport"):  # its width changes after the view's own (scroll bar shown or not)
            view.viewport().installEventFilter(self)

    def eventFilter(self, obj, e):
        if e.type() in (QEvent.Resize, QEvent.Show) and not self.isHidden():
            self.reposition()
            QTimer.singleShot(0, self.reposition)  # again once the window has finished resizing
        return False

    def reposition(self):
        self.adjustSize()
        self.move(self.place_fn(self))
        self.raise_()

    def showEvent(self, e):
        super().showEvent(e)
        QTimer.singleShot(0, self.reposition)


def _scroll_w(view):
    sb = view.verticalScrollBar()
    return sb.width() if sb.isVisible() else 0


class PagePill(Floating):
    """Page number and zoom, floating at the bottom right of the page view. Fades while reading."""
    go_page = Signal(int)
    prev_page = Signal()
    next_page = Signal()
    zoom_in = Signal()
    zoom_out = Signal()
    zoom_preset = Signal(str)

    def __init__(self, view):
        # Bottom right of the pages, out of the way, wherever the window is resized to.
        super().__init__(view, "pill", lambda w: QPoint(view.viewport().width() - w.width() - 18,
                                                        view.height() - w.height() - 10))
        self.lay.setContentsMargins(8, 3, 8, 3)
        self.shadow.setBlurRadius(26)
        self.shadow.setOffset(0, 5)
        self.shadow.setColor(QColor(0, 0, 0, 90))
        prev = tool_button("prev", tip="Previous page (PgUp)", size=16)
        prev.clicked.connect(self.prev_page)
        self.page_edit = QLineEdit()
        self.page_edit.setFixedWidth(34)
        self.page_edit.setAlignment(Qt.AlignRight)
        self.page_edit.setValidator(QIntValidator(1, 99999, self))
        self.page_edit.returnPressed.connect(self._go_typed)
        # Goes there as you type (after a short pause, so typing 12 doesn't stop at page 1 on the way).
        self._typed = QTimer(self, singleShot=True, interval=300)
        self._typed.timeout.connect(self._go_typed)
        self.page_edit.textEdited.connect(lambda _: self._typed.start())
        self.page_edit.installEventFilter(self)  # clicking in picks the number, so typing replaces it
        self.total = QLabel("/ 0")
        self.total.setObjectName("pillText")
        nxt = tool_button("next", tip="Next page (PgDown)", size=16)
        nxt.clicked.connect(self.next_page)
        out = tool_button("minus", tip="Zoom out (Ctrl+-)", size=16)
        out.clicked.connect(self.zoom_out)
        self.zoom_btn = QToolButton()
        self.zoom_btn.setText("100%")
        self.zoom_btn.setPopupMode(QToolButton.InstantPopup)
        self.zoom_btn.setCursor(Qt.PointingHandCursor)
        self.zoom_btn.setFocusPolicy(Qt.NoFocus)
        self.zoom_btn.setStyleSheet("QToolButton::menu-indicator { image: none; width: 0; }")
        menu = QMenu(self.zoom_btn)
        for t in ("50%", "75%", "100%", "125%", "150%", "200%", "300%", None, "Fit width", "Fit page"):
            menu.addSeparator() if t is None else menu.addAction(t, lambda t=t: self.zoom_preset.emit(t))
        self.zoom_btn.setMenu(menu)
        zin = tool_button("plus", tip="Zoom in (Ctrl++)", size=16)
        zin.clicked.connect(self.zoom_in)
        fit = tool_button("fit_width", tip="Fit to width (Ctrl+1)", size=16)
        fit.clicked.connect(lambda: self.zoom_preset.emit("Fit width"))
        for w in (prev, self.page_edit, self.total, nxt):
            self.lay.addWidget(w)
        self.lay.addSpacing(4)
        self.lay.addWidget(separator(18))
        self.lay.addSpacing(4)
        for w in (out, self.zoom_btn, zin, fit):
            self.lay.addWidget(w)
        self._fade = QTimer(self, singleShot=True, interval=2500)
        self._fade.timeout.connect(lambda: self.set_faded(True))
        view.verticalScrollBar().valueChanged.connect(self.wake)
        self.setMouseTracking(True)

    def eventFilter(self, obj, e):
        if obj is self.page_edit and e.type() == QEvent.FocusIn:
            QTimer.singleShot(0, self.page_edit.selectAll)
        return super().eventFilter(obj, e)

    def _go_typed(self):
        self._typed.stop()
        if self.page_edit.text():
            self.go_page.emit(int(self.page_edit.text()) - 1)

    def set_page(self, i, n):
        if not self.page_edit.hasFocus():
            self.page_edit.setText(str(i + 1))
        self.total.setText(f"/ {n}")
        self.wake()

    def set_zoom(self, zoom):
        self.zoom_btn.setText(f"{round(zoom * 100)}%")
        self.wake()

    def wake(self):
        self.set_faded(False)
        self._fade.start()

    def set_faded(self, faded):
        if faded and (self.underMouse() or self.page_edit.hasFocus() or self.zoom_btn.menu().isVisible()):
            self._fade.start()
            return
        self.setWindowOpacity(1)
        self.shadow.setEnabled(not faded)
        c = QColor(theme.SURFACE)
        alpha = 255 if theme.DARK else 150  # see-through dark over a white page reads as a grey smudge
        self.setStyleSheet(f"#pill {{ background: rgba({c.red()},{c.green()},{c.blue()},{alpha}); }} QToolButton, "
                           f"QLabel, QLineEdit {{ color: {theme.SUBTLE}; background: transparent; }}" if faded else "")

    def enterEvent(self, e):
        self.wake()


class FindBar(Floating):
    """Compact find box under the top bar, at the right."""
    closed = Signal()

    def __init__(self, view):
        super().__init__(view, "findBar", lambda w: QPoint(max(6, view.viewport().width() - w.width() - 14), 10))
        self.lay.setContentsMargins(10, 4, 4, 4)
        self.lay.setSpacing(0)
        self.shadow.setBlurRadius(26)  # darker and wider than the others: it mustn't blend into a white page
        self.shadow.setColor(QColor(0, 0, 0, 95))
        self.shadow.setOffset(0, 4)
        glass = QLabel()
        from .icons import pixmap
        glass.setPixmap(pixmap("find", 16, "MUTED"))
        theme.on_change(lambda: glass.setPixmap(pixmap("find", 16, "MUTED")))
        self.box = QLineEdit()
        self.box.setPlaceholderText("Type to find…")
        self.box.textChanged.connect(lambda: self.reposition() if self.isVisible() else self._fit_box())
        self.count = QLabel("")
        self.count.setObjectName("findCount")
        self.count.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        f = self.count.font()
        f.setPointSizeF(f.pointSizeF() * 0.85)
        self.count.setFont(f)
        self.count.setFixedWidth(QFontMetrics(f).horizontalAdvance("888 of 888 · 88 on page") + 6)
        self.prev_page_btn = tool_button("page_up", tip="Previous page with a match", size=16)
        self.prev_btn = tool_button("up", tip="Previous match (Shift+Enter)", size=16)
        self.next_btn = tool_button("down", tip="Next match (Enter)", size=16)
        self.next_page_btn = tool_button("page_down", tip="Next page with a match", size=16)
        close = tool_button("close", tip="Close (Esc)", size=14)
        close.clicked.connect(self.close_bar)
        self.lay.addWidget(glass)
        self.lay.addSpacing(6)
        self.lay.addWidget(self.box)
        self.lay.addSpacing(4)
        self.lay.addWidget(self.count)
        self.lay.addSpacing(4)
        for w in (self.prev_page_btn, self.prev_btn, self.next_btn, self.next_page_btn, close):
            self.lay.addWidget(w)
        self.box.installEventFilter(self)
        self._fit_box()
        self.hide()

    MIN_BOX, MAX_BOX = 110, 300

    def _fit_box(self, *_):
        """The box is short, and grows as the search gets longer than it can show (never off the window)."""
        # In a narrow window the count goes first, then the box gets shorter, so the bar always fits.
        self.count.setVisible(self.view.viewport().width() >= 430)
        fm = self.box.fontMetrics()
        want = max(self.MIN_BOX, min(self.MAX_BOX, fm.horizontalAdvance(self.box.text()) + 18))
        rest = self.lay.sizeHint().width() - self.box.width()
        room = self.view.viewport().width() - 28 - rest
        self.box.setFixedWidth(max(60, min(want, room)))

    def reposition(self):
        self._fit_box()
        super().reposition()

    def eventFilter(self, obj, e):
        if obj is self.box and e.type() == QEvent.KeyPress and e.key() == Qt.Key_Escape:
            self.close_bar()
            return True
        return super().eventFilter(obj, e)

    def open_bar(self):
        self.show()
        self.reposition()
        self.box.setFocus()
        self.box.selectAll()

    def close_bar(self):
        self.hide()
        self.closed.emit()

    def set_count(self, text, tip=""):
        # The count keeps one width, so the bar doesn't jump about while typing.
        self.count.setText(text)
        self.count.setToolTip(tip)


class MatchTicks(QWidget):
    """Little marks beside the scroll bar where the search matches are."""

    def __init__(self, view):
        super().__init__(view)
        self.view = view
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.marks = []  # (page index, y in page points)
        view.installEventFilter(self)
        self.hide()

    def eventFilter(self, obj, e):
        if e.type() == QEvent.Resize:
            self._place()
        return False

    def _place(self):
        vp = self.view.viewport()
        self.setGeometry(vp.width() - 10, 0, 8, vp.height())

    def set_marks(self, marks):
        self.marks = marks
        self.setVisible(bool(marks))
        self._place()
        self.raise_()
        self.update()

    def paintEvent(self, e):
        total = max(1, self.view.widget().height())
        p = QPainter(self)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.WARN))
        labels = self.view.labels
        for i, y in self.marks:
            if i < len(labels):
                ty = (labels[i].y() + y * self.view.zoom) / total * self.height()
                p.drawRoundedRect(QRect(0, int(ty) - 1, 8, 3), 1, 1)
        p.end()


class Toast(QLabel):
    """A short message near the bottom of the window that goes away by itself."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("toast")
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._timer = QTimer(self, singleShot=True)
        self._timer.timeout.connect(self.hide)
        self.hide()

    def show_message(self, text, ms=3500):
        self.setText(text)
        # One line when it fits (a wrapping label otherwise picks a narrow width), wrapped at 520 px when not.
        self.setWordWrap(False)
        self.setMinimumWidth(0)
        self.setMaximumWidth(16777215)
        wide = self.sizeHint().width() > 520
        self.setWordWrap(wide)
        self.setFixedWidth(520 if wide else self.sizeHint().width())
        self.adjustSize()
        par = self.parentWidget()
        self.move((par.width() - self.width()) // 2, par.height() - self.height() - 70)
        self.show()
        self.raise_()
        self._timer.start(ms)


class MiniBar(Floating):
    """Small floating bar of settings for the selected item (or the tool in use)."""

    def __init__(self, view):
        super().__init__(view, "miniBar", lambda w: w.anchor_pos())
        self.lay.setContentsMargins(6, 3, 6, 3)
        self.anchor = None  # function returning a QRect in view coordinates, or None for top centre
        self._timer = QTimer(self, interval=120)
        self._timer.timeout.connect(self._follow)
        self.hide()

    def anchor_pos(self):
        vp = self.view.viewport()
        r = self.anchor() if self.anchor else None
        if r is None:
            return QPoint((vp.width() - self.width()) // 2, 10)
        x = max(6, min(r.center().x() - self.width() // 2, vp.width() - self.width() - 6))
        y = r.top() - self.height() - 10
        if y < 6:
            y = r.bottom() + 10
        y = max(6, min(y, vp.height() - self.height() - 6))
        return QPoint(x, y)

    def follow(self, anchor):
        self.anchor = anchor
        self.show()
        self.reposition()
        self._timer.start()

    def _follow(self):
        if self.isVisible():
            p = self.anchor_pos()
            if p != self.pos():
                self.move(p)
        else:
            self._timer.stop()

    def hideEvent(self, e):
        self._timer.stop()
        super().hideEvent(e)
