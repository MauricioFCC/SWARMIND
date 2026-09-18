"""Tests para adversarial_table — mesa adversarial ejecutable (ADR-0086/0087).

Metodologia MESA: triaje facil/duro (facil->checklist, sin debate) ->
R0 silencioso (3 voces independientes + confianza) -> max 2 rondas con
rotacion -> juez-antes-que-voto (supermayoria 66%) -> fallback voto con
stakes -> acta con mayoria+minoria (disenso preservado) + metricas.
"""

import pytest

from harness.orchestrator.adversarial_table import (
    AdversarialTable,
    TableMinutes,
    triage,
)


def _voices(answers):
    """Fabrica voice_fn con respuestas programadas por llamada."""

    def _fn(prompt: str, voice: str) -> tuple[str, float]:
        idx = len(_voices.calls)
        _voices.calls.append((voice, prompt))
        return answers[min(idx, len(answers) - 1)]

    _voices.calls = []
    return _fn


def _judge_fn(scores):
    """Fabrica judge_fn con scores programados."""

    def _fn(answers: list[str]) -> tuple[str, float]:
        idx = len(_judge_fn.calls)
        _judge_fn.calls.append(list(answers))
        return scores[min(idx, len(scores) - 1)]

    _judge_fn.calls = []
    return _fn


def test_triage_easy_skips_table() -> None:
    """Tarea facil/rutinaria -> checklist, sin mesa."""
    assert triage("extrae los emails del texto", difficulty="easy") == "checklist"
    assert triage("disena la arquitectura", difficulty="hard") == "table"


def test_triage_invalid_difficulty_raises() -> None:
    """Dificultad desconocida falla accionable."""
    with pytest.raises(ValueError, match="WHAT"):
        triage("x", difficulty="media")


def test_table_runs_r0_then_judge() -> None:
    """R0 independiente + juez con supermayoria -> veredicto sin R2."""
    table = AdversarialTable(
        voices=("atacante", "steelman", "critico"),
        voice_fn=_voices([("a", 0.9), ("a", 0.85), ("a", 0.8)]),
        judge_fn=_judge_fn([("a", 0.95)]),
    )
    minutes = table.run("elegir base de datos")
    assert isinstance(minutes, TableMinutes)
    assert minutes.verdict == "a"
    assert minutes.rounds == 0  # acuerdo en R0: sin rondas
    assert minutes.agreement_round == 0


def test_table_second_round_on_disagreement() -> None:
    """Sin acuerdo en R0: R1 con rotacion, luego veredicto."""
    table = AdversarialTable(
        voices=("atacante", "steelman", "critico"),
        voice_fn=_voices([
            ("a", 0.6), ("b", 0.6), ("c", 0.5),   # R0: disenso
            ("b", 0.8), ("b", 0.85), ("b", 0.7),  # R1: convergen
        ]),
        judge_fn=_judge_fn([("b", 0.5), ("b", 0.9)]),
    )
    minutes = table.run("elegir cache")
    assert minutes.verdict == "b"
    assert minutes.rounds == 1
    assert len(minutes.dissent) >= 1  # disenso de R0 preservado


def test_table_caps_at_two_rounds() -> None:
    """Sin acuerdo tras R2: cap duro, fallback a voto con stakes."""
    cycle = [("x", 0.5), ("y", 0.5), ("z", 0.5)]

    def _cycling(prompt: str, voice: str) -> tuple[str, float]:
        _cycling.n += 1
        return cycle[_cycling.n % 3]

    _cycling.n = -1
    table = AdversarialTable(
        voices=("a1", "a2", "a3"),
        voice_fn=_cycling,
        judge_fn=_judge_fn([("x", 0.4)] * 3),
    )
    minutes = table.run("tema imposible")
    assert minutes.rounds == 2
    assert minutes.verdict in ("x", "y", "z")


def test_minutes_preserve_minority() -> None:
    """El acta incluye mayoria Y minoria (Habermas: disenso no se borra)."""
    table = AdversarialTable(
        voices=("a1", "a2", "a3"),
        voice_fn=_voices([("si", 0.9), ("si", 0.8), ("no", 0.7)]),
        judge_fn=_judge_fn([("si", 0.9)]),
    )
    minutes = table.run("migrar o no")
    assert minutes.majority == "si"
    assert "no" in minutes.dissent


def test_table_requires_three_voices() -> None:
    """Menos de 3 voces falla (2 diversas rinden como 16 homogeneas, minimo 3)."""
    with pytest.raises(ValueError, match="WHAT"):
        AdversarialTable(
            voices=("a", "b"),
            voice_fn=_voices([("x", 0.5)]),
            judge_fn=_judge_fn([("x", 0.5)]),
        )
