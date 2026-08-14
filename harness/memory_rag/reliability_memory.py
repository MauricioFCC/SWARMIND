"""Memoria de confiabilidad online (Sigma-Mem, ADR-0039 #6, arXiv 2607.27958).

Registra evidencia de competencia por agente (exitos/fallos por tipo de tarea)
y sirve como insumo para routing adaptativo y votacion ponderada sin respuesta.

Diseno MVP:
  - Suavizado Laplace: score = (successes + 1) / (total + 2). Sin evidencia el
    score es 0.5 (cold-start neutro).
  - Persistencia JSON en ``data/reliability_memory.json`` (path configurable)
    con carga lazy y guardado atomico (tmp + os.replace) para no corromper el
    estado ante escrituras concurrentes.
  - Los errores de escritura se registran como warning (WHAT+WHY+WHERE) sin
    crashear: la memoria sigue operando en RAM.
  - Historial acotado de eventos por agente (provenance, MemClaw) que conserva
    el ``meta`` de cada outcome.

Uso tipico:
    mem = ReliabilityMemory()
    mem.record_outcome("builder", "code_gen", success=True, meta={"ms": 1200})
    print(mem.get_ranked_agents(task_type="code_gen"))
"""
from __future__ import annotations

import json
import logging
import os
import threading
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: Version del formato de persistencia (bump si cambia el schema del JSON).
_STORAGE_VERSION = 1
#: Tamanio maximo del historial de eventos por agente (provenance acotada).
_MAX_EVENTS_PER_AGENT = 100

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
#: Ruta por defecto: data/reliability_memory.json en la raiz del repositorio.
DEFAULT_PATH = _REPO_ROOT / "data" / "reliability_memory.json"


class ReliabilityMemory:
    """Memoria de confiabilidad online por agente con persistencia JSON atomica.

    Args:
        path: Ruta del archivo JSON de persistencia. Si es relativa se resuelve
            contra la raiz del repositorio (default: ``data/reliability_memory.json``).

    Raises:
        TypeError: Si ``path`` no es str ni Path.
    """

    def __init__(self, path: Path | str | None = None) -> None:
        if path is None:
            self._path = DEFAULT_PATH
        elif isinstance(path, (str, Path)):
            resolved = Path(path)
            self._path = resolved if resolved.is_absolute() else _REPO_ROOT / resolved
        else:
            raise TypeError(f"ReliabilityMemory.__init__ | path invalido: {type(path)}")
        # Estado en memoria: agentes -> conteos por tipo de tarea + eventos.
        self._agents: dict[str, dict[str, Any]] = {}
        self._loaded = False
        self._dirty = False
        # RLock: permite mutaciones anidadas (load -> guardar) en un mismo hilo.
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # API publica
    # ------------------------------------------------------------------

    def record_outcome(
        self,
        agent: str,
        task_type: str,
        success: bool,
        meta: dict | None = None,
    ) -> None:
        """Registra una evidencia de competencia (exito o fallo) para un agente.

        Args:
            agent: Identificador del agente (non-empty string).
            task_type: Tipo de tarea evaluado (non-empty string).
            success: True si el outcome fue exitoso, False en caso contrario.
            meta: Metadatos opcionales del outcome (JSON-serializable).

        Raises:
            ValueError: Si ``agent`` o ``task_type`` son vacios o no string.
            TypeError: Si ``success`` no es bool.
        """
        self._ensure_loaded()
        if not isinstance(agent, str) or not agent.strip():
            raise ValueError(
                "ReliabilityMemory.record_outcome | WHAT=argumento_invalido | "
                f"WHY=agent_vacio | WHERE=record_outcome | agent={agent!r}"
            )
        if not isinstance(task_type, str) or not task_type.strip():
            raise ValueError(
                "ReliabilityMemory.record_outcome | WHAT=argumento_invalido | "
                f"WHY=task_type_vacio | WHERE=record_outcome | task_type={task_type!r}"
            )
        if not isinstance(success, bool):
            raise TypeError(
                "ReliabilityMemory.record_outcome | WHAT=argumento_invalido | "
                f"WHY=success_no_bool | WHERE=record_outcome | success={success!r}"
            )
        with self._lock:
            state = self._agents.setdefault(
                agent, {"successes": {}, "failures": {}, "events": []}
            )
            counter = state["successes" if success else "failures"]
            counter[task_type] = counter.get(task_type, 0) + 1
            state["events"] = self._bounded_events(state.get("events", []), success, task_type, meta)
            self._dirty = True
            self._save_if_dirty()

    def get_reliability(self, agent: str, task_type: str | None = None) -> float:
        """Retorna el success-rate con suavizado Laplace para un agente.

        Args:
            agent: Identificador del agente.
            task_type: Si se provee, la confiabilidad se calcula solo para ese
                tipo de tarea; si no, se agrega sobre todos los tipos.

        Returns:
            float en [0, 1]: (successes + 1) / (total + 2). Agente sin evidencia
            retorna 0.5 (cold-start neutro).

        Raises:
            ValueError: Si ``agent`` es vacio o no string.
        """
        self._ensure_loaded()
        if not isinstance(agent, str) or not agent.strip():
            raise ValueError(
                "ReliabilityMemory.get_reliability | WHAT=argumento_invalido | "
                f"WHY=agent_vacio | WHERE=get_reliability | agent={agent!r}"
            )
        with self._lock:
            state = self._agents.get(agent)
            if state is None:
                return 0.5
            successes, failures = self._counts_for(state, task_type)
            return self._laplace(successes, failures)

    def get_ranked_agents(
        self, task_type: str | None = None
    ) -> list[tuple[str, float]]:
        """Ranking de agentes por confiabilidad, ordenado descendente.

        Args:
            task_type: Si se provee, el ranking usa solo la evidencia de ese
                tipo de tarea; si no, la agregada sobre todos los tipos.

        Returns:
            list[(agent, score)] con score Laplace en [0, 1]; agentes sin
            evidencia para el filtro puntuan 0.5. Desempates por nombre
            (orden estable y determinista).
        """
        self._ensure_loaded()
        with self._lock:
            ranked: list[tuple[str, float]] = []
            for agent, state in self._agents.items():
                successes, failures = self._counts_for(state, task_type)
                ranked.append((agent, self._laplace(successes, failures)))
            ranked.sort(key=lambda item: (-item[1], item[0]))
            return ranked

    def get_stats(self) -> dict[str, Any]:
        """Resumen estadistico de la memoria de confiabilidad.

        Returns:
            dict con version del storage, total de agentes, total de eventos y
            desglose por agente (exitos/fallos/score) y por tipo de tarea.
        """
        self._ensure_loaded()
        with self._lock:
            total_events = 0
            per_task: dict[str, dict[str, int]] = {}
            per_agent: dict[str, dict[str, Any]] = {}
            for agent, state in self._agents.items():
                successes, failures = self._counts_for(state, None)
                total_events += successes + failures
                per_agent[agent] = {
                    "successes": successes,
                    "failures": failures,
                    "score": self._laplace(successes, failures),
                }
                for counter_name in ("successes", "failures"):
                    for task, count in state[counter_name].items():
                        bucket = per_task.setdefault(
                            task, {"successes": 0, "failures": 0}
                        )
                        bucket[counter_name] += count
            return {
                "version": _STORAGE_VERSION,
                "agents": len(self._agents),
                "events": total_events,
                "per_agent": per_agent,
                "per_task_type": per_task,
                "path": str(self._path),
            }

    def clear(self) -> None:
        """Limpia toda la evidencia registrada y persiste el estado vacio."""
        with self._lock:
            self._agents = {}
            self._dirty = True
            self._save_if_dirty()

    # ------------------------------------------------------------------
    # Helpers de calculo
    # ------------------------------------------------------------------

    @staticmethod
    def _laplace(successes: int, failures: int) -> float:
        """Suavizado Laplace: (successes + 1) / (total + 2)."""
        return (successes + 1) / (successes + failures + 2)

    def _counts_for(
        self, state: dict[str, Any], task_type: str | None
    ) -> tuple[int, int]:
        """Conteos (successes, failures) del estado, filtrados por tarea.

        Args:
            state: Estado interno de un agente.
            task_type: Tipo de tarea o None para agregar sobre todos.
        """
        successes = state["successes"].get(task_type, 0) if task_type else sum(state["successes"].values())
        failures = state["failures"].get(task_type, 0) if task_type else sum(state["failures"].values())
        return successes, failures

    def _bounded_events(
        self, events: list[dict[str, Any]], success: bool, task_type: str, meta: dict | None
    ) -> list[dict[str, Any]]:
        """Agrega un evento al historial acotado (FIFO, max ``_MAX_EVENTS_PER_AGENT``)."""
        buffer = deque(events, maxlen=_MAX_EVENTS_PER_AGENT)
        buffer.append(
            {
                "task_type": task_type,
                "success": success,
                "timestamp": datetime.now(UTC).isoformat(),
                "meta": meta if meta is not None else {},
            }
        )
        return list(buffer)

    # ------------------------------------------------------------------
    # Persistencia
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        """Carga el estado desde disco una sola vez (lazy load).

        Si el archivo no existe se deja el estado vacio sin error; si esta
        corrupto se registra warning (WHAT+WHY+WHERE) y se parte de vacio.
        """
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            if self._path.exists():
                try:
                    raw = self._path.read_text(encoding="utf-8")
                    data = json.loads(raw)
                    self._agents = data.get("agents", {})
                    self._sanitize_loaded_state()
                    logger.info(
                        "ReliabilityMemory._ensure_loaded | Cargados %d agentes desde %s",
                        len(self._agents),
                        self._path,
                    )
                except (OSError, json.JSONDecodeError, AttributeError, TypeError) as exc:
                    logger.warning(
                        "ReliabilityMemory._ensure_loaded | Archivo corrupto o ilegible: %s | "
                        "WHAT=carga_fallida | WHY=json_invalido | WHERE=_ensure_loaded | error=%s",
                        self._path,
                        exc,
                    )
                    self._agents = {}
            self._loaded = True

    def _sanitize_loaded_state(self) -> None:
        """Normaliza el estado cargado: descarta agentes sin estructura valida."""
        clean: dict[str, dict[str, Any]] = {}
        for agent, state in self._agents.items():
            if isinstance(state, dict) and isinstance(state.get("successes"), dict) and isinstance(
                state.get("failures"), dict
            ):
                clean[agent] = {
                    "successes": {k: int(v) for k, v in state["successes"].items()},
                    "failures": {k: int(v) for k, v in state["failures"].items()},
                    "events": state.get("events", []),
                }
            else:
                logger.warning(
                    "ReliabilityMemory._sanitize_loaded_state | Agente descartado: %s | "
                    "WHAT=estado_invalido | WHY=estructura_incorrecta | WHERE=_sanitize_loaded_state",
                    agent,
                )
        self._agents = clean

    def _save_if_dirty(self) -> None:
        """Persiste solo si hubo mutacion desde la ultima escritura."""
        if not self._dirty:
            return
        try:
            self._atomic_write()
            self._dirty = False
        except OSError as exc:
            logger.warning(
                "ReliabilityMemory._save_if_dirty | No se persistio en %s | "
                "WHAT=escritura_fallida | WHY=sistema_archivos | WHERE=_save_if_dirty | "
                "error=%s | los_datos_siguen_en_ram=True",
                self._path,
                exc,
            )

    def _atomic_write(self) -> None:
        """Escritura atomica: tmp file en el mismo directorio + os.replace.

        Raises:
            OSError: Si el directorio no se puede crear o la escritura falla.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {"version": _STORAGE_VERSION, "agents": self._agents},
            indent=2,
            ensure_ascii=False,
            default=str,
        )
        tmp = self._path.with_name(f"{self._path.name}.tmp")
        try:
            tmp.write_text(payload, encoding="utf-8")
            os.replace(tmp, self._path)
        finally:
            # Si os.replace fallo, no dejar residuos del tmp.
            if tmp.exists():
                tmp.unlink(missing_ok=True)
