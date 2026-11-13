<p align="center"><img src="assets/icone-256.png" width="96" alt=""></p>

# get_frame

[English](README.md) · **Português**

Editor simples para **cortar um vídeo** e, junto com o corte, **salvar o último frame** como PNG.

![Janela do get_frame com o trecho marcado na linha do tempo](assets/prints/janela.png)

<p align="center"><img src="assets/prints/exportado.png" width="480" alt="Diálogo de exportação concluída com a prévia do último frame"></p>

## Requisitos

- Python 3.10+
- PyQt6 com QtMultimedia
- `ffmpeg` e `ffprobe` no PATH

No Arch: `sudo pacman -S python-pyqt6 qt6-multimedia-ffmpeg ffmpeg`.
Em outros sistemas: `pip install PyQt6` e instale o ffmpeg pelo gerenciador de pacotes.

## Como rodar

Direto do repositório (usa o PyQt6 já instalado no sistema):

```bash
python get_frame.py              # abre a janela
python get_frame.py video.mp4    # já abre com um vídeo
./instalar-atalho.sh             # opcional (Linux): atalho no menu, com ícone
```

Ou instalado como comando (`get-frame`), num ambiente isolado que já traz o PyQt6:

```bash
uv tool install git+https://github.com/FRubik/get_frame   # ou: pipx install git+https://…
get-frame video.mp4
```

O ffmpeg continua vindo do sistema em qualquer caso.

## Uso

1. Abra um vídeo (botão, `Ctrl+O` ou arrastando o arquivo para a janela).
2. Navegue e marque o trecho: `I` marca o início, `O` marca o fim (o ponto do corte).
   Os colchetes verde/vermelho na linha do tempo também podem ser arrastados.
3. `Ctrl+E` exporta. São gerados:
   - `nome_corte.ext` — no mesmo container e codec do original;
   - `nome_corte_ultimo_frame.png` — o último frame do corte (o frame marcado como fim).

| Tecla | Ação |
|---|---|
| Espaço | reproduzir / pausar |
| ← / → | frame anterior / próximo |
| Shift + ← / → | −1 s / +1 s |
| Home / End | ir ao início / fim do corte |
| I / O | marcar início / fim |

### Modos de exportação

- **Preciso** (padrão): reencoda o vídeo com o mesmo codec em alta qualidade (h264 → x264 CRF 18,
  hevc → x265, vp9, av1…). O corte cai no frame exato. O áudio é copiado quando possível.
- **Rápido**: copia os streams sem reencodar. Instantâneo e sem perda, mas o início/fim
  podem variar alguns frames (o corte depende dos keyframes).

## Testes

```bash
python -m unittest -v    # da raiz do projeto; sem dependências além das do programa
```

- `tests/test_unidade.py` — funções puras e lógica da interface (não precisa do ffmpeg).
- `tests/test_exportacao.py` — ponta a ponta: gera vídeos sintéticos com o ffmpeg, corta e confere
  container, codec, número de frames e se o PNG salvo é mesmo o frame marcado como fim.
  É pulado se o ffmpeg não estiver instalado.

- `tests/test_projeto.py` — `pyproject.toml`, arquivos empacotados e links do README.

A interface roda em modo `offscreen` nos testes, então não abre janela nem precisa de monitor.

Os prints do README são gerados pelo próprio programa: `python scripts/gerar_prints.py`
(rode de novo quando a interface mudar).

## Licença

[MIT](LICENSE)
