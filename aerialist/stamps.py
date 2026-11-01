"""Ready-made stamps (check mark, X, warning sign, and rubber stamps like RECEIVED) for Fill & Sign
and Edit. Drawn as large pictures with see-through backgrounds, then scaled down on the page."""
import json
import os
import uuid

from PySide6.QtCore import Qt, QPointF, QRectF, QDate, QLocale, QSettings
from PySide6.QtGui import QImage, QPainter, QPen, QColor, QFont, QFontMetricsF, QPainterPath


def _today():
    return QLocale(QLocale.English, QLocale.UnitedStates).toString(QDate.currentDate(), "MMM d, yyyy")


# Stamps: (key, menu label, default height in points).
STAMPS = [("check", "Check mark", 14), ("x", "X", 14), ("warning", "Warning", 20),
          ("attention", "Attention", 26), ("received", "Received", 32), ("missing", "Missing", 26)]
STAMP_COLORS = {"check": "#1E8C45", "x": "#D21F1F", "attention": "#D9480F", "received": "#1E8C45",
                "missing": "#D21F1F"}


# ---- your own stamps (pictures you add) and which stamps sit on the toolbar ----------------
def stamps_dir():
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "Aerialist", "stamps")


def _load_custom():
    try:
        with open(os.path.join(stamps_dir(), "stamps.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


custom = _load_custom()  # [{"key", "label", "file", "height"}]
_images = {}


def _save_custom():
    os.makedirs(stamps_dir(), exist_ok=True)
    tmp = os.path.join(stamps_dir(), "stamps.json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(custom, f, indent=1)
    os.replace(tmp, os.path.join(stamps_dir(), "stamps.json"))


def all_stamps():
    """(key, label, starting height) of every stamp: the ready-made ones, then your own."""
    return STAMPS + [(c["key"], c["label"], c["height"]) for c in custom]


def label(key):
    return next((lb for k, lb, _ in all_stamps() if k == key), key)


def add_custom(img, name):
    """Keep a picture as a stamp. Returns its key."""
    key = "c-" + uuid.uuid4().hex[:10]
    os.makedirs(stamps_dir(), exist_ok=True)
    fname = key + ".png"
    img.save(os.path.join(stamps_dir(), fname), "PNG")
    # Starts about as tall as a rubber stamp, or narrower if it is very wide.
    h = max(12, min(40, 160 * img.height() / max(1, img.width())))
    custom.append({"key": key, "label": name, "file": fname, "height": round(h, 1)})
    _save_custom()
    return key


def remove_custom(key):
    for c in list(custom):
        if c["key"] == key:
            custom.remove(c)
            try:
                os.remove(os.path.join(stamps_dir(), c["file"]))
            except OSError:
                pass
    _images.pop(key, None)
    _save_custom()
    set_quick([k for k in quick() if k != key])


def is_custom(key):
    return any(c["key"] == key for c in custom)


QUICK_DEFAULT = ["check", "x"]


def quick():
    """Stamps shown on the toolbar beside the Stamps menu."""
    v = QSettings("Aerialist", "Aerialist").value("stamps/quick")
    if v is None:
        return list(QUICK_DEFAULT)
    keys = [v] if isinstance(v, str) else list(v)
    have = {k for k, _, _ in all_stamps()}
    return [k for k in keys if k and k in have]


def set_quick(keys):
    QSettings("Aerialist", "Aerialist").setValue("stamps/quick", list(keys) or "")


def stamp_image(key):
    if key.startswith("c-"):
        if key not in _images:
            c = next((c for c in custom if c["key"] == key), None)
            img = QImage(os.path.join(stamps_dir(), c["file"])) if c else QImage()
            if img.isNull():
                img = QImage(8, 8, QImage.Format_ARGB32)
                img.fill(Qt.transparent)
            _images[key] = img
        return _images[key]
    return _builtin_image(key)


def _builtin_image(key):
    """A stamp drawn large (it is scaled down on the page): marks, a warning sign, or a rubber stamp."""
    color = QColor(STAMP_COLORS.get(key, "#1B1B1B"))
    if key in ("check", "x"):
        img = QImage(160, 160, QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(color, 20, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        if key == "check":
            path = QPainterPath(QPointF(24, 86))
            path.lineTo(64, 126)
            path.lineTo(138, 32)
            p.drawPath(path)
        else:
            p.drawLine(QPointF(32, 32), QPointF(128, 128))
            p.drawLine(QPointF(128, 32), QPointF(32, 128))
        p.end()
        return img
    if key == "warning":
        img = QImage(184, 160, QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        tri = QPainterPath(QPointF(92, 10))
        tri.lineTo(176, 150)
        tri.lineTo(8, 150)
        tri.closeSubpath()
        p.setPen(QPen(QColor("#1B1B1B"), 9, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(QColor("#F5C400"))
        p.drawPath(tri)
        p.setPen(QPen(QColor("#1B1B1B"), 15, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(92, 58), QPointF(92, 104))
        p.drawPoint(QPointF(92, 130))
        p.end()
        return img
    # Rubber stamps: bold capitals in a double frame; Received also gets today's date.
    word = {"attention": "ATTENTION", "received": "RECEIVED", "missing": "MISSING"}.get(key, key.upper())
    font = QFont()
    font.setFamilies(["Arial Black", "Arial", "Helvetica"])
    font.setPixelSize(64)
    font.setWeight(QFont.Black)
    font.setLetterSpacing(QFont.PercentageSpacing, 104)
    small = QFont(font)
    small.setPixelSize(30)
    small.setWeight(QFont.Bold)
    fm, fs = QFontMetricsF(font), QFontMetricsF(small)
    date = _today().upper() if key == "received" else ""
    w = max(fm.horizontalAdvance(word), fs.horizontalAdvance(date)) + 64
    h = fm.height() + (fs.height() + 4 if date else 0) + 36
    img = QImage(int(w), int(h), QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    p.setPen(QPen(color, 7))
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(QRectF(4, 4, w - 8, h - 8), 12, 12)
    p.setPen(QPen(color, 2.5))
    p.drawRoundedRect(QRectF(13, 13, w - 26, h - 26), 6, 6)
    p.setPen(color)
    p.setFont(font)
    top = 18
    p.drawText(QRectF(0, top, w, fm.height()), Qt.AlignCenter, word)
    if date:
        p.setFont(small)
        p.drawText(QRectF(0, top + fm.height(), w, fs.height()), Qt.AlignCenter, date)
    p.end()
    return img


# How big stamps are, as a multiple of their starting sizes. Shared by Fill & Sign and Edit, so the
# next stamp comes out the size the last one was given (by scrolling or dragging a corner).
scale = 1.0


def height(key):
    return next((h for k, _, h in all_stamps() if k == key), 26) * scale


def remember(key, h):
    global scale
    base = next((bh for k, _, bh in all_stamps() if k == key), None)
    if base:
        scale = max(0.3, min(8.0, h / base))


def grow(steps):
    """Scroll wheel while a stamp is picked up: bigger or smaller for the next one."""
    global scale
    scale = max(0.3, min(8.0, scale * 1.1 ** steps))
