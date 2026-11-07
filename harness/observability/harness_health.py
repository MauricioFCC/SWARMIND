"""Harness Health — panel unificado de salud del harness (3 medidores + lift).

WHAT: agrega en un UNICO veredicto operativo los medidores de frontera que ya
existian pero estaban cableados sin reporte ni ejecucion programada:
``TokenTelemetry`` (TKN/cache-shape), ``LibraryDriftManager`` (retiro por
outcome), ``ConsistencyEvaluator`` (estabilidad run-to-run) y ``SkillLift``
(skills daninas). WHY: medir por separado no "activa" los medidores; sin un
panel con gates y un veredicto no hay compuerta de CI que convierta la
telemetria real en decision. WHERE: lo consume ``scripts/harness_health.py``
(CLI + persistencia) desde el workflow ``skills-quality.yml``.

Diseno (hexagonal + DI):
    - ``HealthThresholds`` / ``HarnessHealth`` son ``frozen dataclass`` (IMM).
    - ``HarnessHealthReporter`` recibe los medidores por DI (kw-only) y NUNCA
      los instancia: en tests se inyectan mocks/telemetrias temporales.
    - None-safe: un medidor ausente no rompe ``collect()``; su campo queda
      ``None`` (consistency/lift) y NO cuenta como gate evaluado.
    - Best-effort: la persistencia ante ``OSError`` loguea (WHAT+WHY+WHERE) y no
      propaga excepcion (0 except silenciosos).

Gates (3) y veredicto:
    - token: ``token_hit_rate >= min_token_hit_rate`` (default 0.80).
    - harmful: ``lift_harmful <= max_harmful_skills`` (default 0).
    - consistency: ``consistency_score >= min_consistency_score`` (0.9) si el
      medidor esta presente.
    Veredicto: ``healthy`` si todos pasan; ``degraded`` si falla exactamente 1;
    ``unhealthy`` si fallan >= 2 gates o si hay cualquier skill danina.

Uso:
    reporter = HarnessHealthReporter(telemetry=telemetry, drift=drift)
    health = reporter.collect()
    print(health.verdict, reporter.summary_markdown())
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

logger = logging.getLogger("harness.observability.harness_health")

#: Version del esquema de persistencia JSON.
SCHEMA_VERSION = 1

#: Umbral minimo de acierto de cache exigido por el gate TKN (MAG: constante
#: con nombre en vez de un literal repetido en firmas y pruebas).
MIN_TOKEN_HIT_RATE: float = 0.80

#: Maximo de skills daninas admitidas por el gate de skill lift (0 = ninguna).
MAX_HARMFUL_SKILLS: int = 0

#: Umbral minimo de consistencia run-to-run (arXiv:2607.27942, guia #4).
MIN_CONSISTENCY_SCORE: float = 0.9

#: Overrides por entorno (12-Factor; sin hardcode de la politica operativa).
ENV_MIN_TOKEN_HIT_RATE = "SWARMIND_HEALTH_MIN_TOKEN_HIT_RATE"
ENV_MAX_HARMFUL_SKILLS = "SWARMIND_HEALTH_MAX_HARMFUL_SKILLS"
ENV_MIN_CONSISTENCY_SCORE = "SWARMIND_HEALTH_MIN_CONSISTENCY_SCORE"

#: Veredicto agregado del panel de salud.
HealthVerdict = Literal["healthy", "degraded", "unhealthy"]

#: Clave del reporte de consistencia (salida de ``ConsistencyEvaluator.report``).
_CONSISTENCY_SCORE_KEY = "consistency_score"
#: Clave del reporte de lift con el conteo de skills daninas.
_HARMFUL_KEY = "harmful"
#: Claves toleradas del reporte de drift para skills en riesgo.
_AT_RISK_KEYS = ("cap_exceeded", "at_risk")


def _env_float(name: str, default: float) -> float:
    """Lee un flotante de entorno (default si ausente o invalido).

    Args:
        name: Nombre de la variable de entorno.
        default: Valor si no existe o no parsea.

    Returns:
        Flotante leido o ``default``; nunca lanza.
    """
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning(
            "WHAT: %s=%r no es flotante; uso %s. "
            "WHY: override de entorno invalido. "
            "WHERE: harness_health._env_float",
            name,
            raw,
            default,
        )
        return default


def _env_int(name: str, default: int) -> int:
    """Lee un entero de entorno (default si ausente o invalido).

    Args:
        name: Nombre de la variable de entorno.
        default: Valor si no existe o no parsea.

    Returns:
        Entero leido o ``default``; nunca lanza.
    """
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning(
            "WHAT: %s=%r no es entero; uso %s. "
            "WHY: override de entorno invalido. "
            "WHERE: harness_health._env_int",
            name,
            raw,
            default,
        )
        return default


@dataclass(frozen=True)
class HealthThresholds:
    """Umbrales inmutables que gobiernan los gates del panel de salud.

    Attributes:
        min_token_hit_rate: Acierto minimo de cache (gate TKN).
        max_harmful_skills: Maximo de skills daninas admitidas (gate lift).
        min_consistency_score: Consistencia run-to-run minima (gate estabilidad).

    Raises:
        ValueError: Si alguna tasa sale de ``[0, 1]`` o el maximo es negativo.
    """

    min_token_hit_rate: float = MIN_TOKEN_HIT_RATE
    max_harmful_skills: int = MAX_HARMFUL_SKILLS
    min_consistency_score: float = MIN_CONSISTENCY_SCORE

    def __post_init__(self) -> None:
        """Valida los umbrales (WHAT+WHY+WHERE si viola el contrato)."""
        for name, value in (
            ("min_token_hit_rate", self.min_token_hit_rate),
            ("min_consistency_score", self.min_consistency_score),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(
                    f"WHAT: {name}={value} fuera de [0, 1]. "
                    "WHY: es una tasa (fraccion entre 0 y 1). "
                    "WHERE: HealthThresholds.__post_init__"
                )
        if self.max_harmful_skills < 0:
            raise ValueError(
                f"WHAT: max_harmful_skills={self.max_harmful_skills} es negativo. "
                "WHY: no puede haber un maximo de skills daninas negativo. "
                "WHERE: HealthThresholds.__post_init__"
            )

    @classmethod
    def from_env(cls) -> HealthThresholds:
        """Construye los umbrales desde el entorno (defaults seguros).

        Returns:
            ``HealthThresholds`` con los overrides presentes (o defaults).

        Raises:
            ValueError: Si los valores del entorno violan la validacion.
        """
        return cls(
            min_token_hit_rate=_env_float(ENV_MIN_TOKEN_HIT_RATE, MIN_TOKEN_HIT_RATE),
            max_harmful_skills=_env_int(ENV_MAX_HARMFUL_SKILLS, MAX_HARMFUL_SKILLS),
            min_consistency_score=_env_float(
                ENV_MIN_CONSISTENCY_SCORE, MIN_CONSISTENCY_SCORE
            ),
        )


@dataclass(frozen=True)
class HarnessHealth:
    """Snapshot inmutable de la salud agregada del harness.

    Attributes:
        token_hit_rate: Acierto de cache global (0.0 si no hay telemetria).
        token_gate_ok: ``True`` si ``token_hit_rate`` alcanza el umbral.
        skills_total: Skills rastreadas por el medidor de drift.
        skills_retired: Skills retiradas por ``sweep`` (retiro por outcome).
        skills_at_risk: Skills por encima del cap activo (pasan a revision).
        consistency_score: Fraccion de tareas "stable" (``None`` sin medidor).
        lift_harmful: Skills con lift negativo (``None`` sin medidor).
        generated_at: Marca temporal ISO-8601 (UTC) del snapshot.
        verdict: Veredicto agregado ``healthy`` | ``degraded`` | ``unhealthy``.
    """

    token_hit_rate: float
    token_gate_ok: bool
    skills_total: int
    skills_retired: int
    skills_at_risk: int
    consistency_score: float | None
    lift_harmful: int | None
    generated_at: str
    verdict: HealthVerdict


class HarnessHealthReporter:
    """Agrega los medidores del harness en un panel de salud con gates.

    Attributes:
        _telemetry: Medidor de tokens (``TokenTelemetry``-like) o ``None``.
        _drift: Medidor de drift (``LibraryDriftManager``-like) o ``None``.
        _consistency: Reporte de consistencia (mapping) o ``None``.
        _lift_report: Reporte de skill lift (mapping) o ``None``.
        _thresholds: Umbrales de los gates (DI).
    """

    def __init__(
        self,
        *,
        telemetry: object | None = None,
        drift: object | None = None,
        consistency: Mapping[str, float] | None = None,
        lift_report: Mapping[str, int] | None = None,
        thresholds: HealthThresholds | None = None,
    ) -> None:
        """Inicializa el reporter con los medidores inyectados (DI, kw-only).

        Args:
            telemetry: Medidor con ``hit_rate() -> float`` (p. ej.
                ``TokenTelemetry``). ``None`` => ``token_hit_rate`` 0.0.
            drift: Medidor con ``report() -> dict`` (p. ej.
                ``LibraryDriftManager``). ``None`` => conteos en 0.
            consistency: Reporte de ``ConsistencyEvaluator.report`` (mapping con
                ``consistency_score``) o ``None``.
            lift_report: Reporte de ``SkillLiftEvaluator.report`` (mapping con
                ``harmful``) o ``None``.
            thresholds: Umbrales de los gates; default ``HealthThresholds()``.
        """
        self._telemetry = telemetry
        self._drift = drift
        self._consistency = consistency
        self._lift_report = lift_report
        self._thresholds = thresholds if thresholds is not None else HealthThresholds()

    # ------------------------------------------------------------------
    # API publica
    # ------------------------------------------------------------------

    def collect(self) -> HarnessHealth:
        """Reune las metricas de cada medidor en un snapshot de salud.

        WHAT: consulta cada medidor inyectado (None-safe) y calcula el veredicto
        con los gates. WHY: un unico objeto agregado es la fuente de verdad del
        panel (evita recomputar y divergir). WHERE: ``report``/``summary_markdown``.

        Returns:
            El ``HarnessHealth`` inmutable con el veredicto ya calculado.
        """
        token_hit_rate, token_gate_ok = self._collect_token()
        skills_total, skills_retired, skills_at_risk = self._collect_drift()
        consistency_score = self._collect_consistency()
        lift_harmful = self._collect_lift()

        draft = HarnessHealth(
            token_hit_rate=token_hit_rate,
            token_gate_ok=token_gate_ok,
            skills_total=skills_total,
            skills_retired=skills_retired,
            skills_at_risk=skills_at_risk,
            consistency_score=consistency_score,
            lift_harmful=lift_harmful,
            generated_at=datetime.now(UTC).isoformat(),
            verdict="healthy",
        )
        return HarnessHealth(
            **{**asdict(draft), "verdict": self._verdict_from(self._failures(draft))}
        )

    def verdict(self) -> HealthVerdict:
        """Calcula y devuelve el veredicto agregado actual.

        Returns:
            ``"healthy"``, ``"degraded"`` o ``"unhealthy"``.
        """
        return self.collect().verdict

    def report(self) -> dict:
        """Genera el reporte serializable del panel (salud + umbrales + fallos).

        Returns:
            Dict con los campos de ``HarnessHealth``, los ``thresholds``
            aplicados y la lista de ``failures`` (nombres de gates fallidos).
        """
        health = self.collect()
        payload = asdict(health)
        payload["thresholds"] = asdict(self._thresholds)
        payload["failures"] = self._failures(health)
        return payload

    def to_json(self, path: Path) -> bool:
        """Persiste el reporte a JSON (best-effort, no falla el flujo).

        Args:
            path: Ruta destino (se crean los directorios padre si faltan).

        Returns:
            ``True`` si se escribio correctamente; ``False`` ante ``OSError``
            (se emite un warning, sin except silencioso).
        """
        payload = {"version": SCHEMA_VERSION, **self.report()}
        try:
            destination = Path(path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return True
        except OSError as exc:
            logger.warning(
                "WHAT: no se pudo persistir el panel de salud en %s. "
                "WHY: %s. WHERE: HarnessHealthReporter.to_json",
                path,
                exc,
            )
            return False

    def summary_markdown(self) -> str:
        """Renderiza el panel legible en Markdown (para PR/CI step summary).

        Returns:
            Cadena Markdown con el veredicto y una tabla de metricas/gates.
        """
        health = self.collect()
        failures = self._failures(health)
        failures_text = ", ".join(failures) if failures else "ninguno"
        consistency = (
            f"{health.consistency_score:.2f}"
            if health.consistency_score is not None
            else "N/A"
        )
        lift_harmful = (
            str(health.lift_harmful) if health.lift_harmful is not None else "N/A"
        )
        rows = [
            ("token_hit_rate", f"{health.token_hit_rate:.2f}"),
            ("token_gate_ok", str(health.token_gate_ok)),
            ("skills_total", str(health.skills_total)),
            ("skills_retired", str(health.skills_retired)),
            ("skills_at_risk", str(health.skills_at_risk)),
            ("consistency_score", consistency),
            ("lift_harmful", lift_harmful),
            ("generated_at", health.generated_at),
            ("verdict", health.verdict),
        ]
        table = "\n".join(f"| {name} | {value} |" for name, value in rows)
        return (
            "# Harness Health\n\n"
            f"**verdict: {health.verdict}** (gates fallidos: {failures_text})\n\n"
            "| metrica | valor |\n"
            "| --- | --- |\n"
            f"{table}\n"
        )

    # ------------------------------------------------------------------
    # Recoleccion None-safe
    # ------------------------------------------------------------------

    def _collect_token(self) -> tuple[float, bool]:
        """Recolecta el acierto de cache y evalua el gate token.

        Returns:
            Tupla ``(hit_rate, gate_ok)``; ``(0.0, False)`` sin telemetria.
        """
        if self._telemetry is None:
            return 0.0, False
        rate = float(self._telemetry.hit_rate())  # type: ignore[attr-defined]
        return rate, rate >= self._thresholds.min_token_hit_rate

    def _collect_drift(self) -> tuple[int, int, int]:
        """Recolecta el resumen del medidor de drift.

        Returns:
            Tupla ``(total, retired, at_risk)``; ceros sin medidor.
        """
        if self._drift is None:
            return 0, 0, 0
        summary = self._drift.report()  # type: ignore[attr-defined]
        total = int(summary.get("total", 0))
        retired = int(summary.get("retired", 0))
        at_risk = next(
            (int(summary[key]) for key in _AT_RISK_KEYS if key in summary), 0
        )
        return total, retired, at_risk

    def _collect_consistency(self) -> float | None:
        """Recolecta el ``consistency_score`` del reporte (o ``None``).

        Returns:
            El score como ``float``, o ``None`` sin medidor/clave.
        """
        if self._consistency is None:
            return None
        score = self._consistency.get(_CONSISTENCY_SCORE_KEY)
        return float(score) if score is not None else None

    def _collect_lift(self) -> int | None:
        """Recolecta el conteo de skills daninas del reporte de lift (o None).

        Returns:
            El conteo como ``int``, o ``None`` sin medidor/clave.
        """
        if self._lift_report is None:
            return None
        harmful = self._lift_report.get(_HARMFUL_KEY)
        return int(harmful) if harmful is not None else None

    # ------------------------------------------------------------------
    # Gates y veredicto
    # ------------------------------------------------------------------

    def _failures(self, health: HarnessHealth) -> list[str]:
        """Enumera los gates fallidos del snapshot.

        WHAT: aplica los 3 gates (token, harmful, consistency). Un medidor
        ausente (consistency/lift) NO se evalua y por tanto no falla. WHY:
        centralizar la logica de gates evita divergencia entre ``report`` y
        ``summary_markdown``. WHERE: ``collect``/``report``/``summary_markdown``.

        Args:
            health: Snapshot recolectado a evaluar.

        Returns:
            Lista de nombres de gate fallidos (vacia si todos pasan).
        """
        failures: list[str] = []
        if not health.token_gate_ok:
            failures.append("token")
        harmful = health.lift_harmful or 0
        if harmful > self._thresholds.max_harmful_skills:
            failures.append("harmful")
        if (
            health.consistency_score is not None
            and health.consistency_score < self._thresholds.min_consistency_score
        ):
            failures.append("consistency")
        return failures

    def _verdict_from(self, failures: list[str]) -> HealthVerdict:
        """Deriva el veredicto a partir de los gates fallidos.

        Args:
            failures: Nombres de gates fallidos.

        Returns:
            ``"unhealthy"`` si falla ``harmful`` o hay >= 2 fallos;
            ``"degraded"`` si falla exactamente 1; ``"healthy"`` si ninguno.
        """
        if "harmful" in failures or len(failures) >= 2:
            return "unhealthy"
        if len(failures) == 1:
            return "degraded"
        return "healthy"


__all__ = [
    "ENV_MAX_HARMFUL_SKILLS",
    "ENV_MIN_CONSISTENCY_SCORE",
    "ENV_MIN_TOKEN_HIT_RATE",
    "MAX_HARMFUL_SKILLS",
    "MIN_CONSISTENCY_SCORE",
    "MIN_TOKEN_HIT_RATE",
    "SCHEMA_VERSION",
    "HarnessHealth",
    "HarnessHealthReporter",
    "HealthThresholds",
    "HealthVerdict",
]
