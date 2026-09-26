"""batch_vote.py — Votacion k-en-1 con parametro n de la API (ADR-0073).

WHAT: Ejecuta k votos en UNA llamada (parametro n=k): el input se cobra
una vez y solo el output escala con k.
WHY: Frontera (arXiv 2604.13717) — k llamadas cobran input k veces;
con n=k el mismo ensembling (+11.9pp de calidad con criteria) cuesta
kx menos input. En el gate >=70 del orquestador esto acota el 3x a solo
el componente de output.
WHERE: ``parallel_executor`` (votacion) y cualquier fan-out de veredictos;
fallback automatico a k llamadas si el proveedor no soporta n>1.

Uso:
    result = batch_vote(prompt, complete_fn, k=3, input_tokens=800, output_tokens=120)
    if result.quorum_met:
        usar(result.majority)
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass

logger = logging.getLogger("harness.orchestrator.batch_vote")

#: Votos minimos para mayoria (quorum por defecto del gate).
DEFAULT_QUORUM_RATIO = 0.5


@dataclass(frozen=True)
class BatchVoteResult:
    """Resultado de una votacion k-en-1.

    Attributes:
        votes: Respuestas individuales en orden.
        majority: Respuesta mayoriataria (None si empate o sin quorum).
        quorum_met: True si la mayoria supera el quorum.
        input_calls: Llamadas de input realizadas (1 si n soportado, k si fallback).
        effective_input_tokens: Tokens de input cobrados (1x con n, kx en fallback).
        effective_output_tokens: Tokens de output cobrados (kx siempre).
        n_supported: True si el proveedor entrego k respuestas en 1 llamada.
    """

    votes: tuple[str, ...]
    majority: str | None
    quorum_met: bool
    input_calls: int
    effective_input_tokens: int
    effective_output_tokens: int
    n_supported: bool


def estimate_savings(k: int) -> float:
    """Ahorro de input esperado al usar n=k vs k llamadas.

    Args:
        k: Numero de votos (>= 1).

    Returns:
        Fraccion de input ahorrada (0.0 con k=1; (k-1)/k en general).

    Raises:
        ValueError: Si k < 1 (WHAT+WHY+WHERE).
    """
    if k < 1:
        raise ValueError(
            f"WHAT: k invalido: {k}. "
            "WHY: se necesita al menos 1 voto. "
            "WHERE: estimate_savings"
        )
    return (k - 1) / k


def batch_vote(
    prompt: str,
    complete_fn,
    k: int,
    input_tokens: int,
    output_tokens: int,
    quorum_ratio: float = DEFAULT_QUORUM_RATIO,
) -> BatchVoteResult:
    """Ejecuta k votos con cobro de input 1x (parametro n) o fallback kx.

    Args:
        prompt: Pregunta a votar (no vacia).
        complete_fn: (prompt, n) -> list[str]; si con n=k retorna k
            respuestas se cobra input 1x; si retorna 1 sola, se hace
            fallback a k llamadas secuenciales.
        k: Numero de votos.
        input_tokens: Tokens de input por llamada (para contabilidad).
        output_tokens: Tokens de output por respuesta.
        quorum_ratio: Fraccion minima de votos para el quorum.

    Returns:
        BatchVoteResult con votos, mayoria, quorum y contabilidad.

    Raises:
        ValueError: Si prompt vacio o k < 1 (WHAT+WHY+WHERE).
    """
    if not prompt.strip():
        raise ValueError(
            "WHAT: prompt vacio. "
            "WHY: sin pregunta no hay votacion. "
            "WHERE: batch_vote"
        )
    if k < 1:
        raise ValueError(
            f"WHAT: k invalido: {k}. "
            "WHY: se necesita al menos 1 voto. "
            "WHERE: batch_vote"
        )
    raw = complete_fn(prompt, k)
    answers = [str(a) for a in raw]
    n_supported = len(answers) >= k
    if n_supported:
        votes = tuple(answers[:k])
        input_calls = 1
        effective_in = input_tokens
    else:
        votes_list = list(answers)
        while len(votes_list) < k:
            nxt = complete_fn(prompt, 1)
            if not nxt:
                break
            votes_list.append(str(nxt[0]))
        votes = tuple(votes_list[:k])
        input_calls = len(votes)
        effective_in = input_tokens * input_calls
    effective_out = output_tokens * len(votes)
    majority, quorum_met = _majority(votes, quorum_ratio)
    if not n_supported:
        logger.info(
            "batch_vote fallback: proveedor sin n>1; input cobrado %dx", input_calls
        )
    return BatchVoteResult(
        votes=votes,
        majority=majority,
        quorum_met=quorum_met,
        input_calls=input_calls,
        effective_input_tokens=effective_in,
        effective_output_tokens=effective_out,
        n_supported=n_supported,
    )


def _majority(
    votes: tuple[str, ...], quorum_ratio: float
) -> tuple[str | None, bool]:
    """Calcula mayoria y quorum sobre los votos (empate -> None).

    Args:
        votes: Votos individuales.
        quorum_ratio: Fraccion minima para considerar quorum.

    Returns:
        Tupla (mayoria o None, quorum_met).
    """
    if not votes:
        return None, False
    counter = Counter(votes)
    top, count = counter.most_common(1)[0]
    tie = count * 2 <= len(votes) and len(counter) > 1
    if tie:
        return None, False
    quorum_met = count / len(votes) > quorum_ratio
    return (top if quorum_met else None), quorum_met


@dataclass(frozen=True)
class StakeVoteResult:
    """Resultado de votacion ponderada por stakes (wagering, ADR-0085).

    Attributes:
        winner: Respuesta con mayor stake acumulado (None si empate exacto).
        total_stake: Suma de stakes (auditable como ventaja esperada).
        weights: Mapa respuesta -> stake acumulado.
    """

    winner: str | None
    total_stake: float
    weights: dict[str, float]


def stake_weighted_vote(
    votes: tuple[str, ...], stakes: tuple[float, ...]
) -> StakeVoteResult:
    """Votacion independiente ponderada por stakes de confianza (sin debate).

    WHAT: Suma stakes por respuesta; gana el mayor acumulado. Sin rondas
    de debate (KalshiBench: el consenso deliberativo degrada a 76% por
    sycophancy; la agregacion independiente no).
    WHY: Frontera (wagering arXiv:2607.04389): el stake en equilibrio
    equivale a la ventaja esperada del agente; ponderar por stake supera
    a la mayoria plana cuando pocos calibrados discrepan de muchos dudosos.
    WHERE: `batch_vote` cuando cada voto trae confianza; fallback a
    mayoria plana si no hay stakes.

    Args:
        votes: Respuestas (una por agente).
        stakes: Confianza 0..1 por voto (misma longitud).

    Returns:
        StakeVoteResult con ganador, stake total y pesos.

    Raises:
        ValueError: Si longitudes difieren o stakes fuera de [0, 1].
    """
    if len(votes) != len(stakes):
        raise ValueError(
            f"WHAT: {len(votes)} votos vs {len(stakes)} stakes. "
            "WHY: cada voto necesita su stake de confianza. "
            "WHERE: stake_weighted_vote"
        )
    for stake in stakes:
        if not (0.0 <= stake <= 1.0):
            raise ValueError(
                f"WHAT: stake invalido: {stake}. "
                "WHY: el stake es confianza, debe estar en [0, 1]. "
                "WHERE: stake_weighted_vote"
            )
    weights: dict[str, float] = {}
    for vote, stake in zip(votes, stakes):
        weights[vote] = weights.get(vote, 0.0) + stake
    if not weights:
        return StakeVoteResult(winner=None, total_stake=0.0, weights={})
    ranked = sorted(weights.items(), key=lambda kv: (-kv[1], kv[0]))
    tie = len(ranked) > 1 and ranked[0][1] == ranked[1][1]
    winner = None if tie else ranked[0][0]
    return StakeVoteResult(
        winner=winner, total_stake=sum(stakes), weights=dict(weights)
    )
