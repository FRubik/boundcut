<p align="center"><img src="assets/icone-256.png" width="96" alt=""></p>

# get_frame

**English** · [Português](README.pt-BR.md)

A simple video trimmer that, along with the cut, **saves the last frame of the clip** as a PNG.

> The interface is in Brazilian Portuguese.

## Requirements

- Python 3.10+
- PyQt6 with QtMultimedia
- `ffmpeg` and `ffprobe` on the PATH

On Arch: `sudo pacman -S python-pyqt6 qt6-multimedia-ffmpeg ffmpeg`.
Elsewhere: `pip install PyQt6` and install ffmpeg with your package manager.

## Running

```bash
python get_frame.py              # open the window
python get_frame.py video.mp4    # open with a video loaded
./instalar-atalho.sh             # optional (Linux): app menu shortcut with icon
```

## Usage

1. Open a video (button, `Ctrl+O`, or drag the file onto the window).
2. Mark the segment: `I` sets the start, `O` sets the end (the cut point).
   The green/red brackets on the timeline can also be dragged.
3. `Ctrl+E` exports:
   - `name_corte.ext` — same container and codec as the original;
   - `name_corte_ultimo_frame.png` — the last frame of the clip (the frame marked as the end).

| Key | Action |
|---|---|
| Space | play / pause |
| ← / → | previous / next frame |
| Shift + ← / → | −1 s / +1 s |
| Home / End | go to cut start / end |
| I / O | mark start / end |

### Export modes

- **Preciso** (precise, default): re-encodes with the same codec at high quality (h264 → x264 CRF 18,
  hevc → x265, vp9, av1…). Frame-accurate cut. Audio is stream-copied when possible.
- **Rápido** (fast): stream copy, no re-encoding. Instant and lossless, but start/end may be off by
  a few frames (the cut depends on keyframes).

## License

[MIT](LICENSE)
