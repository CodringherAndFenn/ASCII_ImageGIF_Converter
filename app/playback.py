from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QPushButton, QSlider, QCheckBox,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal


class PlaybackBar(QWidget):
    frame_changed = pyqtSignal(int)
    diff_toggled = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._durations: list[int] = []
        self._count = 0

        # Single-shot timer chained per frame so per-frame durations are exact
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._advance)

        self._build_ui()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_animation(self, frame_count: int, durations: list[int]) -> None:
        self.pause()
        self._count = frame_count
        self._durations = durations
        self.frame_slider.blockSignals(True)
        self.frame_slider.setRange(0, max(0, frame_count - 1))
        self.frame_slider.setValue(0)
        self.frame_slider.blockSignals(False)
        self._update_label()

    def clear(self) -> None:
        self.pause()
        self._count = 0
        self._durations = []
        self.frame_slider.blockSignals(True)
        self.frame_slider.setRange(0, 0)
        self.frame_slider.setValue(0)
        self.frame_slider.blockSignals(False)
        self._update_label()

    def set_enabled_controls(self, enabled: bool) -> None:
        for w in (self.play_btn, self.prev_btn, self.next_btn,
                  self.frame_slider, self.diff_check):
            w.setEnabled(enabled)

    def current_frame(self) -> int:
        return self.frame_slider.value()

    def set_current(self, index: int) -> None:
        self.frame_slider.blockSignals(True)
        self.frame_slider.setValue(index)
        self.frame_slider.blockSignals(False)
        self._update_label()

    def play(self) -> None:
        if self._count <= 1:
            return
        self.play_btn.setChecked(True)
        self.play_btn.setText('⏸')
        self._timer.start(self._durations[self.current_frame()])

    def pause(self) -> None:
        self._timer.stop()
        self.play_btn.setChecked(False)
        self.play_btn.setText('▶')

    def is_playing(self) -> bool:
        return self.play_btn.isChecked()

    def toggle_play(self) -> None:
        if self.is_playing():
            self.pause()
        else:
            self.play()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(6)

        self.prev_btn = QPushButton('⏮')
        self.play_btn = QPushButton('▶')
        self.play_btn.setCheckable(True)
        self.next_btn = QPushButton('⏭')
        for btn in (self.prev_btn, self.play_btn, self.next_btn):
            btn.setFixedWidth(34)

        self.frame_slider = QSlider(Qt.Orientation.Horizontal)
        self.frame_slider.setRange(0, 0)

        self.frame_label = QLabel('0 / 0')
        self.frame_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        self.diff_check = QCheckBox('Diff')

        layout.addWidget(self.prev_btn)
        layout.addWidget(self.play_btn)
        layout.addWidget(self.next_btn)
        layout.addWidget(self.frame_slider, 1)
        layout.addWidget(self.frame_label)
        layout.addWidget(self.diff_check)

        self.play_btn.clicked.connect(self._on_play_clicked)
        self.prev_btn.clicked.connect(lambda: self._step(-1))
        self.next_btn.clicked.connect(lambda: self._step(1))
        self.frame_slider.sliderPressed.connect(self.pause)
        self.frame_slider.valueChanged.connect(self._on_slider_changed)
        self.diff_check.toggled.connect(self.diff_toggled)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _advance(self) -> None:
        if self._count == 0:
            return
        nxt = (self.current_frame() + 1) % self._count
        self.set_current(nxt)
        self.frame_changed.emit(nxt)
        self._timer.start(self._durations[nxt])

    def _on_play_clicked(self, checked: bool) -> None:
        if checked:
            self.play()
        else:
            self.pause()

    def _step(self, delta: int) -> None:
        if self._count == 0:
            return
        self.pause()
        nxt = (self.current_frame() + delta) % self._count
        self.set_current(nxt)
        self.frame_changed.emit(nxt)

    def _on_slider_changed(self, value: int) -> None:
        self._update_label()
        self.frame_changed.emit(value)

    def _update_label(self) -> None:
        if self._count == 0:
            self.frame_label.setText('0 / 0')
        else:
            self.frame_label.setText(f'{self.current_frame() + 1} / {self._count}')
