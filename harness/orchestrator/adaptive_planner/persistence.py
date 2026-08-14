"""AdaptivePlanner persistence — mixin con ``_save`` y ``_load``.

Extraccion mecanica de los metodos de persistencia de la clase
``AdaptivePlanner`` del modulo original
``harness/orchestrator/adaptive_planner.py`` (sin cambios de logica
ni firmas).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from .models import PlanStrategy

logger = logging.getLogger(__name__)


class _PersistenceMixin:
    """Mixin con la persistencia de estadisticas a disco."""

    def _save(self) -> None:
        """Persiste estadísticas a disco."""
        if not self._storage_path:
            return

        Path(self._storage_path).parent.mkdir(parents=True, exist_ok=True)

        data = {
            "strategy_stats": {
                k: v.to_dict() for k, v in self._strategy_stats.items()
            },
            "best_strategies": {
                k: (v[0].value, v[1])
                for k, v in self._best_strategies.items()
            },
            "feedback_count": len(self._feedback_history),
            "updated_at": datetime.now(UTC).isoformat(),
        }

        with open(self._storage_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _load(self) -> None:
        """Carga estadísticas desde disco."""
        if not self._storage_path:
            return

        if not Path(self._storage_path).exists():
            return

        try:
            with open(self._storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            for s_name, s_data in data.get("strategy_stats", {}).items():
                if s_name in self._strategy_stats:
                    stats = self._strategy_stats[s_name]
                    stats.total_uses = s_data.get("total_uses", 0)
                    stats.total_successes = s_data.get("total_successes", 0)
                    stats.total_failures = s_data.get("total_failures", 0)
                    stats.avg_duration_ms = s_data.get("avg_duration_ms", 0.0)
                    stats.avg_success_rate = s_data.get("avg_success_rate", 0.0)
                    stats.last_used = s_data.get("last_used", "")

            for key, (s_value, confidence) in data.get("best_strategies", {}).items():
                try:
                    strategy = PlanStrategy(s_value)
                    self._best_strategies[key] = (strategy, confidence)
                except ValueError:
                    pass

        except (json.JSONDecodeError, OSError) as e:
            logger.warning("AdaptivePlanner: error loading stats: %s", e)
