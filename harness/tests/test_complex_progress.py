"""Contrato del ProgressLedger monotono (ciclo 11.17 - AlphaProof Nexus).

WHAT: verifica ``harness/complex_problems/progress.py`` contra la frontera:

- **AlphaProof Nexus** (arXiv 2605.22763): los problemas resueltos (9 de 353
  de Erdos) son UNA DIRECCION: una vez verificado, el resultado nunca se
  revierte (monotonía del progreso) y la evidencia se preserva; registro
  persistente append-only para reanudar la busqueda entre sesiones.

WHY: sin monotonía, un bug de reintentos puede "olvidar" un problema ya
resuelto y re-gastar presupuesto (episodios duplicados); sin persistencia,
cada sesión arranca de cero.

WHERE: ``harness/complex_problems/progress.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.complex_problems.progress import ProgressLedger


class TestProgressLedger:
    """Contrato del registro monotono en memoria."""

    def test_marcar_y_consultar(self) -> None:
        ledger = ProgressLedger()

        assert ledger.mark_solved("erdos-1", "prueba formal") is True
        assert ledger.is_solved("erdos-1") is True
        assert ledger.is_solved("erdos-2") is False
        assert len(ledger) == 1

    def test_marcar_es_idempotente_y_preserva_evidencia(self) -> None:
        ledger = ProgressLedger()
        ledger.mark_solved("p", "evidencia-original")

        assert ledger.mark_solved("p", "segunda evidencia") is False
        assert ledger.evidence("p") == "evidencia-original"

    def test_rollback_se_rechaza_monotonia(self) -> None:
        ledger = ProgressLedger()
        ledger.mark_solved("p", "e")

        with pytest.raises(ValueError, match="monoton"):
            ledger.rollback("p")

    def test_id_vacio_se_rechaza(self) -> None:
        ledger = ProgressLedger()

        with pytest.raises(ValueError, match="vacio"):
            ledger.mark_solved("", "e")

    def test_evidencia_vacia_se_rechaza(self) -> None:
        ledger = ProgressLedger()

        with pytest.raises(ValueError, match="evidencia"):
            ledger.mark_solved("p", "")

    def test_evidencia_inexistente_es_keyerror(self) -> None:
        ledger = ProgressLedger()

        with pytest.raises(KeyError):
            ledger.evidence("fantasma")

    def test_solved_ids_ordenado_determinista(self) -> None:
        ledger = ProgressLedger()
        for problem_id in ("c", "a", "b"):
            ledger.mark_solved(problem_id, "e")

        assert ledger.solved_ids == ("a", "b", "c")


class TestPersistencia:
    """Journal JSONL append-only reanudable entre sesiones."""

    def test_recarga_desde_disco(self, tmp_path: Path) -> None:
        path = tmp_path / "progress.jsonl"
        first = ProgressLedger(path)
        first.mark_solved("p1", "evidencia-1")
        first.mark_solved("p2", "evidencia-2")

        reloaded = ProgressLedger(path)

        assert reloaded.solved_ids == ("p1", "p2")
        assert reloaded.evidence("p2") == "evidencia-2"

    def test_ruta_anidada_inexistente_se_crea(self, tmp_path: Path) -> None:
        path = tmp_path / "deep" / "nested" / "progress.jsonl"
        ledger = ProgressLedger(path)
        ledger.mark_solved("p", "e")

        assert path.exists()
        assert ProgressLedger(path).is_solved("p")

    def test_journal_corrupto_explicita_linea(self, tmp_path: Path) -> None:
        path = tmp_path / "progress.jsonl"
        path.write_text("no-es-json\n", encoding="utf-8")

        with pytest.raises(ValueError, match=r"linea 1"):
            ProgressLedger(path)

    def test_registro_es_append_only(self, tmp_path: Path) -> None:
        path = tmp_path / "progress.jsonl"
        ledger = ProgressLedger(path)
        ledger.mark_solved("p1", "e1")
        first_line = path.read_text(encoding="utf-8")

        ledger.mark_solved("p2", "e2")

        assert path.read_text(encoding="utf-8").startswith(first_line)
        assert len(path.read_text(encoding="utf-8").splitlines()) == 2
