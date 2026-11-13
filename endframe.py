#!/usr/bin/env python3
"""EndFrame — editor simples para cortar um vídeo e salvar o último frame do corte.

Fluxo: abrir vídeo → marcar início/fim → exportar.
A exportação mantém o formato original (mesmo container e, quando possível,
o mesmo codec de vídeo) e grava ao lado um PNG com o último frame do corte.

Requisitos: Python 3.10+, PyQt6 (com QtMultimedia) e ffmpeg/ffprobe no PATH.
"""

from __future__ import annotations

__version__ = "0.1.0"

import json
import math
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF, Qt, QThread, QUrl, pyqtSignal
from PyQt6.QtGui import (
    QAction,
    QColor,
    QDesktopServices,
    QIcon,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QPixmap,
)
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".mpg", ".mpeg", ".ts", ".wmv", ".flv"}

_AQUI = Path(__file__).resolve().parent
# rodando do repositório: assets/icone.svg; instalado (pip/uv/pipx): endframe_icone.svg ao lado do módulo
ICON_PATH = next(
    (p for p in (_AQUI / "assets" / "icone.svg", _AQUI / "endframe_icone.svg") if p.exists()),
    _AQUI / "assets" / "icone.svg",
)

ACCENT = QColor("#4f9dff")
IN_COLOR = QColor("#3ecf8e")
OUT_COLOR = QColor("#ff6b6b")


# --------------------------------------------------------------------------- #
# ffprobe / ffmpeg
# --------------------------------------------------------------------------- #
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
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True,
        text=True,
        check=True,
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


def fmt_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int(seconds % 3600 // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}" if h else f"{m:02d}:{s:06.3f}"


# --------------------------------------------------------------------------- #
# Exportação em thread separada
# --------------------------------------------------------------------------- #
class ExportWorker(QThread):
    progress = pyqtSignal(int)  # 0–100
    status = pyqtSignal(str)
    done = pyqtSignal(bool, str, str, str)  # ok, mensagem, caminho do vídeo, caminho do frame

    def __init__(
        self, info: VideoInfo, start: float, duration: float, out_path: Path, precise: bool, save_frame: bool
    ):
        super().__init__()
        self.info, self.start_s, self.duration = info, start, duration
        self.out_path, self.precise, self.save_frame = out_path, precise, save_frame
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
                    self.done.emit(False, "Exportação cancelada.", "", "")
                    return
                if code == 0:
                    break
            else:
                self.out_path.unlink(missing_ok=True)
                self.done.emit(False, f"O ffmpeg falhou:\n\n{err.strip()[-2000:]}", "", "")
                return

            frame_path = ""
            if self.save_frame:
                self.status.emit("Salvando o último frame…")
                fp = self.out_path.with_name(self.out_path.stem + "_ultimo_frame.png")
                # Decodifica os últimos segundos do arquivo exportado e mantém só o último frame.
                r = subprocess.run(
                    [
                        "ffmpeg",
                        "-hide_banner",
                        "-y",
                        "-loglevel",
                        "error",
                        "-sseof",
                        "-3",
                        "-i",
                        str(self.out_path),
                        "-map",
                        "0:v:0",
                        "-update",
                        "1",
                        str(fp),
                    ],
                    capture_output=True,
                    text=True,
                )
                if r.returncode != 0 or not fp.exists():
                    self.progress.emit(100)
                    self.done.emit(
                        True,
                        f"Vídeo exportado, mas falhou ao salvar o frame:\n{r.stderr[-1000:]}",
                        str(self.out_path),
                        "",
                    )
                    return
                frame_path = str(fp)

            self.progress.emit(100)
            self.done.emit(True, "Exportação concluída.", str(self.out_path), frame_path)
        except Exception as e:  # noqa: BLE001
            self.done.emit(False, f"Erro inesperado: {e}", "", "")


# --------------------------------------------------------------------------- #
# Linha do tempo com marcadores de início/fim arrastáveis
# --------------------------------------------------------------------------- #
class Timeline(QWidget):
    seekRequested = pyqtSignal(int)  # ms
    inChanged = pyqtSignal(int)
    outChanged = pyqtSignal(int)

    PAD = 12
    HANDLE_HIT = 8

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(54)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.duration = 0
        self.position = 0
        self.in_ms = 0
        self.out_ms = 0
        self._drag: str | None = None  # "in" | "out" | "seek"

    def set_duration(self, ms: int):
        self.duration, self.position, self.in_ms, self.out_ms = ms, 0, 0, ms
        self.update()

    def set_position(self, ms: int):
        self.position = ms
        self.update()

    def set_range(self, in_ms: int, out_ms: int):
        self.in_ms, self.out_ms = in_ms, out_ms
        self.update()

    # conversões
    def _track(self) -> QRectF:
        return QRectF(self.PAD, 14, self.width() - 2 * self.PAD, self.height() - 28)

    def _x(self, ms: int) -> float:
        t = self._track()
        return t.left() + (ms / self.duration * t.width() if self.duration else 0)

    def _ms(self, x: float) -> int:
        t = self._track()
        if not self.duration or t.width() <= 0:
            return 0
        return int(round(min(max((x - t.left()) / t.width(), 0), 1) * self.duration))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = self.palette()
        t = self._track()

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(pal.color(QPalette.ColorRole.Base))
        p.drawRoundedRect(t, 6, 6)

        if not self.duration:
            p.setPen(pal.color(QPalette.ColorRole.PlaceholderText))
            p.drawText(t, Qt.AlignmentFlag.AlignCenter, "Nenhum vídeo carregado")
            return

        # trecho selecionado
        xi, xo = self._x(self.in_ms), self._x(self.out_ms)
        sel = QRectF(xi, t.top(), max(1.0, xo - xi), t.height())
        fill = QColor(ACCENT)
        fill.setAlpha(70)
        p.setBrush(fill)
        p.drawRect(sel)
        p.setPen(QPen(ACCENT, 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(sel)

        # marcadores (colchetes)
        for x, color, left in ((xi, IN_COLOR, True), (xo, OUT_COLOR, False)):
            p.setPen(QPen(color, 3))
            d = 6 if left else -6
            path = QPainterPath(QPointF(x + d, t.top() - 4))
            path.lineTo(x, t.top() - 4)
            path.lineTo(x, t.bottom() + 4)
            path.lineTo(x + d, t.bottom() + 4)
            p.drawPath(path)

        # cursor de reprodução
        xp = self._x(self.position)
        p.setPen(QPen(pal.color(QPalette.ColorRole.Text), 2))
        p.drawLine(QPointF(xp, t.top() - 8), QPointF(xp, t.bottom() + 8))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(pal.color(QPalette.ColorRole.Text))
        tri = QPainterPath(QPointF(xp - 6, 2))
        tri.lineTo(xp + 6, 2)
        tri.lineTo(xp, 10)
        tri.closeSubpath()
        p.drawPath(tri)

    def _hit(self, x: float) -> str:
        if self.duration:
            if abs(x - self._x(self.out_ms)) <= self.HANDLE_HIT:
                return "out"
            if abs(x - self._x(self.in_ms)) <= self.HANDLE_HIT:
                return "in"
        return "seek"

    def mousePressEvent(self, e):
        if not self.duration or e.button() != Qt.MouseButton.LeftButton:
            return
        self._drag = self._hit(e.position().x())
        self.mouseMoveEvent(e)

    def mouseMoveEvent(self, e):
        x = e.position().x()
        if self._drag is None:
            self.setCursor(
                Qt.CursorShape.SizeHorCursor if self._hit(x) != "seek" else Qt.CursorShape.PointingHandCursor
            )
            return
        ms = self._ms(x)
        if self._drag == "in":
            self.in_ms = min(ms, self.out_ms)
            self.inChanged.emit(self.in_ms)
            self.seekRequested.emit(self.in_ms)
        elif self._drag == "out":
            self.out_ms = max(ms, self.in_ms)
            self.outChanged.emit(self.out_ms)
            self.seekRequested.emit(self.out_ms)
        else:
            self.seekRequested.emit(ms)
        self.update()

    def mouseReleaseEvent(self, _):
        self._drag = None


# --------------------------------------------------------------------------- #
# Janela principal
# --------------------------------------------------------------------------- #
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("EndFrame — cortar vídeo e salvar último frame")
        self.resize(1100, 760)
        self.setAcceptDrops(True)

        self.info: VideoInfo | None = None
        self.worker: ExportWorker | None = None
        self.in_ms = 0
        self.out_ms = 0

        # player
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.video = QVideoWidget()
        self.video.setStyleSheet("background:#000;")
        self.player.setVideoOutput(self.video)
        self.player.positionChanged.connect(self._on_position)
        self.player.playbackStateChanged.connect(self._on_state)
        self.player.errorOccurred.connect(
            lambda _e, msg: self.statusBar().showMessage(f"Erro no player: {msg}")
        )

        placeholder = QLabel("Arraste um vídeo para cá\nou clique em “Abrir vídeo” (Ctrl+O)")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setStyleSheet("font-size:18px; color:#888; border:2px dashed #555; border-radius:12px;")
        self.stack = QStackedWidget()
        self.stack.addWidget(placeholder)
        self.stack.addWidget(self.video)

        # topo
        self.btn_open = QPushButton("📂  Abrir vídeo")
        self.btn_open.clicked.connect(self.open_dialog)
        self.lbl_file = QLabel("")
        self.lbl_file.setStyleSheet("color:#aaa;")
        top = QHBoxLayout()
        top.addWidget(self.btn_open)
        top.addWidget(self.lbl_file, 1)

        # linha do tempo
        self.timeline = Timeline()
        self.timeline.seekRequested.connect(self.seek)
        self.timeline.inChanged.connect(self._set_in)
        self.timeline.outChanged.connect(self._set_out)

        # transporte
        def btn(text, tip, slot):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            b.setFixedWidth(46)
            return b

        self.btn_play = btn("▶", "Reproduzir / pausar (Espaço)", self.toggle_play)
        transport = QHBoxLayout()
        transport.addWidget(btn("⏮", "Ir para o início do corte (Home)", lambda: self.seek(self.in_ms)))
        transport.addWidget(btn("−1s", "Voltar 1 segundo (Shift+←)", lambda: self.step_seconds(-1)))
        transport.addWidget(btn("◀|", "Frame anterior (←)", lambda: self.step_frames(-1)))
        transport.addWidget(self.btn_play)
        transport.addWidget(btn("|▶", "Próximo frame (→)", lambda: self.step_frames(1)))
        transport.addWidget(btn("+1s", "Avançar 1 segundo (Shift+→)", lambda: self.step_seconds(1)))
        transport.addWidget(btn("⏭", "Ir para o fim do corte (End)", lambda: self.seek(self.out_ms)))
        transport.addSpacing(16)
        self.lbl_time = QLabel("00:00.000 / 00:00.000")
        self.lbl_time.setStyleSheet("font-family:monospace; font-size:14px;")
        transport.addWidget(self.lbl_time)
        transport.addStretch(1)

        # marcação do corte
        self.btn_in = QPushButton("[  Marcar início  (I)")
        self.btn_in.setStyleSheet(f"color:{IN_COLOR.name()}; font-weight:bold;")
        self.btn_in.clicked.connect(lambda: self._set_in(self.player.position(), sync=True))
        self.btn_out = QPushButton("Marcar fim / corte  (O)  ]")
        self.btn_out.setStyleSheet(f"color:{OUT_COLOR.name()}; font-weight:bold;")
        self.btn_out.clicked.connect(lambda: self._set_out(self.player.position(), sync=True))
        self.btn_reset = QPushButton("Limpar marcações")
        self.btn_reset.clicked.connect(self.reset_marks)
        self.lbl_range = QLabel("")
        self.lbl_range.setStyleSheet("font-family:monospace;")
        marks = QHBoxLayout()
        marks.addWidget(self.btn_in)
        marks.addWidget(self.btn_out)
        marks.addWidget(self.btn_reset)
        marks.addSpacing(12)
        marks.addWidget(self.lbl_range, 1)

        # exportação
        self.cmb_mode = QComboBox()
        self.cmb_mode.addItem("Preciso (reencoda, corte no frame exato)", True)
        self.cmb_mode.addItem("Rápido (sem reencodar — início/fim podem variar alguns frames)", False)
        self.chk_frame = QCheckBox("Salvar último frame (PNG)")
        self.chk_frame.setChecked(True)
        self.btn_export = QPushButton("💾  Exportar corte  (Ctrl+E)")
        self.btn_export.setStyleSheet(
            f"QPushButton{{background:{ACCENT.name()}; color:white; font-weight:bold; padding:8px 18px;"
            f" border-radius:6px;}} QPushButton:disabled{{background:#555; color:#999;}}"
        )
        self.btn_export.clicked.connect(self.export)
        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.clicked.connect(self.cancel_export)
        self.btn_cancel.hide()
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.hide()
        export = QHBoxLayout()
        export.addWidget(QLabel("Modo:"))
        export.addWidget(self.cmb_mode)
        export.addWidget(self.chk_frame)
        export.addStretch(1)
        export.addWidget(self.progress, 1)
        export.addWidget(self.btn_cancel)
        export.addWidget(self.btn_export)

        root = QVBoxLayout()
        root.addLayout(top)
        root.addWidget(self.stack, 1)
        root.addWidget(self.timeline)
        root.addLayout(transport)
        root.addLayout(marks)
        root.addLayout(export)
        w = QWidget()
        w.setLayout(root)
        self.setCentralWidget(w)

        # botões não roubam o foco do teclado (Espaço/setas ficam para os atalhos)
        for b in w.findChildren(QPushButton):
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._shortcuts()
        self._set_enabled(False)
        self.statusBar().showMessage("Abra um vídeo para começar.")

    # -- atalhos --------------------------------------------------------------
    def _shortcuts(self):
        def add(keys, slot):
            a = QAction(self)
            a.setShortcut(QKeySequence(keys))
            a.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
            a.triggered.connect(slot)
            self.addAction(a)

        add("Ctrl+O", self.open_dialog)
        add("Ctrl+E", self.export)
        add("Space", self.toggle_play)
        add("Left", lambda: self.step_frames(-1))
        add("Right", lambda: self.step_frames(1))
        add("Shift+Left", lambda: self.step_seconds(-1))
        add("Shift+Right", lambda: self.step_seconds(1))
        add("I", lambda: self._set_in(self.player.position(), sync=True))
        add("O", lambda: self._set_out(self.player.position(), sync=True))
        add("Home", lambda: self.seek(self.in_ms))
        add("End", lambda: self.seek(self.out_ms))

    def _set_enabled(self, on: bool):
        for wdg in (
            self.btn_in,
            self.btn_out,
            self.btn_reset,
            self.btn_export,
            self.btn_play,
            self.cmb_mode,
            self.chk_frame,
        ):
            wdg.setEnabled(on)

    # -- abrir ----------------------------------------------------------------
    def open_dialog(self):
        if self.worker:
            return
        exts = " ".join(f"*{e}" for e in sorted(VIDEO_EXTS))
        path, _ = QFileDialog.getOpenFileName(self, "Abrir vídeo", "", f"Vídeos ({exts});;Todos (*)")
        if path:
            self.load(Path(path))

    def load(self, path: Path):
        try:
            info = probe(path)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Não foi possível abrir", f"{path.name}\n\n{e}")
            return
        self.info = info
        self.player.stop()
        self.player.setSource(QUrl.fromLocalFile(str(path)))
        self.stack.setCurrentIndex(1)
        dur = int(info.duration * 1000)
        self.timeline.set_duration(dur)
        self.in_ms, self.out_ms = 0, dur
        self._update_range_label()
        self._set_enabled(True)
        self._on_position(0)
        audio = info.acodec or "sem áudio"
        self.lbl_file.setText(
            f"{path.name}   ·   {info.width}×{info.height}   ·   {info.fps:.3f} fps   ·   "
            f"{info.vcodec} / {audio}   ·   {fmt_time(info.duration)}"
        )
        self.statusBar().showMessage("Posicione o cursor e use I / O para marcar o início e o fim do corte.")
        self.player.pause()  # mostra o primeiro frame

    # drag & drop
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        urls = [u for u in e.mimeData().urls() if u.isLocalFile()]
        if urls and not self.worker:
            self.load(Path(urls[0].toLocalFile()))

    # -- reprodução -----------------------------------------------------------
    @property
    def frame_ms(self) -> float:
        return 1000.0 / (self.info.fps if self.info and self.info.fps else 30.0)

    def frame_index(self, ms: int) -> int:
        # pequena folga para não cair no frame anterior por arredondamento
        return int(math.floor((ms + 0.5) / self.frame_ms))

    def seek(self, ms: int):
        if not self.info:
            return
        ms = int(max(0, min(ms, self.timeline.duration)))
        self.player.setPosition(ms)
        self._on_position(ms)

    def step_frames(self, n: int):
        if not self.info:
            return
        self.player.pause()
        idx = self.frame_index(self.player.position()) + n
        self.seek(int(math.ceil(idx * self.frame_ms)))

    def step_seconds(self, s: float):
        if self.info:
            self.seek(self.player.position() + int(s * 1000))

    def toggle_play(self):
        if not self.info:
            return
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            if self.player.position() >= self.timeline.duration - 50:
                self.seek(self.in_ms)
            self.player.play()

    def _on_state(self, state):
        self.btn_play.setText("⏸" if state == QMediaPlayer.PlaybackState.PlayingState else "▶")

    def _on_position(self, ms: int):
        self.timeline.set_position(ms)
        total = self.info.duration if self.info else 0
        frame = self.frame_index(ms) if self.info else 0
        self.lbl_time.setText(f"{fmt_time(ms / 1000)} / {fmt_time(total)}   ·   frame {frame}")

    # -- marcações ------------------------------------------------------------
    def _set_in(self, ms: int, sync: bool = False):
        if not self.info:
            return
        self.in_ms = min(ms, self.out_ms)
        if sync:
            self.timeline.set_range(self.in_ms, self.out_ms)
        self._update_range_label()

    def _set_out(self, ms: int, sync: bool = False):
        if not self.info:
            return
        self.out_ms = max(ms, self.in_ms)
        if sync:
            self.timeline.set_range(self.in_ms, self.out_ms)
        self._update_range_label()

    def reset_marks(self):
        if self.info:
            self.in_ms, self.out_ms = 0, self.timeline.duration
            self.timeline.set_range(self.in_ms, self.out_ms)
            self._update_range_label()

    def _cut_seconds(self) -> tuple[float, float]:
        """Converte as marcações em (início, duração) em segundos, incluindo o frame do fim."""
        assert self.info
        fps = self.info.fps or 30.0
        i_idx = self.frame_index(self.in_ms)
        o_idx = self.frame_index(self.out_ms)
        start = i_idx / fps
        # +0,5 frame: inclui o frame marcado como fim e exclui o seguinte
        duration = (o_idx - i_idx + 0.5) / fps
        return start, min(duration, max(0.0, self.info.duration - start))

    def _update_range_label(self):
        if not self.info:
            self.lbl_range.setText("")
            return
        n = self.frame_index(self.out_ms) - self.frame_index(self.in_ms) + 1
        self.lbl_range.setText(
            f"Início {fmt_time(self.in_ms / 1000)}  →  Fim {fmt_time(self.out_ms / 1000)}   "
            f"(duração {fmt_time(n / self.info.fps)} · {n} frames)"
        )

    # -- exportação -----------------------------------------------------------
    def _default_out(self) -> Path:
        src = self.info.path
        cand = src.with_name(f"{src.stem}_corte{src.suffix}")
        n = 2
        while cand.exists():
            cand = src.with_name(f"{src.stem}_corte_{n}{src.suffix}")
            n += 1
        return cand

    def export(self):
        if not self.info or self.worker:
            return
        self.player.pause()
        start, dur = self._cut_seconds()
        if dur <= 0:
            QMessageBox.warning(self, "Corte vazio", "O fim do corte precisa estar depois do início.")
            return

        ext = self.info.path.suffix
        path, _ = QFileDialog.getSaveFileName(
            self, "Salvar corte como", str(self._default_out()), f"Mesmo formato (*{ext})"
        )
        if not path:
            return
        out = Path(path)
        if out.suffix.lower() != ext.lower():
            out = out.with_suffix(ext)
        if out.resolve() == self.info.path.resolve():
            QMessageBox.warning(self, "Arquivo inválido", "Escolha um nome diferente do vídeo original.")
            return

        self.worker = ExportWorker(
            self.info,
            start,
            dur,
            out,
            precise=self.cmb_mode.currentData(),
            save_frame=self.chk_frame.isChecked(),
        )
        self.worker.progress.connect(self.progress.setValue)
        self.worker.status.connect(self.statusBar().showMessage)
        self.worker.done.connect(self._export_done)
        self.progress.setValue(0)
        self.progress.show()
        self.btn_cancel.show()
        self._set_enabled(False)
        self.btn_open.setEnabled(False)
        self.statusBar().showMessage(f"Exportando {out.name}…")
        self.worker.start()

    def cancel_export(self):
        if self.worker:
            self.worker.cancel()

    def _export_done(self, ok: bool, msg: str, video_path: str, frame_path: str):
        self.worker = None
        self.progress.hide()
        self.btn_cancel.hide()
        self._set_enabled(True)
        self.btn_open.setEnabled(True)
        self.statusBar().showMessage(msg.splitlines()[0])
        if not ok:
            if "cancelada" not in msg:
                QMessageBox.critical(self, "Falha na exportação", msg)
            return

        box = QMessageBox(self)
        box.setWindowTitle("Pronto!")
        text = f"{msg}\n\nVídeo: {video_path}"
        if frame_path:
            text += f"\nÚltimo frame: {frame_path}"
            pix = QPixmap(frame_path)
            if not pix.isNull():
                box.setIconPixmap(
                    pix.scaled(
                        260,
                        260,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
        box.setText(text)
        open_btn = box.addButton("Abrir pasta", QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Ok)
        box.exec()
        if box.clickedButton() is open_btn:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(video_path).parent)))

    def closeEvent(self, e):
        if self.worker:
            self.worker.cancel()
            self.worker.wait(3000)
        super().closeEvent(e)


def main():
    missing = [b for b in ("ffmpeg", "ffprobe") if not shutil.which(b)]
    app = QApplication(sys.argv)
    app.setApplicationName("EndFrame")
    app.setDesktopFileName("endframe")  # no Wayland o ícone da barra vem do .desktop
    if ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(ICON_PATH)))
    app.setStyle("Fusion")
    if missing:
        QMessageBox.critical(
            None,
            "ffmpeg não encontrado",
            f"Instale o ffmpeg (faltando: {', '.join(missing)}) e tente de novo.",
        )
        return 1
    win = MainWindow()
    win.show()
    if len(sys.argv) > 1:
        win.load(Path(sys.argv[1]))
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
