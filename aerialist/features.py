"""What the app can do, and where to find each thing: shown once after each install or update, and from Home
and the ☰ menu any time."""
from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget,
)

from . import theme
from .icons import pixmap

# (icon, name, what it does, where to find it)
FEATURES = [
    ("read", "Read", "Open PDFs and pictures, find words (Ctrl+F), zoom with Ctrl+scroll, and scroll by "
     "holding the middle mouse button. Drag over text or click a picture to point it out or copy it (Ctrl+C).",
     "Open on Home, or double-click a PDF."),
    ("save", "Save and find your files", "Save, save a copy under a new name, reopen recent files, jump "
     "to a PDF's folder, and lock a PDF with a password.",
     "☰ > Save as…, Open recent, Show in File Explorer, and Password protect…"),
    ("print", "Print", "Print to any printer, or to a PDF with Microsoft Print to PDF, including what you've "
     "added, with a preview of each sheet. Choose pages, copies, paper and black and white.", "The printer at the top left (Ctrl+P), or ☰ > Print…"),
    ("snip", "Snip", "Copy any part of a page as a sharp picture to paste into an email or document, however "
     "far you're zoomed out. You can save it as a picture too.", "The scissors at the top right (Ctrl+Shift+X)."),
    ("comment", "Comments", "Sticky notes, highlight, underline and strike through text, and replies. Other PDF "
     "programs show them too.", "The speech bubble at the top right."),
    ("pages", "Organize & Merge", "Drag pages into order, rotate or delete them, add other PDFs and pictures, "
     "and save chosen pages as a new PDF.", "The Organize & Merge tab, or Merge PDFs on Home."),
    ("edit", "Edit", "Add text, pictures, shapes, drawings, highlighter, white-out, blur, stamps and links, and move "
     "or resize what's already on the page.", "The Edit tab."),
    ("sign", "Fill & Sign", "Fill in forms, and add signatures, initials, the date and text. Save signatures "
     "for several people.", "The Fill & Sign tab, or Fill & Sign on Home."),
    ("textfield", "Prepare Form", "Turn any PDF into a form people can fill in: text boxes, tick boxes and the "
     "order Tab goes through them.", "☰ > Prepare Form, or Form fields in Edit."),
    ("convert", "Convert", "Turn pictures, Word, Excel, PowerPoint and text files into PDFs, and PDFs into Word "
     "documents or pictures.", "Convert on Home. ☰ > Save pages as images for a PDF that's open."),
    ("pictures", "Resize pictures", "Make photos smaller for email, with a choice of sizes.",
     "☰ > Resize pictures."),
    ("open", "Right-click in File Explorer", "Open, convert, merge or resize files without opening the app "
     "first. Works on several files at once.", "Right-click files > Show more options."),
    ("undo", "Undo and redo", "Take back any change, in every tool.", "The arrows at the top left (Ctrl+Z, "
     "Ctrl+Y)."),
    ("star", "Make it yours", "Dark or light look, your own shortcuts and stamps, and which tools sit on the "
     "toolbar.", "☰ > Dark/Light Mode, and ☰ > Settings (Ctrl+,)."),
]


class FeaturesDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("What Benelli Aerialist can do")
        self.resize(600, 640)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 14)
        lay.setSpacing(10)
        head = QLabel("What Benelli Aerialist can do")
        head.setStyleSheet("font-size: 17px; font-weight: 600;")
        lay.addWidget(head)
        sub = QLabel("A quick tour of everything in the app, and where to find it.")
        sub.setObjectName("subtle")
        lay.addWidget(sub)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        body.setObjectName("featureList")
        theme.style(body, "#featureList {{ background: transparent; }}")
        rows = QVBoxLayout(body)
        rows.setContentsMargins(0, 4, 8, 4)
        rows.setSpacing(14)
        self._icons = []
        for icon_name, name, what, where in FEATURES:
            row = QHBoxLayout()
            row.setSpacing(12)
            ic = QLabel()
            ic.setFixedSize(QSize(26, 26))
            ic.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
            self._icons.append((ic, icon_name))
            row.addWidget(ic, 0, Qt.AlignTop)
            text = QVBoxLayout()
            text.setSpacing(2)
            title = QLabel(name)
            title.setStyleSheet("font-weight: 600;")
            desc = QLabel(what)
            desc.setWordWrap(True)
            place = QLabel("Where: " + where)
            place.setObjectName("subtle")
            place.setWordWrap(True)
            for w in (title, desc, place):
                text.addWidget(w)
            row.addLayout(text, 1)
            rows.addLayout(row)
        rows.addStretch(1)
        scroll.setWidget(body)
        lay.addWidget(scroll, 1)
        self._paint_icons()
        theme.on_change(self._paint_icons)

        buttons = QDialogButtonBox()
        ok = buttons.addButton("Got it", QDialogButtonBox.AcceptRole)
        ok.setDefault(True)
        buttons.accepted.connect(self.accept)
        lay.addWidget(buttons)

    def _paint_icons(self):
        for label, name in self._icons:
            try:
                label.setPixmap(pixmap(name, 22, "ACCENT"))
            except RuntimeError:  # the window has been closed
                return
