# Benelli Aerialist

A free PDF editor for Windows. Read, organize, edit, fill in and sign PDFs, with as little toolbar as possible
in the way of the page.

## What it does
- **Read:** fast scrolling and zoom, page thumbnails, find, clickable links, copy text and pictures.
- **Snip:** copy any part of a page as a sharp picture, or save it.
- **Paste a screenshot:** Ctrl+V opens a picture from the clipboard as a new PDF to blur, mark up or convert.
- **Organize & Merge:** reorder, rotate and delete pages, merge PDFs and pictures, save chosen pages as a new PDF.
- **Edit:** add text, pictures, shapes, drawings, highlighter, white-out, blur (what is under it is removed for good), stamps and links; move or resize
  what's already on the page.
- **Fill & Sign:** fill in forms, add signatures, initials, the date and text.
- **Comments:** sticky notes, highlight, underline and strike-through, with replies, saved as standard PDF comments.
- **Prepare Form:** turn any PDF into a fillable form with text boxes and tick boxes, and set the Tab order.
- **Convert:** pictures, Word, Excel, PowerPoint and text files to PDF (Office files need Microsoft Office or
  LibreOffice), and PDFs to Word or pictures. Resize photos for email.
- **Password protect** a PDF.
- **File Explorer:** right-click files to open, convert, merge or resize them.

Undo and Redo work in every tool. ☰ > What it can do gives a quick tour; Settings > Shortcuts lists the keys.

## Download
Get `BenelliAerialist-Setup.exe` from the [latest release](../../releases/tag/latest) and run it. No admin
rights needed. It adds a Start menu entry and lists the app under "Open with" for PDFs.
For a portable copy, unzip `BenelliAerialist-windows.zip` anywhere and run `BenelliAerialist.exe`.

Windows may warn that the app is from an unknown publisher, because it isn't code-signed. Choose
"More info" > "Run anyway".

## How this was made
This app was written by Claude, Anthropic's AI, working from one person's ideas, design choices and
testing. Every line of code came from Claude; the person decided what to build and checked that it worked.

## Running from source on Windows
1. Install Python 3.12 or newer from https://www.python.org/downloads/ (tick "Add python.exe to PATH").
2. Double-click `run.bat` to try it. The first run takes a minute to set up.
3. Double-click `build_exe.bat` to make a standalone app in `dist\BenelliAerialist\BenelliAerialist.exe`.

GitHub Actions builds the installer automatically on every update to `main`.

## Privacy
The app collects nothing and sends nothing. It works entirely on your PC and only goes online when you
click a link in a PDF (it asks first) or press Check for updates, which opens the download page in your browser.

## Licence
Benelli Aerialist is free software under the [GNU Affero General Public License v3.0](LICENSE)
(AGPL-3.0), with no warranty. You can use, share and change it, as long as anyone you give it to can get
the source code too. It's built on PyMuPDF, Qt for Python and other open-source parts; see
[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).

The app is provided as is, without any warranty. Keep a copy of important PDFs before changing them.
