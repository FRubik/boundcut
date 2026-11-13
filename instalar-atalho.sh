#!/usr/bin/env bash
# Cria o atalho do BoundCut no menu de aplicativos (Linux) e instala o ícone.
# Uso: ./instalar-atalho.sh            (instala)
#      ./instalar-atalho.sh --remover  (desfaz)
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ICONES="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps"

# atalhos dos nomes antigos (get_frame, depois EndFrame), de antes de o programa virar BoundCut
for antigo in get_frame endframe; do
    rm -f "$APPS/$antigo.desktop" "$ICONES/$antigo.svg"
done

if [ "${1:-}" = "--remover" ]; then
    rm -f "$APPS/boundcut.desktop" "$ICONES/boundcut.svg"
    echo "atalho removido."
    exit 0
fi

mkdir -p "$APPS" "$ICONES"
cp "$RAIZ/boundcut/assets/icone.svg" "$ICONES/boundcut.svg"
cat > "$APPS/boundcut.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=BoundCut
Comment=Cortar vídeo e salvar o último frame
Exec=python3 -m boundcut %f
Path=$RAIZ
Icon=boundcut
Terminal=false
Categories=AudioVideo;Video;AudioVideoEditing;
MimeType=video/mp4;video/quicktime;video/x-matroska;video/webm;video/x-msvideo;video/mpeg;
StartupWMClass=boundcut
DESKTOP
command -v update-desktop-database >/dev/null && update-desktop-database "$APPS" >/dev/null 2>&1 || true
echo "atalho instalado: $APPS/boundcut.desktop"
