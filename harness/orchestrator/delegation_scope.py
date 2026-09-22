"""delegation_scope.py — Scope de delegacion inmutable parent-owned (ADR-0098).

WHAT: Statement `issue_scope` con skills+acciones permitidas; `allows`
verifica par (skill, accion); frozen (no ampliable desde dentro).
WHY: deepseek-harness subagent/catalog: permisos parent-owned, linaje
auditable O(D); el hijo nunca se auto-otorga (least privilege real).
WHERE: `delegate()` / subagentes antes de ejecutar tools.

Uso:
    scope = issue_scope("deploy-docs", skills=("docs",), actions=("read",))
    if not scope.allows("db", "write"): denegar()
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DelegationScope:
    """Statement inmutable de alcance de delegacion.

    Attributes:
        task_id: Tarea delegada.
        skills: Skills permitidas (tupla).
        actions: Acciones permitidas (tupla).
    """

    task_id: str
    skills: tuple[str, ...]
    actions: tuple[str, ...]

    def allows(self, skill: str, action: str) -> bool:
        """True si el par (skill, accion) esta permitido.

        Args:
            skill: Skill solicitada.
            action: Accion solicitada.

        Returns:
            True solo si ambos estan en el statement.
        """
        return skill in self.skills and action in self.actions


def issue_scope(
    task_id: str, skills: tuple[str, ...], actions: tuple[str, ...]
) -> DelegationScope:
    """Emite un scope parent-owned (validado).

    Args:
        task_id: ID de la tarea.
        skills: Skills permitidas (no vacio).
        actions: Acciones permitidas (no vacio).

    Returns:
        DelegationScope frozen.

    Raises:
        ValueError: Si skills o actions estan vacios (WHAT+WHY+WHERE).
    """
    if not skills:
        raise ValueError(
            "WHAT: scope sin skills. "
            "WHY: delegar sin alcance es carta blanca. "
            "WHERE: issue_scope"
        )
    if not actions:
        raise ValueError(
            "WHAT: scope sin acciones. "
            "WHY: delegar sin acciones es carta blanca. "
            "WHERE: issue_scope"
        )
    return DelegationScope(
        task_id=task_id, skills=tuple(skills), actions=tuple(actions)
    )
