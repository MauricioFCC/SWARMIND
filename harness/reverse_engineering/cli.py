"""CLI de operaciones de ingeniería inversa (`python -m harness.reverse_engineering`).

Expone el protocolo evidencia/investigación y el triaje para que cualquier
agente (OpenCode, CI, terminal) lo use sin cargar Python a mano:

    python -m harness.reverse_engineering triage <ruta> --record <proyecto>
    python -m harness.reverse_engineering show <proyecto>
    python -m harness.reverse_engineering brief <proyecto> --question "..."
    python -m harness.reverse_engineering finding <proyecto> --statement "..." \\
        --evidence ev_... --revision 3
    python -m harness.reverse_engineering policy native_function_pseudocode
    python -m harness.reverse_engineering bridge native_functions_list --deep

Salida JSON por defecto (apta para agentes); errores con WHAT+WHY+WHERE y exit 2.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .bridge import BridgeUnavailable, CraftAnythingBridge
from .evidence import EvidenceLedger
from .investigation import (
    Brief,
    HypothesisStatus,
    Investigation,
    PlanStep,
    Severity,
    StepStatus,
    Unknown,
)
from .policy import Mode, Policy, PolicyViolation
from .triage import fingerprint, triage_evidence


def _paths(project: Path) -> tuple[Path, Path]:
    """Devuelve (state.json, evidence.jsonl) de un proyecto."""
    directory = project / "investigation"
    return directory / "state.json", directory / "evidence.jsonl"


def _load(project: Path) -> tuple[Investigation, EvidenceLedger]:
    """Carga investigación y ledger de un proyecto."""
    _, ledger_path = _paths(project)
    return Investigation.load(project), EvidenceLedger.load(ledger_path)


def _save(project: Path, investigation: Investigation, ledger: EvidenceLedger) -> None:
    """Persiste investigación y ledger."""
    state_path, ledger_path = _paths(project)
    investigation.save(project)
    ledger.save(ledger_path)
    print(json.dumps({"state": str(state_path), "revision": investigation.revision}))


def _emit(value: Any) -> None:
    """Imprime JSON legible."""
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def _cmd_triage(args: argparse.Namespace) -> int:
    """Triaja un artefacto y, opcionalmente, registra la evidencia."""
    info = fingerprint(Path(args.path))
    payload: dict[str, Any] = {"artifact": info.to_dict()}
    if args.record:
        project = Path(args.record)
        investigation, ledger = _load(project)
        evidence = triage_evidence(Path(args.path), Mode.CLEAN_ROOM)
        payload["evidence_id"] = ledger.add(evidence)
        ledger.save(_paths(project)[1])
        payload["investigation_revision"] = investigation.revision
    _emit(payload)
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    """Muestra el estado de la investigación y el tamaño del ledger."""
    investigation, ledger = _load(Path(args.project))
    payload = investigation.to_dict()
    payload["evidence_count"] = len(ledger.ids())
    _emit(payload)
    return 0


def _cmd_brief(args: argparse.Namespace) -> int:
    """Escribe el brief de la investigación."""
    project = Path(args.project)
    investigation, ledger = _load(project)
    investigation.set_brief(
        Brief(
            question=args.question,
            purpose=args.purpose,
            targets=args.target or [],
            constraints=args.constraint or [],
            done_when=args.done_when,
        ),
        based_on_revision=args.revision,
    )
    _save(project, investigation, ledger)
    return 0


def _cmd_plan(args: argparse.Namespace) -> int:
    """Reemplaza el plan con los pasos indicados ``titulo|why``."""
    project = Path(args.project)
    investigation, ledger = _load(project)
    steps = []
    for raw in args.step:
        title, _, why = raw.partition("|")
        steps.append(PlanStep(title=title.strip(), status=StepStatus(args.status), why=why or None))
    investigation.set_plan(steps, based_on_revision=args.revision)
    _save(project, investigation, ledger)
    return 0


def _cmd_finding(args: argparse.Namespace) -> int:
    """Registra un hallazgo con evidencia existente."""
    project = Path(args.project)
    investigation, ledger = _load(project)
    finding_id = investigation.add_finding(
        statement=args.statement,
        evidence_ids=args.evidence,
        ledger=ledger,
        confidence=args.confidence,
        based_on_revision=args.revision,
    )
    _save(project, investigation, ledger)
    print(json.dumps({"finding_id": finding_id}))
    return 0


def _cmd_hypothesis(args: argparse.Namespace) -> int:
    """Registra una hipótesis con evidencia a favor/en contra."""
    project = Path(args.project)
    investigation, ledger = _load(project)
    hypothesis_id = investigation.add_hypothesis(
        claim=args.claim,
        ledger=ledger,
        prediction=args.prediction,
        supporting=args.support or [],
        contradicting=args.against or [],
        based_on_revision=args.revision,
    )
    investigation.hypotheses[-1].status = HypothesisStatus(args.status)
    _save(project, investigation, ledger)
    print(json.dumps({"hypothesis_id": hypothesis_id}))
    return 0


def _cmd_unknown(args: argparse.Namespace) -> int:
    """Añade una pregunta abierta (unknown)."""
    project = Path(args.project)
    investigation, ledger = _load(project)
    unknown = Unknown.new(args.question, args.domain, Severity(args.severity))
    investigation.add_unknown(unknown, based_on_revision=args.revision)
    _save(project, investigation, ledger)
    print(json.dumps({"unknown_id": unknown.id}))
    return 0


def _cmd_resolve(args: argparse.Namespace) -> int:
    """Resuelve un unknown con resolución y evidencia."""
    project = Path(args.project)
    investigation, ledger = _load(project)
    investigation.resolve_unknown(
        unknown_id=args.id,
        resolution=args.resolution,
        evidence_for=args.evidence,
        ledger=ledger,
        based_on_revision=args.revision,
    )
    _save(project, investigation, ledger)
    return 0


def _cmd_policy(args: argparse.Namespace) -> int:
    """Comprueba si una operación está permitida en el modo actual."""
    mode = Mode.DEEP if args.deep else Mode.CLEAN_ROOM
    policy = Policy(mode=mode)
    try:
        policy.guard(args.operation)
    except PolicyViolation as exc:
        print(json.dumps({"allowed": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps({"allowed": True, **policy.describe()}, ensure_ascii=False))
    return 0


def _cmd_bridge(args: argparse.Namespace) -> int:
    """Ejecuta una herramienta del motor externo craft-anything."""
    mode = Mode.DEEP if args.deep else Mode.CLEAN_ROOM
    bridge = CraftAnythingBridge(mode=mode)
    params = json.loads(args.params) if args.params else {}
    try:
        result = bridge.call(args.tool, params)
    except (BridgeUnavailable, PolicyViolation) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 1
    _emit({"tool": result.tool_id, "evidence_id": result.evidence_id, "result": result.result})
    return 0


def _add_core_commands(sub: Any) -> None:
    """Subcomandos de triaje y memoria básica (show/brief/plan)."""
    triage = sub.add_parser("triage", help="identifica un artefacto por sus bytes")
    triage.add_argument("path")
    triage.add_argument("--record", help="proyecto donde registrar la evidencia")
    triage.set_defaults(func=_cmd_triage)

    show = sub.add_parser("show", help="muestra la investigación")
    show.add_argument("project")
    show.set_defaults(func=_cmd_show)

    brief = sub.add_parser("brief", help="escribe el brief")
    brief.add_argument("project")
    brief.add_argument("--question", required=True)
    brief.add_argument("--purpose")
    brief.add_argument("--target", action="append")
    brief.add_argument("--constraint", action="append")
    brief.add_argument("--done-when")
    brief.add_argument("--revision", type=int)
    brief.set_defaults(func=_cmd_brief)

    plan = sub.add_parser("plan", help="reemplaza el plan")
    plan.add_argument("project")
    plan.add_argument("--step", action="append", required=True, help="titulo|why")
    plan.add_argument("--status", default="todo", choices=[s.value for s in StepStatus])
    plan.add_argument("--revision", type=int)
    plan.set_defaults(func=_cmd_plan)


def _add_memory_commands(sub: Any) -> None:
    """Subcomandos de hallazgos, hipótesis y unknowns."""
    finding = sub.add_parser("finding", help="registra un hallazgo")
    finding.add_argument("project")
    finding.add_argument("--statement", required=True)
    finding.add_argument("--evidence", action="append", required=True)
    finding.add_argument("--confidence", default="observed")
    finding.add_argument("--revision", type=int)
    finding.set_defaults(func=_cmd_finding)

    hypothesis = sub.add_parser("hypothesis", help="registra una hipótesis")
    hypothesis.add_argument("project")
    hypothesis.add_argument("--claim", required=True)
    hypothesis.add_argument("--prediction")
    hypothesis.add_argument("--support", action="append")
    hypothesis.add_argument("--against", action="append")
    hypothesis.add_argument("--status", default="testing", choices=[s.value for s in HypothesisStatus])
    hypothesis.add_argument("--revision", type=int)
    hypothesis.set_defaults(func=_cmd_hypothesis)

    unknown = sub.add_parser("unknown", help="añade una pregunta abierta")
    unknown.add_argument("project")
    unknown.add_argument("--question", required=True)
    unknown.add_argument("--domain", required=True)
    unknown.add_argument("--severity", default="medium", choices=[s.value for s in Severity])
    unknown.add_argument("--revision", type=int)
    unknown.set_defaults(func=_cmd_unknown)
    _add_resolve_command(sub)


def _add_resolve_command(sub: Any) -> None:
    """Subcomando ``resolve`` (resolver un unknown con evidencia)."""
    resolve = sub.add_parser("resolve", help="resuelve un unknown")
    resolve.add_argument("project")
    resolve.add_argument("--id", required=True)
    resolve.add_argument("--resolution", required=True)
    resolve.add_argument("--evidence", action="append", required=True)
    resolve.add_argument("--revision", type=int)
    resolve.set_defaults(func=_cmd_resolve)


def _add_tool_commands(sub: Any) -> None:
    """Subcomandos de política y puente externo."""
    policy = sub.add_parser("policy", help="comprueba la política de una operación")
    policy.add_argument("operation")
    policy.add_argument("--deep", action="store_true")
    policy.set_defaults(func=_cmd_policy)

    bridge = sub.add_parser("bridge", help="llama a craft-anything-cli")
    bridge.add_argument("tool")
    bridge.add_argument("--params", default="{}")
    bridge.add_argument("--deep", action="store_true")
    bridge.set_defaults(func=_cmd_bridge)


def build_parser() -> argparse.ArgumentParser:
    """Construye el parser de subcomandos."""
    parser = argparse.ArgumentParser(prog="python -m harness.reverse_engineering")
    sub = parser.add_subparsers(dest="command", required=True)
    _add_core_commands(sub)
    _add_memory_commands(sub)
    _add_tool_commands(sub)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entrada del CLI; devuelve exit code."""
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (KeyError, ValueError, PolicyViolation, BridgeUnavailable) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
