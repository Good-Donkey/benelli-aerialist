"""PDF pages to images, and images to PDF pages."""
import os

import pymupdf
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QRadioButton, QButtonGroup, QComboBox, QLabel,
    QLineEdit, QPushButton, QFileDialog, QDialogButtonBox, QGroupBox, QFormLayout,
)

LETTER = (612, 792)  # points; images are sized to fit a Letter page, keeping their shape
QUALITY = [("Screen (96 dpi)", 96), ("Standard (150 dpi)", 150), ("High (300 dpi)", 300), ("Print (600 dpi)", 600)]


def image_to_pdf(path):
    """One image -> a one-page PDF (in memory) sized to fit Letter, same aspect ratio."""
    img = pymupdf.open(path)
    rect = img[0].rect  # image size in pixels (treated as points)
    img.close()
    scale = min(LETTER[0] / rect.width, LETTER[1] / rect.height) if rect.width < rect.height else \
        min(LETTER[1] / rect.width, LETTER[0] / rect.height)  # landscape images get a landscape page
    doc = pymupdf.open()
    page = doc.new_page(width=rect.width * scale, height=rect.height * scale)
    page.insert_image(page.rect, filename=path)
    return doc


def export_pages(doc, pages, fmt, dpi, folder, base, jpg_quality=90):
    """Save each page as base-p<N>.<fmt> in folder. Returns the written paths."""
    os.makedirs(folder, exist_ok=True)
    width = len(str(len(doc)))
    files = []
    for i in pages:
        pix = doc[i].get_pixmap(dpi=dpi, alpha=False)
        path = os.path.join(folder, f"{base}-p{str(i + 1).zfill(width)}.{fmt}")
        if fmt == "jpg":
            pix.save(path, jpg_quality=jpg_quality)
        else:
            pix.save(path)
        files.append(path)
    return files


class ExportDialog(QDialog):
    def __init__(self, parent, page_count, current, selected, folder):
        super().__init__(parent)
        self.setWindowTitle("Save pages as images")
        self.page_count, self.current, self.selected = page_count, current, selected
        lay = QVBoxLayout(self)

        box = QGroupBox("Pages")
        bl = QVBoxLayout(box)
        self.group = QButtonGroup(self)
        self.r_all = QRadioButton(f"All pages ({page_count})")
        self.r_cur = QRadioButton(f"Current page ({current + 1})")
        self.r_sel = QRadioButton(f"Selected pages ({len(selected)})")
        self.r_range = QRadioButton("Pages:")
        self.range_edit = QLineEdit()
        self.range_edit.setPlaceholderText("e.g. 1-3, 7")
        self.range_edit.textEdited.connect(lambda: self.r_range.setChecked(True))
        for r in (self.r_all, self.r_cur, self.r_sel, self.r_range):
            self.group.addButton(r)
        bl.addWidget(self.r_all)
        bl.addWidget(self.r_cur)
        bl.addWidget(self.r_sel)
        row = QHBoxLayout()
        row.addWidget(self.r_range)
        row.addWidget(self.range_edit)
        bl.addLayout(row)
        self.r_sel.setEnabled(len(selected) > 1)
        (self.r_sel if len(selected) > 1 else self.r_all).setChecked(True)
        lay.addWidget(box)

        form = QFormLayout()
        self.fmt = QComboBox()
        self.fmt.addItems(["PNG (sharp, larger files)", "JPG (smaller files)"])
        self.quality = QComboBox()
        for label, _ in QUALITY:
            self.quality.addItem(label)
        self.quality.setCurrentIndex(1)
        folder_row = QHBoxLayout()
        self.folder = QLineEdit(folder or os.path.expanduser("~"))
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        folder_row.addWidget(self.folder)
        folder_row.addWidget(browse)
        form.addRow("Format:", self.fmt)
        form.addRow("Quality:", self.quality)
        form.addRow("Save to folder:", folder_row)
        lay.addLayout(form)
        self.error = QLabel()
        self.error.setObjectName("error")
        lay.addWidget(self.error)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self.resize(460, self.sizeHint().height())

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Save images to", self.folder.text())
        if d:
            self.folder.setText(d)

    def _pages(self):
        if self.r_all.isChecked():
            return list(range(self.page_count))
        if self.r_cur.isChecked():
            return [self.current]
        if self.r_sel.isChecked():
            return list(self.selected)
        pages = []
        for part in self.range_edit.text().replace(" ", "").split(","):
            if not part:
                continue
            a, _, b = part.partition("-")
            a, b = int(a), int(b or a)
            if not (1 <= a <= b <= self.page_count):
                raise ValueError(part)
            pages.extend(range(a - 1, b))
        if not pages:
            raise ValueError("empty")
        return sorted(set(pages))

    def _accept(self):
        try:
            self._result = (self._pages(), "jpg" if self.fmt.currentIndex() else "png",
                            QUALITY[self.quality.currentIndex()][1], self.folder.text().strip())
        except ValueError:
            self.error.setText(f"Enter pages between 1 and {self.page_count}, like 1-3, 7")
            return
        if not self._result[3]:
            self.error.setText("Choose a folder to save the images in.")
            return
        self.accept()

    def result_values(self):
        return self._result
