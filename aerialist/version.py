"""Which build this is. The GitHub build writes _build.py next to this file; a copy run from source has none."""
SOURCE_URL = "https://github.com/Good-Donkey/benelli-aerialist"
UPDATES_URL = SOURCE_URL + "/releases/tag/latest"

try:
    from ._build import VERSION, COMMIT, DATE
except ImportError:
    VERSION, COMMIT, DATE = "dev", "", ""


def describe():
    if VERSION == "dev":
        return "Development copy (run from source)"
    return f"Version {VERSION}" + (f" · built {DATE}" if DATE else "")
