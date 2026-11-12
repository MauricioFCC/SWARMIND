"""Modo tutor puro: estados y transiciones (sin I/O ni LLM).

WHAT: máquina de estados determinista para tutoría socrática. El nivel de
ayuda sube de a uno (pregunta → concepto → pista local → parcial) y **nunca**
llega a la solución sin una petición explícita (``reveal_solution(confirm=True)``).
WHY: la evidencia (Harvard 2025, Wharton/PNAS 2025, Anthropic 2026) muestra que
la delegación total mejora la práctica pero empeora la transferencia; preguntar
y exigir un intento produce comprensión. El modo es opt-in.
WHERE: consumido por ``harness/tutor/store.py``, ``scripts/tutor.py`` y la
skill ``socratic-tutor``.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from enum import Enum, IntEnum

#: Días de revisión espaciada tras un intento correcto.
REVIEW_DAYS: tuple[int, ...] = (1, 7, 16, 35)


class TutorMode(str, Enum):
    """Modo de la sesión (``off`` no se persiste como sesión)."""

    OFF = "off"
    GUIDE = "guide"
    EXAM = "exam"


class HintLevel(IntEnum):
    """Escalera de ayuda; ``SOLUTION`` solo con confirmación explícita."""

    QUESTION = 0
    CONCEPT = 1
    LOCAL = 2
    PARTIAL = 3
    SOLUTION = 4


@dataclass(frozen=True)
class TutorSession:
    """Estado inmutable de una sesión de tutoría.

    Args:
        topic: Tema que el usuario quiere aprender.
        mode: ``guide`` (preguntas) o ``exam`` (práctica con preguntas).
        level: Nivel de ayuda actual.
        attempts: Intentos registrados.
        correct: Intentos correctos.
        hints: Pistas entregadas.
        solution_revealed: True solo si el usuario pidió la solución.
        started_at: ISO-8601 UTC de inicio.
        last_attempt_at: ISO-8601 del último intento.
        next_review: Fechas ISO de revisión espaciada.
        notes: Notas breves del alumno.
    """

    topic: str
    mode: TutorMode = TutorMode.GUIDE
    level: HintLevel = HintLevel.QUESTION
    attempts: int = 0
    correct: int = 0
    hints: int = 0
    solution_revealed: bool = False
    started_at: str = ""
    last_attempt_at: str = ""
    next_review: tuple[str, ...] = ()
    notes: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        """Normaliza enums/tuplas y valida el tema."""
        object.__setattr__(self, "mode", TutorMode(self.mode))
        object.__setattr__(self, "level", HintLevel(self.level))
        object.__setattr__(self, "next_review", tuple(self.next_review))
        object.__setattr__(self, "notes", tuple(self.notes))
        if not self.topic.strip():
            raise ValueError(
                "WHAT: sesión sin tema. WHY: no se puede guiar sin objetivo. "
                "WHERE: TutorSession.topic"
            )

    def to_dict(self) -> dict[str, object]:
        """Serializa la sesión a JSON."""
        return {
            "topic": self.topic,
            "mode": self.mode.value,
            "level": int(self.level),
            "attempts": self.attempts,
            "correct": self.correct,
            "hints": self.hints,
            "solution_revealed": self.solution_revealed,
            "started_at": self.started_at,
            "last_attempt_at": self.last_attempt_at,
            "next_review": list(self.next_review),
            "notes": list(self.notes),
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> TutorSession:
        """Reconstruye una sesión desde su JSON."""
        return cls(
            topic=str(data.get("topic", "")),
            mode=TutorMode(str(data.get("mode", "guide"))),
            level=HintLevel(int(data.get("level", 0))),
            attempts=int(data.get("attempts", 0)),
            correct=int(data.get("correct", 0)),
            hints=int(data.get("hints", 0)),
            solution_revealed=bool(data.get("solution_revealed")),
            started_at=str(data.get("started_at", "")),
            last_attempt_at=str(data.get("last_attempt_at", "")),
            next_review=tuple(data.get("next_review") or ()),
            notes=tuple(data.get("notes") or ()),
        )


class TutorPolicy:
    """Transiciones puras del modo tutor (sin I/O)."""

    @staticmethod
    def start(
        topic: str,
        mode: TutorMode | str = TutorMode.GUIDE,
        *,
        now: datetime | None = None,
    ) -> TutorSession:
        """Crea una sesión nueva en el nivel ``QUESTION``."""
        momento = now or datetime.now(UTC)
        return TutorSession(
            topic=topic.strip(),
            mode=TutorMode(mode),
            level=HintLevel.QUESTION,
            started_at=momento.isoformat(timespec="seconds"),
        )

    @staticmethod
    def record_attempt(
        session: TutorSession,
        *,
        correct: bool,
        note: str = "",
        now: datetime | None = None,
    ) -> TutorSession:
        """Registra un intento; un acierto programa la revisión espaciada."""
        momento = now or datetime.now(UTC)
        notas = session.notes + ((note.strip(),) if note.strip() else ())
        revision = (
            TutorPolicy.review_schedule(session, now=momento)
            if correct
            else session.next_review
        )
        return replace(
            session,
            attempts=session.attempts + 1,
            correct=session.correct + (1 if correct else 0),
            last_attempt_at=momento.isoformat(timespec="seconds"),
            next_review=revision,
            notes=notas,
        )

    @staticmethod
    def next_hint(session: TutorSession) -> TutorSession:
        """Sube como máximo un nivel, con tope ``PARTIAL``."""
        if session.solution_revealed:
            return session
        nuevo = min(int(session.level) + 1, int(HintLevel.PARTIAL))
        return replace(session, level=HintLevel(nuevo), hints=session.hints + 1)

    @staticmethod
    def reveal_solution(session: TutorSession, *, confirm: bool) -> TutorSession:
        """Revela la solución SOLO con confirmación explícita.

        Raises:
            ValueError: Si ``confirm`` es False (petición no explícita).
        """
        if not confirm:
            raise ValueError(
                "WHAT: falta confirmación explícita para revelar la solución. "
                "WHY: revelarla antes de intentar anula el aprendizaje (H1). "
                "WHERE: TutorPolicy.reveal_solution(confirm=False)"
            )
        return replace(
            session, level=HintLevel.SOLUTION, solution_revealed=True
        )

    @staticmethod
    def repeat(session: TutorSession) -> TutorSession:
        """Reinicia la escalera a ``QUESTION`` (repaso sin bajar intentos)."""
        return replace(session, level=HintLevel.QUESTION)

    @staticmethod
    def review_schedule(
        session: TutorSession, *, now: datetime | None = None
    ) -> tuple[str, ...]:
        """Fechas ISO de revisión (1/7/16/35 días) desde el último intento."""
        base = session.last_attempt_at or session.started_at
        if base:
            try:
                dia = datetime.fromisoformat(base).date()
            except ValueError:
                dia = (now or datetime.now(UTC)).date()
        else:
            dia = (now or datetime.now(UTC)).date()
        return tuple((dia + timedelta(days=d)).isoformat() for d in REVIEW_DAYS)

    @staticmethod
    def directive(session: TutorSession) -> str:
        """Bloque de prompt que impone el contrato socrático."""
        return (
            f"### MODO TUTOR ({session.mode.value}) — tema: {session.topic}\n"
            f"Nivel de ayuda: {int(session.level)}/4 ({session.level.name})\n"
            "Reglas:\n"
            "- No des la solución completa: haz UNA pregunta guía por turno.\n"
            "- Exige un intento del usuario antes de subir de pista.\n"
            "- Escalera: P0 pregunta → P1 concepto → P2 pista local → P3 parcial.\n"
            "- La solución solo se muestra si el usuario ejecuta "
            "`tutor solve --confirm`.\n"
            "- Al terminar, pide una autoexplicación y programa el repaso."
        )
