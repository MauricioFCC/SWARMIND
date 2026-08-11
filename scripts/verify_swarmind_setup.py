"""
verify_swarmind_setup.py — Health-check del setup Swarmind en un PC.

Verifica que el harness global y la memoria central esten correctamente
instalados y usables (ADR-0042: diagnostico en PC nuevo). Detecta las
causas raiz conocidas ANTES de que fallen los tests TDD:

  1. ``harness_global`` — el harness en ``~/.config/opencode/harness`` debe
     ser un paquete importable (``__init__.py`` + ``__main__.py``). Si falta,
     ``import harness`` resuelve al local o falla.
  2. ``memory_central`` — ``<Documents>/Memory_Proyects`` debe existir con
     colecciones LanceDB en ``data/lancedb``. Si falta, TDD falla al persistir
     memoria (ADR-0038).
  3. ``env_vars`` — ``MEMORY_ROOT``/``DEV_SPACE_ROOT`` informativos (opcional:
     el script funciona con fallback portable a ``Path.home()``).

Cada check reporta WHAT (que fallo) + WHY (causa) + WHERE (ubicacion).

Uso:
    python scripts/verify_swarmind_setup.py             # Todos los checks
    python scripts/verify_swarmind_setup.py --quiet     # Solo exit code
    python scripts/verify_swarmind_setup.py --dry-run   # Simular (no escribe)
    python scripts/verify_swarmind_setup.py --fix       # Crear memoria central si falta
"""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Rutas portables (ADR-0035): env var con fallback a Path.home()
_GLOBAL_DIR = Path(os.environ.get(
    "OPENCODE_GLOBAL_DIR",
    str(Path.home() / ".config" / "opencode"),
))
_MEMORY_ROOT = Path(os.environ.get(
    "MEMORY_ROOT",
    str(Path.home() / "Documents" / "Memory_Proyects"),
))

# Colecciones LanceDB minimas esperadas (ADR-0038)
_EXPECTED_LANCE = [
    "rag_chunks.lance", "tasks_board.lance", "session_kpis.lance",
    "agent_interactions.lance",
]


def _count_lance_collections(db_dir: Path) -> int:
    """Cuenta colecciones .lance validas en un directorio.

    Args:
        db_dir: Directorio de la db LanceDB.

    Returns:
        Numero de subdirectorios .lance.
    """
    if not db_dir.is_dir():
        return 0
    return sum(1 for d in db_dir.iterdir() if d.is_dir() and d.name.endswith(".lance"))


def check_harness_global(global_dir: Path | None = None) -> dict:
    """Verifica que el harness global sea un paquete importable.

    Args:
        global_dir: Directorio global de opencode (default: env/Path.home()).

    Returns:
        Dict con ok, why, where.
    """
    gdir = global_dir or _GLOBAL_DIR
    init_py = gdir / "harness" / "__init__.py"
    main_py = gdir / "harness" / "__main__.py"
    missing = [p.name for p in (init_py, main_py) if not p.is_file()]
    if not missing:
        return {
            "ok": True,
            "why": "Paquete harness completo en el global (importable).",
            "where": str(gdir / "harness"),
        }
    return {
        "ok": False,
        "why": f"Harness global incompleto: faltan {', '.join(missing)}. "
               "import harness / python -m harness fallan y TDD importa el local.",
        "where": str(gdir / "harness"),
    }


def check_memory_central(memory_root: Path | None = None) -> dict:
    """Verifica que la memoria central exista con colecciones LanceDB.

    Args:
        memory_root: Raiz de memoria (default: env/Path.home()).

    Returns:
        Dict con ok, why, where.
    """
    root = memory_root or _MEMORY_ROOT
    db_dir = root / "data" / "lancedb"
    cols = _count_lance_collections(db_dir)
    if cols > 0:
        return {
            "ok": True,
            "why": f"Memoria central OK con {cols} colecciones LanceDB.",
            "where": str(db_dir),
        }
    present = [d.name for d in _EXPECTED_LANCE if (db_dir / d).is_dir()]
    return {
        "ok": False,
        "why": f"Memoria central incompleta: 0 colecciones en data/lancedb "
               f"({len(present)}/{len(_EXPECTED_LANCE)} esperadas presentes). "
               "TDD falla al persistir/recuperar memoria (ADR-0038). "
               "Ejecutar: python scripts/setup_memory_central.py",
        "where": str(db_dir),
    }


def _persisted_user_vars() -> dict[str, str]:
    """Lee env vars persistidas a nivel de usuario (Windows registry / shell rc).

    Returns:
        Dict de variables persistidas (MEMORY_ROOT, DEV_SPACE_ROOT, PYTHONPATH).
    """
    persisted: dict[str, str] = {}
    if os.name == "nt":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                for name in ("MEMORY_ROOT", "DEV_SPACE_ROOT", "PYTHONPATH"):
                    try:
                        value, _ = winreg.QueryValueEx(key, name)
                        if isinstance(value, str) and value:
                            persisted[name] = value
                    except FileNotFoundError:
                        continue
        except OSError:
            return persisted
    return persisted


def check_env_vars() -> dict:
    """Reporta env vars relevantes (informativo, no bloqueante).

    Considera tanto la sesion actual como las persistidas a nivel de usuario
    (Causa 3 ADR-0042: ``setx`` aplica a nuevas terminales).

    Returns:
        Dict con ok, why, where y env (dict de variables).
    """
    current = {
        "MEMORY_ROOT": os.environ.get("MEMORY_ROOT", ""),
        "DEV_SPACE_ROOT": os.environ.get("DEV_SPACE_ROOT", ""),
        "PYTHONPATH": os.environ.get("PYTHONPATH", ""),
    }
    persisted = _persisted_user_vars()
    merged = {
        k: current[k] or persisted.get(k, "") for k in current
    }
    set_vars = [k for k, v in merged.items() if v]
    origin = "sesion actual" if any(current.values()) else "persistidas (nuevas sesiones)"
    return {
        "ok": bool(set_vars),
        "why": f"{len(set_vars)}/3 env vars ({origin}). "
               "Opcional: el sistema usa fallback portable a Path.home().",
        "where": "entorno de usuario",
        "env": merged,
    }


def persist_env_vars() -> dict:
    """Persiste MEMORY_ROOT, DEV_SPACE_ROOT y PYTHONPATH a nivel de usuario.

    Resuelve la Causa 3 del ADR-0042 (PYTHONPATH vacio): los proyectos sin
    ``harness/`` local necesitan poder importar el harness del global.
    Idempotente: no sobreescribe PYTHONPATH existente (append con ';'),
    y solo setea DEV_SPACE_ROOT si el directorio existe.

    Windows: ``setx`` (persistente). Unix: ``~/.bashrc``/``~/.zshrc``.

    Returns:
        Dict con ok, why, set_vars (variables persistidas).
    """
    set_vars: dict[str, str] = {}
    gdir = _GLOBAL_DIR
    mem = _MEMORY_ROOT

    # MEMORY_ROOT: solo si el directorio existe
    if mem.is_dir() and not os.environ.get("MEMORY_ROOT"):
        set_vars["MEMORY_ROOT"] = str(mem)

    # DEV_SPACE_ROOT: detectar <home>/Documents/DEV_SPACE (underscore real)
    dev_space = Path.home() / "Documents" / "DEV_SPACE"
    if not dev_space.is_dir():
        dev_space = Path.home() / "Documents" / "DEV-SPACE"
    if dev_space.is_dir() and not os.environ.get("DEV_SPACE_ROOT"):
        set_vars["DEV_SPACE_ROOT"] = str(dev_space)

    # PYTHONPATH: append del global sin pisar lo existente
    current_pp = os.environ.get("PYTHONPATH", "")
    if str(gdir) not in current_pp.split(";"):
        set_vars["PYTHONPATH"] = f"{current_pp};{gdir}".lstrip(";")

    if os.name == "nt":
        for k, v in set_vars.items():
            os.system(f'setx {k} "{v}" >nul')
    else:
        rc_path = Path.home() / ".bashrc"
        lines = [f'export {k}="{v}"' for k, v in set_vars.items()]
        with rc_path.open("a", encoding="utf-8") as fh:
            fh.write("\n# SWARMIND (verify_swarmind_setup)\n" + "\n".join(lines) + "\n")

    return {
        "ok": not set_vars or True,
        "why": f"{len(set_vars)} env vars persistidas para nuevas sesiones."
               " Abre una terminal nueva para que tomen efecto.",
        "where": "entorno de usuario (setx / shell rc)",
        "set_vars": set_vars,
    }


def run_checks(global_dir: Path | None = None,
               memory_root: Path | None = None) -> dict:
    """Ejecuta todos los health-checks del setup.

    Args:
        global_dir: Directorio global opencode (testable).
        memory_root: Raiz de memoria (testable).

    Returns:
        Dict con resultados por check (ok, why, where).
    """
    return {
        "harness_global": check_harness_global(global_dir),
        "memory_central": check_memory_central(memory_root),
        "env_vars": check_env_vars(),
    }


def _report(results: dict) -> int:
    """Imprime el reporte y devuelve exit code.

    Args:
        results: Dict de run_checks.

    Returns:
        0 si todo ok, 1 si algun check falla.
    """
    logger.info("=" * 60)
    logger.info("🔍 SWARMIND SETUP VERIFICATION (ADR-0042)")
    logger.info("=" * 60)
    exit_code = 0
    for name, check in results.items():
        status = "✅" if check["ok"] else "❌"
        logger.info("%s %-15s WHAT: %s", status, name, check["why"])
        logger.info("   WHERE: %s", check["where"])
        if "env" in check:
            for k, v in check["env"].items():
                logger.info("   %s = %s", k, v or "(vacío)")
        if check.get("set_vars"):
            for k, v in check["set_vars"].items():
                logger.info("   ➕ persistido: %s = %s", k, v)
        if not check["ok"]:
            exit_code = 1
    logger.info("=" * 60)
    if exit_code == 0:
        logger.info("🎉 SETUP OK: harness global + memoria central listos para TDD.")
    else:
        logger.error("  ❌ Setup incompleto: corrige los checks marcados con ❌ "
                     "(ver ADR-0042 para mitigaciones).")
    return exit_code


def _fix_memory() -> bool:
    """Crea la memoria central si falta (idempotente).

    Returns:
        True si la memoria central quedo OK.
    """
    from setup_memory_central import ensure_memory_structure

    ensure_memory_structure()
    result = check_memory_central()
    return result["ok"]


def main() -> None:
    """CLI principal del health-check."""
    parser = argparse.ArgumentParser(description="Verifica setup Swarmind en este PC")
    parser.add_argument("--quiet", action="store_true", help="Solo exit code")
    parser.add_argument("--fix", action="store_true", help="Crear memoria central si falta")
    parser.add_argument("--persist-env", action="store_true",
                        help="Persistir MEMORY_ROOT/DEV_SPACE_ROOT/PYTHONPATH (Causa 3 ADR-0042)")
    args = parser.parse_args()

    if args.fix and not check_memory_central()["ok"]:
        logger.info("🔧 Creando memoria central (fix ADR-0042)...")
        _fix_memory()

    if args.persist_env:
        logger.info("🔧 Persistiendo env vars (Causa 3 ADR-0042)...")
        persist_env_vars()

    results = run_checks()
    exit_code = _report(results)
    if args.quiet:
        print(exit_code)
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
