"""SketchStore con ratings Elo (ciclo 11.17 — AlphaProof Nexus).

WHAT: poblacion compartida de sketches (programas formales candidatos) con
ratings Elo — el puente "rating agents sobre fitness binario" de Nexus
(arXiv 2605.22763): cada verificacion es una partida ganada/perdida y el
Elo bayesiano simple conserva evidencia historica determinista (sin rng,
suma-cero) para guiar la elitizacion de la busqueda.

WHY: sin rating, un sketch que resueltio 8 problemas vale igual que uno
fallido; con Elo suma-cero el ranking es reproducible y seleccionable por
top-k sin re-evaluar toda la poblacion.

WHERE: ``harness/complex_problems/sketch_store.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

#: Rating inicial estandar Elo.
DEFAULT_INITIAL_RATING = 1500.0
#: K-factor por defecto (actualizaciones moderadas, estable ante ruido).
DEFAULT_K_FACTOR = 16.0


@dataclass(frozen=True)
class Sketch:
    """Sketch formal candidato con rating Elo (frozen)."""

    sketch_id: str
    program: str
    rating: float = DEFAULT_INITIAL_RATING


class SketchStore:
    """Poblacion de sketches con resultados binarios verificados."""

    def __init__(self, *, k_factor: float = DEFAULT_K_FACTOR) -> None:
        if k_factor <= 0:
            raise ValueError(
                f"WHAT: k_factor {k_factor} no positivo. WHY: sin K no hay "
                "actualizacion de rating. WHERE: SketchStore."
            )
        self._k = k_factor
        self._sketches: dict[str, Sketch] = {}

    def __len__(self) -> int:
        return len(self._sketches)

    def __contains__(self, sketch_id: object) -> bool:
        return sketch_id in self._sketches

    def add(self, sketch: Sketch) -> bool:
        """Agrega un sketch; los IDs duplicados se rechazan sin pisar.

        Raises:
            ValueError: Si el sketch_id es la cadena vacia.
        """
        if not sketch.sketch_id:
            raise ValueError(
                "WHAT: sketch_id vacio. WHY: el ID es la clave del store. "
                "WHERE: SketchStore.add."
            )
        if sketch.sketch_id in self._sketches:
            return False
        self._sketches[sketch.sketch_id] = sketch
        return True

    def get(self, sketch_id: str) -> Sketch:
        """Devuelve el sketch; KeyError si el ID no existe."""
        return self._sketches[sketch_id]

    def record_result(self, winner_id: str, loser_id: str) -> None:
        """Actualiza Elo con una partida binaria (ganador verifica, perdedor no).

        Expected del ganador: E = 1/(1+10^((R_perdedor-R_ganador)/400));
        delta = K*(1-E) suma-cero entre ambos ratings.

        Raises:
            ValueError: Si es self-play (mismo sketch).
            KeyError: Si algun ID no existe.
        """
        if winner_id == loser_id:
            raise ValueError(
                f"WHAT: self-play '{winner_id}' (mismo sketch). WHY: una "
                "partida requiere dos candidatos. WHERE: record_result."
            )
        winner = self.get(winner_id)
        loser = self.get(loser_id)
        expected_winner = 1.0 / (
            1.0 + 10.0 ** ((loser.rating - winner.rating) / 400.0)
        )
        delta = self._k * (1.0 - expected_winner)
        self._sketches[winner_id] = replace(winner, rating=winner.rating + delta)
        self._sketches[loser_id] = replace(loser, rating=loser.rating - delta)

    def top(self, k: int) -> tuple[Sketch, ...]:
        """Top-k por rating (empates: orden alfabetico de ID, determinista)."""
        ordered = sorted(self._sketches.values(), key=lambda s: (-s.rating, s.sketch_id))
        return tuple(ordered[: max(k, 0)])
