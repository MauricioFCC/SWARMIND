"""Tests del paquete de revisión ciega (EGM + Binnacle, ciclo FR-0010).

Oráculo congelado contra ``docs/specs/blind-review-packet.md``:
AC-BR1..AC-BR8 y las propiedades P1..P3 (PBT con ``hypothesis``).

Se verifican cuatro superficies:
  - extracción de criterios de aceptación de la spec,
  - redacción de secretos y rutas personales,
  - gates deterministas (bloquean antes de cualquier modelo),
  - CLI ``scripts/blind_review.py`` con exit codes 0/1.

Mutantes esperados (demostración de poder discriminante):
  - ``approved_for_review`` con ``any`` en vez de ``all`` → AC-BR2/3/4/5 caen,
  - quitar el patrón ``aws_key`` → AC-BR2 cae,
  - no truncar → AC-BR4 y P3 caen,
  - regex de AC sin sufijo alfanumérico → AC-BR1 cae (ids ``AC-BR*``).
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from harness.validation.blind_review import (
    BlindPacket,
    build_blind_packet,
    extract_acceptance_criteria,
    redact,
    render_markdown,
)

ROOT = Path(__file__).resolve().parent.parent.parent
CLI = ROOT / "scripts" / "blind_review.py"

SPEC = """# Spec de ejemplo

## Criterios de aceptación

- **AC-BR1** — Extraer criterios en orden.
- **AC-BR2** — Redactar secretos.
- **AC-BR3** — Redactar rutas personales.
"""

CLEAN_DIFF = """diff --git a/harness/x.py b/harness/x.py
--- a/harness/x.py
+++ b/harness/x.py
@@ -1 +1 @@
-x = 1
+x = 2
"""

#: Fixtures construidas por partes: así el escáner de seguridad del repo no las
#: confunde con credenciales o rutas reales de la máquina.
_WIN_HOME = "C:" + "\\" + "Users" + "\\"
_POSIX_HOME = "/" + "home" + "/"
_POSIX_USERS = "/" + "Users" + "/"
_FAKE_PEM = "-----BEGIN " + "RSA PRIVATE KEY-----"
_FAKE_ASSIGN = "api_" + 'key = "supersecretvalue"'


def _cli_main(monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> int:
    """Ejecuta ``scripts/blind_review.py`` en proceso y devuelve su exit code.

    Args:
        monkeypatch: Fixture de pytest para sustituir ``sys.argv``.
        argv: Argumentos de la CLI (sin el nombre del script).

    Returns:
        Código de salida de ``main()``.
    """
    spec = importlib.util.spec_from_file_location("blind_review_cli", CLI)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(sys, "argv", ["blind_review.py", *argv])
    return int(module.main())


# ---------------------------------------------------------------------------
# AC-BR1 — extracción de criterios
# ---------------------------------------------------------------------------


def test_extracts_ids_with_alphanumeric_suffix() -> None:
    """AC-BR1: los ids con sufijo alfanumérico (AC-BR2) se extraen."""
    criteria = extract_acceptance_criteria(SPEC)
    assert len(criteria) == 3
    assert "Extraer criterios en orden." in criteria[0]
    assert "Redactar secretos." in criteria[1]


def test_extracts_inline_ids_without_section_heading() -> None:
    """AC-BR1: un criterio con id fuera de la sección también se extrae."""
    spec = "# Nota\n\nTexto libre.\n\n- **AC-BR7** — render determinista.\n"
    criteria = extract_acceptance_criteria(spec)
    assert criteria == ("**AC-BR7** — render determinista.",)


def test_ignores_prose_references_to_criteria() -> None:
    """AC-BR1: la prosa que menciona ids no infla la lista de criterios."""
    spec = (
        "- **AC-7** — dada `AC-1` y `AC-2`, devuelve ambos.\n"
        "El resto se cubre en AC-1 y AC-2 del documento de diseño.\n"
    )
    criteria = extract_acceptance_criteria(spec)
    assert len(criteria) == 1
    assert "AC-7" in criteria[0]


def test_deduplicates_repeated_ids() -> None:
    """AC-BR1: un id repetido se conserva una sola vez, en orden de aparición."""
    spec = "- AC-1 — primero\n- AC-2 — segundo\n- AC-1 — duplicado\n"
    criteria = extract_acceptance_criteria(spec)
    assert len(criteria) == 2
    assert "primero" in criteria[0]
    assert "segundo" in criteria[1]


def test_falls_back_to_section_bullets() -> None:
    """AC-BR1: sin ids, se usan las viñetas de la sección de criterios."""
    spec = "## Criterios de aceptación\n\n- el build pasa\n- ruff sin errores\n"
    assert extract_acceptance_criteria(spec) == ("el build pasa", "ruff sin errores")


def test_ignores_non_criteria_words() -> None:
    """AC-BR1: palabras que empiezan por AC sin dígito no son criterios."""
    spec = "El acceso ACEPTABLE y la actuación ACTUAL no son criterios.\n"
    assert extract_acceptance_criteria(spec) == ()


# ---------------------------------------------------------------------------
# AC-BR2 — secretos
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("secret", "kind"),
    [
        ("ghp_" + "a" * 36, "github_token"),
        ("sk-" + "b" * 24, "openai_key"),
        ("AKIA" + "C" * 16, "aws_key"),
        ("xoxb-" + "1234567890abc", "slack_token"),
        (_FAKE_PEM, "private_key"),
        (_FAKE_ASSIGN, "assignment"),
    ],
)
def test_secret_patterns_block_and_redact(secret: str, kind: str) -> None:
    """AC-BR2: cada patrón de secreto bloquea el paquete y se redacta."""
    diff = CLEAN_DIFF + f"+KEY = {secret}\n"
    packet = build_blind_packet(SPEC, diff)
    assert "no_secrets" in packet.failed_checks()
    assert not packet.approved_for_review
    assert f"<redacted:{kind}>" in packet.diff
    assert secret not in packet.diff


# ---------------------------------------------------------------------------
# AC-BR3 — rutas personales
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        _WIN_HOME + "marta.gil" + "\\project\\file.py",
        _POSIX_HOME + "marta.gil/project/file.py",
        _POSIX_USERS + "marta.gil/project/file.py",
    ],
)
def test_personal_paths_block_and_redact(path: str) -> None:
    """AC-BR3: una ruta con nombre de usuario se redacta y no se aprueba."""
    diff = CLEAN_DIFF + f"+config = '{path}'\n"
    packet = build_blind_packet(SPEC, diff)
    assert "no_personal_paths" in packet.failed_checks()
    assert not packet.approved_for_review
    assert "marta.gil" not in packet.diff
    assert "<user>" in packet.diff


@pytest.mark.parametrize(
    "path",
    [
        _WIN_HOME + "alice\\app.py",
        _POSIX_HOME + "example/x.py",
        _POSIX_USERS + "test/y.py",
        _WIN_HOME + "<x>\\a.py",
    ],
)
def test_placeholder_users_are_redacted_but_do_not_block(path: str) -> None:
    """AC-BR3: los nombres de ejemplo (alice/example/test/<x>) no bloquean."""
    packet = build_blind_packet(SPEC, CLEAN_DIFF + f"+p = '{path}'\n")
    assert "no_personal_paths" not in packet.failed_checks()
    assert packet.approved_for_review
    assert "<user>" in packet.diff


# ---------------------------------------------------------------------------
# AC-BR4 — truncado explícito
# ---------------------------------------------------------------------------


def test_oversized_diff_is_truncated_explicitly() -> None:
    """AC-BR4: el diff grande se corta en salto de línea y se marca."""
    diff = CLEAN_DIFF + "".join(f"+linea {i}\n" for i in range(500))
    packet = build_blind_packet(SPEC, diff, max_diff_chars=400)
    assert packet.truncated
    assert "diff_within_budget" in packet.failed_checks()
    assert not packet.approved_for_review
    assert "[TRUNCADO:" in packet.diff
    assert "caracteres omitidos]" in packet.diff


def test_small_diff_is_not_truncated() -> None:
    """AC-BR4: un diff dentro del presupuesto no se marca como truncado."""
    packet = build_blind_packet(SPEC, CLEAN_DIFF)
    assert not packet.truncated
    assert "diff_within_budget" not in packet.failed_checks()


# ---------------------------------------------------------------------------
# AC-BR5 — alcance de archivos
# ---------------------------------------------------------------------------


def test_too_many_files_block_packet() -> None:
    """AC-BR5: más archivos que el tope activa el gate de alcance."""
    diff = "".join(f"diff --git a/f{i}.py b/f{i}.py\n--- a/f{i}.py\n+++ b/f{i}.py\n" for i in range(4))
    packet = build_blind_packet(SPEC, diff, max_files=3)
    assert packet.files_touched == 4
    assert "scope_files" in packet.failed_checks()


# ---------------------------------------------------------------------------
# AC-BR6 — fail-fast con WHAT/WHY/WHERE
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("spec", "diff"), [("", CLEAN_DIFF), (SPEC, "   ")])
def test_empty_inputs_raise_typed_error(spec: str, diff: str) -> None:
    """AC-BR6: spec o diff vacíos lanzan ValueError con WHAT/WHY/WHERE."""
    with pytest.raises(ValueError) as excinfo:
        build_blind_packet(spec, diff)
    message = str(excinfo.value)
    assert "WHAT:" in message
    assert "WHY:" in message
    assert "WHERE:" in message


@pytest.mark.parametrize(("max_diff_chars", "max_files"), [(0, 5), (100, 0)])
def test_invalid_limits_raise(max_diff_chars: int, max_files: int) -> None:
    """AC-BR6: topes no positivos lanzan ValueError tipado."""
    with pytest.raises(ValueError, match="WHAT:"):
        build_blind_packet(SPEC, CLEAN_DIFF, max_diff_chars=max_diff_chars, max_files=max_files)


# ---------------------------------------------------------------------------
# AC-BR7 — determinismo
# ---------------------------------------------------------------------------


def test_render_is_byte_identical_and_context_free() -> None:
    """AC-BR7: el render es determinista y no arrastra conversación."""
    first = build_blind_packet(SPEC, CLEAN_DIFF)
    second = build_blind_packet(SPEC, CLEAN_DIFF)
    markdown = render_markdown(first)
    assert markdown == render_markdown(second)
    assert "conversación" in markdown
    for forbidden in ("2026-", "T00:", "usuario dijo", "assistant"):
        assert forbidden not in markdown


def test_render_lists_checks_and_criteria() -> None:
    """AC-BR7: el render incluye gates, criterios y diff delimitado."""
    packet = build_blind_packet(SPEC, CLEAN_DIFF)
    markdown = render_markdown(packet)
    assert "| Gate | Estado | Detalle |" in markdown
    assert "| no_secrets | PASS |" in markdown
    assert "AC-BR1" in markdown
    assert "```diff" in markdown


# ---------------------------------------------------------------------------
# AC-BR8 — CLI
# ---------------------------------------------------------------------------


def test_cli_exit_zero_when_approved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """AC-BR8: exit 0 cuando todos los gates pasan; imprime el paquete."""
    spec_file = tmp_path / "spec.md"
    diff_file = tmp_path / "change.diff"
    spec_file.write_text(SPEC, encoding="utf-8")
    diff_file.write_text(CLEAN_DIFF, encoding="utf-8")
    code = _cli_main(monkeypatch, ["--spec", str(spec_file), "--diff", str(diff_file)])
    assert code == 0
    assert "Revisión ciega" in capsys.readouterr().out


def test_cli_exit_one_when_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """AC-BR8: exit 1 cuando un gate bloquea; el motivo queda visible."""
    spec_file = tmp_path / "spec.md"
    diff_file = tmp_path / "change.diff"
    spec_file.write_text(SPEC, encoding="utf-8")
    diff_file.write_text(CLEAN_DIFF + "+KEY = ghp_" + "a" * 36 + "\n", encoding="utf-8")
    code = _cli_main(monkeypatch, ["--spec", str(spec_file), "--diff", str(diff_file)])
    assert code == 1
    assert "BLOCK" in capsys.readouterr().out


def test_secrets_in_spec_are_redacted_too() -> None:
    """AC-BR3: los criterios de la spec también se redactan antes de salir."""
    spec = "- **AC-9** - cubre `" + _WIN_HOME + "alice" + "\\\\app.py` y `" + _POSIX_HOME + "alice/x`\n"
    packet = build_blind_packet(spec, CLEAN_DIFF)
    assert "alice" not in packet.acceptance_criteria[0]
    assert packet.acceptance_criteria[0].count("<user>") == 2
    assert "spec_redactada" in packet.redactions


def test_cli_reads_git_diff_from_stdin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """AC-BR8: ``--git-diff`` lee el diff de stdin (flujo con ``git diff |``)."""
    import io

    spec_file = tmp_path / "spec.md"
    spec_file.write_text(SPEC, encoding="utf-8")
    fake_stdin = type("FakeStdin", (), {"buffer": io.BytesIO(CLEAN_DIFF.encode())})()
    monkeypatch.setattr(sys, "stdin", fake_stdin)
    code = _cli_main(monkeypatch, ["--spec", str(spec_file), "--git-diff"])
    assert code == 0
    assert "Revisión ciega" in capsys.readouterr().out


def test_cli_reports_non_utf8_diff(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-BR8/ERR: un diff no UTF-8 falla con WHAT/WHY/WHERE, no con traceback."""
    spec_file = tmp_path / "spec.md"
    diff_file = tmp_path / "change.diff"
    spec_file.write_text(SPEC, encoding="utf-8")
    diff_file.write_bytes(b"\xff\xfe\x00invalid")
    with pytest.raises(ValueError, match="WHAT:"):
        _cli_main(monkeypatch, ["--spec", str(spec_file), "--diff", str(diff_file)])


# ---------------------------------------------------------------------------
# PBT — P1..P3
# ---------------------------------------------------------------------------


@given(st.text(max_size=200))
def test_p1_redaction_is_idempotent(text: str) -> None:
    """P1: ``redact(redact(x)) == redact(x)`` para cualquier texto."""
    once, _ = redact(text)
    twice, _ = redact(once)
    assert once == twice


@given(st.integers(min_value=1, max_value=5))
def test_p2_gates_are_monotone(extra_files: int) -> None:
    """P2: añadir archivos nunca mejora el veredicto (monotonía de gates)."""
    base = "".join(f"diff --git a/f{i}.py b/f{i}.py\n--- a/f{i}.py\n+++ b/f{i}.py\n" for i in range(extra_files))
    more = base + "".join(f"diff --git a/g{i}.py b/g{i}.py\n--- a/g{i}.py\n+++ b/g{i}.py\n" for i in range(2))
    approved_base = build_blind_packet(SPEC, base, max_files=8).approved_for_review
    approved_more = build_blind_packet(SPEC, more, max_files=8).approved_for_review
    assert not (approved_more and not approved_base)


@given(st.integers(min_value=10, max_value=2_000))
def test_p3_truncation_is_bounded(limit: int) -> None:
    """P3: el diff truncado no excede el tope más la marca de truncado."""
    diff = "".join(f"+linea {i}\n" for i in range(500))
    packet = build_blind_packet(SPEC, diff, max_diff_chars=limit)
    assert len(packet.diff) <= limit + len("[TRUNCADO: 999999 caracteres omitidos]")


def test_packet_is_frozen() -> None:
    """Inmutabilidad: el paquete no se puede mutar tras construirse."""
    packet = build_blind_packet(SPEC, CLEAN_DIFF)
    assert isinstance(packet, BlindPacket)
    with pytest.raises(FrozenInstanceError):
        packet.diff = "otro"  # type: ignore[misc]
