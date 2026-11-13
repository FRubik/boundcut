#!/usr/bin/env bash
# Cria o atalho do EndFrame no menu de aplicativos (Linux) e instala o ícone.
# Uso: ./instalar-atalho.sh            (instala)
#      ./instalar-atalho.sh --remover  (desfaz)
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ICONES="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps"

# atalho do nome antigo (get_frame), de antes de o programa virar EndFrame
rm -f "$APPS/get_frame.desktop" "$ICONES/get_frame.svg"

if [ "${1:-}" = "--remover" ]; then
    rm -f "$APPS/endframe.desktop" "$ICONES/endframe.svg"
    echo "atalho removido."
    exit 0
fi

mkdir -p "$APPS" "$ICONES"
cp "$RAIZ/assets/icone.svg" "$ICONES/endframe.svg"
cat > "$APPS/endframe.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=EndFrame
Comment=Cortar vídeo e salvar o último frame
Exec=python3 "$RAIZ/endframe.py" %f
Icon=endframe
Terminal=false
Categories=AudioVideo;Video;AudioVideoEditing;
MimeType=video/mp4;video/quicktime;video/x-matroska;video/webm;video/x-msvideo;video/mpeg;
StartupWMClass=endframe
DESKTOP
command -v update-desktop-database >/dev/null && update-desktop-database "$APPS" >/dev/null 2>&1 || true
echo "atalho instalado: $APPS/endframe.desktop"
