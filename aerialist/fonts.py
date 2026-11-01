"""Fonts for text written into PDFs.

Three sources, in the order they're listed:
  * PDF built-in fonts (Helvetica, Times, Courier): every reader has them, nothing is embedded.
  * Fonts shipped with the app in assets/fonts (free Google fonts under the SIL Open Font License).
    Arimo, Tinos and Cousine are drop-in matches for Arial, Times New Roman and Courier New.
  * Fonts installed on Windows (Calibri, Cambria, ...).
Non-built-in fonts are embedded in the PDF; saving trims them to the letters actually used.
"""
import hashlib
import os
import re
import sys

import pymupdf
from PySide6.QtGui import QFont, QFontDatabase

from . import pdfio

APP_FONTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "fonts")
BUILTIN = {"helv": ("Helvetica (built-in)", "Arial"), "tiro": ("Times (built-in)", "Times New Roman"),
           "cour": ("Courier (built-in)", "Courier New")}
CODES = {("helv", 0, 0): "helv", ("helv", 1, 0): "hebo", ("helv", 0, 1): "heit", ("helv", 1, 1): "hebi",
         ("tiro", 0, 0): "tiro", ("tiro", 1, 0): "tibo", ("tiro", 0, 1): "tiit", ("tiro", 1, 1): "tibi",
         ("cour", 0, 0): "cour", ("cour", 1, 0): "cobo", ("cour", 0, 1): "coit", ("cour", 1, 1): "cobi"}
STYLES = {"Regular": (0, 0), "Bold": (1, 0), "Italic": (0, 1), "BoldItalic": (1, 1)}
HANDWRITING = ["Caveat", "Dancing Script", "Great Vibes"]  # shipped fonts that suit typed signatures

used_embedded = False  # set once a non-built-in font has been written into the document


class FontInfo:
    def __init__(self, key, label, family, files=None, source="builtin"):
        self.key, self.label, self.family, self.source = key, label, family, source
        self.files = files or {}  # (bold, italic) -> font file


_fonts = None  # key -> FontInfo, in list order


def _load():
    global _fonts
    _fonts = {}
    for key, (label, family) in BUILTIN.items():
        _fonts[key] = FontInfo(key, label, family)
    # Shipped fonts.
    if os.path.isdir(APP_FONTS):
        for folder in sorted(os.listdir(APP_FONTS)):
            files = {}
            for name in os.listdir(os.path.join(APP_FONTS, folder)):
                stem, ext = os.path.splitext(name)
                style = stem.rsplit("-", 1)[-1]
                if ext.lower() == ".ttf" and style in STYLES:
                    files[STYLES[style]] = os.path.join(APP_FONTS, folder, name)
            if (0, 0) not in files:
                continue
            fid = QFontDatabase.addApplicationFont(files[(0, 0)])
            fams = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
            for path in files.values():
                if path != files[(0, 0)]:
                    QFontDatabase.addApplicationFont(path)
            family = fams[0] if fams else folder
            key = "app:" + family
            _fonts[key] = FontInfo(key, family, family, files, "app")
    # Installed Windows fonts.
    if sys.platform == "win32":
        installed = {}
        try:
            for family, style, path in _windows_fonts():
                installed.setdefault(family, {}).setdefault(style, path)
        except Exception:
            pass  # an odd registry entry shouldn't stop the app; the other fonts still work
        for family in sorted(installed, key=str.lower):
            files = installed[family]
            if (0, 0) not in files or any(f.family == family for f in _fonts.values()):
                continue
            key = "win:" + family
            _fonts[key] = FontInfo(key, family, family, files, "windows")


def _windows_fonts():
    """(family, (bold, italic), file) for each installed TrueType/OpenType font file."""
    import winreg
    places = [(winreg.HKEY_LOCAL_MACHINE, os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")),
              (winreg.HKEY_CURRENT_USER, os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts"))]
    for root, folder in places:
        try:
            k = winreg.OpenKey(root, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts")
        except OSError:
            continue
        i = 0
        while True:
            try:
                name, value, _ = winreg.EnumValue(k, i)
            except OSError:
                break
            i += 1
            path = value if os.path.isabs(value) else os.path.join(folder, value)
            if not path.lower().endswith((".ttf", ".otf")) or "&" in name:
                continue
            name = re.sub(r"\s*\((TrueType|OpenType)\)\s*$", "", name).strip()
            bold = italic = 0
            for suffix, b, it in ((" Bold Italic", 1, 1), (" Bold Oblique", 1, 1), (" Bold", 1, 0),
                                  (" Italic", 0, 1), (" Oblique", 0, 1), (" Regular", 0, 0)):
                if name.endswith(suffix):
                    name, bold, italic = name[: -len(suffix)], b, it
                    break
            yield name, (bold, italic), path


def all_fonts():
    if _fonts is None:
        _load()
    return list(_fonts.values())


def get(key):
    if _fonts is None:
        _load()
    return _fonts.get(key) or _fonts["helv"]


def qfont(key, size_px, bold=False, italic=False):
    f = QFont(get(key).family)
    f.setPixelSize(max(1, round(size_px)))
    f.setBold(bool(bold))
    f.setItalic(bool(italic))
    return f


def _file(info, bold, italic):
    files = info.files
    return files.get((int(bool(bold)), int(bool(italic)))) or files.get((int(bool(bold)), 0)) or files.get((0, 0))


def pdf_args(key, bold=False, italic=False):
    """Keyword arguments for page.insert_text / insert_textbox."""
    global used_embedded
    info = get(key)
    if info.source == "builtin":
        return {"fontname": CODES[(info.key, int(bool(bold)), int(bool(italic)))]}
    path = _file(info, bold, italic)
    used_embedded = True
    return {"fontname": "BD" + hashlib.md5(path.encode()).hexdigest()[:8], "fontfile": path}


def save_copy(doc, path, password=None):
    """Save the document; fonts we embedded are trimmed to the letters used (in a copy, so the
    open document keeps full fonts for further editing). With a password, the file asks for it when opened."""
    # Always from a copy: tidying the file renumbers its parts, and the open document must keep its numbering
    # (comments are found by it).
    copy = pymupdf.open("pdf", pdfio.to_bytes(doc))
    if used_embedded:
        try:
            copy.subset_fonts()
        except Exception:
            pass  # a full font is bigger but still correct
    # garbage=3 also merges duplicate parts (smaller files after merging), but its time grows with the square of
    # the number of parts: under a second for most PDFs, ten seconds for a 400-page report. Big files skip it.
    lock = dict(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw=password, owner_pw=password) if password else {}
    copy.save(path, garbage=3 if copy.xref_length() <= 4000 else 2, deflate=True, **lock)
    copy.close()
