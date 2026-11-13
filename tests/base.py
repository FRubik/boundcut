"""Utilitários compartilhados pelos testes."""

from __future__ import annotations

import re
import shutil
import subprocess
import unittest
from pathlib import Path

from PyQt6.QtWidgets import QApplication

TEM_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
precisa_ffmpeg = unittest.skipUnless(TEM_FFMPEG, "ffmpeg/ffprobe não encontrados no PATH")


_APP: QApplication | None = None


def app() -> QApplication:
    # a referência precisa ficar viva: um QApplication coletado derruba o processo
    global _APP
    if _APP is None:
        _APP = QApplication.instance() or QApplication([])
    return _APP


def gerar_video(
    destino: Path, *, fps: int = 30, segundos: float = 10, vcodec: str = "libx264", acodec: str | None = "aac"
) -> Path:
    """Gera um vídeo sintético (testsrc2 tem contador e cores que mudam a cada frame)."""
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"testsrc2=size=320x180:rate={fps}",
    ]
    if acodec:
        cmd += ["-f", "lavfi", "-i", "sine=frequency=440"]
    cmd += ["-t", str(segundos), "-c:v", vcodec, "-pix_fmt", "yuv420p"]
    cmd += ["-c:a", acodec] if acodec else []
    subprocess.run(cmd + [str(destino)], check=True)
    return destino


def contar_frames(video: Path) -> int:
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-count_frames",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=nb_read_frames",
            "-of",
            "csv=p=0",
            str(video),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return int(out.strip().strip(","))


def codec_video(video: Path) -> str:
    return subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name",
            "-of",
            "csv=p=0",
            str(video),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def extrair_frame(video: Path, indice: int, destino: Path) -> Path:
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-i",
            str(video),
            "-vf",
            f"select=eq(n\\,{indice})",
            "-frames:v",
            "1",
            str(destino),
        ],
        check=True,
    )
    return destino


def psnr(a: Path, b: Path) -> float:
    """PSNR médio entre duas imagens; 'inf' se forem idênticas."""
    err = subprocess.run(
        ["ffmpeg", "-i", str(a), "-i", str(b), "-lavfi", "psnr", "-f", "null", "-"],
        capture_output=True,
        text=True,
    ).stderr
    m = re.search(r"average:(\S+)", err)
    assert m, err
    return float(m.group(1))
