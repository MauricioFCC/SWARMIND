"""escalation_policy.py — Escalado por verificacion (ADR-0102).

WHAT: decide, para una salida de modelo local, si se ACEPTA, se ESCALA a un
tier mayor de la flota, o se delega a CLOUD. Combina dos senales baratas:
(1) verificador estructural (vacio/enano/degenerado, JSON invalido) y
(2) confianza verbalizada en el propio texto (0..1), sin token-logprobs.
WHY: frontera 2026 (MetaRoute arXiv:2608.00107: *verificar* pesa mas que
*clasificar*; UCCI arXiv:2605.18796: escalar small->large con incertidumbre
calibrada). Ollama no expone logprobs, asi que la calibracion classic no es
posible: se usan proxies medibles. Antes de calibrar por isotonic hace falta
el journal etiquetado; esta es la infraestructura prerequisito (traza tipada
+ decision determinista) que no depende de datos aun inexistentes.
WHERE: `LocalExecutor` (tras generar) y `run.py`/orquestador antes del
fallback cloud. Traza consumible por el failure registry.

Uso:
    decision = decide(tier="fast", output=texto, expect_json=True)
    if decision.action == "escalate": reintentar_en(decision.target_tier)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

#: Escalera de escalado dentro de la flota (barato -> caro).
TIER_LADDER: tuple[str, ...] = ("fast", "quality", "coding", "reasoning")
#: Umbral de confianza verbalizada bajo el cual se escala (UCCI: calibrar
#: con el journal antes de endurecerlo; 0.70 es el gate inicial conservador).
VERBALIZED_CONFIDENCE_THRESHOLD = 0.70
#: Salida minima aceptable (alineado con LocalExecutor.MIN_LOCAL_OUTPUT_CHARS).
MIN_OUTPUT_CHARS = 8
#: Ratio maximo del caracter dominante (degeneracion tipica SLM).
MAX_REPEAT_RATIO = 0.5

_CONFIDENCE_RE = re.compile(
    r"confianza\s*[:=]\s*(\d+(?:\.\d+)?)\s*%?"
    r"|confidence\s*[:=]\s*(\d+(?:\.\d+)?)\s*%?",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Verdict:
    """Resultado del verificador estructural.

    Attributes:
        ok: True si la salida pasa el verificador.
        verifier: Nombre del verificador aplicado.
        detail: Explicacion corta (para traza/observabilidad).
    """

    ok: bool
    verifier: str
    detail: str


@dataclass(frozen=True)
class EscalationDecision:
    """Decision de la politica de escalado (traza tipada).

    Attributes:
        action: "accept", "escalate" o "cloud".
        target_tier: Tier destino cuando action == "escalate".
        verdict: Verificador que fundamento la decision.
        reason: Motivo legible (WHAT/WHY).
    """

    action: str
    target_tier: str | None
    verdict: Verdict
    reason: str


def verify_structural(
    output: str, expect_json: bool = False, min_chars: int = MIN_OUTPUT_CHARS
) -> Verdict:
    """Verificador barato: contenido real y (si aplica) JSON valido.

    Args:
        output: Texto generado por el modelo local.
        expect_json: True si la tarea exige JSON parseable.
        min_chars: Longitud minima aceptable.

    Returns:
        Verdict con ok=False si esta vacio, es enano, degenerado o JSON
        invalido cuando se esperaba JSON.
    """
    text = (output or "").strip()
    if len(text) < min_chars:
        return Verdict(False, "length", f"salida de {len(text)} chars (<{min_chars})")
    top = max(text.count(ch) for ch in set(text)) if text else 0
    if top / len(text) > MAX_REPEAT_RATIO:
        return Verdict(False, "degenerate", "caracter dominante >50%")
    if expect_json:
        try:
            json.loads(text)
        except (json.JSONDecodeError, ValueError) as exc:
            return Verdict(False, "json", f"JSON invalido: {exc}")
    return Verdict(True, "structural", "ok")


def parse_confidence(output: str) -> float | None:
    """Extrae confianza verbalizada 0..1 del texto (None si no aparece).

    Normaliza porcentajes: "confianza: 85%" -> 0.85. Valores fuera de rango
    se descartan (None) en vez de recortarse: un dato absurdo no debe
    mover la decision.

    Args:
        output: Texto generado.

    Returns:
        Confianza en [0, 1] o None.
    """
    match = _CONFIDENCE_RE.search(output or "")
    if match is None:
        return None
    raw = match.group(1) or match.group(2)
    value = float(raw)
    if "%" in match.group(0):
        value /= 100
    return value if 0.0 <= value <= 1.0 else None


def next_tier(tier: str) -> str | None:
    """Siguiente tier mas capaz en la escalera (None si ya es el tope).

    Args:
        tier: Tier actual ("fast", "quality", "coding", "reasoning").

    Returns:
        Tier superior, o None si `tier` es el ultimo (=> cloud).
    """
    if tier not in TIER_LADDER:
        return TIER_LADDER[1] if len(TIER_LADDER) > 1 else None
    index = TIER_LADDER.index(tier)
    return TIER_LADDER[index + 1] if index + 1 < len(TIER_LADDER) else None


def decide(
    tier: str,
    output: str,
    expect_json: bool = False,
    confidence_threshold: float = VERBALIZED_CONFIDENCE_THRESHOLD,
) -> EscalationDecision:
    """Decide aceptar, escalar dentro de la flota o delegar a cloud.

    Regla (frontera): primero el verificador estructural; si la salida es
    invalida se escala. Si es valida pero la confianza verbalizada esta por
    debajo del umbral, se escala preventivamente. En el tope de la escalera
    se delega a cloud.

    Args:
        tier: Tier que produjo la salida.
        output: Texto generado.
        expect_json: True si la tarea exige JSON parseable.
        confidence_threshold: Umbral de confianza verbalizada.

    Returns:
        EscalationDecision con accion, target_tier y traza.
    """
    verdict = verify_structural(output, expect_json=expect_json)
    if verdict.ok:
        confidence = parse_confidence(output)
        if confidence is None or confidence >= confidence_threshold:
            return EscalationDecision(
                "accept", None, verdict,
                f"salida valida ({verdict.verifier})"
                + ("" if confidence is None else f", confianza {confidence:.2f}"),
            )

    reason = (
        f"salida invalida ({verdict.detail})" if not verdict.ok
        else "confianza verbalizada baja"
    )
    target = next_tier(tier)
    if target is None:
        return EscalationDecision("cloud", None, verdict, f"{reason}: tope de flota -> cloud")
    return EscalationDecision("escalate", target, verdict, f"{reason} -> {target}")
