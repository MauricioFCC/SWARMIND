"""Harness Critic — atribucion de fallos a causas harness-level + diffs locales.

Marco de frontera **Co-Harness** (arXiv:2607.22688): el harness deja de ser un
artefacto fijo y pasa a ser una VARIABLE de optimizacion. Este modulo aporta la
pieza que faltaba en el loop EVO: atribuir cada fallo observado a una CAUSA
harness-level (prompt ambiguo, schema de tool, skill ausente, middleware,
desborde de contexto, gap de guardrail) y proponer un DIFF LOCAL por causa que
luego se valida con un re-rollout (Pareto accuracy x wall-clock + seguridad de
rollback sobre held-out).

Diseno:
    - ``HarnessCause`` / ``HarnessDiff`` son ``frozen dataclass`` (IMM).
    - ``HarnessCritic`` recibe el ``classifier`` por DI (kw-only); el default es
      DETERMINISTA (sin LLM): mapea patrones del mensaje a categorias via
      ``_CAUSE_RULES`` (orden de precedencia explicito).
    - ``validate`` es Pareto-aware: acepta solo si hay mejora Y el held-out no
      cae fuera de tolerancia (rollback safety).
    - ``pareto_accept`` decide sobre la frontera accuracy x wall-clock.
    - El modulo NO ejecuta LLM ni aplica cambios: solo clasifica y propone.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Literal

logger = logging.getLogger(__name__)

#: Categorias de causa harness-level (MAG: Literal como enum de strings).
HarnessCauseCategory = Literal[
    "prompt_ambiguity",
    "tool_schema_error",
    "missing_skill",
    "middleware_mismatch",
    "context_overflow",
    "guardrail_gap",
]

#: Firma del classifier: mensaje de fallo -> categoria harness-level.
Classifier = Callable[[str], HarnessCauseCategory]

#: Limite de longitud de la evidencia cuando no hay fragmento (MAG).
_EVIDENCE_LIMIT = 160

#: Confianza base por defecto al matchear un patron (MAG).
_CONFIDENCE_BASE = 0.60
#: Incremento de confianza por cada match adicional del patron (MAG).
_CONFIDENCE_PER_HIT = 0.10
#: Techo de confianza (nunca 1.0: es heuristica, no certeza) (MAG).
_CONFIDENCE_MAX = 0.95
#: Confianza del fallback ``prompt_ambiguity`` o sin matches (MAG).
_CONFIDENCE_FALLBACK = 0.30
#: Precision de redondeo de ``regression_risk`` (MAG).
_RISK_PRECISION = 4

#: Tolerancia de regresion de held-out por defecto en ``validate`` (MAG).
DEFAULT_REGRESSION_TOLERANCE = 0.0
#: Mejora minima de score para aceptar un diff (estricta: > 0) (MAG).
_MIN_SCORE_IMPROVEMENT = 0.0

#: Tolerancia de caida de accuracy en la frontera Pareto (MAG).
ACCURACY_TOLERANCE = 0.0
#: Tolerancia de empeoramiento de wall-clock en la frontera Pareto (MAG).
WALL_CLOCK_TOLERANCE = 0.0
#: Ganancia de accuracy que por si sola justifica el trade-off de tiempo (MAG).
MIN_ACCURACY_GAIN = 0.0

# -- Patrones deterministas de clasificacion (nombrados, MAG) ---------------

#: Falla de contrato de tool: schema/validacion/tipos.
_PATTERN_TOOL_SCHEMA = re.compile(
    r"\b(schema|validation|validate|type|types|typed)\b", re.IGNORECASE
)
#: Desborde de contexto/KV cache/VRAM.
_PATTERN_CONTEXT = re.compile(
    r"\b(context|token|tokens|overflow|ctx|kv\s*cache|vram|desborde)\b",
    re.IGNORECASE,
)
#: Skill o recurso ausente.
_PATTERN_SKILL = re.compile(
    r"\b(skill|skills|missing|not\s*found)\b", re.IGNORECASE
)
#: Gap de guardrail: bloqueo/negacion por politica.
_PATTERN_GUARDRAIL = re.compile(
    r"\b(guard\w*|blocked|denied|forbidden)\b", re.IGNORECASE
)
#: Desajuste de middleware/enrutamiento.
_PATTERN_MIDDLEWARE = re.compile(
    r"\b(middleware|mismatch|router|routing|dispatch)\b", re.IGNORECASE
)

# -- Orden de precedencia (el primero que matchea gana) ----------------------

#: Reglas ordenadas de causa: seguridad > contrato > contexto > skill > middleware.
_CAUSE_RULES: tuple[tuple[HarnessCauseCategory, re.Pattern[str]], ...] = (
    ("guardrail_gap", _PATTERN_GUARDRAIL),
    ("tool_schema_error", _PATTERN_TOOL_SCHEMA),
    ("context_overflow", _PATTERN_CONTEXT),
    ("missing_skill", _PATTERN_SKILL),
    ("middleware_mismatch", _PATTERN_MIDDLEWARE),
)

#: Indice categoria -> patron (para extraer evidencia y confianza).
_PATTERN_BY_CAUSE: dict[HarnessCauseCategory, re.Pattern[str]] = {
    "tool_schema_error": _PATTERN_TOOL_SCHEMA,
    "context_overflow": _PATTERN_CONTEXT,
    "missing_skill": _PATTERN_SKILL,
    "guardrail_gap": _PATTERN_GUARDRAIL,
    "middleware_mismatch": _PATTERN_MIDDLEWARE,
}

#: Propuesta de accion local por categoria (el "change" del diff).
_PROPOSAL_BY_CAUSE: dict[HarnessCauseCategory, str] = {
    "prompt_ambiguity": "Precisar el prompt: desambiguar objetivo, formato y criterios de exito.",
    "tool_schema_error": "Ajustar el schema de la tool: tipos/validacion y campos esperados.",
    "missing_skill": "Registrar o recuperar la skill ausente antes de reintentar.",
    "middleware_mismatch": "Alinear el middleware/router: contrato de entrada/salida y dispatch.",
    "context_overflow": "Reducir la ventana de contexto o activar compactacion/truncado.",
    "guardrail_gap": "Cerrar el gap de guardrail: regla faltante en la capa de politicas.",
}

#: Componente objetivo por defecto por categoria (target del diff local).
_TARGET_BY_CAUSE: dict[HarnessCauseCategory, str] = {
    "prompt_ambiguity": "prompt",
    "tool_schema_error": "tool_schema",
    "missing_skill": "skill_registry",
    "middleware_mismatch": "middleware",
    "context_overflow": "context_window",
    "guardrail_gap": "guardrails",
}


def _default_classifier(message: str) -> HarnessCauseCategory:
    """Classifier determinista por patrones (sin LLM).

    WHAT: recorre ``_CAUSE_RULES`` en orden de precedencia y devuelve la primera
    categoria cuyo patron aparece en el mensaje. WHY: el critico debe ser
    reproducible y barato (T1 deterministico); los patrones nombrados evitan
    strings magicos dispersos. WHERE: default de ``HarnessCritic.__init__``.

    Args:
        message: Mensaje de error a clasificar.

    Returns:
        Categoria harness-level; ``"prompt_ambiguity"`` si nada matchea.
    """
    for category, pattern in _CAUSE_RULES:
        if pattern.search(message):
            return category
    return "prompt_ambiguity"


def _evidence_for(message: str, category: HarnessCauseCategory) -> str:
    """Extrae el fragmento del mensaje que evidencia la causa.

    Args:
        message: Mensaje de error original.
        category: Categoria asignada por el classifier.

    Returns:
        El fragmento que matcheo el patron, o el mensaje truncado si no hay.
    """
    pattern = _PATTERN_BY_CAUSE.get(category)
    if pattern is not None:
        match = pattern.search(message)
        if match is not None:
            return match.group(0)
    collapsed = " ".join(message.split())
    return collapsed[:_EVIDENCE_LIMIT]


def _confidence_for(message: str, category: HarnessCauseCategory) -> float:
    """Calcula la confianza determinista de la clasificacion.

    WHAT: ``base + step * (matches - 1)`` acotada a ``_CONFIDENCE_MAX``; cae al
    fallback si no hay patron o no hubo matches. WHY: mas evidencia textual =
    mas confianza, sin LLM ni aleatoriedad. WHERE: ``HarnessCritic.analyze``.

    Args:
        message: Mensaje de error original.
        category: Categoria asignada.

    Returns:
        Confianza en ``(0, 1]``.
    """
    pattern = _PATTERN_BY_CAUSE.get(category)
    if pattern is None:
        return _CONFIDENCE_FALLBACK
    hits = len(pattern.findall(message))
    if hits == 0:
        return _CONFIDENCE_FALLBACK
    return min(_CONFIDENCE_MAX, _CONFIDENCE_BASE + _CONFIDENCE_PER_HIT * (hits - 1))


def _proposal_for(category: HarnessCauseCategory, component: str) -> str:
    """Compone la propuesta de accion local para una causa.

    Args:
        category: Categoria de la causa.
        component: Componente/archivo afectado (opcional).

    Returns:
        Propuesta base, con el componente anexado si se provee.
    """
    base = _PROPOSAL_BY_CAUSE[category]
    return f"{base} (componente: {component})" if component else base


@dataclass(frozen=True)
class HarnessCause:
    """Causa harness-level de un fallo (IMM: frozen dataclass).

    Attributes:
        category: Categoria de la causa harness-level.
        evidence: Fragmento del fallo que evidencia la causa.
        proposal: Accion local propuesta para cerrar la causa.
        confidence: Confianza determinista de la clasificacion en ``(0, 1]``.
    """

    category: HarnessCauseCategory
    evidence: str
    proposal: str
    confidence: float


@dataclass(frozen=True)
class HarnessDiff:
    """Diff local propuesto para una causa (IMM: frozen dataclass).

    Attributes:
        cause: Causa harness-level que origina el diff.
        target: Archivo/componente objetivo del cambio.
        change: Descripcion del diff local a aplicar.
        validated: ``True`` solo tras un re-rollout que supera ``validate``.
        regression_risk: Riesgo estimado de regresion en ``[0, 1]``.
    """

    cause: HarnessCause
    target: str
    change: str
    validated: bool
    regression_risk: float


class HarnessCritic:
    """Atribuye fallos a causas harness-level y propone diffs locales validados.

    Attributes:
        _classifier: Callable inyectable ``mensaje -> categoria``; por defecto
            el clasificador determinista por patrones.
    """

    def __init__(self, *, classifier: Classifier | None = None) -> None:
        """Inicializa el critico con DI (kw-only).

        Args:
            classifier: Clasificador ``str -> HarnessCauseCategory``. Si es
                ``None`` se usa el clasificador determinista por patrones.
        """
        self._classifier: Classifier = (
            classifier if classifier is not None else _default_classifier
        )

    def analyze(self, failure_message: str, *, component: str = "") -> HarnessCause:
        """Clasifica un fallo y construye su ``HarnessCause``.

        Args:
            failure_message: Mensaje de error observado.
            component: Componente/archivo afectado (opcional, se anexa al change).

        Returns:
            La ``HarnessCause`` con categoria, evidencia, propuesta y confianza.
        """
        category = self._classifier(failure_message)
        return HarnessCause(
            category=category,
            evidence=_evidence_for(failure_message, category),
            proposal=_proposal_for(category, component),
            confidence=_confidence_for(failure_message, category),
        )

    def propose(
        self, failures: list[str], *, component: str = ""
    ) -> list[HarnessDiff]:
        """Agrupa fallos por causa y propone UN diff local por causa.

        WHAT: analiza cada mensaje, agrupa por categoria preservando el orden de
        primera aparicion y emite un ``HarnessDiff`` por causa (``change`` = la
        propuesta de la causa; ``target`` = componente o su default por causa).
        WHY: un diff por causa evita propuestas redundantes y hace el cambio
        auditable. WHERE: consumido por ``scripts/harness_critic.py``.

        Los diffs salen con ``validated=False``: requieren un re-rollout.

        Args:
            failures: Lista de mensajes de fallo.
            component: Componente/archivo afectado (opcional).

        Returns:
            Un ``HarnessDiff`` no validado por cada causa distinta observada.
        """
        grouped: dict[HarnessCauseCategory, HarnessCause] = {}
        for message in failures:
            cause = self.analyze(message, component=component)
            grouped.setdefault(cause.category, cause)

        return [
            HarnessDiff(
                cause=cause,
                target=component or _TARGET_BY_CAUSE[cause.category],
                change=cause.proposal,
                validated=False,
                regression_risk=round(1.0 - cause.confidence, _RISK_PRECISION),
            )
            for cause in grouped.values()
        ]

    def validate(
        self,
        diff: HarnessDiff,
        *,
        before_score: float,
        after_score: float,
        held_out_delta: float = 0.0,
        regression_tolerance: float = DEFAULT_REGRESSION_TOLERANCE,
    ) -> HarnessDiff:
        """Valida un diff con re-rollout (Pareto-aware + rollback safety).

        WHAT: acepta (``validated=True``) solo si ``after_score`` supera
        estrictamente a ``before_score`` Y la regresion de held-out no excede la
        tolerancia (``held_out_delta >= -regression_tolerance``). WHY: una mejora
        in-sample que degrada held-out es overfit y exige rollback. WHERE: fase
        EXPERIMENT del loop EVO.

        Args:
            diff: Diff a validar.
            before_score: Score de la linea base (antes del cambio).
            after_score: Score tras aplicar el cambio.
            held_out_delta: Delta de score en el conjunto held-out.
            regression_tolerance: Regresion de held-out tolerada (>= 0).

        Returns:
            Una copia del diff con ``validated`` actualizado.
        """
        improved = (after_score - before_score) > _MIN_SCORE_IMPROVEMENT
        held_out_ok = held_out_delta >= -regression_tolerance
        return replace(diff, validated=improved and held_out_ok)

    @staticmethod
    def pareto_accept(
        *,
        accuracy_before: float,
        accuracy_after: float,
        wall_clock_before: float,
        wall_clock_after: float,
    ) -> tuple[bool, str]:
        """Decide sobre la frontera Pareto accuracy x wall-clock.

        WHAT: acepta si el cambio NO degrada accuracy (con ``ACCURACY_TOLERANCE``)
        Y no empeora wall-clock (con ``WALL_CLOCK_TOLERANCE``), o si gana
        accuracy por encima de ``MIN_ACCURACY_GAIN`` (trade-off justificado).
        WHY: el harness es una variable de optimizacion multi-objetivo; un cambio
        que empeora ambos ejes nunca entra. WHERE: fase ANALYZE del loop EVO.

        Args:
            accuracy_before: Accuracy de la linea base.
            accuracy_after: Accuracy tras el cambio.
            wall_clock_before: Wall-clock de la linea base (segundos).
            wall_clock_after: Wall-clock tras el cambio (segundos).

        Returns:
            Tupla ``(aceptado, motivo)`` con explicacion determinista.
        """
        accuracy_delta = accuracy_after - accuracy_before
        wall_delta = wall_clock_after - wall_clock_before
        no_accuracy_regression = accuracy_delta >= -ACCURACY_TOLERANCE
        time_ok = wall_delta <= WALL_CLOCK_TOLERANCE
        accuracy_gain = accuracy_delta > MIN_ACCURACY_GAIN

        if no_accuracy_regression and time_ok:
            return (
                True,
                (
                    "domina o empata la linea base: accuracy no degrada y "
                    f"wall-clock no empeora (d_acc={accuracy_delta:.4f}, "
                    f"d_wall={wall_delta:.4f})"
                ),
            )
        if accuracy_gain:
            return (
                True,
                (
                    f"ganancia de accuracy {accuracy_delta:.4f} > "
                    f"{MIN_ACCURACY_GAIN} justifica el trade-off de tiempo "
                    f"(d_wall={wall_delta:.4f})"
                ),
            )
        return (
            False,
            (
                "rechazado: fuera de la frontera Pareto "
                f"(d_acc={accuracy_delta:.4f}, d_wall={wall_delta:.4f})"
            ),
        )
