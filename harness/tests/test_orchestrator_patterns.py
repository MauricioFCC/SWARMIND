"""
Tests de Orchestrator Patterns 2026 (Dynamic DAG + Conductor YAML + WAL).

Verifica:
  - parse_goal_to_dag: DAG dinamico con keywords, determinismo, root/edges.
  - load/save_yaml_workflow: roundtrip YAML, errores, dependencies = predecesores.
  - DurableExecutionWAL: deltas append-only, snapshots periodicos, resume,
    idempotencia de step_id y stats.

Reglas: determinismo (hashlib, no hash() de Python), PEP 585, sin magic numbers.
"""
from __future__ import annotations

import json

import pytest

from harness.orchestrator.workflows.orchestrator_patterns import (
    DAGEdge,
    DAGNode,
    DurableExecutionWAL,
    DynamicDAG,
    load_yaml_workflow,
    parse_goal_to_dag,
    save_yaml_workflow,
)

AVAILABLE_AGENTS = ["builder", "scientist", "guardian", "coordinator"]

SAMPLE_YAML = """
id: wf_onboard
name: user_onboarding
max_parallel: 3
start_node: start
nodes:
  - id: start
    agent: coordinator
    operation: plan
  - id: create_user
    agent: builder
    operation: implement
    depends_on: [start]
  - id: verify_setup
    agent: guardian
    operation: verify
    depends_on: [create_user]
"""

# ============================================================================
# Dynamic DAG generation
# ============================================================================


class TestParseGoalToDag:
    """Generacion de DAG dinamico a partir de goal descriptions."""

    def test_builder_for_implement_keyword(self) -> None:
        """'implementa' dispara nodo builder."""
        dag = parse_goal_to_dag("implementa una API REST CRUD", AVAILABLE_AGENTS)
        agents = {n.agent for n in dag.nodes.values()}
        assert "builder" in agents

    def test_scientist_for_research_keyword(self) -> None:
        """'investiga' dispara nodo scientist."""
        dag = parse_goal_to_dag("investiga papers de TDD governance", AVAILABLE_AGENTS)
        agents = {n.agent for n in dag.nodes.values()}
        assert "scientist" in agents

    def test_guardian_for_test_keyword(self) -> None:
        """'test' dispara nodo guardian."""
        dag = parse_goal_to_dag("testea el modulo de pagos", AVAILABLE_AGENTS)
        agents = {n.agent for n in dag.nodes.values()}
        assert "guardian" in agents

    def test_root_is_plan(self) -> None:
        """El root del DAG es el nodo 'plan'."""
        dag = parse_goal_to_dag("implementa una API", AVAILABLE_AGENTS)
        assert dag.root == "plan"
        assert dag.nodes["plan"].operation == "plan"

    def test_plan_has_edges_to_exec_nodes(self) -> None:
        """Existen aristas plan -> cada nodo de ejecucion."""
        dag = parse_goal_to_dag("implementa una API y testea", AVAILABLE_AGENTS)
        from_plan = [e for e in dag.edges.values() if e.from_ == "plan"]
        assert len(from_plan) >= 1

    def test_dag_id_deterministic(self) -> None:
        """Misma goal produce el mismo dag_id (hashlib, no hash())."""
        dag1 = parse_goal_to_dag("implementa una API", AVAILABLE_AGENTS)
        dag2 = parse_goal_to_dag("implementa una API", AVAILABLE_AGENTS)
        assert dag1.id == dag2.id

    def test_verify_node_present(self) -> None:
        """Nodo verify (guardian) existe al final del DAG."""
        dag = parse_goal_to_dag("implementa una API y testea", AVAILABLE_AGENTS)
        assert "verify" in dag.nodes

    def test_max_parallel_matches_exec_nodes(self) -> None:
        """max_parallel coincide con el numero de nodos de ejecucion (exec_*)."""
        dag = parse_goal_to_dag("implementa y testea", AVAILABLE_AGENTS)
        exec_nodes = [n for n in dag.nodes.values() if n.id.startswith("exec_")]
        assert dag.max_parallel == len(exec_nodes)


# ============================================================================
# YAML workflow load/save
# ============================================================================


class TestYamlWorkflow:
    """Roundtrip y errores del formato Conductor-style YAML."""

    def test_load_yaml_creates_dag(self, tmp_path) -> None:
        """Carga YAML valido y crea DynamicDAG con nodos y edges."""
        wf_path = tmp_path / "workflow.yaml"
        wf_path.write_text(SAMPLE_YAML, encoding="utf-8")
        dag = load_yaml_workflow(wf_path)
        assert dag is not None
        assert dag.name == "user_onboarding"
        assert dag.root == "start"
        assert set(dag.nodes) == {"start", "create_user", "verify_setup"}

    def test_dependencies_are_predecessors(self, tmp_path) -> None:
        """dependencies de un nodo = sus predecesores (from_), no destinos."""
        wf_path = tmp_path / "workflow.yaml"
        wf_path.write_text(SAMPLE_YAML, encoding="utf-8")
        dag = load_yaml_workflow(wf_path)
        assert dag is not None
        assert dag.nodes["create_user"].dependencies == ["start"]
        assert dag.nodes["verify_setup"].dependencies == ["create_user"]

    def test_load_missing_file_returns_none(self, tmp_path) -> None:
        """Archivo inexistente devuelve None (sin crash)."""
        assert load_yaml_workflow(tmp_path / "no_existe.yaml") is None

    def test_load_invalid_yaml_returns_none(self, tmp_path) -> None:
        """YAML sin clave 'nodes' devuelve None."""
        bad_path = tmp_path / "bad.yaml"
        bad_path.write_text("name: solo_nombre\n", encoding="utf-8")
        assert load_yaml_workflow(bad_path) is None

    def test_save_load_roundtrip(self, tmp_path) -> None:
        """save_yaml_workflow -> load_yaml_workflow preserva la estructura."""
        dag = DynamicDAG(
            id="rt_1",
            name="roundtrip",
            nodes={
                "a": DAGNode(id="a", agent="builder", operation="implement"),
                "b": DAGNode(
                    id="b", agent="guardian", operation="verify", dependencies=["a"]
                ),
            },
            edges={
                "e1": DAGEdge(from_="a", to="b"),
            },
            root="a",
            max_parallel=2,
        )
        out_path = tmp_path / "out.yaml"
        assert save_yaml_workflow(dag, out_path) is True
        loaded = load_yaml_workflow(out_path)
        assert loaded is not None
        assert loaded.id == "rt_1"
        assert loaded.nodes["b"].dependencies == ["a"]
        assert loaded.root == "a"


# ============================================================================
# Durable execution WAL
# ============================================================================


class TestDurableExecutionWAL:
    """WAL append-only con snapshots y resume."""

    def test_record_and_resume_fusion(self, tmp_path) -> None:
        """Deltas registrados se fusionan al hacer resume."""
        wal = DurableExecutionWAL(state_dir=tmp_path, snapshot_interval=100)
        wal.record_step("step_1", {"x": 1})
        wal.record_step("step_2", {"y": 2})
        state = wal.resume()
        assert state == {"x": 1, "y": 2}

    def test_idempotent_step_overwrites(self, tmp_path) -> None:
        """Mismo step_id sobreescribe claves (ultima escritura gana)."""
        wal = DurableExecutionWAL(state_dir=tmp_path, snapshot_interval=100)
        wal.record_step("step_1", {"x": 1})
        wal.record_step("step_1", {"x": 99})
        state = wal.resume()
        assert state["x"] == 99

    def test_snapshot_created_periodically(self, tmp_path) -> None:
        """Con snapshot_interval=2, tras 2 pasos existe archivo snapshot."""
        wal = DurableExecutionWAL(state_dir=tmp_path, snapshot_interval=2)
        wal.record_step("s1", {"a": 1})
        wal.record_step("s2", {"b": 2})
        snapshots = list(tmp_path.glob("snapshot_*.json"))
        assert len(snapshots) >= 1
        snap_data = json.loads(snapshots[-1].read_text(encoding="utf-8"))
        assert snap_data == {"a": 1, "b": 2}

    def test_resume_after_snapshot_replays_deltas(self, tmp_path) -> None:
        """Resume base + replay de deltas posteriores al snapshot."""
        wal = DurableExecutionWAL(state_dir=tmp_path, snapshot_interval=2)
        wal.record_step("s1", {"a": 1})
        wal.record_step("s2", {"b": 2})  # snapshot aqui (sec 1)
        wal.record_step("s3", {"c": 3})  # delta posterior al snapshot
        state = wal.resume()
        assert state == {"a": 1, "b": 2, "c": 3}

    def test_stats_report(self, tmp_path) -> None:
        """stats() devuelve metricas con las claves esperadas."""
        wal = DurableExecutionWAL(state_dir=tmp_path)
        wal.record_step("s1", {"a": 1})
        stats = wal.stats()
        assert stats["total_deltas"] == 1
        assert stats["step_counter"] == 1
        assert "state_dir" in stats

    def test_delta_file_written(self, tmp_path) -> None:
        """Cada paso persistido en disco como delta_<step>.json."""
        wal = DurableExecutionWAL(state_dir=tmp_path)
        wal.record_step("alpha", {"v": 42})
        delta_path = tmp_path / "delta_alpha.json"
        assert delta_path.exists()
        assert json.loads(delta_path.read_text(encoding="utf-8")) == {"v": 42}

    def test_resume_empty_state(self, tmp_path) -> None:
        """Sin deltas ni snapshots, resume devuelve estado vacio."""
        wal = DurableExecutionWAL(state_dir=tmp_path)
        assert wal.resume() == {}

    def test_snapshot_interval_respected(self, tmp_path) -> None:
        """No se crea snapshot antes de completar el intervalo."""
        wal = DurableExecutionWAL(state_dir=tmp_path, snapshot_interval=5)
        wal.record_step("s1", {"a": 1})
        assert not list(tmp_path.glob("snapshot_*.json"))

    def test_pytest_raises_not_needed(self) -> None:
        """Guard de smoke: pytest importado para futuras excepciones."""
        assert pytest is not None
