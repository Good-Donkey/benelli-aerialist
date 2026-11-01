"""The app's look: emerald accent on a light grey canvas (or a dark one), one style sheet for everything.

The colours below are the light ones; set_mode() swaps in the dark set. Code reads them as theme.NAME when it
draws, so a switch shows up everywhere on the next repaint."""
from PySide6.QtCore import Qt, QEvent, QObject, QRectF
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPalette, QPixmap
from PySide6.QtWidgets import QApplication, QProxyStyle, QPushButton, QStyle

LIGHT = dict(
    ACCENT="#107C41",  # emerald: text, outlines, icons that are on
    ACCENT_FILL="#107C41",  # behind white text (Done, Open)
    ACCENT_DARK="#0B5E31",  # a filled button under the mouse
    ACCENT_SOFT="#9CC7AE",  # a filled button that's turned off
    TINT="#E2F2E8",  # selected / active background
    TINT_HOVER="#D3EBDD",
    TINT_TEXT="#0B5E31",
    CANVAS="#E9E9EC",  # behind the pages
    SURFACE="#FFFFFF",
    SOFT="#F7F7F8",  # side panels, home
    PANEL="#FAFAFB",  # comments
    NAV="#F5F5F6",  # Settings' list of pages
    BORDER="#E5E5E5",
    LINE="#D6D6DA",  # edges of buttons and boxes
    LINE_SOFT="#E3E3E6",
    SEP="#E0E0E3",
    HOVER="#F0F0F2",
    PRESSED="#E6E6E9",
    SCROLL="#C2C2C7",
    SCROLL_HOVER="#9A9AA0",
    FIND_EDGE="#D0D0D5",
    FIELD_LINE="#B9B9BF",
    DASH="#C9C9CE",
    RADIO_EDGE="#8A8A90",
    TEXT="#1B1B1B",
    ICON="#3A3A3A",
    MUTED="#5F5F5F",
    SUBTLE="#6B6B70",  # notes under settings
    DISABLED="#A0A0A5",
    DANGER="#C42B1C",
    ERROR="#C5221F",
    WARN="#D9822B",
    TIP_BG="#1B1B1B",
    TIP_FG="#FFFFFF",
    TIP_EDGE="#1B1B1B",
    RUBBER="rgba(16, 124, 65, 40)",
    PAGE_EDGE="#D0D0D5",  # the line round each page
)
DARK_SET = dict(
    ACCENT="#4CC38A",
    ACCENT_FILL="#107C41",
    ACCENT_DARK="#0E8F4A",
    ACCENT_SOFT="#2F5A42",
    TINT="#1F3B2C",
    TINT_HOVER="#27503A",
    TINT_TEXT="#7FD9A9",
    CANVAS="#1A1A1C",
    SURFACE="#2B2B2E",
    SOFT="#232326",
    PANEL="#262629",
    NAV="#202023",
    BORDER="#38383C",
    LINE="#4A4A50",
    LINE_SOFT="#3A3A3F",
    SEP="#404045",
    HOVER="#3A3A3E",
    PRESSED="#444449",
    SCROLL="#55555B",
    SCROLL_HOVER="#76767D",
    FIND_EDGE="#4A4A50",
    FIELD_LINE="#6A6A70",
    DASH="#5A5A60",
    RADIO_EDGE="#9A9AA0",
    TEXT="#EDEDEF",
    ICON="#D4D4D8",
    MUTED="#A8A8AE",
    SUBTLE="#A0A0A6",
    DISABLED="#68686E",
    DANGER="#FF7B6B",
    ERROR="#FF8A80",
    WARN="#E8A25A",
    TIP_BG="#3A3A3E",
    TIP_FG="#F2F2F2",
    TIP_EDGE="#55555B",
    RUBBER="rgba(76, 195, 138, 50)",
    PAGE_EDGE="#000000",
)
MODES = ("auto", "light", "dark")  # auto: the same as Windows
FONT_FAMILIES = ["Segoe UI Variable Text", "Segoe UI", "Arial"]
DARK = False
MODE = "auto"
_listeners = []  # called after a switch, for the few things that keep a colour of their own
globals().update(LIGHT)

_QSS = """
QMainWindow, QDialog {{ background: {SOFT}; }}
QToolTip {{ background: {TIP_BG}; color: {TIP_FG}; border: 1px solid {TIP_EDGE}; padding: 4px 8px; border-radius: 4px; }}
QMenu {{ background: {SURFACE}; border: 1px solid {LINE}; border-radius: 8px; padding: 6px; }}
QMenu::item {{ padding: 7px 28px 7px 10px; border-radius: 4px; color: {TEXT}; }}
QMenu::item:selected {{ background: {HOVER}; }}
QMenu::item:disabled {{ color: {DISABLED}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 5px 8px; }}
QMenu::icon {{ padding-left: 8px; }}
QPushButton {{ background: {SURFACE}; border: 1px solid {LINE}; border-radius: 4px; padding: 6px 14px;
               color: {TEXT}; }}
QPushButton:hover {{ background: {HOVER}; }}
QPushButton:disabled {{ color: {DISABLED}; }}
QPushButton:default, QPushButton[primary="true"] {{ background: {ACCENT_FILL}; border-color: {ACCENT_FILL}; color: white;
                                                   font-weight: 600; }}
QPushButton:default:hover, QPushButton[primary="true"]:hover {{ background: {ACCENT_DARK}; }}
QPushButton[primary="true"]:disabled {{ background: {ACCENT_SOFT}; border-color: {ACCENT_SOFT}; color: white; }}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{ background: {SURFACE}; border: 1px solid {LINE}; border-radius: 4px;
               padding: 4px 6px; selection-background-color: {ACCENT_FILL}; }}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border: 1px solid {ACCENT}; }}
QScrollBar:vertical {{ background: transparent; width: 12px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {SCROLL}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {SCROLL_HOVER}; }}
QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {SCROLL}; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QSplitter::handle {{ background: transparent; }}
QSlider::groove:horizontal {{ height: 4px; background: {LINE}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {SURFACE}; border: 2px solid {ACCENT}; width: 12px; height: 12px;
                              margin: -6px 0; border-radius: 8px; }}
QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 6px; background: {SURFACE}; }}
QTabBar::tab {{ padding: 6px 14px; border: none; color: {ICON}; }}
QTabBar::tab:selected {{ color: {ACCENT}; border-bottom: 2px solid {ACCENT}; }}  /* not bold: Qt cuts it off */

/* the top bar */
#topBar {{ background: {SURFACE}; border-bottom: 1px solid {BORDER}; }}
#topBar QToolButton {{ border: 1px solid transparent; border-radius: 6px; padding: 5px 8px; color: {TEXT};
                       background: transparent; }}
#topBar QToolButton:hover {{ background: {HOVER}; }}
#topBar QToolButton:checked {{ background: {TINT}; border-color: {ACCENT}; color: {ACCENT}; font-weight: 600; }}
#topBar QToolButton:disabled {{ color: {DISABLED}; }}
#topBar QToolButton[iconOnly="true"] {{ padding: 6px; }}
#topBar QToolButton[toggleOn="true"] {{ background: {TINT}; color: {ACCENT}; }}
#topBar QToolButton::menu-indicator {{ image: none; width: 0; }}
#fileName {{ font-weight: 600; color: {TEXT}; }}
#edited {{ color: {MUTED}; font-size: 12px; }}
#modeTitle {{ font-weight: 600; color: {TEXT}; }}
#tabs {{ background: {HOVER}; border-radius: 8px; }}
#tabs QToolButton {{ border: none; border-radius: 6px; padding: 5px 12px; color: {ICON}; }}
#tabs QToolButton:checked {{ background: {SURFACE}; color: {ACCENT}; font-weight: 600; }}
#tabs QToolButton:hover:!checked {{ background: {PRESSED}; }}
#chip {{ background: {TINT}; color: {ACCENT}; font-weight: 600; border-radius: 11px; padding: 3px 10px; }}
#barSep {{ background: {SEP}; }}
#sideTab {{ background: {SURFACE}; border: 1px solid {LINE}; border-left: none; border-top-right-radius: 6px; border-bottom-right-radius: 6px; padding: 0; }}
#sideTab:hover {{ background: {HOVER}; }}
#stampGroup[grouped="true"] {{ background: {HOVER}; border: 1px solid {BORDER}; border-radius: 8px; }}
#topBar QToolButton[mini="true"] {{ padding: 3px; }}

/* floating bits over the pages */
#pill, #findBar, #miniBar, #sizePill {{ background: {SURFACE}; border-radius: 18px; }}
#findBar, #miniBar {{ border-radius: 8px; }}
#pill QToolButton, #findBar QToolButton, #miniBar QToolButton, #sizePill QToolButton {{
    border: none; border-radius: 6px; padding: 4px; background: transparent; color: {TEXT}; }}
#pill QToolButton:hover, #findBar QToolButton:hover, #miniBar QToolButton:hover {{ background: {HOVER}; }}
#miniBar QToolButton:checked {{ background: {TINT}; color: {ACCENT}; }}
#pill QLineEdit {{ border: none; background: transparent; padding: 0; }}
#findBar {{ border: 1px solid {FIND_EDGE}; }}
#findBar QLineEdit {{ border: none; border-bottom: 1px solid {FIELD_LINE}; border-radius: 0; background: transparent;
    padding: 3px 2px; }}
#findBar QLineEdit:focus {{ border-bottom: 2px solid {ACCENT}; }}
#findBar QToolButton {{ padding: 3px; }}
#pillText, #findCount {{ color: {MUTED}; }}
#toast {{ background: {TIP_BG}; color: {TIP_FG}; border: 1px solid {TIP_EDGE}; border-radius: 6px; padding: 8px 14px; }}

/* home */
#home {{ background: {SOFT}; }}
#homeTitle {{ font-size: 20px; font-weight: 600; color: {TEXT}; }}
#openBig {{ background: {ACCENT_FILL}; border: 1px solid {ACCENT_FILL}; border-radius: 8px; color: white; text-align: left;
            padding: 12px 14px; font-weight: 600; }}
#openBig:hover {{ background: {ACCENT_DARK}; }}
#startBtn {{ background: {TINT}; border: 1px solid {TINT}; border-radius: 8px; text-align: left;
             padding: 12px 14px; color: {TINT_TEXT}; font-weight: 600; }}
#startBtn:hover {{ background: {TINT_HOVER}; border-color: {ACCENT}; }}
#dropHint {{ border: 1.5px dashed {DASH}; border-radius: 8px; color: {MUTED}; padding: 16px; }}
#banner {{ background: {SURFACE}; border: 1px solid {LINE_SOFT}; border-radius: 8px; }}
#card {{ background: {SURFACE}; border: 1px solid {LINE_SOFT}; border-radius: 8px; }}
#card:hover {{ border-color: {ACCENT}; }}
#cardName {{ font-weight: 600; color: {TEXT}; }}
#cardWhere, #muted {{ color: {MUTED}; font-size: 12px; }}
QRubberBand {{ background: {RUBBER}; border: 1px solid {ACCENT}; }}
#commentsPanel {{ background: {PANEL}; border-left: 1px solid {LINE_SOFT}; }}
#commentList {{ background: {PANEL}; }}
#commentCard {{ background: {SURFACE}; border: 1px solid {LINE_SOFT}; border-radius: 8px; }}
#commentCard[selected="true"] {{ border: 2px solid {ACCENT}; }}
#commentReply {{ border: none; border-left: 2px solid {LINE_SOFT}; }}
#commentTool {{ border: 1px solid transparent; border-radius: 6px; background: transparent; }}
#commentTool:hover {{ background: {HOVER}; }}
#commentTool:checked {{ background: {TINT}; border-color: {ACCENT}; }}
#link {{ color: {ACCENT}; border: none; background: transparent; padding: 0; }}
#link:hover {{ text-decoration: underline; }}

/* thumbnails */
#sidebar {{ background: {SOFT}; border: none; border-right: 1px solid {SEP}; }}
#pagesGrid {{ background: {CANVAS}; border: none; }}

/* bits that used to carry their own colours */
#choiceNote {{ color: {SUBTLE}; font-size: 12px; margin: 0 2px 8px 2px; }}
#subtle {{ color: {SUBTLE}; }}
#error {{ color: {ERROR}; }}
QToolButton#menuRow {{ border: none; border-radius: 4px; padding: 6px 10px; text-align: left; color: {TEXT}; }}
QToolButton#menuRow:hover {{ background: {HOVER}; }}
QListWidget, QTreeWidget, QTableWidget {{ color: {TEXT}; }}
QHeaderView::section {{ background: {SOFT}; color: {MUTED}; border: none; border-bottom: 1px solid {BORDER};
    padding: 4px 6px; }}
QTableWidget {{ background: {SURFACE}; gridline-color: {BORDER}; border: 1px solid {BORDER}; }}
QGroupBox {{ color: {TEXT}; }}
QProgressBar {{ border: 1px solid {LINE}; border-radius: 4px; background: {SURFACE}; text-align: center; color: {TEXT}; }}
QProgressBar::chunk {{ background: {ACCENT_FILL}; border-radius: 3px; }}
"""


def qss():
    return _QSS.format(**(DARK_SET if DARK else LIGHT))


def _arrows():
    """Small chevrons for spin boxes and drop-down lists (style sheets need them as files)."""
    import os
    import tempfile
    folder = os.path.join(tempfile.gettempdir(), "aerialist-ui")
    mode = "dark" if DARK else "light"  # its own files: Qt keeps pictures it has loaded by their path
    os.makedirs(folder, exist_ok=True)
    paths = {}
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QImage, QPainter, QPen
    for name, pts in (("up", [(4, 15), (10, 9), (16, 15)]), ("down", [(4, 9), (10, 15), (16, 9)])):
        img = QImage(20, 24, QImage.Format_ARGB32)  # drawn at 2x for sharp screens
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(ICON), 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPolyline([QPointF(x, y) for x, y in pts])
        p.end()
        path = os.path.join(folder, f"{name}-{mode}.png")
        img.save(path)
        paths[name] = path.replace("\\", "/")
    # Round option buttons and tick boxes in the emerald style (also drawn at 2x).
    for name in ("radio", "radio_on", "check", "check_on"):
        img = QImage(32, 32, QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        on = name.endswith("_on")
        if name.startswith("radio"):
            p.setPen(QPen(QColor(ACCENT_FILL if on else RADIO_EDGE), 2.4))
            p.setBrush(QColor(SURFACE))
            p.drawEllipse(QPointF(16, 16), 13, 13)
            if on:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(ACCENT_FILL))
                p.drawEllipse(QPointF(16, 16), 7, 7)
        else:
            p.setPen(QPen(QColor(ACCENT_FILL if on else RADIO_EDGE), 2.4))
            p.setBrush(QColor(ACCENT_FILL if on else SURFACE))
            p.drawRoundedRect(3, 3, 26, 26, 5, 5)
            if on:
                p.setPen(QPen(QColor("white"), 3.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                p.drawPolyline([QPointF(9, 16.5), QPointF(14, 21.5), QPointF(23, 11)])
        p.end()
        path = os.path.join(folder, f"{name}-{mode}.png")
        img.save(path)
        paths[name] = path.replace("\\", "/")
    return f"""
QSpinBox, QDoubleSpinBox {{{{ padding-right: 18px; }}}}
QSpinBox::up-button, QDoubleSpinBox::up-button {{{{ subcontrol-origin: border; subcontrol-position: top right;
    width: 18px; border: none; background: transparent; }}}}
QSpinBox::down-button, QDoubleSpinBox::down-button {{{{ subcontrol-origin: border; subcontrol-position: bottom right;
    width: 18px; border: none; background: transparent; }}}}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{{{ background: {HOVER}; }}}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{{{ image: url({paths["up"]}); width: 10px; height: 12px; }}}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{{{ image: url({paths["down"]}); width: 10px; height: 12px; }}}}
QRadioButton::indicator, QCheckBox::indicator {{{{ width: 16px; height: 16px; }}}}
QRadioButton::indicator:unchecked {{{{ image: url({paths["radio"]}); }}}}
QRadioButton::indicator:checked {{{{ image: url({paths["radio_on"]}); }}}}
QCheckBox::indicator:unchecked {{{{ image: url({paths["check"]}); }}}}
QCheckBox::indicator:checked {{{{ image: url({paths["check_on"]}); }}}}
QListView::indicator {{{{ width: 16px; height: 16px; }}}}
QListView::indicator:unchecked {{{{ image: url({paths["check"]}); }}}}
QListView::indicator:checked {{{{ image: url({paths["check_on"]}); }}}}
#topBar QToolButton[dropdown="true"] {{{{ padding-right: 18px; }}}}
#topBar QToolButton[dropdown="true"]::menu-indicator {{{{ image: url({paths["down"]}); width: 9px; height: 11px;
    subcontrol-origin: padding; subcontrol-position: center right; right: 4px; }}}}
#topBar QToolButton::menu-button {{{{ border: none; background: transparent; width: 16px; }}}}
#topBar QToolButton::menu-arrow {{{{ image: url({paths["down"]}); width: 9px; height: 11px; }}}}
QComboBox::drop-down {{{{ border: none; width: 20px; }}}}
QComboBox::down-arrow {{{{ image: url({paths["down"]}); width: 10px; height: 12px; }}}}
""".replace("{{", "{").replace("}}", "}")


def on_change(fn):
    """Call fn() after every switch between light and dark."""
    _listeners.append(fn)


def windows_dark():
    """Whether Windows is set to dark apps."""
    app = QApplication.instance()
    return bool(app) and app.styleHints().colorScheme() == Qt.ColorScheme.Dark


def set_mode(mode, app=None):
    """"light", "dark" or "auto" (follow Windows, and keep following it)."""
    global MODE, DARK
    app = app or QApplication.instance()
    MODE = mode if mode in MODES else "auto"
    hints = app.styleHints()
    # Tell Qt too, so Windows draws the window's title bar to match.
    hints.setColorScheme({"light": Qt.ColorScheme.Light, "dark": Qt.ColorScheme.Dark}.get(MODE, Qt.ColorScheme.Unknown))
    dark = hints.colorScheme() == Qt.ColorScheme.Dark if MODE == "auto" else MODE == "dark"
    if dark == DARK and getattr(app, "_themed", False):
        return
    DARK = dark
    globals().update(DARK_SET if dark else LIGHT)
    _style(app)
    for fn in list(_listeners):
        try:
            fn()
        except RuntimeError:  # its widget is gone
            _listeners.remove(fn)


def _follow_windows():
    if MODE == "auto":
        set_mode("auto")


def _style(app):
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(SOFT))
    pal.setColor(QPalette.WindowText, QColor(TEXT))
    pal.setColor(QPalette.Base, QColor(SURFACE))
    pal.setColor(QPalette.AlternateBase, QColor(SOFT))
    pal.setColor(QPalette.Text, QColor(TEXT))
    pal.setColor(QPalette.Button, QColor(SURFACE))
    pal.setColor(QPalette.ButtonText, QColor(TEXT))
    pal.setColor(QPalette.Highlight, QColor(ACCENT_FILL))
    pal.setColor(QPalette.HighlightedText, QColor("white"))
    pal.setColor(QPalette.Link, QColor(ACCENT))
    pal.setColor(QPalette.ToolTipBase, QColor(TIP_BG))
    pal.setColor(QPalette.ToolTipText, QColor(TIP_FG))
    pal.setColor(QPalette.PlaceholderText, QColor(DISABLED))
    pal.setColor(QPalette.Mid, QColor(LINE))
    pal.setColor(QPalette.Midlight, QColor(LINE_SOFT))
    pal.setColor(QPalette.Light, QColor(SURFACE))
    pal.setColor(QPalette.Dark, QColor(SCROLL))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, QColor(DISABLED))
    app.setPalette(pal)
    app.setStyleSheet(qss() + _arrows())
    app._themed = True


class _Style(QProxyStyle):
    """Fusion, with the popups' question / info / warning / error icons drawn in the app's own colours."""
    GLYPHS = {QStyle.SP_MessageBoxQuestion: ("?", "#107C41"), QStyle.SP_MessageBoxInformation: ("i", "#107C41"),
              QStyle.SP_MessageBoxWarning: ("!", "#D9822B"), QStyle.SP_MessageBoxCritical: ("×", "#C42B1C")}

    def polish(self, *args):
        target = args[0] if args else None
        if isinstance(target, QPushButton):  # only buttons pass through the filter, not every event
            room = getattr(QApplication.instance(), "_bold_room", None)
            if room is not None:
                target.installEventFilter(room)
        return super().polish(*args)

    def standardIcon(self, sp, opt=None, widget=None):
        if sp not in self.GLYPHS:
            return super().standardIcon(sp, opt, widget)
        glyph, fill = self.GLYPHS[sp]
        size, dpr = 32, 2.0
        pix = QPixmap(int(size * dpr), int(size * dpr))
        pix.setDevicePixelRatio(dpr)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(fill))
        p.drawEllipse(QRectF(2, 2, size - 4, size - 4))
        font = QFont()
        font.setFamilies(FONT_FAMILIES)
        font.setBold(True)
        font.setPixelSize(22 if glyph == "×" else 18)
        p.setFont(font)
        p.setPen(QColor("white"))
        p.drawText(QRectF(0, 0, size, size - (2 if glyph == "×" else 0)), Qt.AlignCenter, glyph)
        p.end()
        return QIcon(pix)


class _BoldRoom(QObject):
    """The green (default) button's words are bold, but Qt sizes buttons for plain words, so the end of a
    longer label got cut off ("Throw awa"). Every button gets room for its words in bold, since a dialog
    turns whichever button has the focus into the default one."""

    def eventFilter(self, obj, e):
        if e.type() == QEvent.Show and isinstance(obj, QPushButton) and obj.text():
            bold = QFont(obj.font())
            bold.setWeight(QFont.DemiBold)
            text = obj.text().replace("&&", "\0").replace("&", "").replace("\0", "&")
            extra = QFontMetrics(bold).horizontalAdvance(text) - QFontMetrics(obj.font()).horizontalAdvance(text)
            if extra > 0:
                obj.setMinimumWidth(max(obj.minimumWidth(), obj.sizeHint().width() + extra + 2))
        return False


def apply(app, mode="auto"):
    app._proxy_style = _Style("Fusion")
    app.setStyle(app._proxy_style)
    app._bold_room = _BoldRoom(app)
    font = QFont()
    font.setFamilies(FONT_FAMILIES)
    font.setPointSizeF(10)
    app.setFont(font)
    app.styleHints().colorSchemeChanged.connect(lambda _=None: _follow_windows())
    set_mode(mode, app)


def colours():
    return DARK_SET if DARK else LIGHT


def style(widget, css):
    """widget.setStyleSheet(css) with {NAME} filled in from the theme, done again after each switch."""
    def put():
        widget.setStyleSheet(css.format(**colours()))
    put()
    _listeners.append(put)
    widget.destroyed.connect(lambda *_: put in _listeners and _listeners.remove(put))
