"""Contrato del SketchStore con ratings Elo (ciclo 11.17 - AlphaProof Nexus).

WHAT: verifica ``harness/complex_problems/sketch_store.py`` contra la frontera:

- **AlphaProof Nexus** (arXiv 2605.22763): puente rating-agents/Elo sobre
  fitness binario — cada sketch (programa formal candidato) tiene un Elo que
  se actualiza con resultados verificados (gana/pierde, sin gradiente);
  poblacion compartida entre problemas y P-UCB posterior sobre las familias.

WHY: sin Elo, la busqueda trata igual un sketch que resolvio 8 problemas que
uno fallido; el ranking bayesiano simple conserva evidencia historica
determinista (sin azar) y seleccion elitista reproducible.

WHERE: ``harness/complex_problems/sketch_store.py``.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from harness.complex_problems.sketch_store import (
    DEFAULT_INITIAL_RATING,
    DEFAULT_K_FACTOR,
    Sketch,
    SketchStore,
)


class TestSketch:
    """Contrato del sketch (frozen, rating inicial por defecto)."""

    def test_rating_inicial_por_defecto(self) -> None:
        assert Sketch(sketch_id="s1", program="prg").rating == DEFAULT_INITIAL_RATING == 1500.0

    def test_es_inmutable(self) -> None:
        sketch = Sketch(sketch_id="s1", program="prg")

        with pytest.raises(FrozenInstanceError):
            sketch.rating = 1600.0  # type: ignore[misc]


class TestSketchStore:
    """Contrato de la poblacion compartida de sketches."""

    def test_add_y_longitud(self) -> None:
        store = SketchStore()

        assert store.add(Sketch("s1", "p1")) is True
        assert store.add(Sketch("s2", "p2")) is True
        assert len(store) == 2

    def test_add_duplicado_se_rechaza(self) -> None:
        store = SketchStore()
        store.add(Sketch("s1", "original"))

        assert store.add(Sketch("s1", "reemplazo")) is False
        assert store.get("s1").program == "original", "el duplicado no pisa"

    def test_id_vacio_se_rechaza(self) -> None:
        store = SketchStore()

        with pytest.raises(ValueError, match="vacio"):
            store.add(Sketch("", "p"))

    def test_get_inexistente_es_keyerror(self) -> None:
        store = SketchStore()

        with pytest.raises(KeyError):
            store.get("fantasma")

    def test_k_factor_invalido_se_rechaza(self) -> None:
        with pytest.raises(ValueError, match="k_factor"):
            SketchStore(k_factor=0.0)

    def test_self_play_se_rechaza(self) -> None:
        store = SketchStore()
        store.add(Sketch("s1", "p1"))

        with pytest.raises(ValueError, match="mismo sketch"):
            store.record_result("s1", "s1")

    def test_resultado_conserva_el_total_de_ratings(self) -> None:
        """Elo suma-cero: lo que gana el ganador lo pierde el perdedor."""
        store = SketchStore()
        store.add(Sketch("s1", "p1"))
        store.add(Sketch("s2", "p2"))

        store.record_result("s1", "s2")

        total = store.get("s1").rating + store.get("s2").rating
        assert total == pytest.approx(2 * DEFAULT_INITIAL_RATING)

    def test_ganador_con_400_de_desventaja_gana_lo_minimo(self) -> None:
        """E = 1/(1+10^(400/400)) = 1/11 -> el debil que gana suma K*(1-E)."""
        store = SketchStore()
        store.add(Sketch("fuerte", "p1", rating=1900.0))
        store.add(Sketch("debil", "p2", rating=1500.0))

        store.record_result("debil", "fuerte")

        expected_loser = 1.0 / 11.0
        gain = DEFAULT_K_FACTOR * (1 - expected_loser)
        assert store.get("debil").rating == pytest.approx(1500.0 + gain)
        assert store.get("fuerte").rating == pytest.approx(1900.0 - gain)

    def test_empate_de_rating_actualiza_simetrico(self) -> None:
        store = SketchStore()
        store.add(Sketch("a", "p1"))
        store.add(Sketch("b", "p2"))

        store.record_result("a", "b")

        assert store.get("a").rating == pytest.approx(1500.0 + DEFAULT_K_FACTOR / 2)
        assert store.get("b").rating == pytest.approx(1500.0 - DEFAULT_K_FACTOR / 2)

    def test_top_ordena_por_rating_con_empate_por_id(self) -> None:
        store = SketchStore()
        store.add(Sketch("b", "p", rating=1600.0))
        store.add(Sketch("a", "p", rating=1600.0))
        store.add(Sketch("c", "p", rating=1500.0))

        assert [s.sketch_id for s in store.top(3)] == ["a", "b", "c"]

    def test_top_prioriza_rating_sobre_alfabeto(self) -> None:
        """El orden alfabetico nunca pisa al rating (regresion: not(-rating))."""
        store = SketchStore()
        store.add(Sketch("a", "p", rating=1500.0))
        store.add(Sketch("b", "p", rating=1700.0))
        store.add(Sketch("c", "p", rating=1600.0))

        assert [s.sketch_id for s in store.top(3)] == ["b", "c", "a"]

    def test_top_k_mayor_que_la_poblacion(self) -> None:
        store = SketchStore()
        store.add(Sketch("a", "p"))

        assert len(store.top(10)) == 1

    def test_actualizacion_determinista(self) -> None:
        def play() -> SketchStore:
            store = SketchStore()
            store.add(Sketch("a", "p1"))
            store.add(Sketch("b", "p2"))
            store.record_result("a", "b")
            store.record_result("a", "b")
            store.record_result("b", "a")
            return store

        assert play().get("a").rating == play().get("a").rating
