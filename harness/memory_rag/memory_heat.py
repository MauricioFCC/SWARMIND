"""Politica de calor y eviccion de memoria (STM/MTM/LTM, MemoryOS 2025).

La memoria de agentes no es un almacen pasivo: las entradas compiten por
relevancia y las frias deben salir del camino (o marcarse) sin destruir
informacion. Este modulo implementa:

  - ``heat_score``: popularidad ponderada por recencia
    (``access_count * 0.5 ** (edad / half_life)``).
  - Segmentacion STM/MTM/LTM por antiguedad (MemoryOS, EMNLP 2025).
  - ``plan_eviction``: entradas frias y antiguas que se marcan ``evicted``
    (reversible; el retrieval deja de servirlas salvo peticion explicita).
  - ``apply_heat_policy``: escribe la marca + score en metadata.

El decaimiento por coleccion vive en ``HeatPolicy.half_life_for`` para que
lecciones de codigo (memoria de largo plazo) no compitan con preferencias
recientes del usuario.
"""

from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

#: Vida media (dias) por defecto si la coleccion no declara una.
DEFAULT_HALF_LIFE_DAYS = 30.0


@dataclass(frozen=True)
class HeatPolicy:
    """Umbrales de segmentacion y eviccion de memoria.

    Args:
        stm_max_age_hours: Antiguedad maxima de la memoria de trabajo (STM).
        mtm_max_age_days: Antiguedad maxima de la memoria a medio plazo (MTM).
        half_life_days: Vida media global del decaimiento por uso.
        evict_after_days: Edad minima para poder evacuar una entrada fria.
        min_heat: Score minimo para conservar una entrada antigua.
        per_collection_half_life: Override de vida media por coleccion.
    """

    stm_max_age_hours: float = 24.0
    mtm_max_age_days: float = 7.0
    half_life_days: float = DEFAULT_HALF_LIFE_DAYS
    evict_after_days: float = 180.0
    min_heat: float = 0.05
    per_collection_half_life: Mapping[str, float] = field(default_factory=dict)

    def half_life_for(self, collection: str) -> float:
        """Vida media efectiva de una coleccion.

        Args:
            collection: Nombre de la coleccion.

        Returns:
            Vida media en dias (override por coleccion o global).
        """
        return float(self.per_collection_half_life.get(collection, self.half_life_days))


@dataclass(frozen=True)
class HeatReport:
    """Resultado de aplicar la politica de calor a una coleccion.

    Attributes:
        scanned: Entradas evaluadas.
        evicted: Entradas marcadas como ``evicted``.
        segments: Conteo por segmento (``stm``/``mtm``/``ltm``).
    """

    scanned: int
    evicted: int
    segments: dict[str, int]


def _age_days(stamp: Any, now: dt.datetime) -> float | None:
    """Antiguedad en dias de un timestamp ISO (None si ilegible)."""
    if isinstance(stamp, dt.datetime):
        moment = stamp
    elif isinstance(stamp, str) and stamp:
        try:
            moment = dt.datetime.fromisoformat(stamp)
        except ValueError:
            return None
    else:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=dt.UTC)
    return max((now - moment.astimezone(dt.UTC)).total_seconds() / 86400.0, 0.0)


def heat_score(
    access_count: int,
    last_accessed: Any,
    now: dt.datetime,
    half_life_days: float,
) -> float:
    """Popularidad ponderada por recencia.

    Args:
        access_count: Veces que la entrada fue recordada.
        last_accessed: Timestamp ISO del ultimo uso.
        now: Instante de referencia (UTC aware).
        half_life_days: Vida media del decaimiento.

    Returns:
        Score >= 0 (0.0 si no hay datos utilizables).
    """
    age = _age_days(last_accessed, now)
    if age is None or half_life_days <= 0:
        return 0.0
    decay = 0.5 ** (age / half_life_days)
    return max(float(access_count), 0.0) * decay


def segment_for(age_days: float, policy: HeatPolicy) -> str:
    """Clasifica una entrada en STM/MTM/LTM por antiguedad.

    Args:
        age_days: Antiguedad en dias.
        policy: Politica de calor.

    Returns:
        ``stm``, ``mtm`` o ``ltm``.
    """
    if age_days <= policy.stm_max_age_hours / 24.0:
        return "stm"
    if age_days <= policy.mtm_max_age_days:
        return "mtm"
    return "ltm"


def plan_eviction(
    entries: list[dict[str, Any]],
    policy: HeatPolicy,
    now: dt.datetime | None = None,
    collection: str = "",
) -> list[str]:
    """Selecciona ids frios y antiguos para marcar como evadidos.

    Args:
        entries: Entradas normalizadas con ``id`` y ``metadata``.
        policy: Politica de calor.
        now: Instante de referencia (default UTC actual).
        collection: Coleccion evaluada (para el half-life por coleccion).

    Returns:
        Lista de ids a marcar.
    """
    reference = now or dt.datetime.now(dt.UTC)
    half_life = policy.half_life_for(collection)
    targets: list[str] = []
    for entry in entries:
        entry_id = entry.get("id")
        if not entry_id:
            continue
        meta = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
        stamp = meta.get("last_accessed") or entry.get("created_at")
        age = _age_days(stamp, reference)
        if age is None or age < policy.evict_after_days:
            continue
        score = heat_score(
            int(meta.get("access_count", 0) or 0),
            stamp,
            reference,
            half_life,
        )
        if score < policy.min_heat:
            targets.append(str(entry_id))
    return targets


def apply_heat_policy(
    store: Any,
    collection: str,
    policy: HeatPolicy | None = None,
    now: dt.datetime | None = None,
) -> HeatReport:
    """Marca el score/segmento y evacua lo frio de una coleccion.

    Args:
        store: Store con ``entries`` y ``update_records``.
        collection: Coleccion a evaluar.
        policy: Politica de calor (default ``HeatPolicy()``).
        now: Instante de referencia.

    Returns:
        ``HeatReport`` con el resultado.
    """
    active = policy or HeatPolicy()
    reference = now or dt.datetime.now(dt.UTC)
    half_life = active.half_life_for(collection)
    entries = list(store.entries(collection))
    evict_ids = set(plan_eviction(entries, active, reference, collection))
    segments = {"stm": 0, "mtm": 0, "ltm": 0}
    updates: list[dict[str, Any]] = []
    for entry in entries:
        meta = dict(entry.get("metadata") or {})
        stamp = meta.get("last_accessed") or entry.get("created_at")
        age = _age_days(stamp, reference)
        segment = segment_for(age if age is not None else 0.0, active)
        segments[segment] += 1
        meta["heat_score"] = heat_score(
            int(meta.get("access_count", 0) or 0), stamp, reference, half_life
        )
        meta["heat_segment"] = segment
        if str(entry.get("id")) in evict_ids:
            meta["evicted"] = True
        if entry.get("id"):
            updates.append(
                {
                    "id": str(entry["id"]),
                    "text": str(entry.get("text") or ""),
                    "metadata": meta,
                }
            )
    if updates:
        store.update_records(collection, updates)
    logger.info(
        "heat policy '%s': %d evaluadas, %d evadidas, segmentos=%s",
        collection, len(entries), len(evict_ids), segments,
    )
    return HeatReport(scanned=len(entries), evicted=len(evict_ids), segments=segments)


__all__ = [
    "DEFAULT_HALF_LIFE_DAYS",
    "HeatPolicy",
    "HeatReport",
    "apply_heat_policy",
    "heat_score",
    "plan_eviction",
    "segment_for",
]
