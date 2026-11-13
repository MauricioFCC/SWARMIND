"""Migración expand/contract del frontmatter de skills a ``metadata``.

WHAT: mueve ``domain``, ``version`` y ``project_agnostic`` de nivel superior al
mapa ``metadata`` (string→string, spec Agent Skills) sin tocar el resto del
frontmatter ni el body. Los campos no escalares (``inherit``, ``variables``,
``invocation``, ``calls``) se preservan tal cual.

WHY: la spec define ``metadata`` como mapa string→string y no define esos tres
campos como top-level; un cliente estricto puede ignorarlos. La migración
manual de 50 skills es propensa a drift; el script es determinista e
idempotente (research ``frontier-2026-11-12-skills-metadata-migration.md``).

WHERE: ``scripts/migrate_skills_metadata.py``; consumido por los validadores
(dual-read) y el ciclo de release.

Invariantes: segunda pasada = 0 cambios; body byte-idéntico; solo se tocan los
tres bloques escalares.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

_FRONT_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.DOTALL)
_TOP_KEY_RE = re.compile(r"^([A-Za-z0-9_-]+):(.*)$")
_MIGRATE_KEYS: tuple[str, ...] = ("domain", "version", "project_agnostic")


@dataclass(frozen=True)
class MigrationReport:
    """Resumen de una pasada del migrador.

    Args:
        updated: Archivos con cambios.
        unchanged: Archivos ya migrados o sin los campos.
        files: Rutas relativas modificadas.
        errors: Archivos que fallaron (WHAT+WHY).
    """

    updated: int
    unchanged: int
    files: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()


def _split(text: str) -> tuple[str, str] | None:
    """Separa (frontmatter interno, body) o ``None`` si no hay frontmatter."""
    match = _FRONT_RE.match(text)
    if match is None:
        return None
    return match.group(1), text[match.end():]


def _blocks(front: str) -> list[list[object]]:
    """Divide el frontmatter en bloques ``[clave, lineas]``.

    Un bloque empieza en una línea sin indentar con ``clave:`` y absorbe sus
    líneas indentadas/continuaciones. Los bloques sin clave (preámbulo) se
    conservan con ``None``.
    """
    bloques: list[list[object]] = []
    actual: list[object] | None = None
    for linea in front.splitlines():
        if linea and not linea.startswith((" ", "\t")):
            match = _TOP_KEY_RE.match(linea)
            if match is not None:
                actual = [match.group(1), [linea]]
                bloques.append(actual)
                continue
        if actual is None:
            bloques.append([None, [linea]])
        else:
            actual[1].append(linea)  # type: ignore[union-attr]
    return bloques


def _scalar(bloque: list[object]) -> str:
    """Extrae el valor escalar de un bloque ``clave: valor``."""
    lineas = bloque[1]
    assert isinstance(lineas, list)
    primera = str(lineas[0])
    valor = primera.partition(":")[2].strip()
    if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
        valor = valor[1:-1]
    return valor


def _quote(valor: str) -> str:
    """Serializa un valor como string YAML entre comillas dobles."""
    return json.dumps(valor, ensure_ascii=False)


def _new_meta_lines(meta: list[str], valores: dict[str, str]) -> list[str]:
    """Añade/reemplaza los tres escalares dentro del bloque ``metadata``."""
    existentes: dict[str, int] = {}
    for indice, linea in enumerate(meta):
        if linea.startswith("  ") and not linea.startswith("    ") and ":" in linea:
            existentes[linea.strip().partition(":")[0]] = indice
    for clave, bruto in valores.items():
        if clave == "project_agnostic":
            texto = "true" if bruto.strip().lower() in {"true", "1", "yes"} else "false"
        else:
            texto = bruto.strip()
        linea = f"  {clave}: {_quote(texto)}"
        if clave in existentes:
            meta[existentes[clave]] = linea
        else:
            meta.append(linea)
    return meta


def _split_blocks(
    front: str,
) -> tuple[dict[str, str], list[object] | None, list[list[object]]]:
    """Clasifica los bloques del frontmatter en migrables, metadata y resto."""
    valores: dict[str, str] = {}
    meta_bloque: list[object] | None = None
    conservados: list[list[object]] = []
    for bloque in _blocks(front):
        clave = bloque[0]
        if clave in _MIGRATE_KEYS:
            valores[str(clave)] = _scalar(bloque)
            continue
        if clave == "metadata":
            meta_bloque = bloque
        conservados.append(bloque)
    return valores, meta_bloque, conservados


def _meta_lines(meta_bloque: list[object] | None) -> list[str]:
    """Devuelve las líneas de ``metadata`` (creándolo) y rechaza el inline."""
    if meta_bloque is None:
        return ["metadata:"]
    meta = [str(linea) for linea in meta_bloque[1]]  # type: ignore[index]
    if meta and meta[0].partition(":")[2].strip().startswith("{"):
        raise ValueError("metadata inline no soportado; usa bloque YAML")
    return meta


def _render(nl: str, conservados: list[list[object]], body: str) -> str:
    """Reconstruye el documento con los bloques conservados y el body."""
    front = nl.join(
        str(linea)
        for bloque in conservados
        for linea in bloque[1]  # type: ignore[union-attr]
    )
    return f"---{nl}{front}{nl}---{nl}{body}"


def migrate_frontmatter(text: str) -> tuple[str, bool]:
    """Migra un ``SKILL.md`` completo; devuelve ``(texto, cambiado)``.

    Args:
        text: Contenido del archivo.

    Returns:
        Texto migrado (o el original) y si hubo cambios.

    Raises:
        ValueError: Si ``metadata`` está en formato inline (no soportado).
    """
    partes = _split(text)
    if partes is None:
        return text, False
    front, body = partes
    nl = "\r\n" if "\r\n" in front else "\n"
    valores, meta_bloque, conservados = _split_blocks(front)
    if not valores:
        return text, False
    meta = _meta_lines(meta_bloque)
    _new_meta_lines(meta, valores)
    if meta_bloque is not None:
        meta_bloque[1] = meta  # type: ignore[index]
    else:
        conservados.append(["metadata", meta])
    return _render(nl, conservados, body), True


def _migrate_file(
    ruta: Path, root: Path, write: bool
) -> tuple[str | None, str | None]:
    """Migra un archivo; devuelve (ruta relativa cambiada, error)."""
    try:
        texto = ruta.read_text(encoding="utf-8")
        nuevo, cambiado = migrate_frontmatter(texto)
        if not cambiado:
            return None, None
        if write:
            ruta.write_text(nuevo, encoding="utf-8", newline="")
        return ruta.relative_to(root).as_posix(), None
    except (OSError, ValueError) as exc:
        return None, f"{ruta.name}: {exc}"


def migrate_skills(root: Path, *, write: bool = False) -> MigrationReport:
    """Migra todos los ``*/SKILL.md`` y ``*/SKILL.min.md`` bajo ``root``.

    Args:
        root: Directorio de skills (``.opencode/skills``).
        write: Si True, escribe los cambios; si no, solo simula.

    Returns:
        ``MigrationReport`` con actualizados, sin cambios y errores.
    """
    rutas = sorted(root.glob("*/SKILL.md")) + sorted(root.glob("*/SKILL.min.md"))
    archivos: list[str] = []
    errores: list[str] = []
    for ruta in rutas:
        cambio, error = _migrate_file(ruta, root, write)
        if error is not None:
            errores.append(error)
        elif cambio is not None:
            archivos.append(cambio)
    return MigrationReport(
        updated=len(archivos),
        unchanged=len(rutas) - len(archivos) - len(errores),
        files=tuple(archivos),
        errors=tuple(errores),
    )
