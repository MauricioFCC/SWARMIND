"""
Deploy & Sync — Opción A (SSOT global) + mirror local por proyecto.
Estándar v2.5 (2026-08): OPENCODE GLOBAL = FUENTE DE VERDAD.

El CEREBRO (agents/, skills/, core/) y el MOTOR (harness/) viven como
fuente de verdad en ``~/.config/opencode/`` (config global de opencode).
SWARMIND los sincroniza AUTOMÁTICAMENTE en cada commit (pre-commit hook →
``scripts/sync_opencode_global.py``).

CADA PROYECTO conserva solo:
  - .opencode/          : mirror del cerebro (agents, skills, core, config)
  - skills/             : 31 skills + registry completo
  - config propia       : project_config, routing_rules, token_budgets, .env

EL MOTOR (harness/) NO se copia a los proyectos: una sola copia vive en
opencode global (~/.config/opencode/harness). Esto elimina ~5.3 GB de
duplicación (Hermes: 3.3 GB/88k archivos, sugurityOs: 1.7 GB/43k).

Si un script de un proyecto necesita harness, importa desde el global
(symlink o PYTHONPATH), no copia local.

Este script despliega/limpia el mirror de todos los proyectos de
DEV-SPACE: actualiza cerebro, elimina skills obsoletas, deja
skills_registry.yaml completo (31 skills) y preserva la configuración
propia (project_config, routing_rules, token_budgets, federated/, db/,
.env).

Seguridad (ADR-0035): rutas portables via env vars (DEV_SPACE_ROOT, ...)
con fallback a ``Path.home()``. Nunca ``$HOME`` literal.

Uso:
    python scripts/deploy_all.py                   # Deploy completo a todos
    python scripts/deploy_all.py --dry-run         # Simular sin escribir
    python scripts/deploy_all.py --project CQE     # Solo un proyecto (alias o nombre)
    python scripts/deploy_all.py --sync-only       # Solo sync, sin regenerar README
    python scripts/deploy_all.py --sync-global     # Solo sync del global opencode
    python scripts/deploy_all.py --sync-harness-global  # Sync harness al global opencode
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config (rutas portables, ADR-0035)
# ---------------------------------------------------------------------------

_HERE = Path(__file__).resolve().parent            # Swarmind/scripts/
_ROOT = _HERE.parent                                # Swarmind/
_HARNESS = _ROOT / "harness"                        # Swarmind/harness/

_DEV_SPACE = Path(os.environ.get(
    "DEV_SPACE_ROOT", str(Path.home() / "Documents" / "DEV-SPACE"),
))
_HERMES_PATH = Path(os.environ.get(
    "MEMORY_ROOT",
    str(Path.home() / "Documents" / "Memory_Proyects"),
))
_GLOBAL = Path(os.environ.get(
    "OPENCODE_GLOBAL_DIR",
    str(Path.home() / ".config" / "opencode"),
))

# Directorios que NUNCA se tocan (no-proyecto o ruido)
_SKIP_DIRS = {
    "SWARMIND", ".pytest_cache", "node_modules", "tests",
    ".git", ".venv", "venv", "__pycache__", ".idea", ".vscode",
}

# Alias CLI -> nombre real de carpeta
_ALIASES = {
    "CQE": "core-quant-engine",
    "HC": "Historia Clinica",
    "ONYX": "Onyx-Quan-AIBot",
    "PDV": "PDV Basic",
    "HERMES": "Hermes_Memory_Proyects",
    "ALFA": "de_0_a_Alfa",
    "SECURITY": "sugurityOs",
}

# Skills disponibles (31) — potencia total Swarmind en TODOS los proyectos
_ALL_SKILLS = [
    "evolve", "hedgefund", "quant-trading", "alpha-research", "risk-execution",
    "frontend-uiux", "responsive-ui", "rust-lang", "architecture", "data-science",
    "security-audit", "devops-infra", "business-strategy", "communication",
    "project-management", "behavioral-economics", "math-doc", "science-doc",
    "physical-sciences", "psychology", "education", "ethics", "linguistics",
    "sociology", "creative-design", "healthtech", "legal-doc", "pos-retail",
    "sustainability", "ads-optimizer", "risk-intelligence",
]

# ---------------------------------------------------------------------------
# Modelo de proyecto
# ---------------------------------------------------------------------------


@dataclass
class Project:
    """Proyecto destino detectado en DEV-SPACE.

    Args:
        name: Nombre real de la carpeta (ej. "core-quant-engine").
        path: Ruta absoluta del proyecto.
        ptype: Tipo inferido (trading, healthtech, retail, security, general).
        description: Descripción usada en el README generado.
    """

    name: str
    path: Path
    ptype: str
    description: str


# ---------------------------------------------------------------------------
# Descubrimiento de proyectos
# ---------------------------------------------------------------------------


def _detect_type(name: str) -> str:
    """Infiera el tipo de proyecto desde el nombre de la carpeta.

    Args:
        name: Nombre de la carpeta del proyecto.

    Returns:
        Tipo: trading, healthtech, retail, security o general (default).
    """
    lower = name.lower()
    if any(k in lower for k in ("quant", "alpha", "trading", "bot", "onyx")):
        return "trading"
    if any(k in lower for k in ("clinica", "health", "historia", "salud")):
        return "healthtech"
    if any(k in lower for k in ("pdv", "pos", "venta", "retail", "store")):
        return "retail"
    if any(k in lower for k in ("security", "seguridad", "harden", "sugurity")):
        return "security"
    return "general"


def discover_projects() -> list[Project]:
    """Auto-descubre proyectos en DEV-SPACE (los que tienen .opencode).

    Estándar v2.5: solo requiere .opencode/ (el motor harness vive en
    opencode global). Proyectos sin harness también se despliegan.

    Returns:
        Lista de Project ordenada por nombre.
    """
    projects: list[Project] = []
    if not _DEV_SPACE.exists():
        logger.warning("  ⚠️  DEV-SPACE no existe: %s", _DEV_SPACE)
        return projects

    for entry in sorted(_DEV_SPACE.iterdir()):
        if not entry.is_dir() or entry.name in _SKIP_DIRS:
            continue
        if not (entry / ".opencode").is_dir():
            continue
        # Estándar v2.5: harness ya no es requerido (vive en opencode global)
        projects.append(Project(
            name=entry.name,
            path=entry,
            ptype=_detect_type(entry.name),
            description=f"Proyecto {entry.name} gestionado por Swarmind Harness",
        ))
    return projects


def resolve_project(selector: str, projects: list[Project]) -> Project | None:
    """Resuelve un selector CLI (alias o nombre) a un Project.

    Args:
        selector: Alias (CQE, HC...) o nombre real de carpeta.
        projects: Lista de proyectos descubiertos.

    Returns:
        Project encontrado o None.
    """
    if not selector:
        return None
    target = _ALIASES.get(selector.upper(), selector)
    for project in projects:
        if project.name.lower() == target.lower():
            return project
    return None


# ---------------------------------------------------------------------------
# Preservación de config propia
# ---------------------------------------------------------------------------

# Archivos de config propios por proyecto (se preservan SIEMPRE).
# skills_registry.yaml NO se preserva — se regenera completo desde la fuente.
_CONFIG_FILES = [
    ".opencode/config/project_config.yaml",
    ".opencode/config/routing_rules.yaml",
    ".opencode/config/token_budgets.yaml",
    ".env",
    ".env.example",
]

# Directorios propios por proyecto (se preservan SIEMPRE)
_CONFIG_DIRS = [
    ".opencode/federated",       # memoria federada (knowledge_proj_a/b.json)
    ".opencode/agents/auto",     # agentes auto-generados
    ".opencode/skills/auto",     # skills auto-generadas
    ".opencode/memory",          # memoria local del agente
    ".opencode/db",              # datos runtime
    "harness/db",                # datos LanceDB runtime
]


def _backup_config(project: Project) -> tuple[dict[str, bytes], dict[str, Path]]:
    """Respalda la config propia del proyecto antes del sync.

    Args:
        project: Proyecto destino.

    Returns:
        Tupla (archivos preservados, directorios preservados en temp).
    """
    saved_files: dict[str, bytes] = {}
    for rel in _CONFIG_FILES:
        path = project.path / rel
        if path.is_file():
            saved_files[rel] = path.read_bytes()
            logger.info("    💾 backup: %s", rel)

    saved_dirs: dict[str, Path] = {}
    for rel in _CONFIG_DIRS:
        path = project.path / rel
        if path.is_dir():
            tmp = Path(tempfile.mkdtemp(prefix="deploy_cfg_")) / Path(rel).name
            shutil.copytree(path, tmp)
            saved_dirs[rel] = tmp
            logger.info("    💾 backup dir: %s", rel)
    return saved_files, saved_dirs


def _restore_config(
    project: Project,
    saved_files: dict[str, bytes],
    saved_dirs: dict[str, Path],
) -> None:
    """Restaura la config propia del proyecto tras el sync.

    Args:
        project: Proyecto destino.
        saved_files: Archivos preservados (rel -> bytes).
        saved_dirs: Directorios preservados (rel -> temp path).
    """
    for rel, data in saved_files.items():
        path = project.path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        logger.info("    ♻️  restaurado: %s", rel)

    for rel, tmp in saved_dirs.items():
        path = project.path / rel
        if path.exists():
            shutil.rmtree(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(tmp, path)
        shutil.rmtree(tmp, ignore_errors=True)
        logger.info("    ♻️  restaurado dir: %s", rel)


# ---------------------------------------------------------------------------
# Sync de árboles
# ---------------------------------------------------------------------------


def _sync_tree(src: Path, dst: Path, dry_run: bool = False) -> int:
    """Sync espejo preservador: actualiza src→dst sin borrar archivos propios.

    Copia/sobreescribe los archivos de ``src`` en ``dst``. Los archivos o
    directorios presentes en ``dst`` pero ausentes en ``src`` (config propia
    del proyecto) NO se borran. Devuelve cuántos archivos se actualizaron.

    Args:
        src: Directorio fuente (Swarmind).
        dst: Directorio destino (proyecto).
        dry_run: Si True, solo simula (no escribe).

    Returns:
        Número de archivos copiados.
    """
    if not src.is_dir():
        return 0
    dst.mkdir(parents=True, exist_ok=True)

    count = 0
    for item in src.iterdir():
        target = dst / item.name
        if item.is_dir():
            if target.exists() and target.is_dir() and not target.is_symlink():
                count += _sync_tree(item, target, dry_run)
            else:
                if not dry_run:
                    shutil.copytree(item, target, dirs_exist_ok=True)
                count += sum(1 for _ in item.rglob("*") if _.is_file())
        else:
            if not dry_run:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, target)
            count += 1
    return count


# ---------------------------------------------------------------------------
# Skills (mirror local: 31 skills + registry completo)
# ---------------------------------------------------------------------------


def deploy_skills(project: Project, dry_run: bool) -> int:
    """Despliega TODAS las skills de la fuente + skills_registry completo.

    Todos los proyectos reciben las 31 skills (potencia total). Limpia
    skills obsoletas no presentes en la fuente (excepto auto/).

    Args:
        project: Proyecto destino.
        dry_run: Si True, solo simula.

    Returns:
        Número de skills desplegados.
    """
    allowed = set(_ALL_SKILLS)
    target = project.path / ".opencode" / "skills"
    src_skills = _ROOT / ".opencode" / "skills"

    if dry_run:
        logger.info("    🔍 skills a desplegar (%d) — potencia total", len(allowed))
        return len(allowed)

    target.mkdir(parents=True, exist_ok=True)

    # Limpiar skills obsoletas (no en la fuente, no auto/)
    cleaned = 0
    for skill_dir in target.iterdir():
        if skill_dir.is_dir() and skill_dir.name not in allowed and skill_dir.name != "auto":
            shutil.rmtree(skill_dir)
            cleaned += 1
            logger.info("    🗑️  removed skill obsoleta: %s", skill_dir.name)

    # Copiar las 31 skills desde la fuente
    copied = 0
    for skill_name in sorted(allowed):
        src = src_skills / skill_name
        if src.is_dir():
            dst = target / skill_name
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            copied += 1

    # skills_registry.yaml completo desde la fuente
    registry_src = src_skills / "skills_registry.yaml"
    if registry_src.is_file():
        shutil.copy2(registry_src, target / "skills_registry.yaml")

    logger.info("    📦 skills: %d copiados, %d obsoletas limpiadas, registry actualizado",
                copied, cleaned)
    return copied


# ---------------------------------------------------------------------------
# README
# ---------------------------------------------------------------------------


def generate_readme(project: Project, dry_run: bool) -> bool:
    """Genera/actualiza README.md del proyecto.

    Args:
        project: Proyecto destino.
        dry_run: Si True, solo simula.

    Returns:
        True si el README fue (o sería) actualizado.
    """
    skills_list = "\n".join(f"  - `{s}`" for s in _ALL_SKILLS)
    agents_list = """  - `coordinator` — Entry point, analiza y delega
  - `builder` — Toda implementación (Rust, Go, Python, Web, Mobile)
  - `scientist` — Investigación, papers, AI/ML, patrones
  - `guardian` — Calidad, seguridad, riesgo, documentación
  - `evolve` — Auto-mejora del sistema
  - `evolve-researcher` — Investigación para el loop de evolución
  - `evolve-engineer` — Ingeniería para el loop de evolución
  - `evolve-analyzer` — Análisis para el loop de evolución"""

    content = f"""# ⚙️ {project.name} — Sistema Multi-Agente Evolutivo

**{project.description}**

> Este proyecto utiliza el **Swarmind Harness** (Opción A: cerebro global en
> `~/.config/opencode/` + mirror local). opencode carga agentes, skills y
> core desde el global para TODOS los proyectos; el mirror local mantiene el
> proyecto abierto para cualquier editor.

---

## 🤖 Agentes (20)

{agents_list}

---

## 🧠 Skills ({len(_ALL_SKILLS)} — potencia total)

{skills_list}

---

## 🚀 Inicio Rápido

```bash
# Delegación directa
python harness/run.py "@builder: implementa <tu-tarea>"

# Ver salud del sistema
python harness/run.py '!health'
```

---

## 🔗 Memoria Federada

Comparte conocimiento entre proyectos mediante la memoria central:

```bash
python scripts/agentic_bridge_sync.py
```

---

*Generado por Swarmind Harness — {datetime.now(UTC).strftime('%Y-%m-%d')}*
"""
    if not dry_run:
        (project.path / "README.md").write_text(content, encoding="utf-8")
    return True


# ---------------------------------------------------------------------------
# Deploy por proyecto
# ---------------------------------------------------------------------------


def deploy_project(
    project: Project,
    dry_run: bool = False,
    sync_only: bool = False,
) -> dict:
    """Despliega el mirror local completo a un proyecto.

    Args:
        project: Proyecto destino.
        dry_run: Si True, solo simula (no escribe nada).
        sync_only: Si True, no regenera README.

    Returns:
        Dict con estadísticas del deploy.
    """
    if not project.path.exists():
        logger.warning("  ❌ Project path not found: %s", project.path)
        return {"name": project.name, "status": "skipped", "reason": "path_not_found"}

    logger.info("")
    logger.info("=" * 60)
    logger.info("📦 DEPLOYING: %s (%s) — mirror local", project.name, project.ptype)
    logger.info("=" * 60)

    # 1. Backup config propia (federated/, db/, .env, config/)
    saved_files: dict[str, bytes] = {}
    saved_dirs: dict[str, Path] = {}
    if not dry_run:
        saved_files, saved_dirs = _backup_config(project)

    # 2. Sync .opencode/ (cerebro mirror — agents, skills, core, config)
    logger.info("📁 .opencode/ — syncing cerebro mirror...")
    opencode_count = _sync_tree(_ROOT / ".opencode", project.path / ".opencode", dry_run)
    logger.info("  ✅ .opencode/: %d archivos %s", opencode_count, "(simulado)" if dry_run else "")

    # 3. Motor (harness/): NO se copia a proyectos (estándar v2.5).
    #    Una sola copia vive en ~/.config/opencode/harness.
    #    Projects importan desde el global via PYTHONPATH si lo necesitan.
    logger.info("📁 harness/ — SKIPPED (una sola copia en opencode global, estandar v2.5)")
    harness_count = 0

    # 4. Skills: 31 + registry completo (limpia obsoletas)
    logger.info("🧠 skills — potencia total...")
    skills_count = deploy_skills(project, dry_run)
    logger.info("  ✅ skills: %d %s", skills_count, "(simulado)" if dry_run else "")

    # 5. Restaurar config propia
    if not dry_run:
        _restore_config(project, saved_files, saved_dirs)

    # 6. README
    if not sync_only:
        logger.info("📄 README.md — generando...")
        generate_readme(project, dry_run)
        logger.info("  ✅ README.md %s", "(simulado)" if dry_run else "actualizado")

    return {
        "name": project.name,
        "type": project.ptype,
        "opencode_files": opencode_count,
        "harness_files": harness_count,
        "skills_deployed": skills_count,
        "status": "ok",
    }


# ---------------------------------------------------------------------------
# Memoria principal (Hermes)
# ---------------------------------------------------------------------------


def sync_hermes_memory(dry_run: bool = False) -> dict:
    """Actualiza la memoria principal Hermes_Memory_Proyects.

    Estándar v2.5: sincroniza .opencode/ preservando la estructura de
    memoria propia (knowledge/, syntheses/, 99_Hermes_Brain/, personal/,
    sessions/). harness/ NO se copia (vive en opencode global).

    Args:
        dry_run: Si True, solo simula.

    Returns:
        Dict con estadísticas del sync.
    """
    hermes = Project(
        name=_HERMES_PATH.name,
        path=_HERMES_PATH,
        ptype="general",
        description="Repositorio central de memoria y conocimiento multi-proyecto",
    )
    if not hermes.path.exists():
        logger.warning("  ❌ Hermes memory not found: %s", hermes.path)
        return {"name": "Hermes", "status": "skipped", "reason": "path_not_found"}

    logger.info("")
    logger.info("=" * 60)
    logger.info("🧠 HERMES MEMORY: %s", hermes.path)
    logger.info("=" * 60)

    # Memoria propia de Hermes que NUNCA se toca
    hermes_preserve = {
        "knowledge", "syntheses", "99_Hermes_Brain", "personal",
        "sessions", "projects", "inbox", "templates", "infra", "quality",
        "core", "scripts", "memory_rag",
    }

    saved_files: dict[str, bytes] = {}
    if not dry_run:
        for rel in [".opencode/skills/skills_registry.yaml", ".env", ".env.example"]:
            path = hermes.path / rel
            if path.is_file():
                saved_files[rel] = path.read_bytes()

    # Sync .opencode/ preservando skills_registry (restaurado después)
    opencode_count = _sync_tree(_ROOT / ".opencode", hermes.path / ".opencode", dry_run)

    # harness/ NO se copia a Hermes (estándar v2.5: vive en opencode global)
    logger.info("📁 harness/ — SKIPPED (una sola copia en opencode global, estandar v2.5)")
    harness_count = 0

    if not dry_run:
        for rel, data in saved_files.items():
            path = hermes.path / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        for name in hermes_preserve:
            (hermes.path / name).mkdir(parents=True, exist_ok=True)

    logger.info("  ✅ .opencode/: %d archivos", opencode_count)
    logger.info("  ✅ harness/: SKIPPED (solo en opencode global)")
    logger.info("  ✅ Memoria propia preservada (%d dirs)", len(hermes_preserve))
    return {
        "name": "Hermes",
        "type": "memory",
        "opencode_files": opencode_count,
        "harness_files": harness_count,
        "skills_deployed": 0,
        "status": "ok",
    }


# ---------------------------------------------------------------------------
# Sync harness al global opencode (estándar v2.5)
# ---------------------------------------------------------------------------


def sync_harness_to_global(dry_run: bool = False) -> int:
    """Copia harness/ a ~/.config/opencode/harness (una sola copia SSOT).

    Estándar v2.5: el MOTOR (harness/) vive en opencode global. Los
    proyectos NO lo copian (solo .opencode/ + skills). Si un proyecto
    necesita el motor, importa desde el global via PYTHONPATH.

    Args:
        dry_run: Si True, solo simula.

    Returns:
        Número de archivos sincronizados.
    """
    src = _ROOT / "harness"
    dst = _GLOBAL / "harness"
    logger.info("📦 SYNC HARNESS -> GLOBAL (estándar v2.5)")
    logger.info("   Source: %s", src)
    logger.info("   Global: %s", dst)
    logger.info("   Dry run: %s", dry_run)
    if not src.is_dir():
        logger.error("  ❌ Source harness no existe: %s", src)
        return 0
    count = _sync_tree(src, dst, dry_run)
    logger.info("  ✅ harness -> global: %d archivos %s", count, "(simulado)" if dry_run else "")
    return count


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI principal del deploy."""
    import argparse
    parser = argparse.ArgumentParser(
        description="Deploy & Sync (Opción A: SSOT global + mirror local)")
    parser.add_argument("--dry-run", action="store_true", help="Solo simular (no escribe)")
    parser.add_argument("--project", "-p", type=str, help="Solo un proyecto (alias o nombre)")
    parser.add_argument("--sync-only", action="store_true", help="Solo sync, no regenerar README")
    parser.add_argument("--skip-hermes", action="store_true", help="No sincronizar memoria Hermes")
    parser.add_argument("--sync-global", action="store_true",
                        help="Solo sincronizar el global opencode (no tocar proyectos)")
    parser.add_argument("--sync-harness-global", action="store_true",
                        help="Solo sync harness -> opencode global (una copia SSOT, v2.5)")
    args = parser.parse_args()

    # ── Solo sync global ──
    if args.sync_global:
        from scripts.sync_opencode_global import sync_global
        sync_global(dry_run=args.dry_run)
        return

    # ── Solo sync harness -> global ──
    if args.sync_harness_global:
        sync_harness_to_global(dry_run=args.dry_run)
        return

    logger.info("=" * 60)
    logger.info("🚀 Swarmind DEPLOY & SYNC (Opción A — SSOT global + mirror local)")
    logger.info("   Source:     %s", _ROOT)
    logger.info("   Global:     %s", _GLOBAL)
    logger.info("   DEV-SPACE:  %s", _DEV_SPACE)
    logger.info("   Dry run:    %s", args.dry_run)
    logger.info("=" * 60)

    projects = discover_projects()
    if not projects:
        logger.error("  ❌ No se encontraron proyectos con .opencode/ en %s", _DEV_SPACE)
        return

    logger.info("Proyectos descubiertos: %d", len(projects))
    for p in projects:
        logger.info("  • %-25s (%s)", p.name, p.ptype)

    all_stats = []
    if args.project:
        selected = resolve_project(args.project, projects)
        if selected is None:
            logger.error("  ❌ Proyecto no encontrado: %s", args.project)
            logger.error("     Usa: %s", ", ".join(sorted(_ALIASES)))
            return
        all_stats.append(deploy_project(selected, dry_run=args.dry_run, sync_only=args.sync_only))
    else:
        for project in projects:
            all_stats.append(deploy_project(project, dry_run=args.dry_run, sync_only=args.sync_only))

    if not args.skip_hermes:
        all_stats.append(sync_hermes_memory(dry_run=args.dry_run))

    # Summary
    logger.info("")
    logger.info("=" * 60)
    logger.info("📊 DEPLOY SUMMARY")
    logger.info("=" * 60)
    for s in all_stats:
        if s.get("status") == "skipped":
            logger.info("  ⏭️  %-25s | %s", s.get("name", "?"), s.get("reason", ""))
            continue
        logger.info(
            "  ✅ %-25s | type=%-10s | .opencode=%-5d harness=%-5d skills=%d",
            s.get("name", "?"),
            s.get("type", "?"),
            s.get("opencode_files", 0),
            s.get("harness_files", 0),
            s.get("skills_deployed", 0),
        )

    logger.info("")
    logger.info("🎉 Done! (harness solo en opencode global, estandar v2.5)")


if __name__ == "__main__":
    main()
