"""
Deploy & Sync — Opción A (SSOT global) + mirror local por proyecto.
Estándar v2.5 (2026-08): OPENCODE GLOBAL = FUENTE DE VERDAD.

El CEREBRO (agents/, skills/, core/) y el MOTOR (harness/) viven como
fuente de verdad en ``~/.config/opencode/`` (config global de opencode).
SWARMIND los sincroniza AUTOMÁTICAMENTE en cada commit (pre-commit hook →
``scripts/sync_opencode_global.py``).

CADA PROYECTO conserva solo:
  - .opencode/          : mirror del cerebro (agents, skills, core, config)
  - skills/             : todas las skills (descubiertas dinamicamente) + registry completo
  - config propia       : project_config, routing_rules, token_budgets, .env

EL MOTOR (harness/) NO se copia a los proyectos: una sola copia vive en
opencode global (~/.config/opencode/harness). Esto elimina gigas de
duplicacion en proyectos grandes.

Si un script de un proyecto necesita harness, importa desde el global
(symlink o PYTHONPATH), no copia local.

Este script despliega/limpia el mirror de todos los proyectos del
directorio raiz configurado: actualiza cerebro, elimina skills obsoletas,
deja skills_registry.yaml completo (skills descubiertas dinamicamente) y
preserva la configuración propia (project_config, routing_rules,
token_budgets, federated/, db/, .env).

Seguridad (ADR-0035): rutas portables via env vars (DEV_SPACE_ROOT, ...)
con fallback a ``Path.home()``. Nunca ``$HOME`` literal. Los nombres de
proyectos privados y alias CLI viven SOLO en ``deploy_local.json``
(gitignoreado); el codigo fuente es project-agnostic.

Uso:
    python scripts/deploy_all.py                   # Deploy completo a todos
    python scripts/deploy_all.py --dry-run         # Simular sin escribir
    python scripts/deploy_all.py --project ALIAS   # Solo un proyecto (alias o nombre)
    python scripts/deploy_all.py --sync-only       # Solo sync, sin regenerar README
    python scripts/deploy_all.py --force-mirror    # Ignora politica, espeja (escape hatch)
    python scripts/deploy_all.py --sync-global     # Solo sync del global opencode
    python scripts/deploy_all.py --sync-harness-global  # Sync harness al global opencode

Politica por proyecto (no destructiva): ``<proyecto>/.opencode/deploy.yaml``
  skills:   { mode: mirror|add-only|skip, exclude: [globs] }
  opencode: { exclude: [rutas relativas a .opencode/] }
Sin el archivo se aplica ``mirror`` (compat) con warning. El guard anti-TDR
aborta escribir ``num_ctx=16384`` (BSOD 0x116) y marca el proyecto blocked.
"""

from __future__ import annotations

import fnmatch
import json
import logging
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import yaml

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Politica de deploy por proyecto (no destructiva, configurable)
# ---------------------------------------------------------------------------

#: Ruta del archivo de politica opcional, relativa a la raiz del proyecto.
_POLICY_RELPATH = Path(".opencode") / "deploy.yaml"

#: Modos validos para la propagacion de skills.
_SKILL_MODES = frozenset({"mirror", "add-only", "skip"})

#: Contextos maximos prohibidos por el guard anti-TDR (BSOD 0x116).
_FORBIDDEN_CONTEXT_PATTERNS = (
    re.compile(r"""num_ctx["']?\s*[:=]\s*16384"""),
    re.compile(r"""OLLAMA_CONTEXT_LENGTH["']?\s*[:=]\s*16384"""),
)

#: Nombres exactos de archivos cuyo contenido vigila el guard anti-TDR.
_GUARDED_FILES = frozenset({"opencode.json", "ollama_models.yaml"})

#: Glob de archivos machine-private cuyo contenido tambien vigila el guard.
_GUARDED_FILE_GLOB = "ollama_local*.yaml"

#: Subarbol de skills: lo gestiona deploy_skills (no _sync_tree) para que la
#: politica por proyecto (skip/add-only/mirror) sea la unica autoridad.
_SKILLS_SUBTREE_PATTERNS = ("skills", "skills/**")

#: Proyectos ya avisados por falta de deploy.yaml (warning una sola vez).
_POLICY_WARNED: set[str] = set()


@dataclass(frozen=True)
class DeployPolicy:
    """Politica de propagacion declarada en ``<proyecto>/.opencode/deploy.yaml``.

    Args:
        skills_mode: ``mirror`` (borra+sobrescribe, compat), ``add-only``
            (solo anade skills faltantes) o ``skip`` (no toca skills).
        skills_exclude: Globs de skills que NUNCA se borran ni sobrescriben.
        opencode_exclude: Globs (relativos a ``.opencode/``) que ``_sync_tree``
            no copia ni borra.
    """

    skills_mode: str = "mirror"
    skills_exclude: tuple[str, ...] = field(default_factory=tuple)
    opencode_exclude: tuple[str, ...] = field(default_factory=tuple)


def _load_deploy_policy(project: Project, force_mirror: bool = False) -> DeployPolicy:
    """Carga la politica del proyecto (o default seguro ``mirror``).

    Si ``--force-mirror`` esta activo ignora el archivo y devuelve mirror.
    Si el archivo no existe, aplica ``mirror`` (compat) y avisa UNA vez por
    proyecto. Si es ilegible o trae un modo invalido, degrada a ``mirror``.

    Args:
        project: Proyecto destino.
        force_mirror: Escape hatch que ignora la politica declarada.

    Returns:
        DeployPolicy efectiva para el proyecto.
    """
    if force_mirror:
        logger.info("  ⚙️  politica ignorada (--force-mirror) para %s", project.name)
        return DeployPolicy()
    path = project.path / _POLICY_RELPATH
    if not path.is_file():
        _warn_missing_policy(project)
        return DeployPolicy()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        logger.warning(
            "  ⚠️  deploy.yaml ilegible en %s (%s). WHY: no puedo leer la "
            "politica. WHERE: _load_deploy_policy. Aplico mirror (compat).",
            path, exc,
        )
        return DeployPolicy()
    if not isinstance(data, dict):
        logger.warning("  ⚠️  deploy.yaml sin mapa raiz en %s. WHERE: _load_deploy_policy", path)
        return DeployPolicy()

    raw_skills = data.get("skills") or {}
    raw_opencode = data.get("opencode") or {}
    mode = str(raw_skills.get("mode", "mirror")) if isinstance(raw_skills, dict) else "mirror"
    if mode not in _SKILL_MODES:
        logger.warning(
            "  ⚠️  skills.mode invalido '%s' en %s (validos: %s). WHERE: deploy.yaml. Uso mirror.",
            mode, path, ", ".join(sorted(_SKILL_MODES)),
        )
        mode = "mirror"
    excludes = _as_str_tuple(raw_skills.get("exclude")) if isinstance(raw_skills, dict) else ()
    opencode_excludes = _as_str_tuple(raw_opencode.get("exclude")) if isinstance(raw_opencode, dict) else ()
    return DeployPolicy(
        skills_mode=mode,
        skills_exclude=excludes,
        opencode_exclude=opencode_excludes,
    )


def _as_str_tuple(value: object) -> tuple[str, ...]:
    """Normaliza una lista YAML de globs a tupla de strings.

    Args:
        value: Valor crudo (lista, None o escalar).

    Returns:
        Tupla de strings; vacia si el valor no es lista.
    """
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(str(item) for item in value if str(item).strip())


def _warn_missing_policy(project: Project) -> None:
    """Avisa una sola vez que el proyecto no declara politica.

    Args:
        project: Proyecto sin ``.opencode/deploy.yaml``.
    """
    key = str(project.path)
    if key in _POLICY_WARNED:
        return
    _POLICY_WARNED.add(key)
    logger.warning(
        "  ⚠️  %s sin .opencode/deploy.yaml: aplico skills mode=mirror (compat). "
        "WHY: sin politica, el deploy borra skills curadas (caso Onyx 17->35). "
        "WHERE: _load_deploy_policy. Declara skills.mode para conservar curacion.",
        project.name,
    )


def _is_excluded(rel_path: str, patterns: tuple[str, ...]) -> bool:
    """Indica si una ruta relativa coincide con algun glob de exclusion.

    Args:
        rel_path: Ruta relativa (relativa a ``.opencode/`` o al nombre de skill).
        patterns: Globs estilo fnmatch.

    Returns:
        True si la ruta debe excluirse.
    """
    rel_posix = rel_path.replace("\\", "/")
    return any(fnmatch.fnmatch(rel_posix, pattern) for pattern in patterns)


def _is_guarded_file(name: str) -> bool:
    """Indica si el archivo cae bajo el guard anti-TDR.

    Args:
        name: Nombre base del archivo.

    Returns:
        True si es opencode.json, ollama_models.yaml u ollama_local*.yaml.
    """
    return name in _GUARDED_FILES or fnmatch.fnmatch(name, _GUARDED_FILE_GLOB)


def _violates_context_guard(path: Path) -> bool:
    """Detecta el contexto prohibido (num_ctx/OLLAMA_CONTEXT_LENGTH 16384).

    Args:
        path: Archivo fuente a inspeccionar.

    Returns:
        True si el contenido contiene un contexto prohibido; False si no
        existe, no es texto o no coincide.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return any(pattern.search(text) for pattern in _FORBIDDEN_CONTEXT_PATTERNS)

# ---------------------------------------------------------------------------
# Config (rutas portables, ADR-0035)
# ---------------------------------------------------------------------------

_HERE = Path(__file__).resolve().parent            # Swarmind/scripts/
_ROOT = _HERE.parent                                # Swarmind/

# Config local PRIVADA (gitignoreada): nombres de proyectos reales y rutas
# del operador. El codigo fuente permanece project-agnostic (privacidad).
_LOCAL_CONFIG_PATH = _HERE / "deploy_local.json"


def _load_local_config() -> dict[str, object]:
    """Carga la config local privada si existe (si no, dict vacio).

    Returns:
        Dict con claves opcionales: dev_space_root, aliases.
    """
    if not _LOCAL_CONFIG_PATH.is_file():
        return {}
    try:
        data = json.loads(_LOCAL_CONFIG_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(
            "deploy_all: config local ilegible %s: %s (WHERE: _load_local_config)",
            _LOCAL_CONFIG_PATH, exc,
        )
        return {}


_LOCAL_CONFIG = _load_local_config()

_DEV_SPACE = Path(os.environ.get(
    "DEV_SPACE_ROOT",
    str(_LOCAL_CONFIG.get("dev_space_root") or (Path.home() / "projects")),
))
_HERMES_PATH = Path(
    os.environ.get("MEMORY_ROOT")
    or str(_LOCAL_CONFIG.get("hermes_path") or "")
    or str(Path.home() / "Memory_Proyects")
)
_GLOBAL = Path(os.environ.get(
    "OPENCODE_GLOBAL_DIR",
    str(Path.home() / ".config" / "opencode"),
))

# Directorios que NUNCA se tocan (no-proyecto o ruido)
_SKIP_DIRS = {
    "SWARMIND", ".pytest_cache", "node_modules", "tests",
    ".git", ".venv", "venv", "__pycache__", ".idea", ".vscode",
}

# Archivos machine-private que NUNCA se espejan a otros proyectos
# (tuning confidencial de ESTA maquina; cada proyecto usa el suyo o defaults).
_SKIP_FILES = {
    "ollama_local.yaml",
}

# Dirs que NUNCA se sincronizan archivo-por-archivo (ruido de arranque):
# node_modules (3667 archivos del plugin; se siembra 1 vez si falta),
# __pycache__/.pytest_cache (artefactos regenerables).
_SYNC_SKIP_DIRS = frozenset({"node_modules", "__pycache__", ".pytest_cache"})

# Alias CLI -> nombre real de carpeta (SOLO desde deploy_local.json;
# el codigo fuente no contiene nombres de proyectos privados).
_ALIASES: dict[str, str] = {
    str(k).upper(): str(v)
    for k, v in (_LOCAL_CONFIG.get("aliases") or {}).items()
}

# ---------------------------------------------------------------------------
# Skills (SSOT: se descubren desde .opencode/skills/ — sin hardcode)
# ---------------------------------------------------------------------------


def _discover_skills() -> list[str]:
    """Descubre las skills de la fuente (SSOT: .opencode/skills/).

    Lee los directorios con SKILL.md de ``_ROOT/.opencode/skills/``.
    Excluye ``auto/`` (skills auto-generadas por proyecto) y no-skills.
    Así el deploy SIEMPRE despliega las skills reales, sin lista hardcode
    que se quede obsoleta (fix: diagram-design/swarm-release-ops se borraban
    del mirror por no estar en la lista vieja de 31).

    Returns:
        Lista ordenada de nombres de skills en la fuente.
    """
    src = _ROOT / ".opencode" / "skills"
    if not src.is_dir():
        return []
    return sorted(
        d.name for d in src.iterdir()
        if d.is_dir() and d.name != "auto" and (d / "SKILL.md").is_file()
    )


def _discover_agents() -> list[str]:
    """Descubre los agentes de la fuente (SSOT: .opencode/agents/).

    Lee los ``*.md`` de ``_ROOT/.opencode/agents/`` excluyendo los
    ``*.min.md`` (versión compacta del mismo agente). Devuelve nombres
    ordenados para el README generado.

    Returns:
        Lista ordenada de nombres de agentes en la fuente.
    """
    src = _ROOT / ".opencode" / "agents"
    if not src.is_dir():
        return []
    return sorted(
        p.name[:-3] for p in src.glob("*.md")
        if not p.name.endswith(".min.md")
    )


# ---------------------------------------------------------------------------
# Modelo de proyecto
# ---------------------------------------------------------------------------


@dataclass
class Project:
    """Proyecto destino detectado en la raiz de proyectos.

    Args:
        name: Nombre real de la carpeta del proyecto.
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
    if any(k in lower for k in ("quant", "alpha", "trading", "bot")):
        return "trading"
    if any(k in lower for k in ("clinica", "health", "historia", "salud")):
        return "healthtech"
    if any(k in lower for k in ("pdv", "pos", "venta", "retail", "store")):
        return "retail"
    if any(k in lower for k in ("security", "seguridad", "harden")):
        return "security"
    return "general"


def discover_projects() -> list[Project]:
    """Auto-descubre proyectos en la raiz (los que tienen .opencode).

    Estándar v2.5: solo requiere .opencode/ (el motor harness vive en
    opencode global). Proyectos sin harness también se despliegan.

    Returns:
        Lista de Project ordenada por nombre.
    """
    projects: list[Project] = []
    if not _DEV_SPACE.exists():
        logger.warning("  ⚠️  Raiz de proyectos no existe: %s", _DEV_SPACE)
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
        selector: Alias definido en deploy_local.json o nombre real de carpeta.
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


def _sync_tree(
    src: Path,
    dst: Path,
    dry_run: bool = False,
    exclude: tuple[str, ...] = (),
    blocked: list[str] | None = None,
    _rel: str = "",
) -> int:
    """Sync espejo preservador: actualiza src→dst sin borrar archivos propios.

    Copia/sobreescribe los archivos de ``src`` en ``dst``. Los archivos o
    directorios presentes en ``dst`` pero ausentes en ``src`` (config propia
    del proyecto) NO se borran. Respeta ``exclude`` (globs relativos al
    origen) y el guard anti-TDR (aborta la escritura de archivos con
    ``num_ctx=16384``, BSOD 0x116).

    Args:
        src: Directorio fuente (Swarmind).
        dst: Directorio destino (proyecto).
        dry_run: Si True, solo simula (no escribe).
        exclude: Globs (relativos a ``src``) que no se copian ni borran.
        blocked: Lista donde se anotan los destinos bloqueados por el guard.
        _rel: Ruta relativa acumulada (uso interno de la recursion).

    Returns:
        Número de archivos copiados (excluye los bloqueados).
    """
    if not src.is_dir():
        return 0
    if not dry_run:
        dst.mkdir(parents=True, exist_ok=True)

    count = 0
    for item in src.iterdir():
        rel = f"{_rel}/{item.name}" if _rel else item.name
        if _is_excluded(rel, exclude):
            logger.debug("sync: excluido por politica: %s", rel)
            continue
        if item.name in _SKIP_FILES:
            logger.debug("sync: archivo machine-private excluido: %s", item.name)
            continue
        if item.is_dir() and item.name in _SYNC_SKIP_DIRS:
            logger.debug("sync: dir de ruido excluido: %s", item.name)
            continue
        target = dst / item.name
        if item.is_dir():
            count += _sync_tree(item, target, dry_run, exclude, blocked, rel)
        else:
            if _is_guarded_file(item.name) and _violates_context_guard(item):
                if blocked is not None:
                    blocked.append(str(target))
                logger.error(
                    "  🚫 BLOQUEADO: no escribo %s — contiene num_ctx=16384. "
                    "WHY: ese contexto disparo VIDEO_TDR_FAILURE (BSOD 0x116) en GPU 8GB. "
                    "WHERE: _sync_tree / guard anti-TDR. Corrige la fuente a 8192.",
                    target,
                )
                continue
            if not dry_run:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, target)
            count += 1
    return count


# ---------------------------------------------------------------------------
# Skills (mirror local: todas las skills + registry completo, descubrimiento dinamico)
# ---------------------------------------------------------------------------


def deploy_skills(
    project: Project,
    dry_run: bool,
    policy: DeployPolicy | None = None,
    force_mirror: bool = False,
) -> int:
    """Despliega skills segun la politica del proyecto (no destructiva).

    Modos:
      - ``mirror``   : comportamiento historico (copia+sobrescribe, limpia
        obsoletas). Es el default cuando no hay ``deploy.yaml`` (compat).
      - ``add-only`` : NO borra skills existentes; solo anade las faltantes
        (nunca sobrescribe una existente). Preserva ``skills_registry.yaml``.
      - ``skip``     : no toca ``skills/`` en absoluto (curacion intocable).

    ``skills.exclude`` aplica en los 3 modos, tambien a la limpieza.

    Args:
        project: Proyecto destino.
        dry_run: Si True, solo simula.
        policy: Politica efectiva; si es None se carga de ``deploy.yaml``.
        force_mirror: Escape hatch que fuerza ``mirror`` ignorando la politica.

    Returns:
        Número de skills desplegadas (copiadas o anadidas).
    """
    if policy is None:
        policy = _load_deploy_policy(project, force_mirror=force_mirror)
    mode = policy.skills_mode
    excludes = policy.skills_exclude
    target = project.path / ".opencode" / "skills"
    src_skills = _ROOT / ".opencode" / "skills"

    if mode == "skip":
        logger.info("    ⏭️  skills: SKIPPED (curado) — politica mode=skip")
        return 0

    allowed = [s for s in _discover_skills() if not _is_excluded(s, excludes)]

    if dry_run:
        logger.info("    🔍 skills [%s]: %d a desplegar", mode, len(allowed))
        return len(allowed)

    target.mkdir(parents=True, exist_ok=True)

    deployed = _deploy_skill_dirs(src_skills, target, allowed, mode)
    cleaned = _clean_obsolete_skills(target, set(allowed), excludes) if mode == "mirror" else 0
    _sync_skills_registry(src_skills, target, mode)

    logger.info(
        "    📦 skills [%s]: %d desplegadas, %d obsoletas limpiadas",
        mode, deployed, cleaned,
    )
    return deployed


def _deploy_skill_dirs(
    src_skills: Path, target: Path, allowed: list[str], mode: str
) -> int:
    """Copia/anade los directorios de skills permitidos.

    Args:
        src_skills: Directorio fuente de skills (SSOT).
        target: Directorio destino ``skills/`` del proyecto.
        allowed: Nombres de skills permitidos (ya filtrados por exclude).
        mode: ``mirror`` (sobrescribe) o ``add-only`` (respeta existentes).

    Returns:
        Número de skills desplegadas.
    """
    deployed = 0
    for skill_name in sorted(allowed):
        src = src_skills / skill_name
        if not src.is_dir():
            continue
        dst = target / skill_name
        if mode == "add-only" and dst.exists():
            logger.debug("    ⏭️  skill curada preservada (add-only): %s", skill_name)
            continue
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        deployed += 1
    return deployed


def _clean_obsolete_skills(
    target: Path, allowed: set[str], excludes: tuple[str, ...]
) -> int:
    """Elimina skills del destino ausentes en la fuente (respeta exclude/auto).

    Args:
        target: Directorio ``skills/`` del proyecto.
        allowed: Nombres de skills de la fuente (ya filtrados por exclude).
        excludes: Globs que NUNCA se borran.

    Returns:
        Número de skills obsoletas eliminadas.
    """
    cleaned = 0
    for skill_dir in target.iterdir():
        if not skill_dir.is_dir():
            continue
        name = skill_dir.name
        if name == "auto" or name in allowed or _is_excluded(name, excludes):
            continue
        shutil.rmtree(skill_dir)
        cleaned += 1
        logger.info("    🗑️  removed skill obsoleta: %s", name)
    return cleaned


def _sync_skills_registry(src_skills: Path, target: Path, mode: str) -> None:
    """Copia ``skills_registry.yaml`` salvo en add-only con registry existente.

    Args:
        src_skills: Directorio fuente de skills (SSOT).
        target: Directorio ``skills/`` del destino.
        mode: Modo de skills efectivo.
    """
    registry_src = src_skills / "skills_registry.yaml"
    if not registry_src.is_file():
        return
    registry_dst = target / "skills_registry.yaml"
    if mode == "add-only" and registry_dst.exists():
        logger.info("    ⏭️  skills_registry.yaml preservado (add-only)")
        return
    shutil.copy2(registry_src, registry_dst)


# ---------------------------------------------------------------------------
# README
# ---------------------------------------------------------------------------


def generate_readme(project: Project, dry_run: bool) -> bool:
    """Genera/actualiza README.md del proyecto.

    Usa agentes y skills descubiertos dinámicamente de la fuente (SSOT),
    sin listas hardcode que queden obsoletas.

    Args:
        project: Proyecto destino.
        dry_run: Si True, solo simula.

    Returns:
        True si el README fue (o sería) actualizado.
    """
    skills = _discover_skills()
    agents = _discover_agents()

    skills_list = "\n".join(f"  - `{s}`" for s in skills)
    agents_list = "\n".join(f"  - `{a}`" for a in agents)

    content = f"""# ⚙️ {project.name} — Sistema Multi-Agente Evolutivo

**{project.description}**

> Este proyecto utiliza el **Swarmind Harness** (Opción A: cerebro global en
> `~/.config/opencode/` + mirror local). opencode carga agentes, skills y
> core desde el global para TODOS los proyectos; el mirror local mantiene el
> proyecto abierto para cualquier editor.

---

## 🤖 Agentes ({len(agents)})

{agents_list}

---

## 🧠 Skills ({len(skills)} — potencia total)

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


def _seed_node_modules(dst_opencode: Path, dry_run: bool = False) -> int:
    """Copia node_modules del plugin SOLO si el destino no lo tiene.

    El plugin (.opencode/plugin/) requiere @opencode-ai/plugin en arranque;
    copiar 3667 archivos en cada deploy es lo que lo hacia lento. Primera
    vez se siembra completo; despues se omite (el lockfile manda).

    Args:
        dst_opencode: .opencode/ del proyecto destino.
        dry_run: Si True, solo simula.

    Returns:
        Número de archivos sembrados (0 si ya existía).
    """
    src_nm = _ROOT / ".opencode" / "node_modules"
    dst_nm = dst_opencode / "node_modules"
    if not src_nm.is_dir() or dst_nm.is_dir():
        return 0
    if not dry_run:
        shutil.copytree(src_nm, dst_nm, dirs_exist_ok=True)
    count = sum(1 for _ in src_nm.rglob("*") if _.is_file())
    logger.info("  🌱 node_modules sembrado (1ra vez): %d archivos", count)
    return count


def deploy_project(
    project: Project,
    dry_run: bool = False,
    sync_only: bool = False,
    force_mirror: bool = False,
) -> dict:
    """Despliega el mirror local completo a un proyecto.

    Carga la politica de ``<proyecto>/.opencode/deploy.yaml`` y la respeta:
    las skills se gobiernan por ``deploy_skills`` (excluidas de ``_sync_tree``)
    y ``opencode.exclude`` filtra el arbol del cerebro. El guard anti-TDR
    puede marcar el proyecto como ``blocked`` si la fuente trae ``num_ctx``
    16384 (evita re-propagar el BSOD 0x116).

    Args:
        project: Proyecto destino.
        dry_run: Si True, solo simula (no escribe nada).
        sync_only: Si True, no regenera README.
        force_mirror: Escape hatch que ignora la politica y aplica mirror.

    Returns:
        Dict con estadísticas del deploy (``status``: ok|blocked|skipped).
    """
    if not project.path.exists():
        logger.warning("  ❌ Project path not found: %s", project.path)
        return {"name": project.name, "status": "skipped", "reason": "path_not_found"}

    policy = _load_deploy_policy(project, force_mirror=force_mirror)

    logger.info("")
    logger.info("=" * 60)
    logger.info("📦 DEPLOYING: %s (%s) — mirror local", project.name, project.ptype)
    logger.info("=" * 60)

    # 1. Backup config propia (federated/, db/, .env, config/)
    saved_files: dict[str, bytes] = {}
    saved_dirs: dict[str, Path] = {}
    if not dry_run:
        saved_files, saved_dirs = _backup_config(project)

    # 2. Sync .opencode/ (cerebro mirror — agents, core, config). El subarbol
    #    skills/ se excluye: lo gobierna la politica via deploy_skills.
    logger.info("📁 .opencode/ — syncing cerebro mirror...")
    hidden = tuple(policy.opencode_exclude) + _SKILLS_SUBTREE_PATTERNS
    blocked: list[str] = []
    opencode_count = _sync_tree(
        _ROOT / ".opencode", project.path / ".opencode", dry_run,
        exclude=hidden, blocked=blocked,
    )
    opencode_count += _seed_node_modules(project.path / ".opencode", dry_run)
    logger.info("  ✅ .opencode/: %d archivos %s", opencode_count, "(simulado)" if dry_run else "")

    # 3. Motor (harness/): NO se copia a proyectos (estándar v2.5).
    #    Una sola copia vive en ~/.config/opencode/harness.
    #    Projects importan desde el global via PYTHONPATH si lo necesitan.
    logger.info("📁 harness/ — SKIPPED (una sola copia en opencode global, estandar v2.5)")
    harness_count = 0

    # 4. Skills: segun politica (mirror/add-only/skip + exclude)
    logger.info("🧠 skills — politica: %s", policy.skills_mode)
    skills_count = deploy_skills(project, dry_run, policy=policy)
    logger.info("  ✅ skills: %d %s", skills_count, "(simulado)" if dry_run else "")

    # 5. Restaurar config propia
    if not dry_run:
        _restore_config(project, saved_files, saved_dirs)

    # 6. README
    if not sync_only:
        logger.info("📄 README.md — generando...")
        generate_readme(project, dry_run)
        logger.info("  ✅ README.md %s", "(simulado)" if dry_run else "actualizado")

    status = "blocked" if blocked else "ok"
    if blocked:
        logger.error("  ⛔ %s BLOCKED por guard anti-TDR (%d escrituras)", project.name, len(blocked))
    return {
        "name": project.name,
        "type": project.ptype,
        "opencode_files": opencode_count,
        "harness_files": harness_count,
        "skills_deployed": skills_count,
        "status": status,
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
    opencode_count += _seed_node_modules(hermes.path / ".opencode", dry_run)

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
    parser.add_argument("--force-mirror", action="store_true",
                        help="Ignora la politica y aplica mirror a todos (escape hatch)")
    parser.add_argument("--sync-global", action="store_true",
                        help="Solo sincronizar el global opencode (no tocar proyectos)")
    parser.add_argument("--sync-harness-global", action="store_true",
                        help="Solo sync harness -> opencode global (una copia SSOT, v2.5)")
    args = parser.parse_args()

    # ── Solo sync global ──
    if args.sync_global:
        from sync_opencode_global import sync_global
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
    logger.info("   Raiz proyectos:  %s", _DEV_SPACE)
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
        all_stats.append(deploy_project(
            selected, dry_run=args.dry_run, sync_only=args.sync_only,
            force_mirror=args.force_mirror,
        ))
    else:
        for project in projects:
            all_stats.append(deploy_project(
                project, dry_run=args.dry_run, sync_only=args.sync_only,
                force_mirror=args.force_mirror,
            ))

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
        if s.get("status") == "blocked":
            logger.error(
                "  ⛔ %-25s | BLOCKED por guard anti-TDR (num_ctx=16384)",
                s.get("name", "?"),
            )
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
