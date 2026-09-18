"""adversarial_table.py — Mesa adversarial ejecutable (MESA, ADR-0087).

WHAT: Triaje facil/duro -> R0 silencioso (3 voces independientes +
confianza) -> max 2 rondas con rotacion -> juez-antes-que-voto
(supermayoria 66%) -> fallback voto con stakes -> acta con mayoria +
minoria preservada + metricas (ronda de acuerdo, disenso).
WHY: Sintesis frontera (Du/ReConcile/ChatEval/MAD/FREE-MAD/Habermas/SPRT/
AgentAuditor/consenso/MADC): 3-4 voces diversas +8pp, juez +11pp en
contraintuitivo, consenso 66% primario, cap 2 rondas (mas rondas =
martingala), disenso = senal (no ruido), acuerdo rapido sin evidencia =
confabulacion.
WHERE: Decisiones irreversibles o de alto costo/incertidumbre; lo facil
va a checklist (fanout_gate), nunca a mesa.

Uso:
    table = AdversarialTable(voices=("a","b","c"), voice_fn=..., judge_fn=...)
    minutes = table.run("elegir base de datos")
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from harness.orchestrator.batch_vote import stake_weighted_vote

logger = logging.getLogger("harness.orchestrator.adversarial_table")

#: Voces minimas de la mesa (2 diversas rinden como 16 homogeneas; minimo 3).
MIN_VOICES = 3
#: Cap duro de rondas de ataque (mas = deriva a fallo colectivo).
MAX_ROUNDS = 2
#: Supermayoria para veredicto por consenso (Kaesberg: MMLU +2.3%).
SUPERMAJORITY = 0.66


def triage(task: str, difficulty: str) -> str:
    """Triaje facil/duro de la tarea (encuadre MESA).

    Args:
        task: Descripcion de la tarea.
        difficulty: "easy" (checklist) o "hard" (mesa).

    Returns:
        "checklist" o "table".

    Raises:
        ValueError: Si difficulty no es easy|hard (WHAT+WHY+WHERE).
    """
    if difficulty not in ("easy", "hard"):
        raise ValueError(
            f"WHAT: difficulty invalida: {difficulty!r}. "
            "WHY: el triaje solo distingue facil (checklist) vs dura (mesa). "
            "WHERE: triage"
        )
    _ = task
    return "checklist" if difficulty == "easy" else "table"


@dataclass(frozen=True)
class TableMinutes:
    """Acta de la mesa (mayoria + minoria, Habermas).

    Attributes:
        verdict: Veredicto final.
        majority: Postura mayoritaria.
        dissent: Posturas minoritarias preservadas (tupla, puede estar vacia).
        rounds: Rondas de ataque ejecutadas (0 = acuerdo en R0).
        agreement_round: Ronda donde se logro el acuerdo (0 = R0).
    """

    verdict: str
    majority: str
    dissent: tuple[str, ...] = ()
    rounds: int = 0
    agreement_round: int = 0


class AdversarialTable:
    """Mesa adversarial de 3+ voces con juez y cap de rondas.

    Args:
        voices: Nombres de las voces (>= 3, idealmente diversas).
        voice_fn: (prompt, voice) -> (respuesta, confianza 0..1).
        judge_fn: (respuestas) -> (veredicto, score 0..1).
    """

    def __init__(
        self,
        voices: tuple[str, ...],
        voice_fn: Callable[[str, str], tuple[str, float]],
        judge_fn: Callable[[list[str]], tuple[str, float]],
    ) -> None:
        """Inicializa la mesa validando el minimo de voces.

        Args:
            voices: >= 3 voces.
            voice_fn: Generador por voz.
            judge_fn: Juez de consenso.

        Raises:
            ValueError: Si hay menos de 3 voces.
        """
        if len(voices) < MIN_VOICES:
            raise ValueError(
                f"WHAT: solo {len(voices)} voces (minimo {MIN_VOICES}). "
                "WHY: 2 diversas rinden como 16 homogeneas, pero el minimo "
                "operativo con juez es 3. "
                "WHERE: AdversarialTable.__init__"
            )
        self._voices = tuple(voices)
        self._voice_fn = voice_fn
        self._judge_fn = judge_fn

    def run(self, task: str) -> TableMinutes:
        """Ejecuta la mesa: R0 -> [R1 -> R2] -> veredicto + acta.

        R0 silencioso (sin ver ajenas); si hay acuerdo (>=66% misma
        respuesta) el juez confirma y no hay rondas; si no, hasta 2 rondas
        con rotacion de orden; al final juez, y si no hay supermayoria,
        fallback a voto con stakes (confianzas como stakes).

        Args:
            task: Pregunta a decidir.

        Returns:
            TableMinutes con veredicto, mayoria, disenso y metricas.
        """
        order = list(self._voices)
        r0 = [self._voice_fn(task, voice) for voice in order]
        answers = [a for a, _ in r0]
        verdict, score = self._judge_fn(answers)
        if self._has_supermajority(answers, verdict):
            logger.info("adversarial_table: acuerdo en R0 (sin rondas)")
            return self._minutes(verdict, answers, rounds=0, agreement=0)
        rounds = 0
        current = answers
        confidences = [c for _, c in r0]
        for rnd in range(1, MAX_ROUNDS + 1):
            order = order[1:] + order[:1]  # rotacion (MADC: el orden manda)
            current = [
                self._voice_fn(f"{task} [ronda {rnd}, considera: {current}]", voice)[0]
                for voice in order
            ]
            confidences = [0.5] * len(current)
            verdict, _round_score = self._judge_fn(current)
            rounds = rnd
            if self._has_supermajority(current, verdict):
                logger.info("adversarial_table: acuerdo en R%d", rnd)
                return self._minutes(verdict, current, rounds=rounds, agreement=rnd,
                                     prior=r0)
        logger.info("adversarial_table: cap R2 sin supermayoria; fallback stakes")
        staked = stake_weighted_vote(
            tuple(current),
            tuple(min(max(c, 0.0), 1.0) for c in confidences),
        )
        final = staked.winner or verdict
        return self._minutes(final, current, rounds=rounds, agreement=-1, prior=r0)

    @staticmethod
    def _has_supermajority(answers: list[str], verdict: str) -> bool:
        """True si el veredicto alcanza supermayoria 66%.

        Args:
            answers: Respuestas de la ronda.
            verdict: Veredicto del juez.

        Returns:
            True si >= 66% coincide con el veredicto.
        """
        if not answers:
            return False
        return sum(1 for a in answers if a == verdict) / len(answers) >= SUPERMAJORITY

    @staticmethod
    def _minutes(
        verdict: str, answers: list[str], rounds: int, agreement: int,
        prior: list[tuple[str, float]] | None = None,
    ) -> TableMinutes:
        """Construye el acta con mayoria + minoria preservada.

        Args:
            verdict: Veredicto final.
            answers: Respuestas de la ultima ronda.
            rounds: Rondas ejecutadas.
            agreement: Ronda de acuerdo (-1 = fallback).
            prior: Respuestas R0 (para disenso historico).

        Returns:
            TableMinutes con disenso (todas las posturas != veredicto).
        """
        pool = list(answers)
        if prior:
            pool += [a for a, _ in prior]
        dissent = tuple(sorted({a for a in pool if a != verdict}))
        majority = verdict
        return TableMinutes(
            verdict=verdict, majority=majority, dissent=dissent,
            rounds=rounds, agreement_round=agreement,
        )
