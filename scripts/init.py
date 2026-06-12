"""
Harness bootstrap — cross-platform project initializer.
Creates the directory structure and initializes LanceDB storage.
Runs on Windows, macOS, and Linux (pure Python, no shell dependencies).
"""
import os
import sys
from pathlib import Path


def banner(text: str) -> None:
    print(f"[init] {text}")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    gitkeep = path / ".gitkeep"
    if not gitkeep.exists():
        gitkeep.write_text("")


def create_structure(base: Path) -> None:
    dirs = [
        "harness/db/lancedb_store",
        "harness/orchestrator",
        "harness/memory_rag",
        "harness/evolve_loop",
        "harness/tools_sandbox",
        "docs/arquitectura",
        "docs/dominios_negocio",
        "docs/manual_usuario",
        "scripts",
        ".opencode/skills/auto",
        ".opencode/agents",
        "src",
        "tests",
    ]
    for d in dirs:
        ensure_dir(base / d)
    banner("Estructura de directorios creada.")


def check_dependencies() -> None:
    missing: list[str] = []
    try:
        import numpy  # noqa: F401
    except ImportError:
        missing.append("numpy")

    if missing:
        banner(f"Dependencias opcionales no encontradas: {', '.join(missing)}")
        banner("Instala con: pip install " + " ".join(missing))
    else:
        banner("Dependencias basicas satisfechas.")


def init_lancedb(base: Path) -> None:
    db_path = base / "harness" / "db" / "lancedb_store"
    try:
        from harness.memory_rag.lance_vector_store import LanceVectorStore

        store = LanceVectorStore(str(db_path))
        colls = store.list_collections()
        banner(f"LanceDB inicializado. Colecciones disponibles: {colls}")
    except Exception as exc:
        banner(f"LanceDB no disponible (in-memory fallback activo): {exc}")


def init_project(project_path: str = "") -> str:
    if project_path:
        base = Path(project_path).resolve()
    else:
        base = Path.cwd()

    if not (base / "harness").exists():
        banner("No se detecto un proyecto Harness. Inicializando...")
        create_structure(base)
    else:
        banner("Proyecto Harness detectado. Verificando estructura...")
        create_structure(base)

    check_dependencies()
    init_lancedb(base)

    banner("Inicializacion completa.")
    banner(f"Directorio: {base}")
    banner("Comandos utiles:")
    banner("  python harness/run.py \"@project-manager: plan\"")
    banner("  python scripts/generate_llms_txt.py")

    return str(base)


def main() -> None:
    project_path = sys.argv[1] if len(sys.argv) > 1 else ""
    init_project(project_path)


if __name__ == "__main__":
    main()
