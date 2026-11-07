"""Renderizado Markdown de la memoria de investigación.

Separado de ``investigation.py`` para respetar el límite de tamaño por módulo
(AGR/F3) sin acoplar el estado a la presentación. Las funciones son puras y
reciben los objetos del estado (duck typing) para evitar import circular.
"""

from __future__ import annotations

from typing import Any


def render_brief(brief: Any | None) -> str:
    """Markdown del brief."""
    if brief is None:
        return "# Brief\n\n_No brief yet._\n"
    lines = [f"**Question:** {brief.question}", ""]
    if brief.purpose:
        lines += [f"**Purpose:** {brief.purpose}", ""]
    if brief.targets:
        lines += ["**Targets:**"] + [f"- {item}" for item in brief.targets] + [""]
    if brief.constraints:
        lines += ["**Constraints:**"] + [f"- {item}" for item in brief.constraints] + [""]
    if brief.done_when:
        lines += [f"**Done when:** {brief.done_when}"]
    return "# Brief\n\n" + "\n".join(lines) + "\n"


def render_plan(plan: list[Any]) -> str:
    """Markdown del plan."""
    if not plan:
        return "# Plan\n\n_No plan yet._\n"
    lines = ["# Plan", ""]
    for index, step in enumerate(plan, 1):
        suffix = f" - {step.why}" if step.why else ""
        lines.append(f"{index}. [{step.status.value}] {step.title}{suffix}")
    return "\n".join(lines) + "\n"


def render_hypotheses(hypotheses: list[Any]) -> str:
    """Markdown de las hipótesis."""
    if not hypotheses:
        return "# Hypotheses\n\n_None yet._\n"
    lines = ["# Hypotheses", ""]
    for item in hypotheses:
        lines += [f"## {item.id} ({item.status.value})", "", item.claim, ""]
        if item.prediction:
            lines += [f"Prediction: {item.prediction}", ""]
        if item.supporting:
            lines += [f"Supporting: {', '.join(item.supporting)}", ""]
        if item.contradicting:
            lines += [f"Contradicting: {', '.join(item.contradicting)}", ""]
        lines += [f"- {note}" for note in item.notes]
    return "\n".join(lines).rstrip() + "\n"


def render_findings(findings: list[Any]) -> str:
    """Markdown de los hallazgos."""
    if not findings:
        return "# Findings\n\n_None yet._\n"
    lines = ["# Findings", ""]
    for item in findings:
        evidence = ", ".join(item.evidence_ids)
        lines.append(
            f"- **{item.id}** {item.statement} ({item.confidence}; evidence: {evidence})"
        )
    return "\n".join(lines) + "\n"


def render_handoff(handoff: str | None) -> str:
    """Markdown del handoff."""
    return f"# Handoff\n\n{handoff or '_No handoff yet._'}\n"
