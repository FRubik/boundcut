<p align="center"><img src="assets/icone-256.png" width="96" alt=""></p>

# get_frame

[English](README.md) · **Português**

Editor simples para **cortar um vídeo** e, junto com o corte, **salvar o último frame** como PNG.

## Requisitos

- Python 3.10+
- PyQt6 com QtMultimedia
- `ffmpeg` e `ffprobe` no PATH

No Arch: `sudo pacman -S python-pyqt6 qt6-multimedia-ffmpeg ffmpeg`.
Em outros sistemas: `pip install PyQt6` e instale o ffmpeg pelo gerenciador de pacotes.

## Como rodar

```bash
python get_frame.py              # abre a janela
python get_frame.py video.mp4    # já abre com um vídeo
./instalar-atalho.sh             # opcional (Linux): atalho no menu, com ícone
```

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

A interface roda em modo `offscreen` nos testes, então não abre janela nem precisa de monitor.

## Licença

[MIT](LICENSE)
