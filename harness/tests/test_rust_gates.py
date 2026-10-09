"""Tests TDD del gate T1 para Rust (sin cargo real; subprocess mockeado)."""

from __future__ import annotations

import subprocess

from harness.validation.rust_gates import RustT1Report, run_rust_t1


def _ok(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    """Fabrica un CompletedProcess exitoso para el comando dado."""
    return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="ok", stderr="")


def _patch_run(monkeypatch, handler) -> None:
    """Parchea subprocess.run con un handler fake (sin shell real)."""
    monkeypatch.setattr(subprocess, "run", handler)


def test_all_green_passes(monkeypatch, tmp_path) -> None:
    """Todo verde (opcionales skipped o ok) deja el gate en passed=True."""
    _patch_run(monkeypatch, _ok)
    report = run_rust_t1(tmp_path)
    assert isinstance(report, RustT1Report)
    assert report.passed is True
    assert report.findings == ()
    assert len(report.checks) == 7


def test_clippy_failure_blocks(monkeypatch, tmp_path) -> None:
    """Si clippy falla (rc!=0), el gate bloquea con detalle truncado."""
    def fake(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if "clippy" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=101, stdout="", stderr="error: unused variable `x` in src/lib.rs:10")
        return _ok(cmd, **kwargs)

    _patch_run(monkeypatch, fake)
    report = run_rust_t1(tmp_path)
    assert report.passed is False
    assert any("clippy" in f for f in report.findings)
    clippy = next(c for c in report.checks if c.name == "clippy")
    assert clippy.passed is False
    assert len(clippy.detail) <= 310


def test_missing_cargo_fails_with_hint(monkeypatch, tmp_path) -> None:
    """Sin toolchain (FileNotFoundError) el gate falla con motivo instalable."""
    def fake(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("cargo")

    _patch_run(monkeypatch, fake)
    report = run_rust_t1(tmp_path)
    assert report.passed is False
    assert any("rustup" in f for f in report.findings)


def test_missing_deny_is_skipped_green(monkeypatch, tmp_path) -> None:
    """Sin plugin deny (ausente) el check va skipped y el gate sigue verde."""
    def fake(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if "deny" in cmd:
            raise FileNotFoundError("cargo-deny")
        return _ok(cmd, **kwargs)

    (tmp_path / "deny.toml").write_text('[advisories]\n', encoding="utf-8")
    _patch_run(monkeypatch, fake)
    report = run_rust_t1(tmp_path)
    deny = next(c for c in report.checks if c.name == "deny")
    assert deny.skipped is True
    assert deny.passed is True
    assert report.passed is True


def test_check_timeout_is_failure(monkeypatch, tmp_path) -> None:
    """Un timeout del check se reporta como fallo con motivo."""
    def fake(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if "clippy" in cmd:
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=90)
        return _ok(cmd, **kwargs)

    _patch_run(monkeypatch, fake)
    report = run_rust_t1(tmp_path)
    assert report.passed is False
    clippy = next(c for c in report.checks if c.name == "clippy")
    assert clippy.passed is False
    assert "timeout" in clippy.detail
