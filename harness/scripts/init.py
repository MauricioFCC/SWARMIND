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
import subprocess
import sys
from pathlib import Path


def banner(text: str) -> None:
    print(f"[init] {text}")


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
    path.mkdir(parents=True, exist_ok=True)
    gitkeep = path / ".gitkeep"
    if not gitkeep.exists():
        gitkeep.write_text("")


def create_structure(base: Path) -> None:
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
        ".opencode/agents",
    ]
    for d in dirs:
        ensure_dir(base / d)
    banner("Estructura de directorios creada.")


def init_lancedb(base: Path) -> None:
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
    print()
    banner("🔌 MCP Client activo. El sistema soporta servidores MCP comunitarios.")
    banner("   Ver: https://github.com/modelcontextprotocol/servers")
    print()

    if _ask_yes_no("¿Querés habilitar algún servidor MCP ahora?"):
        print()
        print("  Servidores disponibles:")
        print("    1. filesystem — Acceso a archivos (read/write/list)")
        print("    2. github     — API de GitHub (issues, PRs, repos)")
        print("    3. postgres   — Consultas PostgreSQL")
        print("    4. memory     — Memoria persistente / grafo de conocimiento")
        print("    5. brave_search — Busqueda web")
        print("    6. none       — No habilitar ninguno ahora")
        print()

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
    setup_mcp_servers(base)

    banner("Inicializacion completa.")
    banner(f"Directorio: {base}")
    banner("Comandos utiles:")
    banner("  python harness/run.py \"@project-manager: plan\"")
    banner("  python harness/run.py --force-cloud \"@swe: crear API\"")
    banner("  python harness/scripts/generate_llms_txt.py")

    return str(base)


def main() -> None:
    project_path = sys.argv[1] if len(sys.argv) > 1 else ""
    init_project(project_path)

    # Generate LLMs documentation index
    try:
        from harness.scripts.generate_llms_txt import generate_llms_txt, generate_llms_full_txt
        generate_llms_txt()
        generate_llms_full_txt()
    except Exception as exc:
        banner(f"No se pudo generar llms.txt: {exc}")


if __name__ == "__main__":
    main()
