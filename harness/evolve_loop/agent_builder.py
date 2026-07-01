"""
Hermes Agent Builder — Construye agentes que funcionan, elimina el resto.

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
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np
import yaml

from harness.memory_rag.lance_vector_store import LanceVectorStore
from harness.orchestrator.agent_discovery import parse_agent_profile

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

AUTO_AGENTS_DIR = Path(__file__).resolve().parent.parent.parent / ".opencode" / "agents" / "auto"
COGNITION_COLLECTION = "asi_cognition_store"
AGENT_WORKSPACE_COLLECTION = "agent_workspace_logs"

# Thresholds
MIN_SUCCESSFUL_TASKS = 3       # minimas tareas exitosas para crear agente
MIN_AVG_SCORE = 0.6            # puntuacion minima promedio
MAX_AGENT_AGE_DAYS = 30        # dias sin uso antes de prunear
SCORE_WINDOW_DAYS = 7          # ventana para calcular puntuacion


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
    
    def __init__(self, vector_store: Optional[LanceVectorStore] = None):
        self._store = vector_store or LanceVectorStore()
        self._stats: Dict[str, Any] = {
            "agents_created": 0,
            "candidates_found": 0,
            "errors": 0,
        }
    
    def build_agents_from_cognition(self) -> List[str]:
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
        created: List[str] = []
        for domain, domain_lessons in domains.items():
            if len(domain_lessons) < MIN_SUCCESSFUL_TASKS:
                continue
            
            avg_score = sum(
                l.get("metrics", {}).get("overall_score", 0)
                for l in domain_lessones
            ) / len(domain_lessons)
            
            if avg_score < MIN_AVG_SCORE:
                continue
            
            agent_name = self._create_agent_profile(domain, domain_lessons, avg_score)
            if agent_name:
                created.append(agent_name)
                self._stats["agents_created"] += 1
        
        if created:
            logger.info(
                "Built %d agent(s) from cognition: %s",
                len(created), ", ".join(created),
            )
        else:
            logger.info(
                "No new agents built (%d candidates, avg_score<%.2f or n<%d)",
                len(domains), MIN_AVG_SCORE, MIN_SUCCESSFUL_TASKS,
            )
        
        return created
    
    def _fetch_lessons(self) -> List[Dict[str, Any]]:
        """Obtiene lessons recientes de la cognition store."""
        try:
            dummy = np.zeros(384, dtype=np.float32)
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
        except Exception as exc:
            logger.warning("Failed to fetch cognition lessons: %s", exc)
            return []
    
    @staticmethod
    def _group_by_domain(
        lessons: List[Dict[str, Any]],
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Agrupa lessons por dominio."""
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for lesson in lessons:
            domain = lesson.get("domain", "general")
            # Extraer dominio base (antes del primer .)
            base_domain = domain.split(".")[0] if "." in domain else domain
            
            # Verificar ventana de tiempo
            created = lesson.get("created_at", "")
            if created:
                try:
                    dt = datetime.fromisoformat(created)
                    if datetime.now(timezone.utc) - dt > timedelta(days=SCORE_WINDOW_DAYS):
                        continue  # saltar lessons viejas
                except (ValueError, TypeError):
                    pass
            
            if base_domain not in groups:
                groups[base_domain] = []
            groups[base_domain].append(lesson)
        
        return groups
    
    def _create_agent_profile(
        self,
        domain: str,
        lessons: List[Dict[str, Any]],
        avg_score: float,
    ) -> Optional[str]:
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
        agent_name = slug
        
        # Extraer tags como capacidades
        all_tags: Set[str] = set()
        all_triggers: Set[str] = set()
        for lesson in lessons:
            for tag in lesson.get("tags", []):
                if isinstance(tag, str):
                    all_tags.add(tag.lower())
            content = lesson.get("content", "").lower()
            # Extraer palabras clave como triggers
            for word in content.split()[:20]:
                word = word.strip(".,!?;:")
                if len(word) > 4:
                    all_triggers.add(word)
        
        capabilities = sorted(all_tags)[:8] if all_tags else ["automation", domain]
        triggers = sorted(all_triggers)[:10] if all_triggers else [domain]
        
        # Construir descripcion
        description = (
            f"Auto-generado desde {len(lessons)} tareas exitosas "
            f"en dominio '{domain}' (score: {avg_score:.2f}). "
            f"Especialista en {', '.join(capabilities[:3])}."
        )
        
        # Contenido del perfil
        profile_content = (
            "---\n"
            f"name: {agent_name}\n"
            f"domain: {domain}\n"
            f"triggers: {yaml.dump(triggers, default_flow_style=True).strip()}\n"
            f"capabilities: {yaml.dump(capabilities, default_flow_style=True).strip()}\n"
            f"aliases: [{slug.split('-')[0]}]\n"
            f"description: {description}\n"
            "---\n\n"
            f"# {agent_name}\n\n"
            f"{description}\n\n"
            "## Capacidades\n\n"
        )
        for cap in capabilities:
            profile_content += f"- {cap}\n"
        
        profile_content += "\n## Triggers\n\n"
        for trig in triggers[:5]:
            profile_content += f"- {trig}\n"
        
        profile_content += (
            "\n---\n"
            f"*Generado por Hermes AgentBuilder el "
            f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}*\n"
        )
        
        # Escribir archivo
        filepath = AUTO_AGENTS_DIR / f"{agent_name}.md"
        try:
            filepath.write_text(profile_content, encoding="utf-8")
            logger.info(
                "Created agent profile: %s (%d lessons, score=%.2f)",
                filepath.relative_to(AUTO_AGENTS_DIR.parent.parent.parent),
                len(lessons), avg_score,
            )
            return agent_name
        except Exception as exc:
            logger.error("Failed to write agent profile %s: %s", filepath, exc)
            self._stats["errors"] += 1
            return None
    
    def get_stats(self) -> Dict[str, Any]:
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
    PROTECTED_ROLES = {"coordinator", "builder", "scientist", "guardian", "evolve"}
    
    def __init__(self, vector_store: Optional[LanceVectorStore] = None):
        self._store = vector_store or LanceVectorStore()
        self._stats: Dict[str, Any] = {
            "pruned": 0,
            "protected": 0,
            "errors": 0,
        }
    
    def prune_underperforming(self, dry_run: bool = False) -> List[str]:
        """
        Elimina agentes auto-generados que no cumplen los thresholds.
        
        Args:
            dry_run: Si True, solo muestra que se eliminaria sin hacerlo.
        
        Returns:
            Lista de agentes eliminados.
        """
        auto_dir = AUTO_AGENTS_DIR
        if not auto_dir.exists():
            logger.info("No auto agents directory: %s", auto_dir)
            return []
        
        # 1. Listar agentes auto-generados
        auto_agents = sorted(auto_dir.glob("*.md"))
        if not auto_agents:
            logger.info("No auto-generated agents to prune.")
            return []
        
        # 2. Obtener uso de cada agente
        usage = self._get_agent_usage(auto_agents)
        
        # 3. Evaluar y eliminar
        pruned: List[str] = []
        for agent_file in auto_agents:
            agent_name = agent_file.stem
            
            # Proteger roles universales
            if agent_name in self.PROTECTED_ROLES:
                self._stats["protected"] += 1
                continue
            
            # Verificar uso reciente
            info = usage.get(agent_name, {})
            last_used = info.get("last_used", "")
            avg_score = info.get("avg_score", 0.0)
            task_count = info.get("task_count", 0)
            
            should_prune = False
            reasons: List[str] = []
            
            # Sin uso reciente
            if last_used:
                try:
                    last = datetime.fromisoformat(last_used)
                    age = datetime.now(timezone.utc) - last
                    if age > timedelta(days=MAX_AGENT_AGE_DAYS):
                        should_prune = True
                        reasons.append(f"not used in {age.days}d (> {MAX_AGENT_AGE_DAYS}d)")
                except (ValueError, TypeError):
                    pass
            elif task_count == 0:
                # Nunca usado
                should_prune = True
                reasons.append("never used")
            
            # Baja puntuacion
            if task_count > 0 and avg_score < MIN_AVG_SCORE and avg_score > 0:
                should_prune = True
                reasons.append(f"low avg score ({avg_score:.2f} < {MIN_AVG_SCORE})")
            
            if should_prune:
                pruned.append(agent_name)
                reason_str = ", ".join(reasons)
                
                if dry_run:
                    logger.info(
                        "[DRY-RUN] Would prune '%s': %s", agent_name, reason_str,
                    )
                else:
                    try:
                        agent_file.unlink()
                        # Also remove .agent.min.md if exists
                        min_file = agent_file.with_suffix(".agent.min.md")
                        if min_file.exists():
                            min_file.unlink()
                        logger.info("Pruned agent '%s': %s", agent_name, reason_str)
                        self._stats["pruned"] += 1
                    except Exception as exc:
                        logger.error("Failed to prune '%s': %s", agent_name, exc)
                        self._stats["errors"] += 1
        
        if not dry_run and pruned:
            logger.info("Pruned %d agent(s): %s", len(pruned), ", ".join(pruned))
        elif not pruned:
            logger.info("No agents needed pruning (%d evaluated).", len(auto_agents))
        
        return pruned
    
    def _get_agent_usage(
        self, agent_files: List[Path],
    ) -> Dict[str, Dict[str, Any]]:
        """Obtiene metricas de uso para cada agente desde agent_workspace_logs."""
        usage: Dict[str, Dict[str, Any]] = {}
        
        for agent_file in agent_files:
            agent_name = agent_file.stem
            usage[agent_name] = {
                "last_used": "",
                "task_count": 0,
                "avg_score": 0.0,
            }
            
            try:
                dummy = np.zeros(384, dtype=np.float32)
                results = self._store.search(
                    AGENT_WORKSPACE_COLLECTION, dummy, top_k=100,
                    filters={"to_agent": f"@{agent_name}"},
                )
                
                if results:
                    scores = []
                    last = ""
                    for r in results:
                        meta = r.get("metadata", {})
                        if isinstance(meta, str):
                            import json
                            try:
                                meta = json.loads(meta)
                            except (json.JSONDecodeError, TypeError):
                                meta = {}
                        created = meta.get("created_at", "")
                        if created and created > last:
                            last = created
                        # Intentar extraer score si existe
                        score = r.get("score", 0.0)
                        if score > 0:
                            scores.append(score)
                    
                    usage[agent_name]["last_used"] = last
                    usage[agent_name]["task_count"] = len(results)
                    if scores:
                        usage[agent_name]["avg_score"] = sum(scores) / len(scores)
                
            except Exception:
                pass
        
        return usage
    
    def get_stats(self) -> Dict[str, Any]:
        """Return pruner statistics."""
        return dict(self._stats)


# ---------------------------------------------------------------------------
# CLI command helper
# ---------------------------------------------------------------------------


def run_agent_evolution(dry_run: bool = False) -> Dict[str, Any]:
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
