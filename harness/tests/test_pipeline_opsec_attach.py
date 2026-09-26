"""Tests para tool_pipeline + op_sec + attachment_gate (deep-docs, ADR-0098).

Tool pipeline: pre->guards monotonicos->approval->around(timeout/retry)->
post->finalize inmutable. Op-sec defensivo: scrub env KEY/SECRET en logs,
tmp 0700. Attachments: admitPromptContent + digest verify-on-read,
fail-closed ante swap.
"""

import pytest

from harness.orchestrator.attachment_gate import (
    AttachmentRecord,
    admit_attachment,
    verify_attachment,
)
from harness.orchestrator.tool_pipeline import (
    PipelineResult,
    run_tool_pipeline,
)
from harness.security.op_sec import (
    scrub_secrets,
    secure_tmpdir,
)


def _ok_tool(**kwargs) -> str:
    """Tool que retorna ok."""
    return "hecho"


def _deny_guard(**kwargs) -> str | None:
    """Guard que aprueba (None = pasa)."""
    return None


def _block_guard(**kwargs) -> str:
    """Guard que bloquea con motivo."""
    return "politica: denegado en pruebas"


def test_pipeline_happy_path() -> None:
    """Guards pasan + approval True -> ejecuta y finaliza inmutable."""
    out = run_tool_pipeline(
        tool=_ok_tool, guards=[_deny_guard], approval_fn=lambda: True,
    )
    assert isinstance(out, PipelineResult)
    assert out.output == "hecho"
    assert out.approved is True


def test_pipeline_guard_blocks() -> None:
    """Guard que bloquea -> no ejecuta (tool ni se llama)."""
    calls: list[str] = []

    def _spy(**kwargs) -> str:
        calls.append("x")
        return "x"

    out = run_tool_pipeline(tool=_spy, guards=[_block_guard], approval_fn=lambda: True)
    assert out.output is None
    assert calls == []
    assert "denegado" in out.reason.lower()


def test_pipeline_approval_denied() -> None:
    """Approval False -> no ejecuta."""
    out = run_tool_pipeline(tool=_ok_tool, guards=[], approval_fn=lambda: False)
    assert out.approved is False
    assert out.output is None


def test_pipeline_tool_error_captured() -> None:
    """Error del tool se captura (no lanza)."""
    def _boom(**kwargs) -> str:
        raise RuntimeError("fallo interno")

    out = run_tool_pipeline(tool=_boom, guards=[], approval_fn=lambda: True)
    assert out.output is None
    assert "fallo" in out.reason.lower()


def test_scrub_masks_secrets() -> None:
    """Scrub enmascara KEY/SECRET/TOKEN en logs."""
    text = "llamando con api_key=ABCDEF123456 y token xyz"
    out = scrub_secrets(text)
    assert "ABCDEF" not in out
    assert "api_key=" in out  # la clave queda, el valor no


def test_scrub_clean_passthrough() -> None:
    """Texto limpio pasa identico."""
    assert scrub_secrets("hola mundo") == "hola mundo"


def test_secure_tmpdir_mode(tmp_path) -> None:
    """secure_tmpdir crea dir 0700 en POSIX (en Windows: aislado por ACL)."""
    import os
    import stat
    import sys

    path = secure_tmpdir(tmp_path / "vault")
    assert path.is_dir()
    if sys.platform == "win32":
        pytest.skip("chmod POSIX no aplica en Windows (ACL de usuario)")
    mode = stat.S_IMODE(os.stat(path).st_mode)
    assert mode == 0o700


def test_admit_and_verify_ok(tmp_path) -> None:
    """Admit registra digest; verify-on-read pasa si no cambio."""
    f = tmp_path / "doc.md"
    f.write_text("contenido", encoding="utf-8")
    rec = admit_attachment(f)
    assert isinstance(rec, AttachmentRecord)
    assert verify_attachment(rec) is True


def test_verify_fails_on_swap(tmp_path) -> None:
    """Si el archivo cambio tras admit -> fail-closed."""
    f = tmp_path / "doc.md"
    f.write_text("original", encoding="utf-8")
    rec = admit_attachment(f)
    f.write_text("TROYANO", encoding="utf-8")
    assert verify_attachment(rec) is False


def test_admit_missing_raises(tmp_path) -> None:
    """Archivo inexistente falla accionable."""
    with pytest.raises(FileNotFoundError, match="WHAT"):
        admit_attachment(tmp_path / "no-existe.md")
