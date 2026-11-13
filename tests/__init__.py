"""Testes do BoundCut. Rodar da raiz do projeto:  python -m unittest -v"""

import os

# Sem janela de verdade: os testes rodam em qualquer máquina, inclusive sem monitor.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
