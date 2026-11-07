"""Umbral adaptativo por prompt para el cache semantico (vCache, ICLR 2026).

Un umbral global fijo produce tasas de error no garantizadas: la similitud
necesaria para que un hit sea correcto depende del tipo de prompt. vCache
aprende el umbral por familia de prompt con feedback de aciertos.

Implementacion: cubos por prefijo del prompt; cada cubo mantiene un umbral en
``[min_threshold, max_threshold]`` que sube ante un falso positivo y baja ante
un acierto confirmado. Persistencia opcional en el store (coleccion
``semantic_cache``, metadata ``kind="threshold"``), de modo que el aprendizaje
sobrevive reinicios.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

#: Prefijo reservado de claves de persistencia del umbral.
THRESHOLD_KEY_PREFIX = "__adaptive_threshold__"

#: Marca de metadata para que invalidacion/purga no confundan el estado.
THRESHOLD_KIND = "threshold"


@dataclass
class AdaptiveThreshold:
    """Umbral aprendido por familia de prompt.

    Args:
        base: Umbral inicial (el configurado en el cache).
        min_threshold: Piso del aprendizaje.
        max_threshold: Techo del aprendizaje.
        step: Incremento/decremento por observacion.
        prefix_chars: Caracteres del prompt que definen la familia.
        store: Store opcional con ``semantic_cache_get/set`` para persistir.
    """

    base: float = 0.92
    min_threshold: float = 0.90
    max_threshold: float = 0.99
    step: float = 0.005
    prefix_chars: int = 48
    store: Any = None
    _buckets: dict[str, float] = field(default_factory=dict)
    _loaded: set[str] = field(default_factory=set)

    def bucket(self, prompt: str) -> str:
        """Identificador estable de la familia del prompt.

        Args:
            prompt: Prompt normalizado.

        Returns:
            Hex corto del prefijo del prompt.
        """
        head = (prompt or "")[: self.prefix_chars]
        return hashlib.sha256(head.encode("utf-8")).hexdigest()[:16]

    def _persist_key(self, bucket: str) -> str:
        """Clave de persistencia de un cubo."""
        return f"{THRESHOLD_KEY_PREFIX}{bucket}"

    def _load(self, bucket: str) -> None:
        """Carga perezosa del umbral persistido (una vez por cubo)."""
        if bucket in self._loaded or self.store is None:
            return
        self._loaded.add(bucket)
        getter = getattr(self.store, "semantic_cache_get", None)
        if not callable(getter):
            return
        try:
            value = getter(self._persist_key(bucket))
        except Exception as exc:  # noqa: BLE001
            logger.debug("adaptive threshold load fallo: %s", exc)
            return
        if isinstance(value, (int, float)):
            self._buckets[bucket] = self._clamp(float(value))

    def _persist(self, bucket: str, value: float) -> None:
        """Guarda el umbral aprendido (best effort)."""
        setter = getattr(self.store, "semantic_cache_set", None)
        if not callable(setter):
            return
        try:
            setter(
                self._persist_key(bucket),
                value,
                None,
                {"kind": THRESHOLD_KIND},
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("adaptive threshold persist fallo: %s", exc)

    def _clamp(self, value: float) -> float:
        """Acota el umbral al rango permitido."""
        return max(self.min_threshold, min(self.max_threshold, value))

    def threshold_for(self, prompt: str) -> float:
        """Umbral efectivo para un prompt.

        Args:
            prompt: Prompt normalizado.

        Returns:
            Umbral aprendido del cubo (o ``base``).
        """
        bucket = self.bucket(prompt)
        self._load(bucket)
        return self._buckets.get(bucket, self.base)

    def observe(self, prompt: str, correct: bool) -> float:
        """Actualiza el umbral con feedback de un hit.

        Args:
            prompt: Prompt que produjo el hit.
            correct: True si la respuesta cacheada fue correcta.

        Returns:
            Umbral actualizado.
        """
        bucket = self.bucket(prompt)
        self._load(bucket)
        current = self._buckets.get(bucket, self.base)
        delta = -self.step if correct else self.step
        updated = self._clamp(current + delta)
        self._buckets[bucket] = updated
        self._persist(bucket, updated)
        return updated

    def stats(self) -> dict[str, Any]:
        """Resumen del aprendizaje para telemetria.

        Returns:
            ``{buckets, mean_threshold, min, max}``.
        """
        values = list(self._buckets.values())
        return {
            "buckets": len(values),
            "mean_threshold": (sum(values) / len(values)) if values else self.base,
            "min": min(values) if values else self.base,
            "max": max(values) if values else self.base,
        }


__all__ = [
    "THRESHOLD_KEY_PREFIX",
    "THRESHOLD_KIND",
    "AdaptiveThreshold",
]
