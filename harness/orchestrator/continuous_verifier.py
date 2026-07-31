"""Continuous Verification (CV) post-deploy — ADR-0033, plan maestro Fase 3.3.

Monitorea metricas de negocio reales tras cada despliegue: se registra un
baseline pre-deploy y muestras post-deploy durante una ventana de tiempo.
Si una metrica sube mas del umbral configurado respecto al baseline, el
cambio se revierte automaticamente (rollback) y queda registrado para que
el evolve-analyzer lo notifique.

Uso:
    verifier = ContinuousVerifier(degradation_threshold_pct=5.0)
    verifier.register_baseline("deploy-1", {"latency_ms": 100.0})
    verifier.record_sample("deploy-1", "latency_ms", 118.0)
    result = verifier.verify("deploy-1")
    if not result.passed:
        print(verifier.get_rollback_log())
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class MetricSample:
    """Muestra de una metrica de negocio post-despliegue."""

    metric: str
    value: float
    timestamp: float

    def to_dict(self) -> dict[str, float | str]:
        """Serializa la muestra a dict plano.

        Returns:
            dict con las claves "metric", "value" y "timestamp".
        """
        return {
            "metric": self.metric,
            "value": self.value,
            "timestamp": self.timestamp,
        }


@dataclass
class VerificationResult:
    """Resultado de una verificacion continua de despliegue."""

    deployment_id: str
    passed: bool
    degraded_metrics: list[str] = field(default_factory=list)
    rollback_triggered: bool = False
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serializa el resultado a dict plano (copias defensivas).

        Returns:
            dict con deployment_id, passed, degraded_metrics,
            rollback_triggered y details.
        """
        return {
            "deployment_id": self.deployment_id,
            "passed": self.passed,
            "degraded_metrics": list(self.degraded_metrics),
            "rollback_triggered": self.rollback_triggered,
            "details": dict(self.details),
        }


class ContinuousVerifier:
    """Verificador continuo de metricas post-despliegue.

    Registra un baseline por despliegue, acumula muestras con timestamp del
    clock inyectable y compara el valor actual contra el baseline: si el
    incremento porcentual supera (estrictamente) el umbral, la metrica se
    considera degradada y se ejecuta rollback automatico (ADR-0033).
    """

    def __init__(
        self,
        degradation_threshold_pct: float = 5.0,
        window_minutes: int = 30,
        clock: Callable[[], float] | None = None,
    ) -> None:
        """Inicializa el verificador con umbral, ventana y clock.

        Args:
            degradation_threshold_pct: incremento porcentual sobre el
                baseline que se considera degradacion (debe ser > 0).
            window_minutes: duracion de la ventana de monitoreo en minutos.
            clock: funcion sin argumentos del tiempo actual (inyectable
                para tests); por defecto usa time.time.

        Raises:
            ValueError: si degradation_threshold_pct <= 0 o
                window_minutes <= 0.
        """
        if degradation_threshold_pct <= 0:
            raise ValueError(
                f"WHAT: degradation_threshold_pct={degradation_threshold_pct} <= 0. "
                "WHY: un umbral no positivo degradaria cualquier despliegue o ninguno. "
                "WHERE: ContinuousVerifier.__init__"
            )
        if window_minutes <= 0:
            raise ValueError(
                f"WHAT: window_minutes={window_minutes} <= 0. "
                "WHY: la ventana de monitoreo debe tener duracion positiva. "
                "WHERE: ContinuousVerifier.__init__"
            )
        self._threshold_pct: float = degradation_threshold_pct
        self._window_seconds: float = window_minutes * 60.0
        self._clock: Callable[[], float] = clock or time.time
        self._baselines: dict[str, dict[str, float]] = {}
        self._baseline_times: dict[str, float] = {}
        self._samples: dict[str, dict[str, list[MetricSample]]] = {}
        self._rollback_log: list[dict] = []
        self._verified_deployments: set[str] = set()
        self._degraded_metric_count: int = 0
        self._lock = threading.RLock()

    def register_baseline(self, deployment_id: str, baseline: dict[str, float]) -> None:
        """Registra el baseline pre-deploy de un despliegue.

        Reinicia las muestras previas del despliegue: cada despliegue es un
        ciclo de monitoreo independiente.

        Args:
            deployment_id: identificador unico del despliegue.
            baseline: dict metrica -> valor pre-despliegue.

        Raises:
            ValueError: si deployment_id esta vacio o baseline es vacio.
        """
        if not deployment_id:
            raise ValueError(
                "WHAT: deployment_id vacio. "
                "WHY: un despliegue sin identificador no se puede verificar. "
                "WHERE: ContinuousVerifier.register_baseline"
            )
        if not baseline:
            raise ValueError(
                "WHAT: baseline vacio. "
                "WHY: sin metricas baseline no hay nada que comparar. "
                "WHERE: ContinuousVerifier.register_baseline"
            )
        with self._lock:
            self._baselines[deployment_id] = dict(baseline)
            self._baseline_times[deployment_id] = self._clock()
            self._samples[deployment_id] = {}

    def record_sample(self, deployment_id: str, metric: str, value: float) -> None:
        """Registra una muestra post-deploy con el timestamp del clock.

        Args:
            deployment_id: identificador del despliegue.
            metric: nombre de la metrica muestreada.
            value: valor observado de la metrica.
        """
        with self._lock:
            samples = self._samples.setdefault(deployment_id, {})
            samples.setdefault(metric, []).append(
                MetricSample(metric=metric, value=value, timestamp=self._clock())
            )

    def verify(
        self,
        deployment_id: str,
        current: dict[str, float] | None = None,
    ) -> VerificationResult:
        """Compara cada metrica del baseline con el valor actual.

        El valor actual proviene del dict `current` si se entrega; si no,
        de la ultima muestra registrada para esa metrica. Una metrica se
        considera degradada cuando
        (actual - baseline) / baseline * 100 > umbral, estrictamente.
        Ante degradacion se ejecuta rollback automatico y se registra log
        con WHAT+WHY+WHERE.

        Args:
            deployment_id: identificador del despliegue verificado.
            current: dict metrica -> valor actual (opcional; alternativo
                a las muestras registradas).

        Returns:
            VerificationResult con passed, metricas degradadas,
            rollback_triggered y detalles por metrica.

        Raises:
            ValueError: si no hay baseline registrado para el despliegue.
        """
        with self._lock:
            baseline = self._baselines.get(deployment_id)
            if baseline is None:
                raise ValueError(
                    f"WHAT: sin baseline para deployment_id={deployment_id!r}. "
                    "WHY: no se puede verificar un despliegue sin baseline pre-deploy. "
                    "WHERE: ContinuousVerifier.verify"
                )

            degraded_metrics: list[str] = []
            metrics_detail: dict = {}
            for metric, base_value in baseline.items():
                if base_value == 0:
                    logger.warning(
                        "WHAT: baseline=0 para metrica %s (deploy %s). "
                        "WHY: el porcentaje de cambio no esta definido (division por cero). "
                        "WHERE: ContinuousVerifier.verify; metrica omitida",
                        metric,
                        deployment_id,
                    )
                    continue
                actual = self._resolve_current(deployment_id, metric, current)
                if actual is None:
                    continue
                delta_pct = (actual - base_value) / base_value * 100.0
                degraded = delta_pct > self._threshold_pct
                metrics_detail[metric] = {
                    "baseline": base_value,
                    "current": actual,
                    "delta_pct": round(delta_pct, 4),
                    "degraded": degraded,
                }
                if degraded:
                    degraded_metrics.append(metric)

            self._verified_deployments.add(deployment_id)
            self._degraded_metric_count += len(degraded_metrics)
            details = {
                "compared_via": "current_dict" if current is not None else "samples",
                "threshold_pct": self._threshold_pct,
                "metrics": metrics_detail,
            }

            if degraded_metrics:
                logger.warning(
                    "WHAT: degradacion detectada en %s (deploy %s): %s. "
                    "WHY: el incremento supera el umbral de %.2f%% sobre el baseline. "
                    "WHERE: ContinuousVerifier.verify; rollback automatico",
                    ", ".join(degraded_metrics),
                    deployment_id,
                    {
                        m: metrics_detail[m]["delta_pct"] for m in degraded_metrics
                    },
                    self._threshold_pct,
                )
                self.rollback(
                    deployment_id,
                    f"degradacion en metricas {', '.join(degraded_metrics)}",
                )
                return VerificationResult(
                    deployment_id=deployment_id,
                    passed=False,
                    degraded_metrics=degraded_metrics,
                    rollback_triggered=True,
                    details=details,
                )

            return VerificationResult(
                deployment_id=deployment_id,
                passed=True,
                degraded_metrics=[],
                rollback_triggered=False,
                details=details,
            )

    def check_window(self, deployment_id: str) -> tuple[bool, dict]:
        """Verifica si la ventana de monitoreo sigue activa.

        La ventana empieza al registrar el baseline y dura window_minutes.

        Args:
            deployment_id: identificador del despliegue.

        Returns:
            Tupla (activa, muestras_por_metrica) donde activa es True si el
            tiempo transcurrido es menor a la ventana, y muestras_por_metrica
            mapea cada metrica a la lista de valores muestreados.
        """
        with self._lock:
            start = self._baseline_times.get(deployment_id)
            if start is None:
                return False, {}
            active = (self._clock() - start) < self._window_seconds
            baseline = self._baselines.get(deployment_id, {})
            samples_by_metric = {
                metric: [
                    sample.value
                    for sample in self._samples.get(deployment_id, {}).get(metric, [])
                ]
                for metric in baseline
            }
            return active, samples_by_metric

    def rollback(self, deployment_id: str, reason: str) -> str:
        """Ejecuta el rollback del despliegue y lo registra en el log interno.

        Args:
            deployment_id: identificador del despliegue a revertir.
            reason: motivo del rollback.

        Returns:
            Mensaje "ROLLBACK: <deployment_id> — <reason>".
        """
        message = f"ROLLBACK: {deployment_id} — {reason}"
        with self._lock:
            self._rollback_log.append(
                {
                    "deployment_id": deployment_id,
                    "reason": reason,
                    "timestamp": self._clock(),
                    "message": message,
                }
            )
            logger.warning(
                "WHAT: %s. WHY: se revierte el cambio al commit anterior "
                "por degradacion post-despliegue. WHERE: ContinuousVerifier.rollback",
                message,
            )
        return message

    def get_rollback_log(self) -> list[dict]:
        """Historial de rollbacks ejecutados.

        Returns:
            Lista de entradas con deployment_id, reason, timestamp y message.
        """
        with self._lock:
            return [dict(entry) for entry in self._rollback_log]

    def stats(self) -> dict:
        """Resumen de actividad del verificador.

        Returns:
            dict con "verified_deployments" (despliegues unicos verificados),
            "rollbacks" (rollbacks registrados) y "degraded_metrics"
            (total de metricas degradadas detectadas).
        """
        with self._lock:
            return {
                "verified_deployments": len(self._verified_deployments),
                "rollbacks": len(self._rollback_log),
                "degraded_metrics": self._degraded_metric_count,
            }

    def _resolve_current(
        self,
        deployment_id: str,
        metric: str,
        current: dict[str, float] | None,
    ) -> float | None:
        """Resuelve el valor actual de una metrica para la verificacion.

        Args:
            deployment_id: identificador del despliegue.
            metric: nombre de la metrica.
            current: dict actual explicito, si se entrego.

        Returns:
            El valor actual (de `current` o de la ultima muestra) o None
            si no hay dato disponible.
        """
        if current is not None:
            return current.get(metric)
        samples = self._samples.get(deployment_id, {}).get(metric)
        if not samples:
            return None
        return samples[-1].value


__all__ = ["MetricSample", "VerificationResult", "ContinuousVerifier"]
