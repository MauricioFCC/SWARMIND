"""Persistencia JSON atómica del estado del modo tutor.

WHAT: guarda las sesiones en ``<MEMORY_ROOT>/data/tutor/sessions.json`` (o
``TUTOR_STATE_PATH``). Sin código ni secretos: solo tema, nivel, intentos,
fechas y notas.
WHY: el tutor necesita memoria entre invocaciones para no reiniciar la escalera
en cada turno; el archivo debe ser portable y pequeño (O(1) por turno).
WHERE: ``scripts/tutor.py`` y la skill ``socratic-tutor``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from harness.tutor.policy import TutorSession


def default_state_path() -> Path:
    """Ruta del estado del tutor (env > MEMORY_ROOT > Documents portable).

    Returns:
        ``TUTOR_STATE_PATH`` si está definido; si no,
        ``<MEMORY_ROOT>/data/tutor/sessions.json``; si no,
        ``Path.home()/Documents/Memory_Proyects/data/tutor/sessions.json``.
    """
    override = os.environ.get("TUTOR_STATE_PATH")
    if override:
        return Path(override)
    root = os.environ.get("MEMORY_ROOT")
    base = Path(root) if root else Path.home() / "Documents" / "Memory_Proyects"
    return base / "data" / "tutor" / "sessions.json"


class TutorStore:
    """Almacén JSON de sesiones de tutoría (escritura atómica).

    Args:
        path: Ruta del JSON; ``None`` usa :func:`default_state_path`.
    """

    def __init__(self, path: Path | None = None) -> None:
        """Fija la ruta del almacén."""
        self.path = Path(path) if path is not None else default_state_path()

    def _read(self) -> dict[str, dict[str, object]]:
        """Lee el mapa de sesiones (vacío si falta o está corrupto)."""
        if not self.path.is_file():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        sesiones = payload.get("sessions") if isinstance(payload, dict) else None
        return sesiones if isinstance(sesiones, dict) else {}

    def _write(self, sesiones: dict[str, dict[str, object]]) -> None:
        """Escribe el JSON de forma atómica (tmp + replace)."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporal = self.path.with_suffix(".tmp")
        temporal.write_text(
            json.dumps(
                {"version": 1, "sessions": sesiones},
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        temporal.replace(self.path)

    def save(self, session: TutorSession) -> Path:
        """Guarda (o reemplaza) la sesión por tema; devuelve la ruta."""
        sesiones = self._read()
        sesiones[session.topic] = session.to_dict()
        self._write(sesiones)
        return self.path

    def load(self, topic: str) -> TutorSession | None:
        """Carga una sesión por tema (``None`` si no existe)."""
        crudo = self._read().get(topic)
        return TutorSession.from_dict(crudo) if isinstance(crudo, dict) else None

    def list(self) -> list[TutorSession]:
        """Lista todas las sesiones guardadas."""
        return [TutorSession.from_dict(dato) for dato in self._read().values()]

    def active(self) -> TutorSession | None:
        """Sesión más reciente por ``started_at`` (``None`` si no hay)."""
        sesiones = self.list()
        if not sesiones:
            return None
        return max(sesiones, key=lambda sesion: sesion.started_at)

    def clear(self, topic: str) -> bool:
        """Elimina una sesión; True si existía."""
        sesiones = self._read()
        if topic not in sesiones:
            return False
        sesiones.pop(topic)
        self._write(sesiones)
        return True
