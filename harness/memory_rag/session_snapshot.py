"""session_snapshot.py — Snapshot de sesion: estado completo a disco, vista 5KB (ADR-0082).

WHAT: Persiste el estado completo de la sesion en JSON y retorna una vista
esencial acotada (tarea + ultimos turnos resumidos + hechos); restore()
devuelve el estado byte-exacto.
WHY: Frontera 2026 — Scroll (arXiv 2608.21690: el estado vive FUERA del
contexto; el prompt lleva solo la working view) + ACM (manage_context:
resume + offload raw a disco; context-mode 315KB->5KB). Sin snapshot, la
compaction decide que sobrevive sin saber el futuro.
WHERE: Antes de cada compaction mayor; `restore` on-demand (query_memory).

Uso:
    out = SessionSnapshotter().save(state_dict)
    # out.view (<=5KB) va al contexto; out.handle recupera todo
    full = SessionSnapshotter().restore(out.handle)
"""

from __future__ import annotations

import json
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from harness.common import short_hash

logger = logging.getLogger("harness.memory_rag.session_snapshot")

#: Techo de la vista esencial (5KB, context-mode).
ESSENTIAL_MAX_CHARS = 5 * 1024
#: Turnos resumidos incluidos en la vista.
VIEW_TURNS = 5
#: Hechos incluidos en la vista.
VIEW_FACTS = 10
_HASH_LEN = 12


def _handle_for(payload: str) -> str:
    """Hash corto determinista del payload serializado.

    Args:
        payload: JSON serializado del estado.

    Returns:
        Handle hexadecimal (12 chars).
    """
    return short_hash(payload, _HASH_LEN)


@dataclass(frozen=True)
class SnapshotOutput:
    """Resultado de guardar un snapshot.

    Attributes:
        handle: Identificador para restore().
        view: Vista esencial (<= ESSENTIAL_MAX_CHARS) para el contexto.
    """

    handle: str
    view: str


class SessionSnapshotter:
    """Snapshots de sesion con vista esencial acotada.

    Args:
        cache_dir: Directorio de snapshots (None -> tmp del sistema).
    """

    def __init__(self, cache_dir: str | Path | None = None) -> None:
        """Inicializa el snapshotter garantizando el directorio.

        Args:
            cache_dir: Ruta del directorio; None usa tmp del sistema.
        """
        if cache_dir is None:
            cache_dir = tempfile.mkdtemp(prefix="swarmind_snapshots_")
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def save(self, state: dict[str, Any]) -> SnapshotOutput:
        """Persiste el estado y retorna la vista esencial.

        Args:
            state: Estado de la sesion (JSON-serializable; claves
                sugeridas: task, turns[{summary,...}], facts[...]).

        Returns:
            SnapshotOutput con handle y vista <= ESSENTIAL_MAX_CHARS.
        """
        payload = json.dumps(state, ensure_ascii=False, sort_keys=True)
        handle = _handle_for(payload)
        (self._cache_dir / f"{handle}.json").write_text(payload, encoding="utf-8")
        view = self._render_view(state, handle)
        logger.info(
            "session_snapshot: estado %d chars -> vista %d chars (handle=%s)",
            len(payload), len(view), handle,
        )
        return SnapshotOutput(handle=handle, view=view)

    def restore(self, handle: str) -> dict[str, Any]:
        """Restaura el estado completo por handle (byte-exacto).

        Args:
            handle: Identificador del snapshot.

        Returns:
            Dict del estado guardado.

        Raises:
            FileNotFoundError: Si el handle no existe (WHAT+WHY+WHERE).
        """
        path = self._cache_dir / f"{handle}.json"
        if not path.is_file():
            raise FileNotFoundError(
                f"WHAT: snapshot no encontrado: {handle}. "
                f"WHY: el handle no fue guardado en este store (o la cache "
                f"fue limpiada). WHERE: SessionSnapshotter.restore"
            )
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"value": data}

    def _render_view(self, state: dict[str, Any], handle: str) -> str:
        """Renderiza la vista esencial acotada del estado.

        Args:
            state: Estado de la sesion.
            handle: Handle del snapshot (para restore on-demand).

        Returns:
            Texto <= ESSENTIAL_MAX_CHARS con tarea, ultimos turnos y hechos.
        """
        lines = ["[session-snapshot] estado completo en disco:"]
        task = str(state.get("task", ""))
        if task:
            lines.append(f"TAREA: {task[:200]}")
        turns = state.get("turns", [])
        if isinstance(turns, list) and turns:
            lines.append(f"ULTIMOS {VIEW_TURNS} TURNOS:")
            for turn in turns[-VIEW_TURNS:]:
                if isinstance(turn, dict):
                    summary = str(turn.get("summary", turn.get("tool", "?")))
                else:
                    summary = str(turn)
                lines.append(f"- {summary[:160]}")
        facts = state.get("facts", [])
        if isinstance(facts, list) and facts:
            lines.append("HECHOS:")
            for fact in facts[:VIEW_FACTS]:
                lines.append(f"- {str(fact)[:160]}")
        lines.append(f"RESTORE: handle={handle} (query_memory on-demand)")
        view = "\n".join(lines)
        if len(view.encode("utf-8")) > ESSENTIAL_MAX_CHARS:
            view = view[: ESSENTIAL_MAX_CHARS - 3].rstrip() + "..."
        return view


def save_snapshot(state: dict[str, Any]) -> SnapshotOutput:
    """Atajo: guarda con directorio default.

    Args:
        state: Estado de la sesion.

    Returns:
        SnapshotOutput con handle y vista.
    """
    return SessionSnapshotter().save(state)
