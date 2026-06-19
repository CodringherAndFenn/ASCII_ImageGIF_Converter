from PyQt6.QtWidgets import (
    QMainWindow, QSplitter, QMessageBox, QFileDialog, QApplication,
    QWidget, QVBoxLayout,
)
from PyQt6.QtCore import Qt, QSettings, QTimer
from PyQt6.QtGui import QShortcut, QKeySequence, QDragEnterEvent, QDropEvent

from . import processor
from .controls import ControlPanel
from .preview import PreviewPanel
from .worker import ConversionWorker, AnimationConversionWorker
from .playback import PlaybackBar
from .framestrip import FrameStrip


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('ASCII Converter')
        self.setAcceptDrops(True)

        self.worker: ConversionWorker | None = None
        self.current_rgba = None
        self.last_chars: list = []
        self.last_colors: list = []
        self.last_mask = None

        # Paint post-processing: per-cell foreground colour overrides.
        self.overrides: dict = {}            # static image edits
        self.anim_overrides: list = []       # per-frame edits, parallel to anim_chars
        self._override_shape: tuple | None = None
        self._anim_override_shape: tuple | None = None
        self._paint_color: tuple = (74, 246, 38)

        self.anim_worker: AnimationConversionWorker | None = None
        self.anim_frames: list | None = None  # None => static mode
        self.anim_durations: list = []
        self.anim_loop: int = 0
        self.anim_chars: list = []  # per-frame grids, None until converted
        self.anim_colors: list = []
        self.anim_masks: list = []
        self.anim_diffs: list = []  # per-frame changed-cell sets
        self._resume_after_convert = False

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(150)
        self._debounce.timeout.connect(self.start_conversion)

        # Coalesce rapid paint events into a single re-render.
        self._paint_timer = QTimer(self)
        self._paint_timer.setSingleShot(True)
        self._paint_timer.setInterval(40)
        self._paint_timer.timeout.connect(self._repaint_preview)

        self._build_ui()
        self._build_shortcuts()
        self._paint_color = self.controls.current_paint_color()
        self._restore_settings()

        # Pre-load the sphere demo on first launch
        self._load_demo('Sphere')

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.controls = ControlPanel()
        self.preview = PreviewPanel()
        self.playback = PlaybackBar()
        self.playback.hide()
        self.strip = FrameStrip()
        self.strip.hide()

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)
        right_layout.addWidget(self.preview, 1)
        right_layout.addWidget(self.playback)
        right_layout.addWidget(self.strip)

        self.splitter.addWidget(self.controls)
        self.splitter.addWidget(right)
        self.splitter.setSizes([288, 912])
        self.splitter.setCollapsible(0, False)

        self.setCentralWidget(self.splitter)

        self.controls.settings_changed.connect(self._on_settings_changed)
        self.controls.open_file_requested.connect(self._open_file)
        self.controls.demo_requested.connect(self._load_demo)
        self.controls.file_dropped.connect(self._load_file)
        self.controls.copy_text.connect(self._copy_text)
        self.controls.save_txt.connect(self._save_txt)
        self.controls.save_html.connect(self._save_html)
        self.controls.save_png.connect(self._save_png)
        self.controls.export_animation.connect(self._export_animation)
        self.controls.paint_toggled.connect(self._on_paint_toggled)
        self.controls.paint_color_changed.connect(self._on_paint_color)
        self.controls.clear_edits.connect(self._clear_current_edits)
        self.preview.cell_painted.connect(self._on_cell_painted)

        self.playback.frame_changed.connect(self._show_frame)
        self.playback.diff_toggled.connect(
            lambda _on: self._show_frame(self.playback.current_frame())
        )
        self.strip.frame_clicked.connect(self._seek_frame)

    def _build_shortcuts(self) -> None:
        QShortcut(QKeySequence('Ctrl+O'), self).activated.connect(self._open_file)
        QShortcut(QKeySequence('Ctrl+C'), self).activated.connect(self._copy_text)
        QShortcut(QKeySequence('Ctrl+S'), self).activated.connect(self._save_txt)
        QShortcut(QKeySequence('Ctrl+Shift+S'), self).activated.connect(self._save_png)
        QShortcut(QKeySequence('I'), self).activated.connect(self.controls.toggle_invert)
        QShortcut(QKeySequence('E'), self).activated.connect(self.controls.cycle_mode)
        QShortcut(QKeySequence('+'), self).activated.connect(lambda: self.controls.adjust_cols(5))
        QShortcut(QKeySequence('-'), self).activated.connect(lambda: self.controls.adjust_cols(-5))
        QShortcut(QKeySequence('Space'), self).activated.connect(self._toggle_playback)

    # ------------------------------------------------------------------
    # Settings persistence
    # ------------------------------------------------------------------

    def _restore_settings(self) -> None:
        s = QSettings()
        geom = s.value('geometry')
        if geom:
            self.restoreGeometry(geom)
        else:
            self.resize(1200, 800)
        splitter_state = s.value('splitter')
        if splitter_state:
            self.splitter.restoreState(splitter_state)
        self.controls.restore_settings(s)

    def _save_settings(self) -> None:
        s = QSettings()
        s.setValue('geometry', self.saveGeometry())
        s.setValue('splitter', self.splitter.saveState())
        self.controls.save_settings(s)

    # ------------------------------------------------------------------
    # Image loading
    # ------------------------------------------------------------------

    def _open_file(self) -> None:
        s = QSettings()
        last_dir = s.value('last_dir', '')
        path, _ = QFileDialog.getOpenFileName(
            self, 'Open Image', last_dir,
            'Images (*.png *.jpg *.jpeg *.bmp *.gif *.tiff *.webp *.ico *.ppm)',
        )
        if not path:
            return
        from pathlib import Path
        s.setValue('last_dir', str(Path(path).parent))
        self._load_file(path)

    def _load_file(self, path: str) -> None:
        try:
            anim = processor.load_animation(path)
            if anim is not None:
                self._load_animation(anim)
            else:
                self._load_rgba(processor.load_image(path))
        except Exception as exc:
            QMessageBox.critical(self, 'Error', f'Failed to load image:\n{exc}')

    def _load_demo(self, name: str) -> None:
        generators = {
            'Sphere': processor.demo_sphere,
            'Wave': processor.demo_wave,
            'Portrait': processor.demo_portrait,
            'Gradient': processor.demo_gradient,
        }
        fn = generators.get(name)
        if fn:
            self._load_rgba(fn())

    def _load_rgba(self, rgba) -> None:
        self._clear_animation()
        self.overrides = {}
        self._override_shape = None
        self.current_rgba = rgba
        self.start_conversion()

    def _load_animation(self, anim) -> None:
        self._clear_animation()
        self.anim_frames = anim.frames
        self.anim_durations = anim.durations
        self.anim_loop = anim.loop_count
        self.current_rgba = anim.frames[0]
        self.strip.set_frames(anim.frames)
        self.strip.show()
        self.playback.set_animation(len(anim.frames), anim.durations)
        self.playback.show()
        self.controls.set_animation_mode(True)
        self.controls.set_frame_count(len(anim.frames))
        if anim.truncated:
            self.controls.set_status(f'GIF truncated to {len(anim.frames)} frames')
        self.start_conversion()

    def _clear_animation(self) -> None:
        if self.anim_worker and self.anim_worker.isRunning():
            self.anim_worker.cancel()
            self._disconnect_anim_worker()
            self.anim_worker.wait()
        self.anim_worker = None
        self.anim_frames = None
        self.anim_durations = []
        self.anim_loop = 0
        self.anim_chars = []
        self.anim_colors = []
        self.anim_masks = []
        self.anim_diffs = []
        self.anim_overrides = []
        self._anim_override_shape = None
        self.playback.clear()
        self.playback.hide()
        self.strip.clear()
        self.strip.hide()
        self.controls.set_animation_mode(False)

    def _disconnect_anim_worker(self) -> None:
        try:
            self.anim_worker.frame_done.disconnect()
            self.anim_worker.all_done.disconnect()
            self.anim_worker.error.disconnect()
        except TypeError:
            pass  # already disconnected

    # ------------------------------------------------------------------
    # Conversion
    # ------------------------------------------------------------------

    def _on_settings_changed(self) -> None:
        self._debounce.start()

    def start_conversion(self) -> None:
        if self.anim_frames is not None:
            self._start_animation_conversion()
            return
        if self.current_rgba is None:
            return
        if self.worker and self.worker.isRunning():
            self.worker.finished.disconnect()
            self.worker.error.disconnect()
            self.worker.quit()
            self.worker.wait()

        self.preview.set_busy(True)
        self.worker = ConversionWorker(self.current_rgba, self.controls.collect_settings())
        self.worker.finished.connect(self._on_done)
        self.worker.error.connect(self._on_error)
        self.worker.start()

    def _on_done(self, chars: list, colors: list, mask, elapsed_ms: float) -> None:
        self.last_chars = chars
        self.last_colors = colors
        self.last_mask = mask
        rows = len(chars)
        cols = len(chars[0]) if rows else 0
        if self._override_shape != (rows, cols):
            self.overrides = {}
            self._override_shape = (rows, cols)
        s = self.controls.collect_settings()
        self.preview.render(chars, colors, s['color'], s['font_size'], None, self.overrides)
        self.preview.set_busy(False)
        if chars:
            self.controls.set_status(f'{cols}×{rows}  |  {rows * cols:,} chars  |  {elapsed_ms:.0f} ms')

    def _on_error(self, msg: str) -> None:
        self.preview.set_busy(False)
        QMessageBox.critical(self, 'Conversion Error', msg)

    # ------------------------------------------------------------------
    # Paint post-processing
    # ------------------------------------------------------------------

    def _current_overrides(self) -> dict:
        if self.anim_frames is not None:
            idx = self.playback.current_frame()
            if 0 <= idx < len(self.anim_overrides):
                return self.anim_overrides[idx]
            return {}
        return self.overrides

    def _on_paint_toggled(self, on: bool) -> None:
        self.preview.set_paint_mode(on)
        self._repaint_preview()

    def _on_paint_color(self, rgb: tuple) -> None:
        self._paint_color = rgb

    def _on_cell_painted(self, row: int, col: int, erase: bool) -> None:
        ov = self._current_overrides()
        size = self.controls.brush_size()
        half = (size - 1) // 2
        for dr in range(size):
            r = row - half + dr
            if r < 0 or r >= len(self.last_chars):
                continue
            for dc in range(size):
                c = col - half + dc
                if c < 0 or c >= len(self.last_chars[r]):
                    continue
                key = (r, c)
                if erase:
                    ov.pop(key, None)
                else:
                    ov[key] = self._paint_color
        if not self._paint_timer.isActive():
            self._paint_timer.start()

    def _repaint_preview(self) -> None:
        if not self.last_chars:
            return
        s = self.controls.collect_settings()
        if self.anim_frames is not None:
            idx = self.playback.current_frame()
            diff = None
            if self.playback.diff_check.isChecked() and idx > 0:
                diff = self.anim_diffs[idx] or set()
            self.preview.render(
                self.last_chars, self.last_colors, s['color'], s['font_size'],
                diff, self._current_overrides(),
            )
        else:
            self.preview.render(
                self.last_chars, self.last_colors, s['color'], s['font_size'],
                None, self.overrides,
            )

    def _clear_current_edits(self) -> None:
        self._current_overrides().clear()
        self._repaint_preview()

    # ------------------------------------------------------------------
    # Animation conversion & playback
    # ------------------------------------------------------------------

    def _start_animation_conversion(self) -> None:
        if self.anim_worker and self.anim_worker.isRunning():
            self.anim_worker.cancel()
            self._disconnect_anim_worker()
            self.anim_worker.wait()

        self._resume_after_convert = self.playback.is_playing()
        self.playback.pause()
        self.playback.set_enabled_controls(False)

        n = len(self.anim_frames)
        self.anim_chars = [None] * n
        self.anim_colors = [None] * n
        self.anim_masks = [None] * n
        self.anim_diffs = [None] * n
        if len(self.anim_overrides) != n:
            self.anim_overrides = [{} for _ in range(n)]

        self.preview.set_busy(True)
        self.anim_worker = AnimationConversionWorker(
            self.anim_frames, self.controls.collect_settings()
        )
        self.anim_worker.frame_done.connect(self._on_anim_frame_done)
        self.anim_worker.all_done.connect(self._on_anim_done)
        self.anim_worker.error.connect(self._on_error)
        self.anim_worker.start()

    def _on_anim_frame_done(self, idx: int, chars: list, colors: list, mask) -> None:
        self.anim_chars[idx] = chars
        self.anim_colors[idx] = colors
        self.anim_masks[idx] = mask
        if idx == 0:
            rows = len(chars)
            cols = len(chars[0]) if rows else 0
            if self._anim_override_shape != (rows, cols):
                for d in self.anim_overrides:
                    d.clear()
                self._anim_override_shape = (rows, cols)
        if idx > 0:  # frames arrive sequentially, so idx-1 is already done
            self.anim_diffs[idx] = processor.diff_grids(
                self.anim_chars[idx - 1], chars, self.anim_colors[idx - 1], colors
            )
        self.controls.set_status(f'Converting frame {idx + 1}/{len(self.anim_frames)}…')
        if idx == self.playback.current_frame():
            self._show_frame(idx)

    def _on_anim_done(self, elapsed_ms: float) -> None:
        self.preview.set_busy(False)
        self.playback.set_enabled_controls(True)
        if self.anim_chars and self.anim_chars[0]:
            rows = len(self.anim_chars[0])
            cols = len(self.anim_chars[0][0]) if rows else 0
            self.controls.set_status(
                f'{cols}×{rows}  |  {len(self.anim_frames)} frames  |  {elapsed_ms:.0f} ms'
            )
        if self._resume_after_convert:
            self._resume_after_convert = False
            self.playback.play()

    def _show_frame(self, idx: int) -> None:
        if self.anim_frames is None or not (0 <= idx < len(self.anim_chars)):
            return
        if self.anim_chars[idx] is None:
            return  # not converted yet
        s = self.controls.collect_settings()
        diff = None
        if self.playback.diff_check.isChecked() and idx > 0:
            diff = self.anim_diffs[idx] or set()
        ov = self.anim_overrides[idx] if idx < len(self.anim_overrides) else {}
        self.preview.render(
            self.anim_chars[idx], self.anim_colors[idx], s['color'], s['font_size'], diff, ov
        )
        self.last_chars = self.anim_chars[idx]
        self.last_colors = self.anim_colors[idx]
        self.last_mask = self.anim_masks[idx]
        self.strip.set_current(idx)

    def _seek_frame(self, idx: int) -> None:
        self.playback.pause()
        self.playback.set_current(idx)
        self._show_frame(idx)

    def _toggle_playback(self) -> None:
        if self.anim_frames is not None:
            self.playback.toggle_play()

    # ------------------------------------------------------------------
    # Export actions
    # ------------------------------------------------------------------

    def _copy_text(self) -> None:
        if self.last_chars:
            QApplication.clipboard().setText('\n'.join(''.join(r) for r in self.last_chars))

    def _save_txt(self) -> None:
        if not self.last_chars:
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Save Text', '', 'Text Files (*.txt)')
        if path:
            from .exporter import export_txt
            export_txt(self.last_chars, path)

    def _save_html(self) -> None:
        if not self.last_chars:
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Save HTML', '', 'HTML Files (*.html)')
        if path:
            from .exporter import export_html
            font_size = self.controls.collect_settings()['font_size']
            export_html(self.last_chars, self.last_colors, path,
                        overrides=self._current_overrides(),
                        font_size=font_size,
                        line_height=self.preview.css_line_height(font_size))

    def _save_png(self) -> None:
        if not self.last_chars:
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Save PNG', '', 'PNG Files (*.png)')
        if path:
            from .exporter import export_png
            export_png(self.last_chars, self.last_colors, path,
                       self.controls.collect_settings()['font_size'],
                       mask=self.last_mask,
                       overrides=self._current_overrides())

    def _export_animation(self, fmt: str) -> None:
        if self.anim_frames is None:
            return
        if any(c is None for c in self.anim_chars):
            QMessageBox.information(self, 'Export', 'Conversion still in progress.')
            return
        from . import exporter
        font_size = self.controls.collect_settings()['font_size']
        start, end = self.controls.export_frame_range()
        chars = self.anim_chars[start:end]
        colors = self.anim_colors[start:end]
        durations = self.anim_durations[start:end]
        masks = self.anim_masks[start:end]
        overrides = self.anim_overrides[start:end] if self.anim_overrides else None
        if not chars:
            return
        if fmt in ('frames_txt', 'frames_md'):
            d = QFileDialog.getExistingDirectory(self, 'Choose folder for frames')
            if d:
                folder = exporter.export_frames(
                    chars, d, 'md' if fmt == 'frames_md' else 'txt')
                self.controls.set_status(f'{len(chars)} frames → {folder}')
        elif fmt == 'anim_txt':
            path, _ = QFileDialog.getSaveFileName(
                self, 'Save animated text', '', 'Text Files (*.txt)')
            if path:
                exporter.export_anim_txt(chars, durations, self.anim_loop, path)
        elif fmt == 'anim_html':
            path, _ = QFileDialog.getSaveFileName(
                self, 'Save animated HTML', '', 'HTML Files (*.html)')
            if path:
                exporter.export_anim_html(
                    chars, colors, durations, self.anim_loop, path, font_size,
                    frames_overrides=overrides,
                    line_height=self.preview.css_line_height(font_size))
        elif fmt == 'anim_gif':
            path, _ = QFileDialog.getSaveFileName(
                self, 'Save animated GIF', '', 'GIF Files (*.gif)')
            if path:
                self.controls.set_status('Rendering GIF…')
                QApplication.processEvents()
                exporter.export_anim_gif(
                    chars, colors, durations, self.anim_loop, path, font_size,
                    masks=masks, frames_overrides=overrides)
                self.controls.set_status('GIF saved')
        elif fmt == 'spritesheet':
            path, _ = QFileDialog.getSaveFileName(
                self, 'Save sprite sheet', '', 'PNG Files (*.png)')
            if path:
                self.controls.set_status('Rendering sprite sheet…')
                QApplication.processEvents()
                info = exporter.export_spritesheet(
                    chars, colors, path, font_size,
                    masks=masks, frames_overrides=overrides)
                self.controls.set_status(
                    f"Sprite sheet: {info['columns']}×{info['rows']} grid  |  "
                    f"frame {info['frame_w']}×{info['frame_h']}px"
                )

    # ------------------------------------------------------------------
    # Window-wide drag & drop
    # ------------------------------------------------------------------

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        urls = event.mimeData().urls()
        if urls:
            self._load_file(urls[0].toLocalFile())

    # ------------------------------------------------------------------
    # Close
    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.quit()
            self.worker.wait()
        if self.anim_worker and self.anim_worker.isRunning():
            self.anim_worker.cancel()
            self.anim_worker.wait()
        self._save_settings()
        super().closeEvent(event)
