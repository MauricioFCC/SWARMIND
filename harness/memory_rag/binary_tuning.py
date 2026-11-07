"""Ajuste de oversampling del KNN binario por carga real (SPEC-0171).

RaBitQ necesita ``oversample`` (candidatos binarios antes del rescore exacto):
un valor bajo ahorra CPU pero puede romper recall; uno alto lo garantiza a
coste lineal. El valor optimo depende de la distribucion de la coleccion y del
trafico real, no de una constante.

Este modulo implementa un lazo de control simple y medible:

  - ``recall`` muestreado: en una fraccion configurable de queries se compara
    el top-k binario contra el KNN exacto (ground truth) y se calcula la
    interseccion.
  - EWMA del recall por coleccion + ajuste multiplicativo del oversample
    dentro de ``[min_oversample, max_oversample]``.
  - Persistencia opcional en el store (``semantic_cache_set`` con
    ``kind="bq_tuner"``), para sobrevivir reinicios.

El objetivo por defecto es recall@k >= 0.90 (criterio de aceptacion del spec).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

#: Prefijo de claves de persistencia del tuner.
TUNER_KEY_PREFIX = "__bq_oversample__"

#: Marca de metadata para no confundir el estado con entradas del cache.
TUNER_KIND = "bq_tuner"


@dataclass
class OversampleTuner:
    """Control adaptativo del oversample del KNN binario.

    Args:
        target_recall: Recall objetivo (0-1).
        min_oversample: Piso del factor.
        max_oversample: Techo del factor.
        alpha: Peso del EWMA (0-1).
        up_factor: Multiplicador al subir (recall bajo).
        down_factor: Multiplicador al bajar (recall alto).
        upper_margin: Holgura sobre el objetivo para empezar a bajar.
        store: Store opcional con ``semantic_cache_get/set`` para persistir.
    """

    target_recall: float = 0.90
    min_oversample: int = 1
    max_oversample: int = 8
    alpha: float = 0.3
    up_factor: float = 1.25
    down_factor: float = 0.8
    upper_margin: float = 0.05
    store: Any = None
    _values: dict[str, int] = field(default_factory=dict)
    _recall: dict[str, float] = field(default_factory=dict)
    _samples: dict[str, int] = field(default_factory=dict)
    _loaded: set[str] = field(default_factory=set)

    def _key(self, collection: str) -> str:
        """Clave de persistencia por coleccion."""
        return f"{TUNER_KEY_PREFIX}{collection}"

    def _load(self, collection: str) -> None:
        """Carga perezosa del valor persistido (una vez por coleccion)."""
        if collection in self._loaded or self.store is None:
            return
        self._loaded.add(collection)
        getter = getattr(self.store, "semantic_cache_get", None)
        if not callable(getter):
            return
        try:
            value = getter(self._key(collection))
        except Exception as exc:  # noqa: BLE001
            logger.debug("oversample tuner load fallo: %s", exc)
            return
        if isinstance(value, (int, float)):
            self._values[collection] = self._clamp(int(value))

    def _persist(self, collection: str, value: int) -> None:
        """Guarda el valor ajustado (best effort)."""
        setter = getattr(self.store, "semantic_cache_set", None)
        if not callable(setter):
            return
        try:
            setter(self._key(collection), value, None, {"kind": TUNER_KIND})
        except Exception as exc:  # noqa: BLE001
            logger.debug("oversample tuner persist fallo: %s", exc)

    def _clamp(self, value: int) -> int:
        """Acota el oversample al rango permitido."""
        return max(self.min_oversample, min(self.max_oversample, int(value)))

    def value_for(self, collection: str) -> int:
        """Oversample vigente para una coleccion.

        Args:
            collection: Coleccion consultada.

        Returns:
            Factor de oversampling en ``[min_oversample, max_oversample]``.
        """
        self._load(collection)
        return self._values.get(collection, self.min_oversample)

    def observe(self, collection: str, recall: float) -> int:
        """Actualiza el oversample con el recall medido de una query.

        Args:
            collection: Coleccion consultada.
            recall: Recall@k observado (0-1) frente al KNN exacto.

        Returns:
            Oversample ajustado.
        """
        recall = max(0.0, min(1.0, float(recall)))
        current = self.value_for(collection)
        previous = self._recall.get(collection)
        smoothed = recall if previous is None else (
            self.alpha * recall + (1.0 - self.alpha) * previous
        )
        self._recall[collection] = smoothed
        self._samples[collection] = self._samples.get(collection, 0) + 1
        if smoothed < self.target_recall:
            updated = self._clamp(
                max(current + 1, math.ceil(current * self.up_factor))
            )
        elif smoothed > self.target_recall + self.upper_margin:
            updated = self._clamp(
                min(current - 1, math.floor(current * self.down_factor))
            )
        else:
            updated = current
        if updated != current:
            logger.info(
                "oversample '%s': %d -> %d (recall~%.3f, muestras=%d)",
                collection, current, updated, smoothed, self._samples[collection],
            )
        self._values[collection] = updated
        self._persist(collection, updated)
        return updated

    def stats(self) -> dict[str, Any]:
        """Resumen del control para telemetria.

        Returns:
            ``{collections, values, recalls, samples}``.
        """
        return {
            "collections": len(self._values),
            "values": dict(self._values),
            "recalls": {k: round(v, 4) for k, v in self._recall.items()},
            "samples": dict(self._samples),
        }


__all__ = ["TUNER_KEY_PREFIX", "TUNER_KIND", "OversampleTuner"]
