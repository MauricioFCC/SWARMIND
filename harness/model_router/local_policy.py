"""local_policy.py — Politica local-first config-driven, sin hardcode (ADR-0084).

WHAT: Carga `local_first:` del YAML (target_local_ratio, confidence_margin,
sample_rate) con overrides por entorno (`SWARMIND_LOCAL_*`) y defaults
seguros si falta el archivo.
WHY: Frontera (RLM-Cascade/Local-Splitter/UCCI): el ratio local objetivo
(>=60%), el margen anti falso-positivo y la tasa de supervision son
parametros operativos — viven en config, no en codigo.
WHERE: `DraftReviewer` (margin), `LocalSupervisor` (sample_rate) y el
monitor de ratio (target).

Uso:
    policy = load_local_policy(Path(".opencode/config/ollama_models.yaml"))
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("harness.model_router.local_policy")

#: Prefijo de overrides por entorno.
ENV_PREFIX = "SWARMIND_LOCAL_"
#: Defaults seguros (documentados en el YAML).
DEFAULT_TARGET_RATIO = 0.6
DEFAULT_CONFIDENCE_MARGIN = 0.5
DEFAULT_SAMPLE_RATE = 0.1


@dataclass(frozen=True)
class LocalPolicy:
    """Politica local-first (inmutable).

    Attributes:
        target_local_ratio: Objetivo de tareas en local (0..1).
        confidence_margin: Margen anti falso-positivo (0..1).
        sample_rate: Fraccion auditada por el cloud (0..1).

    Raises:
        ValueError: Si algun valor esta fuera de [0, 1].
    """

    target_local_ratio: float = DEFAULT_TARGET_RATIO
    confidence_margin: float = DEFAULT_CONFIDENCE_MARGIN
    sample_rate: float = DEFAULT_SAMPLE_RATE

    def __post_init__(self) -> None:
        """Valida los tres ratios (WHAT+WHY+WHERE)."""
        for name in ("target_local_ratio", "confidence_margin", "sample_rate"):
            value = getattr(self, name)
            if not (0.0 <= value <= 1.0):
                raise ValueError(
                    f"WHAT: {name} invalido: {value}. "
                    "WHY: es una fraccion, debe estar en [0, 1]. "
                    "WHERE: LocalPolicy.__post_init__"
                )


def _parse_simple_yaml(text: str) -> dict:
    """Parse minimo de YAML (seccion local_first, sin dependencias).

    Args:
        text: Contenido del YAML.

    Returns:
        Dict con las claves de local_first (vacio si no hay seccion).
    """
    out: dict = {}
    in_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not line.startswith((" ", "\t")):
            in_section = stripped.rstrip(":") == "local_first"
            continue
        if in_section and ":" in stripped:
            key, _, value = stripped.partition(":")
            cleaned = value.split("#", 1)[0].strip()
            try:
                out[key.strip()] = float(cleaned)
            except ValueError:
                logger.warning("local_policy: valor no numerico '%s' ignorado", key)
    return out


def load_local_policy(yaml_path: str | Path) -> LocalPolicy:
    """Carga la politica desde YAML + entorno (sin hardcode).

    Precedencia: entorno `SWARMIND_LOCAL_*` > YAML > defaults.

    Args:
        yaml_path: Ruta del YAML (si no existe, solo defaults+env).

    Returns:
        LocalPolicy validada.
    """
    values: dict[str, float] = {
        "target_local_ratio": DEFAULT_TARGET_RATIO,
        "confidence_margin": DEFAULT_CONFIDENCE_MARGIN,
        "sample_rate": DEFAULT_SAMPLE_RATE,
    }
    path = Path(yaml_path)
    if path.is_file():
        try:
            values.update(_parse_simple_yaml(path.read_text(encoding="utf-8")))
        except OSError as exc:
            logger.warning("local_policy: no se pudo leer %s: %s", path, exc)
    env_map = {
        "TARGET_LOCAL_RATIO": "target_local_ratio",
        "CONFIDENCE_MARGIN": "confidence_margin",
        "SAMPLE_RATE": "sample_rate",
    }
    for env_key, field in env_map.items():
        raw = os.environ.get(ENV_PREFIX + env_key, "").strip()
        if raw:
            try:
                values[field] = float(raw)
            except ValueError:
                logger.warning("local_policy: %s%s no numerico, ignorado", ENV_PREFIX, env_key)
    return LocalPolicy(**values)
