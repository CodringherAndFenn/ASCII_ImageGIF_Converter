import time
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from . import processor


class ConversionWorker(QThread):
    finished = pyqtSignal(object, object, object, float)  # char_grid, color_grid, mask, elapsed_ms
    error = pyqtSignal(str)

    def __init__(self, rgba: np.ndarray, settings: dict):
        super().__init__()
        self.rgba = rgba
        self.settings = settings

    def run(self) -> None:
        try:
            t0 = time.perf_counter()
            chars, colors, mask = processor.convert_frame(self.rgba, self.settings)
            elapsed = (time.perf_counter() - t0) * 1000.0
            self.finished.emit(chars, colors, mask, elapsed)

        except Exception as exc:
            import traceback
            self.error.emit(f"{exc}\n{traceback.format_exc()}")


class AnimationConversionWorker(QThread):
    frame_done = pyqtSignal(int, object, object, object)  # index, char_grid, color_grid, mask
    all_done = pyqtSignal(float)  # total elapsed_ms
    error = pyqtSignal(str)

    def __init__(self, frames: list, settings: dict):
        super().__init__()
        self.frames = frames
        self.settings = settings
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            t0 = time.perf_counter()
            precomputed = None
            if (
                self.settings.get('mask_enabled')
                and self.settings.get('mask_mode') == 'first_frame'
            ):
                precomputed = processor.compute_mask(self.frames[0], self.settings)
            for i, rgba in enumerate(self.frames):
                if self._cancel:
                    return
                chars, colors, mask = processor.convert_frame(rgba, self.settings, precomputed)
                self.frame_done.emit(i, chars, colors, mask)
            self.all_done.emit((time.perf_counter() - t0) * 1000.0)

        except Exception as exc:
            import traceback
            self.error.emit(f"{exc}\n{traceback.format_exc()}")
