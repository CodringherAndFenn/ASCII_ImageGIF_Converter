from PyQt6.QtWidgets import QWidget, QVBoxLayout, QScrollArea
from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF, pyqtSignal
from PyQt6.QtGui import QFont, QFontDatabase, QFontMetricsF, QFontInfo, QPainter, QColor


_PAD = 4
_BG = QColor('#0d0d0d')
_DEFAULT_FG = QColor('#c8c8c8')
_DIFF_BG = QColor('#402020')
_DIFF_FG = QColor('#4af626')


class AsciiCanvas(QWidget):
    """Custom-painted ASCII grid. Drawing and mouse hit-testing use the exact
    same cell geometry, so painted cells always land where they were clicked —
    and the grid can stay centered without throwing the mapping off."""

    cell_painted = pyqtSignal(int, int, bool)  # row, col, erase

    def __init__(self, parent=None):
        super().__init__(parent)
        self._chars: list = []
        self._colors: list = []
        self._overrides: dict | None = None
        self._diff: set | None = None
        self._color_mode = False
        self._font = QFont()
        self._paint_mode = False
        self._drag_button = None
        self._seen: set = set()

    # -- content -----------------------------------------------------------

    def set_content(self, chars, colors, color_mode, font, diff=None, overrides=None) -> None:
        self._chars = chars
        self._colors = colors
        self._color_mode = color_mode
        self._font = font
        self._diff = diff
        self._overrides = overrides or None
        cw, ch = self._cell_size()
        rows = len(chars)
        cols = max((len(r) for r in chars), default=0)
        self.setMinimumSize(
            int(round(cols * cw)) + 2 * _PAD, int(round(rows * ch)) + 2 * _PAD
        )
        self.update()

    def set_paint_mode(self, on: bool) -> None:
        self._paint_mode = on
        self._drag_button = None
        self._seen = set()
        self.setCursor(Qt.CursorShape.CrossCursor if on else Qt.CursorShape.ArrowCursor)
        if not on:
            self.unsetCursor()

    # -- geometry ----------------------------------------------------------

    def _cell_size(self) -> tuple[float, float]:
        # Fractional advance/height: positioning, hit-testing and sizing all
        # use the same exact cell metrics, so the grid never shifts between
        # renders (e.g. when the first paint stroke is applied).
        fm = QFontMetricsF(self._font)
        return max(1.0, fm.horizontalAdvance('X')), max(1.0, fm.height())

    def _geometry(self):
        cw, ch = self._cell_size()
        rows = len(self._chars)
        cols = max((len(r) for r in self._chars), default=0)
        offset_x = max(float(_PAD), (self.width() - cols * cw) / 2.0)
        offset_y = float(_PAD)
        return cw, ch, offset_x, offset_y, rows, cols

    def _cell_at(self, pos):
        cw, ch, ox, oy, rows, cols = self._geometry()
        if rows <= 0 or cols <= 0:
            return None
        x = pos.x() - ox
        y = pos.y() - oy
        if x < 0 or y < 0:
            return None
        col = int(x // cw)
        row = int(y // ch)
        if 0 <= row < rows and 0 <= col < len(self._chars[row]):
            return row, col
        return None

    # -- painting ----------------------------------------------------------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), _BG)
        if not self._chars:
            return
        painter.setFont(self._font)
        cw, ch, ox, oy, rows, cols = self._geometry()
        ascent = QFontMetricsF(self._font).ascent()

        for r, row in enumerate(self._chars):
            y = oy + r * ch
            baseline = y + ascent
            for c, ch_ in enumerate(row):
                x = ox + c * cw
                changed = self._diff is not None and (r, c) in self._diff
                if changed:
                    painter.fillRect(QRectF(x, y, cw, ch), _DIFF_BG)
                rgb = self._overrides.get((r, c)) if self._overrides else None
                if rgb is None and self._color_mode and self._colors \
                        and r < len(self._colors) and c < len(self._colors[r]):
                    rgb = self._colors[r][c]
                if rgb is not None:
                    painter.setPen(QColor(rgb[0], rgb[1], rgb[2]))
                elif changed:
                    painter.setPen(_DIFF_FG)
                else:
                    painter.setPen(_DEFAULT_FG)
                painter.drawText(QPointF(x, baseline), ch_)

    # -- mouse -------------------------------------------------------------

    def _paint_at(self, pos) -> None:
        cell = self._cell_at(pos)
        if cell is None or cell in self._seen:
            return
        self._seen.add(cell)
        erase = self._drag_button == Qt.MouseButton.RightButton
        self.cell_painted.emit(cell[0], cell[1], erase)

    def mousePressEvent(self, event):
        if not self._paint_mode:
            return super().mousePressEvent(event)
        btn = event.button()
        if btn in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            self._drag_button = btn
            self._seen = set()
            self._paint_at(event.position().toPoint())
            event.accept()

    def mouseMoveEvent(self, event):
        if not self._paint_mode or self._drag_button is None:
            return super().mouseMoveEvent(event)
        self._paint_at(event.position().toPoint())
        event.accept()

    def mouseReleaseEvent(self, event):
        if not self._paint_mode or self._drag_button is None:
            return super().mouseReleaseEvent(event)
        self._drag_button = None
        self._seen = set()
        event.accept()


class PreviewPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._font_family = self._pick_font()
        self._border_state = False
        self._setup_ui()

        self._border_timer = QTimer(self)
        self._border_timer.setInterval(400)
        self._border_timer.timeout.connect(self._toggle_border)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_busy(self, busy: bool) -> None:
        if busy:
            self._border_timer.start()
        else:
            self._border_timer.stop()
            self._set_border('#1e1e1e')

    def set_paint_mode(self, on: bool) -> None:
        self.canvas.set_paint_mode(on)

    def css_line_height(self, font_size: int) -> float:
        """CSS line-height (em multiplier) that reproduces the preview's row
        pitch in a browser, so HTML exports aren't vertically smushed."""
        font = QFont(self._font_family)
        font.setPointSize(font_size)
        px = QFontInfo(font).pixelSize()
        return QFontMetricsF(font).height() / px if px else 1.36

    def render(
        self,
        chars: list[list[str]],
        colors: list,
        color_mode: bool,
        font_size: int,
        diff_cells: set | None = None,
        overrides: dict | None = None,
    ) -> None:
        font = QFont(self._font_family)
        font.setPointSize(font_size)
        self.canvas.set_content(chars, colors, color_mode, font, diff_cells, overrides)

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _pick_font(self) -> str:
        families = QFontDatabase.families()
        for candidate in ('JetBrains Mono', 'Fira Code', 'Courier New'):
            if candidate in families:
                return candidate
        return 'monospace'

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._set_border('#1e1e1e')

        self.canvas = AsciiCanvas()
        self.cell_painted = self.canvas.cell_painted

        self.scroll.setWidget(self.canvas)
        layout.addWidget(self.scroll)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _set_border(self, color: str) -> None:
        self.scroll.setStyleSheet(f'QScrollArea {{ border: 1px solid {color}; }}')

    def _toggle_border(self) -> None:
        self._border_state = not self._border_state
        self._set_border('#4af626' if self._border_state else '#1e1e3a')
