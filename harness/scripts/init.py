"""
Harness bootstrap — cross-platform project initializer.
Creates the directory structure and initializes LanceDB storage.
Runs on Windows, macOS, and Linux (pure Python, no shell dependencies).

Now with:
  - Ollama detection (for local model routing)
  - MCP server setup wizard
  - Renamed DB: lancedb_store → lancedb
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path
import logging
logger = logging.getLogger(__name__)


def banner(text: str) -> None:
    """Banner."""
    logger.info(f"[init] {text}")


def check_lancedb() -> bool:
    """Check if lancedb is installed; attempt auto-install if missing."""
    try:
        import lancedb  # noqa: F401
        banner("LanceDB detectado.")
        return True
    except ImportError:
        banner("LanceDB NO detectado. Intentando instalar...")
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "lancedb"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            banner("LanceDB instalado correctamente.")
            return True
        except Exception as exc:
            banner(f"ERROR: No se pudo instalar LanceDB: {exc}")
            banner("Instala manualmente: pip install lancedb")
            return False


def check_ollama() -> bool:
    """Check if Ollama is available for local model execution."""
    try:
        result = subprocess.run(
            ["ollama", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            version = result.stdout.strip()
            banner(f"Ollama detectado: {version}")
            return True
    except FileNotFoundError:
        banner("Ollama NO detectado. Para modo local: https://ollama.com")
    except Exception as exc:
        banner(f"Error al verificar Ollama: {exc}")

    return False


def check_dependencies() -> None:
    """Check dependencies."""
    missing: list[str] = []
    try:
        import numpy  # noqa: F401
    except ImportError:
        missing.append("numpy")

    try:
        import yaml  # noqa: F401
    except ImportError:
        missing.append("pyyaml")

    try:
        import schedule  # noqa: F401
    except ImportError:
        missing.append("schedule")

    try:
        import requests  # noqa: F401
    except ImportError:
        missing.append("requests")

    # LanceDB es obligatorio, no opcional
    if not check_lancedb():
        banner("LanceDB es OBLIGATORIO. El sistema no puede funcionar sin el.")
        sys.exit(1)

    if missing:
        banner(f"Dependencias adicionales no encontradas: {', '.join(missing)}")
        banner("Instalando automaticamente...")
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install"] + missing,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            banner(f"Dependencias instaladas: {', '.join(missing)}")
        except Exception as exc:
            banner(f"ERROR: No se pudieron instalar dependencias: {exc}")
            banner("Instala manualmente: pip install " + " ".join(missing))
    else:
        banner("Dependencias basicas satisfechas.")

    # Ollama check (no blocking)
    ollama_ok = check_ollama()
    if ollama_ok:
        banner("ModelRouter podra usar modo LOCAL con Ollama.")
    else:
        banner("ModelRouter usara solo modo CLOUD (Ollama no disponible).")
        if _ask_yes_no("¿Queres instalar Ollama ahora? (se abrira el sitio web)"):
            import webbrowser
            webbrowser.open("https://ollama.com")


def _ask_yes_no(prompt: str) -> bool:
    """Ask a yes/no question and return bool."""
    try:
        answer = input(f"  {prompt} (y/N): ").strip().lower()
        return answer == "y"
    except (EOFError, KeyboardInterrupt):
        return False


def ensure_dir(path: Path) -> None:
    """Ensure dir."""
    path.mkdir(parents=True, exist_ok=True)
    gitkeep = path / ".gitkeep"
    if not gitkeep.exists():
        gitkeep.write_text("")


def create_structure(base: Path) -> None:
    """Create structure."""
    dirs = [
        "harness/db/lancedb",           # renamed from lancedb_store
        "harness/db/lancedb_store",     # legacy (kept for migration)
        "harness/orchestrator",
        "harness/orchestrator/hitl",
        "harness/memory_rag",
        "harness/model_router",
        "harness/evolve_loop",
        "harness/tools_sandbox",
        "harness/scripts",
        ".opencode/skills/auto",
        ".opencode/skills/domain",
        ".opencode/agents",
    ]
    for d in dirs:
        ensure_dir(base / d)
    banner("Estructura de directorios creada.")


def init_lancedb(base: Path) -> None:
    """Init lancedb."""
    db_path = base / "harness" / "db" / "lancedb"
    try:
        sys.path.insert(0, str(base))
        from harness.memory_rag.lance_vector_store import LanceVectorStore

        store = LanceVectorStore(str(db_path))
        colls = store.list_collections()
        banner(f"LanceDB inicializado. Colecciones disponibles: {colls}")
    except ImportError as exc:
        banner(f"ERROR: LanceDB no disponible: {exc}")
        banner("Ejecuta: pip install lancedb  o  python harness/scripts/init.py")
        sys.exit(1)
    except Exception as exc:
        banner(f"ERROR al inicializar LanceDB: {exc}")
        sys.exit(1)


def setup_mcp_servers(base: Path) -> None:
    """Interactive MCP server setup."""
    logger.info("")
    banner("🔌 MCP Client activo. El sistema soporta servidores MCP comunitarios.")
    banner("   Ver: https://github.com/modelcontextprotocol/servers")
    logger.info("")

    if _ask_yes_no("¿Querés habilitar algún servidor MCP ahora?"):
        logger.info("")
        logger.info("  Servidores disponibles:")
        logger.info("    1. filesystem — Acceso a archivos (read/write/list)")
        logger.info("    2. github     — API de GitHub (issues, PRs, repos)")
        logger.info("    3. postgres   — Consultas PostgreSQL")
        logger.info("    4. memory     — Memoria persistente / grafo de conocimiento")
        logger.info("    5. brave_search — Busqueda web")
        logger.info("    6. none       — No habilitar ninguno ahora")
        logger.info("")

        try:
            choice = input("  Selecciona un numero (1-6): ").strip()
            server_map = {
                "1": ("filesystem", "npx @modelcontextprotocol/server-filesystem"),
                "2": ("github", "npx @modelcontextprotocol/server-github"),
                "3": ("postgres", "npx @modelcontextprotocol/server-postgres"),
                "4": ("memory", "npx @modelcontextprotocol/server-memory"),
                "5": ("brave_search", "npx @modelcontextprotocol/server-brave-search"),
            }
            if choice in server_map:
                name, install_cmd = server_map[choice]
                banner(f"Servidor '{name}' seleccionado.")
                banner(f"Instalalo con: {install_cmd}")
                banner("Luego habilitalo en harness/tools_sandbox/mcp_servers.yaml")
            elif choice == "6":
                banner("OK, podes habilitarlos luego en mcp_servers.yaml.")
            else:
                banner("Opcion invalida. Podes configurarlo luego.")
        except (EOFError, KeyboardInterrupt):
            pass


def init_project(project_path: str = "") -> str:
    """Init project."""
    if project_path:
        base = Path(project_path).resolve()
    else:
        base = Path.cwd()

    # Check for legacy lancedb_store and migrate
    legacy_db = base / "harness" / "db" / "lancedb_store"
    new_db = base / "harness" / "db" / "lancedb"
    if legacy_db.exists() and not new_db.exists():
        banner("Migrando lancedb_store → lancedb...")
        legacy_db.rename(new_db)
        banner("Migracion completada.")

    if not (base / "harness").exists():
        banner("No se detecto un proyecto Harness. Inicializando...")
        create_structure(base)
    else:
        banner("Proyecto Harness detectado. Verificando estructura...")
        create_structure(base)

    check_dependencies()
    init_lancedb(base)

    # ── Migración automática de BD legacy ──
    _auto_migrate(base)

    setup_mcp_servers(base)

    banner("Inicializacion completa.")
    banner(f"Directorio: {base}")
    banner("Comandos utiles:")
    banner("  python harness/run.py \"@project-manager: plan\"")
    banner("  python harness/run.py --force-cloud \"@swe: crear API\"")
    banner("  python harness/scripts/generate_llms_txt.py")

    return str(base)


def _auto_migrate(base: Path) -> None:
    """Detecta bases de datos legacy en import/ y ofrece migrarlas."""
    import_dir = base / "harness" / "db" / "import"
    if not import_dir.exists():
        return

    # Solo import si hay algo que migrar
    from harness.db.migrate_db import DBMigrator

    migrator = DBMigrator()
    imports = migrator.scan_imports()
    if not imports:
        return

    banner("Se detectaron {} base(s) de datos para importar:".format(len(imports)))
    for imp in imports:
        banner("  * {}: {} colecciones, {}".format(
            imp["name"], len(imp["collections"]), imp["estimated_size_human"]
        ))

    try:
        choice = input("  Migrar ahora? [Y/n]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        choice = "y"

    if choice == "n":
        banner("Migracion omitida. Pods migrar luego con: python harness/run.py '!db migrate'")
        return

    for imp in imports:
        banner("Migrando '{}'...".format(imp["name"]))
        result = migrator.migrate(imp["path"])
        if result["migrated_collections"]:
            banner("[OK] Migradas: {}".format(", ".join(result["migrated_collections"])))
        if result["created"]:
            banner("[NEW] Creadas: {}".format(", ".join(result["created"])))
        if result["errors"]:
            for e in result["errors"]:
                banner("[ERROR] {}".format(e))
        if result.get("backup_path"):
            banner("[BACKUP] {}".format(result["backup_path"]))


def _auto_ingest_project() -> None:
    """Escanea el proyecto e ingiere codigo fuente como RAG.

    Detecta automaticamente directorios con archivos fuente fuera de
    ``harness/`` y ``.opencode/``, y ofrece ingerirlos como chunks RAG.
    """
    import time as _time

    from harness.memory_rag.doc_ingester import (
        RAG_EXTENSIONS,
        RAG_EXCLUDE,
        ingest_project_directory,
    )

    project_root = Path(__file__).resolve().parent.parent.parent  # raiz del proyecto
    harness_dir = project_root / "harness"
    opencode_dir = project_root / ".opencode"

    # Detectar archivos relevantes fuera de harness/ y .opencode/
    source_dirs: list[tuple[str, int]] = []
    for item in sorted(project_root.iterdir()):
        if item.name.startswith("."):
            continue
        if item.name == "harness" or item.name == ".opencode":
            continue
        if not item.is_dir():
            continue
        # Contar archivos fuente
        count = 0
        for f in item.rglob("*"):
            if not f.is_file():
                continue
            if f.suffix.lower() not in RAG_EXTENSIONS:
                continue
            if any(part in RAG_EXCLUDE for part in f.parts):
                continue
            if any(part.startswith(".") for part in f.parts):
                continue
            count += 1
        if count > 0:
            source_dirs.append((item.name, count))

    if not source_dirs:
        logger.info("  No se encontraron archivos fuente fuera del harness.")
        return

    logger.info("\n  Se detectaron %d directorios con codigo fuente:", len(source_dirs))
    for name, count in sorted(source_dirs, key=lambda x: -x[1])[:10]:
        logger.info("     - %s/ (%d archivos)", name, count)

    total = sum(c for _, c in source_dirs)
    logger.info("  Total aproximado: %d archivos", total)

    try:
        choice = input("\n  \u00bfIngerir codigo fuente como RAG? [Y/n]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        choice = "y"

    if choice == "n":
        logger.info("  Omitido. Puedes ejecutar RAG ingest manualmente despues:")
        logger.info("    python harness/scripts/rag_ingest.py")
        logger.info("    python harness/run.py \"!rag ingest\"")
        return

    logger.info("  Ingestando codigo fuente... (esto puede tomar unos segundos)")
    start = _time.time()
    try:
        stats = ingest_project_directory(str(project_root))
        elapsed = _time.time() - start
        logger.info(
            "  \u2705 RAG ingest completado en %.1fs: %d archivos, %d chunks",
            elapsed,
            stats.get("files_processed", 0),
            stats.get("chunks_inserted", 0),
        )
        if stats.get("errors", 0):
            logger.warning("  \u26a0\ufe0f  %d errores durante la ingestion", stats["errors"])
    except Exception as e:
        logger.error("  \u274c Error en RAG ingest: %s", e)


def _load_domain_skills() -> None:
    """Carga skills específicos del dominio según TECH_STACK en project_config.yaml.

    Escanea ``.opencode/config/project_config.yaml``, determina el skill de
    dominio que corresponde al ``TECH_STACK`` y lo copia a
    ``.opencode/skills/domain/`` como skill complementario.
    """
    import yaml

    config_path = (
        Path(__file__).resolve().parent.parent.parent
        / ".opencode" / "config" / "project_config.yaml"
    )
    if not config_path.exists():
        logger.info("  No se encontro project_config.yaml — saltando skills de dominio.")
        return

    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    tech_stack = config.get("TECH_STACK", "") or ""
    domain = config.get("DOMAIN", "") or ""

    # Mapeo tech-stack → nombre de skill (ordenado por especificidad)
    skill_map: list[tuple[str, str]] = [
        ("Rust", "rust-leptos"),
        ("Go", "go-web"),
        ("Python", "python-web"),
        ("TypeScript", "typescript-web"),
        ("Node", "typescript-web"),
    ]

    # Si el stack es Rust + trading -> rust-trading
    if "Rust" in tech_stack and "trading" in domain.lower():
        skill_name = "rust-trading"
    else:
        skill_name = None
        for key, val in skill_map:
            if key in tech_stack:
                skill_name = val
                break

    if not skill_name:
        logger.info(f"  No hay skill de dominio para: TECH_STACK={tech_stack!r}")
        return

    skill_src = (
        Path(__file__).resolve().parent.parent
        / "skills" / "domain" / f"{skill_name}.md"
    )
    if not skill_src.exists():
        logger.info(f"  Skill de dominio {skill_name!r} no encontrado en skills/domain/")
        return

    target_dir = (
        Path(__file__).resolve().parent.parent.parent
        / ".opencode" / "skills" / "domain"
    )
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{skill_name}.md"
    shutil.copy2(str(skill_src), str(target))
    logger.info(f"  ✅ Skill de dominio cargado: {skill_name} ({tech_stack})")


def main() -> None:
    """Main."""
    project_path = sys.argv[1] if len(sys.argv) > 1 else ""
    init_project(project_path)

    # Generate LLMs documentation index
    try:
        from harness.scripts.generate_llms_txt import generate_llms_txt, generate_llms_full_txt
        generate_llms_txt()
        generate_llms_full_txt()
    except Exception as exc:
        banner(f"No se pudo generar llms.txt: {exc}")

    # RAG ingest automático al primer uso
    _auto_ingest_project()

    # Skills de dominio según TECH_STACK
    _load_domain_skills()


if __name__ == "__main__":
    main()
