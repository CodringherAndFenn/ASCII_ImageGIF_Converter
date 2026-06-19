import json
import os
from pathlib import Path


def export_txt(chars: list[list[str]], path: str) -> None:
    text = '\n'.join(''.join(row) for row in chars)
    Path(path).write_text(text, encoding='utf-8')


_HTML_STYLE = (
    '<style>\n'
    'body { background:#0d0d0d; margin:0; padding:1rem; }\n'
    "pre { font-family:'JetBrains Mono','JuliaMono','Cascadia Code',"
    "'DejaVu Sans Mono','Noto Sans Mono','Symbola',monospace; "
    "font-size:10px; line-height:1;\n"
    '      color:#c8c8c8; white-space:pre; }\n'
    '</style>'
)


def export_html(
    chars: list[list[str]],
    colors: list,
    path: str,
    overrides: dict | None = None,
    font_size: int = 10,
    line_height: float = 1.36,
) -> None:
    style = (_HTML_STYLE
             .replace('font-size:10px', f'font-size:{font_size}px')
             .replace('line-height:1;', f'line-height:{line_height:.3f};'))
    html = (
        '<!DOCTYPE html>\n'
        '<html><head><meta charset="utf-8">\n'
        + style
        + '</head><body><pre>'
        + '<br>'.join(_frame_html_lines(chars, colors, overrides))
        + '</pre></body></html>'
    )
    Path(path).write_text(html, encoding='utf-8')


def export_png(
    chars: list[list[str]],
    colors: list,
    path: str,
    font_size: int = 10,
    mask=None,
    overrides: dict | None = None,
) -> None:
    if not chars:
        return

    font = _load_font(font_size, _grid_has_braille(chars))
    cell_w, cell_h = _measure_cell(font)

    rows = len(chars)
    cols = max(len(r) for r in chars)
    img = _render_frame_image(chars, colors, font, cell_w, cell_h, cols, rows, mask, overrides)
    img.save(path, format='PNG')


# ---------------------------------------------------------------------------
# Animation exports
# ---------------------------------------------------------------------------

def export_md(chars: list[list[str]], path: str) -> None:
    # Fenced code block so markdown viewers keep the whitespace intact
    text = '\n'.join(''.join(row) for row in chars)
    Path(path).write_text(f'```text\n{text}\n```\n', encoding='utf-8')


def export_frames(frames_chars: list, dir_path: str, fmt: str = 'txt') -> str:
    """Write one file per frame into a fresh subfolder of dir_path
    (so frame files never spill into the chosen directory directly).
    Returns the created subfolder path."""
    base = Path(dir_path) / 'ascii_frames'
    folder = base
    n = 1
    while folder.exists():
        n += 1
        folder = base.parent / f'{base.name}_{n}'
    folder.mkdir(parents=True)
    writer = export_md if fmt == 'md' else export_txt
    for i, chars in enumerate(frames_chars):
        writer(chars, str(folder / f'frame_{i + 1:04d}.{fmt}'))
    return str(folder)


def export_anim_txt(frames_chars: list, durations: list[int], loop: int, path: str) -> None:
    parts = [f'# ascii-animation frames={len(frames_chars)} loop={loop}']
    for i, chars in enumerate(frames_chars):
        parts.append(f'--- frame {i + 1:04d} duration={durations[i]}ms ---')
        parts.append('\n'.join(''.join(row) for row in chars))
    Path(path).write_text('\n'.join(parts) + '\n', encoding='utf-8')


def export_anim_html(
    frames_chars: list,
    frames_colors: list,
    durations: list[int],
    loop: int,
    path: str,
    font_size: int = 10,
    frames_overrides: list | None = None,
    line_height: float = 1.36,
) -> None:
    frame_html = [
        '<br>'.join(_frame_html_lines(
            chars,
            frames_colors[i] if frames_colors else [],
            frames_overrides[i] if frames_overrides else None,
        ))
        for i, chars in enumerate(frames_chars)
    ]
    style = (_HTML_STYLE
             .replace('font-size:10px', f'font-size:{font_size}px')
             .replace('line-height:1;', f'line-height:{line_height:.3f};'))
    script = (
        '<script>\n'
        f'const frames = {json.dumps(frame_html)};\n'
        f'const durations = {json.dumps(list(durations))};\n'
        f'const loop = {int(loop)};\n'
        'const screen = document.getElementById("screen");\n'
        'let i = 0, pass = 0;\n'
        'function tick() {\n'
        '  screen.innerHTML = frames[i];\n'
        '  const d = durations[i];\n'
        '  i += 1;\n'
        '  if (i >= frames.length) {\n'
        '    i = 0; pass += 1;\n'
        '    if (loop > 0 && pass >= loop) return;\n'
        '  }\n'
        '  setTimeout(tick, d);\n'
        '}\n'
        'tick();\n'
        '</script>'
    )
    html = (
        '<!DOCTYPE html>\n'
        '<html><head><meta charset="utf-8">\n'
        + style
        + '</head><body><pre id="screen"></pre>\n'
        + script
        + '</body></html>'
    )
    Path(path).write_text(html, encoding='utf-8')


def export_spritesheet(
    frames_chars: list,
    frames_colors: list,
    path: str,
    font_size: int = 10,
    columns: int | None = None,
    masks: list | None = None,
    frames_overrides: list | None = None,
) -> dict:
    """Tile every frame into one PNG grid of uniform cells (a sprite sheet
    ready for game engines). Returns a dict describing the layout
    (frames, columns, rows, frame_w, frame_h, sheet_w, sheet_h) so the
    caller can report the per-frame size needed to slice it back."""
    if not frames_chars:
        return {}

    import math
    from PIL import Image

    font = _load_font(font_size, _frames_have_braille(frames_chars))
    cell_w, cell_h = _measure_cell(font)

    # Uniform frame size across the sheet (braille rounding can vary the grid).
    rows = max(len(chars) for chars in frames_chars)
    cols = max(max(len(r) for r in chars) if chars else 0 for chars in frames_chars)
    frame_w = cols * cell_w
    frame_h = rows * cell_h

    n = len(frames_chars)
    if columns is None or columns < 1:
        # Square-ish grid: predictable for engines, space-efficient.
        columns = max(1, math.ceil(math.sqrt(n)))
    columns = min(columns, n)
    grid_rows = math.ceil(n / columns)

    transparent = masks is not None and any(m is not None for m in masks)
    mode = 'RGBA' if transparent else 'RGB'
    bg = (13, 13, 13, 0) if transparent else (13, 13, 13)
    sheet = Image.new(mode, (columns * frame_w, grid_rows * frame_h), color=bg)

    for i, chars in enumerate(frames_chars):
        img = _render_frame_image(
            chars, frames_colors[i] if frames_colors else [],
            font, cell_w, cell_h, cols, rows,
            masks[i] if transparent else None,
            frames_overrides[i] if frames_overrides else None,
        )
        if transparent and img.mode != 'RGBA':
            img = img.convert('RGBA')
        gx = (i % columns) * frame_w
        gy = (i // columns) * frame_h
        sheet.paste(img, (gx, gy))

    sheet.save(path, format='PNG')
    return {
        'frames': n,
        'columns': columns,
        'rows': grid_rows,
        'frame_w': frame_w,
        'frame_h': frame_h,
        'sheet_w': columns * frame_w,
        'sheet_h': grid_rows * frame_h,
    }


def export_anim_gif(
    frames_chars: list,
    frames_colors: list,
    durations: list[int],
    loop: int,
    path: str,
    font_size: int = 10,
    masks: list | None = None,
    frames_overrides: list | None = None,
) -> None:
    if not frames_chars:
        return

    font = _load_font(font_size, _frames_have_braille(frames_chars))
    cell_w, cell_h = _measure_cell(font)

    # Common canvas across frames guards against braille rounding differences
    rows = max(len(chars) for chars in frames_chars)
    cols = max(max(len(r) for r in chars) if chars else 0 for chars in frames_chars)

    transparent = masks is not None and any(m is not None for m in masks)
    imgs = [
        _render_frame_image(
            chars, frames_colors[i] if frames_colors else [],
            font, cell_w, cell_h, cols, rows,
            masks[i] if transparent else None,
            frames_overrides[i] if frames_overrides else None,
        )
        for i, chars in enumerate(frames_chars)
    ]
    extra = {}
    if transparent:
        # GIF transparency needs palette mode with a reserved index; quantize
        # to 255 colors so index 255 stays free for transparent pixels.
        from PIL import Image
        quantized = []
        for im in imgs:
            p = im.convert('RGB').quantize(colors=255, method=Image.Quantize.MEDIANCUT)
            if im.mode == 'RGBA':
                alpha = im.getchannel('A')
                p.paste(255, mask=alpha.point(lambda a: 255 if a < 128 else 0))
            quantized.append(p)
        imgs = quantized
        extra['transparency'] = 255
    imgs[0].save(
        path, format='GIF', save_all=True, append_images=imgs[1:],
        duration=list(durations), loop=int(loop), disposal=2, **extra,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _frame_html_lines(chars: list[list[str]], colors: list, overrides: dict | None = None) -> list[str]:
    lines = []
    for r, row in enumerate(chars):
        parts = []
        for c, ch in enumerate(row):
            escaped = ch.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            rgb = overrides.get((r, c)) if overrides else None
            if rgb is None and colors and r < len(colors) and c < len(colors[r]):
                rgb = colors[r][c]
            if rgb is not None:
                parts.append(f'<span style="color:rgb({rgb[0]},{rgb[1]},{rgb[2]})">{escaped}</span>')
            else:
                parts.append(escaped)
        lines.append(''.join(parts))
    return lines


def _render_frame_image(
    chars: list[list[str]],
    colors: list,
    font,
    cell_w: int,
    cell_h: int,
    cols: int,
    rows: int,
    mask=None,
    overrides: dict | None = None,
):
    from PIL import Image, ImageDraw
    import numpy as np

    if mask is None:
        img = Image.new("RGB", (cols * cell_w, rows * cell_h), color=(13, 13, 13))
    else:
        img = Image.new("RGBA", (cols * cell_w, rows * cell_h), color=(13, 13, 13, 255))
    draw = ImageDraw.Draw(img)

    for r, row in enumerate(chars):
        for c, ch in enumerate(row):
            color = (200, 200, 200)
            rgb = overrides.get((r, c)) if overrides else None
            if rgb is None and colors and r < len(colors) and c < len(colors[r]):
                rgb = colors[r][c]
            if rgb is not None:
                color = (int(rgb[0]), int(rgb[1]), int(rgb[2]))
            draw.text((c * cell_w, r * cell_h), ch, fill=color, font=font)

    if mask is not None:
        arr = np.array(img)
        for r, mask_row in enumerate(mask):
            for c, m in enumerate(mask_row):
                if m:
                    arr[r * cell_h:(r + 1) * cell_h, c * cell_w:(c + 1) * cell_w, 3] = 0
        img = Image.fromarray(arr)

    return img


# Bundled OFL font shipped with the app (app/fonts/). JuliaMono covers ASCII,
# block elements AND Braille (U+2800–U+28FF), so raster exports render every
# charset identically on any machine — PIL does no per-glyph fallback, unlike
# Qt/browsers, so a complete bundled font is the only way to guarantee output.
_BUNDLED_FONT = os.path.join(os.path.dirname(__file__), 'fonts', 'JuliaMono-Regular.ttf')

# System fallbacks, used only if the bundled font can't be loaded.
_FONT_SEARCH_PATHS = [
    "/usr/share/fonts/truetype/jetbrains-mono/JetBrainsMono-Regular.ttf",
    "/usr/share/fonts/OTF/JetBrainsMono-Regular.ttf",
    "/usr/share/fonts/jetbrains-mono/JetBrainsMono-Regular.ttf",
    "/usr/share/fonts/truetype/firacode/FiraCode-Regular.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
    "/usr/share/fonts/liberation/LiberationMono-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/freefont/FreeMono.ttf",
    "C:/Windows/Fonts/consola.ttf",
    "C:/Windows/Fonts/cour.ttf",
    "/Library/Fonts/Courier New.ttf",
    "/System/Library/Fonts/Menlo.ttc",
]

_BRAILLE_LO, _BRAILLE_HI = 0x2800, 0x28FF


def _grid_has_braille(chars: list) -> bool:
    """True if any cell uses a Braille-pattern glyph (U+2800–U+28FF)."""
    for row in chars:
        for ch in row:
            if ch and _BRAILLE_LO <= ord(ch[0]) <= _BRAILLE_HI:
                return True
    return False


def _frames_have_braille(frames_chars: list) -> bool:
    return any(_grid_has_braille(c) for c in frames_chars if c)


def _fc_match(want_braille: bool) -> str | None:
    """Resolve a monospace font path via fontconfig, preferring JetBrains
    Mono and (when Braille is needed) requiring charset coverage. Returns
    None when fontconfig is unavailable (e.g. Windows/macOS)."""
    import shutil
    import subprocess
    fc = shutil.which('fc-match')
    if not fc:
        return None
    pattern = 'JetBrains Mono,monospace:spacing=100'
    if want_braille:
        pattern += ':charset=2800-28ff'
    try:
        res = subprocess.run(
            [fc, '-f', '%{file}', pattern],
            capture_output=True, text=True, timeout=5,
        )
    except Exception:
        return None
    path = res.stdout.strip()
    return path if path and os.path.exists(path) else None


def _load_font(size: int, want_braille: bool = False):
    from PIL import ImageFont
    candidates = [_BUNDLED_FONT]
    matched = _fc_match(want_braille)
    if matched:
        candidates.append(matched)
    candidates += _FONT_SEARCH_PATHS
    for fp in candidates:
        if fp and os.path.exists(fp):
            try:
                return ImageFont.truetype(fp, size)
            except Exception:
                continue
    try:
        return ImageFont.load_default(size)  # Pillow >= 10.1: sized TTF
    except TypeError:
        return ImageFont.load_default()


def _measure_cell(font) -> tuple[int, int]:
    # A monospace cell is the glyph *advance width* by the *line height*
    # (ascent + descent) — not the tight bounding box of a glyph, which is
    # nearly square and would render the art stretched/overlapping.
    from PIL import ImageFont
    if isinstance(font, ImageFont.FreeTypeFont):
        cell_w = font.getlength('X')
        ascent, descent = font.getmetrics()
        cell_h = ascent + descent
        return max(1, int(round(cell_w))), max(1, int(round(cell_h)))
    return 6, 12
