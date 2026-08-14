"""Carga de YAML de configuracion: funcion ``load_yaml``.

Extraido mecanicamente de ``token_budget_manager.py`` (regla AGR < 500
lineas). Sin cambios de logica ni de firmas.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_yaml(path: str | Path) -> dict[str, Any]:
    """Carga un archivo YAML de configuracion.

    WHAT: Lee el archivo en ``path`` (UTF-8) y retorna su contenido como
    un diccionario plano.
    WHY: Centralizar el parsing YAML evita duplicar la logica en cada
    consumidor y garantiza un unico punto de error con contexto WHAT+WHY+WHERE.
    WHERE: ``TokenBudgetManager`` — carga del SSOT token_budgets.yaml.

    Args:
        path: Ruta del archivo YAML.

    Returns:
        Contenido del YAML como dict.

    Raises:
        FileNotFoundError: Si el archivo no existe.
        TypeError: Si el contenido no es un mapping plano.
        ValueError: Si el YAML esta mal formado.
    """
    yaml_path = Path(path)
    if not yaml_path.is_file():
        raise FileNotFoundError(
            f"WHAT: No se encontro el archivo YAML '{yaml_path}'. "
            f"WHY: El SSOT de budgets debe existir para cargar configuracion. "
            f"WHERE: load_yaml()"
        )
    try:
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(
            f"WHAT: El YAML '{yaml_path}' esta mal formado ({exc}). "
            f"WHY: Un SSOT corrupto degradaria silenciosamente los budgets. "
            f"WHERE: load_yaml()"
        ) from exc
    if not isinstance(data, dict):
        raise TypeError(
            f"WHAT: El YAML '{yaml_path}' no contiene un mapping en la raiz "
            f"(tipo: {type(data).__name__}). "
            f"WHY: El SSOT de budgets debe ser un dict de secciones. "
            f"WHERE: load_yaml()"
        )
    return data
