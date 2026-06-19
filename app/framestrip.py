import numpy as np
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QScrollArea, QLabel
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap


class _Thumb(QLabel):
    clicked = pyqtSignal(int)

    _STYLE_IDLE = 'QLabel { border: 2px solid #1e1e1e; }'
    _STYLE_CURRENT = 'QLabel { border: 2px solid #4af626; }'

    def __init__(self, index: int, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self._index = index
        self.setPixmap(pixmap)
        self.setStyleSheet(self._STYLE_IDLE)
        self.setToolTip(f'Frame {index + 1}')

    def set_current(self, current: bool) -> None:
        self.setStyleSheet(self._STYLE_CURRENT if current else self._STYLE_IDLE)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._index)
        super().mousePressEvent(event)


class FrameStrip(QWidget):
    frame_clicked = pyqtSignal(int)

    THUMB_HEIGHT = 64

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thumbs: list[_Thumb] = []
        self._current = -1

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setFixedHeight(self.THUMB_HEIGHT + 24)

        self._inner = QWidget()
        self._inner_layout = QHBoxLayout(self._inner)
        self._inner_layout.setContentsMargins(4, 4, 4, 4)
        self._inner_layout.setSpacing(4)
        self._inner_layout.addStretch()

        self.scroll.setWidget(self._inner)
        layout.addWidget(self.scroll)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_frames(self, frames: list) -> None:
        self.clear()
        for i, frame in enumerate(frames):
            thumb = _Thumb(i, self._make_pixmap(frame))
            thumb.clicked.connect(self.frame_clicked)
            self._inner_layout.insertWidget(self._inner_layout.count() - 1, thumb)
            self._thumbs.append(thumb)
        if self._thumbs:
            self.set_current(0)

    def set_current(self, index: int) -> None:
        if not (0 <= index < len(self._thumbs)) or index == self._current:
            return
        if 0 <= self._current < len(self._thumbs):
            self._thumbs[self._current].set_current(False)
        self._current = index
        self._thumbs[index].set_current(True)
        self.scroll.ensureWidgetVisible(self._thumbs[index])

    def clear(self) -> None:
        for thumb in self._thumbs:
            self._inner_layout.removeWidget(thumb)
            thumb.deleteLater()
        self._thumbs = []
        self._current = -1

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @classmethod
    def _make_pixmap(cls, frame: np.ndarray) -> QPixmap:
        arr = np.ascontiguousarray(frame)
        h, w = arr.shape[:2]
        # .copy() because QImage does not own the numpy buffer
        qimg = QImage(arr.data, w, h, w * 4, QImage.Format.Format_RGBA8888).copy()
        return QPixmap.fromImage(qimg).scaledToHeight(
            cls.THUMB_HEIGHT, Qt.TransformationMode.SmoothTransformation
        )
