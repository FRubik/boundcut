"""Ponto de entrada: QApplication, ícone e checagem do ffmpeg."""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMessageBox

from boundcut.janela import MainWindow
from boundcut.midia import ffmpeg_faltando, usar_ffmpeg_de

# o ícone vai dentro do pacote: serve rodando do repositório e instalado (pip/uv/pipx/.exe)
ICON_PATH = Path(__file__).resolve().parent / "assets" / "icone.svg"


def pasta_ffmpeg_embutido() -> Path | None:
    """No .exe (PyInstaller), o ffmpeg vai numa pasta `ffmpeg/` ao lado do executável."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "ffmpeg"
    return None


def main():
    pasta = pasta_ffmpeg_embutido()
    if pasta:
        usar_ffmpeg_de(pasta)
    missing = ffmpeg_faltando()
    app = QApplication(sys.argv)
    app.setApplicationName("BoundCut")
    app.setDesktopFileName("boundcut")  # no Wayland o ícone da barra vem do .desktop
    if ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(ICON_PATH)))
    app.setStyle("Fusion")
    if len(sys.argv) > 2 and sys.argv[1] == "--verificar":
        from boundcut.verificacao import verificar

        return verificar(Path(sys.argv[2]), ICON_PATH)
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
