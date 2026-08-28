# ADR-0060: Install scripts cross-platform (install.sh + install.ps1)

**Fecha**: 2026-08-26
**Estado**: Aceptado
**Decisor**: Coordinator (SWARMIND)
**Categoría**: DevEx / Portabilidad

## Contexto

SWARMIND requiere 6 pasos para setup en una máquina nueva:
1. Python >= 3.12
2. uv package manager
3. Dependencias (uv sync)
4. Sync a `~/.config/opencode/`
5. Pre-commit hooks
6. Verificación

Actualmente `setup_swarmind.py` hace todo esto pero:
- Solo funciona en Windows (usa `setx` para env vars)
- No crea symlinks (usa copy)
- No es idempotente (si se ejecuta 2 veces, re-hace todo)

El patrón del ecosistema (fazt.dev) usa scripts separados por OS:
- `install.sh` para Linux/Mac
- `install.ps1` para Windows

## Decisión

Crear dos scripts idempotentes:

### `install.sh` (317 líneas, Linux/Mac)
- Detecta OS via `$OSTYPE`
- Prefiere `python3`, valida >= 3.12
- Instala uv via `curl -LsSf https://astral.sh/uv/install.sh | sh`
- `uv sync --extra dev`
- Crea symlinks: `~/.config/opencode/{agents,skills,core}` → repo
- Instala hooks: `git config core.hooksPath .githooks`
- Verifica: `python -c "import harness"`
- `--dry-run` flag, colores ANSI, idempotente

### `install.ps1` (413 líneas, Windows)
- Detecta Python via `Get-Command`
- Instala uv via `pip install uv` (portable)
- `uv sync --extra dev`
- Symlinks con fallback a copy (Developer Mode check)
- Hooks via `git config core.hooksPath`
- Verificación con `sys.path` fallback
- `-DryRun` switch, `Write-Host` con colores

## Consecuencias

### Positivas
- `git clone` → `./install.sh` → todo funciona (1 comando)
- Cross-platform: Linux, Mac, Windows
- Idempotente: seguro ejecutar múltiples veces
- Sin dependencias externas (solo Python + Git)

### Negativas
- Dos scripts que mantener (diff sintáctico, misma lógica)
- Windows symlinks requieren Developer Mode (fallback mitigado)

### Riesgos
- **Bajo**: fallback a copy si symlink falla
- **Bajo**: idempotente (verifica estado antes de actuar)

## Referencias

- fazt.dev: "Cómo Sincronizar Agentes de IA en Todas tus Máquinas" (2026-08)
- setup_swarmind.py: script existente (se mantiene como alternativa Python)
- opencode.ai docs: rutas de configuración por OS

## Archivos afectados

- `scripts/install.sh` (nuevo)
- `scripts/install.ps1` (nuevo)
