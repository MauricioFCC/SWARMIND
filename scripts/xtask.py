"""xtask — política única de calidad, seguridad y buenas prácticas de SWARMIND.

WHAT: un solo comando evalúa TODAS las políticas del repo (lint, dead code,
arquitectura, complejidad, ratchets, PEP 649, docs, workflows, skills,
seguridad y tests) con tabla PASS/FAIL/SKIP y salida 0/1/2. La deuda técnica
queda en 0 **por política**: cada trinquete solo puede bajar.

WHY: los gates vivían dispersos en pre-commit, CI y scripts sueltos; nada
impedía olvidar uno. Medido 2026-11-10: de 12 políticas, el pre-commit solo
ejecutaba 4 y CI duplicaba comandos sin una SSOT. Con `xtask` el conjunto es
datos versionados (`POLICY`) y cualquier gate nuevo entra por el mismo camino.

WHERE: ``scripts/xtask.py`` (esta política) + pre-commit
(``harness/scripts/install_hooks.py``) + ``.github/workflows/ci.yml``.

Uso:
    python scripts/xtask.py check            # TODAS las políticas (incluye tests)
    python scripts/xtask.py gate             # gates + trinquetes + seguridad
    python scripts/xtask.py gate --fast      # subconjunto pre-commit (<90 s)
    python scripts/xtask.py gate --with-tests
    python scripts/xtask.py ratchet          # solo trinquetes (decrease-only)
    python scripts/xtask.py check --json     # salida máquina
    --only id1,id2 / --skip id1,id2          # selección fina

Exit: 0 = todo PASS (o SKIP justificado); 1 = algún FAIL; 2 = política inválida.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Marcador reemplazado por ``sys.executable`` al ejecutar.
PY = "{py}"

KINDS: frozenset[str] = frozenset({"gate", "ratchet", "security"})
MODES: frozenset[str] = frozenset({"check", "gate", "ratchet"})


@dataclass(frozen=True)
class Gate:
    """Política atómica: un comando que debe salir 0.

    Args:
        id: Identificador único y estable (usado por ``--only``/``--skip``).
        kind: ``gate`` (calidad), ``ratchet`` (solo puede bajar) o ``security``.
        cmd: Argumentos; ``{py}`` se sustituye por el intérprete actual.
        fast: True si pertenece al subconjunto de pre-commit (<90 s).
        timeout: Segundos máximos antes de FAIL.
        why: Motivo/alcance de la política (se muestra al fallar).
    """

    id: str
    kind: str
    cmd: tuple[str, ...]
    fast: bool
    timeout: int
    why: str


POLICY: tuple[Gate, ...] = (
    Gate(
        "ruff", "gate",
        (PY, "-m", "ruff", "check", "harness", "scripts"),
        True, 300,
        "lint y buenas prácticas (0 hallazgos)",
    ),
    Gate(
        "ruff-preview", "ratchet",
        (PY, "scripts/check_ruff_preview.py", "--gate"),
        True, 600,
        "reglas preview allowlisted no reaparecen",
    ),
    Gate(
        "ruff-ratchet", "ratchet",
        (PY, "scripts/check_ruff_ratchet.py", "--gate"),
        True, 600,
        "PERF/FURB/RUF nunca suben sobre el baseline",
    ),
    Gate(
        "arquitectura", "ratchet",
        (PY, "scripts/check_architecture.py", "--gate", "--ratchet"),
        True, 600,
        "capas, ciclos e imports prohibidos + deuda F3/F5",
    ),
    Gate(
        "complejidad", "ratchet",
        (PY, "scripts/check_complexity.py", "--gate"),
        True, 600,
        "complejidad ciclomática/cognitiva no sube",
    ),
    Gate(
        "pep649", "ratchet",
        (PY, "scripts/audit_pep649.py", "--gate"),
        True, 300,
        "anotaciones perezosas (PEP 649) sin usos nuevos",
    ),
    Gate(
        "docs-links", "gate",
        (PY, "scripts/check_docs_links.py"),
        True, 300,
        "enlaces internos de la documentación vivos",
    ),
    Gate(
        "docs-index", "gate",
        (PY, "scripts/gen_docs_index.py", "--check"),
        True, 300,
        "índices de documentación generados y sin drift",
    ),
    Gate(
        "workflows", "gate",
        (PY, "scripts/check_workflows.py"),
        True, 300,
        "GitHub Actions válidos y sin comandos inseguros",
    ),
    Gate(
        "skills", "gate",
        (PY, "scripts/validate_skills.py", "--strict", "--quiet"),
        True, 300,
        "frontmatter, SKILL.min.md, registry y referencias",
    ),
    Gate(
        "skills-standard", "gate",
        (PY, "scripts/check_skills_standard.py"),
        True, 300,
        "conformidad Agent Skills L1 (agentskills.io / AAIF)",
    ),
    Gate(
        "skills-spec", "gate",
        (PY, "scripts/generate_skill_specs.py", "--check"),
        True, 300,
        "contratos SDD de skills sin drift (source_sha256)",
    ),
    Gate(
        "vulture", "gate",
        (PY, "-m", "vulture", "harness", "harness/vulture_whitelist.py"),
        False, 600,
        "0 código muerto",
    ),
    Gate(
        "security", "security",
        (PY, "scripts/security_scan.py", "--quiet"),
        False, 900,
        "0 rutas no portables, $HOME literal, secretos o .env trackeados",
    ),
    Gate(
        "tests", "gate",
        (PY, "-m", "pytest", "harness/tests", "-q", "-x"),
        False, 3600,
        "suite completa sin fallos",
    ),
)


@dataclass(frozen=True)
class Result:
    """Resultado de una política (inmutable para tablas/JSON)."""

    id: str
    kind: str
    status: str
    seconds: float
    detail: str = ""


def validate_policy(policy: tuple[Gate, ...] = POLICY) -> list[str]:
    """Comprueba que la política sea ejecutable (ids únicos, scripts reales).

    Args:
        policy: Conjunto de políticas a validar.

    Returns:
        Lista de errores (vacía = política válida).
    """
    errores: list[str] = []
    vistos: set[str] = set()
    for gate in policy:
        if gate.id in vistos:
            errores.append(f"id duplicado: {gate.id}")
        vistos.add(gate.id)
        if gate.kind not in KINDS:
            errores.append(f"{gate.id}: kind inválido '{gate.kind}'")
        if not gate.cmd:
            errores.append(f"{gate.id}: cmd vacío")
        errores.extend(
            f"{gate.id}: no existe {parte}"
            for parte in gate.cmd
            if parte.startswith("scripts/") and not (ROOT / parte).is_file()
        )
    return errores


def select(
    policy: tuple[Gate, ...],
    mode: str,
    fast: bool = False,
    with_tests: bool = False,
    only: frozenset[str] = frozenset(),
    skip: frozenset[str] = frozenset(),
) -> list[Gate]:
    """Selecciona las políticas aplicables al modo y filtros.

    Args:
        policy: Política completa.
        mode: ``check`` (todas), ``gate`` (sin tests por defecto) o ``ratchet``.
        fast: True si solo el subconjunto de pre-commit.
        with_tests: Incluye ``tests`` en modo ``gate``.
        only: Ids a ejecutar (si no está vacío, manda sobre el resto).
        skip: Ids a excluir.

    Returns:
        Lista ordenada de políticas a ejecutar.
    """
    elegidas = [
        g for g in policy
        if (mode == "check" or g.id != "tests" or with_tests)
        and (mode != "ratchet" or g.kind == "ratchet")
        and (not fast or g.fast)
    ]
    if only:
        elegidas = [g for g in elegidas if g.id in only]
    return [g for g in elegidas if g.id not in skip]


def _command(gate: Gate) -> list[str]:
    """Sustituye ``{py}`` por el intérprete actual."""
    return [sys.executable if p == PY else p for p in gate.cmd]


def run_gate(gate: Gate) -> Result:
    """Ejecuta una política y clasifica PASS/FAIL/SKIP (nunca lanza).

    SKIP solo cuando falta una herramienta externa (código 127 o
    ``No module named``): una política del repo ausente es FAIL.

    Args:
        gate: Política a ejecutar.

    Returns:
        Resultado con estado y últimas líneas de salida si falla.
    """
    inicio = time.monotonic()
    try:
        proc = subprocess.run(
            _command(gate),
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=gate.timeout,
        )
    except subprocess.TimeoutExpired:
        return Result(gate.id, gate.kind, "FAIL", time.monotonic() - inicio,
                      f"timeout tras {gate.timeout}s")
    except OSError as exc:
        return Result(gate.id, gate.kind, "SKIP", time.monotonic() - inicio, str(exc))
    segundos = time.monotonic() - inicio
    if proc.returncode == 0:
        return Result(gate.id, gate.kind, "PASS", segundos)
    salida = (proc.stderr or proc.stdout or "").strip()
    if proc.returncode == 127 or "No module named" in salida:
        return Result(gate.id, gate.kind, "SKIP", segundos, salida.splitlines()[-1][:160] if salida else "")
    return Result(gate.id, gate.kind, "FAIL", segundos, _tail(salida))


def _tail(texto: str, lines: int = 12) -> str:
    """Últimas ``lines`` líneas de una salida (para no inundar la consola)."""
    return "\n".join(texto.splitlines()[-lines:])


def run_all(gates: list[Gate]) -> list[Result]:
    """Ejecuta las políticas en orden y devuelve sus resultados."""
    return [run_gate(g) for g in gates]


def _print_table(results: list[Result]) -> None:
    """Imprime la tabla PASS/FAIL/SKIP con duración."""
    print("=" * 72)
    print(f"  XTASK — política de calidad ({len(results)} gates)")
    print("=" * 72)
    for r in results:
        print(f"  {r.status:<4} {r.id:<14} {r.kind:<9} {r.seconds:6.1f}s")
    print("=" * 72)
    for r in results:
        if r.status == "FAIL":
            print(f"\n[FAIL] {r.id} — {r.detail}")


def summarize(results: list[Result]) -> dict:
    """Resumen máquina (para ``--json`` y CI)."""
    cuenta = {"PASS": 0, "FAIL": 0, "SKIP": 0}
    for r in results:
        cuenta[r.status] = cuenta.get(r.status, 0) + 1
    return {
        "total": len(results),
        "counts": cuenta,
        "gates": [asdict(r) for r in results],
        "ok": cuenta.get("FAIL", 0) == 0,
    }


def _build_parser() -> argparse.ArgumentParser:
    """Parser CLI de xtask."""
    parser = argparse.ArgumentParser(description="Política de gates y trinquetes SWARMIND")
    parser.add_argument("mode", nargs="?", default="check", choices=sorted(MODES))
    parser.add_argument("--fast", action="store_true", help="Solo el subconjunto de pre-commit")
    parser.add_argument("--with-tests", action="store_true", help="Incluye la suite en 'gate'")
    parser.add_argument("--only", default="", help="Ids separados por coma")
    parser.add_argument("--skip", default="", help="Ids a excluir, separados por coma")
    parser.add_argument("--json", action="store_true", help="Salida JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entrada CLI: valida política, ejecuta y devuelve exit 0/1/2."""
    args = _build_parser().parse_args(argv)
    errores = validate_policy()
    if errores:
        for error in errores:
            print(f"xtask | POLITICA INVALIDA: {error}", file=sys.stderr)
        return 2
    only = frozenset(x for x in args.only.split(",") if x)
    skip = frozenset(x for x in args.skip.split(",") if x)
    gates = select(POLICY, args.mode, args.fast, args.with_tests, only, skip)
    if not gates:
        print("xtask | sin gates que ejecutar (revisa --only/--skip)", file=sys.stderr)
        return 2
    results = run_all(gates)
    if args.json:
        print(json.dumps(summarize(results), indent=2, ensure_ascii=False))
    else:
        _print_table(results)
    return 0 if all(r.status != "FAIL" for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
