"""☰ > Password protect…: lock a PDF so it asks for a password when it opens (in any PDF program), change that
password, or take it off. It's written into the file when the PDF is saved (strong AES-256 encryption)."""
from PySide6.QtWidgets import QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QVBoxLayout

from .popups import APP_NAME


class PasswordDialog(QDialog):
    """result: the new password, "" to remove the password, or None (cancelled)."""

    def __init__(self, parent, protected):
        super().__init__(parent)
        self.setWindowTitle(APP_NAME)
        self.result_password = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 14)
        lay.setSpacing(10)
        head = QLabel("Change or remove the password" if protected else "Protect this PDF with a password")
        head.setStyleSheet("font-size: 15px; font-weight: 600;")
        lay.addWidget(head)
        info = QLabel(("This PDF already asks for a password when it opens. " if protected else "") +
                      "Anyone opening the PDF will need the password, in any PDF program. Keep it somewhere safe: "
                      "if it's forgotten, the PDF can't be opened.")
        info.setWordWrap(True)
        info.setObjectName("subtle")
        lay.addWidget(info)
        form = QFormLayout()
        self.first = QLineEdit()
        self.again = QLineEdit()
        for box in (self.first, self.again):
            box.setEchoMode(QLineEdit.Password)
            box.setMinimumWidth(240)
            box.textChanged.connect(self._check)
        form.addRow("New password:", self.first)
        form.addRow("Type it again:", self.again)
        lay.addLayout(form)
        show = QCheckBox("Show password")
        show.toggled.connect(lambda on: [b.setEchoMode(QLineEdit.Normal if on else QLineEdit.Password)
                                         for b in (self.first, self.again)])
        lay.addWidget(show)
        self.problem = QLabel("")
        self.problem.setObjectName("subtle")
        lay.addWidget(self.problem)
        buttons = QDialogButtonBox()
        self.ok = buttons.addButton("Change password" if protected else "Protect", QDialogButtonBox.AcceptRole)
        self.ok.setDefault(True)
        if protected:
            remove = buttons.addButton("Remove password", QDialogButtonBox.DestructiveRole)
            remove.clicked.connect(self._remove)
        buttons.addButton("Cancel", QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self._check()

    def _check(self):
        a, b = self.first.text(), self.again.text()
        self.ok.setEnabled(bool(a) and a == b)
        self.problem.setText("The two passwords don't match yet." if a and b and a != b else "")

    def _accept(self):
        if self.first.text() and self.first.text() == self.again.text():
            self.result_password = self.first.text()
            self.accept()

    def _remove(self):
        self.result_password = ""
        self.accept()
