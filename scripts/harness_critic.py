"""harness_critic.py — CLI del Harness Critic (Co-Harness, arXiv:2607.22688).

WHAT: lee los fallos reales del ``FailureRegistry`` (``harness/db/failures.jsonl``),
corre ``HarnessCritic.analyze``/``propose`` y emite los DIFTS LOCALES sugeridos
por causa harness-level (prompt ambiguo, schema, skill ausente, middleware,
contexto, guardrail). WHY: el critico existia como modulo pero nada lo invocaba;
este es el disparador operativo del loop de mejora del harness (fase EXPERIMENT).
WHERE: ``uv run python scripts/harness_critic.py [--json] [--component X]``.

IMPORTANTE: el CLI es DRY-RUN por contrato. SOLO propone diffs; NUNCA aplica
cambios sobre el harness, el registry ni ningun archivo.

Uso:
    uv run python scripts/harness_critic.py                 # propone (humano)
    uv run python scripts/harness_critic.py --json          # machine-readable
    uv run python scripts/harness_critic.py --component mcp/filesystem
    uv run python scripts/harness_critic.py --limit 50

Exit codes: 0 = OK (aunque no haya fallos); 1 = error fatal (registry ilegible).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

#: Raiz del repo en sys.path[1] (SEG: nunca index 0) para importar el harness.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(1, str(_ROOT))

from harness.evolve_loop.harness_critic import HarnessCritic, HarnessDiff
from harness.failure_registry.registry import FailureRegistry

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("harness_critic")


def _build_parser() -> argparse.ArgumentParser:
    """Construye el parser de argumentos del CLI.

    Returns:
        Parser con ``--component``, ``--limit`` y ``--json``.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Propone diffs locales del harness a partir de causas de fallo (dry-run)."
        )
    )
    parser.add_argument(
        "--component",
        default="",
        help="componente/archivo afectado (se anexa al change y fija el target)",
    )
    parser.add_argument(
        "--limit", type=int, default=0, help="maximo de fallos a analizar (0 = todos)"
    )
    parser.add_argument(
        "--json", action="store_true", help="salida machine-readable (JSON)"
    )
    return parser


def _diffs_payload(diffs: list[HarnessDiff]) -> list[dict[str, object]]:
    """Serializa los diffs a una lista de dicts JSON-safe.

    Args:
        diffs: Diffs sugeridos por el critico.

    Returns:
        Lista de dicts con categoria, target, change, validacion y confianza.
    """
    return [
        {
            "category": diff.cause.category,
            "target": diff.target,
            "change": diff.change,
            "validated": diff.validated,
            "regression_risk": diff.regression_risk,
            "confidence": diff.cause.confidence,
            "evidence": diff.cause.evidence,
        }
        for diff in diffs
    ]


def _emit(diffs: list[HarnessDiff], *, as_json: bool) -> None:
    """Imprime los diffs sugeridos (humano o JSON).

    Args:
        diffs: Diffs sugeridos por el critico.
        as_json: True para emitir JSON machine-readable.
    """
    if as_json:
        payload = {
            "dry_run": True,
            "count": len(diffs),
            "diffs": _diffs_payload(diffs),
        }
        print(json.dumps(payload, ensure_ascii=False))
        return

    print(f"[DRY-RUN] Diffs sugeridos (solo propuesta, NO se aplica): {len(diffs)}")
    for diff in diffs:
        print(f"  - [{diff.cause.category}] target={diff.target}")
        print(f"    change: {diff.change}")
        print(f"    evidence: {diff.cause.evidence} (conf={diff.cause.confidence:.2f})")


def main(
    argv: list[str] | None = None,
    *,
    critic: HarnessCritic | None = None,
    registry: FailureRegistry | None = None,
) -> int:
    """CLI entry point: propone diffs locales del harness (dry-run).

    Args:
        argv: Argumentos (None = ``sys.argv[1:]``).
        critic: Critico inyectable (DI para tests); None usa ``HarnessCritic()``.
        registry: Registry inyectable (DI para tests); None usa el real.

    Returns:
        Exit code: 0 exito (aunque no haya fallos); 1 error fatal.
    """
    args = _build_parser().parse_args(argv)
    critic = critic if critic is not None else HarnessCritic()

    try:
        registry = registry if registry is not None else FailureRegistry()
        messages = [record.error_msg for record in registry.get_all()]
        if args.limit > 0:
            messages = messages[: args.limit]
        diffs = critic.propose(messages, component=args.component)
        _emit(diffs, as_json=args.json)
        return 0
    except Exception as exc:  # noqa: BLE001 — error fatal: el CLI debe reportarlo
        logger.error(
            "Harness Critic abortado: %s | WHY: registry inaccesible o corrupto | "
            "WHERE: scripts/harness_critic.py,main",
            exc,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
