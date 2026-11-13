#!/usr/bin/env bash
# Cria o atalho do get_frame no menu de aplicativos (Linux) e instala o ícone.
# Uso: ./instalar-atalho.sh            (instala)
#      ./instalar-atalho.sh --remover  (desfaz)
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ICONES="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps"

if [ "${1:-}" = "--remover" ]; then
    rm -f "$APPS/get_frame.desktop" "$ICONES/get_frame.svg"
    echo "atalho removido."
    exit 0
fi

mkdir -p "$APPS" "$ICONES"
cp "$RAIZ/assets/icone.svg" "$ICONES/get_frame.svg"
cat > "$APPS/get_frame.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=get_frame
Comment=Cortar vídeo e salvar o último frame
Exec=python3 "$RAIZ/get_frame.py" %f
Icon=get_frame
Terminal=false
Categories=AudioVideo;Video;AudioVideoEditing;
MimeType=video/mp4;video/quicktime;video/x-matroska;video/webm;video/x-msvideo;video/mpeg;
StartupWMClass=get_frame
DESKTOP
command -v update-desktop-database >/dev/null && update-desktop-database "$APPS" >/dev/null 2>&1 || true
echo "atalho instalado: $APPS/get_frame.desktop"
