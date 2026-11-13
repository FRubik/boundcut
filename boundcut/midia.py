"""ffprobe/ffmpeg: leitura do vídeo e montagem dos comandos. Não depende do Qt."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# executáveis do ffmpeg: pelo nome (vêm do PATH) ou, no .exe do Windows, pelo caminho completo da
# cópia embutida — assim as DLLs dela não se misturam com as que o Qt usa para tocar o vídeo
BIN = {"ffmpeg": "ffmpeg", "ffprobe": "ffprobe"}

# um programa sem console (o .exe) abriria uma janela preta a cada chamada do ffmpeg; e no Windows a
# saída não viria em UTF-8 (nomes de arquivo com acento quebrariam o JSON do ffprobe)
SUBPROCESS_KW: dict = {"encoding": "utf-8", "errors": "replace"}
if sys.platform == "win32":
    SUBPROCESS_KW["creationflags"] = subprocess.CREATE_NO_WINDOW


def usar_ffmpeg_de(pasta: Path) -> bool:
    """Passa a usar o ffmpeg/ffprobe de `pasta`, se os dois estiverem lá."""
    exe = ".exe" if sys.platform == "win32" else ""
    caminhos = {nome: pasta / f"{nome}{exe}" for nome in BIN}
    if not all(p.is_file() for p in caminhos.values()):
        return False
    BIN.update({nome: str(p) for nome, p in caminhos.items()})
    return True


def ffmpeg_faltando() -> list[str]:
    return [nome for nome, b in BIN.items() if not shutil.which(b)]


VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".mpg", ".mpeg", ".ts", ".wmv", ".flv"}


@dataclass
class VideoInfo:
    path: Path
    duration: float  # segundos
    fps: float
    vcodec: str
    pix_fmt: str
    acodec: str | None
    width: int
    height: int


def _parse_rate(rate: str | None) -> float:
    if not rate or rate in ("0/0", "0"):
        return 0.0
    if "/" in rate:
        num, den = rate.split("/", 1)
        try:
            return float(num) / float(den) if float(den) else 0.0
        except ValueError:
            return 0.0
    try:
        return float(rate)
    except ValueError:
        return 0.0


def probe(path: Path) -> VideoInfo:
    out = subprocess.run(
        [BIN["ffprobe"], "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True,
        check=True,
        **SUBPROCESS_KW,
    ).stdout
    data = json.loads(out)
    v = next(
        (
            s
            for s in data.get("streams", [])
            if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")
        ),
        None,
    )
    if v is None:
        raise ValueError("O arquivo não tem faixa de vídeo.")
    a = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
    fps = _parse_rate(v.get("avg_frame_rate")) or _parse_rate(v.get("r_frame_rate")) or 30.0
    duration = float(data.get("format", {}).get("duration") or v.get("duration") or 0)
    return VideoInfo(
        path=path,
        duration=duration,
        fps=fps,
        vcodec=v.get("codec_name", ""),
        pix_fmt=v.get("pix_fmt", ""),
        acodec=a.get("codec_name") if a else None,
        width=int(v.get("width", 0)),
        height=int(v.get("height", 0)),
    )


def video_encoder_args(info: VideoInfo, ext: str) -> list[str]:
    """Escolhe um encoder que produza o mesmo codec do original, com alta qualidade."""
    c = info.vcodec
    if c == "h264":
        return ["-c:v", "libx264", "-crf", "18", "-preset", "medium"]
    if c == "hevc":
        args = ["-c:v", "libx265", "-crf", "20", "-preset", "medium", "-x265-params", "log-level=error"]
        if ext in (".mp4", ".mov", ".m4v"):
            args += ["-tag:v", "hvc1"]
        return args
    if c == "vp9":
        return ["-c:v", "libvpx-vp9", "-crf", "30", "-b:v", "0", "-row-mt", "1"]
    if c == "vp8":
        return ["-c:v", "libvpx", "-crf", "10", "-b:v", "4M"]
    if c == "av1":
        return ["-c:v", "libsvtav1", "-crf", "30", "-preset", "8"]
    if c == "mpeg4":
        return ["-c:v", "mpeg4", "-q:v", "2"]
    if c == "prores":
        return ["-c:v", "prores_ks", "-profile:v", "3"]
    # Codec sem mapeamento: usa um padrão compatível com o container.
    if ext == ".webm":
        return ["-c:v", "libvpx-vp9", "-crf", "30", "-b:v", "0", "-row-mt", "1"]
    return ["-c:v", "libx264", "-crf", "18", "-preset", "medium"]


def audio_fallback_args(ext: str) -> list[str]:
    if ext in (".webm", ".mkv"):
        return ["-c:a", "libopus", "-b:a", "160k"]
    return ["-c:a", "aac", "-b:a", "192k"]


# frames que podem ser salvos junto com o corte, na ordem em que aparecem
FRAMES = {"primeiro": "Primeiro frame", "ultimo": "Último frame"}


def frame_png(out_path: Path, qual: str) -> Path:
    """Caminho do PNG de um frame do corte: video_corte.mp4 → video_corte_ultimo_frame.png."""
    return out_path.with_name(f"{out_path.stem}_{qual}_frame.png")


def frame_cmd(video: Path, qual: str, png: Path) -> list[str]:
    """Comando do ffmpeg que grava o primeiro ou o último frame de `video` em `png`."""
    if qual == "primeiro":
        entrada, saida = ["-i", str(video)], ["-frames:v", "1"]
    elif qual == "ultimo":
        # decodifica só os últimos segundos e vai sobrescrevendo: fica o último frame
        entrada, saida = ["-sseof", "-3", "-i", str(video)], ["-update", "1"]
    else:
        raise ValueError(f"frame desconhecido: {qual}")
    return [
        BIN["ffmpeg"],
        "-hide_banner",
        "-y",
        "-loglevel",
        "error",
        *entrada,
        "-map",
        "0:v:0",
        *saida,
        str(png),
    ]


def fmt_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int(seconds % 3600 // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}" if h else f"{m:02d}:{s:06.3f}"
