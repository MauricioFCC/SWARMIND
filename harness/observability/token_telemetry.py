"""TokenTelemetry — telemetria de tokens y cache por rol (FR-A1, ADR-0103).

WHAT: registra el uso de tokens (``cached``, ``input``, ``output``) por rol
de agente y expone el acierto de cache (``hit_rate``) mas una compuerta
(``gate_ok``) para verificar el umbral de Token Economics.
WHY: sin medir no hay ahorro verificable; la frontera 2026 (TKN) exige
telemetria primero para justificar cache-shape y observation masking.
WHERE: consumido por el coordinador/orchestrator para reportar token economics;
persistible a disco de forma opcional (best-effort, sin fallar el flujo).

Diseno:
    - ``UsageRecord``: registro inmutable de un uso puntual.
    - ``TokenTelemetry``: acumulador thread-safe (``threading.Lock``) que
      agrega por rol y total.

Uso:
    telemetry = TokenTelemetry()
    telemetry.record_usage("coder", cached=100, input=400, output=50)
    if telemetry.gate_ok(0.80):
        ...  # cache-hit suficiente
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger("harness.observability.token_telemetry")

#: Version del esquema de persistencia JSON.
SCHEMA_VERSION = 1

#: Umbral minimo de acierto de cache exigido por la compuerta TKN (FR-3).
MIN_HIT_RATE = 0.80


@dataclass(frozen=True)
class UsageRecord:
    """Registro inmutable de un uso de tokens (IMM: frozen dataclass).

    Attributes:
        role: Rol/agente que consumio los tokens.
        cached_tokens: Tokens servidos desde cache (cache-hit).
        input_tokens: Tokens de entrada no cacheados.
        output_tokens: Tokens generados como salida.
        timestamp: Marca temporal ISO-8601 (UTC).
    """

    role: str
    cached_tokens: int
    input_tokens: int
    output_tokens: int
    timestamp: str


class TokenTelemetry:
    """Acumulador thread-safe de telemetria de tokens por rol.

    Attributes:
        _records: Lista de registros de uso (protegida por ``_lock``).
        _lock: Lock que serializa lecturas/escrituras concurrentes.
    """

    def __init__(self) -> None:
        """Inicializa la telemetria vacia con su lock de concurrencia."""
        self._records: list[UsageRecord] = []
        self._lock: threading.Lock = threading.Lock()

    # ------------------------------------------------------------------
    # Registro
    # ------------------------------------------------------------------

    def record_usage(
        self,
        role: str,
        cached: int,
        input: int,
        output: int,
    ) -> None:
        """Registra un uso de tokens para un rol (thread-safe).

        Args:
            role: Rol/agente (no vacio).
            cached: Tokens servidos desde cache (>= 0).
            input: Tokens de entrada no cacheados (>= 0).
            output: Tokens de salida (>= 0).

        Raises:
            ValueError: Si ``role`` esta vacio o algun conteo es negativo
                (WHAT+WHY+WHERE).
        """
        if not role or not role.strip():
            raise ValueError(
                "WHAT: rol vacio en record_usage. "
                "WHY: sin rol no se puede atribuir el uso de tokens. "
                "WHERE: TokenTelemetry.record_usage"
            )
        for name, value in (("cached", cached), ("input", input), ("output", output)):
            if value < 0:
                raise ValueError(
                    f"WHAT: {name}={value} es negativo en record_usage. "
                    "WHY: los conteos de tokens no pueden ser negativos. "
                    "WHERE: TokenTelemetry.record_usage"
                )
        record = UsageRecord(
            role=role.strip(),
            cached_tokens=cached,
            input_tokens=input,
            output_tokens=output,
            timestamp=datetime.now(UTC).isoformat(),
        )
        with self._lock:
            self._records.append(record)

    # ------------------------------------------------------------------
    # Metricas
    # ------------------------------------------------------------------

    def hit_rate(self) -> float:
        """Calcula el acierto de cache global.

        Returns:
            ``total_cached / (total_input + total_cached)`` o ``0.0`` si el
            denominador es cero.
        """
        with self._lock:
            snapshot = list(self._records)
        return self._hit_rate_from(snapshot)

    def gate_ok(self, threshold: float = 0.80) -> bool:
        """Evalua si el ``hit_rate`` alcanza el umbral (compuerta TKN).

        Args:
            threshold: Umbral minimo de acierto de cache (default 0.80).

        Returns:
            True si ``hit_rate() >= threshold``.
        """
        return self.hit_rate() >= threshold

    def report(self) -> dict:
        """Genera el resumen agregado por rol, total y ``hit_rate``.

        Returns:
            Dict con ``roles`` (desglose por rol), ``total`` (agregado) y
            ``hit_rate`` global.
        """
        with self._lock:
            snapshot = list(self._records)

        roles: dict[str, dict[str, int]] = {}
        total = _empty_bucket()
        for record in snapshot:
            bucket = roles.setdefault(record.role, _empty_bucket())
            for name, value in (
                ("cached_tokens", record.cached_tokens),
                ("input_tokens", record.input_tokens),
                ("output_tokens", record.output_tokens),
            ):
                bucket[name] += value
                total[name] += value
            bucket["records"] += 1
            total["records"] += 1

        return {
            "roles": roles,
            "total": total,
            "hit_rate": self._hit_rate_from(snapshot),
        }

    # ------------------------------------------------------------------
    # Persistencia (best-effort)
    # ------------------------------------------------------------------

    def to_json(self, path: Path) -> bool:
        """Persiste los registros a JSON (best-effort, no falla el flujo).

        Args:
            path: Ruta destino (no se crean directorios padre).

        Returns:
            True si se escribio correctamente; False ante ``OSError``
            (se emite un warning, sin except silencioso).
        """
        with self._lock:
            snapshot = list(self._records)
        payload = {
            "version": SCHEMA_VERSION,
            "records": [asdict(record) for record in snapshot],
        }
        try:
            Path(path).write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return True
        except OSError as exc:
            logger.warning(
                "WHAT: no se pudo persistir telemetria en %s. "
                "WHY: %s. WHERE: TokenTelemetry.to_json",
                path,
                exc,
            )
            return False

    @classmethod
    def from_json(cls, path: Path) -> TokenTelemetry | None:
        """Carga registros desde JSON (best-effort).

        Args:
            path: Ruta del archivo a leer.

        Returns:
            Instancia con los registros reconstruidos, o None ante
            ``OSError``/JSON invalido (se emite warning).
        """
        try:
            raw = Path(path).read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning(
                "WHAT: no se pudo leer telemetria de %s. "
                "WHY: %s. WHERE: TokenTelemetry.from_json",
                path,
                exc,
            )
            return None
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning(
                "WHAT: JSON invalido en %s. "
                "WHY: %s. WHERE: TokenTelemetry.from_json",
                path,
                exc,
            )
            return None

        instance = cls()
        records = [
            UsageRecord(
                role=str(item.get("role", "")),
                cached_tokens=int(item.get("cached_tokens", 0)),
                input_tokens=int(item.get("input_tokens", 0)),
                output_tokens=int(item.get("output_tokens", 0)),
                timestamp=str(item.get("timestamp", "")),
            )
            for item in payload.get("records", [])
            if isinstance(item, dict)
        ]
        with instance._lock:
            instance._records = records
        return instance

    # ------------------------------------------------------------------
    # Helpers privados
    # ------------------------------------------------------------------

    @staticmethod
    def _hit_rate_from(records: list[UsageRecord]) -> float:
        """Calcula el hit_rate de una lista de registros.

        Args:
            records: Registros a agregar.

        Returns:
            Acierto de cache; ``0.0`` si el denominador es cero.
        """
        total_cached = sum(record.cached_tokens for record in records)
        total_input = sum(record.input_tokens for record in records)
        denominator = total_input + total_cached
        return total_cached / denominator if denominator > 0 else 0.0


class TelemetryGate:
    """Compuerta de cache-hit sobre una ``TokenTelemetry`` (FR-3, TKN).

    WHAT: verifica que el ``hit_rate`` global alcance ``MIN_HIT_RATE`` y, si no,
    entrega un diagnostico accionable (cache-buster flaggeado) que sugiere
    re-shapear el prompt. WHY: un hit-rate bajo suele indicar que el prefijo
    estable del prompt se invalida entre llamadas; medirlo con evidencia evita
    optimizar a ciegas. WHERE: lo consume ``PipelineRouter.route`` para loggear
    (nunca bloquea el pipeline).

    Uso:
        gate = TelemetryGate()
        ok, message = gate.check(telemetry)
    """

    def __init__(self, threshold: float = MIN_HIT_RATE) -> None:
        """Inicializa la compuerta con el umbral minimo de acierto.

        Args:
            threshold: Umbral minimo de ``hit_rate`` exigido (default
                ``MIN_HIT_RATE`` = 0.80).
        """
        self._threshold = threshold

    @property
    def threshold(self) -> float:
        """Umbral minimo de acierto de cache exigido por la compuerta."""
        return self._threshold

    def check(self, telemetry: TokenTelemetry) -> tuple[bool, str]:
        """Evalua el ``hit_rate`` de ``telemetry`` contra el umbral.

        Args:
            telemetry: Acumulador de telemetria a inspeccionar.

        Returns:
            Tupla ``(ok, message)``. ``ok`` es ``True`` si
            ``hit_rate >= threshold``; en caso contrario ``ok`` es ``False`` y
            ``message`` describe el "cache-buster" con la sugerencia de
            re-shapear el prompt (estables primero).
        """
        rate = telemetry.hit_rate()
        if rate < self._threshold:
            message = (
                f"cache-buster flaggeado: hit_rate {rate:.2f} < {self._threshold:.2f}; "
                "re-shapea el prompt (tools+system+static antes que dynamic)"
            )
            return False, message
        return True, f"cache-hit OK: hit_rate {rate:.2f} >= {self._threshold:.2f}"


def _empty_bucket() -> dict[str, int]:
    """Crea un bucket de agregacion en cero.

    Returns:
        Dict mutable con contadores de tokens y registros en cero.
    """
    return {
        "cached_tokens": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "records": 0,
    }


__all__ = ["MIN_HIT_RATE", "SCHEMA_VERSION", "TelemetryGate", "TokenTelemetry", "UsageRecord"]
