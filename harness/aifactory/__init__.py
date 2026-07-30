"""
AIFactory — Entry point del orquestador AI Factory Stack 7-capas.

Provee acceso lazy a los simbolos principales via __getattr__ (PEP 562)
para evitar imports pesados en cold-start. El modulo central es factory.py.

Exporta:
    AIFactory        -> Clase orquestadora principal
    FactoryStatus    -> Enum de estados del pipeline
    FactoryConfig    -> Configuracion del factory
    FactoryResult    -> Resultado del pipeline completo
    LayerTrace       -> Traza individual por capa
    LayerType        -> Enum de tipos de capa

Uso:
    from harness.aifactory import AIFactory, FactoryStatus
    factory = AIFactory()
    result = factory.process("Construye un microservicio")
    print(result.status)
"""

from __future__ import annotations

import importlib
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mapa de simbolos para lazy loading
# ---------------------------------------------------------------------------
_SYMBOL_MAP: dict[str, str] = {
    "AIFactory": "harness.aifactory.factory",
    "FactoryConfig": "harness.aifactory.factory",
    "FactoryResult": "harness.aifactory.factory",
    "LayerTrace": "harness.aifactory.factory",
    "FactoryStatus": "harness.aifactory.factory",
    "LayerType": "harness.aifactory.factory",
}


def __getattr__(name: str) -> Any:
    """Importacion lazy de simbolos del modulo factory.

    Solo carga harness.aifactory.factory cuando se accede por primera vez
    a un simbolo, reduciendo el cold-start de ~300ms a ~5ms.

    Args:
        name: Nombre del simbolo a importar.

    Returns:
        El objeto solicitado (clase, enum o funcion).

    Raises:
        AttributeError: Si el simbolo no esta registrado en _SYMBOL_MAP.
    """
    module_path = _SYMBOL_MAP.get(name)
    if module_path is None:
        raise AttributeError(
            f"module 'harness.aifactory' has no attribute '{name}'. "
            f"Simbolos disponibles: {list(_SYMBOL_MAP.keys())}"
        )

    module = importlib.import_module(module_path)
    attr = getattr(module, name, None)
    if attr is None:
        raise AttributeError(
            f"module '{module_path}' no contiene el atributo '{name}'. "
            f"Posible error de definicion en factory.py."
        )

    globals()[name] = attr
    return attr


def __dir__() -> list:
    """Soporte para autocompletado en editores y shells interactivos.

    Returns:
        Lista de nombres de simbolos exportables.
    """
    return list(_SYMBOL_MAP.keys())


__all__ = list(_SYMBOL_MAP.keys())
