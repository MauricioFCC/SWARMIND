"""compaction_calibration.py — Compaction calibrada (AgeMem) (ADR-0074).

WHAT: Decide CUANDO y CUAN agresivamente compactar: ceiling de tokens con
zonas warn/critical de acciones diferenciadas + dedup de lineas repetidas.
WHY: AgeMem 2026 — thresholds calibrados (ceiling 6000, warn 0.75 ->
summary, critical 0.90 -> filter+drop) evitan compactions prematuras
(perdida de info) y tardias (overflow); el dedup de turnos repetidos es
puro waste de atencion.
WHERE: Delante de ``structured_compact`` (no lo reemplaza: lo invoca con
el budget_ratio correspondiente a la zona).

Uso:
    out = compact_calibrated(session_text)          # defaults AgeMem
    out = compact_calibrated(session_text, policy)  # calibrado
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from harness.memory_rag.compaction import structured_compact

logger = logging.getLogger("harness.memory_rag.compaction_calibration")

#: Techo de tokens de contexto de sesion (AgeMem).
DEFAULT_TOKEN_CEILING = 6000
#: Zona warn (fraccion del ceiling) -> compaction suave.
DEFAULT_WARN_RATIO = 0.75
#: Zona critical (fraccion del ceiling) -> compaction agresiva.
DEFAULT_CRITICAL_RATIO = 0.90
#: Ratio chars/token para estimacion rapida.
_CHARS_PER_TOKEN = 4
#: Repeticiones consecutivas que se conservan tras dedup.
_MAX_REPEATED_LINES = 2
#: Budget ratio de compaction suave (zona warn).
WARN_BUDGET_RATIO = 0.7
#: Budget ratio de compaction agresiva (zona critical).
CRITICAL_BUDGET_RATIO = 0.4


def estimate_tokens(text: str) -> int:
    """Estima tokens de un texto con ratio chars/token ~4.

    Args:
        text: Texto a estimar (puede ser vacio).

    Returns:
        Tokens estimados (>= 0).
    """
    return max(0, len(text) // _CHARS_PER_TOKEN)


@dataclass(frozen=True)
class CompactionPolicy:
    """Politica de compaction calibrada.

    Attributes:
        token_ceiling: Techo de tokens de la sesion.
        warn_ratio: Fraccion que activa la zona warn (0 < warn < 1).
        critical_ratio: Fraccion que activa la zona critical (warn < crit <= 1).

    Raises:
        ValueError: Si warn_ratio >= critical_ratio o ratios fuera de rango
            (WHAT+WHY+WHERE).
    """

    token_ceiling: int = DEFAULT_TOKEN_CEILING
    warn_ratio: float = DEFAULT_WARN_RATIO
    critical_ratio: float = DEFAULT_CRITICAL_RATIO

    def __post_init__(self) -> None:
        """Valida los ratios de la politica (WHAT+WHY+WHERE)."""
        if not (0.0 < self.warn_ratio < 1.0):
            raise ValueError(
                f"WHAT: warn_ratio invalido: {self.warn_ratio}. "
                "WHY: debe estar en (0, 1) para derivar una zona warn real. "
                "WHERE: CompactionPolicy.__post_init__"
            )
        if not (self.warn_ratio < self.critical_ratio <= 1.0):
            raise ValueError(
                f"WHAT: critical_ratio invalido: {self.critical_ratio} "
                f"(warn={self.warn_ratio}). "
                "WHY: critical debe ser estrictamente mayor que warn y <= 1. "
                "WHERE: CompactionPolicy.__post_init__"
            )

    @property
    def warn_tokens(self) -> float:
        """Umbral de tokens de la zona warn."""
        return self.token_ceiling * self.warn_ratio

    @property
    def critical_tokens(self) -> float:
        """Umbral de tokens de la zona critical."""
        return self.token_ceiling * self.critical_ratio


def _dedup_repeated_lines(text: str) -> str:
    """Colapsa lineas identicas consecutivas a _MAX_REPEATED_LINES.

    Args:
        text: Texto de sesion.

    Returns:
        Texto con repeticiones consecutivas colapsadas.
    """
    out_lines: list[str] = []
    run_value: str | None = None
    run_count = 0
    for line in text.splitlines():
        if line == run_value:
            run_count += 1
        else:
            run_value = line
            run_count = 1
        if run_count <= _MAX_REPEATED_LINES:
            out_lines.append(line)
    return "\n".join(out_lines)


def compact_calibrated(
    session_text: str,
    policy: CompactionPolicy | None = None,
) -> str:
    """Compacta la sesion segun la zona (ok/warn/critical) de la politica.

    Zonas: bajo warn -> solo dedup de repetidos; warn -> compaction suave
    (budget 0.7); critical -> compaction agresiva (budget 0.4).

    Args:
        session_text: Texto completo de la sesion (puede ser vacio).
        policy: Politica calibrada (None -> defaults AgeMem).

    Returns:
        Texto de sesion ajustado a la zona.
    """
    active_policy = policy or CompactionPolicy()
    tokens = estimate_tokens(session_text)
    if tokens <= active_policy.warn_tokens:
        return _dedup_repeated_lines(session_text)
    if tokens <= active_policy.critical_tokens:
        compacted = structured_compact(session_text, WARN_BUDGET_RATIO)
        return _dedup_repeated_lines(compacted)
    logger.info(
        "compaction_calibration: zona critical (%d >= %.0f tokens), ratio agresivo",
        tokens, active_policy.critical_tokens,
    )
    compacted = structured_compact(session_text, CRITICAL_BUDGET_RATIO)
    return _dedup_repeated_lines(compacted)
