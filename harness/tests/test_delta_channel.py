"""Tests para DeltaChannel — durable execution con checkpoints delta (ADR-0041 H3).

Cubren el ciclo TDD estricto (ADR-0033): apply_step + snapshot, snapshot cada
K pasos, resume flat (snapshot base + replay), idempotencia, reset, stats y
persistencia atomica sin archivos .tmp huerfanos.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from harness.orchestrator.delta_channel import DeltaChannel


def _snapshot_files(state_dir: Path) -> list[Path]:
    """Lista de archivos snapshot_*.json en state_dir."""
    return sorted(state_dir.glob("snapshot_*.json"))


def _delta_files(state_dir: Path) -> list[Path]:
    """Lista de archivos delta_*.json en state_dir."""
    return sorted(state_dir.glob("delta_*.json"))


def _tmp_files(state_dir: Path) -> list[Path]:
    """Lista de archivos .tmp huerfanos en state_dir."""
    return sorted(state_dir.glob("*.tmp"))


class TestDeltaChannelCore:
    """Tests del comportamiento core del canal de deltas."""

    def test_apply_step_and_snapshot_consolidates(self, tmp_path: Path) -> None:
        """
        PRUEBA: apply_step registra deltas y snapshot() consolida el estado.

        Escenario: aplicar dos pasos con claves disjuntas y verificar que
        snapshot() devuelve la fusion completa de ambos deltas.
        """
        channel = DeltaChannel(snapshot_every=3, state_dir=tmp_path)

        channel.apply_step("s1", {"title": "H3"})
        channel.apply_step("s2", {"count": 3})

        assert channel.snapshot() == {"title": "H3", "count": 3}

    def test_snapshot_written_every_k_steps(self, tmp_path: Path) -> None:
        """
        PRUEBA: cada K pasos se escribe un snapshot completo.

        Con K=3: tras 3 pasos debe existir 1 snapshot y pending_deltas=0;
        tras 6 pasos deben existir 2 snapshots y el estado consolidado
        debe contener los 6 deltas.
        """
        channel = DeltaChannel(snapshot_every=3, state_dir=tmp_path)

        channel.apply_step("s1", {"a": 1})
        channel.apply_step("s2", {"b": 2})
        channel.apply_step("s3", {"c": 3})

        assert len(_snapshot_files(tmp_path)) == 1
        assert channel.stats()["pending_deltas"] == 0

        channel.apply_step("s4", {"d": 4})
        channel.apply_step("s5", {"e": 5})
        channel.apply_step("s6", {"f": 6})

        assert len(_snapshot_files(tmp_path)) == 2
        assert channel.snapshot() == {"a": 1, "b": 2, "c": 3, "d": 4, "e": 5, "f": 6}

    def test_resume_reconstructs_state_after_deltas(self, tmp_path: Path) -> None:
        """
        PRUEBA: resume() reconstruye el estado tras un crash.

        Se aplican deltas en una instancia, se simula un crash creando una
        instancia nueva con el mismo state_dir, y resume() debe devolver el
        estado consolidado completo (snapshot + replay de deltas).
        """
        writer = DeltaChannel(snapshot_every=3, state_dir=tmp_path)
        writer.apply_step("s1", {"a": 1})
        writer.apply_step("s2", {"b": 2})
        writer.apply_step("s3", {"c": 3})
        writer.apply_step("s4", {"d": 4})

        reader = DeltaChannel(snapshot_every=3, state_dir=tmp_path)
        assert reader.resume() == {"a": 1, "b": 2, "c": 3, "d": 4}

    def test_resume_replays_deltas_after_snapshot(self, tmp_path: Path) -> None:
        """
        PRUEBA: resume() reconstruye con snapshot base + replay de deltas posteriores.

        Con K=3 y 4 pasos: el snapshot cubre s1..s3 y el delta s4 queda
        pendiente. Al resumir en una instancia nueva, el estado debe incluir
        s4 via replay y stats debe reportar 1 delta pendiente post-snapshot.
        """
        writer = DeltaChannel(snapshot_every=3, state_dir=tmp_path)
        for i in range(1, 5):
            writer.apply_step(f"s{i}", {f"k{i}": i})

        assert len(_snapshot_files(tmp_path)) == 1  # snapshot tras s3

        reader = DeltaChannel(snapshot_every=3, state_dir=tmp_path)
        state = reader.resume()

        assert state == {"k1": 1, "k2": 2, "k3": 3, "k4": 4}
        assert reader.stats()["pending_deltas"] == 1

    def test_idempotent_reapply_same_step_id(self, tmp_path: Path) -> None:
        """
        PRUEBA: re-aplicar el mismo step_id no duplica el delta.

        En la misma instancia, re-aplicar s1 con otro valor es no-op (el
        primer delta gana). En una instancia nueva, resume() + re-apply
        tampoco duplica: steps_applied se mantiene en 1.
        """
        channel = DeltaChannel(snapshot_every=3, state_dir=tmp_path)
        channel.apply_step("s1", {"count": 1})
        channel.apply_step("s1", {"count": 99})  # no-op idempotente

        assert channel.snapshot() == {"count": 1}
        assert channel.stats()["steps_applied"] == 1

        # Instancia nueva: resume no duplica y el re-apply es no-op.
        reader = DeltaChannel(snapshot_every=3, state_dir=tmp_path)
        assert reader.resume() == {"count": 1}
        reader.apply_step("s1", {"count": 77})
        assert reader.snapshot() == {"count": 1}
        assert reader.stats()["steps_applied"] == 1

    def test_reset_clears_checkpoint(self, tmp_path: Path) -> None:
        """
        PRUEBA: reset() limpia el checkpoint actual por completo.

        Tras aplicar pasos y generar snapshot, reset() debe eliminar todos
        los archivos delta_*.json y snapshot_*.json, y resume() debe devolver
        None (no hay estado).
        """
        channel = DeltaChannel(snapshot_every=3, state_dir=tmp_path)
        channel.apply_step("s1", {"a": 1})
        channel.apply_step("s2", {"b": 2})
        channel.apply_step("s3", {"c": 3})

        channel.reset()

        assert channel.resume() is None
        assert _delta_files(tmp_path) == []
        assert _snapshot_files(tmp_path) == []

    def test_stats_reports_metrics(self, tmp_path: Path) -> None:
        """
        PRUEBA: stats() reporta pasos aplicados, deltas pendientes,
        snapshots totales y storage aproximado en bytes.

        Con K=3 y 4 pasos: steps_applied=4, pending_deltas=1 (s4 tras el
        snapshot de s1..s3), total_snapshots=1 y storage_bytes>0.
        """
        channel = DeltaChannel(snapshot_every=3, state_dir=tmp_path)
        channel.apply_step("s1", {"a": 1})
        channel.apply_step("s2", {"b": 2})
        channel.apply_step("s3", {"c": 3})
        channel.apply_step("s4", {"d": 4})

        stats = channel.stats()

        assert stats["steps_applied"] == 4
        assert stats["pending_deltas"] == 1
        assert stats["total_snapshots"] == 1
        assert stats["storage_bytes"] > 0

    def test_no_orphan_tmp_files(self, tmp_path: Path) -> None:
        """
        PRUEBA: la persistencia atomica no deja archivos .tmp huerfanos.

        Tras apply_step, snapshot(), resume() y reset() no debe quedar
        ningun archivo *.tmp en state_dir (los temporales se renombran).
        """
        channel = DeltaChannel(snapshot_every=3, state_dir=tmp_path)
        channel.apply_step("s1", {"a": 1})
        channel.apply_step("s2", {"b": 2})
        channel.apply_step("s3", {"c": 3})
        channel.snapshot()

        reader = DeltaChannel(snapshot_every=3, state_dir=tmp_path)
        reader.resume()
        reader.reset()

        assert _tmp_files(tmp_path) == []

    def test_apply_step_validates_inputs(self, tmp_path: Path) -> None:
        """
        PRUEBA: apply_step valida entradas (step_id y delta).

        step_id vacio o con espacios lanza ValueError; delta que no es dict
        lanza TypeError. Los errores son legibles y accionables.
        """
        channel = DeltaChannel(snapshot_every=3, state_dir=tmp_path)

        with pytest.raises(ValueError, match="step_id"):
            channel.apply_step("", {"a": 1})
        with pytest.raises(ValueError, match="step_id"):
            channel.apply_step("   ", {"a": 1})
        with pytest.raises(ValueError, match="step_id"):
            channel.apply_step("../escape", {"a": 1})
        with pytest.raises(TypeError, match="delta"):
            channel.apply_step("s1", [1, 2])  # type: ignore[arg-type]
