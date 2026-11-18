"""Autoteste do programa empacotado: `boundcut --verificar relatorio.txt`.

A build do Windows roda isto no próprio .exe: confere que o ffmpeg embutido é o usado, que os
encoders do modo preciso existem, que o ícone carrega e faz uma exportação de verdade.
O .exe não tem console, então o resultado vai para um arquivo e o código de saída diz se passou.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

from PyQt6.QtGui import QIcon

from boundcut.exportacao import ExportWorker
from boundcut.janela import MainWindow
from boundcut.midia import BIN, SUBPROCESS_KW, ffmpeg_faltando, probe

ENCODERS = ("libx264", "libx265", "libvpx-vp9", "libopus", "aac")


def verificar(relatorio: Path, icone: Path) -> int:
    linhas: list[str] = []
    falhas = 0

    def item(nome: str, passou: bool, detalhe: str = "") -> None:
        nonlocal falhas
        falhas += not passou
        linhas.append(f"[{'ok' if passou else 'FALHA'}] {nome}" + (f": {detalhe}" if detalhe else ""))

    try:
        item("ffmpeg e ffprobe", not ffmpeg_faltando(), str(BIN))
        if getattr(sys, "frozen", False):
            item("ffmpeg embutido", all(Path(b).is_absolute() for b in BIN.values()))
        enc = subprocess.run(
            [BIN["ffmpeg"], "-hide_banner", "-encoders"], capture_output=True, **SUBPROCESS_KW
        )
        for e in ENCODERS:
            item(f"encoder {e}", f" {e} " in enc.stdout)
        item("ícone", not QIcon(str(icone)).pixmap(32, 32).isNull(), str(icone))
        MainWindow().close()
        item("janela", True)

        with tempfile.TemporaryDirectory(prefix="boundcut-verificar-", ignore_cleanup_errors=True) as tmp:
            origem, saida = Path(tmp) / "origem.mp4", Path(tmp) / "corte.mp4"
            subprocess.run(
                [BIN["ffmpeg"], "-hide_banner", "-loglevel", "error", "-y"]
                + ["-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30:duration=3"]
                + ["-f", "lavfi", "-i", "sine=duration=3", "-c:v", "libx264", "-c:a", "aac", "-shortest"]
                + [str(origem)],
                check=True,
                capture_output=True,
                **SUBPROCESS_KW,
            )
            res: list[tuple] = []
            w = ExportWorker(probe(origem), 0.5, 1.0, saida, precise=True, frames=("primeiro", "ultimo"))
            w.done.connect(lambda *a: res.append(a))
            w.run()
            ok, msg, _video, pngs = res[0] if res else (False, "sem resposta", "", [])
            item("exportação com os dois frames", ok and saida.exists() and len(pngs) == 2, msg)
    except Exception:  # noqa: BLE001 — tudo vai para o relatório
        item("execução", False, traceback.format_exc())

    linhas.append("RESULTADO: " + ("ok" if not falhas else f"{falhas} falha(s)"))
    relatorio.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return 1 if falhas else 0
