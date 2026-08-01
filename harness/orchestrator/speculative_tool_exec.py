"""
SpeculativeToolExecutor — Ejecución especulativa de tools (PASTE-lite, ADR-0034).

Middleware que predice y pre-ejecuta tools side-effect-free mientras el LLM
aún está generando, eliminando la latencia de round-trip de la ruta crítica.
Basado en PASTE (SJTU/MSR, arXiv 2603.18897): -43.5% latencia avg, -55.4% p99.

Seguridad:
  - Solo tools registradas explícitamente como elegibles se especulan.
  - Tools con side-effects (write/delete/update/execute/send/deploy) NUNCA.
  - dry_run=True por defecto: solo mide, no ejecuta.
  - Lossless: los resultados especulativos se aíslan hasta confirmación del
    LLM; si la predicción es errónea, se descartan sin consecuencias.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

# Tools con side-effects: prohibidas de especulación por policy (como PASTE).
FORBIDDEN_TOOLS: frozenset[str] = frozenset({
    "write", "write_file", "create", "delete", "remove", "update",
    "execute", "run", "send", "deploy", "publish", "commit", "push",
    "transfer", "pay", "buy", "sell",
})


class PatternLearner:
    """
    Aprende patrones (tool_actual -> tool_siguiente) de trayectorias reales.

    Uso:
        learner = PatternLearner()
        learner.observe("read_file", "search_code")
        preds = learner.predict("read_file", k=3)  # [(tool, prob), ...]
    """

    def __init__(self) -> None:
        self._transitions: dict[str, dict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )
        self._totals: dict[str, int] = defaultdict(int)

    def observe(self, tool_name: str, next_tool: str | None) -> None:
        """Registra una transición observada.

        Args:
            tool_name: tool actual.
            next_tool: tool siguiente (None si es la última).
        """
        if next_tool is None:
            return
        self._transitions[tool_name][next_tool] += 1
        self._totals[tool_name] += 1

    def predict(self, current_tool: str, k: int = 3) -> list[tuple[str, float]]:
        """Predice las k tools siguientes más probables.

        Args:
            current_tool: tool actual.
            k: cantidad máxima de predicciones.

        Returns:
            Lista de (tool, probabilidad empírica) ordenada desc, vacía si no
            hay historial.
        """
        if current_tool not in self._transitions:
            return []
        total = self._totals[current_tool]
        ranked = sorted(
            self._transitions[current_tool].items(),
            key=lambda kv: (-kv[1], kv[0]),
        )
        return [(tool, count / total) for tool, count in ranked[:k]]


@dataclass
class _SpecStats:
    """Estadísticas de ejecución especulativa."""
    speculative_runs: int = 0
    predictions: int = 0
    hits: int = 0
    misses: int = 0


class SpeculativeToolExecutor:
    """
    Ejecutor especulativo de tools con aislamiento de resultados.

    Uso:
        ex = SpeculativeToolExecutor(eligible={"search"}, dry_run=False)
        ex.run_speculative("read_file", executor)   # pre-ejecuta "search"
        result = ex.confirm("search")                # disponible solo aquí
    """

    def __init__(
        self,
        *,
        learner: PatternLearner | None = None,
        eligible: set[str] | None = None,
        dry_run: bool = True,
        max_speculative: int = 2,
    ) -> None:
        """
        Inicializa el ejecutor especulativo.

        Args:
            learner: PatternLearner con el historial (se crea uno si None).
            eligible: conjunto de tools permitidas para especulación. Default
                None => NADA elegible (opt-in por seguridad).
            dry_run: True => solo predice y mide, NO ejecuta (default).
            max_speculative: máximo de tools a especular por turno.
        """
        self._learner = learner if learner is not None else PatternLearner()
        self._eligible: frozenset[str] = frozenset(
            t for t in (eligible or set()) if t not in FORBIDDEN_TOOLS
        )
        self._dry_run = bool(dry_run)
        self._max_speculative = int(max_speculative)
        self._pending: dict[str, object] = {}
        self._stats = _SpecStats()

    # ------------------------------------------------------------------
    # Políticas
    # ------------------------------------------------------------------

    def is_eligible(self, tool: str) -> bool:
        """True si la tool puede ejecutarse especulativamente.

        Args:
            tool: nombre de la tool.

        Returns:
            False si está prohibida por side-effects o no registrada.
        """
        if tool in FORBIDDEN_TOOLS:
            return False
        return tool in self._eligible

    # ------------------------------------------------------------------
    # Predicción
    # ------------------------------------------------------------------

    def predict(self, current_tool: str, k: int | None = None) -> list[tuple[str, float]]:
        """Predice las próximas tools elegibles.

        Args:
            current_tool: tool actual.
            k: top-k (default: max_speculative).

        Returns:
            Lista de (tool, prob) solo con tools elegibles, ordenada desc.
        """
        limit = k if k is not None else self._max_speculative
        preds = self._learner.predict(current_tool, k=max(limit * 2, 1))
        eligible = [(t, p) for t, p in preds if self.is_eligible(t)][:limit]
        return eligible

    # ------------------------------------------------------------------
    # Ejecución especulativa
    # ------------------------------------------------------------------

    def run_speculative(self, current_tool: str, executor) -> dict[str, object]:
        """Pre-ejecuta las tools predichas y aísla sus resultados.

        Args:
            current_tool: tool actual del agente.
            executor: callable(tool, params=None) -> resultado.

        Returns:
            Dict {tool: resultado} de las ejecuciones especulativas exitosas.
            Vacío si dry_run, sin predicciones, o tools no elegibles.
        """
        preds = self.predict(current_tool)
        self._stats.speculative_runs += 1
        self._stats.predictions += len(preds)
        results: dict[str, object] = {}
        for tool, _prob in preds:
            if self._dry_run:
                continue
            try:
                outcome = executor(tool)
            except Exception:  # noqa: BLE001 - la especulacion nunca rompe el flujo principal
                self._stats.misses += 1
                continue
            self._pending[tool] = outcome
            results[tool] = outcome
        return results

    def confirm(self, tool: str) -> object | None:
        """Recupera el resultado especulativo confirmado por el LLM.

        Lossless: si el LLM elige una tool que NO se especuló, retorna None y
        la ejecución normal procede (sin impacto en exactitud).

        Args:
            tool: tool que el LLM decidió llamar.

        Returns:
            El resultado cacheado, o None si no se especuló (el llamador debe
            ejecutar la tool normalmente).
        """
        result = self._pending.pop(tool, None)
        if result is not None:
            self._stats.hits += 1
        return result

    # ------------------------------------------------------------------
    # Estadísticas
    # ------------------------------------------------------------------

    def stats(self) -> dict:
        """Métricas de la especulación para observabilidad.

        Returns:
            Dict con speculative_runs, predictions, hits, misses y hit_rate.
        """
        attempts = self._stats.hits + self._stats.misses
        return {
            "speculative_runs": self._stats.speculative_runs,
            "predictions": self._stats.predictions,
            "hits": self._stats.hits,
            "misses": self._stats.misses,
            "hit_rate": round(self._stats.hits / attempts, 4) if attempts else 0.0,
        }
