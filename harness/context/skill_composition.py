"""skill_composition.py — Skills como primitivas: calls + invocation + compat (ADR-0075).

WHAT: Parser del frontmatter de skills para composicion: ``calls:`` (skills
que la skill delega, resueltas lazy con dedup y deteccion de ciclos),
``invocation:`` (user|model|skill) y poda de pares conflictivos
(set-compatibility).
WHY: Frontera 2026 — Pocock v1.0: composicion de skills compartidas dio
-63% tokens (inline eliminados, delegacion); taxonomia user-invoked vs
model-invoked evita que composites tasen la sesion raiz; Wang: un set de
skills debe ser EJECUTABLE en conjunto, no solo relevante (+1 reinforcing /
-1 conflicting).
WHERE: ``skill_bundler`` / ``SkillRouter``: resolver composicion antes de
inyectar y podar conflictivos.

Uso:
    resolved = resolve_composition("tdd", skills_dir)
    pruned = prune_conflicts(["frontend-uiux", "rust-lang", "quant-trading"])
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("harness.context.skill_composition")

#: Tiers de invocacion validos (Pocock 2026).
VALID_INVOCATIONS: frozenset[str] = frozenset({"user", "model", "skill"})

#: Tier por defecto si el frontmatter no declara invocation.
DEFAULT_INVOCATION = "model"

#: Pares conflictivos default (heuristica del dominio SWARMIND).
_DEFAULT_CONFLICTS: frozenset[frozenset[str]] = frozenset()


_CALLS_RE = re.compile(r"^calls:\s*\[(.*)\]\s*$", re.MULTILINE)
_INVOCATION_RE = re.compile(r"^invocation:\s*(\w+)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class CompositionResult:
    """Resultado de resolver la composicion de una skill.

    Attributes:
        roots: Skills raiz solicitadas.
        invoked: Skills delegadas (orden de descubrimiento, dedup).
        invocation_tiers: Mapa skill -> tier de invocacion.
    """

    roots: tuple[str, ...]
    invoked: tuple[str, ...]
    invocation_tiers: dict[str, str]


class SkillCompositionError(RuntimeError):
    """Error de composicion (skill ausente, ciclo, frontmatter invalido)."""


def parse_calls(skill_md: Path) -> tuple[str, ...]:
    """Extrae ``calls: [a, b]`` del frontmatter de una skill.

    Args:
        skill_md: Ruta del SKILL.md.

    Returns:
        Tupla de nombres delegados (vacia si no declara calls).
    """
    text = skill_md.read_text(encoding="utf-8-sig")
    match = _CALLS_RE.search(text)
    if not match:
        return ()
    return tuple(p.strip() for p in match.group(1).split(",") if p.strip())


def parse_invocation(skill_md: Path) -> str:
    """Extrae el tier ``invocation:`` del frontmatter (default model).

    Args:
        skill_md: Ruta del SKILL.md.

    Returns:
        Tier ("user"|"model"|"skill").

    Raises:
        SkillCompositionError: Si el tier es desconocido (WHAT+WHY+WHERE).
    """
    text = skill_md.read_text(encoding="utf-8-sig")
    match = _INVOCATION_RE.search(text)
    tier = match.group(1).lower() if match else DEFAULT_INVOCATION
    if tier not in VALID_INVOCATIONS:
        raise SkillCompositionError(
            f"WHAT: invocation invalida: '{tier}' en {skill_md}. "
            f"WHY: debe ser uno de {sorted(VALID_INVOCATIONS)}. "
            "WHERE: parse_invocation"
        )
    return tier


def resolve_composition(root_skill: str, skills_dir: Path) -> CompositionResult:
    """Resuelve lazy la composicion de una skill con dedup y anti-ciclos.

    Args:
        root_skill: Nombre de la skill raiz.
        skills_dir: Directorio base de skills (cada una en un subdir).

    Returns:
        CompositionResult con raiz, delegadas (dedup) y tiers.

    Raises:
        SkillCompositionError: Si la skill no existe, un calls apunta a una
            skill ausente, o hay un ciclo (WHAT+WHY+WHERE).
    """
    visited: list[str] = []
    seen: set[str] = set()
    tiers: dict[str, str] = {}
    path: list[str] = []

    def _walk(name: str, is_root: bool) -> None:
        """Recorre la composicion en profundidad con guardas de ciclo.

        Args:
            name: Skill actual.
            is_root: True si es la raiz (no se agrega a invoked).
        """
        if name in path:
            cycle = " -> ".join([*path, name])
            raise SkillCompositionError(
                f"WHAT: ciclo de composicion detectado: {cycle}. "
                "WHY: una skill no puede delegarse a si misma (directa o "
                "indirectamente): colgaria la resolucion. "
                "WHERE: resolve_composition"
            )
        skill_md = skills_dir / name / "SKILL.md"
        if not skill_md.is_file():
            raise SkillCompositionError(
                f"WHAT: skill '{name}' no encontrada en {skills_dir}. "
                f"WHY: {'raiz solicitada' if is_root else 'referenciada por calls'}. "
                "WHERE: resolve_composition"
            )
        if name not in seen:
            seen.add(name)
            if not is_root:
                visited.append(name)
        tiers[name] = parse_invocation(skill_md)
        path.append(name)
        for callee in parse_calls(skill_md):
            _walk(callee, is_root=False)
        path.pop()

    _walk(root_skill, is_root=True)
    return CompositionResult(
        roots=(root_skill,), invoked=tuple(visited), invocation_tiers=tiers
    )


def prune_conflicts(
    selected: list[str],
    conflicts: frozenset[frozenset[str]] = _DEFAULT_CONFLICTS,
) -> list[str]:
    """Poda pares conflictivos de un set de skills (set-compatibility).

    Conserva el primer elemento del par conflictivo (orden de seleccion) y
    descarta el segundo. Set vacio de conflictos = pasa todo (identidad).

    Args:
        selected: Skills seleccionadas (en orden de relevancia).
        conflicts: Matriz de pares conflictivos (frozensets de 2 nombres).

    Returns:
        Lista podada conservando el orden de los seleccionados.
    """
    if not conflicts:
        return list(selected)
    out: list[str] = []
    for skill in selected:
        clash = next(
            (pair for pair in conflicts if skill in pair and (set(pair) & set(out))),
            None,
        )
        if clash is not None:
            other = next(iter(clash - {skill}))
            logger.info(
                "prune_conflicts: '%s' conflictivo con '%s' (ya en set); se descarta",
                skill, other,
            )
            continue
        out.append(skill)
    return out
