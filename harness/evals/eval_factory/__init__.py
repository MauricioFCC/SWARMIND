"""EvalFactory (refactorizado a paquete).

Antes: harness/evals/eval_factory.py (655 lineas).
Ahora: paquete ``harness/evals/eval_factory/`` con submódulos cohesivos:

- ``models.py``: ``EvalResult``, ``EvalSuite``, ``EvalReport``, ``EvalDiff``.
- ``registry.py``: ``_LAYER_EVAL_REGISTRY``, ``register_layer_evals``,
  ``run_layer``, ``run_all``.
- ``recommend.py``: ``_generate_recommendations``, ``get_recommendations``.
- ``compare.py``: ``compare_reports``.

Este ``__init__.py`` re-exporta TODOS los simbolos publicos del modulo
original para mantener backward-compat:

    from harness.evals.eval_factory import EvalResult, register_layer_evals

Regla AGR: cada archivo del paquete queda por debajo de 500 lineas.
"""

from __future__ import annotations

from .compare import compare_reports
from .models import EvalDiff, EvalReport, EvalResult, EvalSuite
from .recommend import (
    _generate_recommendations as _generate_recommendations,
)
from .recommend import (
    get_recommendations,
)
from .registry import (
    _LAYER_EVAL_REGISTRY as _LAYER_EVAL_REGISTRY,
)
from .registry import (
    register_layer_evals,
    run_all,
    run_layer,
)

__all__ = [
    "EvalDiff",
    "EvalReport",
    "EvalResult",
    "EvalSuite",
    "compare_reports",
    "get_recommendations",
    "register_layer_evals",
    "run_all",
    "run_layer",
]
