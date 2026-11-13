"""Janela principal: player, linha do tempo, marcações e exportação."""

from __future__ import annotations

import math
from pathlib import Path

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import (
    QAction,
    QDesktopServices,
    QKeySequence,
    QPainter,
    QPixmap,
)
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtWidgets import (
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

from boundcut.exportacao import ExportWorker
from boundcut.midia import FRAMES, VIDEO_EXTS, VideoInfo, fmt_time, frame_png, probe
from boundcut.timeline import ACCENT, IN_COLOR, OUT_COLOR, Timeline


def previa_frames(paths: list, lado: int = 260) -> QPixmap:
    """Miniaturas dos PNGs lado a lado (primeiro à esquerda), para o diálogo de conclusão."""
    pix = [QPixmap(p) for p in paths]
    pix = [
        p.scaled(
            lado if len(pix) == 1 else lado * 3 // 4,
            lado,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        for p in pix
        if not p.isNull()
    ]
    if len(pix) <= 1:
        return pix[0] if pix else QPixmap()
    gap = 8
    out = QPixmap(sum(p.width() for p in pix) + gap * (len(pix) - 1), max(p.height() for p in pix))
    out.fill(Qt.GlobalColor.transparent)
    with QPainter(out) as painter:
        x = 0
        for p in pix:
            painter.drawPixmap(x, (out.height() - p.height()) // 2, p)
            x += p.width() + gap
    return out


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BoundCut — cortar vídeo e salvar o primeiro e o último frame")
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
        # um checkbox por frame salvo junto com o corte; o último vem marcado
        self.chk_frames = {qual: QCheckBox(f"{rotulo} (PNG)") for qual, rotulo in FRAMES.items()}
        self.chk_frames["ultimo"].setChecked(True)
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
        for chk in self.chk_frames.values():
            export.addWidget(chk)
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
            *self.chk_frames.values(),
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
            frames=self.frames_escolhidos(),
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

    def frames_escolhidos(self) -> tuple[str, ...]:
        return tuple(q for q, chk in self.chk_frames.items() if chk.isChecked())

    def cancel_export(self):
        if self.worker:
            self.worker.cancel()

    def _export_done(self, ok: bool, msg: str, video_path: str, frame_paths: list):
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
        rotulos = {str(frame_png(Path(video_path), q)): r for q, r in FRAMES.items()}
        for fp in frame_paths:
            text += f"\n{rotulos.get(fp, 'Frame')}: {fp}"
        previa = previa_frames(frame_paths)
        if not previa.isNull():
            box.setIconPixmap(previa)
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
        # solta o arquivo: no Windows, vídeo aberto no player não pode ser apagado nem movido
        self.player.stop()
        self.player.setSource(QUrl())
        super().closeEvent(e)
