"""BoundCut — editor simples para cortar um vídeo e salvar o primeiro e/ou o último frame do corte.

Fluxo: abrir vídeo → marcar início/fim → exportar.
A exportação mantém o formato original (mesmo container e, quando possível,
o mesmo codec de vídeo) e grava ao lado um PNG com o primeiro e/ou o último frame do corte.

Requisitos: Python 3.10+, PyQt6 (com QtMultimedia) e ffmpeg/ffprobe no PATH.

Módulos: midia (ffprobe/ffmpeg, sem Qt) · exportacao (thread do corte) ·
timeline (linha do tempo) · janela (janela principal) · app (main).
"""

__version__ = "0.2.0"
