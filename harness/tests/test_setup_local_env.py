"""Tests de ``setup_local_env.py`` — persistencia portable multi-SO.

Cubren el bloque POSIX (idempotencia, actualizacion y retiro) sin tocar el
HOME real (se inyecta ``tmp_path``). La rama Windows se valida solo en dry-run
(no se invoca ``setx`` en CI/unitarios).
"""

from __future__ import annotations

from pathlib import Path

from scripts.setup_local_env import _apply_rc, _block


def test_block_genera_export_con_marcadores() -> None:
    """El bloque POSIX contiene marcadores, exports ordenados y salto final."""
    # Act
    text = _block({"SWARMIND_REQUIRE_LOCAL": "1", "SWARMIND_LLAMA_DIR": "/x/llama"})

    # Assert
    assert "# >>> SWARMIND start >>>" in text
    assert "# <<< SWARMIND end <<<" in text
    assert 'export SWARMIND_LLAMA_DIR="/x/llama"' in text
    assert 'export SWARMIND_REQUIRE_LOCAL="1"' in text
    assert text.endswith("\n")


def test_apply_rc_inserta_y_no_duplica(tmp_path: Path) -> None:
    """Aplicar dos veces el bloque deja UN solo bloque (idempotente)."""
    # Arrange
    rc = tmp_path / ".bashrc"
    rc.write_text("PS1='$'\n", encoding="utf-8")

    # Act
    _apply_rc(rc, _block({"SWARMIND_REQUIRE_LOCAL": "1"}), dry_run=False, unset=False)
    result = _apply_rc(rc, _block({"SWARMIND_REQUIRE_LOCAL": "1"}), dry_run=False, unset=False)

    # Assert
    assert "actualizado" in result or "insertado" in result
    text = rc.read_text(encoding="utf-8")
    assert text.count("# >>> SWARMIND start >>>") == 1
    assert text.count('export SWARMIND_REQUIRE_LOCAL="1"') == 1


def test_apply_rc_actualiza_en_sitio(tmp_path: Path) -> None:
    """Un segundo bloque con otras vars reemplaza (no acumula) el anterior."""
    # Arrange
    rc = tmp_path / ".zshrc"
    rc.write_text("", encoding="utf-8")
    _apply_rc(rc, _block({"SWARMIND_REQUIRE_LOCAL": "1"}), dry_run=False, unset=False)

    # Act
    _apply_rc(rc, _block({"SWARMIND_REQUIRE_LOCAL": "1", "SWARMIND_LLAMA_DIR": "/z"}), dry_run=False, unset=False)

    # Assert
    text = rc.read_text(encoding="utf-8")
    assert text.count("# >>> SWARMIND start >>>") == 1
    assert 'export SWARMIND_LLAMA_DIR="/z"' in text
    assert 'export SWARMIND_REQUIRE_LOCAL="1"' in text


def test_apply_rc_unset_retira(tmp_path: Path) -> None:
    """``unset`` elimina el bloque y conserva el resto del archivo."""
    # Arrange
    rc = tmp_path / ".profile"
    rc.write_text("alias ll='ls -l'\n", encoding="utf-8")
    _apply_rc(rc, _block({"SWARMIND_REQUIRE_LOCAL": "1"}), dry_run=False, unset=False)

    # Act
    _apply_rc(rc, _block({"SWARMIND_REQUIRE_LOCAL": "1"}), dry_run=False, unset=True)

    # Assert
    text = rc.read_text(encoding="utf-8")
    assert "SWARMIND" not in text
    assert "alias ll" in text


def test_apply_rc_unset_sin_bloque_no_falla(tmp_path: Path) -> None:
    """``unset`` sobre un rc sin bloque no lanza (idempotente)."""
    # Arrange
    rc = tmp_path / ".bashrc"
    rc.write_text("", encoding="utf-8")

    # Act / Assert
    result = _apply_rc(rc, _block({}), dry_run=False, unset=True)
    assert "nada que retirar" in result


def test_dry_run_no_escribe(tmp_path: Path) -> None:
    """``dry_run`` reporta la accion sin modificar el rc-file."""
    # Arrange
    rc = tmp_path / ".bashrc"

    # Act
    result = _apply_rc(rc, _block({"SWARMIND_REQUIRE_LOCAL": "1"}), dry_run=True, unset=False)

    # Assert
    assert "actualizaria" in result
    assert not rc.exists()