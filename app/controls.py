from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QComboBox, QCheckBox, QLineEdit, QButtonGroup,
    QFrame, QSizePolicy, QSpinBox,
)
from PyQt6.QtWidgets import QColorDialog
from PyQt6.QtCore import Qt, pyqtSignal, QSettings
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QColor

from . import palettes as pal


# ---------------------------------------------------------------------------
# Drop Zone
# ---------------------------------------------------------------------------

class DropZone(QLabel):
    file_dropped = pyqtSignal(str)

    _STYLE_IDLE = (
        'QLabel { border: 2px dashed #2a2a2a; border-radius: 6px;'
        ' color: #444; font-size: 11px; }'
        'QLabel:hover { border-color: #4af626; color: #4af626; }'
    )
    _STYLE_HOVER = (
        'QLabel { border: 2px dashed #4af626; border-radius: 6px;'
        ' color: #4af626; font-size: 11px; }'
    )

    def __init__(self, parent=None):
        super().__init__('Drop image here', parent)
        self.setAcceptDrops(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumHeight(72)
        self.setStyleSheet(self._STYLE_IDLE)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setStyleSheet(self._STYLE_HOVER)

    def dragLeaveEvent(self, event) -> None:
        self.setStyleSheet(self._STYLE_IDLE)

    def dropEvent(self, event: QDropEvent) -> None:
        self.setStyleSheet(self._STYLE_IDLE)
        urls = event.mimeData().urls()
        if urls:
            self.file_dropped.emit(urls[0].toLocalFile())


# ---------------------------------------------------------------------------
# Control Panel
# ---------------------------------------------------------------------------

class ControlPanel(QWidget):
    settings_changed = pyqtSignal()
    open_file_requested = pyqtSignal()
    demo_requested = pyqtSignal(str)
    file_dropped = pyqtSignal(str)
    copy_text = pyqtSignal()
    save_txt = pyqtSignal()
    save_html = pyqtSignal()
    save_png = pyqtSignal()
    export_animation = pyqtSignal(str)  # 'frames_txt'|'frames_md'|'anim_txt'|'anim_html'|'anim_gif'|'spritesheet'
    paint_toggled = pyqtSignal(bool)
    paint_color_changed = pyqtSignal(tuple)
    clear_edits = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(288)
        self._mask_color: tuple | None = None  # None = auto from corners
        self._paint_color: tuple = (74, 246, 38)  # #4af626
        self._anim_active = False
        self._build_ui()
        self._wire_signals()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def collect_settings(self) -> dict:
        charset_name = self.charset_combo.currentText()
        if charset_name == 'Custom':
            palette = self.custom_chars.text() or '@. '
        else:
            palette = pal.get(charset_name)

        return {
            'cols': self.cols_slider.value(),
            'mode': self._current_mode(),
            'palette': palette,
            'palette_name': charset_name,
            'invert': self.invert_check.isChecked(),
            'color': self.color_check.isChecked(),
            'threshold': self.thresh_slider.value(),
            'contrast': self.contrast_slider.value() / 10.0,
            'font_size': self.font_slider.value(),
            'mask_enabled': self.mask_check.isChecked(),
            'mask_tolerance': self.mask_tol_slider.value(),
            'mask_mode': ('per_frame', 'first_frame')[self.mask_mode_combo.currentIndex()],
            'mask_color': self._mask_color,
        }

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def set_animation_mode(self, active: bool) -> None:
        self._anim_active = active
        self.anim_export_box.setVisible(active)
        self._update_mask_widgets()

    def set_frame_count(self, n: int) -> None:
        """Reset the export frame-range spinboxes for a freshly loaded
        animation: full range 1..n selected."""
        for box in (self.frame_from, self.frame_to):
            box.blockSignals(True)
            box.setRange(1, n)
        self.frame_from.setValue(1)
        self.frame_to.setValue(n)
        for box in (self.frame_from, self.frame_to):
            box.blockSignals(False)

    def export_frame_range(self) -> tuple[int, int]:
        """Selected export range as a 0-based half-open slice (start, end)."""
        return self.frame_from.value() - 1, self.frame_to.value()

    def toggle_invert(self) -> None:
        self.invert_check.setChecked(not self.invert_check.isChecked())

    def cycle_mode(self) -> None:
        order = ['luminance', 'edge', 'hybrid']
        current = self._current_mode()
        nxt = order[(order.index(current) + 1) % len(order)]
        for btn in self.mode_group.buttons():
            if btn.property('mode') == nxt:
                btn.setChecked(True)
                self._on_mode_changed()
                break

    def adjust_cols(self, delta: int) -> None:
        self.cols_slider.setValue(
            max(20, min(300, self.cols_slider.value() + delta))
        )

    def save_settings(self, s: QSettings) -> None:
        s.setValue('cols', self.cols_slider.value())
        s.setValue('mode', self._current_mode())
        s.setValue('charset', self.charset_combo.currentText())
        s.setValue('custom_chars', self.custom_chars.text())
        s.setValue('invert', self.invert_check.isChecked())
        s.setValue('color', self.color_check.isChecked())
        s.setValue('threshold', self.thresh_slider.value())
        s.setValue('contrast', self.contrast_slider.value())
        s.setValue('font_size', self.font_slider.value())
        s.setValue('mask_enabled', self.mask_check.isChecked())
        s.setValue('mask_tolerance', self.mask_tol_slider.value())
        s.setValue('mask_mode', ('per_frame', 'first_frame')[self.mask_mode_combo.currentIndex()])
        s.setValue(
            'mask_color',
            'auto' if self._mask_color is None
            else '#{:02x}{:02x}{:02x}'.format(*self._mask_color),
        )

    def restore_settings(self, s: QSettings) -> None:
        widgets = [
            self.cols_slider, self.thresh_slider, self.contrast_slider,
            self.font_slider, self.charset_combo, self.custom_chars,
            self.invert_check, self.color_check,
            self.mask_check, self.mask_tol_slider, self.mask_mode_combo,
        ]
        for w in widgets:
            w.blockSignals(True)

        if s.contains('cols'):
            self.cols_slider.setValue(int(s.value('cols', 80)))
        if s.contains('mode'):
            mode = s.value('mode', 'luminance')
            for btn in self.mode_group.buttons():
                if btn.property('mode') == mode:
                    btn.setChecked(True)
        if s.contains('charset'):
            idx = self.charset_combo.findText(s.value('charset', 'Standard'))
            if idx >= 0:
                self.charset_combo.setCurrentIndex(idx)
        if s.contains('custom_chars'):
            self.custom_chars.setText(s.value('custom_chars', ''))
        if s.contains('invert'):
            self.invert_check.setChecked(self._bool(s.value('invert', False)))
        if s.contains('color'):
            self.color_check.setChecked(self._bool(s.value('color', False)))
        if s.contains('threshold'):
            self.thresh_slider.setValue(int(s.value('threshold', 60)))
        if s.contains('contrast'):
            self.contrast_slider.setValue(int(s.value('contrast', 10)))
        if s.contains('font_size'):
            self.font_slider.setValue(int(s.value('font_size', 10)))
        if s.contains('mask_enabled'):
            self.mask_check.setChecked(self._bool(s.value('mask_enabled', False)))
        if s.contains('mask_tolerance'):
            self.mask_tol_slider.setValue(int(s.value('mask_tolerance', 40)))
        if s.contains('mask_mode'):
            self.mask_mode_combo.setCurrentIndex(
                1 if s.value('mask_mode', 'per_frame') == 'first_frame' else 0
            )
        if s.contains('mask_color'):
            stored = s.value('mask_color', 'auto')
            if isinstance(stored, str) and stored.startswith('#') and len(stored) == 7:
                self._set_mask_color(tuple(int(stored[i:i + 2], 16) for i in (1, 3, 5)))
            else:
                self._set_mask_color(None)

        for w in widgets:
            w.blockSignals(False)

        self._sync_labels()
        self._on_mode_changed_silent()
        self._update_mask_widgets()
        self._on_charset_changed(self.charset_combo.currentText())

    # ------------------------------------------------------------------
    # Build UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(7)

        # Title
        title = QLabel('ASCII CONVERTER')
        title.setObjectName('title')
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Drop zone
        self.drop_zone = DropZone()
        layout.addWidget(self.drop_zone)

        # Open + demo row
        open_row = QHBoxLayout()
        self.open_btn = QPushButton('Open image…')
        open_row.addWidget(self.open_btn)
        layout.addLayout(open_row)

        demo_row = QHBoxLayout()
        demo_lbl = QLabel('Demo:')
        demo_lbl.setFixedWidth(38)
        self.demo_combo = QComboBox()
        self.demo_combo.addItems(['Sphere', 'Wave', 'Portrait', 'Gradient'])
        self.demo_load_btn = QPushButton('Load')
        self.demo_load_btn.setFixedWidth(44)
        demo_row.addWidget(demo_lbl)
        demo_row.addWidget(self.demo_combo, 1)
        demo_row.addWidget(self.demo_load_btn)
        layout.addLayout(demo_row)

        layout.addWidget(self._sep())

        # Columns
        layout.addLayout(self._label_row('Columns', 'cols_val', '80'))
        self.cols_slider = self._slider(20, 300, 80)
        layout.addWidget(self.cols_slider)

        # Render mode
        layout.addWidget(QLabel('Render Mode'))
        mode_row = QHBoxLayout()
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        for label, mode in [('Luminance', 'luminance'), ('Edge', 'edge'), ('Hybrid', 'hybrid')]:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setProperty('mode', mode)
            self.mode_group.addButton(btn)
            mode_row.addWidget(btn)
        self.mode_group.buttons()[0].setChecked(True)
        layout.addLayout(mode_row)

        # Character set
        layout.addWidget(QLabel('Character Set'))
        self.charset_combo = QComboBox()
        self.charset_combo.addItems(['Standard', 'Extended', 'Block', 'Braille', 'Minimal', 'Custom'])
        layout.addWidget(self.charset_combo)

        self.custom_chars = QLineEdit()
        self.custom_chars.setPlaceholderText('Enter custom characters…')
        self.custom_chars.setText('@%#*+=-:. ')
        self.custom_chars.hide()
        layout.addWidget(self.custom_chars)

        # Invert + Color
        check_row = QHBoxLayout()
        self.invert_check = QCheckBox('Invert')
        self.color_check = QCheckBox('Color')
        check_row.addWidget(self.invert_check)
        check_row.addStretch()
        check_row.addWidget(self.color_check)
        layout.addLayout(check_row)

        # Edge threshold
        layout.addLayout(self._label_row('Edge Threshold', 'thresh_val', '60'))
        self.thresh_slider = self._slider(10, 200, 60)
        self.thresh_slider.setEnabled(False)
        layout.addWidget(self.thresh_slider)

        # Contrast
        layout.addLayout(self._label_row('Contrast', 'contrast_val', '1.0'))
        self.contrast_slider = self._slider(5, 20, 10)
        layout.addWidget(self.contrast_slider)

        layout.addWidget(self._sep())

        # Background mask
        self.mask_check = QCheckBox('Background Mask')
        layout.addWidget(self.mask_check)

        layout.addLayout(self._label_row('Mask Tolerance', 'mask_tol_val', '40'))
        self.mask_tol_slider = self._slider(0, 150, 40)
        layout.addWidget(self.mask_tol_slider)

        key_row = QHBoxLayout()
        key_lbl = QLabel('Key:')
        key_lbl.setFixedWidth(38)
        self.mask_color_btn = QPushButton('Auto')
        self.mask_reset_btn = QPushButton('Reset')
        self.mask_reset_btn.setFixedWidth(50)
        key_row.addWidget(key_lbl)
        key_row.addWidget(self.mask_color_btn, 1)
        key_row.addWidget(self.mask_reset_btn)
        layout.addLayout(key_row)

        # Animation mask mode (visible only for animations with mask on)
        self.mask_anim_box = QWidget()
        mask_anim_lay = QVBoxLayout(self.mask_anim_box)
        mask_anim_lay.setContentsMargins(0, 0, 0, 0)
        mask_anim_lay.setSpacing(7)
        mask_anim_lay.addWidget(QLabel('Animation mask'))
        self.mask_mode_combo = QComboBox()
        self.mask_mode_combo.addItems(['Per-frame', 'From first frame'])
        mask_anim_lay.addWidget(self.mask_mode_combo)
        self.mask_anim_box.hide()
        layout.addWidget(self.mask_anim_box)

        self._update_mask_widgets()

        layout.addWidget(self._sep())

        # Post-processing: paint cells
        layout.addWidget(QLabel('Edit (paint)'))
        paint_row = QHBoxLayout()
        self.paint_btn = QPushButton('Paint')
        self.paint_btn.setCheckable(True)
        self.paint_color_btn = QPushButton('Color')
        paint_row.addWidget(self.paint_btn)
        paint_row.addWidget(self.paint_color_btn, 1)
        layout.addLayout(paint_row)

        layout.addLayout(self._label_row('Brush Size', 'brush_val', '1'))
        self.brush_slider = self._slider(1, 15, 1)
        layout.addWidget(self.brush_slider)

        self.clear_edits_btn = QPushButton('Clear edits')
        layout.addWidget(self.clear_edits_btn)

        paint_hint = QLabel('Left-drag paints · right-drag erases')
        paint_hint.setStyleSheet('color: #555; font-size: 10px;')
        paint_hint.setWordWrap(True)
        layout.addWidget(paint_hint)

        self._set_paint_color(self._paint_color)

        # Font size
        layout.addLayout(self._label_row('Font Size', 'font_val', '10px'))
        self.font_slider = self._slider(6, 16, 10)
        layout.addWidget(self.font_slider)

        layout.addWidget(self._sep())

        # Export buttons
        exp1 = QHBoxLayout()
        self.copy_btn = QPushButton('Copy text')
        self.txt_btn = QPushButton('Save .txt')
        exp1.addWidget(self.copy_btn)
        exp1.addWidget(self.txt_btn)
        layout.addLayout(exp1)

        exp2 = QHBoxLayout()
        self.html_btn = QPushButton('Save .html')
        self.png_btn = QPushButton('Save .png')
        exp2.addWidget(self.html_btn)
        exp2.addWidget(self.png_btn)
        layout.addLayout(exp2)

        # Animation export (visible only when an animation is loaded)
        self.anim_export_box = QWidget()
        anim_lay = QVBoxLayout(self.anim_export_box)
        anim_lay.setContentsMargins(0, 0, 0, 0)
        anim_lay.setSpacing(7)
        anim_lay.addWidget(self._sep())
        anim_lay.addWidget(QLabel('Animation Export'))
        self.anim_export_combo = QComboBox()
        self.anim_export_combo.addItems([
            'Frames → folder (.txt)',
            'Frames → folder (.md)',
            'Single .txt (annotated)',
            'Animated .html',
            'Animated .gif',
            'Sprite sheet (.png)',
        ])
        anim_lay.addWidget(self.anim_export_combo)

        range_row = QHBoxLayout()
        range_row.addWidget(QLabel('Frames:'))
        self.frame_from = QSpinBox()
        self.frame_to = QSpinBox()
        range_row.addWidget(self.frame_from, 1)
        range_row.addWidget(QLabel('to'))
        range_row.addWidget(self.frame_to, 1)
        anim_lay.addLayout(range_row)

        self.anim_export_btn = QPushButton('Export animation')
        anim_lay.addWidget(self.anim_export_btn)
        self.anim_export_box.hide()
        layout.addWidget(self.anim_export_box)

        layout.addStretch()

        # Status
        self.status_label = QLabel('Ready')
        self.status_label.setObjectName('status')
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

    def _label_row(self, left: str, val_attr: str, default: str) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(QLabel(left))
        row.addStretch()
        lbl = QLabel(default)
        lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        setattr(self, val_attr, lbl)
        row.addWidget(lbl)
        return row

    @staticmethod
    def _slider(lo: int, hi: int, val: int) -> QSlider:
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(lo, hi)
        s.setValue(val)
        return s

    @staticmethod
    def _sep() -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.Shape.HLine)
        f.setStyleSheet('QFrame { color: #1e1e1e; }')
        return f

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _wire_signals(self) -> None:
        self.open_btn.clicked.connect(self.open_file_requested)
        self.demo_load_btn.clicked.connect(
            lambda: self.demo_requested.emit(self.demo_combo.currentText())
        )
        self.drop_zone.file_dropped.connect(self.file_dropped)

        self.cols_slider.valueChanged.connect(
            lambda v: (self.cols_val.setText(str(v)), self.settings_changed.emit())
        )
        self.thresh_slider.valueChanged.connect(
            lambda v: (self.thresh_val.setText(str(v)), self.settings_changed.emit())
        )
        self.contrast_slider.valueChanged.connect(
            lambda v: (self.contrast_val.setText(f'{v / 10:.1f}'), self.settings_changed.emit())
        )
        self.font_slider.valueChanged.connect(
            lambda v: (self.font_val.setText(f'{v}px'), self.settings_changed.emit())
        )

        for btn in self.mode_group.buttons():
            btn.clicked.connect(self._on_mode_changed)

        self.charset_combo.currentTextChanged.connect(self._on_charset_changed)
        self.custom_chars.textChanged.connect(lambda: self.settings_changed.emit())
        self.invert_check.stateChanged.connect(lambda: self.settings_changed.emit())
        self.color_check.stateChanged.connect(lambda: self.settings_changed.emit())

        self.mask_check.stateChanged.connect(
            lambda: (self._update_mask_widgets(), self.settings_changed.emit())
        )
        self.mask_tol_slider.valueChanged.connect(
            lambda v: (self.mask_tol_val.setText(str(v)), self.settings_changed.emit())
        )
        self.mask_mode_combo.currentIndexChanged.connect(
            lambda: self.settings_changed.emit()
        )
        self.mask_color_btn.clicked.connect(self._pick_mask_color)
        self.mask_reset_btn.clicked.connect(self._reset_mask_color)

        self.paint_btn.toggled.connect(self.paint_toggled)
        self.paint_color_btn.clicked.connect(self._pick_paint_color)
        self.brush_slider.valueChanged.connect(lambda v: self.brush_val.setText(str(v)))
        self.clear_edits_btn.clicked.connect(self.clear_edits)

        self.copy_btn.clicked.connect(self.copy_text)
        self.txt_btn.clicked.connect(self.save_txt)
        self.html_btn.clicked.connect(self.save_html)
        self.png_btn.clicked.connect(self.save_png)
        self.anim_export_btn.clicked.connect(self._on_anim_export)
        # Keep from <= to by tightening the opposite spinbox's bound
        self.frame_from.valueChanged.connect(self.frame_to.setMinimum)
        self.frame_to.valueChanged.connect(self.frame_from.setMaximum)

    # ------------------------------------------------------------------
    # Slot helpers
    # ------------------------------------------------------------------

    def _on_mode_changed(self) -> None:
        self._on_mode_changed_silent()
        self.settings_changed.emit()

    def _on_mode_changed_silent(self) -> None:
        edge_modes = ('edge', 'hybrid')
        self.thresh_slider.setEnabled(self._current_mode() in edge_modes)

    def _update_mask_widgets(self) -> None:
        on = self.mask_check.isChecked()
        self.mask_tol_slider.setEnabled(on)
        self.mask_color_btn.setEnabled(on)
        self.mask_reset_btn.setEnabled(on)
        self.mask_anim_box.setVisible(self._anim_active and on)

    def _pick_mask_color(self) -> None:
        initial = QColor(*self._mask_color) if self._mask_color else QColor(0, 0, 0)
        color = QColorDialog.getColor(initial, self, 'Pick background key color')
        if color.isValid():
            self._set_mask_color((color.red(), color.green(), color.blue()))
            self.settings_changed.emit()

    def _reset_mask_color(self) -> None:
        if self._mask_color is not None:
            self._set_mask_color(None)
            self.settings_changed.emit()

    def _set_mask_color(self, rgb: tuple | None) -> None:
        self._mask_color = rgb
        if rgb is None:
            self.mask_color_btn.setText('Auto')
            self.mask_color_btn.setStyleSheet('')
        else:
            hexcode = '#{:02x}{:02x}{:02x}'.format(*rgb)
            self.mask_color_btn.setText(hexcode)
            luma = 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]
            fg = '#000' if luma > 128 else '#fff'
            self.mask_color_btn.setStyleSheet(
                f'QPushButton {{ background: {hexcode}; color: {fg}; }}'
            )

    def current_paint_color(self) -> tuple:
        return self._paint_color

    def brush_size(self) -> int:
        return self.brush_slider.value()

    def _pick_paint_color(self) -> None:
        color = QColorDialog.getColor(QColor(*self._paint_color), self, 'Pick paint color')
        if color.isValid():
            self._set_paint_color((color.red(), color.green(), color.blue()))
            self.paint_color_changed.emit(self._paint_color)

    def _set_paint_color(self, rgb: tuple) -> None:
        self._paint_color = rgb
        hexcode = '#{:02x}{:02x}{:02x}'.format(*rgb)
        luma = 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]
        fg = '#000' if luma > 128 else '#fff'
        self.paint_color_btn.setText(hexcode)
        self.paint_color_btn.setStyleSheet(
            f'QPushButton {{ background: {hexcode}; color: {fg}; }}'
        )

    def _on_charset_changed(self, text: str) -> None:
        self.custom_chars.setVisible(text == 'Custom')
        self.settings_changed.emit()

    def _on_anim_export(self) -> None:
        keys = ['frames_txt', 'frames_md', 'anim_txt', 'anim_html', 'anim_gif', 'spritesheet']
        self.export_animation.emit(keys[self.anim_export_combo.currentIndex()])

    def _sync_labels(self) -> None:
        self.cols_val.setText(str(self.cols_slider.value()))
        self.thresh_val.setText(str(self.thresh_slider.value()))
        self.contrast_val.setText(f'{self.contrast_slider.value() / 10:.1f}')
        self.font_val.setText(f'{self.font_slider.value()}px')
        self.mask_tol_val.setText(str(self.mask_tol_slider.value()))

    def _current_mode(self) -> str:
        for btn in self.mode_group.buttons():
            if btn.isChecked():
                return btn.property('mode')
        return 'luminance'

    @staticmethod
    def _bool(val) -> bool:
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.lower() == 'true'
        return bool(val)
