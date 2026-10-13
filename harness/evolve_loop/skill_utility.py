"""Skill Utility — asignacion de utilidad y retencion de skills (SESA).

Implementa las reglas de *utility assignment* y *retention* de SESA
(arXiv 2607.29468): los skills derivados de fallos deben trackear su utilidad
observada downstream y evitarse (evictarse) cuando no ayudan.

Reglas:
    - Cada skill acumula tres contadores: ``helpful`` (usado en una trayectoria
      CORRECTA), ``hurt`` (usado en una trayectoria INCORRECTA sustantiva) y
      ``retrievals`` (total de recuperaciones/invocaciones).
    - Un skill NO-seed es **evictable** cuando ``retrievals >= min_retrievals``
      y la utilidad neta ``helpful - hurt < 0``.
    - Las trayectorias malformadas se ignoran: el caller simplemente no marca.

Persistencia (JSONL append-only, como ``failure_registry``):
    Cada marca escribe UNA linea ``{"name": ..., "event": ...}``. El estado se
    reconstruye replayando los eventos al cargar; el evento ``removed`` borra el
    registro (eviction). Este diseno es idempotente y reconstruible.

Diseno:
    - ``SkillUtility`` es un ``frozen dataclass`` (IMM: snapshot inmutable).
    - ``SkillUtilityTracker`` recibe ``path`` y ``skills_dir`` por DI; en tests
      se inyectan rutas temporales para NUNCA tocar el JSONL real ni el
      directorio real de skills auto-generados.
    - Best-effort: un fallo de IO loguea (WHAT+WHY+WHERE) y no rompe el loop.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from harness.evolve_loop.procedural_memory import AUTO_SKILLS_DIR

logger = logging.getLogger(__name__)

#: Minimo de recuperaciones antes de poder evictar un skill (MAG: constante con
#: nombre en vez de un literal magico repetido en firmas y pruebas).
MIN_RETRIEVALS = 3

#: Evento de recuperacion/invocacion del skill.
_EVENT_RETRIEVAL = "retrieval"
#: Evento de uso del skill en una trayectoria CORRECTA.
_EVENT_HELPFUL = "helpful"
#: Evento de uso del skill en una trayectoria INCORRECTA sustantiva.
_EVENT_HURT = "hurt"
#: Evento de eviction: borra el registro del skill al reconstruir.
_EVENT_REMOVED = "removed"

#: Mapeo evento → nombre del campo del ``SkillUtility`` que incrementa.
_EVENT_FIELD: dict[str, str] = {
    _EVENT_HELPFUL: "helpful",
    _EVENT_HURT: "hurt",
    _EVENT_RETRIEVAL: "retrievals",
}

#: Ruta por defecto del JSONL (hermana de ``failures.jsonl``).
_DEFAULT_PATH = Path(__file__).resolve().parent.parent / "db" / "skill_utility.jsonl"


@dataclass(frozen=True)
class SkillUtility:
    """Snapshot inmutable de la utilidad observada de un skill.

    Attributes:
        name: Nombre del skill (determinista, p. ej. ``avoid-<slug>-<hash>``).
        helpful: Veces usado en una trayectoria CORRECTA.
        hurt: Veces usado en una trayectoria INCORRECTA sustantiva.
        retrievals: Total de veces recuperado/invocado.
    """

    name: str
    helpful: int = 0
    hurt: int = 0
    retrievals: int = 0

    @property
    def net(self) -> int:
        """Utilidad neta observada (``helpful - hurt``).

        Returns:
            Entero; negativo indica skill danino, positivo beneficioso.
        """
        return self.helpful - self.hurt

    def to_dict(self) -> dict[str, Any]:
        """Serializa el snapshot a un dict plano para persistencia JSON.

        Returns:
            Dict con ``name``, ``helpful``, ``hurt`` y ``retrievals``.
        """
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SkillUtility:
        """Deserializa un snapshot desde un dict (tolerante a campos faltantes).

        Args:
            data: Dict con al menos ``name``; el resto opcional (default 0).

        Returns:
            La instancia ``SkillUtility`` reconstruida.
        """
        return cls(
            name=data["name"],
            helpful=int(data.get("helpful", 0)),
            hurt=int(data.get("hurt", 0)),
            retrievals=int(data.get("retrievals", 0)),
        )


class SkillUtilityTracker:
    """Rastrea y persiste la utilidad observada de los skills (SESA retention).

    Attributes:
        _path: Ruta al JSONL append-only de eventos.
        _skills_dir: Directorio donde viven los ``.md`` auto-generados.
        _state: Cache en memoria ``name → SkillUtility``.
    """

    def __init__(
        self,
        *,
        path: Path | None = None,
        skills_dir: Path | None = None,
    ) -> None:
        """Inicializa el tracker y reconstruye su estado desde disco.

        Args:
            path: Ruta al JSONL de eventos. Default: ``harness/db/skill_utility.jsonl``.
            skills_dir: Directorio de skills auto-generados para ``prune``.
                Default: el directorio ``.opencode/skills/auto`` de ``ProceduralMemory``.
        """
        self._path = path if path is not None else _DEFAULT_PATH
        self._skills_dir = (
            Path(skills_dir) if skills_dir is not None else Path(AUTO_SKILLS_DIR)
        )
        self._state: dict[str, SkillUtility] = {}
        self._load()

    # -- Marcado publico ---------------------------------------------------

    def mark_helpful(self, name: str) -> None:
        """Marca el skill como usado en una trayectoria CORRECTA.

        Args:
            name: Nombre del skill invocado.
        """
        self._mark(name, _EVENT_HELPFUL)

    def mark_hurt(self, name: str) -> None:
        """Marca el skill como usado en una trayectoria INCORRECTA sustantiva.

        Args:
            name: Nombre del skill invocado.
        """
        self._mark(name, _EVENT_HURT)

    def mark_retrieval(self, name: str) -> None:
        """Registra una recuperacion/invocacion del skill.

        Args:
            name: Nombre del skill recuperado.
        """
        self._mark(name, _EVENT_RETRIEVAL)

    def get(self, name: str) -> SkillUtility:
        """Devuelve el snapshot de utilidad de un skill.

        Args:
            name: Nombre del skill consultado.

        Returns:
            El ``SkillUtility`` observado, o uno con contadores en cero si no existe.
        """
        return self._state.get(name, SkillUtility(name=name))

    def names(self) -> list[str]:
        """Lista los nombres de las skills rastreadas actualmente.

        WHAT: expone (solo lectura) las claves del estado en memoria para que
        un consumidor —p. ej. ``LibraryDriftManager``— pueda recorrer TODAS las
        skills registradas sin tocar el atributo privado ``_state``. WHY: el
        ``sweep`` de la politica de retiro necesita el universo completo, no
        solo los evictables. WHERE: ``SkillUtilityTracker.names``.

        Returns:
            Lista con los nombres rastreados (en orden de insercion).
        """
        return list(self._state)

    # -- Eviction ----------------------------------------------------------

    def evictable(self, *, min_retrievals: int = MIN_RETRIEVALS) -> list[SkillUtility]:
        """Lista los skills con utilidad neta negativa y suficiente uso.

        Args:
            min_retrievals: Minimo de recuperaciones para ser evictable.

        Returns:
            Snapshots evictables ordenados por ``net`` ascendente (los mas
            daninos primero).
        """
        candidates = [
            util
            for util in self._state.values()
            if util.retrievals >= min_retrievals and util.net < 0
        ]
        return sorted(candidates, key=lambda util: util.net)

    def prune(self, *, min_retrievals: int = MIN_RETRIEVALS) -> list[str]:
        """Ejecuta la eviction: elimina el ``.md`` y el registro del tracker.

        Args:
            min_retrievals: Minimo de recuperaciones para ser evictable.

        Returns:
            Nombres de los skills eliminados, en el orden de ``evictable``.
        """
        pruned: list[str] = []
        for util in self.evictable(min_retrievals=min_retrievals):
            self._remove_skill_file(util.name)
            self._append_event(util.name, _EVENT_REMOVED)
            self._state.pop(util.name, None)
            pruned.append(util.name)
            logger.info("Skill evictado por utilidad neta negativa: %s", util.name)
        return pruned

    # -- Internos ----------------------------------------------------------

    def _mark(self, name: str, event: str) -> None:
        """Aplica un evento de marcado y lo persiste (best-effort).

        Args:
            name: Nombre del skill.
            event: Tipo de evento (``helpful``, ``hurt`` o ``retrieval``).
        """
        self._append_event(name, event)
        self._apply(event, name)

    def _apply(self, event: str, name: str) -> None:
        """Actualiza el estado en memoria replayando un evento.

        Args:
            event: Tipo de evento.
            name: Nombre del skill afectado.
        """
        if event == _EVENT_REMOVED:
            self._state.pop(name, None)
            return
        field = _EVENT_FIELD.get(event)
        if field is None:
            logger.warning(
                "Evento de utilidad desconocido ignorado: %s | "
                "WHY: el JSONL contiene una linea no reconocida | "
                "WHERE: SkillUtilityTracker._apply",
                event,
            )
            return
        current = self._state.get(name, SkillUtility(name=name))
        self._state[name] = replace(current, **{field: getattr(current, field) + 1})

    def _load(self) -> None:
        """Reconstruye el estado replayando el JSONL (carga idempotente).

        Un archivo ausente deja el estado vacio. Lineas malformadas o JSON
        invalido se ignoran con warning (best-effort).
        """
        if not self._path.is_file():
            return
        try:
            raw = self._path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning(
                "No se pudo leer skill_utility.jsonl: %s | "
                "WHY: permisos o disco inaccesible | "
                "WHERE: SkillUtilityTracker._load",
                exc,
            )
            return
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError as exc:
                logger.warning(
                    "Linea de skill_utility.jsonl invalida ignorada: %s | "
                    "WHY: JSON corrupto | "
                    "WHERE: SkillUtilityTracker._load",
                    exc,
                )
                continue
            self._apply(str(data.get("event", "")), str(data.get("name", "")))

    def _append_event(self, name: str, event: str) -> None:
        """Append un evento al JSONL (best-effort, append-only).

        Args:
            name: Nombre del skill.
            event: Tipo de evento.
        """
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps({"name": name, "event": event}, ensure_ascii=False)
                    + "\n"
                )
        except OSError as exc:
            logger.warning(
                "No se pudo persistir evento de utilidad %s/%s: %s | "
                "WHY: disco lleno o permisos | "
                "WHERE: SkillUtilityTracker._append_event",
                name,
                event,
                exc,
            )

    def _remove_skill_file(self, name: str) -> None:
        """Elimina el ``.md`` del skill si existe (best-effort).

        Args:
            name: Nombre del skill a eliminar fisicamente.
        """
        skill_path = self._skills_dir / f"{name}.md"
        if not skill_path.is_file():
            return
        try:
            skill_path.unlink()
        except OSError as exc:
            logger.warning(
                "No se pudo eliminar el skill %s: %s | "
                "WHY: permisos o archivo bloqueado | "
                "WHERE: SkillUtilityTracker._remove_skill_file",
                skill_path,
                exc,
            )
