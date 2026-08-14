"""Clase ``ComplexityRouter`` — enrutador por complejidad semantica.

Antes: harness/model_router/complexity_router.py (539 lineas).
Ahora: paquete ``harness/model_router/complexity_router/``:

- ``constants.py``: constantes (umbrales, ponderaciones, senales).
- ``models.py``: dataclasses ``ComplexityDecision`` y ``ComplexityResult``.
- ``signals.py``: mixin ``_SignalMixin`` (extraccion de senales + scoring).
- ``routing.py``: mixin ``_RoutingMixin`` (decide/route/validacion/fallback).
- ``core.py``: clase ``ComplexityRouter(_SignalMixin, _RoutingMixin)``.

Regla AGR: cada archivo del paquete queda por debajo de 500 lineas.
"""

from __future__ import annotations

from .constants import DEFAULT_THRESHOLD
from .routing import _RoutingMixin
from .signals import _SignalMixin


class ComplexityRouter(_SignalMixin, _RoutingMixin):
    """Router por complejidad semántica 0..100.

    Args:
        threshold: Umbral de complejidad (score >= umbral -> frontier).
        domain_hint: Pista de dominio complejo (ej. "legal") que inyecta
            la señal domain_complex aunque no haya keywords en el texto.
    """

    def __init__(
        self,
        threshold: float = DEFAULT_THRESHOLD,
        domain_hint: str | None = None,
    ) -> None:
        self.threshold = threshold
        self._domain_hint = domain_hint
