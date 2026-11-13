#!/usr/bin/env python3
"""Regenera os prints do README (assets/prints/) a partir do programa de verdade.

Uso, da raiz do projeto:  python scripts/gerar_prints.py

Roda sem abrir janela (QT_QPA_PLATFORM=offscreen) com um vídeo sintético gerado
pelo ffmpeg. Nesse modo o Qt não desenha o vídeo dentro do QVideoWidget, então a
área do vídeo recebe o frame real daquela posição, extraído com o ffmpeg; o
resto da janela e o diálogo de exportação são os do programa.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from PyQt6.QtCore import Qt, QTimer  # noqa: E402
from PyQt6.QtGui import QPixmap  # noqa: E402
from PyQt6.QtWidgets import QApplication, QLabel  # noqa: E402

import boundcut as g  # noqa: E402

SAIDA = RAIZ / "assets" / "prints"
IN_MS, OUT_MS = 1500, 6000


def ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


def main() -> int:
    app = QApplication([])
    app.setStyle("Fusion")
    SAIDA.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="boundcut-") as tmp:
        tmp = Path(tmp)
        video = tmp / "exemplo.mp4"
        ffmpeg(
            "-f",
            "lavfi",
            "-i",
            "mandelbrot=size=1280x720:rate=30",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=330",
            "-t",
            "8",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(video),
        )

        w = g.MainWindow()
        w.resize(1100, 720)
        w.show()
        w.load(video)
        w._set_in(IN_MS, sync=True)
        w._set_out(OUT_MS, sync=True)
        w.seek(OUT_MS)

        # área do vídeo: frame real da posição atual
        frame = tmp / "frame.png"
        idx = w.frame_index(OUT_MS)
        ffmpeg("-i", str(video), "-vf", f"select=eq(n\\,{idx})", "-frames:v", "1", str(frame))
        tela = QLabel()
        tela.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tela.setStyleSheet("background:#000;")
        w.stack.addWidget(tela)
        w.stack.setCurrentWidget(tela)
        app.processEvents()
        tela.setPixmap(
            QPixmap(str(frame)).scaled(
                tela.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
        )
        app.processEvents()
        w.grab().save(str(SAIDA / "janela.png"))

        # exportação real e o diálogo de conclusão do próprio programa
        start, dur = w._cut_seconds()
        out = tmp / "exemplo_corte.mp4"
        res = []
        worker = g.ExportWorker(w.info, start, dur, out, precise=True, frames=("primeiro", "ultimo"))
        worker.done.connect(lambda *a: res.append(a))
        worker.run()
        ok, msg, vpath, fpaths = res[0]
        if not ok:
            print(msg, file=sys.stderr)
            return 1

        def capturar_dialogo():
            d = app.activeModalWidget()
            d.grab().save(str(SAIDA / "exportado.png"))
            d.done(0)  # close() é ignorado pelo QMessageBox

        QTimer.singleShot(300, capturar_dialogo)
        w._export_done(ok, msg, vpath, fpaths)
        w.close()

    for f in sorted(SAIDA.glob("*.png")):
        print(f.relative_to(RAIZ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
