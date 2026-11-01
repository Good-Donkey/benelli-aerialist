"""Offering to become the default app for PDFs. Windows doesn't let programs make themselves
the default; the most an app may do is ask and open the Default apps page in Settings at its
own entry, where one click (Set default) does it."""
import os
import sys

from PySide6.QtWidgets import QMessageBox, QPushButton

PROG_ID = "BenelliAerialist.pdf"
SETTINGS_PAGE = "ms-settings:defaultapps?registeredAppUser=Benelli%20Aerialist"


def current_default():
    """The ProgID Windows uses to open .pdf files for this user, or None if unknown."""
    if sys.platform != "win32":
        return None
    import winreg
    base = r"Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.pdf"
    for sub in ("UserChoiceLatest", "UserChoice"):  # newer Windows 11 builds use UserChoiceLatest
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, base + "\\" + sub) as k:
                return winreg.QueryValueEx(k, "ProgId")[0]
        except OSError:
            continue
    return None


def default_exe():
    """The program Windows actually opens .pdf files with (asks the shell, so it is right whichever
    registry key this Windows version keeps the choice in), or None."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes
    ASSOCSTR_EXECUTABLE = 2
    size = wintypes.DWORD(1024)
    buf = ctypes.create_unicode_buffer(size.value)
    hr = ctypes.windll.shlwapi.AssocQueryStringW(0, ASSOCSTR_EXECUTABLE, ".pdf", "open", buf, ctypes.byref(size))
    return buf.value if hr == 0 and buf.value else None


def is_default():
    exe = default_exe()
    if exe and os.path.basename(exe).lower() == "benelliaerialist.exe":
        return True
    prog = current_default() or ""
    return prog.lower() in (PROG_ID.lower(), r"applications\benelliaerialist.exe")


def installed():
    """Only the installed app is registered with Windows (not the portable zip or a dev copy)."""
    return getattr(sys, "frozen", False) and os.path.exists(os.path.join(os.path.dirname(sys.executable),
                                                                         "unins000.exe"))


def open_settings():
    try:
        os.startfile(SETTINGS_PAGE)
    except OSError:
        os.startfile("ms-settings:defaultapps")


def ask(parent, settings, app_name, forced=False):
    """Ask once per launch (until "Don't ask again"); forced is the menu item, which always asks."""
    if sys.platform != "win32" or is_default():
        if forced:
            QMessageBox.information(parent, app_name, f"{app_name} is already your default app for PDFs."
                                    if sys.platform == "win32" else "This only applies on Windows.")
        return
    if not forced and (settings.value("default_app/dont_ask", False, type=bool) or not installed()):
        return
    box = QMessageBox(parent)
    box.setWindowTitle(app_name)
    box.setIcon(QMessageBox.Question)
    box.setText(f"Make {app_name} your default app for PDFs?")
    box.setInformativeText("Windows will open its Default apps page at Benelli Aerialist. "
                           "Click “Set default” at the top of that page.")
    yes = box.addButton("Yes, open Settings", QMessageBox.AcceptRole)
    box.addButton("Not now", QMessageBox.RejectRole)
    never = None if forced else box.addButton("Don't ask again", QMessageBox.DestructiveRole)
    box.setDefaultButton(yes)
    box.exec()
    if box.clickedButton() is yes:
        open_settings()
    elif never is not None and box.clickedButton() is never:
        settings.setValue("default_app/dont_ask", True)
