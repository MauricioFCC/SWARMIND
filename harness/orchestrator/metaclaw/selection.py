"""Seleccion adaptativa de herramientas (extraccion mecanica).

Mixin privado con registro de herramientas, seleccion por Thompson
Sampling y consultas de estadisticas/rendimiento.
"""
from __future__ import annotations

import logging
import random
from typing import Any

from .constants import EXPLORATION_NOISE
from .models import ToolRecord

logger = logging.getLogger(__name__)


class _SelectionMixin:
    """Metodos de seleccion y consulta de MetaClaw."""
    def register_tool(self, tool_name: str) -> None:
        """Registra una herramienta en el MetaClaw.

        WHAT: Anade una herramienta al conjunto de opciones disponibles.
        Si ya existe, no hace nada.
        WHY: El MetaClaw solo puede seleccionar entre herramientas
        registradas. El registro permite inicializar sus estadisticas.
        WHERE: Durante la inicializacion del sistema o al anadir una
        nueva herramienta.

        Args:
            tool_name: Identificador unico de la herramienta
                (ej: "gpt-4", "sandbox-python", "code-executor").

        Raises:
            ValueError: Si tool_name esta vacio o es solo espacios.
        """
        if not tool_name or not tool_name.strip():
            raise ValueError(
                f"WHAT: tool_name='{tool_name}' esta vacio. "
                f"WHY: Toda herramienta necesita un identificador valido. "
                f"WHERE: MetaClaw.register_tool"
            )

        with self._lock:
            if tool_name not in self._tool_records:
                self._tool_records[tool_name] = ToolRecord(tool_name=tool_name)
                # Indicar que no hay sesgo: prior uniforme
                logger.info("MetaClaw: herramienta '%s' registrada", tool_name)

    def select_tool(
        self,
        task_type: str,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Selecciona la mejor herramienta para una tarea usando meta-aprendizaje.

        WHAT: Usa Thompson Sampling con posteriors Beta para balancear
        exploracion y explotacion. Con probabilidad exploration_rate,
        explora aleatoriamente. Sino, selecciona la herramienta con
        mayor muestra del posterior.
        WHY: Thompson Sampling converge al optimo con garantias
        teoricas de regret sublineal, y maneja naturalmente la
        incertidumbre sobre herramientas nuevas.
        WHERE: Cada vez que el orquestador necesita delegar una tarea
        a una herramienta.

        Args:
            task_type: Tipo de tarea (ej: "code_generation",
                "test_generation", "analysis", "research").
            context: Diccionario con metadatos de la tarea
                (ej: {"lang": "python", "complexity": 0.8}).
                Puede ser None para tareas simples.

        Returns:
            Nombre de la herramienta seleccionada.

        Raises:
            RuntimeError: Si no hay herramientas registradas.
        """
        if context is None:
            context = {}

        with self._lock:
            if not self._tool_records:
                raise RuntimeError(
                    "WHAT: No hay herramientas registradas en MetaClaw. "
                    "WHY: No se puede seleccionar sin opciones disponibles. "
                    "WHERE: MetaClaw.select_tool. "
                    "SUGGEST: Registrar al menos una herramienta con register_tool()."
                )

            tool_names = list(self._tool_records.keys())

            # Registrar tipo de tarea
            self._known_task_types[task_type] += 1

            # Actualizar embedding de la tarea (aprendizaje incremental)
            self._update_task_embedding(task_type, context)

            # Decidir si explorar o explotar
            if random.random() < self._exploration_rate:
                selected = random.choice(tool_names)
                logger.debug(
                    "MetaClaw: exploracion -> herramienta='%s' para tarea='%s'",
                    selected, task_type,
                )
            else:
                # Thompson Sampling: muestrear del posterior de cada herramienta
                best_tool = tool_names[0]
                best_sample = float("-inf")

                for tool_name in tool_names:
                    alpha, beta = self._get_posterior(task_type, tool_name)
                    # Muestrear de Beta(alpha, beta)
                    sample = random.betavariate(alpha, beta)

                    # Agregar ruido de exploracion
                    sample += random.gauss(0, EXPLORATION_NOISE)

                    if sample > best_sample:
                        best_sample = sample
                        best_tool = tool_name

                selected = best_tool
                logger.debug(
                    "MetaClaw: explotacion -> herramienta='%s' "
                    "(sample=%.4f) para tarea='%s'",
                    selected, best_sample, task_type,
                )

            return selected

    def get_best_tool(self, task_type: str) -> str | None:
        """Obtiene la mejor herramienta para un tipo de tarea.

        Args:
            task_type: Tipo de tarea a consultar.

        Returns:
            Nombre de la herramienta con mayor expected reward, o None
            si no hay datos para ese tipo de tarea.
        """
        with self._lock:
            best: str | None = None
            best_score = float("-inf")

            for tool_name in self._tool_records:
                alpha, beta = self._get_posterior(task_type, tool_name)
                expected = alpha / max(alpha + beta, 1)

                if expected > best_score:
                    best_score = expected
                    best = tool_name

            return best

    def get_tool_stats(self, tool_name: str) -> dict[str, Any] | None:
        """Obtiene estadisticas detalladas de una herramienta.

        Args:
            tool_name: Nombre de la herramienta.

        Returns:
            Diccionario con: tool_name, total_calls, success_rate,
            avg_latency, avg_cost, last_used, task_types, o None
            si la herramienta no existe.
        """
        with self._lock:
            record = self._tool_records.get(tool_name)
            if record is None:
                return None

            return {
                "tool_name": record.tool_name,
                "total_calls": record.total_calls,
                "success_rate": (
                    record.successes / max(record.total_calls, 1)
                ),
                "avg_latency": (
                    record.total_latency / max(record.total_calls, 1)
                ),
                "avg_cost": (
                    record.total_cost / max(record.total_calls, 1)
                ),
                "last_used": record.last_used,
                "task_types": dict(record.task_types),
                "failures": record.failures,
                "successes": record.successes,
            }

    def get_task_performance(
        self,
        task_type: str,
    ) -> dict[str, Any] | None:
        """Obtiene el rendimiento agregado para un tipo de tarea.

        Args:
            task_type: Tipo de tarea a consultar.

        Returns:
            Diccionario con: task_type, total_calls, success_rate,
            avg_reward, tools_used, best_tool, o None si no hay datos.
        """
        with self._lock:
            tools_data = {}
            total_calls = 0
            total_rewards = 0.0
            reward_count = 0

            for tool_name in self._tool_records:
                hist = self._reward_history[task_type].get(tool_name, [])
                if not hist:
                    continue

                alpha, beta = self._get_posterior(task_type, tool_name)
                tools_data[tool_name] = {
                    "calls": len(hist),
                    "success_rate_estimate": alpha / max(alpha + beta, 1),
                    "avg_reward": sum(hist) / max(len(hist), 1),
                }
                total_calls += len(hist)
                total_rewards += sum(hist)
                reward_count += len(hist)

            if not tools_data:
                return None

            # Mejor herramienta por expected reward
            best_tool = max(
                tools_data.keys(),
                key=lambda t: tools_data[t]["success_rate_estimate"],
            )

            return {
                "task_type": task_type,
                "total_calls": total_calls,
                "tools_used": tools_data,
                "best_tool": best_tool,
                "avg_reward": total_rewards / max(reward_count, 1),
                "known_frequency": self._known_task_types.get(task_type, 0),
            }

    def get_all_stats(self) -> dict[str, Any]:
        """Retorna estadisticas completas del MetaClaw.

        Returns:
            Diccionario con: tools, task_types, total_selections,
            exploration_rate, learning_rate, posteriors size.
        """
        with self._lock:
            return {
                "tools": {
                    name: {
                        "total_calls": r.total_calls,
                        "success_rate": (
                            r.successes / max(r.total_calls, 1)
                        ),
                        "avg_latency": (
                            r.total_latency / max(r.total_calls, 1)
                        ),
                        "avg_cost": (
                            r.total_cost / max(r.total_calls, 1)
                        ),
                    }
                    for name, r in self._tool_records.items()
                },
                "task_types": dict(self._known_task_types),
                "total_selections": len(self._selection_history),
                "exploration_rate": self._exploration_rate,
                "learning_rate": self._learning_rate,
                "posterior_pairs": sum(
                    len(pts) for pts in self._posteriors.values()
                ),
                "known_tasks": len(self._known_task_types),
                "registered_tools": len(self._tool_records),
            }

    def reset_tool(self, tool_name: str) -> bool:
        """Resetea las estadisticas de una herramienta.

        WHAT: Elimina todos los datos y posteriors asociados a la
        herramienta. Vuelve a registrarla con prior uniforme.
        WHY: Util cuando una herramienta cambia de version o se
        detecta que sus estadisticas estan desactualizadas.
        WHERE: Despues de actualizar una herramienta.

        Args:
            tool_name: Nombre de la herramienta a resetear.

        Returns:
            True si se reseteo, False si no existia.
        """
        with self._lock:
            if tool_name not in self._tool_records:
                return False

            # Limpiar posteriors asociados
            for task_type in list(self._posteriors.keys()):
                self._posteriors[task_type].pop(tool_name, None)

            # Limpiar reward history
            for task_type in list(self._reward_history.keys()):
                self._reward_history[task_type].pop(tool_name, None)

            # Re-registrar
            self._tool_records[tool_name] = ToolRecord(tool_name=tool_name)

            logger.info("MetaClaw: herramienta '%s' reseteada", tool_name)
            return True

    def get_selection_history(
        self,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Obtiene el historial de selecciones recientes.

        Args:
            limit: Maximo de entradas a retornar. Default: 50.

        Returns:
            Lista de diccionarios con datos de seleccion.
        """
        with self._lock:
            recent = self._selection_history[-limit:]
            return [
                {
                    "task_type": s.task_type,
                    "selected_tool": s.selected_tool,
                    "success": s.success,
                    "latency": s.latency,
                    "cost": s.cost,
                    "reward": round(s.reward, 4),
                    "timestamp": s.timestamp,
                }
                for s in recent
            ]
