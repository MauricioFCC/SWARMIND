"""Tests del gate de política de seguridad Rust (TDD, fixtures en tmp_path)."""

from __future__ import annotations

from pathlib import Path

from harness.security.rust_policy import evaluate_rust_policy

_HEALTHY_CARGO_TOML = """[package]
name = "demo"
version = "0.1.0"

[workspace.lints.rust]
unsafe_code = "forbid"
missing_docs = "deny"
"""

_HEALTHY_MAIN_RS = """fn main() {
    let _token = std::env::var("APP_TOKEN").unwrap_or_default();
    println!("ok");
}
"""

_HEALTHY_DENY_TOML = """[advisories]
db-urls = ["https://github.com/rustsec/advisory-db"]

[licenses]
allow = ["MIT", "Apache-2.0"]

[bans]
multiple-versions = "deny"

[sources]
unknown-registry = "deny"
"""


def _write(path: Path, content: str) -> None:
    """Escribe contenido UTF-8 creando los directorios padres."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_healthy_repo(root: Path) -> Path:
    """Crea un repo Rust mínimo que pasa todos los chequeos del gate."""
    _write(root / "Cargo.toml", _HEALTHY_CARGO_TOML)
    _write(root / "src" / "main.rs", _HEALTHY_MAIN_RS)
    _write(root / "deny.toml", _HEALTHY_DENY_TOML)
    _write(root / "Cargo.lock", 'version = 3\n[[package]]\nname = "demo"\nversion = "0.1.0"\n')
    _write(root / "sbom.cdx.json", '{"bomFormat": "CycloneDX", "version": 1}\n')
    return root


def test_healthy_repo_passes(tmp_path: Path) -> None:
    """Un repo sano cumple lints, deny, lockfile, SBOM y sin unsafe/secretos."""
    report = evaluate_rust_policy(_make_healthy_repo(tmp_path))
    assert report.passed is True
    assert report.findings == ()
    assert report.unsafe_count == 0
    assert report.kloc > 0.0


def test_unsafe_without_safety_reports_file_line(tmp_path: Path) -> None:
    """Un bloque `unsafe {` sin `// SAFETY:` genera hallazgo archivo:linea."""
    root = _make_healthy_repo(tmp_path)
    _write(root / "src" / "main.rs", _HEALTHY_MAIN_RS + "fn f() {\n    unsafe { core::hint::black_box(()); }\n}\n")
    report = evaluate_rust_policy(root)
    assert report.passed is False
    assert any("src/main.rs:6:" in f and "SAFETY" in f for f in report.findings)


def test_unsafe_with_safety_and_allowlist_passes(tmp_path: Path) -> None:
    """SAFETY documentado + ubicación eximida en allowlist no bloquean."""
    root = _make_healthy_repo(tmp_path)
    padding = "".join(f"// relleno {i}\n" for i in range(600))
    code = (
        padding
        + "// SAFETY: acceso validado, invariante documentada.\n"
        + "fn first() {\n"
        + "    unsafe { core::hint::black_box(()); }\n"
        + "}\n"
        + "fn second() {\n"
        + "    unsafe { core::hint::black_box(()); }\n"
        + "}\n"
    )
    _write(root / "src" / "main.rs", code)
    second_line = len(code.splitlines()) - 1
    allowlist = {"exemptions": [{"file": "src/main.rs", "line": second_line, "reason": "auditoria manual"}]}
    report = evaluate_rust_policy(root, allowlist=allowlist)
    assert report.passed is True
    assert report.unsafe_count == 1


def test_missing_deny_toml_reported(tmp_path: Path) -> None:
    """Sin deny.toml el gate falla (se exige cargo-deny)."""
    root = _make_healthy_repo(tmp_path)
    (root / "deny.toml").unlink()
    report = evaluate_rust_policy(root)
    assert report.passed is False
    assert any(f.startswith("deny.toml:") for f in report.findings)


def test_missing_lockfile_reported(tmp_path: Path) -> None:
    """Sin Cargo.lock el gate falla (build reproducible --locked)."""
    root = _make_healthy_repo(tmp_path)
    (root / "Cargo.lock").unlink()
    report = evaluate_rust_policy(root)
    assert report.passed is False
    assert any(f.startswith("Cargo.lock:") for f in report.findings)


def test_missing_sbom_reported(tmp_path: Path) -> None:
    """Sin SBOM el gate falla (presencia de sbom.cdx.json/bom.xml/sbom/)."""
    root = _make_healthy_repo(tmp_path)
    (root / "sbom.cdx.json").unlink()
    report = evaluate_rust_policy(root)
    assert report.passed is False
    assert any("SBOM" in f for f in report.findings)


def test_hardcoded_secret_reported(tmp_path: Path) -> None:
    """Una api_key hardcodeada en .rs genera hallazgo archivo:linea."""
    root = _make_healthy_repo(tmp_path)
    _write(root / "src" / "main.rs", _HEALTHY_MAIN_RS + 'let api_key = "sk-abc123456789";\n')
    report = evaluate_rust_policy(root)
    assert report.passed is False
    assert any("src/main.rs:" in f and "secreto" in f for f in report.findings)


def test_over_budget_unsafe_reported(tmp_path: Path) -> None:
    """Más de 2 bloques unsafe por kLOC genera hallazgo de budget."""
    root = _make_healthy_repo(tmp_path)
    blocks = "".join(
        f"// SAFETY: caso {i} auditado.\nfn f{i}() {{\n    unsafe {{ core::hint::black_box(()); }}\n}}\n"
        for i in range(5)
    )
    _write(root / "src" / "extra.rs", blocks)
    report = evaluate_rust_policy(root)
    assert report.passed is False
    assert not any("SAFETY" in f for f in report.findings)
    assert any("budget unsafe" in f for f in report.findings)


def test_missing_workspace_lints_reported(tmp_path: Path) -> None:
    """Un Cargo.toml sin [workspace.lints] genera hallazgo."""
    root = _make_healthy_repo(tmp_path)
    _write(root / "Cargo.toml", '[package]\nname = "demo"\nversion = "0.1.0"\n')
    report = evaluate_rust_policy(root)
    assert report.passed is False
    assert any("workspace.lints" in f for f in report.findings)
