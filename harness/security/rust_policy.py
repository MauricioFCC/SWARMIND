"""rust_policy.py — Gate de política de seguridad Rust (determinista, sin red).

WHAT: Evalúa un repo Rust solo con archivos: lints, SAFETY, budget unsafe,
    cargo-deny, lockfile, SBOM y secretos hardcodeados.
WHY: Hoja de ruta de DB embebida: `unsafe` acotado, supply chain, SBOM, secretos.
WHERE: CI / pre-merge de crates Rust; estilo `supply_chain_gate` (veredicto
    frozen, hallazgos "archivo:linea: motivo", errores WHAT+WHY+WHERE).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("harness.security.rust_policy")

#: Budget máximo de bloques `unsafe` por cada 1k líneas Rust.
MAX_UNSAFE_PER_KLOC = 2
#: Ventana (líneas previas + actual) donde se exige el marcador SAFETY.
SAFETY_WINDOW_LINES = 5
#: Marcador obligatorio junto a cada bloque `unsafe`.
SAFETY_MARKER = "SAFETY:"
#: Divisor para miles de líneas de código.
LINES_PER_KLOC = 1000.0
#: Allowlist opcional con exenciones `unsafe` declaradas (crate/file/reason).
ALLOWLIST_FILENAME = "unsafe-allowlist.json"
#: Secciones obligatorias de `deny.toml` (cargo-deny 0 HIGH/CRITICAL).
DENY_REQUIRED_SECTIONS: tuple[str, ...] = ("advisories", "licenses", "bans", "sources")
#: Candidatos válidos de SBOM (presencia, sin validar contenido).
SBOM_CANDIDATES: tuple[str, ...] = ("sbom.cdx.json", "bom.xml", "sbom")
#: Directorios excluidos del escaneo Rust.
EXCLUDED_DIRS: frozenset[str] = frozenset({"target", ".git"})

_UNSAFE_RE: re.Pattern[str] = re.compile(r"\bunsafe\s*\{")
_LINTS_SECTION_RE: re.Pattern[str] = re.compile(r"\[\s*(workspace\.lints|lints)\b")
_UNSAFE_LINT_RE: re.Pattern[str] = re.compile(r"unsafe_code\s*=\s*\"(forbid|deny)\"")
_MISSING_DOCS_RE: re.Pattern[str] = re.compile(r"missing_docs\s*=\s*\"deny\"")
_DENY_SECTION_RE: re.Pattern[str] = re.compile(r"^\s*\[(advisories|licenses|bans|sources)\]", re.MULTILINE)
_SECRET_RE: re.Pattern[str] = re.compile(r"(?i)\b(api_key|secret|password|passwd|token)\b\s*[:=]\s*\S{4,}")
_ENV_READ_MARKERS: tuple[str, ...] = ("env::var", "std::env", "getenv", "env!(", "option_env!")


@dataclass(frozen=True)
class RustPolicyReport:
    """Reporte del gate de política Rust.

    Attributes:
        passed: True si hay 0 hallazgos.
        findings: Tupla "archivo:linea: motivo".
        unsafe_count: Bloques `unsafe` no eximidos.
        kloc: Miles de líneas Rust auditadas.
    """

    passed: bool
    findings: tuple[str, ...] = ()
    unsafe_count: int = 0
    kloc: float = 0.0


def _rel(repo: Path, path: Path) -> str:
    """Ruta relativa POSIX para hallazgos deterministas."""
    try:
        return path.relative_to(repo).as_posix()
    except ValueError as exc:
        logger.warning("ruta fuera del repo %s: %s", path, exc)
        return path.name


def _read_text(path: Path) -> str | None:
    """Lee UTF-8; None si el archivo no existe o falla."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        logger.warning("no se pudo leer %s: %s", path, exc)
        return None


def _parse_allowlist(raw: dict | None) -> tuple[tuple[str, int | None], ...]:
    """Normaliza la allowlist a tupla (archivo, linea|None)."""
    if not isinstance(raw, dict) or not raw:
        return ()
    if "exemptions" in raw or "entries" in raw:
        items = raw.get("exemptions", raw.get("entries", []))
    else:
        items = [{"file": k, "line": None} for k in raw]
    parsed: list[tuple[str, int | None]] = []
    if not isinstance(items, list):
        return ()
    for item in items:
        if not isinstance(item, dict) or "file" not in item:
            continue
        line = item.get("line")
        parsed.append((str(item["file"]), int(line) if isinstance(line, int) else None))
    return tuple(parsed)


def _load_allowlist(repo: Path, allowlist: dict | None) -> tuple[tuple[str, int | None], ...]:
    """Carga unsafe-allowlist.json salvo que se pase allowlist explícita."""
    if allowlist is not None:
        return _parse_allowlist(allowlist)
    if not (repo / ALLOWLIST_FILENAME).is_file():
        return ()
    text = _read_text(repo / ALLOWLIST_FILENAME)
    if text is None:
        return ()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.warning("allowlist inválida %s: %s", ALLOWLIST_FILENAME, exc)
        return ()
    return _parse_allowlist(data if isinstance(data, dict) else None)


def _is_exempt(rel_path: str, lineno: int, exemptions: tuple[tuple[str, int | None], ...]) -> bool:
    """True si (archivo, linea) está eximida por la allowlist."""
    for exempt_file, exempt_line in exemptions:
        norm = exempt_file.replace("\\", "/").lstrip("/").removeprefix("./")
        if (rel_path == norm or rel_path.endswith("/" + norm)) and (exempt_line is None or exempt_line == lineno):
            return True
    return False


def _check_lints(repo: Path) -> list[str]:
    """Exige [workspace.lints] con unsafe_code forbid/deny y missing_docs deny."""
    text = _read_text(repo / "Cargo.toml")
    if text is None:
        return ["Cargo.toml:0: falta Cargo.toml (repo Rust sin manifiesto)"]
    if not _LINTS_SECTION_RE.search(text):
        return ["Cargo.toml:1: workspace sin [workspace.lints] (se exige unsafe_code + missing_docs)"]
    findings: list[str] = []
    if not _UNSAFE_LINT_RE.search(text):
        findings.append('Cargo.toml:1: falta unsafe_code = "forbid" (o deny) en lints')
    if not _MISSING_DOCS_RE.search(text):
        findings.append('Cargo.toml:1: falta missing_docs = "deny" en lints')
    return findings


def _collect_rs_files(repo: Path) -> list[Path]:
    """Lista *.rs del repo (ordenada); excluye target/ y .git/."""
    found = [p for p in repo.rglob("*.rs") if EXCLUDED_DIRS.isdisjoint(p.relative_to(repo).parts)]
    return sorted(found)


def _check_safety(
    rs_files: list[Path],
    repo: Path,
    exemptions: tuple[tuple[str, int | None], ...],
) -> tuple[list[str], int, int]:
    """Verifica // SAFETY: cerca de cada `unsafe {`."""
    findings: list[str] = []
    unsafe_count = 0
    total_lines = 0
    for path in rs_files:
        text = _read_text(path)
        if text is None:
            continue
        rel = _rel(repo, path)
        lines = text.splitlines()
        total_lines += len(lines)
        for lineno, line in enumerate(lines, 1):
            if not _UNSAFE_RE.search(line):
                continue
            if _is_exempt(rel, lineno, exemptions):
                continue
            unsafe_count += 1
            start = max(0, lineno - 1 - SAFETY_WINDOW_LINES)
            if SAFETY_MARKER not in "\n".join(lines[start:lineno]):
                findings.append(f"{rel}:{lineno}: unsafe sin SAFETY (exige // SAFETY: previo)")
    return findings, unsafe_count, total_lines


def _check_budget(unsafe_count: int, total_lines: int) -> list[str]:
    """Aplica MAX_UNSAFE_PER_KLOC sobre bloques no eximidos."""
    if total_lines <= 0 or unsafe_count <= 0:
        return []
    kloc = total_lines / LINES_PER_KLOC
    if unsafe_count / kloc <= MAX_UNSAFE_PER_KLOC:
        return []
    return [f"src:1: budget unsafe excedido: {unsafe_count} bloques en {kloc:.2f} kLOC (max 2/kLOC)"]


def _check_deny(repo: Path) -> list[str]:
    """Exige deny.toml con secciones advisories/licenses/bans/sources."""
    text = _read_text(repo / "deny.toml")
    if text is None:
        return ["deny.toml:0: falta deny.toml (se exige cargo-deny con 0 HIGH/CRITICAL)"]
    missing = [s for s in DENY_REQUIRED_SECTIONS if s not in set(_DENY_SECTION_RE.findall(text))]
    if missing:
        return [f"deny.toml:1: secciones faltantes en deny.toml: {', '.join(missing)}"]
    return []


def _check_lockfile(repo: Path) -> list[str]:
    """Exige Cargo.lock para build reproducible --locked."""
    if (repo / "Cargo.lock").is_file():
        return []
    return ["Cargo.lock:0: falta Cargo.lock (build reproducible exige --locked)"]


def _check_sbom(repo: Path) -> list[str]:
    """Exige SBOM: sbom.cdx.json, bom.xml o directorio sbom/."""
    for candidate in SBOM_CANDIDATES:
        if (repo / candidate).exists():
            return []
    return ["sbom.cdx.json:0: falta SBOM (sbom.cdx.json, bom.xml o sbom/)"]


def _check_secrets(rs_files: list[Path], repo: Path) -> list[str]:
    """Detecta api_key|secret|password|token hardcodeado en *.rs."""
    findings: list[str] = []
    for path in rs_files:
        text = _read_text(path)
        if text is None:
            continue
        rel = _rel(repo, path)
        for lineno, line in enumerate(text.splitlines(), 1):
            if any(marker in line for marker in _ENV_READ_MARKERS):
                continue
            if _SECRET_RE.search(line):
                findings.append(f"{rel}:{lineno}: posible secreto hardcodeado en Rust")
    return findings


def evaluate_rust_policy(repo: str | Path, *, allowlist: dict | None = None) -> RustPolicyReport:
    """Evalúa la política de seguridad Rust de un repo (solo archivos, sin red).

    Args:
        repo: Raíz del repo Rust a auditar.
        allowlist: Dict con exenciones unsafe (crate/file/reason).

    Returns:
        RustPolicyReport con veredicto y hallazgos archivo:linea: motivo.
    """
    root = Path(repo)
    exemptions = _load_allowlist(root, allowlist)
    findings: list[str] = []
    findings.extend(_check_lints(root))
    rs_files = _collect_rs_files(root)
    safety, unsafe_count, total_lines = _check_safety(rs_files, root, exemptions)
    findings.extend(safety)
    findings.extend(_check_budget(unsafe_count, total_lines))
    findings.extend(_check_deny(root))
    findings.extend(_check_lockfile(root))
    findings.extend(_check_sbom(root))
    findings.extend(_check_secrets(rs_files, root))
    kloc = total_lines / LINES_PER_KLOC if total_lines > 0 else 0.0
    if findings:
        logger.warning("rust_policy: %d hallazgos en %s", len(findings), root)
    return RustPolicyReport(passed=not findings, findings=tuple(findings), unsafe_count=unsafe_count, kloc=kloc)
