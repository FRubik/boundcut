"""Ponto de entrada: QApplication, ícone e checagem do ffmpeg."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from PyQt6.QtGui import (
    QIcon,
)
from PyQt6.QtWidgets import (
    QApplication,
    QMessageBox,
)

from boundcut.janela import MainWindow

# o ícone vai dentro do pacote: serve rodando do repositório e instalado (pip/uv/pipx/.exe)
ICON_PATH = Path(__file__).resolve().parent / "assets" / "icone.svg"


def main():
    missing = [b for b in ("ffmpeg", "ffprobe") if not shutil.which(b)]
    app = QApplication(sys.argv)
    app.setApplicationName("BoundCut")
    app.setDesktopFileName("boundcut")  # no Wayland o ícone da barra vem do .desktop
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
