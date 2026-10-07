"""Hermes Agent Builder — Construye agentes que funcionan, elimina el resto.

Observa la cognition store (asi_cognition_store) buscando patrones de tareas
exitosas. Cuando un tipo de tarea se repite N veces con alta puntuacion,
genera un perfil de agente especializado en .opencode/agents/auto/.

Si un agente generado no se usa en 30 dias o tiene baja puntuacion,
se elimina automaticamente.

MENOS CODIGO: elimina la necesidad de mantener 21+ profiles a mano.
El sistema descubre y construye solo los agentes que realmente se usan.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, ClassVar

import numpy as np
import yaml

from harness.memory_rag.lance_vector_store import LanceVectorStore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

AUTO_AGENTS_DIR = Path(__file__).resolve().parent.parent.parent / ".opencode" / "agents" / "auto"
COGNITION_COLLECTION = "asi_cognition_store"
AGENT_WORKSPACE_COLLECTION = "agent_workspace_logs"

# Thresholds
EMBEDDING_DIM = 384
MIN_SUCCESSFUL_TASKS = 3       # minimas tareas exitosas para crear agente
MIN_AVG_SCORE = 0.6            # puntuacion minima promedio
MAX_AGENT_AGE_DAYS = 30        # dias sin uso antes de prunear
SCORE_WINDOW_DAYS = 7          # ventana para calcular puntuacion


# ---------------------------------------------------------------------------
# Helpers de modulo (FSZ: mantienen las clases por debajo de 30 lineas)
# ---------------------------------------------------------------------------


def _is_outside_window(created_at: str) -> bool:
    """Indica si una leccion quedo fuera de la ventana temporal.

    Args:
        created_at: Fecha ISO 8601 de creacion ("" si no existe).

    Returns:
        True si la leccion es mas antigua que SCORE_WINDOW_DAYS.
    """
    if not created_at:
        return False
    try:
        created = datetime.fromisoformat(created_at)
        return datetime.now(UTC) - created > timedelta(days=SCORE_WINDOW_DAYS)
    except (ValueError, TypeError):
        return False


def _time_since_last_use(last_used: str) -> timedelta | None:
    """Calcula el tiempo transcurrido desde el ultimo uso de un agente.

    Args:
        last_used: Fecha ISO 8601 del ultimo uso.

    Returns:
        timedelta transcurrido, o None si la fecha no es parseable.
    """
    try:
        last = datetime.fromisoformat(last_used)
        return datetime.now(UTC) - last
    except (ValueError, TypeError):
        return None


def _extract_tags_and_triggers(
    lessons: list[dict[str, Any]], domain: str
) -> tuple[list[str], list[str]]:
    """Extrae capacidades y triggers a partir de las lecciones.

    Args:
        lessons: Lecciones del dominio origen.
        domain: Dominio base, usado como fallback.

    Returns:
        Tupla ``(capabilities, triggers)`` ya ordenadas y truncadas.
    """
    all_tags: set[str] = set()
    all_triggers: set[str] = set()
    for lesson in lessons:
        for tag in lesson.get("tags", []):
            if isinstance(tag, str):
                all_tags.add(tag.lower())
        content = lesson.get("content", "").lower()
        for word in content.split()[:20]:
            word = word.strip(".,!?;:")
            if len(word) > 4:
                all_triggers.add(word)
    capabilities = sorted(all_tags)[:8] if all_tags else ["automation", domain]
    triggers = sorted(all_triggers)[:10] if all_triggers else [domain]
    return capabilities, triggers


def _render_profile_header(
    agent_name: str,
    domain: str,
    capabilities: list[str],
    triggers: list[str],
    description: str,
) -> str:
    """Ensambla el encabezado YAML y el titulo del perfil de agente.

    Args:
        agent_name: Slug del agente.
        domain: Dominio del agente.
        capabilities: Capacidades detectadas.
        triggers: Triggers detectados.
        description: Descripcion legible del agente.

    Returns:
        Encabezado markdown del perfil.
    """
    aliases = agent_name.split("-")[0]
    return (
        "---\n"
        f"name: {agent_name}\n"
        f"domain: {domain}\n"
        f"triggers: {yaml.dump(triggers, default_flow_style=True).strip()}\n"
        f"capabilities: {yaml.dump(capabilities, default_flow_style=True).strip()}\n"
        f"aliases: [{aliases}]\n"
        f"description: {description}\n"
        "---\n\n"
        f"# {agent_name}\n\n"
        f"{description}\n\n"
        "## Capacidades\n\n"
    )


def _render_profile(
    agent_name: str,
    domain: str,
    capabilities: list[str],
    triggers: list[str],
    description: str,
) -> str:
    """Ensambla el contenido markdown completo del perfil de agente.

    Args:
        agent_name: Slug del agente.
        domain: Dominio del agente.
        capabilities: Capacidades detectadas.
        triggers: Triggers detectados.
        description: Descripcion legible del agente.

    Returns:
        Contenido markdown listo para escribir en disco.
    """
    header = _render_profile_header(
        agent_name, domain, capabilities, triggers, description
    )
    capabilities_block = "".join(f"- {cap}\n" for cap in capabilities)
    triggers_block = "".join(f"- {trig}\n" for trig in triggers[:5])
    footer = (
        f"*Generado por Hermes AgentBuilder el "
        f"{datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}*\n"
    )
    return (
        header + capabilities_block + "\n## Triggers\n\n"
        + triggers_block + "\n---\n" + footer
    )


def _decode_metadata(entry: dict[str, Any]) -> dict[str, Any]:
    """Decodifica el metadata de un log (puede venir como str JSON).

    Args:
        entry: Resultado crudo del vector store.

    Returns:
        Metadata como diccionario (vacio si no es decodificable).
    """
    meta = entry.get("metadata", {})
    if isinstance(meta, str):
        import json
        try:
            meta = json.loads(meta)
        except (json.JSONDecodeError, TypeError):
            return {}
    return meta


def _summarize_usage(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Resume los logs de uso de un agente.

    Args:
        results: Resultados crudos del vector store.

    Returns:
        Dict con ``last_used``, ``task_count`` y ``avg_score``.
    """
    summary: dict[str, Any] = {
        "last_used": "",
        "task_count": len(results),
        "avg_score": 0.0,
    }
    if not results:
        return summary
    scores: list[float] = []
    last = ""
    for result in results:
        created = _decode_metadata(result).get("created_at", "")
        if created and created > last:
            last = created
        score = result.get("score", 0.0)
        if score > 0:
            scores.append(score)
    summary["last_used"] = last
    if scores:
        summary["avg_score"] = sum(scores) / len(scores)
    return summary


# ---------------------------------------------------------------------------
# AgentBuilder
# ---------------------------------------------------------------------------


class AgentBuilder:
    """
    Construye agentes especializados desde patrones de tareas exitosas.
    
    Flujo:
      1. Escanea asi_cognition_store buscando lessons agrupables por dominio
      2. Si hay MIN_SUCCESSFUL_TASKS lessons en un dominio con score > MIN_AVG_SCORE
      3. Genera un perfil .md en .opencode/agents/auto/{slug}.md
      4. El agente es auto-descubierto por agent_discovery.py en el proximo ciclo
    """

    def __init__(self, vector_store: LanceVectorStore | None = None):
        self._store = vector_store or LanceVectorStore()
        self._stats: dict[str, Any] = {
            "agents_created": 0,
            "candidates_found": 0,
            "errors": 0,
        }

    def build_agents_from_cognition(self) -> list[str]:
        """
        Escanea cognition store y crea agentes para dominios recurrentes.
        
        Returns:
            Lista de nombres de agentes creados.
        """
        os.makedirs(str(AUTO_AGENTS_DIR), exist_ok=True)

        # 1. Obtener lessons agrupables
        lessons = self._fetch_lessons()
        if not lessons:
            logger.info("No cognition lessons found to build agents from.")
            return []

        # 2. Agrupar por dominio
        domains = self._group_by_domain(lessons)
        self._stats["candidates_found"] = len(domains)

        # 3. Crear agente para cada dominio que cumpla thresholds
        created: list[str] = []
        for domain, domain_lessons in domains.items():
            avg_score = self._domain_avg_score(domain_lessons)
            if avg_score is None:
                continue
            agent_name = self._create_agent_profile(domain, domain_lessons, avg_score)
            if agent_name:
                created.append(agent_name)
                self._stats["agents_created"] += 1

        self._log_build_summary(created, len(domains))
        return created

    def _domain_avg_score(self, lessons: list[dict[str, Any]]) -> float | None:
        """Calcula el score promedio si el dominio cumple los thresholds.

        Args:
            lessons: Lecciones del dominio a evaluar.

        Returns:
            Score promedio, o None si el dominio no califica para un agente.
        """
        if len(lessons) < MIN_SUCCESSFUL_TASKS:
            return None
        avg_score = sum(
            lesson.get("metrics", {}).get("overall_score", 0)
            for lesson in lessons
        ) / len(lessons)
        if avg_score < MIN_AVG_SCORE:
            return None
        return avg_score

    @staticmethod
    def _log_build_summary(created: list[str], domain_count: int) -> None:
        """Registra el resultado de la construccion de agentes.

        Args:
            created: Nombres de agentes creados.
            domain_count: Numero de dominios candidatos evaluados.
        """
        if created:
            logger.info(
                "Built %d agent(s) from cognition: %s",
                len(created), ", ".join(created),
            )
        else:
            logger.info(
                "No new agents built (%d candidates, avg_score<%.2f or n<%d)",
                domain_count, MIN_AVG_SCORE, MIN_SUCCESSFUL_TASKS,
            )

    def _fetch_lessons(self) -> list[dict[str, Any]]:
        """Obtiene lessons recientes de la cognition store."""
        try:
            dummy = np.zeros(EMBEDDING_DIM, dtype=np.float32)
            results = self._store.search(
                COGNITION_COLLECTION, dummy, top_k=200
            )
            lessons = []
            for r in results:
                meta = r.get("metadata", {})
                if isinstance(meta, str):
                    import json
                    try:
                        meta = json.loads(meta)
                    except (json.JSONDecodeError, TypeError):
                        meta = {}
                metrics = meta.get("metrics", {})
                if isinstance(metrics, str):
                    try:
                        metrics = json.loads(metrics)
                    except (json.JSONDecodeError, TypeError):
                        metrics = {}
                meta["metrics"] = metrics
                lessons.append(meta)
            return lessons
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to fetch cognition lessons: %s", exc)
            return []

    @staticmethod
    def _group_by_domain(
        lessons: list[dict[str, Any]],
    ) -> dict[str, list[dict[str, Any]]]:
        """Agrupa lessons por dominio.

        Args:
            lessons: Lista de dicts de lecciones con key 'domain'
                (ej. "trading.ml") y 'created_at' opcional.

        Returns:
            Dict {dominio_base: [lessons]} filtrando las fuera de
            la ventana de tiempo (SCORE_WINDOW_DAYS).
        """
        groups: dict[str, list[dict[str, Any]]] = {}
        for lesson in lessons:
            if _is_outside_window(lesson.get("created_at", "")):
                continue  # saltar lessons viejas
            domain = lesson.get("domain", "general")
            # Extraer dominio base (antes del primer .)
            base_domain = domain.split(".")[0] if "." in domain else domain
            groups.setdefault(base_domain, []).append(lesson)
        return groups

    def _create_agent_profile(
        self, domain: str, lessons: list[dict[str, Any]], avg_score: float
    ) -> str | None:
        """
        Crea un perfil de agente .md en .opencode/agents/auto/.
        
        El perfil incluye:
          - Triggers inferidos de las lessons
          - Capacidades derivadas de los tags
          - Descripcion basada en el dominio
        """
        # Generar nombre del agente
        slug = re.sub(r"[^a-z0-9]+", "-", domain.lower()).strip("-")[:40]
        if not slug:
            slug = f"auto-agent-{len(lessons)}"

        capabilities, triggers = _extract_tags_and_triggers(lessons, domain)

        # Construir descripcion
        description = (
            f"Auto-generado desde {len(lessons)} tareas exitosas "
            f"en dominio '{domain}' (score: {avg_score:.2f}). "
            f"Especialista en {', '.join(capabilities[:3])}."
        )

        profile_content = _render_profile(
            agent_name=slug,
            domain=domain,
            capabilities=capabilities,
            triggers=triggers,
            description=description,
        )
        return self._write_profile(slug, profile_content, len(lessons), avg_score)

    def _write_profile(
        self,
        agent_name: str,
        profile_content: str,
        lesson_count: int,
        avg_score: float,
    ) -> str | None:
        """Escribe el perfil en disco y registra el resultado.

        Args:
            agent_name: Nombre/slug del agente.
            profile_content: Contenido markdown del perfil.
            lesson_count: Numero de lecciones que originaron el agente.
            avg_score: Score promedio del dominio.

        Returns:
            Nombre del agente si se escribio, None si fallo.
        """
        filepath = AUTO_AGENTS_DIR / f"{agent_name}.md"
        try:
            filepath.write_text(profile_content, encoding="utf-8")
            logger.info(
                "Created agent profile: %s (%d lessons, score=%.2f)",
                filepath.relative_to(AUTO_AGENTS_DIR.parent.parent.parent),
                lesson_count, avg_score,
            )
            return agent_name
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to write agent profile %s: %s", filepath, exc)
            self._stats["errors"] += 1
            return None

    def get_stats(self) -> dict[str, Any]:
        """Return builder statistics."""
        return dict(self._stats)


# ---------------------------------------------------------------------------
# AgentPruner
# ---------------------------------------------------------------------------


class AgentPruner:
    """
    Elimina agentes que no funcionan.
    
    Criterios de eliminacion:
      - No usado en MAX_AGENT_AGE_DAYS dias (sin entradas en agent_workspace_logs)
      - Puntuacion promedio baja (< MIN_AVG_SCORE)
      - Es un agente auto-generado (en .opencode/agents/auto/)
    
    Los 5 roles universales NUNCA se eliminan.
    """

    # Roles que nunca se prunean
    PROTECTED_ROLES: ClassVar[set[str]] = {"coordinator", "builder", "scientist", "guardian", "evolve"}

    def __init__(self, vector_store: LanceVectorStore | None = None):
        self._store = vector_store or LanceVectorStore()
        self._stats: dict[str, Any] = {
            "pruned": 0,
            "protected": 0,
            "errors": 0,
        }

    def prune_underperforming(self, dry_run: bool = False) -> list[str]:
        """
        Elimina agentes auto-generados que no cumplen los thresholds.
        
        Args:
            dry_run: Si True, solo muestra que se eliminaria sin hacerlo.
        
        Returns:
            Lista de agentes eliminados (o por eliminar en dry-run).
        """
        auto_agents = self._list_auto_agents()
        if auto_agents is None:
            return []

        usage = self._get_agent_usage(auto_agents)
        pruned: list[str] = []
        for agent_file in auto_agents:
            agent_name = agent_file.stem
            if agent_name in self.PROTECTED_ROLES:
                self._stats["protected"] += 1
                continue
            reasons = self._prune_reasons(usage.get(agent_name, {}))
            if reasons:
                pruned.append(agent_name)
                self._prune_agent(agent_file, reasons, dry_run)

        self._log_prune_summary(pruned, len(auto_agents), dry_run)
        return pruned

    @staticmethod
    def _list_auto_agents() -> list[Path] | None:
        """Lista los agentes auto-generados o None si no hay nada que podar.

        Returns:
            Lista ordenada de archivos .md, o None si el directorio no
            existe o esta vacio.
        """
        auto_dir = AUTO_AGENTS_DIR
        if not auto_dir.exists():
            logger.info("No auto agents directory: %s", auto_dir)
            return None
        auto_agents = sorted(auto_dir.glob("*.md"))
        if not auto_agents:
            logger.info("No auto-generated agents to prune.")
            return None
        return auto_agents

    @staticmethod
    def _prune_reasons(info: dict[str, Any]) -> list[str]:
        """Determina los motivos por los que un agente debe prunearse.

        Args:
            info: Metricas de uso del agente (last_used, avg_score, task_count).

        Returns:
            Lista de motivos; vacia si el agente no debe prunearse.
        """
        reasons: list[str] = []
        last_used = info.get("last_used", "")
        avg_score = info.get("avg_score", 0.0)
        task_count = info.get("task_count", 0)

        if last_used:
            age = _time_since_last_use(last_used)
            if age is not None and age > timedelta(days=MAX_AGENT_AGE_DAYS):
                reasons.append(f"not used in {age.days}d (> {MAX_AGENT_AGE_DAYS}d)")
        elif task_count == 0:
            reasons.append("never used")

        if task_count > 0 and avg_score < MIN_AVG_SCORE and avg_score > 0:
            reasons.append(f"low avg score ({avg_score:.2f} < {MIN_AVG_SCORE})")

        return reasons

    def _prune_agent(
        self, agent_file: Path, reasons: list[str], dry_run: bool
    ) -> None:
        """Elimina (o simula eliminar) un agente bajo rendimiento.

        Args:
            agent_file: Archivo .md del agente a podar.
            reasons: Motivos del pruneo, usados en el log.
            dry_run: Si True, solo registra la accion sin borrar archivos.
        """
        agent_name = agent_file.stem
        reason_str = ", ".join(reasons)

        if dry_run:
            logger.info("[DRY-RUN] Would prune '%s': %s", agent_name, reason_str)
            return

        try:
            agent_file.unlink()
            # Also remove .agent.min.md if exists
            min_file = agent_file.with_suffix(".agent.min.md")
            if min_file.exists():
                min_file.unlink()
            logger.info("Pruned agent '%s': %s", agent_name, reason_str)
            self._stats["pruned"] += 1
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to prune '%s': %s", agent_name, exc)
            self._stats["errors"] += 1

    @staticmethod
    def _log_prune_summary(pruned: list[str], evaluated: int, dry_run: bool) -> None:
        """Registra el resumen de la poda de agentes.

        Args:
            pruned: Nombres de agentes podados (o por podar en dry-run).
            evaluated: Cantidad de agentes evaluados.
            dry_run: Si True, omite el log de resumen real.
        """
        if not dry_run and pruned:
            logger.info("Pruned %d agent(s): %s", len(pruned), ", ".join(pruned))
        elif not pruned:
            logger.info("No agents needed pruning (%d evaluated).", evaluated)

    def _get_agent_usage(
        self, agent_files: list[Path],
    ) -> dict[str, dict[str, Any]]:
        """Obtiene metricas de uso para cada agente desde agent_workspace_logs.

        Args:
            agent_files: Archivos de agente a consultar.

        Returns:
            Dict {agent_name: {last_used, task_count, avg_score}}.
        """
        usage: dict[str, dict[str, Any]] = {}
        for agent_file in agent_files:
            agent_name = agent_file.stem
            usage[agent_name] = {
                "last_used": "",
                "task_count": 0,
                "avg_score": 0.0,
            }
            try:
                results = self._search_agent_logs(agent_name)
            except Exception as _exc:  # noqa: BLE001
                logger.warning("agent_builder: %s", _exc)
                continue
            usage[agent_name].update(_summarize_usage(results))

        return usage

    def _search_agent_logs(self, agent_name: str) -> list[dict[str, Any]]:
        """Consulta los workspace logs asociados a un agente.

        Args:
            agent_name: Nombre del agente (sin extension).

        Returns:
            Lista de resultados crudos del vector store.
        """
        dummy = np.zeros(EMBEDDING_DIM, dtype=np.float32)
        return self._store.search(
            AGENT_WORKSPACE_COLLECTION, dummy, top_k=100,
            filters={"to_agent": f"@{agent_name}"},
        )

    def get_stats(self) -> dict[str, Any]:
        """Return pruner statistics."""
        return dict(self._stats)


# ---------------------------------------------------------------------------
# CLI command helper
# ---------------------------------------------------------------------------


def run_agent_evolution(dry_run: bool = False) -> dict[str, Any]:
    """
    Ejecuta el ciclo completo de evolucion de agentes:
    1. Construye nuevos agentes desde cognition store
    2. Elimina agentes que no funcionan
    
    Args:
        dry_run: Si True, no hace cambios.
    
    Returns:
        Dict con estadisticas de build y prune.
    """
    store = LanceVectorStore()
    builder = AgentBuilder(vector_store=store)
    pruner = AgentPruner(vector_store=store)

    built = builder.build_agents_from_cognition()
    pruned = pruner.prune_underperforming(dry_run=dry_run)

    return {
        "built": built,
        "pruned": pruned,
        "builder_stats": builder.get_stats(),
        "pruner_stats": pruner.get_stats(),
    }
