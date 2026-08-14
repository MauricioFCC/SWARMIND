"""
DeltaChannel — durable execution con checkpoints delta (ADR-0041 H3).

Inspirado en DeltaChannel de LangChain (langchain.com/blog/delta-channels):
cada mutacion registra SOLO el delta incremental (WAL por paso) y se escribe
un snapshot completo cada K pasos, acotando el costo de resume.

Reduccion de storage ~40x frente a full-snapshot por paso (O(N^2) -> O(N)).

Diseño (KISS + robusto):
  - Delta log por archivo: `delta_<step_id>.json` (append-only, un archivo por
    paso). La idempotencia es trivial: si el archivo existe, no se re-aplica.
  - Snapshots: `snapshot_<seq>.json` con el estado consolidado + la lista de
    step_ids incluidos. Se conservan todos (historia append-only); resume lee
    el de mayor seq.
  - Persistencia atomica: escritura a `<nombre>.tmp` y `os.replace()` — nunca
    se observa un archivo corrupto tras un crash a mitad de escritura.

CONSTRAINT (Batching-Invariance):
  Los reducers deben ser conmutativos/asociativos: el resultado consolidado
  debe ser identico independientemente del orden en que se apliquen los deltas
  (igual que DeltaChannel de LangChain). En la practica, `apply_step` fusiona
  `delta` sobre el estado con `state.update(delta)` (reemplazo de claves de
  nivel superior). Por tanto, si dos pasos escriben la MISMA clave de nivel
  superior con valores distintos, el estado final depende del orden y viola el
  constraint — el caller debe evitar ese escenario o usar valores identicos.

API (lista para integrarse con TaskOrchestrator/WAL; sin acoplamiento en esta
iteracion — YAGNI):
  - apply_step(step_id, delta): registra y persiste el delta.
  - snapshot(): estado consolidado actual y lo persiste.
  - resume(): reconstruye estado desde el ultimo snapshot + replay (resume flat).
  - reset(): limpia el checkpoint.
  - stats(): metricas de la instancia.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes (sin magic numbers)
# ---------------------------------------------------------------------------

K_SNAPSHOT_DEFAULT = 50
DEFAULT_STATE_DIR = Path.home() / ".swarmind" / "checkpoints"
SNAPSHOT_PREFIX = "snapshot_"
DELTA_PREFIX = "delta_"
JSON_SUFFIX = ".json"
TMP_SUFFIX = ".tmp"
SNAPSHOT_TYPE = "delta_snapshot"
DELTA_TYPE = "delta_entry"
_STEP_ID_PATTERN = re.compile(r"[A-Za-z0-9._-]+")


# ---------------------------------------------------------------------------
# Helpers de archivos (pathlib siempre)
# ---------------------------------------------------------------------------


def _snapshot_files(state_dir: Path) -> list[Path]:
    """Archivos snapshot_*.json existentes en state_dir (orden lexicografico)."""
    return sorted(state_dir.glob(f"{SNAPSHOT_PREFIX}*{JSON_SUFFIX}"))


def _delta_files(state_dir: Path) -> list[Path]:
    """Archivos delta_*.json existentes en state_dir (orden lexicografico)."""
    return sorted(state_dir.glob(f"{DELTA_PREFIX}*{JSON_SUFFIX}"))


def _snapshot_seq(path: Path) -> int:
    """Secuencia numerica de un snapshot a partir de su nombre de archivo.

    Args:
        path: Ruta del snapshot (ej. `snapshot_3.json`).

    Returns:
        Entero de secuencia del snapshot.

    Raises:
        ValueError: Si el nombre no tiene un entero valido tras el prefijo.
    """
    return int(path.stem[len(SNAPSHOT_PREFIX):])


def _step_id_from_delta_path(path: Path) -> str:
    """Step_id de un delta a partir de su nombre de archivo.

    Args:
        path: Ruta del delta (ej. `delta_s1.json`).

    Returns:
        Step_id del paso (todo lo que sigue al prefijo `delta_`).
    """
    return path.stem[len(DELTA_PREFIX):]


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    """Escritura atomica de JSON: archivo .tmp + os.replace.

    Args:
        path: Ruta final del archivo JSON.
        data: Dict JSON-serializable a persistir.

    Raises:
        OSError: Si la escritura del temporal falla.
        TypeError: Si data contiene valores no serializables.
    """
    tmp_path = path.with_suffix(TMP_SUFFIX)
    tmp_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    os.replace(tmp_path, path)


class DeltaChannel:
    """
    Canal de ejecucion durable con checkpoints delta (ADR-0041 H3).

    Cada paso registra un delta incremental en un archivo JSON (WAL por paso)
    y, cada `snapshot_every` pasos, se persiste un snapshot completo del estado
    consolidado. `resume()` reconstruye el estado desde el ultimo snapshot y
    reaplica los deltas posteriores (resume flat).

    Usage:
        channel = DeltaChannel(snapshot_every=3, state_dir=Path("cp"))
        channel.apply_step("s1", {"tokens": 10})
        state = channel.resume()  # tras un crash: {"tokens": 10}
    """

    def __init__(
        self,
        snapshot_every: int = K_SNAPSHOT_DEFAULT,
        state_dir: str | Path | None = None,
    ) -> None:
        """
        Args:
            snapshot_every: Pasos entre snapshots completos (>= 1).
            state_dir: Directorio de persistencia. Si es None se usa
                `~/.swarmind/checkpoints`.

        Raises:
            ValueError: Si snapshot_every < 1.
        """
        if snapshot_every < 1:
            raise ValueError(
                "DeltaChannel.__init__ | WHAT=snapshot_every_invalido "
                f"| WHY=debe_ser_mayor_o_igual_a_1 | WHERE=__init__ | valor={snapshot_every}"
            )
        self._snapshot_every = snapshot_every
        self._state_dir = Path(state_dir) if state_dir is not None else DEFAULT_STATE_DIR
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._state: dict[str, Any] = {}
        self._applied_steps: list[str] = []
        self._pending_deltas = 0
        logger.debug("DeltaChannel init: state_dir=%s", self._state_dir)

    # ------------------------------------------------------------------
    # API publica
    # ------------------------------------------------------------------

    def apply_step(self, step_id: str, delta: dict[str, Any]) -> None:
        """
        Registrar y persistir el delta incremental de un paso.

        Valida entradas, ignora pasos ya aplicados (idempotencia en memoria y
        en disco) y escribe un snapshot completo cada `snapshot_every` pasos.

        Args:
            step_id: Identificador unico del paso (non-empty, chars seguros).
            delta: Cambio incremental JSON-serializable (dict).

        Raises:
            ValueError: Si step_id es vacio, solo espacios o con caracteres
                inseguros para nombre de archivo.
            TypeError: Si delta no es un dict.
            OSError: Si la persistencia del delta falla.
        """
        self._validate_step_id(step_id)
        if not isinstance(delta, dict):
            raise TypeError(
                "DeltaChannel.apply_step | WHAT=delta_no_dict "
                "| WHY=delta_debe_ser_dict | WHERE=apply_step"
            )
        if self._is_applied(step_id):
            logger.debug("DeltaChannel.apply_step | skip idempotente: %s", step_id)
            return

        self._write_delta(step_id, delta)
        self._state.update(copy.deepcopy(delta))
        self._applied_steps.append(step_id)
        self._pending_deltas += 1
        if self._pending_deltas >= self._snapshot_every:
            self._persist_snapshot()

    def snapshot(self) -> dict[str, Any]:
        """
        Devolver el estado consolidado actual y persistirlo.

        El snapshot completo incluye el estado base mas todos los deltas
        aplicados hasta el momento.

        Returns:
            Copia del estado consolidado (snapshot base + deltas aplicados).
        """
        self._persist_snapshot()
        return copy.deepcopy(self._state)

    def resume(self) -> dict[str, Any] | None:
        """
        Reconstruir el estado desde el ultimo snapshot + replay de deltas.

        Si no existe snapshot, se reaplican todos los deltas desde estado
        vacio. Devuelve None si no hay estado persistido (sin snapshots y sin
        deltas). En instancias nuevas, llamar a resume() antes de apply_step
        para rehidratar el estado previo.

        Returns:
            Estado consolidado reconstruido, o None si no hay estado.

        Raises:
            OSError: Si la lectura de archivos falla.
        """
        snapshots = _snapshot_files(self._state_dir)
        deltas = _delta_files(self._state_dir)
        if not snapshots and not deltas:
            return None

        self._state = {}
        self._applied_steps = []
        self._pending_deltas = 0
        included: set[str] = set()

        if snapshots:
            latest = max(snapshots, key=_snapshot_seq)
            data = json.loads(latest.read_text(encoding="utf-8"))
            self._state = copy.deepcopy(data["state"])
            included = set(data["included_step_ids"])
            self._applied_steps = list(data["included_step_ids"])

        for delta_path in deltas:
            step_id = _step_id_from_delta_path(delta_path)
            if step_id in included:
                continue
            entry = json.loads(delta_path.read_text(encoding="utf-8"))
            self._state.update(copy.deepcopy(entry["delta"]))
            self._applied_steps.append(step_id)
            self._pending_deltas += 1

        logger.info(
            "DeltaChannel resume: %d pasos, %d pendientes",
            len(self._applied_steps), self._pending_deltas,
        )
        return copy.deepcopy(self._state)

    def reset(self) -> None:
        """Limpiar el checkpoint actual (deltas + snapshots) y el estado."""
        for path in _delta_files(self._state_dir) + _snapshot_files(self._state_dir):
            path.unlink(missing_ok=True)
        self._state = {}
        self._applied_steps = []
        self._pending_deltas = 0
        logger.debug("DeltaChannel reset: checkpoint limpiado en %s", self._state_dir)

    def stats(self) -> dict[str, int]:
        """
        Metricas de la instancia.

        Returns:
            Dict con: steps_applied (pasos aplicados), pending_deltas (deltas
            posteriores al ultimo snapshot), total_snapshots (snapshots en
            disco) y storage_bytes (tamano aproximado en disco).
        """
        snapshots = _snapshot_files(self._state_dir)
        deltas = _delta_files(self._state_dir)
        storage_bytes = sum(
            path.stat().st_size for path in snapshots + deltas
        )
        return {
            "steps_applied": len(self._applied_steps),
            "pending_deltas": self._pending_deltas,
            "total_snapshots": len(snapshots),
            "storage_bytes": storage_bytes,
        }

    # ------------------------------------------------------------------
    # Helpers privados
    # ------------------------------------------------------------------

    def _validate_step_id(self, step_id: str) -> None:
        """Validar step_id (non-empty y con caracteres seguros para filename).

        Args:
            step_id: Identificador del paso a validar.

        Raises:
            ValueError: Si es vacio, solo espacios o con caracteres inseguros
                (previene path traversal en el nombre del archivo delta).
        """
        if not isinstance(step_id, str) or not step_id.strip():
            raise ValueError(
                "DeltaChannel.apply_step | WHAT=step_id_vacio "
                "| WHY=identificador_obligatorio_no_vacio | WHERE=apply_step"
            )
        if _STEP_ID_PATTERN.fullmatch(step_id) is None:
            raise ValueError(
                "DeltaChannel.apply_step | WHAT=step_id_invalido "
                "| WHY=caracteres_inseguros_para_filename | WHERE=apply_step"
                f" | step_id={step_id!r}"
            )

    def _delta_path(self, step_id: str) -> Path:
        """Ruta del archivo delta para un step_id."""
        return self._state_dir / f"{DELTA_PREFIX}{step_id}{JSON_SUFFIX}"

    def _is_applied(self, step_id: str) -> bool:
        """True si el paso ya fue aplicado (en memoria o en disco)."""
        return step_id in self._applied_steps or self._delta_path(step_id).exists()

    def _write_delta(self, step_id: str, delta: dict[str, Any]) -> None:
        """Persistir el delta en un archivo JSON de forma atomica."""
        path = self._delta_path(step_id)
        data = {
            "type": DELTA_TYPE,
            "step_id": step_id,
            "delta": delta,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        _atomic_write_json(path, data)

    def _persist_snapshot(self) -> None:
        """Persistir snapshot completo del estado consolidado (atomico)."""
        seq = len(_snapshot_files(self._state_dir)) + 1
        path = self._state_dir / f"{SNAPSHOT_PREFIX}{seq}{JSON_SUFFIX}"
        data = {
            "type": SNAPSHOT_TYPE,
            "sequence": seq,
            "steps": len(self._applied_steps),
            "included_step_ids": list(self._applied_steps),
            "state": copy.deepcopy(self._state),
            "timestamp": datetime.now(UTC).isoformat(),
        }
        _atomic_write_json(path, data)
        self._pending_deltas = 0
        logger.debug("DeltaChannel snapshot #%d: %d pasos", seq, len(self._applied_steps))
