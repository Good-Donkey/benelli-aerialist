"""Other files to PDF (Word, Excel, PowerPoint, text) and PDF to Word.

Office files are turned into PDFs by Microsoft Office itself (or the free LibreOffice) on this PC, so they look
exactly as they do there. PDF to Word uses pdf2docx, which rebuilds paragraphs, tables and pictures from the
page: good on simple documents, rough on complicated layouts. Both run in a separate process so the window
stays responsive (and can be cancelled)."""
import multiprocessing
import os
import shutil
import subprocess
import sys
import tempfile

import pymupdf
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QLabel, QMessageBox, QProgressDialog, QPushButton, QVBoxLayout,
)

from .popups import APP_NAME

WORD = (".doc", ".docx", ".docm", ".dot", ".dotx", ".rtf", ".odt", ".wpd")
EXCEL = (".xls", ".xlsx", ".xlsm", ".xlsb", ".csv", ".ods")
POWERPOINT = (".ppt", ".pptx", ".pptm", ".pps", ".ppsx", ".odp")
TEXT = (".txt", ".text", ".log", ".md")
OFFICE = WORD + EXCEL + POWERPOINT
CONVERTIBLE = OFFICE + TEXT

# A note shown (until "Don't show this again") when a kind of conversion has a catch.
NOTES = {
    "office": ("Word, Excel and PowerPoint files are converted by Microsoft Office on this PC (or LibreOffice if "
               "Office isn't installed), so it needs one of them. The PDF looks just like the file does there."),
    "excel": ("Spreadsheets are split into pages the way Excel prints them: what File > Print shows in Excel is "
              "what you'll get. Set a print area or \"Fit sheet on one page\" in Excel first if pages split badly."),
    "text": "Text files come out as plain text in a standard font: any formatting a text file can't hold is lost.",
    "word": ("Works best on simple documents. Tables, columns, text boxes and unusual fonts may need tidying up in "
             "Word afterwards, and scanned pages come out as pictures rather than text you can edit."),
}

_PS = r"""param([string]$kind, [string]$src, [string]$dst)
$ErrorActionPreference = 'Stop'
try {
  if ($kind -eq 'word') {
    $app = New-Object -ComObject Word.Application
    $app.Visible = $false; $app.DisplayAlerts = 0
    try { $app.AutomationSecurity = 3 } catch {}  # never stop to ask about macros
    # Word lays pages out for a printer and stalls when the usual one isn't connected (e.g. away from the
    # office), so it uses Windows' own "Microsoft Print to PDF" meanwhile, then switches back.
    $printer = $null
    try { $printer = $app.ActivePrinter } catch {}
    try { $app.ActivePrinter = 'Microsoft Print to PDF' } catch { $printer = $null }  # (not there: carry on)
    $d = $null
    try {
      $d = $app.Documents.Open($src, $false, $true, $false)
      # Export first; some setups refuse it ("could not be prepared"), and Save as PDF still works there.
      try { $d.ExportAsFixedFormat($dst, 17) } catch { $d.SaveAs2($dst, 17) }
    } finally {
      if ($d) { $d.Close(0) }
      if ($printer) { try { $app.ActivePrinter = $printer } catch {} }
      $app.Quit()
    }
  } elseif ($kind -eq 'excel') {
    $app = New-Object -ComObject Excel.Application
    $app.Visible = $false; $app.DisplayAlerts = $false
    try { $b = $app.Workbooks.Open($src, 0, $true); $b.ExportAsFixedFormat(0, $dst); $b.Close($false) }
    finally { $app.Quit() }
  } else {
    $app = New-Object -ComObject PowerPoint.Application
    try { $p = $app.Presentations.Open($src, -1, 0, 0); $p.SaveAs($dst, 32); $p.Close() }
    finally { $app.Quit() }
  }
} catch {
  [Console]::Error.WriteLine($_.Exception.Message)  # just the reason, not PowerShell's whole report
  exit 1
}
"""


def kind_of(path):
    ext = os.path.splitext(path)[1].lower()
    return "word" if ext in WORD else "excel" if ext in EXCEL else "powerpoint" if ext in POWERPOINT \
        else "text" if ext in TEXT else None


def _soffice():
    for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                 os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")):
        exe = os.path.join(base, "LibreOffice", "program", "soffice.exe")
        if os.path.exists(exe):
            return exe
    return None


def _office_to_pdf(src, dst, kind):
    """Runs in the helper process. Microsoft Office first, then LibreOffice."""
    if sys.platform != "win32":
        raise RuntimeError("Converting Office files works on Windows only.")
    no_window = 0x08000000
    script = os.path.join(tempfile.gettempdir(), "aerialist-office-to-pdf.ps1")
    with open(script, "w", encoding="utf-8") as f:
        f.write(_PS)
    # Office works on a plain copy in a short temp folder: no long or cloud-only paths, no "downloaded from
    # the internet" mark (which can make Office refuse), and the original can stay open in Word meanwhile.
    work = tempfile.mkdtemp(prefix="aerialist-office-")
    copy = os.path.join(work, "document" + os.path.splitext(src)[1].lower())
    out = os.path.join(work, "document.pdf")
    shutil.copyfile(src, copy)
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
                            script, "-kind", kind, "-src", copy, "-dst", out],
                           capture_output=True, text=True, timeout=300, creationflags=no_window)
        office_error = " ".join((r.stderr or r.stdout).split())
        if r.returncode == 0 and os.path.exists(out):
            shutil.move(out, dst)
            return
    except subprocess.TimeoutExpired:
        office_error = ("Office took more than 5 minutes and was stopped waiting. It may be stuck on a message only "
                        "it can show (try opening the file in Office once), or on an unreachable default printer.")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    soffice = _soffice()
    if soffice:
        out = os.path.dirname(dst)
        subprocess.run([soffice, "--headless", "--convert-to", "pdf", "--outdir", out, src],
                       capture_output=True, timeout=600, creationflags=no_window)
        made = os.path.join(out, os.path.splitext(os.path.basename(src))[0] + ".pdf")
        if os.path.exists(made):
            os.replace(made, dst)
            return
    if "80040154" in office_error or "COM class factory" in office_error:
        raise RuntimeError("Microsoft Office (or the free LibreOffice) needs to be installed to convert this file.")
    raise RuntimeError(office_error[:300] or "Office couldn't convert the file.")


def _text_to_pdf(src, dst):
    with open(src, "rb") as f:
        raw = f.read()
    for enc in ("utf-8-sig", "utf-16", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    out = pymupdf.open()
    width, height, margin, size = 612, 792, 54, 10.5
    font = pymupdf.Font("cour")
    rect = pymupdf.Rect(margin, margin, width - margin, height - margin)
    lines = text.replace("\r\n", "\n").replace("\r", "\n").expandtabs(4).split("\n")
    # Wrap long lines to the page width, then fill pages.
    per_line = max(10, int(rect.width / font.text_length("M", size)))
    wrapped = []
    for line in lines:
        while len(line) > per_line:
            cut = line.rfind(" ", 0, per_line)
            cut = cut if cut > per_line // 2 else per_line
            wrapped.append(line[:cut])
            line = line[cut:].lstrip(" ")
        wrapped.append(line)
    per_page = int(rect.height / (size * 1.25))
    for start in range(0, max(1, len(wrapped)), per_page):
        page = out.new_page(width=width, height=height)
        tw = pymupdf.TextWriter(page.rect)
        y = margin + size
        for line in wrapped[start:start + per_page]:
            if line:
                tw.append((margin, y), line, font=font, fontsize=size)
            y += size * 1.25
        tw.write_text(page)
    out.save(dst, garbage=3, deflate=True)


def _pdf_to_word(src, dst, password):
    from pdf2docx import Converter
    cv = Converter(src, password=password)
    try:
        cv.convert(dst)
    finally:
        cv.close()


def _job(what, src, dst, password, conn):
    try:
        if what == "word_out":
            _pdf_to_word(src, dst, password)
        elif kind_of(src) == "text":
            _text_to_pdf(src, dst)
        else:
            _office_to_pdf(src, dst, kind_of(src))
        conn.send(None)
    except Exception as e:
        conn.send(str(e) or e.__class__.__name__)


def run(parent, what, src, dst, label, password=None):
    """Convert in a helper process with a busy box (Cancel stops it). Returns None when done, else the error text
    ("" if cancelled)."""
    ctx = multiprocessing.get_context("spawn")
    here, there = ctx.Pipe(duplex=False)
    proc = ctx.Process(target=_job, args=(what, src, dst, password, there), daemon=True)
    proc.start()
    box = QProgressDialog(label, "Cancel", 0, 0, parent)
    box.setWindowTitle("Convert")
    box.setWindowModality(Qt.WindowModal)
    box.setMinimumDuration(300)
    result = {}

    def poll():
        if here.poll():
            result["error"] = here.recv()
            box.reset()
        elif not proc.is_alive():
            result["error"] = "The conversion stopped unexpectedly."
            box.reset()
    timer = QTimer(box, interval=150)
    timer.timeout.connect(poll)
    timer.start()
    box.exec()
    timer.stop()
    if "error" not in result:  # cancelled
        proc.terminate()
        result["error"] = ""
    proc.join(2)
    return result["error"]


def show_note(parent, settings, key):
    """The note about a conversion's catch, until "Don't show this again". False if they cancelled."""
    if settings.value(f"convert_notes/{key}", False, type=bool) or "--selftest" in sys.argv:
        return True
    dlg = QDialog(parent)
    dlg.setWindowTitle("Before converting")
    lay = QVBoxLayout(dlg)
    text = QLabel(NOTES[key])
    text.setWordWrap(True)
    text.setMinimumWidth(380)
    lay.addWidget(text)
    again = QCheckBox("Don't show this again")
    lay.addWidget(again)
    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    buttons.button(QDialogButtonBox.Ok).setText("Convert")
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)
    lay.addWidget(buttons)
    if not dlg.exec():
        return False
    if again.isChecked():
        settings.setValue(f"convert_notes/{key}", True)
    return True


def to_pdfs(parent, settings, paths, workdir):
    """Turn the Office and text files among paths into PDFs; other paths pass through. Returns the new list
    (files that couldn't be converted are left out, with a message)."""
    kinds = {kind_of(p) for p in paths} - {None}
    if not kinds:
        return paths
    if kinds & {"word", "excel", "powerpoint"} and not show_note(parent, settings, "office"):
        return [p for p in paths if kind_of(p) is None]
    if "excel" in kinds and not show_note(parent, settings, "excel"):
        return [p for p in paths if kind_of(p) is None]
    if "text" in kinds and not show_note(parent, settings, "text"):
        return [p for p in paths if kind_of(p) is None]
    out, failed = [], []
    for n, p in enumerate(paths):
        if kind_of(p) is None:
            out.append(p)
            continue
        dst = os.path.join(workdir, f"converted{n}-{os.path.splitext(os.path.basename(p))[0]}.pdf")
        error = run(parent, "pdf", os.path.abspath(p), dst, f"Converting {os.path.basename(p)} to PDF…")
        if error is None and os.path.exists(dst):
            out.append(dst)
        elif error == "":  # cancelled: stop here
            return out
        else:
            failed.append(f"{os.path.basename(p)}: {error}")
    if failed:
        QMessageBox.warning(parent, APP_NAME, "Some files couldn't be converted:\n\n" + "\n".join(failed))
    return out


class PdfChoice(QDialog):
    """A PDF picked in Convert: make it a Word document, or images."""

    def __init__(self, parent, name):
        super().__init__(parent)
        self.setWindowTitle("Convert")
        self.choice = None
        lay = QVBoxLayout(self)
        q = QLabel(f"Convert <b>{name}</b> to:")
        lay.addWidget(q)
        for key, label, note in (("word", "Word document (.docx)", NOTES["word"]),
                                 ("images", "Images (PNG or JPG), one per page", "")):
            b = QPushButton(label)
            b.setMinimumHeight(34)
            b.clicked.connect(lambda _=False, k=key: self._pick(k))
            lay.addWidget(b)
            if note:
                n = QLabel(note)
                n.setWordWrap(True)
                n.setObjectName("choiceNote")
                lay.addWidget(n)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self.setMinimumWidth(420)

    def _pick(self, key):
        self.choice = key
        self.accept()
