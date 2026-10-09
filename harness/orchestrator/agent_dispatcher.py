"""
Agent Dispatcher — Skill-aware task routing.

Finds relevant procedural skills for a task description and includes them
in the dispatch context if the match is strong enough (>70% similarity).
"""

from __future__ import annotations

import functools
import logging
import os
from pathlib import Path
from typing import Any

import numpy as np

from harness.context.skill_inherit import (
    CompositionError,
    parse_inherit,
    resolve_inherit,
)
from harness.evolve_loop.skill_generator import REGISTRY_PATH, SkillGenerator
from harness.memory_rag.lance_vector_store import (
    COLLECTION_PROCEDURAL_SKILLS,
    LanceVectorStore,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SIMILARITY_THRESHOLD = 0.70  # 70% match to load skill

#: Env que habilita la inyeccion de la herencia (`inherit:`) en el runtime.
#: Default OFF para no inflar el contexto (TKN-safe).
ENV_INHERIT_INJECT = "SWARMIND_SKILL_INHERIT_INJECT"

#: Valores (case-insensitive) que activan la inyeccion de herencia.
_INHERIT_TRUTHY = frozenset({"1", "true", "yes", "on"})

#: Raiz contra la que se resuelven las rutas de `inherit:` (frontmatter).
_OPENCODE_BASE_DIR = Path(".opencode")

#: Marcador que separa el contenido del skill de su herencia anexada.
_INHERIT_SEPARATOR = "\n\n<!-- SWARMIND:SKILL-INHERIT-BEGIN -->\n"


# ---------------------------------------------------------------------------
# Inheritance helpers (best-effort, nunca lanzan)
# ---------------------------------------------------------------------------


def _inherit_inject_enabled() -> bool:
    """Indica si la inyeccion de herencia esta habilitada por variable de entorno.

    Lee ``SWARMIND_SKILL_INHERIT_INJECT`` y la considera activa solo si vale
    ``1/true/yes/on`` (case-insensitive). Default OFF.

    Returns:
        ``True`` si la env esta en un valor afirmativo; ``False`` en caso contrario.
    """
    raw = os.getenv(ENV_INHERIT_INJECT, "")
    return raw.strip().lower() in _INHERIT_TRUTHY


def _should_inject_inherit(include_inherit: bool | None) -> bool:
    """Resuelve si se debe inyectar la herencia segun flag explicito o env.

    Args:
        include_inherit: ``True``/``False`` fuerzan la decision; ``None`` delega
            en :func:`_inherit_inject_enabled`.

    Returns:
        ``True`` si procede anexar el contenido heredado; ``False`` si no.
    """
    if include_inherit is not None:
        return include_inherit
    return _inherit_inject_enabled()


def _append_inherit(content: str, path: str) -> str:
    """Anexa el contenido de la herencia declarada al del skill (best-effort).

    Args:
        content: Contenido base del skill ya leido.
        path: Ruta del ``SKILL.md`` que declara ``inherit:``.

    Returns:
        ``content`` mas la herencia separada por marcador si resuelve; el
        ``content`` base si no hay herencia o si su resolucion falla.
        Nunca lanza: degrada con ``logger.warning``.

    Raises:
        No aplica: los errores de resolucion se capturan y registran.
    """
    try:
        resolution = resolve_inherit(Path(path), _OPENCODE_BASE_DIR)
    except (CompositionError, OSError, UnicodeError) as exc:
        logger.warning(
            "agent_dispatcher: WHAT: herencia no resuelta para '%s': %s. "
            "WHY: la ruta declarada en 'inherit:' falta o escapa .opencode/. "
            "WHERE: _append_inherit",
            path,
            exc,
        )
        return content
    if not resolution.content.strip():
        return content
    return f"{content}{_INHERIT_SEPARATOR}{resolution.content}"


def _resolve_inherit_meta(path: str) -> tuple[tuple[str, ...], bool]:
    """Resuelve (best-effort) las rutas heredadas declaradas y su integridad.

    Args:
        path: Ruta del ``SKILL.md`` (puede estar vacia o no existir).

    Returns:
        Tupla ``(declared, ok)``: rutas declaradas en ``inherit:`` (``()`` si no
        hay) y ``True`` si todas resuelven; ``False`` si alguna falta, escapa
        ``.opencode/`` o el frontmatter es invalido. Nunca lanza.

    Raises:
        No aplica: fallos de parseo/resolucion se capturan y registran.
    """
    if not path:
        return (), True
    skill_md = Path(path)
    try:
        declared = parse_inherit(skill_md)
    except (CompositionError, OSError, UnicodeError) as exc:
        logger.warning(
            "agent_dispatcher: WHAT: no se pudo parsear 'inherit:' en '%s': %s. "
            "WHERE: _resolve_inherit_meta",
            path,
            exc,
        )
        return (), False
    if not declared:
        return (), True
    try:
        resolution = resolve_inherit(skill_md, _OPENCODE_BASE_DIR)
    except (CompositionError, OSError, UnicodeError) as exc:
        logger.warning(
            "agent_dispatcher: WHAT: herencia declarada no resuelve en '%s': %s. "
            "WHY: artefacto heredado ausente o path traversal. "
            "WHERE: _resolve_inherit_meta",
            path,
            exc,
        )
        return declared, False
    return resolution.declared, True


def _resolve_skill_path_by_name(name: str) -> str:
    """Resuelve la ruta de un skill curado por nombre (fallback de ``path``).

    WHAT: busca ``.opencode/skills/<name>/SKILL.md`` y, como respaldo, un glob
    ``**/<name>/SKILL.md`` bajo la raiz de skills. WHY: el registry curado puede
    no declarar ``path``; sin resolver, el ``content`` del skill quedaba vacio.
    WHERE: ``AgentDispatcher.find_skill_for_task``.

    Args:
        name: Nombre del skill (p. ej. ``"security-audit"``).

    Returns:
        Ruta existente (str) o ``""`` si no se encuentra.
    """
    if not name:
        return ""
    skills_root = Path(REGISTRY_PATH).parent
    direct = skills_root / name / "SKILL.md"
    if direct.exists():
        return str(direct)
    for found in skills_root.glob(f"**/{name}/SKILL.md"):
        if found.exists():
            return str(found)
    return ""


# ---------------------------------------------------------------------------
# AgentDispatcher
# ---------------------------------------------------------------------------


class AgentDispatcher:
    """
    Dispatches tasks to agents with optional skill injection.

    If a relevant skill exists (from skills_registry.yaml or LanceDB
    ``procedural_skills``), its .md content is included in the dispatch
    context so the agent can reuse known patterns.
    """

    def __init__(self, vector_store: LanceVectorStore | None = None) -> None:
        """Inicializa la instancia de la clase."""
        self._vector_store = vector_store
        self._stats: dict[str, Any] = {
            "total_dispatches": 0,
            "skill_matches": 0,
            "no_skill_matches": 0,
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def find_skill_for_task(self, task_description: str) -> dict[str, Any] | None:
        """
        Find the best-matching skill for a task description.

        Search order:
          1. YAML registry (``skills_registry.yaml``) — keyword match.
          2. LanceDB ``procedural_skills`` — vector similarity.

        Returns:
            The best-matching skill dict with keys (name, path, domain, agent,
            trigger, content, similarity), or ``None``.
        """
        # Lazy import: yaml solo se necesita si hay registro YAML que leer
        import yaml  # noqa: F401

        query_lower = task_description.lower()

        # --- 1. Check YAML registry ---
        registry_match = SkillGenerator.find_in_registry(query_lower)
        if registry_match:
            skill_path = registry_match.get("path", "") or _resolve_skill_path_by_name(
                str(registry_match.get("name", ""))
            )
            content = self._read_skill_md(skill_path) if skill_path else ""
            inherited, inherited_ok = _resolve_inherit_meta(skill_path)
            logger.info(
                "Skill found in YAML registry: %s (path=%s)",
                registry_match.get("name"),
                skill_path,
            )
            return {
                **registry_match,
                "content": content,
                "similarity": 0.80,  # YAML keyword match = strong
                "inherited": inherited,
                "inherited_ok": inherited_ok,
            }

        # --- 2. Search LanceDB procedural_skills ---
        if self._vector_store is not None:
            lancedb_match = self._search_lancedb_skills(query_lower)
            if lancedb_match and lancedb_match.get("similarity", 0) >= SIMILARITY_THRESHOLD:
                return lancedb_match

        logger.debug("No skill found for: %s", task_description[:80])
        return None

    def dispatch(self, agent_role: str, task_description: str) -> dict[str, Any]:
        """
        Dispatch a task to an agent, optionally including skill context.

        Args:
            agent_role: The target agent (e.g. "software-engineer").
            task_description: What needs to be done.

        Returns:
            Dict with:
              - ``agent``: The target agent role.
              - ``task``: The task description.
              - ``used_skill``: Whether a skill was injected.
              - ``skill_context``: The skill .md content (or empty str).
              - ``reasoning_mode``: "from_scratch" or "guided_by_skill".
        """
        self._stats["total_dispatches"] += 1

        skill = self.find_skill_for_task(task_description)

        result: dict[str, Any] = {
            "agent": agent_role,
            "task": task_description,
            "used_skill": False,
            "skill_context": "",
            "reasoning_mode": "from_scratch",
        }

        if skill is not None and skill.get("similarity", 0) >= SIMILARITY_THRESHOLD:
            result["used_skill"] = True
            result["skill_context"] = skill.get("content", "")
            result["reasoning_mode"] = "guided_by_skill"
            result["skill_name"] = skill.get("name", "")
            self._stats["skill_matches"] += 1
            logger.info(
                "Dispatch @%s guided by skill '%s' (sim=%.2f)",
                agent_role,
                skill.get("name"),
                skill.get("similarity", 0),
            )
        else:
            result["reasoning_mode"] = "from_scratch"
            self._stats["no_skill_matches"] += 1
            logger.info(
                "Dispatch @%s from scratch (no skill match > %.0f%%)",
                agent_role,
                SIMILARITY_THRESHOLD * 100,
            )

        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _search_lancedb_skills(self, query: str) -> dict[str, Any] | None:
        """Search for skills in LanceDB procedural_skills collection."""
        if self._vector_store is None:
            return None

        # Build embedding for query
        dim = 384
        vec = np.zeros(dim, dtype=np.float32)
        for i, ch in enumerate(query.encode("utf-8", errors="replace")):
            idx = (i * 7 + ch) % dim
            vec[idx] += 1.0
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm

        try:
            results = self._vector_store.search(
                COLLECTION_PROCEDURAL_SKILLS, vec, top_k=3
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("LanceDB skill search failed: %s", exc)
            return None

        if not results:
            return None

        # Take best result with metadata
        best = results[0]
        meta = best.get("metadata", {})
        score = best.get("score", 0.0)

        if score < SIMILARITY_THRESHOLD:
            return None

        skill_name = meta.get("name", "")
        skill_path = str(
            Path(str(REGISTRY_PATH)).parent / "auto" / f"{skill_name}.md"
        )
        content = self._read_skill_md(skill_path)
        inherited, inherited_ok = _resolve_inherit_meta(skill_path)

        return {
            "name": skill_name,
            "path": skill_path,
            "domain": meta.get("domain", ""),
            "agent": meta.get("agent", ""),
            "trigger": meta.get("trigger", ""),
            "content": content,
            "similarity": score,
            "inherited": inherited,
            "inherited_ok": inherited_ok,
        }

    @staticmethod
    def _read_skill_file(path: str) -> str:
        """Lee el contenido crudo de un skill, prefiriendo la version .min.md.

        Args:
            path: Ruta del skill ``.md``.

        Returns:
            Contenido del ``.min.md`` si existe, si no el del ``.md``; cadena
            vacia si ninguno existe o falla la lectura (nunca lanza).

        Raises:
            No aplica: los errores de I/O se registran y degradan a ``""``.
        """
        try:
            p = Path(path)
            min_p = p.with_suffix('.min.md')
            if min_p.exists():
                return min_p.read_text(encoding='utf-8')
            if p.exists():
                return p.read_text(encoding='utf-8')
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "agent_dispatcher: WHAT: fallo leyendo skill '%s': %s. "
                "WHY: archivo inaccesible o corrupto. WHERE: _read_skill_file",
                path,
                exc,
            )
        return ""

    @staticmethod
    @functools.lru_cache(maxsize=64)
    def _read_skill_md(path: str, include_inherit: bool | None = None) -> str:
        """Read a skill .md file, prefer pre-compiled .min.md version.

        Si existe el archivo .min.md (pre-compilado), lo usa para ahorrar
        tokens (~40-60% menos). Si no, cae en el .md original.

        Args:
            path: Ruta del skill ``.md``.
            include_inherit: ``True`` anexa el contenido de ``inherit:``;
                ``False`` no lo anexa; ``None`` (default) usa la env
                ``SWARMIND_SKILL_INHERIT_INJECT`` (OFF por defecto).

        Returns:
            Contenido del skill; con la herencia anexada tras el marcador
            ``SWARMIND:SKILL-INHERIT-BEGIN`` cuando aplica. Cadena vacia si el
            archivo no existe.

        Raises:
            No aplica: nunca lanza; degrada con ``logger.warning``.
        """
        content = AgentDispatcher._read_skill_file(path)
        if not content or not _should_inject_inherit(include_inherit):
            return content
        return _append_inherit(content, path)

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        """Return dispatch statistics."""
        return dict(self._stats)

    def reset_stats(self) -> None:
        """Reset dispatch counters."""
        self._stats = {
            "total_dispatches": 0,
            "skill_matches": 0,
            "no_skill_matches": 0,
        }

    # ------------------------------------------------------------------
    # Async API
    # ------------------------------------------------------------------

    async def dispatch_async(
        self,
        agent_role: str,
        task_description: str,
        vector_store: Any | None = None,
        plan_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Version ASYNC de dispatch(). Ejecuta en PARALELO:
        1. Busqueda de skill en LanceDB
        2. Contexto RAG
        3. Mensajes recientes del agent_bus
        4. Plan de ejecución (si existe)

        Args:
            plan_context: Optional dict with plan info (from TaskOrchestrator).
                         Includes: session_id, plan_summary, current_level,
                         previous_results, communication_log.
        """
        import asyncio

        from harness.memory_rag.context_assembler import ContextAssembler
        from harness.orchestrator.agent_bus import AgentBus

        store = vector_store or LanceVectorStore()
        assembler = ContextAssembler(store)
        bus = AgentBus(vector_store=store)

        # Paralelizar: skill, RAG, mensajes, y formateo del plan
        skill_task = asyncio.to_thread(self.find_skill_for_task, task_description)
        context_task = asyncio.to_thread(
            assembler.assemble, task_description, agent_role
        )
        messages_task = asyncio.to_thread(
            bus.get_channel_history, f"@{agent_role}", 10
        )

        skill_result, context_result, messages = await asyncio.gather(
            skill_task, context_task, messages_task
        )

        result: dict[str, Any] = {
            "agent": agent_role,
            "task": task_description,
            "used_skill": skill_result is not None,
            "skill_context": skill_result.get("content", "") if skill_result else "",
            "rag_context": context_result,
            "recent_messages": messages,
            "reasoning_mode": "guided_by_skill" if skill_result else "from_scratch",
        }

        # Incluir plan context si existe (Plan-and-Execute)
        if plan_context:
            result["execution_plan"] = {
                "session_id": plan_context.get("session_id", ""),
                "plan_summary": plan_context.get("plan_summary", ""),
                "current_level": plan_context.get("current_level", []),
                "previous_results": plan_context.get("previous_results", []),
                "communication_log": plan_context.get("communication_log", []),
                "is_complete": plan_context.get("is_complete", False),
            }
            result["reasoning_mode"] = "guided_by_plan"

        return result

    async def dispatch_batch(
        self,
        tasks: list[tuple[str, str]],
        vector_store: Any | None = None,
    ) -> list[dict[str, Any]]:
        """
        Dispatch MULTIPLE tareas en PARALELO.
        Args:
            tasks: Lista de (agent_role, task_description)
        """
        import asyncio
        coros = [
            self.dispatch_async(role, task, vector_store)
            for role, task in tasks
        ]
        return await asyncio.gather(*coros)
