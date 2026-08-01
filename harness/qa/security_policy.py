"""SecurityPolicyScanner — politica de seguridad de paths portables (ADR-0035).

Escanea el repositorio en busca de violaciones de la politica de seguridad:

1. PATHS_NO_PORTABLES: rutas absolutas con nombre de usuario de la maquina
   (``C:\\Users\\<user>``, ``/Users/<user>``, ``/home/<user>``) — exponen la
   estructura del equipo y fallan en otra maquina.
2. HOME_LITERAL_PY: ``$HOME`` literal en codigo Python — nunca se expande en
   ``Path("$HOME/...")``, produce rutas inexistentes (bug) y puede revelar
   estructura personal.
3. DOC_HOME_STRUCTURE: ``$HOME`` seguido de estructura personal
   (``$HOME\\Documents\\...``, ``$HOME\\Mi unidad\\...``) en CUALQUIER archivo
   incluyendo documentacion — revela el layout del equipo del desarrollador.
4. SECRETOS: API keys, tokens (sk-...), passwords hardcodeados, llaves
   privadas PEM y credenciales en codigo fuente.
5. ENV_TRACKEADO: archivos ``.env`` con contenido real trackeados en git.

La politica exige: env vars con fallback a ``Path.home()`` (nunca ``$HOME``
literal ni rutas absolutas personales), y documentacion con placeholders
genericos (``~/proyecto``, ``<HOME>/proyecto``) sin estructura personal.
Codigo determinista: misma entrada -> mismas violaciones.

Uso:
    from harness.qa.security_policy import SecurityPolicyScanner

    scanner = SecurityPolicyScanner(repo_root=".")
    findings = scanner.scan()
    if scanner.has_violations(findings):
        scanner.print_report(findings)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Reglas de deteccion
# ---------------------------------------------------------------------------

# Rutas absolutas personales: C:\\Users\\<user>, /Users/<user>, /home/<user>.
# El lookbehind (?<![\w./-]) evita falsos positivos con paths de repo como
# "docs/home/" o URLs de GitHub (precedidos por letras/slash).
_PERSONAL_PATH_RE = re.compile(
    r"(?:[A-Za-z]:\\Users\\.+|(?<![\w./\-])/Users/[^/\"']+|(?<![\w./\-])/home/[^/\"']+)"
)

# $HOME literal en codigo (Path("$HOME...") o r"$HOME...")
_HOME_LITERAL_RE = re.compile(r"\$HOME[/\\\\]")

# $HOME con estructura personal del usuario (revela layout del equipo):
# $HOME\Documents\..., $HOME\Mi unidad\..., $HOME\AppData\...
# En documentacion, $HOME generico ("cd $HOME/proyecto") es placeholder valido,
# pero la estructura personal NO debe documentarse.
_HOME_STRUCTURE_RE = re.compile(
    r"\$HOME[/\\\\](?:Documents|Documentos|Mi unidad|Desktop|Escritorio|"
    r"AppData|Downloads|Descargas|DEV-SPACE|SIDEPROYECT|shared_memory|"
    r"Hermes_Memory_Proyects)[/\\\\]?",
    re.IGNORECASE,
)

# Secretos: claves API, tokens, passwords, llaves privadas
_SECRET_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("api_key_assign", re.compile(r"(?:api[_-]?key|apikey)\s*=\s*[\"'][A-Za-z0-9_\-]{16,}[\"']", re.IGNORECASE)),
    ("openai_key", re.compile(r"sk-[A-Za-z0-9\-]{20,}")),
    ("github_token", re.compile(r"ghp_[A-Za-z0-9]{30,}")),
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("password_assign", re.compile(r"(?:password|passwd|pwd)\s*=\s*[\"'][^\"']{6,}[\"']", re.IGNORECASE)),
    ("secret_assign", re.compile(r"(?:secret|token)\s*=\s*[\"'][A-Za-z0-9_\-\.]{16,}[\"']", re.IGNORECASE)),
    ("private_key_pem", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----")),
    ("bearer_token", re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]{20,}")),
]

# Extensiones que SI se escanean por contenido
_SCAN_EXTENSIONS = {".py", ".sh", ".ps1", ".yaml", ".yml", ".json", ".toml", ".ini", ".cfg"}
_DOC_EXTENSIONS = {".md", ".rst", ".txt"}  # $HOME valido aqui (placeholder)

# Directorios siempre ignorados
_IGNORED_DIRS = {
    ".git", ".venv", "venv", "env", "node_modules", "__pycache__",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".coverage",
    ".idea", ".vscode", "dist", "build", "target", ".tox", ".nox",
}
_IGNORED_FILES = {
    ".gitignore", ".gitattributes", ".env.example", "poetry.lock",
    "package-lock.json", "uv.lock", "Cargo.lock", "pnpm-lock.yaml",
    "coverage.xml", "Pipfile.lock", "go.sum",
}

# Auto-exclusion del propio scanner, su test y el ADR canonico de la politica:
# contienen patrones de ejemplo deliberadamente (docstrings, fixtures y
# descripcion de bugs hallados) que no son violaciones reales.
_SELF_FILES = {
    "harness/qa/security_policy.py",
    "harness/tests/test_security_policy.py",
    "docs/src/es/adr/adr0035-security-policy-portable-paths-2026.md",
}


@dataclass(frozen=True)
class SecurityFinding:
    """Violacion de la politica de seguridad.

    Args:
        rule: Identificador de la regla violada (PATHS_NO_PORTABLES, ...).
        file: Ruta relativa del archivo (string portable).
        line: Numero de linea (1-based; 0 si no aplica).
        severity: criticidad (CRITICAL | HIGH | MEDIUM | LOW).
        message: Descripcion accionable de la violacion.
    """

    rule: str
    file: str
    line: int
    severity: str
    message: str


class SecurityPolicyScanner:
    """Escanea un repositorio y reporta violaciones de la politica.

    Determinista: mismo repo -> mismas violaciones. No ejecuta codigo,
    solo analisis estatico de texto.

    Uso:
        scanner = SecurityPolicyScanner(repo_root=Path("."))
        findings = scanner.scan()
    """

    def __init__(self, repo_root: str | Path = ".") -> None:
        """
        Args:
            repo_root: raiz del repositorio a escanear.
        """
        self._root = Path(repo_root).resolve()

    # ------------------------------------------------------------------
    # Scan principal
    # ------------------------------------------------------------------

    def scan(self) -> list[SecurityFinding]:
        """Escanea todos los archivos del repositorio.

        Returns:
            Lista de SecurityFinding ordenada por archivo y linea.
        """
        findings: list[SecurityFinding] = []
        for fpath in sorted(self._iter_files()):
            if self._rel(fpath) in _SELF_FILES:
                continue
            findings.extend(self._scan_file(fpath))
        return findings

    def has_violations(self, findings: list[SecurityFinding] | None = None) -> bool:
        """True si hay violaciones (por defecto escanea el repo)."""
        findings = findings if findings is not None else self.scan()
        return bool(findings)

    def print_report(self, findings: list[SecurityFinding] | None = None) -> str:
        """Genera un reporte legible de violaciones.

        Args:
            findings: lista de hallazgos (por defecto escanea el repo).

        Returns:
            Texto del reporte listo para imprimir.
        """
        findings = findings if findings is not None else self.scan()
        lines = [
            "=" * 60,
            "SECURITY POLICY SCAN (ADR-0035) — paths portables + secretos",
            "=" * 60,
        ]
        if not findings:
            lines.append("OK: sin violaciones de la politica de seguridad.")
            return "\n".join(lines)
        lines.append(f"Violaciones encontradas: {len(findings)}\n")
        for f in findings:
            lines.append(
                f"[{f.severity:^8}] {f.rule:<18} {f.file}:{f.line} — {f.message}"
            )
        lines.append("\nAccion: reemplazar rutas por env vars + Path.home(); "
                     "nunca commitear secretos.")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Iteracion de archivos
    # ------------------------------------------------------------------

    def _iter_files(self) -> list[Path]:
        """Lista archivos escaneables (ignora dirs y archivos sensibles)."""
        files: list[Path] = []
        for fpath in self._root.rglob("*"):
            if not fpath.is_file():
                continue
            rel = fpath.relative_to(self._root)
            if any(part in _IGNORED_DIRS for part in rel.parts):
                continue
            if fpath.name in _IGNORED_FILES:
                continue
            # .env sin extension (trackeado = violacion) SI se escanea.
            if fpath.name == ".env":
                files.append(fpath)
                continue
            if fpath.suffix.lower() in _SCAN_EXTENSIONS | _DOC_EXTENSIONS:
                files.append(fpath)
        return files

    # ------------------------------------------------------------------
    # Scan por archivo
    # ------------------------------------------------------------------

    def _scan_file(self, fpath: Path) -> list[SecurityFinding]:
        """Escanea un archivo y devuelve sus violaciones.

        Args:
            fpath: archivo a analizar.

        Returns:
            Lista de SecurityFinding del archivo.
        """
        try:
            content = fpath.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []
        findings: list[SecurityFinding] = []
        is_doc = fpath.suffix.lower() in _DOC_EXTENSIONS

        # 4) .env con credenciales TRACKEADO en git (no el .env local ignorado).
        if fpath.name == ".env" and self._is_git_tracked(fpath):
            findings.append(SecurityFinding(
                rule="ENV_TRACKEADO", file=self._rel(fpath),
                line=0, severity="CRITICAL",
                message="archivo .env con credenciales no debe trackearse "
                        "(anadir a .gitignore)",
            ))

        for lineno, raw_line in enumerate(content.splitlines(), start=1):
            line = raw_line.strip()
            if not line or line.startswith("#") or line.startswith("//"):
                continue
            # 1) Rutas personales (en cualquier archivo).
            if _PERSONAL_PATH_RE.search(line):
                findings.append(SecurityFinding(
                    rule="PATHS_NO_PORTABLES", file=self._rel(fpath),
                    line=lineno, severity="HIGH",
                    message="ruta absoluta con nombre de usuario de la maquina; "
                            "usa env var + Path.home()",
                ))
            # 2) $HOME literal en codigo Python (no en docs/placeholders).
            if not is_doc and _HOME_LITERAL_RE.search(line):
                findings.append(SecurityFinding(
                    rule="HOME_LITERAL_PY", file=self._rel(fpath),
                    line=lineno, severity="HIGH",
                    message="'$HOME' literal no se expande en Path(); "
                            "usa Path.home()",
                ))
            # 2b) $HOME con estructura personal (docs Y codigo): revela el
            #     layout del equipo del desarrollador.
            if _HOME_STRUCTURE_RE.search(line):
                findings.append(SecurityFinding(
                    rule="DOC_HOME_STRUCTURE", file=self._rel(fpath),
                    line=lineno, severity="HIGH",
                    message="'$HOME' con estructura personal (Documents, "
                            "Mi unidad, DEV-SPACE...); usa placeholder "
                            "generico ~/ o <HOME>/",
                ))
            # 3) Secretos (en cualquier archivo).
            for rule_name, pattern in _SECRET_PATTERNS:
                if pattern.search(line):
                    findings.append(SecurityFinding(
                        rule="SECRETO", file=self._rel(fpath),
                        line=lineno, severity="CRITICAL",
                        message=f"posible secreto hardcodeado ({rule_name})",
                    ))

        return findings

    def _rel(self, fpath: Path) -> str:
        """Ruta relativa portable (forward slashes)."""
        return fpath.relative_to(self._root).as_posix()

    def _is_git_tracked(self, fpath: Path) -> bool:
        """True si el archivo esta trackeado por git.

        Consulta el index de git (no el working tree) para distinguir un
        .env ignorado por .gitignore de uno commiteado accidentalmente.
        Determinista y sin efectos secundarios.

        Args:
            fpath: archivo a verificar.

        Returns:
            False si no es un repo git o si git no lo trackea.
        """
        import subprocess
        try:
            rel = self._rel(fpath)
            result = subprocess.run(
                ["git", "ls-files", "--error-unmatch", "--", rel],
                cwd=self._root, capture_output=True, text=True,
                timeout=10,
            )
            return result.returncode == 0
        except (OSError, subprocess.SubprocessError):
            # Sin git disponible: reportar como violacion (defensa en
            # profundidad — un .env presente es sospechoso por defecto).
            return True
