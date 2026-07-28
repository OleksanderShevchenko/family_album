from PyQt6 import QtCore
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout


class AboutDialog(QDialog):
    """
    Formatted modal dialog displaying application details, features, and author contacts.
    Supports both Light and Dark OS desktop themes using adaptive semi-transparent styles.
    """

    def __init__(self, parent=None, app_name: str = "Family Album", version: str = "0.1"):
        super().__init__(parent)
        self.setWindowTitle(f"About {app_name}")
        self.setFixedSize(510, 420)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(14)

        # Header Title with Emoji
        lbl_title = QLabel(f"<h2 style='margin: 0;'>📸 {app_name}</h2>", self)
        lbl_title.setTextFormat(QtCore.Qt.TextFormat.RichText)
        lbl_title.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_title)

        lbl_version = QLabel(f"<b>✨ Version:</b> {version}", self)
        lbl_version.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_version)

        # Main Description & Details Card with Theme-Adaptive Semi-Transparent Background
        html_info = """
        <div style='background-color: rgba(128, 128, 128, 0.12); border: 1px solid rgba(128, 128, 128, 0.3); border-radius: 8px; padding: 14px; font-size: 13px; line-height: 1.4;'>
            <p style='margin-top: 0;'><b>📸 Family Album</b> — a versatile desktop application for media archives and files:</p>
            <ul style='margin-top: 4px; margin-bottom: 8px; padding-left: 20px;'>
                <li><b>💾 Duplicate Search for Any Files</b> — with state pause, save, and resume functionality at any time.</li>
                <li><b>🖼️ 🎥 Visual Comparison Control</b> — convenient preview for photos & videos <i>(target types, but not limited to them)</i>.</li>
                <li><b>📁 Catalog Organization</b> — organizing photos & videos into structured folders by date <i>(coming soon 🚀)</i>.</li>
            </ul>
            <hr style='border: none; border-top: 1px solid rgba(128, 128, 128, 0.25); margin: 10px 0;'>
            <p style='margin: 4px 0;'><b>👨‍💻 Author:</b> Oleksandr Shevchenko</p>
            <p style='margin: 4px 0;'><b>✉️ Contact:</b> <a href='mailto:oleksander.shevchenko777@gmail.com' style='color: #3498DB;'>oleksander.shevchenko777@gmail.com</a></p>
            <p style='margin: 4px 0;'><b>📜 License:</b> MIT License</p>
            <p style='margin: 4px 0 0 0;'><b>© Copyright:</b> © 2026 Oleksandr Shevchenko</p>
        </div>
        """
        lbl_info = QLabel(html_info, self)
        lbl_info.setTextFormat(QtCore.Qt.TextFormat.RichText)
        lbl_info.setOpenExternalLinks(True)
        lbl_info.setWordWrap(True)
        layout.addWidget(lbl_info)

        # OK Button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_ok = QPushButton("👌 OK", self)
        btn_ok.setFixedWidth(110)
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self.accept)
        btn_layout.addWidget(btn_ok)
        btn_layout.addStretch()

        layout.addLayout(btn_layout)
