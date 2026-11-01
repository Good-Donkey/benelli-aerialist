"""Line icons, style B: bold rounded outline (2.3 px on a 24 px grid). Dark grey normally,
emerald when on, grey when unavailable. Shapes from the design mockups."""
from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QIconEngine, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from . import theme

STROKE = 2.3
PATHS = {
    "menu": "M4 6h16M4 12h16M4 18h16",
    "thumbs": "M3.5 5h17v14h-17zM9 5v14",
    "find": "M10.5 4a6.5 6.5 0 110 13 6.5 6.5 0 010-13zM15.5 15.5L21 21",
    "more": "M5 12h.01M12 12h.01M19 12h.01",
    "read": "M12 6.5C10 5 7 4.5 3.5 5v13c3.5-.5 6.5 0 8.5 1.5 2-1.5 5-2 8.5-1.5V5C17 4.5 14 5 12 6.5zM12 6.5V19",
    "pages": "M4 4h6.5v7H4zM13.5 4H20v7h-6.5zM4 14h6.5v7H4zM13.5 14H20v7h-6.5z",
    "edit": "M13 3H5v18h6M13 3l5 5h-5zM18 8v3M13.5 21v-2.6l6.2-6.2 2.6 2.6-6.2 6.2z",
    "sign": "M3 20.5h18M3.5 16c2-5.5 4-9.5 5.5-8.5S7.5 15.5 9.8 15.3 12.5 11 14 11.5s.4 3.8 2.5 3.8 2.7-2 4-2",
    "select": "M5 3l13 7.5-6 1.5-2.5 6z",
    "move": "M12 3v18M3 12h18M9 6l3-3 3 3M9 18l3 3 3-3M6 9l-3 3 3 3M18 9l3 3-3 3",
    "text": "M5 5h14M12 5v14M9 19h6",
    "image": "M3 5h18v14H3zM3 16l5-5 4 4 3-3 6 6M15.5 8.5a1.2 1.2 0 110 .01",
    "shape": "M3 4h9v9H3zM16.5 11a4.5 4.5 0 110 9 4.5 4.5 0 010-9z",
    "rect": "M4 5h16v14H4z",
    "ellipse": "M12 5c4.7 0 8.5 3.1 8.5 7s-3.8 7-8.5 7-8.5-3.1-8.5-7 3.8-7 8.5-7z",
    "line": "M5 19L19 5",
    "arrow": "M5 19L19 5M10 5h9v9",
    "draw": "M3 21l3.5-1L19 7.5 16.5 5 4 17.5zM14.5 7l2.5 2.5",
    "marker": "M4 20h16M7 15l7-10 4 3-7 10H7z",
    "highlight": "M4 20h16M7 15l7-10 4 3-7 10H7z",
    "whiteout": "M3 7h18v10H3zM7 11h10",
    "wpen": "M3 21l3.5-1L19 7.5 16.5 5 4 17.5zM14.5 7l2.5 2.5M14 21h7",
    "undo": "M8 5L4 9l4 4M4 9h11a5 5 0 010 10h-3",
    "redo": "M16 5l4 4-4 4M20 9H9a5 5 0 000 10h3",
    "open": "M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z",
    "recent": "M12 3a9 9 0 110 18 9 9 0 010-18zM12 7v5l3 2",
    "save": "M5 3h11l4 4v14H5zM8 3v5h7V3M8 21v-7h8v7",
    "save_copy": "M8 3h9l4 4v11H8zM5 7v14h11",
    "save_images": "M13 3H6v18h6M13 3l5 5h-5zM18 8v4M15 18h7M19 15l3 3-3 3",
    "pictures": "M3 5h18v14H3zM3 16l5-5 4 4 3-3 6 6M15.5 8.5a1.2 1.2 0 110 .01",
    "convert": "M4 8h13M14 4.5L17.5 8 14 11.5M20 16H7M10 12.5L6.5 16l3.5 3.5",
    "fill": "M5 11l6.5-6.5 7 7L12 18a1.5 1.5 0 01-2 0l-5-5a1.5 1.5 0 010-2zM5 11h13.5M20 15.5c0 1-1.5 2.5-1.5 3.5a1.5 1.5 0 003 0c0-1-1.5-2.5-1.5-3.5z",
    "star": "M12 3l2.6 5.5 6 .8-4.4 4.2 1.1 6L12 16.6 6.7 19.5l1.1-6L3.4 9.3l6-.8z",
    "close": "M6 6l12 12M18 6L6 18",
    "rot_right": "M20 12a8 8 0 11-3-6.2M20 3v5h-5",
    "rot_left": "M4 12a8 8 0 103-6.2M4 3v5h5",
    "delete": "M4 6h16M9 6V4h6v2M6.5 6l1 14h9l1-14",
    "plus": "M12 5v14M5 12h14",
    "minus": "M5 12h14",
    "merge": "M3.5 3h6v7h-6zM14.5 3h6v7h-6zM6.5 10v2.5h11V10M12 12.5V15M8.5 15h7v6.5h-7z",
    "prev": "M15 5l-7 7 7 7",
    "next": "M9 5l7 7-7 7",
    "up": "M5 15l7-7 7 7",
    "down": "M5 9l7 7 7-7",
    "page_up": "M5 12l7-7 7 7M5 19l7-7 7 7",
    "page_down": "M5 5l7 7 7-7M5 12l7 7 7-7",
    "fit_width": "M3 12h18M7 8l-4 4 4 4M17 8l4 4-4 4",
    "fit_page": "M6 3h12v18H6zM9 9h6M9 13h6",
    "check": "M4.5 12.5l5 5L19.5 6.5",
    "stamp": "M9.5 3.5h5l-.8 6.5h4.8a1.5 1.5 0 011.5 1.5V15h-16v-3.5A1.5 1.5 0 015.5 10h4.8zM4.5 18.5h15",
    "date": "M4 6h16v15H4zM4 10h16M8 3v5M16 3v5",
    "initials": "M4 19l4.5-14L13 19M5.8 14h5.4M15 19V5h3a3.5 3.5 0 010 7h-3",
    "person": "M12 4a4 4 0 110 8 4 4 0 010-8zM4.5 20.5c1-4 4-6 7.5-6s6.5 2 7.5 6",
    "next_field": "M4 12h13M13 7l5 5-5 5M20 5v14",
    "chevron": "M7 10l5 5 5-5",
    "home": "M3.5 11L12 4l8.5 7M6 9v11h4.5v-5.5h3V20H18V9",
    "textfield": "M3 7h18v10H3zM7 10v4",
    "checkbox": "M4 4h16v16H4zM8 12.5l3 3 5-6.5",
    "snip": "M6 4.5a2.5 2.5 0 110 5 2.5 2.5 0 010-5zM6 14.5a2.5 2.5 0 110 5 2.5 2.5 0 010-5zM8.1 8.4L20 18.5M8.1 15.6L20 5.5",
    "link": "M10 14a4 4 0 005.7 0l3.5-3.5a4 4 0 00-5.7-5.7L12 6.3M14 10a4 4 0 00-5.7 0l-3.5 3.5a4 4 0 005.7 5.7l1.5-1.5",
    "comment": "M4 5h16v11H10l-4.5 4v-4H4z",
    "note": "M4 4h16v11l-5 5H4zM15 20v-5h5M8 9h8M8 12.5h5",
    "underline": "M7 4v6.5a5 5 0 0010 0V4M5 20h14",
    "strike": "M4 12h16M16.5 7c-.8-1.6-2.4-2.5-4.5-2.5-2.6 0-4.3 1.4-4.3 3.3 0 1.5 1 2.5 3 3.2M8 16.5c.8 1.8 2.5 3 4.5 3 2.7 0 4.3-1.5 4.3-3.4 0-.8-.3-1.6-.8-2.1",
    "exit": "M10 4H5v16h5M14 8l4 4-4 4M18 12H9",
}


def _svg(name, color, stroke=STROKE):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
            f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round"><path d="{PATHS[name]}"/></svg>')


def colour(c):
    """A colour, or the name of one of the theme's (\"ICON\", \"ACCENT\"…) as it is right now."""
    return getattr(theme, c) if isinstance(c, str) and c.isidentifier() and c.isupper() else c


def pixmap(name, size=20, color="ICON", dpr=2.0, stroke=STROKE):
    pix = QPixmap(int(size * dpr), int(size * dpr))
    pix.fill(Qt.transparent)
    pix.setDevicePixelRatio(dpr)
    p = QPainter(pix)
    QSvgRenderer(QByteArray(_svg(name, colour(color), stroke).encode())).render(p, QRectF(0, 0, size, size))
    p.end()
    return pix


class _Engine(QIconEngine):
    """Draws the icon in the theme's colours of the moment, so it follows a switch to dark and back."""

    def __init__(self, name, color, on, size):
        super().__init__()
        self.args = (name, color, on, size)

    def _pix(self, mode, state, dpr):
        name, color, on, size = self.args
        c = theme.DISABLED if mode == QIcon.Disabled else colour(on if state == QIcon.On else color)
        key = (name, c, size, dpr)
        if key not in _pixes:
            _pixes[key] = pixmap(name, size, c, dpr)
        return _pixes[key]

    def paint(self, painter, rect, mode, state):
        dpr = painter.device().devicePixelRatioF() if painter.device() else 2.0
        painter.drawPixmap(rect, self._pix(mode, state, max(2.0, dpr)))

    def pixmap(self, size, mode, state):
        return self._pix(mode, state, 2.0)

    def scaledPixmap(self, size, mode, state, scale):
        return self._pix(mode, state, max(1.0, scale))

    def clone(self):
        return _Engine(*self.args)


class _Drawn(QIconEngine):
    """An icon painted by a function, painted again after a switch between light and dark."""

    def __init__(self, draw):
        super().__init__()
        self.draw, self.made = draw, {}

    def _pix(self):
        if theme.DARK not in self.made:
            self.made[theme.DARK] = self.draw()
        return self.made[theme.DARK]

    def paint(self, painter, rect, mode, state):
        painter.drawPixmap(rect, self._pix())

    def pixmap(self, size, mode, state):
        return self._pix()

    def scaledPixmap(self, size, mode, state, scale):
        return self._pix()

    def clone(self):
        return _Drawn(self.draw)


def drawn(draw):
    """QIcon from draw() -> QPixmap, redrawn in the other theme's colours when it changes."""
    return QIcon(_Drawn(draw))


_cache = {}
_pixes = {}


def icon(name, color="ICON", on="ACCENT", size=20):
    """Icon that turns emerald when its button is checked, grey when disabled. Colours can be theme names."""
    key = (name, color, on, size)
    if key not in _cache:
        _cache[key] = QIcon(_Engine(name, color, on, size))
    return _cache[key]
