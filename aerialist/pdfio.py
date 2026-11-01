"""The whole PDF as bytes (for undo snapshots and safe saving), written the fast way."""
import os
import tempfile


def to_bytes(doc):
    """Same as doc.tobytes(), about six times faster on big files: PyMuPDF writes to memory through Python
    one small piece at a time, but to a file in one go, so go through a temporary file."""
    fd, path = tempfile.mkstemp(suffix=".pdf", prefix="aerialist-")
    os.close(fd)
    try:
        doc.save(path)
        with open(path, "rb") as f:
            return f.read()
    except Exception:
        return doc.tobytes()  # e.g. no room in the temp folder: the slow way still works
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
