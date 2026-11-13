"""Exportação do corte numa thread separada (QThread), com progresso."""

from __future__ import annotations

import subprocess
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from boundcut.midia import FRAMES, VideoInfo, audio_fallback_args, frame_cmd, frame_png, video_encoder_args


class ExportWorker(QThread):
    progress = pyqtSignal(int)  # 0–100
    status = pyqtSignal(str)
    done = pyqtSignal(bool, str, str, list)  # ok, mensagem, caminho do vídeo, PNGs salvos

    def __init__(
        self,
        info: VideoInfo,
        start: float,
        duration: float,
        out_path: Path,
        precise: bool,
        frames: tuple[str, ...] = ("ultimo",),
    ):
        super().__init__()
        self.info, self.start_s, self.duration = info, start, duration
        self.out_path, self.precise = out_path, precise
        self.frames = tuple(q for q in FRAMES if q in frames)  # ordem fixa: primeiro, último
        self._proc: subprocess.Popen | None = None
        self._cancelled = False

    def cancel(self):
        self._cancelled = True
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()

    # -- ffmpeg com barra de progresso --------------------------------------
    def _run(self, cmd: list[str], total: float) -> tuple[int, str]:
        # o "with" fecha os pipes ao terminar, inclusive se a exportação for cancelada
        with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as proc:
            self._proc = proc
            assert proc.stdout and proc.stderr
            for line in proc.stdout:
                if line.startswith("out_time_us=") and total > 0:
                    try:
                        us = int(line.split("=", 1)[1])
                        self.progress.emit(min(99, int(us / 1e6 / total * 100)))
                    except ValueError:
                        pass
            err = proc.stderr.read()
            return proc.wait(), err

    def _build_cmds(self) -> list[list[str]]:
        ext = self.out_path.suffix.lower()
        base = [
            "ffmpeg",
            "-hide_banner",
            "-y",
            "-nostats",
            "-progress",
            "pipe:1",
            "-loglevel",
            "error",
            "-ss",
            f"{self.start_s:.6f}",
            "-i",
            str(self.info.path),
            "-t",
            f"{self.duration:.6f}",
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-map_metadata",
            "0",
        ]
        tail = ["-movflags", "+faststart"] if ext in (".mp4", ".mov", ".m4v") else []
        tail.append(str(self.out_path))

        if not self.precise:
            return [base + ["-c", "copy", "-avoid_negative_ts", "make_zero"] + tail]

        venc = video_encoder_args(self.info, ext)
        pix = ["-pix_fmt", self.info.pix_fmt] if self.info.pix_fmt else []
        # 1ª tentativa: áudio copiado e pix_fmt original; 2ª: áudio reencodado e pix_fmt padrão.
        return [
            base + venc + pix + ["-c:a", "copy"] + tail,
            base + venc + audio_fallback_args(ext) + tail,
        ]

    def run(self):
        try:
            err = ""
            for i, cmd in enumerate(self._build_cmds()):
                if i:
                    self.status.emit("Ajustando parâmetros e tentando novamente…")
                code, err = self._run(cmd, self.duration)
                if self._cancelled:
                    self.out_path.unlink(missing_ok=True)
                    self.done.emit(False, "Exportação cancelada.", "", [])
                    return
                if code == 0:
                    break
            else:
                self.out_path.unlink(missing_ok=True)
                self.done.emit(False, f"O ffmpeg falhou:\n\n{err.strip()[-2000:]}", "", [])
                return

            salvos: list[str] = []
            for qual in self.frames:
                nome = FRAMES[qual].lower()
                self.status.emit(f"Salvando o {nome}…")
                fp = frame_png(self.out_path, qual)
                r = subprocess.run(frame_cmd(self.out_path, qual, fp), capture_output=True, text=True)
                if r.returncode != 0 or not fp.exists():
                    self.progress.emit(100)
                    self.done.emit(
                        True,
                        f"Vídeo exportado, mas falhou ao salvar o {nome}:\n{r.stderr[-1000:]}",
                        str(self.out_path),
                        salvos,
                    )
                    return
                salvos.append(str(fp))

            self.progress.emit(100)
            self.done.emit(True, "Exportação concluída.", str(self.out_path), salvos)
        except Exception as e:  # noqa: BLE001
            self.done.emit(False, f"Erro inesperado: {e}", "", [])
