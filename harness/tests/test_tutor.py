"""Tests del modo tutor socrático (spec ``socratic-tutor.md``).

Contratos (AC1-AC8): estado de sesión, escalera de pistas que nunca revela la
solución sin petición explícita, directiva para el prompt, persistencia atómica
y CLI que conserva el estado entre invocaciones.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from harness.tutor import (
    HintLevel,
    TutorMode,
    TutorPolicy,
    TutorSession,
    TutorStore,
    default_state_path,
)

ROOT = Path(__file__).resolve().parents[2]


def _session(topic: str = "closures en Rust") -> TutorSession:
    """Sesión de tutoría base para los tests."""
    return TutorPolicy.start(topic)


# ---------------------------------------------------------------------------
# AC1/AC2 — estado e intentos
# ---------------------------------------------------------------------------


class TestEstado:
    def test_start_crea_sesion_en_pregunta(self) -> None:
        """AC1: arranca en QUESTION, sin intentos ni pistas."""
        session = _session()

        assert session.mode is TutorMode.GUIDE
        assert session.level is HintLevel.QUESTION
        assert session.attempts == 0
        assert session.hints == 0
        assert session.solution_revealed is False

    def test_attempt_incrementa_y_no_baja_nivel(self) -> None:
        """AC2: un intento cuenta y conserva el nivel."""
        session = TutorPolicy.next_hint(_session())
        after = TutorPolicy.record_attempt(session, correct=False, note="casi")

        assert after.attempts == 1
        assert after.level == session.level
        assert "casi" in after.notes

    def test_attempt_correcto_programa_revision(self) -> None:
        """Un acierto fija 4 fechas de revisión crecientes."""
        after = TutorPolicy.record_attempt(_session(), correct=True)

        assert after.correct == 1
        assert len(after.next_review) == 4
        assert list(after.next_review) == sorted(after.next_review)


# ---------------------------------------------------------------------------
# AC3/AC4 — escalera de pistas y solución
# ---------------------------------------------------------------------------


class TestEscalera:
    def test_hint_sube_exactamente_un_nivel(self) -> None:
        """AC3: cada pista avanza un nivel."""
        session = _session()
        uno = TutorPolicy.next_hint(session)
        dos = TutorPolicy.next_hint(uno)

        assert uno.level is HintLevel.CONCEPT
        assert dos.level is HintLevel.LOCAL
        assert dos.hints == 2

    @given(st.integers(min_value=0, max_value=50))
    def test_hint_nunca_llega_a_solucion(self, veces: int) -> None:
        """AC3/PBT: por muchas pistas, no se revela la solución."""
        session = _session()
        for _ in range(veces):
            session = TutorPolicy.next_hint(session)
        assert session.level is not HintLevel.SOLUTION
        assert session.solution_revealed is False

    def test_solve_sin_confirmacion_falla(self) -> None:
        """AC4: revelar la solución exige petición explícita."""
        with pytest.raises(ValueError, match="confirm"):
            TutorPolicy.reveal_solution(_session(), confirm=False)

    def test_solve_con_confirmacion_marca_revelada(self) -> None:
        """AC4: con confirmación, el estado lo registra."""
        after = TutorPolicy.reveal_solution(_session(), confirm=True)

        assert after.solution_revealed is True
        assert after.level is HintLevel.SOLUTION


# ---------------------------------------------------------------------------
# AC5/AC6 — directiva y revisión
# ---------------------------------------------------------------------------


class TestDirectiva:
    def test_incluye_prohibicion_y_nivel(self) -> None:
        """AC5: el prompt prohíbe revelar y muestra el nivel."""
        texto = TutorPolicy.directive(_session("ownership"))

        assert "ownership" in texto
        assert "no des la solución" in texto.lower()
        assert "intento" in texto.lower()
        assert "QUESTION" in texto or "0/4" in texto

    def test_review_schedule_cuatro_fechas(self) -> None:
        """AC6: 1/7/16/35 días, en orden."""
        fechas = TutorPolicy.review_schedule(_session())

        assert len(fechas) == 4
        assert list(fechas) == sorted(fechas)


# ---------------------------------------------------------------------------
# AC7 — persistencia
# ---------------------------------------------------------------------------


class TestStore:
    def test_roundtrip_atomico(self, tmp_path: Path) -> None:
        """AC7: guardar y cargar conserva la sesión."""
        store = TutorStore(tmp_path / "sessions.json")
        session = TutorPolicy.record_attempt(_session(), correct=True)
        store.save(session)

        leida = store.load(session.topic)

        assert leida is not None
        assert leida.topic == session.topic
        assert leida.attempts == 1
        assert json.loads((tmp_path / "sessions.json").read_text())["version"] == 1

    def test_list_y_active(self, tmp_path: Path) -> None:
        """AC7: lista todas y activa la más reciente."""
        store = TutorStore(tmp_path / "sessions.json")
        store.save(TutorPolicy.start("tema A"))
        store.save(TutorPolicy.start("tema B"))

        assert {s.topic for s in store.list()} == {"tema A", "tema B"}
        assert store.active() is not None

    def test_off_elimina_sesion(self, tmp_path: Path) -> None:
        """``off`` borra la sesión del almacén."""
        store = TutorStore(tmp_path / "sessions.json")
        store.save(_session("tema"))
        store.clear("tema")

        assert store.load("tema") is None

    def test_default_state_path_respeta_env(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """La ruta por defecto usa ``TUTOR_STATE_PATH`` (sin rutas personales)."""
        destino = tmp_path / "tutor.json"
        monkeypatch.setenv("TUTOR_STATE_PATH", str(destino))
        assert default_state_path() == destino


# ---------------------------------------------------------------------------
# AC8 — CLI
# ---------------------------------------------------------------------------


class TestCLI:
    def test_cli_persiste_entre_invocaciones(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
    ) -> None:
        """AC8: start → hint → status conserva el nivel en disco."""
        monkeypatch.setenv("TUTOR_STATE_PATH", str(tmp_path / "tutor.json"))
        sys.path.insert(0, str(ROOT / "scripts"))
        import tutor as cli

        assert cli.main(["start", "ownership", "--mode", "guide"]) == 0
        assert cli.main(["hint"]) == 0
        capsys.readouterr()
        assert cli.main(["status", "--json"]) == 0
        salida = json.loads(capsys.readouterr().out)

        assert salida["topic"] == "ownership"
        assert salida["level"] == 1
