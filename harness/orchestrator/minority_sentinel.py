"""minority_sentinel.py — Sentinel de minoria / mayoria revertible (ACL 2026).

WHAT: Meta-clasificador que revisa la respuesta de mayoria de un debate o
votacion y, cuando procede, la revierte hacia la minoria mas fuerte.
WHY: Frontera (ACL 2026): el debate vanilla pierde frente a majority-vote;
el meta-clasificador que revierte la mayoria ~1/4 de las veces (umbral
``override``) mejora el resultado global. El sentinel aporta esa capacidad
revertible sin debate adicional: por defecto mantiene la mayoria y solo la
revierte si el acuerdo es bajo y existe una minoria con apoyo suficiente
(heuristica determinista), o si el meta-clasificador lo pide explicitamente.
WHERE: se inyecta via DI en ``DebateOrchestrator`` (parametro ``sentinel``):
tras agregar la mayoria, ``_majority_winner`` la pasa por
``MinoritySentinel.review``. Backward-compat total: sin sentinel inyectado
el orquestador se comporta como antes.

Uso:
    sentinel = MinoritySentinel()  # heuristico determinista (sin LLM)
    verdict = sentinel.review("respuesta_mayoritaria", votos)
    if verdict.reverted:
        usar(verdict.final_answer)
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass

from harness.orchestrator.batch_vote import _majority

logger = logging.getLogger("harness.orchestrator.minority_sentinel")

#: Apoyo minimo de la minoria para revertir (~1/4 de las veces, ACL 2026).
DEFAULT_OVERRIDE_THRESHOLD: float = 0.25
#: Acuerdo minimo de la mayoria; por debajo pasa a ser revertible.
DEFAULT_MIN_AGREEMENT: float = 0.66


@dataclass(frozen=True)
class SentinelVerdict:
    """Veredicto del sentinel sobre una agregacion por mayoria.

    Attributes:
        majority_answer: Respuesta mayoritaria evaluada.
        final_answer: Respuesta final (la mayoria, o la minoria si revierte).
        reverted: True si el sentinel revirtio la mayoria a la minoria.
        reason: Explicacion legible (WHAT+WHY) de la decision.
        minority_answer: Minoria mas fuerte, o None si no hay minoria.
        confidence: Confianza en ``final_answer`` (apoyo del grupo elegido).
    """

    majority_answer: str
    final_answer: str
    reverted: bool
    reason: str
    minority_answer: str | None
    confidence: float


class MinoritySentinel:
    """Meta-clasificador que revierte la mayoria hacia la minoria mas fuerte.

    Determinista por defecto (sin LLM): la decision heuristica solo depende de
    ``override_threshold``, ``min_agreement`` y los votos. La DI de
    ``override_fn`` permite enchufar un meta-clasificador externo sin acoplar
    el sentinel a un proveedor concreto.

    Attributes:
        _override_threshold: Apoyo minimo de la minoria para revertir.
        _min_agreement: Acuerdo minimo; por debajo la mayoria es revertible.
        _override_fn: Meta-clasificador inyectable; None = heuristico puro.
    """

    def __init__(
        self,
        *,
        override_threshold: float = DEFAULT_OVERRIDE_THRESHOLD,
        min_agreement: float = DEFAULT_MIN_AGREEMENT,
        override_fn: Callable[[str, list[str]], bool] | None = None,
    ) -> None:
        """Configura los umbrales del sentinel y su meta-clasificador opcional.

        Args:
            override_threshold: Apoyo minimo de la minoria para revertir;
                debe estar en [0, 1].
            min_agreement: Acuerdo minimo de la mayoria por debajo del cual
                es revertible; debe estar en [0, 1].
            override_fn: Meta-clasificador inyectable
                ``(majority_answer, all_answers) -> bool``; None usa la
                heuristica determinista.

        Raises:
            ValueError: Si algun umbral esta fuera de [0, 1] o ``override_fn``
                no es invocable (WHAT+WHY+WHERE).
        """
        if not 0.0 <= override_threshold <= 1.0:
            raise ValueError(
                f"WHAT: override_threshold invalido: {override_threshold}. "
                "WHY: es una fraccion de apoyo y debe estar en [0, 1]. "
                "WHERE: MinoritySentinel.__init__"
            )
        if not 0.0 <= min_agreement <= 1.0:
            raise ValueError(
                f"WHAT: min_agreement invalido: {min_agreement}. "
                "WHY: es una fraccion de acuerdo y debe estar en [0, 1]. "
                "WHERE: MinoritySentinel.__init__"
            )
        if override_fn is not None and not callable(override_fn):
            raise ValueError(
                "WHAT: override_fn no es invocable. "
                "WHY: el meta-clasificador debe ser Callable[[str, list], bool]. "
                "WHERE: MinoritySentinel.__init__"
            )
        self._override_threshold = override_threshold
        self._min_agreement = min_agreement
        self._override_fn = override_fn

    @staticmethod
    def agreement(answers: list[str]) -> float:
        """Fraccion de apoyo del grupo mayoritario (mayoria exacta).

        Reusa la definicion de mayoria de ``batch_vote._majority`` (mismo
        concepto de ``Counter``); si existe empate, usa el grupo mas grande
        como mayoria para que la fraccion siempre este definida.

        Args:
            answers: Respuestas individuales. Vacio -> 0.0.

        Returns:
            Fraccion en [0, 1] del grupo mayoritario.
        """
        if not answers:
            return 0.0
        majority, _ = _majority(tuple(answers), 0.0)
        counts = Counter(answers)
        if majority is None:
            majority = counts.most_common(1)[0][0]
        return counts[majority] / len(answers)

    @staticmethod
    def _strongest_minority(majority_answer: str, answers: list[str]) -> str | None:
        """Minoria con mas apoyo; empate -> la mas larga (determinista).

        Args:
            majority_answer: Respuesta mayoritaria a excluir.
            answers: Respuestas individuales.

        Returns:
            La minoria mas fuerte, o None si no existe (todas mayoritarias).
        """
        counts = Counter(answers)
        minority = {ans: c for ans, c in counts.items() if ans != majority_answer}
        if not minority:
            return None
        top = max(minority.values())
        candidates = [ans for ans, c in minority.items() if c == top]
        return max(candidates, key=lambda ans: (len(ans), ans))

    def review(
        self,
        majority_answer: str,
        all_answers: list[str],
        *,
        override_signal: bool | None = None,
    ) -> SentinelVerdict:
        """Revisa la mayoria y decide si revertirla hacia la minoria.

        Precedencia de la decision: ``override_signal`` explicito (tri-estado)
        > ``override_fn`` inyectado > heuristica determinista. La heuristica
        revierte solo si el acuerdo de la mayoria es menor que ``min_agreement``
        Y la minoria mas fuerte alcanza al menos ``override_threshold``. Nunca
        revierte si no hay minoria (todas las respuestas coinciden).

        Args:
            majority_answer: Respuesta mayoritaria que se evalua.
            all_answers: Respuestas individuales (incluye la mayoria).
            override_signal: Senal explicita del meta-clasificador. True
                fuerza la reversion; False la prohibe; None delega en el
                ``override_fn`` inyectado o en la heuristica.

        Returns:
            SentinelVerdict con respuesta final, bandera de reversion,
            minoria elegida, razon legible y confianza.

        Raises:
            ValueError: Si ``all_answers`` esta vacio, ``majority_answer``
                esta vacio o no pertenece a ``all_answers`` (WHAT+WHY+WHERE).
        """
        if not all_answers:
            raise ValueError(
                "WHAT: all_answers vacio. "
                "WHY: sin votos no hay mayoria que revisar. "
                "WHERE: MinoritySentinel.review"
            )
        if not majority_answer.strip():
            raise ValueError(
                "WHAT: majority_answer vacio. "
                "WHY: se necesita la respuesta mayoritaria a evaluar. "
                "WHERE: MinoritySentinel.review"
            )
        if majority_answer not in set(all_answers):
            raise ValueError(
                f"WHAT: majority_answer {majority_answer!r} no esta en all_answers. "
                "WHY: la mayoria evaluada debe pertenecer a los votos. "
                "WHERE: MinoritySentinel.review"
            )

        majority_agreement = self.agreement(all_answers)
        minority = self._strongest_minority(majority_answer, all_answers)

        if minority is None:
            return SentinelVerdict(
                majority_answer=majority_answer,
                final_answer=majority_answer,
                reverted=False,
                reason="sin minoria: todas las respuestas coinciden; mayoria intacta",
                minority_answer=None,
                confidence=majority_agreement,
            )

        minority_support = Counter(all_answers)[minority] / len(all_answers)
        reverted = self._decide(
            majority_answer,
            all_answers,
            majority_agreement,
            minority_support,
            override_signal,
        )
        reason = self._reason(reverted, majority_agreement, minority_support, override_signal)

        if reverted:
            logger.info(
                "minority_sentinel revierte mayoria: agreement=%.2f minoria=%.2f",
                majority_agreement,
                minority_support,
            )
            return SentinelVerdict(
                majority_answer=majority_answer,
                final_answer=minority,
                reverted=True,
                reason=reason,
                minority_answer=minority,
                confidence=minority_support,
            )

        return SentinelVerdict(
            majority_answer=majority_answer,
            final_answer=majority_answer,
            reverted=False,
            reason=reason,
            minority_answer=minority,
            confidence=majority_agreement,
        )

    def _decide(
        self,
        majority_answer: str,
        all_answers: list[str],
        majority_agreement: float,
        minority_support: float,
        override_signal: bool | None,
    ) -> bool:
        """Decide si revertir la mayoria (senal > override_fn > heuristica).

        Args:
            majority_answer: Respuesta mayoritaria.
            all_answers: Respuestas individuales.
            majority_agreement: Acuerdo del grupo mayoritario.
            minority_support: Apoyo de la minoria mas fuerte.
            override_signal: Senal explicita del meta-clasificador (tri-estado).

        Returns:
            True si debe revertirse la mayoria hacia la minoria.
        """
        if override_signal is not None:
            return override_signal
        if self._override_fn is not None:
            return bool(self._override_fn(majority_answer, list(all_answers)))
        return (
            majority_agreement < self._min_agreement
            and minority_support >= self._override_threshold
        )

    def _reason(
        self,
        reverted: bool,
        majority_agreement: float,
        minority_support: float,
        override_signal: bool | None,
    ) -> str:
        """Compone la razon legible (WHAT+WHY) del veredicto.

        Args:
            reverted: Resultado de la decision.
            majority_agreement: Acuerdo del grupo mayoritario.
            minority_support: Apoyo de la minoria mas fuerte.
            override_signal: Senal explicita usada (o None).

        Returns:
            Cadena legible con la fuente de decision y los umbrales aplicados.
        """
        if override_signal is not None:
            source = "override_signal"
        elif self._override_fn is not None:
            source = "override_fn"
        else:
            source = "heuristica"
        decision = "revierte" if reverted else "mantiene"
        return (
            f"{source} {decision} la mayoria: "
            f"acuerdo={majority_agreement:.2f} (min_agreement={self._min_agreement:.2f}), "
            f"minoria={minority_support:.2f} "
            f"(override_threshold={self._override_threshold:.2f})"
        )
