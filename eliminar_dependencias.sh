#!/usr/bin/env bash
# Desinstala dependencias instaladas por print_scanner_app/installer/install.py
# Uso: ./eliminar_dependencias.sh   (NO usar: sudo ./eliminar_dependencias.sh)

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# Coincide con print_scanner_app/installer/install.py (_APT_REQUIRED + opcional)
APT_PACKAGES=(
    build-essential
    python3-dev
    gphoto2
    libgphoto2-dev
    xclip
    usbutils
    libsdl2-dev
    libsdl2-image-dev
    libsdl2-mixer-dev
    libsdl2-ttf-dev
    libportmidi-dev
    libswscale-dev
    libavformat-dev
    libavcodec-dev
    zlib1g-dev
    entangle
)

# requirements-runtime.txt + legado (psutil no está en runtime)
PIP_PACKAGES=(
    gphoto2
    python-escpos
    kivy
    numpy
    opencv-python
    Pillow
    psutil
)

DESKTOP_NAMES=(
    "Print Scanner.desktop"
    "Thermal Scanner.desktop"
    "print-scanner-app.desktop"
    "thermal-scanner-modular.desktop"
)

UDEV_RULE="/etc/udev/rules.d/99-thermal-scanner-lp.rules"

SKIP_APT=false
SKIP_PIP=false
SKIP_DESKTOP=false
PURGE_BUILD=false

usage() {
    cat <<EOF
Uso: $0 [opciones]

  Desinstala dependencias del instalador print_scanner_app.
  Ejecutar como su usuario normal (sin sudo delante del script).

Opciones:
  --apt-only       Solo paquetes apt
  --pip-only       Solo módulos pip
  --no-desktop     No borrar accesos directos ni udev
  --purge-build    Incluir python3-pip en apt (no recomendado si usa pip en el sistema)
  -h, --help       Esta ayuda
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --apt-only) SKIP_PIP=true; SKIP_DESKTOP=true ;;
        --pip-only) SKIP_APT=true; SKIP_DESKTOP=true ;;
        --no-desktop) SKIP_DESKTOP=true ;;
        --purge-build) PURGE_BUILD=true ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Opción desconocida: $1" >&2; usage; exit 1 ;;
    esac
    shift
done

if [[ "$PURGE_BUILD" == true ]]; then
    APT_PACKAGES+=(python3-pip)
fi

# Si invocaron con sudo ./script, volver al usuario real (pip --user está en su HOME)
if [[ "$(id -u)" -eq 0 ]]; then
    if [[ -n "${SUDO_USER:-}" && "${SUDO_USER}" != "root" ]]; then
        echo -e "${YELLOW}Reejecutando como ${SUDO_USER} (pip debe correr sin ser root).${NC}"
        exec sudo -u "${SUDO_USER}" -H bash "$0" "$@"
    fi
    echo -e "${RED}No ejecute este script como root.${NC}"
    echo "  Correcto: ./eliminar_dependencias.sh"
    echo "  El script pedirá sudo solo para apt/udev."
    exit 1
fi

command_exists() { command -v "$1" >/dev/null 2>&1; }

if command_exists python3; then
    PYTHON_CMD=python3
elif command_exists python; then
    PYTHON_CMD=python
else
    echo -e "${RED}No se encontró Python.${NC}"
    exit 1
fi

pip_supports_break_system() {
    "$PYTHON_CMD" -m pip uninstall --help 2>/dev/null | grep -q -- '--break-system-packages'
}

pip_extra_flags() {
    if pip_supports_break_system; then
        echo --break-system-packages
    fi
}

apt_installed() {
    local pkg=$1
    dpkg-query -W -f='${Status}\n' "$pkg" 2>/dev/null | grep -q '^install ok installed$'
}

pip_installed() {
    local pkg=$1
    "$PYTHON_CMD" -m pip show "$pkg" >/dev/null 2>&1
}

explain_apt_kept() {
    local pkg=$1
    echo -e "    ${YELLOW}Motivo posible:${NC}"
    if apt_installed "$pkg"; then
        local manual
        manual=$(apt-mark showmanual "$pkg" 2>/dev/null || true)
        if [[ -n "$manual" ]]; then
            echo "      • Marcado como instalado manualmente (apt-mark manual)."
            echo "        Para forzar: sudo apt-mark auto $pkg && sudo apt autoremove -y"
        fi
        echo "      • Otros paquetes pueden depender de él:"
        apt-cache rdepends --installed "$pkg" 2>/dev/null | head -8 | sed 's/^/        /' || true
    fi
}

remove_apt_packages() {
    echo ""
    echo "1. Paquetes del sistema (apt)..."
    echo "--------------------------------"
    echo -e "${CYAN}Se pedirá contraseña de sudo si hace falta.${NC}"

    if ! sudo -v; then
        echo -e "${RED}No se pudo obtener sudo. Omitiendo apt.${NC}"
        return 1
    fi

    local to_remove=()
    for package in "${APT_PACKAGES[@]}"; do
        if apt_installed "$package"; then
            to_remove+=("$package")
        else
            echo -e "  $package ${YELLOW}(no instalado — omitido)${NC}"
        fi
    done

    if [[ ${#to_remove[@]} -eq 0 ]]; then
        echo -e "${GREEN}  Ningún paquete apt de la lista estaba instalado.${NC}"
        echo "  (libgphoto2-dev u otros pueden no haberse instalado si el instalador falló en apt.)"
        return 0
    fi

    echo "  Eliminando: ${to_remove[*]}"
    if ! sudo apt-get remove -y "${to_remove[@]}"; then
        echo -e "${YELLOW}  apt remove devolvió error; algunos paquetes pueden quedar por dependencias.${NC}"
    fi

    echo ""
    echo "  Limpiando dependencias automáticas no usadas..."
    sudo apt-get autoremove -y || true
    sudo apt-get autoclean -y || true
}

pip_uninstall_one() {
    local pkg=$1
    local flags
    flags=($(pip_extra_flags))

    if ! pip_installed "$pkg"; then
        echo -e "  $pkg ${YELLOW}(no instalado con pip para este usuario)${NC}"
        return 0
    fi

    echo -n "  Desinstalando $pkg... "
    # Mismo criterio que install.py: --user + --break-system-packages (Ubuntu 24+)
    if "$PYTHON_CMD" -m pip uninstall -y "${flags[@]}" --user "$pkg" 2>/dev/null; then
        echo -e "${GREEN}✓${NC}"
        return 0
    fi
    if "$PYTHON_CMD" -m pip uninstall -y "${flags[@]}" "$pkg" 2>/dev/null; then
        echo -e "${GREEN}✓ (sistema)${NC}"
        return 0
    fi
    echo -e "${RED}✗${NC}"
    return 1
}

remove_pip_packages() {
    echo ""
    echo "2. Módulos Python (pip)..."
    echo "--------------------------"
    echo "  Usuario: $(whoami)  |  Python: $($PYTHON_CMD -c 'import sys; print(sys.executable)')"
    if pip_supports_break_system; then
        echo -e "  ${GREEN}PEP 668: usando --break-system-packages (como el instalador).${NC}"
    else
        echo -e "  ${YELLOW}pip antiguo: sin flag --break-system-packages.${NC}"
    fi

    local failed=0
    for package in "${PIP_PACKAGES[@]}"; do
        pip_uninstall_one "$package" || failed=$((failed + 1))
    done
    return "$failed"
}

remove_desktop_and_udev() {
    echo ""
    echo "3. Acceso directo, menú y udev..."
    echo "----------------------------------"

    for name in "${DESKTOP_NAMES[@]}"; do
        for dir in "$HOME/Escritorio" "$HOME/Desktop" "$HOME/.local/share/applications"; do
            if [[ -f "$dir/$name" ]]; then
                rm -f "$dir/$name"
                echo -e "  ${GREEN}✓${NC} Eliminado $dir/$name"
            fi
        done
    done

    if [[ -f "$UDEV_RULE" ]]; then
        if sudo -n true 2>/dev/null || sudo -v; then
            sudo rm -f "$UDEV_RULE"
            sudo udevadm control --reload-rules 2>/dev/null || true
            sudo udevadm trigger 2>/dev/null || true
            echo -e "  ${GREEN}✓${NC} Regla udev eliminada"
        else
            echo -e "  ${YELLOW}⚠${NC} Sin sudo: no se eliminó $UDEV_RULE"
        fi
    else
        echo -e "  Regla udev ${YELLOW}(no presente)${NC}"
    fi
}

verify_removal() {
    echo ""
    echo "4. Verificación..."
    echo "------------------"

    echo "  Paquetes apt:"
    for package in "${APT_PACKAGES[@]}"; do
        if apt_installed "$package"; then
            echo -e "    ${RED}✗ $package (aún instalado)${NC}"
            explain_apt_kept "$package"
        else
            echo -e "    ${GREEN}✓ $package${NC}"
        fi
    done

    echo ""
    echo "  Módulos pip (usuario $(whoami)):"
    for package in "${PIP_PACKAGES[@]}"; do
        if pip_installed "$package"; then
            echo -e "    ${RED}✗ $package (aún instalado)${NC}"
            loc=$("$PYTHON_CMD" -m pip show "$package" 2>/dev/null | awk -F': ' '/^Location:/{print $2}')
            [[ -n "$loc" ]] && echo "        Location: $loc"
        else
            echo -e "    ${GREEN}✓ $package${NC}"
        fi
    done

    echo ""
    echo "  Importación (debe fallar si todo se quitó):"
    if "$PYTHON_CMD" -c "
import sys
mods = ('gphoto2', 'kivy', 'cv2', 'numpy', 'PIL', 'escpos')
bad = []
for m in mods:
    try:
        __import__(m)
        bad.append(m)
    except ImportError:
        pass
if bad:
    print('    Aún importable:', ', '.join(bad))
    sys.exit(1)
print('    OK: módulos de la app no importan')
" 2>/dev/null; then
        :
    else
        echo -e "    ${YELLOW}Algunos módulos siguen importables (otro pip/venv o paquetes deb de python3-*).${NC}"
    fi
}

print_manual_hints() {
    echo ""
    echo "=========================================="
    echo -e "${GREEN}Proceso terminado${NC}"
    echo "=========================================="
    echo ""
    echo "Si apt no eliminó gphoto2 / xclip / entangle:"
    echo "  • Otro software del sistema puede depender de ellos."
    echo "  • Pruebe: sudo apt-mark showmanual gphoto2 xclip entangle"
    echo "  • Luego:    sudo apt-mark auto <paquete> && sudo apt autoremove -y"
    echo ""
    echo "Si pip falló con externally-managed-environment:"
    echo "  $PYTHON_CMD -m pip uninstall -y --break-system-packages --user \\"
    echo "    gphoto2 python-escpos kivy numpy opencv-python Pillow"
    echo ""
    echo "libgphoto2-dev «no instalado»:"
    echo "  • Normal si el instalador no completó apt o solo quedó gphoto2 (runtime)."
    echo "  • Comprobar: dpkg -l | grep gphoto"
    echo ""
    echo "Grupo lp (opcional): sudo gpasswd -d \$USER lp  # y cerrar sesión"
}

main() {
    echo "=========================================="
    echo "Desinstalador Print Scanner"
    echo "=========================================="
    echo -e "${CYAN}Ejecutar SIN sudo delante: ./eliminar_dependencias.sh${NC}"
    echo ""

    [[ "$SKIP_APT" == false ]] && remove_apt_packages || true
    [[ "$SKIP_PIP" == false ]] && remove_pip_packages || true
    [[ "$SKIP_DESKTOP" == false ]] && remove_desktop_and_udev || true
    verify_removal
    print_manual_hints
}

main "$@"
