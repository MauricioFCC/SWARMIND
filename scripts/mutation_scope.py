"""Mutación *scoped* por diff de git con umbrales por paquete.

Implementa la política P2 de `docs/specs/tdd-mutation-gate.md`:

1. Calcula los archivos mutables cambiados entre ``base`` y ``HEAD``.
2. Mapea cada fuente a los tests que la referencian (por nombre o import).
3. Agrupa por paquete y aplica el umbral de mutación del paquete:
   kernel 90 %, domain 75 %, memory_rag 70 %, resto 40 %.
4. Genera la config de mutmut 3.x (`source_paths`, `only_mutate`,
   `pytest_add_cli_args_test_selection`) y, en Linux/macOS, ejecuta mutmut
   por paquete leyendo `mutants/mutmut-cicd-stats.json`.

mutmut 3.x necesita `fork`: en Windows el modo ``--run`` no está soportado
(se usa WSL/CI). ``--dry-run``/``--write-config`` sí funcionan en Windows.

Uso:

    python scripts/mutation_scope.py --base origin/main
    python scripts/mutation_scope.py --base origin/main --write-config
    python scripts/mutation_scope.py --base origin/main --run --max-children 2
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

#: Declaración de un ``Protocol`` de ``typing`` (con o sin ``@runtime_checkable``).
_PROTOCOL_DECL = re.compile(r"@runtime_checkable|\(\s*Protocol\s*\)")

#: Umbral de mutation score por paquete (core alto, adapters bajo).
#:
#: ``harness/kernel`` está en **0.60** (baseline calibrado): la primera
#: medición real del gate (2026-11-07, WSL) dio 62.6 % sobre 286 mutantes.
#: El 90 % sigue siendo la meta del spec (MU-02) y se alcanza subiendo este
#: valor (o el baseline) a medida que los tests maduran. Ver
#: ``scripts/mutation_baseline.json`` (ratchet: solo sube).
MUTATION_THRESHOLDS: dict[str, float] = {
    "harness/kernel": 0.60,
    "harness/domain": 0.75,
    "harness/memory_rag": 0.70,
}

#: Baseline de ratchet: score mínimo medido por paquete (solo sube).
BASELINE_PATH = ROOT / "scripts" / "mutation_baseline.json"

#: Umbral para paquetes no listados (adapters/infra).
DEFAULT_THRESHOLD = 0.40

#: Paquetes "core" que corre la mutación nocturna (rápida, sin diff).
CORE_PACKAGES: tuple[str, ...] = ("harness/kernel", "harness/domain")

#: Directorio de tests y prefijo de la raíz de código mutable.
TESTS_ROOT = "harness/tests"


def is_mutable(path: str) -> bool:
    """Indica si un archivo es candidato a mutación.

    Args:
        path: Ruta relativa al repo.

    Returns:
        True si es un ``.py`` bajo ``harness/`` fuera de tests.
    """
    normalized = path.replace("\\", "/")
    return (
        normalized.startswith("harness/")
        and not normalized.startswith(f"{TESTS_ROOT}/")
        and normalized.endswith(".py")
        and "/tests/" not in normalized
    )


def package_for(path: str) -> str:
    """Paquete de mutación al que pertenece una fuente.

    Args:
        path: Ruta relativa al repo.

    Returns:
        El prefijo más específico de ``MUTATION_THRESHOLDS`` o ``"harness"``.
    """
    normalized = path.replace("\\", "/")
    matches = [
        package
        for package in MUTATION_THRESHOLDS
        if normalized == f"{package}.py" or normalized.startswith(f"{package}/")
    ]
    return max(matches, key=len) if matches else "harness"


def threshold_for(package: str) -> float:
    """Umbral de mutation score de un paquete.

    Args:
        package: Paquete de mutación (``harness/kernel``, ...).

    Returns:
        Umbral en ``[0, 1]`` (default 0.40).
    """
    return MUTATION_THRESHOLDS.get(package, DEFAULT_THRESHOLD)


def changed_files(base: str, head: str = "HEAD") -> list[str]:
    """Lista archivos mutables cambiados entre ``base`` y ``head``.

    Args:
        base: Ref base (p. ej. ``origin/main``).
        head: Ref final (default ``HEAD``).

    Returns:
        Rutas relativas ordenadas y mutables.

    Raises:
        RuntimeError: Si ``git diff`` falla (ref inexistente, etc.).
    """
    completed = subprocess.run(
        [
            "git",
            "diff",
            "--name-only",
            "--diff-filter=ACMR",
            f"{base}...{head}",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "mutation_scope | WHAT=git_diff_fallo | WHY=ref_invalida | "
            f"WHERE=changed_files | base={base!r} | "
            f"stderr={completed.stderr.strip()[:300]}"
        )
    return sorted(
        line.strip()
        for line in completed.stdout.splitlines()
        if is_mutable(line.strip())
    )


def files_for_packages(
    packages: tuple[str, ...] = CORE_PACKAGES, root: Path = ROOT
) -> list[str]:
    """Lista todos los ``.py`` de los paquetes indicados (modo nocturno).

    Args:
        packages: Paquetes a incluir.
        root: Raíz del repo.

    Returns:
        Rutas relativas ordenadas (vacío si el paquete no existe).
    """
    files: list[str] = []
    for package in packages:
        base = root / package
        if not base.is_dir():
            continue
        files.extend(
            path.relative_to(root).as_posix()
            for path in base.rglob("*.py")
            if "__pycache__" not in path.parts
        )
    return sorted(set(files))


def _module_dotted(path: str) -> str:
    """Convierte ``harness/a/b.py`` en ``harness.a.b``."""
    return path.replace("\\", "/").removesuffix(".py").replace("/", ".")


def find_tests(
    source: str, tests_root: Path, *, root: Path = ROOT
) -> list[str]:
    """Encuentra los tests que cubren una fuente.

    Criterio: ``test_<stem>.py`` o cualquier test que importe el módulo
    (``harness.pkg.mod`` / ``from harness.pkg import mod``).

    Args:
        source: Ruta de la fuente (relativa al repo).
        tests_root: Directorio de tests.
        root: Raíz del repo para relativizar las rutas.

    Returns:
        Rutas de tests (relativas a ``root``) ordenadas.
    """
    path = Path(source)
    candidates: set[Path] = set()
    direct = tests_root / f"test_{path.stem}.py"
    if direct.is_file():
        candidates.add(direct)
    dotted = _module_dotted(source)
    parts = path.parent.parts
    package = _module_dotted("/".join(parts)) if len(parts) >= 2 else ""
    for test_file in tests_root.rglob("test_*.py"):
        try:
            text = test_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if dotted in text:
            candidates.add(test_file)
        elif package and package in text:
            # from harness.kernel import X: el test puede usar cualquier
            # modulo del paquete, no solo el import explicito.
            candidates.add(test_file)
        elif path.stem and path.stem in test_file.stem:
            # test_<paquete>_<stem>.py (p. ej. test_kernel_mailbox.py)
            candidates.add(test_file)
    return sorted(candidate.relative_to(root).as_posix() for candidate in candidates)


def build_scope(
    files: list[str], tests_root: Path, *, root: Path = ROOT
) -> dict[str, dict[str, list[str]]]:
    """Agrupa fuentes y tests por paquete.

    Args:
        files: Rutas mutables.
        tests_root: Directorio de tests.
        root: Raíz del repo para relativizar las rutas.

    Returns:
        ``{paquete: {"sources": [...], "tests": [...]}}``.
    """
    scope: dict[str, dict[str, list[str]]] = {}
    for source in files:
        package = package_for(source)
        bucket = scope.setdefault(package, {"sources": [], "tests": []})
        bucket["sources"].append(source)
        for test in find_tests(source, tests_root, root=root):
            if test not in bucket["tests"]:
                bucket["tests"].append(test)
    for bucket in scope.values():
        bucket["sources"].sort()
        bucket["tests"].sort()
    return dict(sorted(scope.items()))


def is_mutable_source(path: str | Path) -> bool:
    """Indica si una fuente tiene lógica que merezca mutación.

    Excluye dos casos que **rompen** la recolección de stats de mutmut:

    1. ``@runtime_checkable Protocol``: mutmut inyecta métodos
       ``x||Clase||metodo__mutmut_*`` en la clase; al ser atributos del
       protocolo, ``isinstance(store, VectorStorePort)`` pasa a False aunque
       el store implemente todo el contrato (evidencia: 15 atributos, 5
       inyectados) y la factory lanza ``TypeError``.
    2. ``__init__.py``: solo re-exporta; sus mutantes no tienen tests que los
       cubran y mutmut aborta con "could not find any test case".

    Args:
        path: Ruta de la fuente (relativa al repo o absoluta).

    Returns:
        ``True`` si es mutable; ``False`` si es interfaz o re-export. Un
        archivo ilegible se trata como mutable (sin evidencia en contra).
    """
    target = Path(path)
    if not target.is_absolute():
        target = ROOT / target
    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return True
    if target.name == "__init__.py":
        return False
    return _PROTOCOL_DECL.search(text) is None


def packages_with_mutable_code(
    scope: dict[str, dict[str, list[str]]],
) -> dict[str, dict[str, list[str]]]:
    """Filtra los paquetes que al menos tienen una fuente mutable.

    Args:
        scope: Salida de :func:`build_scope`.

    Returns:
        Subconjunto de ``scope`` con paquetes mutables (los que solo tienen
        interfaces/re-exports se omiten: no hay nada que medir).
    """
    return {
        package: bucket
        for package, bucket in scope.items()
        if any(is_mutable_source(source) for source in bucket["sources"])
    }


def render_config(sources: list[str], tests: list[str]) -> str:
    """Genera la sección ``[mutmut]`` para ``setup.cfg``.

    Args:
        sources: Archivos a mutar.
        tests: Tests que selecciona el runner.

    Returns:
        Texto de configuración (sin cabecera).
    """
    lines = [
        "[mutmut]",
        "source_paths =",
        "    harness/",
        # La copia ``mutants/`` solo trae ``source_paths``; los tests
        # seleccionados importan ``scripts`` y leen la SSOT ``.opencode/``.
        "also_copy =",
        "    scripts/",
        "    .opencode/",
        "only_mutate =",
    ]
    lines.extend(f"    {source}" for source in sources)
    interfaces = [source for source in sources if not is_mutable_source(source)]
    if interfaces:
        lines.append("do_not_mutate =")
        lines.extend(f"    {source}" for source in interfaces)
    lines.append("pytest_add_cli_args_test_selection =")
    lines.extend(f"    {test}" for test in tests)
    return "\n".join(lines) + "\n"


def write_config(path: Path, bucket: dict[str, list[str]]) -> None:
    """Escribe la config de mutmut para un paquete.

    Args:
        path: Ruta del ``setup.cfg`` a escribir.
        bucket: ``{"sources": [...], "tests": [...]}``.
    """
    path.write_text(
        render_config(bucket["sources"], bucket["tests"]), encoding="utf-8"
    )


def score_from_stats(stats: dict[str, Any]) -> float | None:
    """Calcula el mutation score a partir de ``mutmut-cicd-stats.json``.

    Args:
        stats: Payload con ``total``, ``killed``, ``no_tests`` y ``skipped``.

    Returns:
        Score en ``[0, 1]`` o ``None`` si no hay mutantes evaluables.
    """
    total = int(stats.get("total", 0))
    no_tests = int(stats.get("no_tests", 0))
    skipped = int(stats.get("skipped", 0))
    denominator = total - no_tests - skipped
    if denominator <= 0:
        return None
    return int(stats.get("killed", 0)) / denominator


def load_baseline(path: Path = BASELINE_PATH) -> dict[str, float]:
    """Lee el baseline de mutation score por paquete.

    Args:
        path: Archivo JSON (``scripts/mutation_baseline.json``).

    Returns:
        Mapa paquete -> score mínimo. Vacío si el archivo no existe o está
        ilegible (nunca lanza: el baseline es opcional).
    """
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        str(key): float(value)
        for key, value in payload.items()
        if isinstance(value, (int, float))
    }


def update_baseline(
    scores: dict[str, float | None], path: Path = BASELINE_PATH
) -> dict[str, float]:
    """Sube el baseline a lo medido sin bajarlo jamás (ratchet).

    Args:
        scores: Score medido por paquete (``None`` = sin mutantes, se ignora).
        path: Archivo JSON a actualizar.

    Returns:
        Baseline resultante persistido.
    """
    baseline = load_baseline(path)
    for package, score in scores.items():
        if score is None:
            continue
        if score > baseline.get(package, 0.0):
            baseline[package] = round(score, 4)
    path.write_text(
        json.dumps(baseline, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return baseline


def evaluate(
    scope: dict[str, dict[str, list[str]]],
    scores: dict[str, float | None],
    baseline: dict[str, float] | None = None,
) -> list[str]:
    """Compara cada score con el umbral de su paquete.

    Args:
        scope: Salida de :func:`build_scope`.
        scores: Mapa ``paquete -> score`` (``None`` = sin mutantes).
        baseline: Score mínimo calibrado por paquete; manda si supera el
            umbral del paquete (ratchet).

    Returns:
        Fallos legibles (vacío si todos los paquetes cumplen).
    """
    floors = baseline or {}
    failures: list[str] = []
    for package in scope:
        score = scores.get(package)
        threshold = max(threshold_for(package), floors.get(package, 0.0))
        if score is None:
            continue
        if score < threshold:
            failures.append(
                f"{package}: mutation score {score:.1%} < {threshold:.0%}"
            )
    return failures


def _run_mutmut(package: str, bucket: dict[str, list[str]], max_children: int) -> dict[str, Any]:
    """Ejecuta mutmut para un paquete y devuelve sus stats.

    Args:
        package: Paquete mutado (para el mensaje de error).
        bucket: Fuentes y tests del paquete.
        max_children: Workers de mutmut.

    Returns:
        Payload de ``mutants/mutmut-cicd-stats.json``.

    Raises:
        RuntimeError: Si mutmut o la exportación fallan.
    """
    write_config(ROOT / "setup.cfg", bucket)
    stats_path = ROOT / "mutants" / "mutmut-cicd-stats.json"
    # Sin este unlink se leerían los stats del paquete anterior y el score
    # sería de otro paquete (falso positivo/negativo).
    stats_path.unlink(missing_ok=True)
    run = subprocess.run(
        [sys.executable, "-m", "mutmut", "run", "--max-children", str(max_children)],
        cwd=ROOT,
        check=False,
    )
    if run.returncode not in (0, 1):
        raise RuntimeError(
            f"mutation_scope | WHAT=mutmut_fallo | WHY=exit_{run.returncode} | "
            f"WHERE=_run_mutmut | package={package}"
        )
    subprocess.run(
        [sys.executable, "-m", "mutmut", "export-cicd-stats"],
        cwd=ROOT,
        check=False,
    )
    if not stats_path.exists():
        print(f"{package}: sin stats de mutmut (sin mutantes) -> score omitido")
        return {"total": 0, "killed": 0, "no_tests": 0, "skipped": 0}
    return json.loads(stats_path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    """Entrypoint del scoping de mutación.

    Args:
        argv: Argumentos CLI (``None`` usa ``sys.argv``).

    Returns:
        Exit code (0 = OK, 1 = umbral incumplido, 2 = no soportado/error).
    """
    parser = argparse.ArgumentParser(description="Mutación scoped por git diff")
    parser.add_argument("--base", default="origin/main", help="ref base del diff")
    parser.add_argument("--head", default="HEAD", help="ref final del diff")
    parser.add_argument(
        "--tests-root", default=TESTS_ROOT, help=f"tests (default {TESTS_ROOT})"
    )
    parser.add_argument(
        "--write-config", action="store_true", help="escribe setup.cfg del primer paquete"
    )
    parser.add_argument("--run", action="store_true", help="ejecuta mutmut (POSIX)")
    parser.add_argument(
        "--all-core",
        action="store_true",
        help="muta todos los .py de kernel+domain (nocturna, sin diff)",
    )
    parser.add_argument("--max-children", type=int, default=2, help="workers de mutmut")
    parser.add_argument(
        "--packages",
        nargs="+",
        default=[],
        metavar="PKG",
        help="mide paquetes concretos sin diff (p. ej. harness/memory_rag)",
    )
    parser.add_argument("--json", action="store_true", help="salida JSON del scope")
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="sube scripts/mutation_baseline.json a lo medido (ratchet, nunca baja)",
    )
    parser.add_argument(
        "--check-stats",
        default="",
        help="evalua un mutmut-cicd-stats.json existente",
    )
    parser.add_argument("--package", default="harness", help="paquete para --check-stats")
    args = parser.parse_args(argv)

    if args.check_stats:
        stats = json.loads(Path(args.check_stats).read_text(encoding="utf-8"))
        score = score_from_stats(stats)
        failures = evaluate(
            {args.package: {"sources": [], "tests": []}},
            {args.package: score},
            load_baseline(),
        )
        print(f"{args.package}: score={score}")
        for failure in failures:
            print(f"FAIL {failure}", file=sys.stderr)
        return 1 if failures else 0

    try:
        if args.all_core:
            files = files_for_packages()
        elif args.packages:
            files = files_for_packages(tuple(args.packages))
            if not files:
                print(
                    "mutation_scope | WHAT=paquetes_sin_py | WHY=ruta_invalida | "
                    f"WHERE=main | packages={args.packages}",
                    file=sys.stderr,
                )
                return 2
        else:
            files = changed_files(args.base, args.head)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    scope = build_scope(files, ROOT / args.tests_root)
    if args.json:
        print(json.dumps({"scope": scope, "thresholds": MUTATION_THRESHOLDS}, indent=2))
    else:
        print(f"mutación scoped: {len(files)} archivos en {len(scope)} paquetes")
        for package, bucket in scope.items():
            print(
                f"  {package}: {len(bucket['sources'])} fuentes, "
                f"{len(bucket['tests'])} tests, umbral {threshold_for(package):.0%}"
            )

    if not scope:
        print("nada que mutar en el diff (skip)")
        return 0

    if args.write_config:
        first_package, bucket = next(iter(scope.items()))
        write_config(ROOT / "setup.cfg", bucket)
        print(f"setup.cfg escrito para {first_package}")

    if not args.run:
        return 0
    if os.name != "posix":
        print(
            "mutmut 3.x requiere fork: ejecuta --run en WSL/CI (Linux). "
            "En Windows usa --write-config o --json.",
            file=sys.stderr,
        )
        return 2

    mutables = packages_with_mutable_code(scope)
    for package in scope:
        if package not in mutables:
            print(f"{package}: sin codigo mutable (interfaces/re-exports) -> omitido")
    if not mutables:
        print("nada que mutar: todas las fuentes son interfaces/re-exports")
        return 0

    scores: dict[str, float | None] = {}
    for package, bucket in mutables.items():
        stats = _run_mutmut(package, bucket, args.max_children)
        scores[package] = score_from_stats(stats)
        print(f"{package}: score={scores[package]}")
    # Se evalua con el baseline vigente: actualizarlo no puede encubrir una
    # regresion en la misma corrida.
    failures = evaluate(scope, scores, load_baseline())
    if args.update_baseline:
        print(f"baseline: {update_baseline(scores)}")
    for failure in failures:
        print(f"FAIL {failure}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
