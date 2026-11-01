"""Small popups: questions whose buttons say what they do ("Undo changes", "Keep editing") instead of Yes / No,
and the one that explains why a file wouldn't open."""
import os

from PySide6.QtWidgets import QMessageBox

APP_NAME = "Benelli Aerialist"  # display name; files and settings use the short "Aerialist"


def choose(parent, text, buttons, icon=QMessageBox.Question, info=""):
    """Show text with one button per label, the first one the default and the last one what Esc does.
    Returns the index of the button clicked."""
    box = QMessageBox(parent)
    box.setWindowTitle(APP_NAME)
    box.setIcon(icon)
    box.setText(text)
    if info:
        box.setInformativeText(info)
    made = [box.addButton(label, QMessageBox.AcceptRole if i == 0 else
                          QMessageBox.RejectRole if i == len(buttons) - 1 else QMessageBox.DestructiveRole)
            for i, label in enumerate(buttons)]
    box.setDefaultButton(made[0])
    box.setEscapeButton(made[-1])
    box.exec()
    clicked = box.clickedButton()
    return made.index(clicked) if clicked in made else len(made) - 1


def ask(parent, text, yes, no="Cancel", icon=QMessageBox.Question, info=""):
    """True if the user clicks yes."""
    return choose(parent, text, [yes, no], icon, info) == 0


def cant_open(parent, path, error):
    """A file wouldn't open: say which, why, and what to try, with the technical message under Show Details."""
    from .filecheck import explain, details
    what, advice = explain(path, error)
    box = QMessageBox(parent)
    box.setWindowTitle(APP_NAME)
    box.setIcon(QMessageBox.Warning)
    box.setStyleSheet("QLabel#qt_msgbox_label, QLabel#qt_msgbox_informativelabel { min-width: 420px; }")
    box.setText(f"Couldn't open “{os.path.basename(path)}”.\n\n{what}")
    box.setInformativeText(advice + f"\n\nFolder: {os.path.dirname(path)}")
    if details(error):
        box.setDetailedText(details(error))
    box.exec()
