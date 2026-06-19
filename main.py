import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QSettings

from app.window import MainWindow

_STYLESHEET = """
QWidget {
    background: #0d0d0d;
    color: #c8c8c8;
    font-family: 'JetBrains Mono', 'Fira Code', 'Courier New', monospace;
    font-size: 11px;
}

QLabel#title {
    color: #4af626;
    font-size: 17px;
    font-weight: bold;
    letter-spacing: 2px;
    padding: 6px 0;
}

QLabel#status {
    color: #484848;
    font-size: 10px;
    padding: 2px 0;
}

/* Sliders */
QSlider::groove:horizontal {
    background: #1a1a1a;
    height: 3px;
    border-radius: 2px;
}
QSlider::sub-page:horizontal {
    background: #4af626;
    height: 3px;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #4af626;
    width: 12px;
    height: 12px;
    border-radius: 6px;
    margin: -5px 0;
}
QSlider::handle:horizontal:disabled {
    background: #2a2a2a;
}
QSlider::sub-page:horizontal:disabled {
    background: #1a1a1a;
}

/* Buttons */
QPushButton {
    background: #141414;
    border: 1px solid #242424;
    padding: 5px 12px;
    border-radius: 4px;
    color: #c8c8c8;
}
QPushButton:hover {
    border-color: #4af626;
    color: #4af626;
}
QPushButton:checked {
    background: #0e1e0e;
    border-color: #4af626;
    color: #4af626;
}
QPushButton:pressed {
    background: #080808;
}
QPushButton:disabled {
    color: #383838;
    border-color: #1a1a1a;
}

/* ComboBox */
QComboBox {
    background: #141414;
    border: 1px solid #242424;
    padding: 4px 8px;
    border-radius: 4px;
    color: #c8c8c8;
}
QComboBox:hover {
    border-color: #4af626;
}
QComboBox::drop-down {
    border: none;
    width: 18px;
}
QComboBox::down-arrow {
    width: 8px;
    height: 8px;
    border-left: 2px solid #555;
    border-bottom: 2px solid #555;
    margin-right: 4px;
    top: -2px;
}
QComboBox QAbstractItemView {
    background: #141414;
    border: 1px solid #242424;
    selection-background-color: #0e1e0e;
    selection-color: #4af626;
    color: #c8c8c8;
    outline: none;
}

/* CheckBox */
QCheckBox {
    color: #c8c8c8;
    spacing: 7px;
}
QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border-radius: 3px;
    border: 1px solid #2a2a2a;
    background: #141414;
}
QCheckBox::indicator:checked {
    background: #4af626;
    border-color: #4af626;
    image: none;
}
QCheckBox::indicator:hover {
    border-color: #4af626;
}

/* LineEdit */
QLineEdit {
    background: #141414;
    border: 1px solid #242424;
    border-radius: 4px;
    padding: 4px 8px;
    color: #c8c8c8;
}
QLineEdit:focus {
    border-color: #4af626;
}

/* Scroll area / bars */
QScrollArea {
    border: none;
}
QScrollBar:vertical {
    background: #0d0d0d;
    width: 8px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #242424;
    border-radius: 4px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover {
    background: #4af626;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal {
    background: #0d0d0d;
    height: 8px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background: #242424;
    border-radius: 4px;
    min-width: 24px;
}
QScrollBar::handle:horizontal:hover {
    background: #4af626;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

/* Splitter */
QSplitter::handle {
    background: #141414;
}
QSplitter::handle:horizontal {
    width: 2px;
}

/* Menu / dialogs */
QMessageBox {
    background: #141414;
}
QFileDialog {
    background: #141414;
}
"""


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName('ASCIIConverter')
    app.setOrganizationName('ASCIIConverter')
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    app.setStyleSheet(_STYLESHEET)

    window = MainWindow()
    window.setMinimumSize(760, 500)
    if not window.isVisible():
        window.resize(1200, 800)
    window.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
