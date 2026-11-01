"""When a file won't open, find out why in words a person can act on: cloud file not downloaded, file gone,
locked by another program, empty, damaged or not a PDF."""
import os
import sys

RECALL_ON_DATA_ACCESS = 0x400000  # a cloud placeholder: the contents are fetched only when read
OFFLINE = 0x1000


def cloud_place(path):
    """Which cloud or network storage the file lives on, as a name to show, or None for a local disk."""
    parts = [p.lower() for p in os.path.normpath(path).split(os.sep)]
    if "my drive" in parts or "shared drives" in parts or "other computers" in parts:
        return "Google Drive"
    if any(p.startswith("onedrive") for p in parts):
        return "OneDrive"
    if any(p.startswith("dropbox") for p in parts):
        return "Dropbox"
    if any(p.startswith("icloud") for p in parts):
        return "iCloud Drive"
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        drive = os.path.splitdrive(os.path.abspath(path))[0]
        if drive.startswith("\\\\"):
            return "a network drive"
        root = drive + "\\"
        label = ctypes.create_unicode_buffer(261)
        fs = ctypes.create_unicode_buffer(261)
        if ctypes.windll.kernel32.GetVolumeInformationW(root, label, 261, None, None, None, fs, 261):
            text = (label.value + " " + fs.value).lower()
            if "google" in text:
                return "Google Drive"
        if ctypes.windll.kernel32.GetDriveTypeW(root) == 4:  # DRIVE_REMOTE
            return "a network drive"
    except Exception:
        pass
    return None


def online_only(path):
    """True for a cloud file that isn't on this PC yet: reading it means downloading it first."""
    return _placeholder(path)


def _placeholder(path):
    try:
        attrs = getattr(os.stat(path), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attrs & (RECALL_ON_DATA_ACCESS | OFFLINE))


def explain(path, error=None):
    """Why path couldn't be opened, as (what went wrong, what to try)."""
    cloud = cloud_place(path) or ("cloud storage" if _placeholder(path) else None)
    online = "Check your internet connection and try again." if cloud else ""
    try:
        with open(path, "rb") as f:
            head = f.read(4096)
    except FileNotFoundError:
        return ("The file isn't there any more.",
                "It may have been moved, renamed or deleted." +
                (f" It appears to be on {cloud}, so also check your internet connection." if cloud else ""))
    except PermissionError:
        return ("Windows didn't allow the file to be read.",
                "It may be open in a program that locks it, or your account may not have access to it. "
                "Close other programs using it and try again." +
                (f" It also appears to be on {cloud}, so check your internet connection." if cloud else ""))
    except OSError:
        if cloud:
            return (f"It appears to be on {cloud} and isn't available right now.", online)
        return ("Windows couldn't read the file.",
                "The drive it's on may be disconnected or not responding. Check it's plugged in, then try again.")
    if not head:
        return ("The file is empty (0 bytes).",
                (f"It may not have finished downloading from {cloud} yet. Wait a moment and try again."
                 if cloud else "It was probably cut short when it was saved or downloaded. Ask for a new copy."))
    if path.lower().endswith(".pdf") and b"%PDF" not in head:
        return ("This isn't really a PDF.",
                "It may be a different kind of file renamed to .pdf, or a download that didn't finish. "
                "Ask for a new copy.")
    return ("The file looks damaged.",
            "Try opening it in another PDF program. If it fails there too, ask whoever sent it for a new copy.")


def details(error):
    """The technical message, for the Show Details part of the popup."""
    return str(error).replace("\\\\", "\\").strip() if error else ""
