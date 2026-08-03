"""
setup_swarmind.py — Configuración inicial completa de Swarmind (estándar v2.5).

Para un usuario que acaba de clonar SWARMIND de GitHub. Ejecuta todos los
pasos necesarios para dejar el sistema operativo:

  1. Verifica Python >= 3.12 instalado
  2. Instala uv (gestor de paquetes Python) si no existe
  3. Instala dependencias del proyecto (uv sync)
  4. Sincroniza CEREBRO + MOTOR a opencode global (~/.config/opencode/)
  5. Verifica que todo funcione (imports, tests smoke)

La fuente de verdad es OPENCODE GLOBAL (~/.config/opencode/). Los proyectos
nuevos solo reciben .opencode/ + skills (sin copia de harness).

Uso:
    python scripts/setup_swarmind.py                # Setup completo
    python scripts/setup_swarmind.py --dry-run      # Solo simular
    python scripts/setup_swarmind.py --skip-uv      # No instalar uv
    python scripts/setup_swarmind.py --skip-sync    # No sincronizar global

Requisitos:
    - Python 3.12+ (3.10 EOL 2026-10-31, numpy 2.5.1 requiere >=3.12)
    - Git (para clonar y hooks)

Salida:
    - Código 0 si todo OK
    - Código 1 si hubo errores
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

_HERE = Path(__file__).resolve().parent        # Swarmind/scripts/
_ROOT = _HERE.parent                           # Swarmind/


def _check_python() -> bool:
    """Verifica que Python >= 3.12 está disponible.

    Returns:
        True si cumple, False en caso contrario.
    """
    ver = sys.version_info
    ok = (ver.major, ver.minor) >= (3, 12)
    if not ok:
        logger.error("  ❌ Python %d.%d detectado. Se requiere >= 3.12 "
                     "(3.10 EOL 2026-10-31, numpy 2.5.1 requiere >= 3.12).",
                     ver.major, ver.minor)
        logger.error("     Descarga: https://www.python.org/downloads/")
        return False
    logger.info("  ✅ Python %d.%d.%d", ver.major, ver.minor, ver.micro)
    return True


def _check_uv() -> bool:
    """Verifica que uv está instalado (o lo instala).

    Returns:
        True si uv está disponible.
    """
    if shutil.which("uv"):
        logger.info("  ✅ uv: %s", subprocess.run(["uv", "--version"], capture_output=True,
                                                  text=True, check=False).stdout.strip())
        return True
    logger.info("  ⚠️  uv no encontrado. Instalando...")
    # Windows: pip install uv (más portable que winget para scripts)
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "uv"],
            capture_output=True, text=True,
            check=False,
        )
        if result.returncode != 0:
            logger.error("  ❌ No se pudo instalar uv: %s", result.stderr[-300:])
            return False
        # Buscar uv en el PATH tras instalarlo
        if not shutil.which("uv"):
            # Agregar user site-packages scripts al PATH (Windows)
            user_scripts = Path(sys.executable).parent
            os.environ["PATH"] = f"{user_scripts}{os.pathsep}{os.environ['PATH']}"
        if not shutil.which("uv"):
            logger.error("  ❌ uv instalado pero no encontrado en PATH.")
            logger.error("     Agrega %s a tu PATH y reintenta.", Path(sys.executable).parent)
            return False
        logger.info("  ✅ uv: %s", subprocess.run(["uv", "--version"], capture_output=True,
                                                  text=True, check=False).stdout.strip())
        return True
    except Exception as e:  # noqa: BLE001 - setup defensivo
        logger.error("  ❌ Error instalando uv: %s", e)
        return False


def _install_deps(skip_uv: bool = False) -> bool:
    """Instala dependencias del proyecto con uv sync.

    Args:
        skip_uv: Si True, usa pip en vez de uv.

    Returns:
        True si exito.
    """
    if skip_uv:
        logger.info("  📦 Instalando deps con pip...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-e", ".", "--quiet"],
            cwd=_ROOT, capture_output=True, text=True,
            check=False,
        )
    else:
        logger.info("  📦 Instalando deps con uv sync...")
        result = subprocess.run(["uv", "sync", "--extra", "dev"], cwd=_ROOT,
                                capture_output=True, text=True, check=False)
    if result.returncode != 0:
        logger.error("  ❌ Error instalando deps:\n%s", result.stderr[-500:])
        return False
    logger.info("  ✅ Dependencias instaladas")
    return True


def _sync_global(dry_run: bool) -> bool:
    """Sincroniza cerebro + motor a opencode global.

    Args:
        dry_run: Si True, solo simula.

    Returns:
        True si exito.
    """
    logger.info("  🌐 Sincronizando a opencode global (~/.config/opencode/)...")
    cmd = [sys.executable, str(_HERE / "sync_opencode_global.py")]
    if dry_run:
        cmd.append("--dry-run")
    result = subprocess.run(cmd, cwd=_ROOT, capture_output=True, text=True, check=False)
    print(result.stdout[-1500:])
    if result.stderr:
        print(result.stderr[-500:])
    if result.returncode != 0:
        logger.error("  ❌ Error en sync global")
        return False
    logger.info("  ✅ OpenCode global sincronizado (cerebro + motor)")
    return True


def _verify() -> bool:
    """Verifica que el sistema funciona (imports + smoke test).

    Returns:
        True si todo OK.
    """
    logger.info("  🧪 Verificando instalación...")
    import sys as _sys
    _sys.path.insert(0, str(_ROOT))
    try:
        # Importar módulos clave
        from harness.orchestrator.agent_discovery import (
            discover_agents_recursive,  # noqa: F401
        )
        logger.info("  ✅ Imports de harness OK")
        return True
    except Exception as e:  # noqa: BLE001 - setup defensivo
        logger.error("  ❌ Error importando harness: %s", e)
        return False


def main() -> None:
    """CLI principal del setup."""
    parser = argparse.ArgumentParser(description="Setup inicial de Swarmind (v2.5)")
    parser.add_argument("--dry-run", action="store_true", help="Solo simular")
    parser.add_argument("--skip-uv", action="store_true", help="Usar pip en vez de uv")
    parser.add_argument("--skip-sync", action="store_true", help="No sincronizar global")
    parser.add_argument("--skip-config", action="store_true", help="No abrir menú de configuración")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("🚀 SWARMIND SETUP (estándar v2.5 — opencode global = SSOT)")
    logger.info("   Raíz:  %s", _ROOT)
    logger.info("   Dry:   %s", args.dry_run)
    logger.info("=" * 60)

    steps_ok = True

    # 1. Python
    if args.dry_run:
        logger.info("  [simulado] Verificar Python >= 3.12")
    else:
        steps_ok = _check_python() and steps_ok

    # 2. uv
    if args.skip_uv:
        logger.info("  [skip] uv (usando pip)")
    elif args.dry_run:
        logger.info("  [simulado] Instalar/verificar uv")
    else:
        steps_ok = _check_uv() and steps_ok

    # 3. Dependencias
    if args.dry_run:
        logger.info("  [simulado] Instalar dependencias (uv sync)")
    else:
        steps_ok = _install_deps(skip_uv=args.skip_uv) and steps_ok

    # 4. Sync global (cerebro + motor)
    if args.skip_sync:
        logger.info("  [skip] Sync a opencode global")
    elif args.dry_run:
        logger.info("  [simulado] Sync cerebro + motor a opencode global")
    else:
        steps_ok = _sync_global(dry_run=False) and steps_ok

    # 5. Verificación
    if args.dry_run:
        logger.info("  [simulado] Verificar imports + smoke test")
    else:
        steps_ok = _verify() and steps_ok

    # 6. Menú de configuración (memoria central, backup, opciones)
    if args.skip_config:
        logger.info("  [skip] Menú de configuración")
    elif args.dry_run:
        logger.info("  [simulado] Menú de configuración interactivo")
    else:
        logger.info("")
        logger.info("=" * 60)
        logger.info("⚙️  CONFIGURACIÓN INICIAL")
        logger.info("=" * 60)
        import subprocess as _sp
        cfg_cmd = [sys.executable, str(_HERE / "config_swarmind.py")]
        _sp.run(cfg_cmd, cwd=_ROOT, check=False)

    logger.info("=" * 60)
    if steps_ok:
        logger.info("🎉 SETUP COMPLETO. Reinicia opencode para tomar los cambios.")
        logger.info("")
        logger.info("Siguiente paso (opcional):")
        logger.info("  python scripts/deploy_all.py --dry-run   # Ver proyectos a desplegar")
        logger.info("  python scripts/deploy_all.py             # Desplegar a proyectos DEV-SPACE")
        logger.info("  python scripts/config_swarmind.py        # Menú de configuración")
        logger.info("  python scripts/backup_memory.py --list   # Ver backups de memoria")
        sys.exit(0)
    else:
        logger.error("❌ SETUP INCOMPLETO. Revisa los errores arriba.")
        sys.exit(1)


if __name__ == "__main__":
    main()
