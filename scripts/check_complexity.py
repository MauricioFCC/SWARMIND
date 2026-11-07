"""Gate de complejidad algorítmica por escalas (N, 2N, 4N).

Mide funciones **puras** del harness con tiempo de pared (mínimo de varias
repeticiones: el ruido solo puede añadir tiempo) y calcula el ratio efectivo
por duplicación de tamaño:

    ratio_efectivo = (t(4N) / t(N)) ** (1 / 2)

Interpretación (con margen de ruido):

    linear     ~2.0        (ratio <= 2.8)
    n_log_n    ~2.2        (ratio <= 3.2)
    quadratic  ~4.0        (ratio > 3.2)

Un benchmark declarado lineal que supera su umbral es un hotspot
superlineal: el gate falla y debe refactorizarse (spec
``docs/specs/o-n-2-hotspots-gate.md``).

Uso:

    python scripts/check_complexity.py            # mide y reporta
    python scripts/check_complexity.py --gate     # falla si hay regresión
    python scripts/check_complexity.py --json     # salida para CI
    python scripts/check_complexity.py --write-baseline

El baseline guarda **ratios** (adimensionales, independientes de la máquina),
no tiempos absolutos; así el gate es portable entre local y CI.
"""

from __future__ import annotations

import argparse
import gc
import json
import math
import statistics
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.complexity_benchmarks import BENCHMARKS, SCALES

BASELINE_PATH = Path(__file__).with_name("complexity_baseline.json")

#: Ratio máximo admisible por duplicación, según la clase declarada. El margen
#: absorbe efectos de caché del intérprete y ruido de CI: el gate apunta a
#: hotspots O(n²) (ratio ~4), no a microdiferencias de constante.
THRESHOLDS: dict[str, float] = {
    "linear": 2.8,
    "n_log_n": 3.2,
    "quadratic": 5.0,
}

#: Margen admitido frente al ratio del baseline (ruido de máquina/CI).
BASELINE_ALLOWANCE = 1.35
#: Piso del ratchet: por debajo de este ratio el ruido domina y el baseline no
#: aporta señal (el umbral absoluto ya cubre la clase declarada).
RATCHET_FLOOR_RATIO = 0.9


def _measure(benchmark: Any, scale: int, reps: int) -> float:
    """Tiempo mínimo de pared (s) de ``reps`` ejecuciones de un benchmark.

    Se usa el **mínimo** (no la mediana) porque el ruido del scheduler, del
    recolector y de otros procesos solo puede *añadir* tiempo: el mínimo es el
    estimador menos sesgado para microbenchmarks de CPU (misma doctrina que
    ``timeit.repeat``).

    Args:
        benchmark: Callable ``(n) -> Any`` con coste declarado.
        scale: Tamaño de entrada ``n``.
        reps: Número de repeticiones (mínimo 1).

    Returns:
        Tiempo mínimo en segundos (``float``).
    """
    samples: list[float] = []
    gc_was_enabled = gc.isenabled()
    # El recolector introduce pausas que distorsionan la escala grande y
    # producen ratios fantasma; se desactiva solo durante la medición.
    gc.disable()
    try:
        for _ in range(max(1, reps)):
            started = time.perf_counter()
            benchmark(scale)
            samples.append(time.perf_counter() - started)
    finally:
        if gc_was_enabled:
            gc.enable()
    return min(samples)


def _effective_ratio(times: list[float]) -> float:
    """Ratio efectivo por duplicación a partir de los tiempos por escala.

    Args:
        times: Tiempos medidos en las escalas de ``SCALES`` (al menos 2).

    Returns:
        ``(t_ultimo / t_primero) ** (1 / duplicaciones)``; ``inf`` si el
        primer tiempo es cero.
    """
    first, last = times[0], times[-1]
    if first <= 0.0:
        return math.inf
    doublings = math.log2(SCALES[-1] / SCALES[0])
    if doublings <= 0.0:
        return 1.0
    return (last / first) ** (1.0 / doublings)


def _median_measurement(
    measurements: list[tuple[list[float], float]],
) -> tuple[list[float], float]:
    """Selecciona la medición cuyo ratio es la mediana (soporta nº par).

    Args:
        measurements: Pares ``(tiempos_por_escala, ratio)`` de cada ronda.

    Returns:
        El par más cercano al ratio mediano (nunca falla con rondas pares,
        donde ``statistics.median`` promedia dos valores).
    """
    median = statistics.median([ratio for _, ratio in measurements])
    return min(measurements, key=lambda item: abs(item[1] - median))


def run_all(reps: int = 5, rounds: int = 2) -> dict[str, dict[str, Any]]:
    """Mide todos los benchmarks y los clasifica.

    El ratio de cada benchmark es la **mediana de ``rounds`` mediciones
    independientes** (cada una con mínimo de ``reps`` muestras por escala):
    así un pico aislado del sistema no decide el veredicto del gate.

    Args:
        reps: Repeticiones por escala dentro de una ronda (mínimo 1).
        rounds: Rondas independientes por benchmark (mínimo 1).

    Returns:
        Mapa ``nombre -> {expected, times, ratio, threshold, ok}``.
    """
    results: dict[str, dict[str, Any]] = {}
    for name, (benchmark, expected) in BENCHMARKS.items():
        # Calentamiento: una pasada a escala reducida para pagar imports/JIT
        # de CPython antes de medir (evita inflar el primer tiempo).
        _measure(benchmark, max(1, SCALES[0] // 10), reps=1)
        measurements: list[tuple[list[float], float]] = []
        for _ in range(max(1, rounds)):
            times = [_measure(benchmark, scale, reps) for scale in SCALES]
            measurements.append((times, _effective_ratio(times)))
        times, ratio = _median_measurement(measurements)
        threshold = THRESHOLDS.get(expected, THRESHOLDS["linear"])
        results[name] = {
            "expected": expected,
            "times": [round(value, 6) for value in times],
            "ratio": round(ratio, 3),
            "threshold": threshold,
            "ok": ratio <= threshold,
        }
    return results


def load_baseline() -> dict[str, dict[str, Any]]:
    """Lee el baseline versionado (vacío si no existe o está corrupto).

    Returns:
        Mapa ``nombre -> entrada de baseline``.
    """
    if not BASELINE_PATH.exists():
        return {}
    try:
        data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"WARN baseline ilegible: {type(exc).__name__}: {exc}", file=sys.stderr)
        return {}
    benchmarks = data.get("benchmarks", data)
    return benchmarks if isinstance(benchmarks, dict) else {}


def write_baseline(results: dict[str, dict[str, Any]]) -> None:
    """Escribe el baseline con los ratios actuales (ratchet).

    Args:
        results: Salida de :func:`run_all`.
    """
    payload = {
        "version": 1,
        "scales": list(SCALES),
        "thresholds": THRESHOLDS,
        "benchmarks": {
            name: {
                "expected": entry["expected"],
                "ratio": entry["ratio"],
                "threshold": entry["threshold"],
            }
            for name, entry in results.items()
        },
    }
    BASELINE_PATH.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"baseline escrito: {BASELINE_PATH} ({len(results)} benchmarks)")


def evaluate(
    results: dict[str, dict[str, Any]], baseline: dict[str, dict[str, Any]]
) -> list[str]:
    """Aplica umbral absoluto y ratchet contra el baseline.

    Args:
        results: Salida de :func:`run_all`.
        baseline: Baseline cargado (puede estar vacío).

    Returns:
        Lista de fallos legibles (vacía si todo pasa).
    """
    failures: list[str] = []
    for name, entry in results.items():
        if not entry["ok"]:
            failures.append(
                f"{name}: ratio={entry['ratio']} > umbral={entry['threshold']} "
                f"(esperado {entry['expected']})"
            )
            continue
        allowed = baseline.get(name, {}).get("ratio")
        if allowed is None:
            continue
        limit = round(
            max(
                float(allowed) * BASELINE_ALLOWANCE,
                entry["threshold"] * RATCHET_FLOOR_RATIO,
            ),
            3,
        )
        if entry["ratio"] > limit:
            failures.append(
                f"{name}: regresión vs baseline ratio={entry['ratio']} > {limit} "
                f"(baseline={allowed})"
            )
    return failures


def _print_table(results: dict[str, dict[str, Any]]) -> None:
    """Imprime la tabla de resultados por benchmark."""
    print(f"{'benchmark':<26} {'clase':<10} {'ratio':>7} {'umbral':>7}  estado")
    for name, entry in results.items():
        state = "OK" if entry["ok"] else "FAIL"
        print(
            f"{name:<26} {entry['expected']:<10} {entry['ratio']:>7} "
            f"{entry['threshold']:>7}  {state}"
        )


def main(argv: list[str] | None = None) -> int:
    """Entrypoint del gate.

    Args:
        argv: Argumentos CLI (``None`` usa ``sys.argv``).

    Returns:
        Exit code (0 = OK, 1 = regresión/hotspot).
    """
    parser = argparse.ArgumentParser(description="Gate de complejidad O(n)")
    parser.add_argument("--gate", action="store_true", help="falla si hay regresión")
    parser.add_argument("--json", action="store_true", help="salida JSON")
    parser.add_argument(
        "--write-baseline", action="store_true", help="escribe el baseline actual"
    )
    parser.add_argument(
        "--reps", type=int, default=5, help="repeticiones por escala (default 5)"
    )
    args = parser.parse_args(argv)

    results = run_all(reps=args.reps)
    # Al escribir baseline se ignora el ratchet previo: solo cuenta el umbral.
    failures = evaluate(results, {})
    if args.write_baseline and failures:
        print(
            "baseline NO escrito: hay hotspots fuera de umbral (corrige antes de fijar ratios)",
            file=sys.stderr,
        )
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    if args.write_baseline:
        write_baseline(results)

    ratchet_failures = evaluate(results, load_baseline())
    failures = ratchet_failures or failures

    if args.json:
        print(
            json.dumps(
                {"benchmarks": results, "failures": failures, "ok": not failures},
                indent=2,
                sort_keys=True,
            )
        )
    else:
        _print_table(results)

    if failures and args.gate:
        print("\nGATE COMPLEJIDAD: FAIL", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
