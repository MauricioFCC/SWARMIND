"""rust_gates.py — Gate T1 determinista para proyectos Rust (DB embebida).

WHAT: Ejecuta el pipeline T1 (<90s, bloquea merge): fmt, clippy, nextest
  (fallback cargo test), deny, audit, geiger e insta, sin shell.
WHY: La hoja de ruta exige calidad institucional en Rust (0 HIGH/CRITICAL,
  0 warnings de clippy, formato y tests verdes) con veredicto determinista.
WHERE: CI pre-merge y guardian local; estilo `supply_chain_gate`.

Uso:
    report = run_rust_t1(repo=".")
    if not report.passed: bloquear(report.findings)
"""

from __future__ import annotations

import logging
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("harness.validation.rust_gates")

#: Timeout individual por comando T1 (el gate total queda <90s con 7 checks).
DEFAULT_TIMEOUT_S: float = 90.0
#: Truncado de findings para no inundar el veredicto.
DETAIL_MAX_CHARS: int = 300
#: Checks que bloquean el merge cuando fallan.
REQUIRED_CHECKS: tuple[str, ...] = ("fmt", "clippy", "nextest")
#: Marcas de salida que indican herramienta ausente (plugin cargo no instalado).
MISSING_TOOL_MARKERS: tuple[str, ...] = ("no such command", "could not determine", "not found")
#: Pista accionable cuando falta la toolchain.
CARGO_INSTALL_HINT: str = "instala toolchain Rust via rustup (https://rustup.rs)"

_FMT_CMD: tuple[str, ...] = ("cargo", "fmt", "--all", "--", "--check")
_CLIPPY_CMD: tuple[str, ...] = ("cargo", "clippy", "--workspace", "--all-targets", "--all-features", "--", "-D", "warnings")
_NEXTEST_CMD: tuple[str, ...] = ("cargo", "nextest", "run", "--workspace", "--profile", "ci")
_TEST_FALLBACK_CMD: tuple[str, ...] = ("cargo", "test", "--workspace")
_DENY_CMD: tuple[str, ...] = ("cargo", "deny", "check")
_AUDIT_CMD: tuple[str, ...] = ("cargo", "audit")
_GEIGER_CMD: tuple[str, ...] = ("cargo", "geiger")
_INSTA_CMD: tuple[str, ...] = ("cargo", "insta", "test", "--check")


@dataclass(frozen=True)
class RustCheck:
    """Resultado de un check T1 individual.

    Attributes:
        name: Nombre del check (fmt, clippy, nextest, deny, audit, geiger, insta).
        passed: True si el check paso (los skipped pasan con skipped=True).
        skipped: True si se omitio (herramienta ausente o sin snapshots).
        detail: Motivo accionable WHAT+WHY+WHERE (truncado).
        duration_s: Duracion del check en segundos.
    """

    name: str
    passed: bool
    skipped: bool
    detail: str
    duration_s: float


@dataclass(frozen=True)
class RustT1Report:
    """Veredicto del gate T1 para Rust.

    Attributes:
        passed: True solo si todo lo requerido paso y 0 HIGH/CRITICAL.
        checks: Tupla con el resultado por check.
        findings: Tupla "check: motivo" de fallos no omitidos.
        duration_s: Duracion total del gate en segundos.
    """

    passed: bool
    checks: tuple[RustCheck, ...] = ()
    findings: tuple[str, ...] = ()
    duration_s: float = 0.0


def _truncate_detail(text: str) -> str:
    """Trunca un detalle a DETAIL_MAX_CHARS (evita veredictos gigantes)."""
    cleaned = " ".join((text or "").split())
    if len(cleaned) <= DETAIL_MAX_CHARS:
        return cleaned
    return cleaned[:DETAIL_MAX_CHARS] + "..."


def _is_missing_tool_output(text: str) -> bool:
    """Detecta si la salida indica plugin cargo ausente."""
    lowered = (text or "").lower()
    return any(marker in lowered for marker in MISSING_TOOL_MARKERS)


def _from_completed(name: str, result: subprocess.CompletedProcess[str], duration_s: float) -> RustCheck:
    """Construye RustCheck desde un CompletedProcess (rc!=0 es fallo)."""
    output = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
    detail = _truncate_detail(output) if output else f"{name}: rc={result.returncode}"
    passed = result.returncode == 0
    if not passed:
        detail = f"{name}: WHAT fallo rc={result.returncode} WHY {detail} WHERE cargo"
    return RustCheck(name=name, passed=passed, skipped=False, detail=detail, duration_s=duration_s)


def _run_cmd(cmd: tuple[str, ...], repo: Path, timeout_s: float) -> subprocess.CompletedProcess[str]:
    """Ejecuta un comando cargo con timeout y captura (nunca shell=True)."""
    return subprocess.run(list(cmd), cwd=repo, capture_output=True, text=True, timeout=timeout_s, check=False)


def _run_single(name: str, cmd: tuple[str, ...], repo: Path, timeout_s: float, optional: bool) -> RustCheck:
    """Ejecuta un check; ausente->skipped si optional, fallo si requerido."""
    start = time.monotonic()
    try:
        result = _run_cmd(cmd, repo, timeout_s)
    except FileNotFoundError as exc:
        duration_s = time.monotonic() - start
        reason = f"{name}: WHAT herramienta ausente WHY {exc} WHERE {' '.join(cmd)}"
        if optional:
            return RustCheck(name=name, passed=True, skipped=True, detail=reason, duration_s=duration_s)
        hint = f"{name}: WHAT cargo ausente WHY toolchain no instalada WHERE PATH; {CARGO_INSTALL_HINT}"
        return RustCheck(name=name, passed=False, skipped=False, detail=hint, duration_s=duration_s)
    except subprocess.TimeoutExpired as exc:
        duration_s = time.monotonic() - start
        detail = f"{name}: WHAT timeout {timeout_s}s WHY comando colgado WHERE {' '.join(cmd)} ({exc})"
        logger.warning("rust_t1 timeout: %s", name)
        return RustCheck(name=name, passed=False, skipped=False, detail=detail, duration_s=duration_s)
    duration_s = time.monotonic() - start
    if optional and result.returncode != 0:
        output = (result.stdout or "") + (result.stderr or "")
        if _is_missing_tool_output(output):
            reason = f"{name}: WHAT herramienta ausente WHY plugin no instalado WHERE {' '.join(cmd)}"
            return RustCheck(name=name, passed=True, skipped=True, detail=reason, duration_s=duration_s)
    return _from_completed(name, result, duration_s)


def _run_fmt(repo: Path, timeout_s: float) -> RustCheck:
    """Ejecuta `cargo fmt --check` (requerido, bloquea merge)."""
    return _run_single("fmt", _FMT_CMD, repo, timeout_s, optional=False)


def _run_clippy(repo: Path, timeout_s: float) -> RustCheck:
    """Ejecuta `cargo clippy -D warnings` (requerido, bloquea merge)."""
    return _run_single("clippy", _CLIPPY_CMD, repo, timeout_s, optional=False)


def _run_nextest(repo: Path, timeout_s: float) -> RustCheck:
    """Ejecuta nextest con fallback a `cargo test` (requerido)."""
    check = _run_single("nextest", _NEXTEST_CMD, repo, timeout_s, optional=False)
    if check.passed or "cargo ausente" in check.detail or "timeout" in check.detail:
        return check
    output = check.detail.lower()
    if _is_missing_tool_output(output):
        fallback = _run_single("nextest", _TEST_FALLBACK_CMD, repo, timeout_s, optional=False)
        return RustCheck(name="nextest", passed=fallback.passed, skipped=False, detail=fallback.detail, duration_s=check.duration_s + fallback.duration_s)
    return check


def _run_deny(repo: Path, timeout_s: float) -> RustCheck:
    """Ejecuta `cargo deny check` (0 HIGH/CRITICAL; sin deny.toml = skipped)."""
    if not (repo / "deny.toml").is_file():
        return RustCheck(name="deny", passed=True, skipped=True, detail="deny: WHAT omitido WHY sin deny.toml WHERE repo", duration_s=0.0)
    return _run_single("deny", _DENY_CMD, repo, timeout_s, optional=True)


def _run_audit(repo: Path, timeout_s: float) -> RustCheck:
    """Ejecuta `cargo audit` (0 HIGH/CRITICAL; herramienta ausente = skipped)."""
    return _run_single("audit", _AUDIT_CMD, repo, timeout_s, optional=True)


def _run_geiger(repo: Path, timeout_s: float) -> RustCheck:
    """Reporta conteo `unsafe` via `cargo geiger` (ausente = skipped)."""
    return _run_single("geiger", _GEIGER_CMD, repo, timeout_s, optional=True)


def _has_snapshots(repo: Path) -> bool:
    """Detecta snapshots insta (*.snap o dir snapshots)."""
    if (repo / "snapshots").is_dir():
        return True
    try:
        return next(repo.rglob("*.snap"), None) is not None
    except OSError as exc:
        logger.warning("rust_t1 snapshots: WHAT rglob fallo WHY %s WHERE %s", exc, repo)
        return False


def _run_insta(repo: Path, timeout_s: float) -> RustCheck:
    """Ejecuta `cargo insta test --check` (sin snapshots = skipped)."""
    if not _has_snapshots(repo):
        return RustCheck(name="insta", passed=True, skipped=True, detail="insta: WHAT omitido WHY sin snapshots WHERE repo", duration_s=0.0)
    return _run_single("insta", _INSTA_CMD, repo, timeout_s, optional=True)


def run_rust_t1(repo: str | Path, *, timeout_s: float = DEFAULT_TIMEOUT_S, required: tuple[str, ...] = REQUIRED_CHECKS) -> RustT1Report:
    """Gate T1 determinista para Rust (<90s, bloquea merge si falla).

    Args:
        repo: Ruta a la raiz del proyecto Rust.
        timeout_s: Timeout individual por comando cargo.
        required: Nombres de checks que bloquean el merge.

    Returns:
        RustT1Report con passed, checks, findings y duracion total.
    """
    start = time.monotonic()
    repo_path = Path(repo)
    checks = (_run_fmt(repo_path, timeout_s), _run_clippy(repo_path, timeout_s), _run_nextest(repo_path, timeout_s), _run_deny(repo_path, timeout_s), _run_audit(repo_path, timeout_s), _run_geiger(repo_path, timeout_s), _run_insta(repo_path, timeout_s))
    required_set = set(required)
    failed_required = [c for c in checks if c.name in required_set and not c.passed]
    failed_optional = [c for c in checks if c.name not in required_set and not c.passed and not c.skipped]
    passed = not failed_required and not failed_optional
    findings = tuple(f"{c.name}: {c.detail}" for c in checks if not c.passed and not c.skipped)
    duration_s = time.monotonic() - start
    if not passed:
        logger.warning("rust_t1: FAILED %d findings", len(findings))
    return RustT1Report(passed=passed, checks=checks, findings=findings, duration_s=duration_s)
