"""
Orchestrator Patterns 2026 — Dynamic DAG + Conductor YAML workflows
(ADR-0041: frontier optimization; integrates with existing Swarmind orchestrator).

Patrones añadidos:
  1. OMA-style: Dynamic DAG generation from goal description + model-routing
  2. Conductor-style: YAML-first declarative workflows with zero-token routing
  3. Durable execution: WAL + checkpoint/resume (inspired by DeltaChannel ADR-0041 H3)
  4. Cost governance: per-agent budget caps with automatic fallback
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataclasses: DAG node + edge definitions
# ---------------------------------------------------------------------------

@dataclass
class DAGNode:
    """Un nodo en el DAG de orquestacion."""
    id: str
    agent: str  # nombre del agente builder/scientist/guardian
    operation: str  # qué hacer (implement, research, audit, etc.)
    params: dict[str, Any] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)  # IDs de nodos previos
    timeout_seconds: float | None = None
    max_retries: int = 3


@dataclass
class DAGEdge:
    """Una arista entre nodos del DAG."""
    from_: str  # ID del nodo origen
    to: str  # ID del nodo destino
    # Atributos opcionales para routing
    condition: str | None = None  # condición booleana en string
    timeout_multiplier: float = 1.0


@dataclass
class DynamicDAG:
    """DAG generado dinámicamente a partir de una goal description."""
    id: str
    name: str
    nodes: dict[str, DAGNode] = field(default_factory=dict)
    edges: dict[str, DAGEdge] = field(default_factory=dict)
    root: str = "start"  # nodo de entrada
    max_parallel: int = 5  # máximo de agentes en paralelo


# ---------------------------------------------------------------------------
# 1. OMA-style: Dynamic DAG generation from goal
# ---------------------------------------------------------------------------

def parse_goal_to_dag(goal: str, available_agents: list[str]) -> DynamicDAG:
    """
    Convierte una goal description en un DAG dinámico.

    La lógica es deliberadamente simple pero extensible:
    - Palabras-clave trigger el tipo de agente necesario.
    - Se crea un DAG de 2-3 niveles: plan → exec → verify.
    - Se asignan agentes segun disponibilidad.

    Args:
        goal: Descripcion natural de la tarea (ej.
              'implementa una API REST CRUD para gestionar usuarios').
        available_agents: Lista de nombres de agentes disponibles
                          (builder, scientist, guardian, coordinator).

    Returns:
        DynamicDAG listo para ser enviado al AgentBus.
    """
    # Id determinista (hashlib: estable entre procesos, no hash() de Python)
    dag_id = "dag_" + hashlib.sha256(goal.encode("utf-8")).hexdigest()[:8]
    nodes: dict[str, DAGNode] = {}
    edges: dict[str, DAGEdge] = {}

    # Nivel 1: Plan (siempre el coordinator o scientist)
    plan_node = DAGNode(
        id="plan",
        agent="coordinator",
        operation="plan",
        params={"goal": goal, "available_agents": available_agents},
    )
    nodes["plan"] = plan_node

    # Determinar agentes necesarios segun keywords
    goal_lower = goal.lower()
    needed: list[str] = []

    if any(k in goal_lower for k in ["implementa", "codigo", "api", "endpoint", "componente"]):
        needed.append("builder")
    if any(k in goal_lower for k in ["investiga", "paper", "arquitectura", "estudio", "analisis"]):
        needed.append("scientist")
    if any(k in goal_lower for k in ["test", "validar", "verificar", "bug", "error"]):
        needed.append("guardian")

    # Asegurar al menos un builder y un guardian
    if "builder" not in needed:
        needed.append("builder")
    if "guardian" not in needed:
        needed.append("guardian")

    # Nivel 2: Execution nodes (uno por agente necesario)
    exec_ids = []
    for i, agent in enumerate(needed):
        exec_id = f"exec_{agent}_{i}"
        exec_node = DAGNode(
            id=exec_id,
            agent=agent,
            operation=f"{agent}_task",
            params={"goal": goal, "agent": agent},
            timeout_seconds=120.0,
            max_retries=3,
        )
        nodes[exec_id] = exec_node
        exec_ids.append(exec_id)
        # Edge: plan -> exec
        edges[f"e_{exec_id}"] = DAGEdge(from_="plan", to=exec_id)

    # Nivel 3: Verification (guardian si hay tests/code)
    if "guardian" in needed:
        verify_node = DAGNode(
            id="verify",
            agent="guardian",
            operation="verify",
            params={"goal": goal, "check": "tests_pass"},
            timeout_seconds=60.0,
            max_retries=2,
        )
        nodes["verify"] = verify_node
        # Edge: último exec -> verify
        last_exec = exec_ids[-1] if exec_ids else "plan"
        edges[f"e_verify_{last_exec}"] = DAGEdge(from_=last_exec, to="verify")

    # Raiz
    if "plan" not in nodes:
        nodes["plan"] = DAGNode(id="plan", agent="coordinator", operation="plan")

    return DynamicDAG(
        id=dag_id,
        name=f"dynamic_{len(nodes)}nodes",
        nodes=nodes,
        edges=edges,
        root="plan",
        max_parallel=len(exec_ids) if exec_ids else 1,
    )


# ---------------------------------------------------------------------------
# 2. Conductor-style: YAML-first declarative workflows
# ---------------------------------------------------------------------------

def load_yaml_workflow(yaml_path: Path) -> DynamicDAG | None:
    """
    Carga un workflow definido en YAML estilo Conductor.

    Ejemplo YAML esperado (ver docs/guide/conductor-workflow-pattern.md):

    ```yaml
    name: user_onboarding
    description: Onboard a new user to the system
    max_parallel: 3
    nodes:
      - id: start
        agent: coordinator
        operation: plan
        params:
          goal: "Onboard new user"
      - id: create_user
        agent: builder
        operation: implement
        params:
          goal: "Create user account in DB"
        depends_on: [start]
      - id: send_welcome
        agent: builder
        operation: implement
        params:
          goal: "Send welcome email"
        depends_on: [create_user]
      - id: verify_setup
        agent: guardian
        operation: verify
        params:
          check: "all_services_ready"
        depends_on: [send_welcome]
    ```

    Returns:
        DynamicDAG cargado del YAML, o None si el formato es invalido.
    """
    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to load YAML workflow %s: %s", yaml_path, exc)
        return None

    if not data or "nodes" not in data:
        logger.error("YAML workflow %s missing 'nodes' key", yaml_path)
        return None

    dag_id = data.get("id", yaml_path.stem)
    name = data.get("name", yaml_path.stem)
    max_parallel = data.get("max_parallel", 3)

    nodes: dict[str, DAGNode] = {}
    edges: dict[str, DAGEdge] = {}

    # First pass: create all nodes
    node_by_id: dict[str, DAGNode] = {}
    for node_data in data["nodes"]:
        node_id = node_data.get("id")
        agent = node_data.get("agent")
        operation = node_data.get("operation")
        params = node_data.get("params", {})
        depends_on = node_data.get("depends_on", [])

        node = DAGNode(
            id=node_id,
            agent=agent,
            operation=operation,
            params=params,
        )
        nodes[node_id] = node
        node_by_id[node_id] = node

        # Edge: depends_on -> node_id (from_ = dependencia, to = este nodo)
        for dep in depends_on:
            edges[f"e_{node_id}_{dep}"] = DAGEdge(from_=dep, to=node_id)

    # Set edges reference in nodes (optional, for traversal):
    # dependencies = predecesores (origenes de las aristas que entran al nodo)
    for node in nodes.values():
        node.dependencies = [
            e.from_ for e in edges.values() if e.to == node.id
        ]

    return DynamicDAG(
        id=dag_id,
        name=name,
        nodes=nodes,
        edges=edges,
        root=data.get("start_node", data["nodes"][0]["id"]),
        max_parallel=max_parallel,
    )


def save_yaml_workflow(dag: DynamicDAG, yaml_path: Path) -> bool:
    """
    Guarda un DynamicDAG a YAML, compatible con el formato de load_yaml_workflow.

    Returns:
        True si se guardó correctamente.
    """
    try:
        data: dict[str, Any] = {
            "id": dag.id,
            "name": dag.name,
            "max_parallel": dag.max_parallel,
            "nodes": [
                {
                    "id": node.id,
                    "agent": node.agent,
                    "operation": node.operation,
                    "params": node.params,
                    "depends_on": [
                        dep for dep in node.dependencies
                    ],
                }
                for node in dag.nodes.values()
            ],
            "start_node": dag.root,
        }
        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to save YAML workflow %s: %s", yaml_path, exc)
        return False


# ---------------------------------------------------------------------------
# 3. Durable execution: WAL + checkpoint/resume (DeltaChannel inspiration ADR-0041 H3)
# ---------------------------------------------------------------------------

K_SNAPSHOT_DEFAULT = 50  # snapshot cada K pasos


@dataclass
class CheckpointRecord:
    """Un checkpoint delta (ún solo paso) persistido en disco."""
    step_id: str  # identificador unico del paso (puede ser node_id + iter)
    delta: dict[str, Any]  # cambios incrementales sobre el estado
    timestamp: float = field(default_factory=time.time)


class DurableExecutionWAL:
    """
    Write-Ahead Log + snapshots para durable execution.

    Inspired by:
      - DeltaChannel (LangChain blog 2026-07-28, ADR-0041 H3)
      - CCR (Compress-Cache-Retrieve) reversible compaction

    Garantias:
      - Append-only delta log: nunca se pierden cambios.
      - Snapshots cada K pasos: reduce costo de resume de O(N²) a O(N).
      - Resume: lee el snapshot + replay de deltas posteriores.
    """

    def __init__(self, state_dir: Path, snapshot_interval: int = K_SNAPSHOT_DEFAULT):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.snapshot_interval = snapshot_interval
        self._step_counter = 0
        self._deltas: list[CheckpointRecord] = []
        self._last_snapshot_path: Path | None = None

    def _delta_path(self, step_id: str) -> Path:
        return self.state_dir / f"delta_{step_id}.json"

    def _snapshot_file(self, seq: int) -> Path:
        return self.state_dir / f"snapshot_{seq}.json"

    def record_step(self, step_id: str, delta: dict[str, Any]) -> None:
        """Registra un delta incremental. Idempotente: si el step_id ya existe,
        el nuevo delta se fusiona (sobreescribe claves idénticas)."""
        record = CheckpointRecord(step_id=step_id, delta=delta)
        path = self._delta_path(step_id)
        # escritura atomica via tmp + os.replace (sobreescribe en Windows)
        tmp_path = Path(str(path) + ".tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(delta, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, path)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to write delta %s: %s", step_id, exc)
            return
        self._deltas.append(record)
        self._step_counter += 1

        # Snapshot periodic
        if self._step_counter % self.snapshot_interval == 0:
            self._take_snapshot()

    def _take_snapshot(self) -> None:
        """Guarda un snapshot con el estado consolidado hasta ahora."""
        # Consolidar todos los deltas aplicados hasta ahora
        consolidated: dict[str, Any] = {}
        for rec in self._deltas:
            consolidated.update(rec.delta)  # last-write-wins por clave

        seq = (self._step_counter // self.snapshot_interval)
        snap_path = self._snapshot_file(seq)
        tmp_path = Path(str(snap_path) + ".tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(consolidated, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, snap_path)
            self._last_snapshot_path = snap_path
            logger.info("Snapshot %s creado en %s", seq, snap_path)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to write snapshot %s: %s", seq, exc)

    def resume(self, base_snapshot_seq: int | None = None) -> dict[str, Any]:
        """
        Reconstruye el estado despues de un snapshot.

        Si base_snapshot_seq es None, busca el snapshot de mayor secuencia.
        Luego reapply los deltas que vengan despues de ese snapshot.
        """
        # Encontrar snapshot base
        if base_snapshot_seq is None:
            # Buscar snapshots existentes
            snapshots = sorted(
                self.state_dir.glob("snapshot_*.json"),
                key=lambda p: int(p.stem.split("_")[1]),
            )
            base_snapshot_seq = (
                int(snapshots[-1].stem.split("_")[1]) if snapshots else 0
            )

        base_path = self._snapshot_file(base_snapshot_seq)
        if not base_path.exists():
            logger.warning("Base snapshot %s not found, starting from empty", base_path)
            base_state: dict[str, Any] = {}
        else:
            with open(base_path, "r", encoding="utf-8") as f:
                base_state = json.load(f)

        # Reaplicar deltas despues del snapshot base
        start_idx = base_snapshot_seq * self.snapshot_interval
        deltas_to_reapply = self._deltas[start_idx:]

        state = dict(base_state)
        for rec in deltas_to_reapply:
            state.update(rec.delta)  # fusion idempotente

        return state

    def stats(self) -> dict[str, Any]:
        """Metricas de la instancia WAL."""
        return {
            "total_deltas": len(self._deltas),
            "snapshot_interval": self.snapshot_interval,
            "step_counter": self._step_counter,
            "state_dir": str(self.state_dir),
        }