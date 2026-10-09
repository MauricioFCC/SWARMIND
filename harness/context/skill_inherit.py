"""skill_inherit.py — Herencia de skills: resolver y validar ``inherit:``.

WHAT: Lee el campo ``inherit:`` del frontmatter de cada ``SKILL.md`` (lista de
rutas relativas a la raiz ``.opencode/``), resuelve cada ruta contra esa raiz
y concatena el contenido de los artefactos que existen. Falla rapido
(``CompositionError``) si una ruta falta o escapa ``base_dir``.
WHY: ``inherit:`` estaba INERTE: ``skill_composition`` parseaba ``calls:`` e
``invocation:`` pero nadie resolvia ni validaba la herencia declarada. El
frontmatter prometia dependencias (p.ej. ``core/base_principles.md``) que
nunca se inyectaban ni se comprobaba su existencia (integridad referencial
rota). Frontera 2026 (Anthropic Agent Skills + progressive disclosure): la
herencia debe ser verificable y fail-fast, no decorativa.
WHERE: pre-commit de skills (``scripts/validate_skills.py``), ``skill_bundler``
y CI de integridad referencial via :func:`validate_inherit_corpus`.

Decision de diseno: modulo nuevo (no extender ``skill_composition``) para no
mezclar la composicion dinamica (``calls:``/``invocation:``) con la herencia
estatica de artefactos; se reutiliza su ``SkillCompositionError`` como
``CompositionError`` para un unico contrato de error.

Uso:
    resolution = resolve_inherit(skill_md, base_dir=Path(".opencode"))
    errors = validate_inherit_corpus(skills_dir, base_dir)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from harness.context.skill_composition import SkillCompositionError

logger = logging.getLogger("harness.context.skill_inherit")

#: Clave del frontmatter que declara la herencia.
INHERIT_KEY = "inherit"

#: Nombre canonico del archivo de skill.
SKILL_MD_FILENAME = "SKILL.md"

#: Delimitador del frontmatter YAML.
FRONTMATTER_DELIM = "---"

#: Alias explicito del error de composicion (contrato publico del modulo).
CompositionError = SkillCompositionError


@dataclass(frozen=True)
class InheritResolution:
    """Resultado inmutable de resolver la herencia de una skill.

    Attributes:
        skill_name: Nombre derivado del directorio padre del SKILL.md.
        declared: Rutas heredadas tal como las declara el frontmatter.
        resolved: Tupla ``(ruta_declarada, path_absoluto, existe)`` por entrada.
        content: Contenido concatenado (``\\n``) de los artefactos heredados.
    """

    skill_name: str
    declared: tuple[str, ...]
    resolved: tuple[tuple[str, Path, bool], ...]
    content: str


def _load_frontmatter(skill_md: Path) -> dict[str, Any]:
    """Extrae y parsea el frontmatter YAML de un SKILL.md.

    Args:
        skill_md: Ruta del archivo SKILL.md.

    Returns:
        Dict del frontmatter; ``{}`` si no hay frontmatter valido.

    Raises:
        CompositionError: Si el YAML del frontmatter esta roto (WHAT+WHY+WHERE).
    """
    text = skill_md.read_text(encoding="utf-8-sig")
    if not text.startswith(FRONTMATTER_DELIM):
        return {}
    parts = text.split(FRONTMATTER_DELIM, 2)
    if len(parts) < 3:
        return {}
    try:
        data = yaml.safe_load(parts[1])
    except yaml.YAMLError as exc:
        raise CompositionError(
            f"WHAT: frontmatter YAML invalido en {skill_md}: {exc}. "
            "WHY: no se pudo parsear 'inherit:' para resolver la herencia. "
            "WHERE: parse_inherit"
        ) from exc
    return data if isinstance(data, dict) else {}


def parse_inherit(skill_md: Path) -> tuple[str, ...]:
    """Extrae la lista de rutas declaradas en ``inherit:`` del frontmatter.

    Args:
        skill_md: Ruta del SKILL.md.

    Returns:
        Tupla de rutas relativas declaradas (vacia si no hay ``inherit:``).

    Raises:
        CompositionError: Si ``inherit:`` no es una lista de strings.
    """
    declared = _load_frontmatter(skill_md).get(INHERIT_KEY)
    if declared is None:
        return ()
    if not isinstance(declared, list) or not all(isinstance(item, str) for item in declared):
        raise CompositionError(
            f"WHAT: '{INHERIT_KEY}' invalido en {skill_md}: se esperaba lista de "
            f"strings, se obtuvo {type(declared).__name__}. "
            f"WHY: el contrato de herencia exige rutas relativas a '.opencode/'. "
            "WHERE: parse_inherit"
        )
    return tuple(item.strip() for item in declared if item.strip())


def _resolve_one(rel_path: str, base_root: Path) -> Path:
    """Resuelve y valida una ruta heredada contra la raiz ``.opencode/``.

    Args:
        rel_path: Ruta relativa declarada en el frontmatter.
        base_root: Raiz ``.opencode/`` ya resuelta (absoluta).

    Returns:
        Path absoluto del artefacto heredado (existe garantizado).

    Raises:
        CompositionError: Si la ruta escapa ``base_root`` (path traversal) o
            si el artefacto declarado no existe (WHAT+WHY+WHERE).
    """
    candidate = (base_root / rel_path).resolve()
    if not candidate.is_relative_to(base_root):
        raise CompositionError(
            f"WHAT: herencia '{rel_path}' escapa base_dir {base_root}. "
            "WHY: path traversal prohibido: solo se permite heredar artefactos "
            "dentro de '.opencode/'. "
            "WHERE: resolve_inherit"
        )
    if not candidate.is_file():
        raise CompositionError(
            f"WHAT: artefacto heredado ausente: '{rel_path}' (resuelto {candidate}). "
            f"WHY: el frontmatter declara '{INHERIT_KEY}' pero el archivo no existe. "
            "WHERE: resolve_inherit"
        )
    return candidate


def resolve_inherit(skill_md: Path, base_dir: Path) -> InheritResolution:
    """Resuelve la herencia declarada por una skill.

    Args:
        skill_md: Ruta del SKILL.md de la skill.
        base_dir: Raiz ``.opencode/`` contra la que se resuelven las rutas.

    Returns:
        InheritResolution con rutas declaradas, rutas resueltas y contenido
        concatenado de los artefactos heredados.

    Raises:
        CompositionError: Si una ruta falta, escapa ``base_dir`` o el
            frontmatter es invalido (WHAT+WHY+WHERE).
    """
    declared = parse_inherit(skill_md)
    base_root = base_dir.resolve()
    resolved: list[tuple[str, Path, bool]] = []
    chunks: list[str] = []
    for rel_path in declared:
        path = _resolve_one(rel_path, base_root)
        resolved.append((rel_path, path, True))
        chunks.append(path.read_text(encoding="utf-8-sig"))
    return InheritResolution(
        skill_name=skill_md.parent.name,
        declared=declared,
        resolved=tuple(resolved),
        content="\n".join(chunks),
    )


def validate_inherit_corpus(skills_dir: Path, base_dir: Path) -> list[str]:
    """Valida la integridad referencial de la herencia de todo el corpus.

    Recorre ``skills_dir/**/SKILL.md``, resuelve la herencia de cada skill y
    acumula los errores sin lanzar, para usar en gates de CI/pre-commit.

    Args:
        skills_dir: Raiz de skills (cada skill en su subdirectorio).
        base_dir: Raiz ``.opencode/`` contra la que se resuelven las rutas.

    Returns:
        Lista de mensajes WHAT+WHY+WHERE de las herencias invalidas; lista
        vacia si todas las skills resuelven correctamente.
    """
    errors: list[str] = []
    for skill_md in sorted(skills_dir.glob(f"**/{SKILL_MD_FILENAME}")):
        try:
            resolve_inherit(skill_md, base_dir)
        except CompositionError as exc:
            errors.append(str(exc))
    return errors
