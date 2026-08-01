"""
Tests de SecurityPolicyScanner (ADR-0035) — politica de paths portables.

Verifica que el scanner detecte:
- Rutas absolutas personales (C:\\Users\\<user>, /home/<user>)
- $HOME literal en codigo Python (bug + exposicion)
- Secretos hardcodeados (API keys, tokens, passwords, PEM)
- .env con contenido real trackeado
Y que NO genere falsos positivos en:
- Documentacion con $HOME como placeholder
- Codigo limpio con env vars + Path.home()
"""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.qa.security_policy import SecurityPolicyScanner


@pytest.fixture()
def scanner(tmp_path: Path) -> SecurityPolicyScanner:
    """Scanner apuntando a un repo temporal."""
    return SecurityPolicyScanner(repo_root=tmp_path)


def _write(tmp_path: Path, name: str, content: str) -> None:
    """Escribe un archivo en el repo temporal."""
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# PATHS_NO_PORTABLES
# ---------------------------------------------------------------------------


class TestPathsNoPortables:
    def test_detects_windows_absolute_user_path(self, scanner, tmp_path):
        _write(tmp_path, "scripts/deploy.py",
               'path = Path(r"C:\\Users\\ana\\Documents\\proj")\n')
        findings = scanner.scan()
        rules = [f.rule for f in findings]
        assert "PATHS_NO_PORTABLES" in rules

    def test_detects_unix_home_path(self, scanner, tmp_path):
        _write(tmp_path, "scripts/setup.py",
               'config = "/home/maria/config.yaml"\n')
        findings = scanner.scan()
        assert any(f.rule == "PATHS_NO_PORTABLES" for f in findings)

    def test_clean_code_no_findings(self, scanner, tmp_path):
        _write(tmp_path, "scripts/ok.py",
               "from pathlib import Path\n"
               "p = Path.home() / 'Documents' / 'proj'\n")
        findings = scanner.scan()
        assert findings == []


# ---------------------------------------------------------------------------
# HOME_LITERAL_PY
# ---------------------------------------------------------------------------


class TestHomeLiteralPy:
    def test_detects_home_literal_in_python(self, scanner, tmp_path):
        _write(tmp_path, "scripts/bad.py",
               'p = Path(r"$HOME\\Documents\\proj")\n')
        findings = scanner.scan()
        assert any(f.rule == "HOME_LITERAL_PY" for f in findings)

    def test_doc_md_placeholder_allowed(self, scanner, tmp_path):
        _write(tmp_path, "docs/guia.md",
               "Tu proyecto esta en $HOME/Documents/DEV-SPACE\n")
        findings = scanner.scan()
        assert not any(f.rule == "HOME_LITERAL_PY" for f in findings)


# ---------------------------------------------------------------------------
# DOC_HOME_STRUCTURE
# ---------------------------------------------------------------------------


class TestDocHomeStructure:
    def test_detects_personal_structure_in_docs(self, scanner, tmp_path):
        _write(tmp_path, "docs/guia.md",
               "Mi proyecto esta en $HOME\\Documents\\DEV-SPACE\\Swarmind\n")
        findings = scanner.scan()
        assert any(f.rule == "DOC_HOME_STRUCTURE" for f in findings)

    def test_detects_mi_unidad_in_docs(self, scanner, tmp_path):
        _write(tmp_path, "docs/export.md",
               "Destino: `$HOME\\Mi unidad\\DEV\\SIDEPROYECT\\exports\\`\n")
        findings = scanner.scan()
        assert any(f.rule == "DOC_HOME_STRUCTURE" for f in findings)

    def test_generic_home_placeholder_allowed(self, scanner, tmp_path):
        _write(tmp_path, "docs/guia.md",
               "cd $HOME/proyecto\npython $HOME/tools/x.py\n")
        findings = scanner.scan()
        assert not any(f.rule == "DOC_HOME_STRUCTURE" for f in findings)

    def test_detects_in_python_too(self, scanner, tmp_path):
        _write(tmp_path, "scripts/x.py",
               'p = Path(r"$HOME\\AppData\\Local\\Temp")\n')
        findings = scanner.scan()
        assert any(f.rule == "DOC_HOME_STRUCTURE" for f in findings)


# ---------------------------------------------------------------------------
# SECRETOS
# ---------------------------------------------------------------------------


class TestSecretos:
    @pytest.mark.parametrize("content", [
        'api_key = "sk-abc123456789012345678901234"\n',
        'openai = "sk-proj-abcdefghijklmnopqrstuvwxyz1234567890"\n',
        'password = "supersecreto123"\n',
        'token = "ghp_abcdefghijklmnopqrstuvwxyz1234567890"\n',
        "-----BEGIN RSA PRIVATE KEY-----\n",
    ])
    def test_detects_secrets(self, scanner, tmp_path, content):
        _write(tmp_path, "config/secrets.py", content)
        findings = scanner.scan()
        assert any(f.rule == "SECRETO" for f in findings)

    def test_env_var_reference_not_secret(self, scanner, tmp_path):
        _write(tmp_path, "config/router.py",
               'key = os.environ.get("OPENAI_API_KEY", "")\n')
        findings = scanner.scan()
        assert not any(f.rule == "SECRETO" for f in findings)


# ---------------------------------------------------------------------------
# ENV_TRACKEADO
# ---------------------------------------------------------------------------


class TestEnvTrackeado:
    def _git_init(self, root: Path) -> None:
        """Inicializa un repo git minimo en root."""
        import subprocess
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(
            ["git", "add", "-A"], cwd=root, check=True, capture_output=True,
        )

    def test_detects_env_with_content(self, scanner, tmp_path):
        _write(tmp_path, ".env", "OPENAI_API_KEY=sk-abc123\n")
        self._git_init(tmp_path)  # .env trackeado => violacion CRITICA
        findings = scanner.scan()
        assert any(f.rule == "ENV_TRACKEADO" for f in findings)

    def test_env_ignored_not_violation(self, scanner, tmp_path):
        """.env ignorado por .gitignore (no trackeado) NO es violacion."""
        _write(tmp_path, ".gitignore", ".env\n")
        _write(tmp_path, ".env", "OPENAI_API_KEY=sk-abc123\n")
        self._git_init(tmp_path)
        findings = scanner.scan()
        assert not any(f.rule == "ENV_TRACKEADO" for f in findings)

    def test_env_example_allowed(self, scanner, tmp_path):
        _write(tmp_path, ".env.example", "OPENAI_API_KEY=\n")
        self._git_init(tmp_path)
        findings = scanner.scan()
        assert not any(f.rule == "ENV_TRACKEADO" for f in findings)


# ---------------------------------------------------------------------------
# API publica
# ---------------------------------------------------------------------------


class TestApiPublica:
    def test_has_violations_true(self, scanner, tmp_path):
        _write(tmp_path, "bad.py", 'Path(r"$HOME\\x")\n')
        assert scanner.has_violations()

    def test_has_violations_false(self, scanner):
        assert not scanner.has_violations()

    def test_print_report_empty(self, scanner):
        report = scanner.print_report([])
        assert "OK" in report

    def test_print_report_with_findings(self, scanner):
        report = scanner.print_report([
            scanner._scan_file(Path("x.py"))[0] if False else None,
        ]) if False else ""
        # Construir hallazgo manual para el reporte.
        from harness.qa.security_policy import SecurityFinding
        f = SecurityFinding("SECRETO", "a.py", 1, "CRITICAL", "secreto")
        report = scanner.print_report([f])
        assert "SECRETO" in report
        assert "a.py:1" in report

    def test_ignores_git_and_venv(self, scanner, tmp_path):
        _write(tmp_path, ".git/config", 'path = "C:\\Users\\x\\repo"\n')
        _write(tmp_path, ".venv/lib/bad.py", 'Path(r"$HOME\\x")\n')
        findings = scanner.scan()
        assert findings == []
