"""Constantes del paquete ``token_budget_manager``.

Extraido mecanicamente de ``token_budget_manager.py`` (regla AGR < 500
lineas). Sin cambios de logica: los valores y nombres son identicos al
original.
"""
from __future__ import annotations

from pathlib import Path

# Ruta por defecto del SSOT de budgets, relativa al repo root (SWARMIND/).
# Nota: al vivir ahora en ``token_budget_manager/constants.py`` (un nivel
# mas profundo que el modulo plano original) se necesitan 4 ``parent`` para
# preservar la MISMA ruta fisica: SWARMIND/.opencode/config/token_budgets.yaml.
DEFAULT_TOKEN_BUDGETS_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent / ".opencode" / "config" / "token_budgets.yaml"
)

# Umbral de compresion por defecto (mismo valor que defaults.compression_threshold del YAML).
DEFAULT_COMPRESSION_THRESHOLD = 0.85

# Nivel de compresion neutro para roles sin configuracion explicita.
DEFAULT_COMPRESSION_LEVEL = "none"
