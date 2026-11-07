"""Journal JSONL append-only + audit de monotonicidad (ADR-0010 anti-rollback).

WHAT: append de entradas (una linea JSON cada una) y verificacion del
invariante — para 'updated': to >= from y to >= maxima previa; para
'downgrade_forced': justification no vacio; lineas ilegibles = violacion.
WHY: el mandato exige un log de actualizacion que impida reversiones;
el journal es la SSOT de la cota historica (max_seen_version) que usa el
gate de apply_update. Solo avanza = propiedad de prefijo auditable.
WHERE: harness/self_update/journal.py; consumido por core.apply_update y
por el CLI scripts/self_update.py --audit.
"""
from __future__ import annotations

import json
from pathlib import Path

from harness.self_update.versions import NO_VERSION, fmt_version, parse_semver

_VERSIONED_ACTIONS = frozenset({"attempt", "updated", "downgrade_forced"})


def _read_entries(log_path: Path) -> list[dict]:
    """Entradas validas del journal ([] si falta o linea rota: la audit acusa)."""
    if not log_path.is_file():
        return []
    entradas: list[dict] = []
    for linea in log_path.read_text(encoding="utf-8").splitlines():
        if not linea.strip():
            continue
        try:
            dato = json.loads(linea)
        except json.JSONDecodeError:
            continue
        if isinstance(dato, dict):
            entradas.append(dato)
    return entradas


def append_log(entry: dict, log_path: Path) -> None:
    """Agrega UNA linea JSON al journal append-only (crea padres)."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def audit_log(log_path: Path) -> list[str]:
    """Violaciones de monotonicidad/reversion en el journal (lista vacia = OK).

    Args:
        log_path: Ruta del journal JSONL append-only.

    Returns:
        Descripciones de violacion; vacio si el historial es monotono.
    """
    violaciones: list[str] = []
    if not log_path.is_file():
        return violaciones
    maximo = NO_VERSION
    crudo = log_path.read_text(encoding="utf-8").splitlines()
    for indice, linea in enumerate(crudo, 1):
        if not linea.strip():
            continue
        try:
            entry = json.loads(linea)
        except json.JSONDecodeError:
            violaciones.append(f"linea {indice}: JSON ilegible")
            continue
        nuevas, maximo = _audit_entry(entry, indice, maximo)
        violaciones.extend(nuevas)
    return violaciones


def _audit_entry(
    entry: object, indice: int, maximo: tuple[int, ...]
) -> tuple[list[str], tuple[int, ...]]:
    """Audita UNA entrada; devuelve (violaciones, nueva_maxima_solo_avance)."""
    if not isinstance(entry, dict):
        return [f"linea {indice}: entrada no es objeto"], maximo
    accion = str(entry.get("action") or "")
    from_v = parse_semver(str(entry.get("from_version") or ""))
    to_v = parse_semver(str(entry.get("to_version") or ""))
    viol: list[str] = []
    if accion in _VERSIONED_ACTIONS and (from_v is None or to_v is None):
        viol.append(f"linea {indice}: faltan from_version/to_version")
    elif accion == "updated" and from_v is not None and to_v is not None:
        if to_v < from_v:
            viol.append(
                f"linea {indice}: reversal to={fmt_version(to_v)} < from={fmt_version(from_v)}"
            )
        if to_v < maximo:
            viol.append(
                f"linea {indice}: to={fmt_version(to_v)} < maxima previa {fmt_version(maximo)}"
            )
    if accion == "downgrade_forced" and not str(entry.get("justification") or "").strip():
        viol.append(f"linea {indice}: downgrade_forced sin justification")
    candidatos = [maximo] + [v for v in (from_v, to_v) if v]
    return viol, max(candidatos)


def max_seen_version(log_path: Path) -> tuple[int, ...]:
    """Cota historica maxima (ADR-0010 max_seen) derivada del journal."""
    mejor = NO_VERSION
    for entry in _read_entries(log_path):
        for campo in ("from_version", "to_version"):
            version = parse_semver(str(entry.get(campo) or ""))
            if version:
                mejor = max(mejor, version)
    return mejor
