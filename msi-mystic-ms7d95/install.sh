#!/usr/bin/env bash
# Instalador de MSI Mystic Light (MS-7D95) para Linux.
# Uso: ./install.sh [--sin-venv] [--sin-escritorio]
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SIN_VENV=0
SIN_ESCRITORIO=0
for arg in "$@"; do
  case "$arg" in
    --sin-venv) SIN_VENV=1 ;;
    --sin-escritorio) SIN_ESCRITORIO=1 ;;
    -h|--help)
      echo "Uso: ./install.sh [--sin-venv] [--sin-escritorio]"; exit 0 ;;
    *) echo "Opcion desconocida: $arg (usa --help)" >&2; exit 1 ;;
  esac
done

echo "== MSI Mystic Light MS-7D95 — instalador =="
echo "Placa detectada: $(cat /sys/class/dmi/id/board_vendor 2>/dev/null) $(cat /sys/class/dmi/id/board_name 2>/dev/null)"
command -v python3 >/dev/null || { echo "ERROR: python3 no encontrado" >&2; exit 1; }

echo "[1/5] Dependencias del sistema..."
if command -v pacman >/dev/null; then
  sudo pacman -S --needed --noconfirm python polkit 2>/dev/null || true
elif command -v apt-get >/dev/null; then
  sudo apt-get update && sudo apt-get install -y python3 python3-venv policykit-1 2>/dev/null || true
elif command -v dnf >/dev/null; then
  sudo dnf install -y python3 polkit 2>/dev/null || true
else
  echo "(gestor no reconocido: instala python3 y polkit a mano si algo falla)"
fi

echo "[2/5] Entorno Python..."
if [[ "$SIN_VENV" == "1" ]]; then
  python3 -c "import PySide6" 2>/dev/null \
    || pip install --user PySide6 \
    || { echo "ERROR: instala PySide6 (pip install PySide6)" >&2; exit 1; }
else
  [[ -d "$DIR/.venv" ]] || python3 -m venv "$DIR/.venv"
  "$DIR/.venv/bin/pip" install --upgrade pip
  "$DIR/.venv/bin/pip" install -r "$DIR/requirements.txt"
fi

echo "[3/5] Permisos..."
chmod +x "$DIR/msi-mystic" "$DIR/msi-mystic-gui-root"

echo "[4/5] Icono..."
mkdir -p ~/.local/share/icons/hicolor/scalable/apps
cp "$DIR/icons/msi-mystic.svg" ~/.local/share/icons/hicolor/scalable/apps/msi-mystic.svg
gtk-update-icon-cache -f -t ~/.local/share/icons/hicolor 2>/dev/null || true

if [[ "$SIN_ESCRITORIO" == "1" ]]; then
  echo "(acceso directo omitido)"
else
  echo "[5/5] Acceso directo + servicio..."
  mkdir -p ~/.local/share/applications ~/.config/systemd/user
  sed "s|@@APP_DIR@@|$DIR|g" "$DIR/msi-mystic.desktop" > ~/.local/share/applications/msi-mystic.desktop
  chmod 644 ~/.local/share/applications/msi-mystic.desktop
  sed "s|@@APP_DIR@@|$DIR|g" "$DIR/msi-mystic.service" > ~/.config/systemd/user/msi-mystic.service
  update-desktop-database ~/.local/share/applications 2>/dev/null || true
  systemctl --user daemon-reload 2>/dev/null || true
  command -v desktop-file-validate >/dev/null \
    && desktop-file-validate ~/.local/share/applications/msi-mystic.desktop \
    && echo "(lanzador validado)"
fi

echo
echo "OK. Prueba en modo seguro (sin root, sin hardware):"
echo "  $DIR/msi-mystic detect --dry-run --verbose"
echo
echo "Uso real (el GUI se eleva solo, no pongas sudo delante):"
echo "  $DIR/msi-mystic detect --dry-run --verbose   # primero esto"
echo "  sudo $DIR/msi-mystic detect --verbose        # deteccion SuperIO"
echo "  sudo $DIR/msi-mystic set --color 00E676"
echo "  $DIR/msi-mystic --gui                        # o buscala como 'Mystic' en el menu"
echo
echo "Restaurar color al arrancar (edita el color en ~/.config/systemd/user/msi-mystic.service):"
echo "  systemctl --user enable --now msi-mystic.service"
