import math
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageSequence

# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_image(path: str) -> np.ndarray:
    img = Image.open(path).convert("RGBA")
    arr = np.array(img)
    h, w = arr.shape[:2]
    if max(h, w) > 4000:
        scale = 2000 / max(h, w)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        arr = np.array(img)
    return arr


MAX_ANIM_FRAMES = 300
MAX_ANIM_DIM = 1280


@dataclass
class AnimationData:
    frames: list  # list[np.ndarray], per-frame RGBA, uniform shape
    durations: list  # list[int], ms per frame
    loop_count: int  # 0 = infinite (GIF convention)
    truncated: bool  # True if MAX_ANIM_FRAMES cap was hit


def load_animation(
    path: str,
    max_frames: int = MAX_ANIM_FRAMES,
    max_dim: int = MAX_ANIM_DIM,
) -> AnimationData | None:
    """Decode a multi-frame image. Returns None for static images and
    single-frame GIFs so callers can fall back to load_image()."""
    img = Image.open(path)
    if not getattr(img, 'is_animated', False) or getattr(img, 'n_frames', 1) <= 1:
        return None

    frames: list[np.ndarray] = []
    durations: list[int] = []
    truncated = False
    target_size = None

    for i, frame in enumerate(ImageSequence.Iterator(img)):
        if i >= max_frames:
            truncated = True
            break
        # Sequential seek lets Pillow compose each frame against the
        # canvas honoring disposal, so convert("RGBA") is fully coalesced.
        rgba = frame.convert("RGBA")
        if target_size is None:
            w, h = rgba.size
            if max(w, h) > max_dim:
                scale = max_dim / max(w, h)
                target_size = (int(w * scale), int(h * scale))
            else:
                target_size = rgba.size
        if rgba.size != target_size:
            rgba = rgba.resize(target_size, Image.LANCZOS)
        frames.append(np.array(rgba))

        d = frame.info.get('duration') or 0
        if d < 20:
            d = 100
        durations.append(int(d))

    return AnimationData(
        frames=frames,
        durations=durations,
        loop_count=int(img.info.get('loop', 0)),
        truncated=truncated,
    )


def grid_rows(w: int, h: int, cols: int, font_aspect: float = 2.0) -> int:
    return max(1, int(cols * (h / w) / font_aspect))


def resize_for_grid(rgba: np.ndarray, cols: int, font_aspect: float = 2.0) -> np.ndarray:
    h, w = rgba.shape[:2]
    rows = grid_rows(w, h, cols, font_aspect)
    img = Image.fromarray(rgba).resize((cols, rows), Image.LANCZOS)
    return np.array(img)


# ---------------------------------------------------------------------------
# Grayscale pipeline
# ---------------------------------------------------------------------------

# Filters run at SUPERSAMPLE x the character grid so they see real image
# detail rather than the already-decimated grid.
SUPERSAMPLE = 4

_srgb = np.arange(256, dtype=np.float32) / 255.0
_SRGB_LINEAR_LUT = np.where(
    _srgb <= 0.04045, _srgb / 12.92, ((_srgb + 0.055) / 1.055) ** 2.4
).astype(np.float32)
del _srgb


def to_grayscale(rgba: np.ndarray) -> np.ndarray:
    """Perceived luminance computed in linear light (Rec.709 weights);
    weighting gamma-encoded values directly would over-darken midtones."""
    lin = _SRGB_LINEAR_LUT[rgba[..., :3]]
    y = lin[..., 0] * 0.2126 + lin[..., 1] * 0.7152 + lin[..., 2] * 0.0722
    enc = np.where(y <= 0.0031308, y * 12.92, 1.055 * np.power(y, 1 / 2.4) - 0.055)
    return (enc * 255.0 + 0.5).astype(np.uint8)


def apply_contrast(gray: np.ndarray, factor: float) -> np.ndarray:
    if factor == 1.0:
        return gray
    mean = float(gray.mean())
    out = mean + (gray.astype(np.float32) - mean) * factor
    return np.clip(out, 0, 255).astype(np.uint8)


def _resize(img: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    interp = cv2.INTER_AREA if size[0] < img.shape[1] else cv2.INTER_CUBIC
    return cv2.resize(img, size, interpolation=interp)


def prepare_gray(
    rgba: np.ndarray,
    grid_w: int,
    grid_h: int,
    contrast: float = 1.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Full grayscale pipeline: denoise (bilateral), local contrast (CLAHE),
    user contrast, unsharp mask, then downsample to the character grid.

    Returns (gray, gray_soft) at grid size; gray_soft skips the unsharp
    mask so edge detection doesn't pick up sharpening halos.
    """
    h, w = rgba.shape[:2]
    mid_w = max(grid_w, min(w, grid_w * SUPERSAMPLE))
    mid_h = max(grid_h, round(h * mid_w / w))
    rgb = _resize(np.ascontiguousarray(rgba[:, :, :3]), (mid_w, mid_h))
    gray = to_grayscale(rgb)
    gray = cv2.bilateralFilter(gray, 5, 35, 5)
    gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    gray = apply_contrast(gray, contrast)
    soft = _resize(gray, (grid_w, grid_h))
    blurred = cv2.GaussianBlur(gray, (0, 0), 2.0)
    sharp = cv2.addWeighted(gray, 1.6, blurred, -0.6, 0)
    return _resize(sharp, (grid_w, grid_h)), soft


# ---------------------------------------------------------------------------
# Edge detection
# ---------------------------------------------------------------------------

def _convolve3x3(img: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    padded = np.pad(img.astype(np.float32), 1, mode='edge')
    out = np.zeros_like(img, dtype=np.float32)
    for i in range(3):
        for j in range(3):
            out += kernel[i, j] * padded[i:i + img.shape[0], j:j + img.shape[1]]
    return out


def sobel(gray: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    kx = np.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]], dtype=np.float32)
    ky = np.array([[-1, -2, -1], [0, 0, 0], [1, 2, 1]], dtype=np.float32)
    gx = _convolve3x3(gray, kx)
    gy = _convolve3x3(gray, ky)
    mag = np.clip(np.sqrt(gx ** 2 + gy ** 2), 0, 255).astype(np.uint8)
    angle = np.degrees(np.arctan2(gy, gx))
    return mag, angle


# ---------------------------------------------------------------------------
# Character mapping
# ---------------------------------------------------------------------------

def map_luminance(gray: np.ndarray, palette: str, invert: bool) -> list[list[str]]:
    chars = list(palette)
    if invert:
        chars = chars[::-1]
    n = len(chars) - 1
    indices = np.clip((gray.astype(np.float32) / 255.0 * n).astype(int), 0, n)
    return [[chars[i] for i in row] for row in indices]


def map_edges(
    gray: np.ndarray,
    mag: np.ndarray,
    angle: np.ndarray,
    palette: str,
    threshold: int,
    invert: bool,
) -> list[list[str]]:
    chars = list(palette)
    if invert:
        chars = chars[::-1]
    n = len(chars) - 1
    rows, cols = gray.shape
    result = []
    for r in range(rows):
        row = []
        for c in range(cols):
            if mag[r, c] >= threshold:
                a = float(angle[r, c]) % 180
                if a < 22.5 or a >= 157.5:
                    row.append('—')
                elif a < 67.5:
                    row.append('/')
                elif a < 112.5:
                    row.append('|')
                else:
                    row.append('\\')
            else:
                idx = int(gray[r, c] / 255 * n)
                row.append(chars[max(0, min(idx, n))])
        result.append(row)
    return result


# ---------------------------------------------------------------------------
# Braille mapping
# ---------------------------------------------------------------------------

BRAILLE_BASE = 0x2800
# Unicode dot bit for each (dy, dx) position within a 4x2 braille cell.
_DOT_WEIGHTS = np.array(
    [[0x01, 0x08], [0x02, 0x10], [0x04, 0x20], [0x40, 0x80]], dtype=np.uint16
)


def map_braille(gray: np.ndarray, invert: bool = False) -> list[list[str]]:
    """Floyd-Steinberg dither to 1-bit, then pack 4x2 cells into braille
    chars. Dithering preserves smooth gradients a hard threshold destroys.
    Active dots are the dark pixels (the bright ones when inverted)."""
    bw = np.array(Image.fromarray(gray).convert('1'))  # bool, True = white
    mask = bw if invert else ~bw
    rows, cols = gray.shape[0] // 4, gray.shape[1] // 2
    cells = mask[:rows * 4, :cols * 2].reshape(rows, 4, cols, 2).transpose(0, 2, 1, 3)
    codes = (cells * _DOT_WEIGHTS).sum(axis=(2, 3))
    return [[chr(BRAILLE_BASE | int(v)) for v in row] for row in codes]


# ---------------------------------------------------------------------------
# Color sampling
# ---------------------------------------------------------------------------

def sample_colors(rgba: np.ndarray, saturation: float = 1.0) -> list[list[list[int]]]:
    h, w = rgba.shape[:2]
    rgb = rgba[:, :, :3].astype(np.float32)
    if saturation != 1.0:
        gray_v = (0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2])[:, :, np.newaxis]
        rgb = np.clip(gray_v + (rgb - gray_v) * saturation, 0, 255)
    rgb_int = rgb.astype(np.uint8)
    return [[rgb_int[r, c].tolist() for c in range(w)] for r in range(h)]


# ---------------------------------------------------------------------------
# Background masking
# ---------------------------------------------------------------------------

def sample_background_color(rgba: np.ndarray) -> tuple[int, int, int]:
    """Median RGB of the four corner patches; the median resists noise and
    JPEG artifacts better than a mean."""
    h, w = rgba.shape[:2]
    p = max(2, min(h, w) // 32)
    corners = np.concatenate([
        rgba[:p, :p, :3].reshape(-1, 3),
        rgba[:p, -p:, :3].reshape(-1, 3),
        rgba[-p:, :p, :3].reshape(-1, 3),
        rgba[-p:, -p:, :3].reshape(-1, 3),
    ])
    return tuple(int(v) for v in np.median(corners, axis=0))


def compute_mask(rgba: np.ndarray, settings: dict) -> np.ndarray:
    """Full-resolution boolean mask, True = background (within mask_tolerance
    of the key color in RGB distance)."""
    key = settings.get('mask_color') or sample_background_color(rgba)
    dist = np.linalg.norm(
        rgba[:, :, :3].astype(np.float32) - np.array(key, dtype=np.float32),
        axis=-1,
    )
    return dist <= settings.get('mask_tolerance', 40)


def mask_to_grid(mask: np.ndarray, grid_w: int, grid_h: int, coverage: float = 0.5) -> np.ndarray:
    """Area-downsample a pixel mask to grid cells; a cell is masked when more
    than `coverage` of its pixels are background."""
    scaled = cv2.resize(
        mask.astype(np.float32), (grid_w, grid_h), interpolation=cv2.INTER_AREA
    )
    return scaled > coverage


def _apply_cell_mask(chars: list[list[str]], grid_mask: np.ndarray) -> None:
    for r, row in enumerate(chars):
        mask_row = grid_mask[r]
        for c in range(len(row)):
            if mask_row[c]:
                row[c] = ' '


# ---------------------------------------------------------------------------
# Frame conversion (shared by static and animation workers)
# ---------------------------------------------------------------------------

def convert_frame(
    rgba: np.ndarray,
    settings: dict,
    precomputed_mask: np.ndarray | None = None,
) -> tuple[list[list[str]], list, np.ndarray | None]:
    s = settings
    cols: int = s['cols']
    palette_name: str = s.get('palette_name', 'Standard')
    palette: str | None = s.get('palette')
    invert: bool = s.get('invert', False)
    contrast: float = s.get('contrast', 1.0)
    threshold: int = s.get('threshold', 60)
    color: bool = s.get('color', False)
    mode: str = s.get('mode', 'luminance')

    h, w = rgba.shape[:2]

    pixel_mask = None
    if s.get('mask_enabled', False):
        pixel_mask = (
            precomputed_mask if precomputed_mask is not None
            else compute_mask(rgba, s)
        )

    if palette_name == 'Braille':
        dot_w = cols * 2
        dot_h = grid_rows(w, h, dot_w, font_aspect=1.0)
        gray, _ = prepare_gray(rgba, dot_w, dot_h, contrast)
        chars = map_braille(gray, invert=invert)
    else:
        gray, gray_soft = prepare_gray(rgba, cols, grid_rows(w, h, cols), contrast)

        if palette is None:
            palette = '@%#*+=-:. '

        if mode == 'luminance':
            chars = map_luminance(gray, palette, invert)
        else:
            mag, angle = sobel(gray_soft)
            chars = map_edges(gray, mag, angle, palette, threshold, invert)

    colors: list = []
    if color:
        colors = sample_colors(resize_for_grid(rgba, cols))

    grid_mask = None
    if pixel_mask is not None:
        # Masking happens after char mapping so Sobel never sees an
        # artificial step at the mask boundary (no fake edge ring).
        grid_mask = mask_to_grid(pixel_mask, len(chars[0]), len(chars))
        _apply_cell_mask(chars, grid_mask)
        if colors:
            color_mask = mask_to_grid(pixel_mask, len(colors[0]), len(colors))
            for r, row in enumerate(colors):
                for c in range(len(row)):
                    if color_mask[r][c]:
                        row[c] = [0, 0, 0]

    return chars, colors, grid_mask


# ---------------------------------------------------------------------------
# Frame diffing
# ---------------------------------------------------------------------------

def diff_grids(
    prev_chars: list[list[str]],
    cur_chars: list[list[str]],
    prev_colors: list | None = None,
    cur_colors: list | None = None,
) -> set:
    """Cells of cur that differ from prev (char or sampled color).
    Cells outside the overlap of differently sized grids count as changed."""
    changed: set = set()
    prev_rows = len(prev_chars)
    cur_rows = len(cur_chars)
    for r in range(cur_rows):
        cur_row = cur_chars[r]
        if r >= prev_rows:
            changed.update((r, c) for c in range(len(cur_row)))
            continue
        prev_row = prev_chars[r]
        for c in range(len(cur_row)):
            if c >= len(prev_row) or cur_row[c] != prev_row[c]:
                changed.add((r, c))
                continue
            if (
                prev_colors and cur_colors
                and r < len(prev_colors) and r < len(cur_colors)
                and c < len(prev_colors[r]) and c < len(cur_colors[r])
                and list(prev_colors[r][c]) != list(cur_colors[r][c])
            ):
                changed.add((r, c))
    return changed


# ---------------------------------------------------------------------------
# Demo image generators  (all vectorised with NumPy)
# ---------------------------------------------------------------------------

def demo_sphere(size: int = 512) -> np.ndarray:
    cx = cy = size // 2
    radius = size // 2 - 20
    x = np.arange(size, dtype=np.float32)
    y = np.arange(size, dtype=np.float32)
    xx, yy = np.meshgrid(x, y)
    dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    mask = dist < radius
    brightness = np.zeros((size, size), dtype=np.float32)
    brightness[mask] = 255.0 * (1.0 - dist[mask] / radius) ** 0.6
    hdx = xx - (cx - radius * 0.3)
    hdy = yy - (cy - radius * 0.3)
    hi_mask = mask & ((hdx ** 2 + hdy ** 2) < (radius * 0.25) ** 2)
    brightness[hi_mask] = np.minimum(255.0, brightness[hi_mask] + 80.0)
    b = brightness.astype(np.uint8)
    alpha = (mask * 255).astype(np.uint8)
    out = np.zeros((size, size, 4), dtype=np.uint8)
    out[:, :, 0] = b
    out[:, :, 1] = b
    out[:, :, 2] = b
    out[:, :, 3] = 255
    return out


def demo_wave(size: int = 512) -> np.ndarray:
    img = Image.new("RGB", (size, size), "black")
    draw = ImageDraw.Draw(img)
    for freq in [1, 2, 3, 5]:
        pts = [
            (x, int(size / 2 + size / 3 * math.sin(2 * math.pi * freq * x / size + freq)))
            for x in range(size)
        ]
        draw.line(pts, fill=(255 // freq, 255 // freq, 255 // freq), width=2)
    return np.array(img.convert("RGBA"))


def demo_portrait(size: int = 512) -> np.ndarray:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 255))
    draw = ImageDraw.Draw(img)
    cx, cy = size // 2, size // 2
    r = size // 3
    fg = (200, 200, 200, 255)
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=fg, width=3)
    ey = cy - r // 4
    for ex in [cx - r // 3, cx + r // 3]:
        ew, eh = r // 8, r // 12
        draw.ellipse([ex - ew, ey - eh, ex + ew, ey + eh], outline=fg, width=2)
        draw.ellipse([ex - ew // 2, ey - eh // 2, ex + ew // 2, ey + eh // 2], fill=fg)
    nose = [(cx, cy - r // 8), (cx - r // 10, cy + r // 6), (cx + r // 10, cy + r // 6)]
    draw.line(nose, fill=(180, 180, 180, 255), width=2)
    mouth_pts = [
        (cx - r // 4 + i, cy + r // 3 + int(r // 14 * (1 - ((i - r // 4) / (r // 4 + 1)) ** 2)))
        for i in range(r // 2 + 1)
    ]
    if len(mouth_pts) > 1:
        draw.line(mouth_pts, fill=fg, width=2)
    for ex in [cx - r // 3, cx + r // 3]:
        brow_y = ey - r // 5
        draw.line([(ex - r // 8, brow_y + r // 20), (ex + r // 8, brow_y - r // 20)], fill=fg, width=2)
    return np.array(img)


def demo_gradient(size: int = 512) -> np.ndarray:
    nx, ny = np.meshgrid(np.linspace(0, 1, size), np.linspace(0, 1, size))
    v3 = 0.5 + 0.5 * np.sin(np.pi * (nx + ny) * 3)
    r = np.clip(nx * 200 + 55, 0, 255).astype(np.uint8)
    g = np.clip(ny * 180 + 30, 0, 255).astype(np.uint8)
    b = np.clip(v3 * 220 + 35, 0, 255).astype(np.uint8)
    alpha = np.full((size, size), 255, dtype=np.uint8)
    return np.stack([r, g, b, alpha], axis=-1)
