# ASCII Converter

A native desktop app that turns images and animated GIFs into ASCII art — with live
preview, color, background masking, brush editing, and a pile of export formats
(including PNG sprite sheets for game engines).

Built with PyQt6, Pillow, and NumPy.

<img width="3412" height="1363" alt="image" src="https://github.com/user-attachments/assets/b01c1f41-29ed-4805-98b7-3915de3017f9" />


## Features

- **Live conversion** — adjust any control and the preview re-renders in the background
  (debounced, off the UI thread) so it stays responsive on large grids.
- **Render modes** — Luminance, Edge (Sobel), and Hybrid.
- **Character sets** — Standard, Extended, Block, Braille (2×4 px Unicode cells),
  Minimal, or your own Custom palette.
- **Color** — sample the source image's colors per cell, or render monochrome.
- **Background mask** — key out a background color (auto-sampled from the corners or
  picked manually, with a tolerance slider) to produce transparent sprites.
- **Paint editing** — brush a foreground color onto cells right in the preview
  (left-drag paints, right-drag erases), with an adjustable brush size.
- **Animated GIF support** — load a GIF and scrub/play it back with a frame strip,
  per-frame timing, and changed-cell diff highlighting.
- **Exports**
  - Static: `.txt`, `.html` (styled, colored), `.png` (RGB or transparent RGBA),
    and copy-to-clipboard.
  - Animation: per-frame folder (`.txt`/`.md`), single annotated `.txt`,
    self-contained animated `.html`, rendered animated `.gif`, and
    **PNG sprite sheets**.

### Sprite sheets

The sprite-sheet export tiles every frame into a single PNG grid of uniform-size cells,
ready to import into a game engine. It honors the background mask (transparent RGBA) and
any paint edits, and after exporting it reports the grid layout and the **per-frame cell
size** in the status bar — that's the value you feed into your engine's frame-slicing
(e.g. Godot's *hframes/vframes*, Aseprite, Unity's Sprite Editor).

> **Tip:** the font-size slider is a point size in the preview but is applied as a pixel
> size to the rendered exports, so exported sprites come out at roughly 75% of the
> preview's apparent size. Bump up the Font Size before exporting if you want
> higher-resolution sprites.

## Requirements

- Python 3.10+
- Dependencies (installed automatically by the run scripts):
  - PyQt6
  - Pillow
  - NumPy
  - opencv-python-headless
- No font installation needed: raster exports (PNG/GIF/sprite sheets) use a bundled
  copy of JuliaMono (`app/fonts/`), which covers ASCII, block elements, and Braille, so
  output is identical on every machine. If the bundled font is missing, the app falls
  back to a system monospace via fontconfig.

## Running

### Linux / macOS

```bash
./run.sh
```

### Windows

```bat
run.bat
```

Both scripts create a `.venv`, install the requirements, and launch the app.

### Manual

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## Usage

1. Drag an image or GIF onto the window (or use **Open image…**, or pick a built-in
   demo: Sphere, Wave, Portrait, Gradient).
2. Tune **Columns**, **Render Mode**, **Character Set**, **Contrast**, and toggle
   **Color** / **Invert** until the preview looks right.
3. Optionally enable **Background Mask** for transparency, or use **Edit (paint)** to
   touch up individual cells.
4. Export with the buttons at the bottom. When a GIF is loaded, the **Animation Export**
   section appears with a frame-range selector and the sprite-sheet option.

### Keyboard shortcuts

| Shortcut       | Action                |
| -------------- | --------------------- |
| `Ctrl+O`       | Open image            |
| `Ctrl+C`       | Copy ASCII text       |
| `Ctrl+S`       | Save `.txt`           |
| `Ctrl+Shift+S` | Save `.png`           |
| `I`            | Toggle invert         |
| `E`            | Cycle render mode     |
| `+` / `-`      | Adjust columns        |
| `Space`        | Play/pause animation  |

## Project layout

```
main.py            App entry point + global stylesheet
app/
  window.py        MainWindow: wiring, loading, conversion orchestration, exports
  controls.py      Left-hand control panel and all settings widgets
  preview.py       AsciiCanvas — custom-painted, hit-testable preview grid
  processor.py     Pure Python/NumPy conversion core (no Qt; testable headlessly)
  worker.py        QThread workers for static and animated conversion
  exporter.py      All export formats (txt/html/png/gif/sprite sheet)
  playback.py      Animation playback bar
  framestrip.py    Thumbnail frame strip
  palettes.py      Character-set definitions
```

The conversion core (`processor.py`) has zero Qt imports and can be tested headlessly;
Qt-dependent code can be exercised with `QT_QPA_PLATFORM=offscreen`.

## License

MIT

The bundled font **JuliaMono** (`app/fonts/JuliaMono-Regular.ttf`) is © cormullion and
licensed under the SIL Open Font License 1.1; the full license is in
`app/fonts/OFL.txt`.
