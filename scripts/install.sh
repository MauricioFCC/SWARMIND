#!/usr/bin/env bash
# ============================================================================
# install.sh — Script de instalacion cross-platform para SWARMIND (Linux/Mac)
# ============================================================================
#
# Configura el entorno de desarrollo completo de SWARMIND despues de clonar
# el repositorio. Ejecuta todos los pasos necesarios para dejar el sistema
# operativo y listo para trabajar.
#
# Pasos que ejecuta:
#   1. Detecta SO (Linux/Mac) y arquitectura
#   2. Verifica Python >= 3.12
#   3. Instala uv (gestor de paquetes) si no existe
#   4. Instala dependencias del proyecto (uv sync --extra dev)
#   5. Crea symlinks de .opencode/ -> ~/.config/opencode/ (cerebro)
#   6. Instala git hooks (core.hooksPath)
#   7. Verifica que todo funcione (import harness)
#
# Uso:
#     bash scripts/install.sh              # Instalacion completa
#     bash scripts/install.sh --dry-run    # Solo simular (sin cambios)
#     bash scripts/install.sh --help       # Mostrar ayuda
#
# Requisitos:
#     - Git
#     - bash >= 4.0
#     - curl (para instalar uv)
#
# Seguridad:
#     - 0 secrets hardcodeados
#     - No ejecuta nada destructivo
#     - Idempotente: seguro de ejecutar multiples veces
#
# Idioma:
#     - Docstrings y mensajes: Espanol
#     - Codigo: Ingles
# ============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Colores (desactivados si NO es terminal interactiva)
# ---------------------------------------------------------------------------
if [[ -t 1 ]]; then
    GREEN='\033[0;32m'
    RED='\033[0;31m'
    YELLOW='\033[1;33m'
    CYAN='\033[0;36m'
    BOLD='\033[1m'
    RESET='\033[0m'
else
    GREEN='' RED='' YELLOW='' CYAN='' BOLD='' RESET=''
fi

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
OPENCODE_GLOBAL="${OPENCODE_GLOBAL_DIR:-$HOME/.config/opencode}"
DRY_RUN=false

info()    { echo -e "${CYAN}  ℹ${RESET}  $*"; }
ok()      { echo -e "${GREEN}  ✔${RESET}  $*"; }
warn()    { echo -e "${YELLOW}  ⚠${RESET}  $*"; }
fail()    { echo -e "${RED}  ✖${RESET}  $*"; }
step()    { echo -e "\n${BOLD}[$1/6]${RESET} ${BOLD}$2${RESET}"; }

die() {
    fail "$1"
    echo -e "\n${RED}INSTALACION FALLIDA.${RESET} Revisa los errores arriba."
    exit 1
}

run_or_sim() {
    if $DRY_RUN; then
        info "[dry-run] $*"
        return 0
    fi
    "$@"
}

usage() {
    echo "Uso: bash scripts/install.sh [opciones]"
    echo ""
    echo "Opciones:"
    echo "  --dry-run    Solo simular, sin hacer cambios"
    echo "  --help       Mostrar esta ayuda"
    exit 0
}

# ---------------------------------------------------------------------------
# Parseo de argumentos
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)  DRY_RUN=true; shift ;;
        --help|-h)  usage ;;
        *)          die "Opcion desconocida: $1" ;;
    esac
done

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------
echo ""
echo -e "${BOLD}================================================================${RESET}"
echo -e "${BOLD}  SWARMIND — Instalacion de entorno de desarrollo${RESET}"
echo -e "${BOLD}================================================================${RESET}"
echo "  Root:  $ROOT_DIR"
echo "  Global: $OPENCODE_GLOBAL"
echo "  Dry:  $DRY_RUN"
echo ""

# ============================================================================
# PASO 1: Detectar SO
# ============================================================================
step 1 "Detectar sistema operativo"

OS_TYPE="unknown"
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OS_TYPE="linux"
elif [[ "$OSTYPE" == "darwin"* ]]; then
    OS_TYPE="macos"
else
    warn "SO no reconocido: $OSTYPE — se continuara igualmente"
fi

ARCH="$(uname -m 2>/dev/null || echo 'unknown')"
ok "SO: $OS_TYPE | Arquitectura: $ARCH"

# ============================================================================
# PASO 2: Verificar Python >= 3.12
# ============================================================================
step 2 "Verificar Python >= 3.12"

if ! command -v python3 &>/dev/null && ! command -v python &>/dev/null; then
    die "Python no encontrado. Instala Python >= 3.12: https://www.python.org/downloads/"
fi

# Preferir python3 sobre python
PYTHON_CMD="python3"
if ! command -v python3 &>/dev/null; then
    PYTHON_CMD="python"
fi

PY_VERSION="$($PYTHON_CMD -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')" 2>/dev/null || echo "0.0.0")"
PY_MAJOR="$($PYTHON_CMD -c "import sys; print(sys.version_info.major)" 2>/dev/null || echo "0")"
PY_MINOR="$($PYTHON_CMD -c "import sys; print(sys.version_info.minor)" 2>/dev/null || echo "0")"

if [[ "$PY_MAJOR" -lt 3 ]] || { [[ "$PY_MAJOR" -eq 3 ]] && [[ "$PY_MINOR" -lt 12 ]]; }; then
    die "Python $PY_VERSION detectado. Se requiere >= 3.12 (3.10 EOL 2026-10-31, numpy 2.5.1 requiere >= 3.12). Descarga: https://www.python.org/downloads/"
fi

ok "Python $PY_VERSION"

# ============================================================================
# PASO 3: Instalar uv si no existe
# ============================================================================
step 3 "Verificar/instalar uv (gestor de paquetes)"

if command -v uv &>/dev/null; then
    UV_VERSION="$(uv --version 2>/dev/null | head -1)"
    ok "uv ya instalado: $UV_VERSION"
else
    warn "uv no encontrado. Instalando via installer oficial..."
    run_or_sim bash -c "curl -LsSf https://astral.sh/uv/install.sh | sh" || die "Error instalando uv. Instala manualmente: https://docs.astral.sh/uv/getting-started/installation/"

    # uv se instala en ~/.local/bin o ~/.cargo/bin — asegurar que esta en PATH
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

    if ! command -v uv &>/dev/null; then
        die "uv instalado pero no encontrado en PATH. Agrega ~/.local/bin o ~/.cargo/bin a tu PATH."
    fi

    ok "uv instalado: $(uv --version 2>/dev/null | head -1)"
fi

# ============================================================================
# PASO 4: Instalar dependencias
# ============================================================================
step 4 "Instalar dependencias (uv sync --extra dev)"

run_or_sim uv sync --extra dev --directory "$ROOT_DIR" \
    || die "Error instalando dependencias. Revisa que uv y Python funcionen correctamente."

ok "Dependencias instaladas"

# ============================================================================
# PASO 5: Crear symlinks a opencode global
# ============================================================================
step 5 "Crear symlinks .opencode/ -> ~/.config/opencode/"

# Directorios del cerebro que se enlazan al global
BRAIN_DIRS=("agents" "skills" "core")

for dir in "${BRAIN_DIRS[@]}"; do
    SRC="$ROOT_DIR/.opencode/$dir"
    DST="$OPENCODE_GLOBAL/$dir"

    if [[ ! -d "$SRC" ]]; then
        warn "Fuente no existe: $SRC — saltando"
        continue
    fi

    # Si ya existe un symlink apuntando al destino correcto, OK (idempotente)
    if [[ -L "$DST" ]]; then
        CURRENT_TARGET="$(readlink "$DST" 2>/dev/null || true)"
        if [[ "$CURRENT_TARGET" == "$SRC" ]]; then
            ok "Symlink $dir ya configurado"
            continue
        fi
        # Symlink apunta a otro lugar — reemplazar
        warn "Symlink $dir apunta a $CURRENT_TARGET — reemplazando"
        run_or_sim rm -f "$DST"
    fi

    # Si es un directorio real (copia previa), respaldar
    if [[ -d "$DST" && ! -L "$DST" ]]; then
        BACKUP="${DST}.bak.$(date +%s)"
        warn "Directorio real existe en $DST — respaldando a $BACKUP"
        run_or_sim mv "$DST" "$BACKUP"
    fi

    # Crear directorio padre si no existe
    run_or_sim mkdir -p "$(dirname "$DST")"

    # Crear symlink
    run_or_sim ln -s "$SRC" "$DST" \
        || warn "No se pudo crear symlink para $dir (¿permisos?). Intentando copia..."
        # Fallback a copia si symlink falla (ej. Windows sin admin en Git Bash)
        if ! $DRY_RUN && [[ ! -L "$DST" ]] && [[ ! -d "$DST" ]]; then
            run_or_sim cp -r "$SRC" "$DST" \
                || die "No se pudo enlazar ni copiar $dir"
        fi

    ok "Enlazado: $dir -> $SRC"
done

# ============================================================================
# PASO 6: Instalar git hooks
# ============================================================================
step 6 "Instalar git hooks"

cd "$ROOT_DIR"

if [[ ! -d ".git" ]]; then
    warn "No es un repositorio git — saltando hooks"
else
    # Estrategia: usar core.hooksPath (Git >= 2.9, 2016) sobre copiar archivos
    # Es mas limpio y容易 de mantener
    run_or_sim git config core.hooksPath .githooks \
        || die "Error configurando git hooks. Verifica que '.githooks/' exista."

    # Asegurar que los hooks son ejecutables (Linux/Mac)
    if [[ -d ".githooks" ]]; then
        chmod +x .githooks/* 2>/dev/null || true
    fi

    ok "Git hooks configurados (core.hooksPath = .githooks)"
fi

# ============================================================================
# PASO 7: Verificacion
# ============================================================================
echo ""
step 7 "Verificacion final"

if $DRY_RUN; then
    info "[dry-run] Se saltaria verificacion de imports"
else
    # Verificar import basico de harness
    if "$PYTHON_CMD" -c "import harness; print('  ✔ import harness: OK')" 2>/dev/null; then
        ok "Import harness exitoso"
    else
        warn "import harness falló — intentando con sys.path..."
        if "$PYTHON_CMD" -c "import sys; sys.path.insert(0, '$ROOT_DIR'); import harness; print('  ✔ import harness (con path): OK')" 2>/dev/null; then
            ok "Import harness exitoso (con path explicito)"
        else
            warn "import harness fallo. Los hooks de git y opencode funcionaran igualmente."
            warn "Si necesitas importar harness directamente, ejecuta: source .venv/bin/activate"
        fi
    fi

    # Verificar uv
    if command -v uv &>/dev/null; then
        ok "uv: $(uv --version 2>/dev/null | head -1)"
    fi

    # Verificar symlinks
    for dir in "${BRAIN_DIRS[@]}"; do
        DST="$OPENCODE_GLOBAL/$dir"
        if [[ -L "$DST" ]]; then
            ok "Symlink $dir activo"
        elif [[ -d "$DST" ]]; then
            ok "Directorio $dir presente (copia)"
        else
            warn "$dir no encontrado en $OPENCODE_GLOBAL"
        fi
    done
fi

# ============================================================================
# Resumen
# ============================================================================
echo ""
echo -e "${BOLD}================================================================${RESET}"
echo -e "${GREEN}${BOLD}  INSTALACION COMPLETADA${RESET}"
echo -e "${BOLD}================================================================${RESET}"
echo ""
echo "  Proximos pasos:"
echo "    source .venv/bin/activate     # Activar entorno virtual"
echo "    python -m harness --help      # Verificar harness"
echo "    git status                    # Verificar hooks"
echo ""
echo "  Si re-instalaste, reinicia opencode para tomar los cambios."
echo ""
