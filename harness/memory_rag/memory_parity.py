"""Health-check de paridad de memoria (Item 4 — memoria-optimality).

WHAT: Audita la memoria central (LanceDB) y detecta cuando las caches
regenerables dominan el almacenamiento mientras las colecciones de VALOR
(informacion que sostiene las decisiones) estan vacias.
WHY: En 2026-10 ``semantic_cache`` (138 MB, 5201 fragments) +
``agent_workspace_logs`` (48 MB) sumaban 99.7% del disco, y las 13
colecciones de valor estaban en ~0.3 MB (casi todas schema-only). Ese
desequilibrio significa que el harness acumula cache de retrieval pero no
experiencia que mejorar las decisiones. Nadie lo vigilaba.
WHERE: ``scripts/verify_swarmind_setup.py`` (seccion NO fatal, warning).

Contratos: 11-15 de ``docs/specs/memory-optimality.md``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from harness.memory_rag.memory_bootstrap import VOLATILE_COLLECTIONS

logger = logging.getLogger("harness.memory_rag.memory_parity")

#: La cache "domina" si supera este multiplo del conocimiento de valor.
_CACHE_DOMINANCE_RATIO = 4
#: Minimo de colecciones de valor vacias para declarar desbalance.
_MIN_EMPTY_VALUE_COLLECTIONS = 3
#: Colecciones con <= a este numero de fragments de datos se consideran
#: schema-only (vacias). Medido en 2026-10: las vacias tenian 2 fragments
#: (schema-init) y las pobladas >= 8.
_EMPTY_MAX_DATA_FILES = 2


@dataclass(frozen=True)
class ParityReport:
    """Resultado de ``audit_parity``.

    Attributes:
        cache_bytes: Bytes totales de las colecciones volatiles (regenerables).
        value_bytes: Bytes totales de las colecciones de valor.
        value_collections_empty: Colecciones de valor schema-only (vacias).
        is_imbalanced: True si la cache domina y hay >=3 valor vacias.
    """

    cache_bytes: int
    value_bytes: int
    value_collections_empty: tuple[str, ...]
    is_imbalanced: bool


def _collection_bytes(path: Path) -> int:
    """Bytes totales de una coleccion ``.lance`` (recursivo).

    Args:
        path: Directorio ``<nombre>.lance``.

    Returns:
        Suma de tamano de archivos ([] si no se puede leer).
    """
    try:
        return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    except OSError as exc:
        logger.warning("memory_parity: no se pudo medir %s: %s", path, exc)
        return 0


def _data_file_count(path: Path) -> int:
    """Numero de fragments de datos de una coleccion (subdir ``data/``).

    Args:
        path: Directorio ``<nombre>.lance``.

    Returns:
        Numero de archivos de datos (0 si el subdir no existe).
    """
    data_dir = path / "data"
    if not data_dir.is_dir():
        return 0
    try:
        return sum(1 for f in data_dir.iterdir() if f.is_file())
    except OSError:
        return 0


def _collection_name(entry: Path) -> str:
    """Extrae el nombre de coleccion de un directorio ``.lance``.

    Args:
        entry: Entrada del filesystem ``<nombre>.lance``.

    Returns:
        Nombre sin el sufijo ``.lance``.
    """
    return entry.name.removesuffix(".lance")


def audit_parity(db_path: str | Path) -> ParityReport:
    """Audita la paridad caches-vs-valor de la memoria central.

    Cuenta bytes de colecciones volatiles (cache) vs de valor, y detecta
    colecciones de valor vacias (schema-only). ``is_imbalanced`` es True solo
    si la cache supera ``_CACHE_DOMINANCE_RATIO`` veces el valor Y hay al
    menos ``_MIN_EMPTY_VALUE_COLLECTIONS`` colecciones de valor vacias.

    Args:
        db_path: Directorio ``data/lancedb`` de la memoria central.

    Returns:
        ParityReport con metricas y bandera de desbalance. Si ``db_path``
        no existe, devuelve un report vacio (``is_imbalanced=False``).
    """
    root = Path(db_path)
    if not root.is_dir():
        logger.debug("memory_parity: path inexistente %s (report vacio)", root)
        return ParityReport(0, 0, (), False)

    cache_bytes = 0
    value_bytes = 0
    empty: list[str] = []

    for entry in sorted(root.iterdir()):
        if not entry.name.endswith(".lance") or not entry.is_dir():
            continue
        name = _collection_name(entry)
        size = _collection_bytes(entry)
        if name in VOLATILE_COLLECTIONS:
            cache_bytes += size
            continue
        value_bytes += size
        if _data_file_count(entry) <= _EMPTY_MAX_DATA_FILES:
            empty.append(name)

    is_imbalanced = (
        cache_bytes > _CACHE_DOMINANCE_RATIO * value_bytes
        and len(empty) >= _MIN_EMPTY_VALUE_COLLECTIONS
    )
    report = ParityReport(cache_bytes, value_bytes, tuple(empty), is_imbalanced)
    if is_imbalanced:
        logger.warning(
            "memory_parity DESBALANCE: cache=%d bytes > %dx valor=%d bytes; "
            "valor vacias=%s. WHY: cache regenerable domina el SSOT sin aportar "
            "recall. WHERE: memory_parity.audit_parity. ACCION: poblar colecciones "
            "de valor / barrer caches (clear_expired).",
            cache_bytes, _CACHE_DOMINANCE_RATIO, value_bytes, report.value_collections_empty,
        )
    return report
