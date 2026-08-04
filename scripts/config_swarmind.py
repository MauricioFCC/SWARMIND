"""
config_swarmind.py — Menú de configuración interactivo (al instalar Swarmind).

Se ejecuta al final de `setup_swarmind.py` (o manualmente) para configurar
las opciones del sistema de forma persistente.

OPCIONES DEL MENÚ:
  1. MEMORY_ROOT   — ruta de la memoria central (portable, cualquier SO)
  2. Backup        — activar/desactivar backup automático de la db
  3. Backup cadence — frecuencia (cada N dias / cada commit / manual)
  4. Revisar estructura — ver el layout resultante
  5. Ejecutar setup de memoria central
  6. Salir

PERSISTENCIA: las opciones se guardan en `<MEMORY_ROOT>/.swarmind_config.json`
y se leen por todos los scripts (setup_memory_central, deploy_all, etc.).

Uso:
    python scripts/config_swarmind.py              # Menú interactivo
    python scripts/config_swarmind.py --set MEMORY_ROOT=<ruta>   # Set directo
    python scripts/config_swarmind.py --show       # Mostrar config actual
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent

# Ruta central portable
_MEMORY_ROOT = Path(os.environ.get(
    "MEMORY_ROOT",
    str(Path.home() / "Documents" / "Memory_Proyects"),
))
_CONFIG_FILE = _MEMORY_ROOT / ".swarmind_config.json"

_DEFAULTS = {
    "memory_root": str(_MEMORY_ROOT),
    "backup_enabled": True,
    "backup_interval_hours": 24,     # N horas entre backups automaticos
    "backup_cadence": "daily",       # manual | daily | weekly | commit
    "backup_keep": 5,                  # N backups a conservar
    "cleanup_duplicates": True,        # limpiar harness/scripts duplicados
    "auto_import_db": False,           # importar db desde otro origen (solo si usuario lo pide)
}


def _load_config() -> dict:
    """Carga la config persistente (o defaults)."""
    if _CONFIG_FILE.exists():
        try:
            data = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
            merged = dict(_DEFAULTS)
            merged.update(data)
            return merged
        except Exception:  # noqa: BLE001 - config defensiva
            logger.warning("  ⚠️  Config corrupta. Usando defaults.")
            return dict(_DEFAULTS)
    return dict(_DEFAULTS)


def _save_config(config: dict) -> None:
    """Persiste la config."""
    _MEMORY_ROOT.mkdir(parents=True, exist_ok=True)
    _CONFIG_FILE.write_text(
        json.dumps(config, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("  💾 Config guardada: %s", _CONFIG_FILE)


def _show(config: dict) -> None:
    """Muestra la config actual."""
    logger.info("=" * 60)
    logger.info("⚙️  SWARMIND CONFIG")
    logger.info("=" * 60)
    for k, v in config.items():
        logger.info("  %-20s = %s", k, v)
    logger.info("  Config file: %s", _CONFIG_FILE)


def _ask(prompt: str, default: str = "") -> str:
    """Pregunta al usuario (con fallback para no-interactivo)."""
    try:
        if default:
            response = input(f"{prompt} [{default}]: ").strip()
        else:
            response = input(f"{prompt}: ").strip()
        return response or default
    except EOFError:
        logger.info("  (modo no-interactivo, usando default: %s)", default or "-")
        return default


def _menu(config: dict) -> None:
    """Menú interactivo de configuración."""
    while True:
        logger.info("")
        logger.info("=" * 60)
        logger.info("⚙️  MENÚ DE CONFIGURACIÓN SWARMIND")
        logger.info("=" * 60)
        logger.info("  1. Memoria central (MEMORY_ROOT)  → %s", config["memory_root"])
        logger.info("  2. Backup automático               → %s", config["backup_enabled"])
        logger.info("  3. Frecuencia (cada N horas)       → %s h", config["backup_interval_hours"])
        logger.info("  4. Backups a conservar             → %s", config["backup_keep"])
        logger.info("  5. Limpiar duplicados              → %s", config["cleanup_duplicates"])
        logger.info("  6. Registrar tarea programada (auto-backup)")
        logger.info("  7. Ejecutar setup memoria central")
        logger.info("  8. Ver estructura")
        logger.info("  9. Backup ahora (manual)")
        logger.info("  0. Guardar y salir")
        logger.info("=" * 60)
        choice = _ask("Selecciona", "0").strip()
        if choice == "1":
            new_root = _ask("Nueva ruta memoria central", config["memory_root"])
            if new_root:
                config["memory_root"] = new_root
        elif choice == "2":
            val = _ask("Backup automático (si/no)", "si").strip().lower()
            config["backup_enabled"] = val in ("si", "s", "yes", "y", "1", "true")
        elif choice == "3":
            val = _ask("Backup cada N horas (1-720)", str(config["backup_interval_hours"])).strip()
            if val.isdigit():
                config["backup_interval_hours"] = min(max(int(val), 1), 720)
        elif choice == "4":
            val = _ask("Backups a conservar (1-20)", str(config["backup_keep"])).strip()
            if val.isdigit():
                config["backup_keep"] = min(max(int(val), 1), 20)
        elif choice == "5":
            val = _ask("Limpiar duplicados (si/no)", "si").strip().lower()
            config["cleanup_duplicates"] = val in ("si", "s", "yes", "y", "1", "true")
        elif choice == "6":
            _save_config(config)
            logger.info("  ▶️  Registrando tarea programada...")
            import subprocess
            cmd = [sys.executable, str(_HERE / "backup_memory.py"), "--schedule"]
            subprocess.run(cmd, env={**os.environ, "MEMORY_ROOT": config["memory_root"]}, check=False)
        elif choice == "7":
            logger.info("  ▶️  Ejecutando setup memoria central...")
            import subprocess
            cmd = [sys.executable, str(_HERE / "setup_memory_central.py")]
            result = subprocess.run(cmd, env={**os.environ, "MEMORY_ROOT": config["memory_root"]}, check=False)
            if result.returncode != 0:
                logger.error("  ❌ Setup memoria central falló")
        elif choice == "8":
            _show(config)
        elif choice == "9":
            logger.info("  ▶️  Backup manual...")
            import subprocess
            cmd = [sys.executable, str(_HERE / "backup_memory.py"), "--force"]
            subprocess.run(cmd, env={**os.environ, "MEMORY_ROOT": config["memory_root"]}, check=False)
        elif choice == "0":
            _save_config(config)
            logger.info("  👋 Config guardada. ¡Listo!")
            return
        else:
            logger.info("  Opción no válida")


def main() -> None:
    """CLI principal."""
    parser = argparse.ArgumentParser(description="Configuración interactiva de Swarmind")
    parser.add_argument("--show", action="store_true", help="Mostrar config actual")
    parser.add_argument("--set", type=str, metavar="KEY=VALUE", help="Set directo (ej. backup_enabled=true)")
    parser.add_argument("--non-interactive", action="store_true", help="Sin prompts (usa defaults/env)")
    args = parser.parse_args()

    config = _load_config()

    if args.show:
        _show(config)
        return

    if args.set:
        if "=" not in args.set:
            logger.error("  ❌ Formato: KEY=VALUE")
            sys.exit(1)
        key, value = args.set.split("=", 1)
        if key in _DEFAULTS:
            if isinstance(_DEFAULTS[key], bool):
                config[key] = value.lower() in ("true", "1", "si", "yes")
            elif isinstance(_DEFAULTS[key], int):
                config[key] = int(value)
            else:
                config[key] = value
            _save_config(config)
            logger.info("  ✅ %s = %s", key, config[key])
        else:
            logger.error("  ❌ Clave desconocida: %s (válidas: %s)", key, ", ".join(_DEFAULTS))
            sys.exit(1)
        return

    if args.non_interactive:
        _save_config(config)
        logger.info("  ✅ Config guardada (no-interactivo)")
        return

    _menu(config)


if __name__ == "__main__":
    main()
