"""
Agent Dispatcher — Skill-aware task routing.

Finds relevant procedural skills for a task description and includes them
in the dispatch context if the match is strong enough (>70% similarity).
"""

from __future__ import annotations

import functools
import logging
import os
import re
from pathlib import Path
from typing import Any

import numpy as np

from harness.common import estimate_tokens
from harness.context.skill_inherit import (
    CompositionError,
    parse_inherit,
    resolve_inherit,
)
from harness.evolve_loop.feedback_scorer import score_outcome
from harness.evolve_loop.library_drift import LibraryDriftManager
from harness.evolve_loop.skill_generator import REGISTRY_PATH, SkillGenerator
from harness.memory_rag.lance_vector_store import (
    COLLECTION_PROCEDURAL_SKILLS,
    LanceVectorStore,
)
from harness.observability.token_telemetry import TokenTelemetry
from harness.orchestrator.hidden_body import (
    _body_keyword_score,
    combine_hidden_body_score,
    read_skill_body,
    tokenize,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SIMILARITY_THRESHOLD = 0.70  # 70% match to load skill

#: Rol con el que el dispatcher registra el uso de tokens (FR-2, ADR-0103).
DISPATCH_TELEMETRY_ROLE = "agent_dispatch"

#: Tokens de salida fijos por dispatch (una decision de despacho).
DISPATCH_OUTPUT_TOKENS = 1

#: Similitud de un match del registry YAML curado (keyword = senal fuerte).
_YAML_MATCH_SIMILARITY = 0.80

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
# Hard veto (anti-triggers) — Codex #34712 + ThakiCloud Description Budget
# ---------------------------------------------------------------------------
#
# WHAT: los anti-triggers en prosa de la ``description`` ("No usar para X",
# "Evitar Y", "Cuando NO usar", "anti-trigger") los IGNORA el routing implicito;
# el veto NEGATIVO debe vivir en el ROUTER (veto duro). WHY: el matching por
# tokens puede cargar una skill que explicitamente NO aplica a la tarea. WHERE:
# ``AgentDispatcher.find_skill_for_task`` (filtra el candidato ANTES del rank).

#: Anti-triggers en prosa cuyo contexto se inspecciona para vetar un candidato.
NEGATIVE_TRIGGER_RE = re.compile(
    r"(?:Cuando NO usar|No usar|Evitar|NO aplica|anti-trigger|sin )",
    re.IGNORECASE,
)

#: Caracteres de contexto tras el trigger anti-patron que se inspeccionan.
VETO_CONTEXT_CHARS = 60

#: Tokens minimos de interseccion clausula<->tarea para confirmar el veto.
VETO_TOKEN_MATCH = 1


def _skill_description(skill: Any) -> str:
    """Extrae el texto de ``description`` de un candidato de skill.

    WHAT: acepta dicts (``description``/``trigger``/``name``) o strings. WHY: el
    candidato del registry YAML trae ``description`` y el de LanceDB ``trigger``.

    Args:
        skill: Dict de skill o string con la descripcion.

    Returns:
        Texto de la description; ``""`` si no hay campo reconocible.
    """
    if isinstance(skill, str):
        return skill
    if isinstance(skill, dict):
        for key in ("description", "trigger", "name"):
            value = skill.get(key)
            if value:
                return str(value)
    return ""


def hard_veto_score(
    description: str,
    task_text: str,
    *,
    veto_context_chars: int = VETO_CONTEXT_CHARS,
    veto_token_match: int = VETO_TOKEN_MATCH,
) -> float:
    """Puntua si una description veta la tarea por anti-trigger (0.0 = veta).

    WHAT: detecta un anti-trigger (``No usar``, ``Evitar``, ``Cuando NO usar``,
    ``anti-trigger``, ``sin ``) en la ``description``; extrae la clausula
    siguiente (``veto_context_chars``) y, si sus tokens intersectan los de la
    tarea (``>= veto_token_match``), devuelve ``0.0`` (veta). WHY: un
    anti-trigger en prosa que menciona la tarea debe excluir al candidato ANTES
    del rank, no depender del veto implicito del LLM (Codex #34712). WHERE:
    ``AgentDispatcher.find_skill_for_task``.

    Args:
        description: Description del candidato (puede ser vacia).
        task_text: Texto de la tarea a rutear.
        veto_context_chars: Caracteres de contexto tras el trigger a inspeccionar.
        veto_token_match: Tokens minimos de interseccion para confirmar el veto.

    Returns:
        ``0.0`` si la description veta la tarea; ``1.0`` en caso contrario.
        Nunca lanza: sin clausula (contexto vacio) no hay veto.
    """
    if not description or not task_text:
        return 1.0
    match = NEGATIVE_TRIGGER_RE.search(description)
    if match is None:
        return 1.0
    context = max(veto_context_chars, 0)
    clause = description[match.end() : match.end() + context]
    clause_tokens = tokenize(clause)
    task_tokens = tokenize(task_text)
    if not clause_tokens or not task_tokens:
        return 1.0
    if len(clause_tokens & task_tokens) >= max(veto_token_match, 1):
        return 0.0
    return 1.0


def apply_hard_veto(skills_list: list[Any], task_text: str) -> list[Any]:
    """Filtra los candidatos que la tarea activa via anti-trigger.

    WHAT: aplica :func:`hard_veto_score` a cada candidato y conserva solo los que
    NO son vetados (score ``1.0``). WHY: excluir al candidato ANTES del rank
    evita que un anti-trigger en prosa pase desapercibido. WHERE:
    ``AgentDispatcher.find_skill_for_task``.

    Args:
        skills_list: Candidatos (dicts con description/trigger/name, o strings).
        task_text: Texto de la tarea a rutear.

    Returns:
        Lista filtrada en el orden original; vacia si todos fueron vetados.
    """
    return [
        skill
        for skill in skills_list
        if hard_veto_score(_skill_description(skill), task_text) > 0.0
    ]


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

    def __init__(
        self,
        vector_store: LanceVectorStore | None = None,
        *,
        telemetry: TokenTelemetry | None = None,
        drift_manager: LibraryDriftManager | None = None,
    ) -> None:
        """Inicializa la instancia de la clase.

        Args:
            vector_store: Store vectorial opcional para busqueda de skills.
            telemetry: Acumulador de telemetria de tokens (FR-2). Si es ``None``
                (default) no se registra nada: backward-compatible.
            drift_manager: Gestor de retiro por outcome (Library Drift). Si es
                ``None`` (default) el dispatcher no acumula utilidad de skills:
                backward-compatible.
        """
        self._vector_store = vector_store
        self._telemetry = telemetry
        self._drift_manager = drift_manager
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
        if registry_match and not apply_hard_veto([registry_match], task_description):
            # Veto duro (Codex #34712): la description del candidato contiene un
            # anti-trigger cuya clausula menciona la tarea -> se excluye antes
            # del rank (no se inyecta una skill que explicita "No usar para X").
            logger.info(
                "hard-veto: skill '%s' vetada para la tarea (anti-trigger)",
                registry_match.get("name"),
            )
            registry_match = None
        if registry_match:
            skill_path = registry_match.get("path", "") or _resolve_skill_path_by_name(
                str(registry_match.get("name", ""))
            )
            content = self._read_skill_md(skill_path) if skill_path else ""
            inherited, inherited_ok = _resolve_inherit_meta(skill_path)
            # Hidden-body (FR-C2): la metadata es asimetrica; se puntua el
            # CUERPO real y se combina 0.5/0.5 con la similitud del match YAML.
            body = read_skill_body(skill_path)
            body_score = _body_keyword_score(body, tokenize(task_description))
            similarity = (
                combine_hidden_body_score(_YAML_MATCH_SIMILARITY, body_score)
                if body
                else _YAML_MATCH_SIMILARITY
            )
            logger.info(
                "Skill found in YAML registry: %s (path=%s, body_score=%.2f)",
                registry_match.get("name"),
                skill_path,
                body_score,
            )
            return {
                **registry_match,
                "content": content,
                "similarity": similarity,  # YAML keyword + hidden-body
                "body_score": body_score,
                "inherited": inherited,
                "inherited_ok": inherited_ok,
            }

        # --- 2. Search LanceDB procedural_skills ---
        if self._vector_store is not None:
            lancedb_match = self._search_lancedb_skills(query_lower)
            if lancedb_match and lancedb_match.get("similarity", 0) >= SIMILARITY_THRESHOLD:
                if not apply_hard_veto([lancedb_match], task_description):
                    logger.info(
                        "hard-veto: skill '%s' vetada para la tarea (anti-trigger)",
                        lancedb_match.get("name"),
                    )
                    return None
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

        self._record_dispatch_telemetry(task_description, result["skill_context"])
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def record_skill_outcome(
        self, skill_name: str, *, success: bool, agent_role: str | None = None
    ) -> None:
        """Registra el outcome real de una skill usada en un dispatch.

        WHAT: (1) delega en ``LibraryDriftManager.record_outcome`` para
        evidencia de utilidad (recuperacion + helpful/hurt); (2) escribe la
        efectividad en las colecciones de valor ``skill_effectiveness`` y
        ``agent_performance`` via ``feedback_scorer`` (Item 1,
        docs/specs/memory-optimality.md). WHY: el outcome se conoce DESPUES
        de que el agente termina (no en ``dispatch``), asi que el caller que
        ejecuta la tarea invoca este metodo para cerrar el ciclo. WHERE:
        caller de ``AgentDispatcher`` tras evaluar el resultado; ambas
        acciones son best-effort y backward-compatible (no-op si faltan
        ``drift_manager``/``_vector_store``).

        Args:
            skill_name: Nombre del skill inyectado en el dispatch.
            success: ``True`` si la trayectoria guiada por el skill fue correcta.
            agent_role: Rol del agente que ejecuto (opcional; si se provee
                tambien se escribe ``agent_performance``).
        """
        if self._drift_manager is not None:
            self._drift_manager.record_outcome(skill_name, success=success, used=True)
        # Feedback en colecciones de valor (best-effort; jamas lanza).
        try:
            score_outcome(
                self._vector_store, skill_name,
                success=success, agent_role=agent_role,
            )
        except Exception:  # noqa: BLE001, S110
            pass

    def _record_dispatch_telemetry(self, task_description: str, skill_context: str) -> None:
        """Registra el uso de tokens del dispatch (FR-2, best-effort).

        WHAT: atribuye tokens al rol ``agent_dispatch``: ``cached`` = tokens del
        contexto de skill (prefijo reutilizable/cacheable) e ``input`` = tokens
        de la tarea del turno. WHY: sin un call site real la telemetria de
        cache-hit no es medible. WHERE: ``dispatch`` y ``dispatch_async``.

        No hace nada si no se inyecto ``telemetry`` (backward-compatible) y
        nunca lanza: un fallo de telemetria no debe romper el despacho.

        Args:
            task_description: Tarea del turno (entrada dinamica).
            skill_context: Contenido del skill inyectado (prefijo cacheable);
                cadena vacia si no hubo match.
        """
        if self._telemetry is None:
            return
        cached = estimate_tokens(skill_context, minimum=0)
        dynamic = estimate_tokens(task_description, minimum=0)
        try:
            self._telemetry.record_usage(
                DISPATCH_TELEMETRY_ROLE,
                cached=cached,
                input=dynamic,
                output=DISPATCH_OUTPUT_TOKENS,
            )
        except (ValueError, TypeError) as exc:
            logger.warning(
                "agent_dispatcher: WHAT: no se pudo registrar telemetria: %s. "
                "WHY: conteo invalido o rol vacio. "
                "WHERE: AgentDispatcher._record_dispatch_telemetry",
                exc,
            )

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
        # Hidden-body (FR-C2): combina el score vectorial con el del cuerpo.
        body = read_skill_body(skill_path)
        body_score = _body_keyword_score(body, tokenize(query))
        similarity = combine_hidden_body_score(score, body_score) if body else score

        return {
            "name": skill_name,
            "path": skill_path,
            "domain": meta.get("domain", ""),
            "agent": meta.get("agent", ""),
            "trigger": meta.get("trigger", ""),
            "content": content,
            "similarity": similarity,
            "body_score": body_score,
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

        self._record_dispatch_telemetry(
            task_description, result["skill_context"]
        )

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
