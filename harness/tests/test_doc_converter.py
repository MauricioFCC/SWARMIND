"""
Tests para harness/memory_rag/doc_converter.py — conversion binario -> Markdown.

Usa un modulo `anydoc` fake inyectado en sys.modules: sin red, sin archivos reales.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from harness.memory_rag.doc_converter import (
    DOC_EXTENSIONS,
    AnyDocConverter,
    DocumentConversionError,
)


@pytest.fixture
def fake_anydoc(monkeypatch):
    """Instala un modulo anydoc fake en sys.modules con API compatible."""
    fake = types.ModuleType("anydoc")

    class ConvertError(Exception):
        """Error base de conversion (fake)."""

    class UnsupportedError(ConvertError):
        """Formato no soportado (fake)."""

    fake.ConvertError = ConvertError
    fake.UnsupportedError = UnsupportedError
    fake.to_markdown = MagicMock(return_value="# Titulo\nlinea 1\nlinea 2\n")

    monkeypatch.setitem(sys.modules, "anydoc", fake)
    return fake


@pytest.fixture
def no_anydoc(monkeypatch):
    """Elimina anydoc de sys.modules para simular que no esta instalado."""
    monkeypatch.setitem(sys.modules, "anydoc", None)


def test_doc_extensions_contiene_formatos_clave() -> None:
    """DOC_EXTENSIONS debe incluir los formatos binarios soportados."""
    assert ".pdf" in DOC_EXTENSIONS
    assert ".docx" in DOC_EXTENSIONS
    assert ".pptx" in DOC_EXTENSIONS
    assert ".xlsx" in DOC_EXTENSIONS
    assert ".epub" in DOC_EXTENSIONS
    assert ".csv" in DOC_EXTENSIONS
    assert ".rtf" in DOC_EXTENSIONS
    assert ".md" not in DOC_EXTENSIONS


def test_doc_extensions_es_frozenset() -> None:
    """DOC_EXTENSIONS debe ser un frozenset inmutable."""
    assert isinstance(DOC_EXTENSIONS, frozenset)


class TestAnyDocConverterIsAvailable:
    """Tests de is_available()."""

    def test_is_available_true_con_anydoc(self, fake_anydoc) -> None:
        """Con anydoc instalado, is_available() debe retornar True."""
        assert AnyDocConverter().is_available() is True

    def test_is_available_false_sin_anydoc(self, no_anydoc) -> None:
        """Sin anydoc, is_available() debe retornar False."""
        assert AnyDocConverter().is_available() is False


class TestAnyDocConverterConvert:
    """Tests de convert()."""

    def test_convert_success(self, fake_anydoc, tmp_path: Path) -> None:
        """convert() debe delegar en anydoc.to_markdown y retornar el texto."""
        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        result = AnyDocConverter().convert(pdf)

        assert result == "# Titulo\nlinea 1\nlinea 2\n"
        fake_anydoc.to_markdown.assert_called_once_with(str(pdf))

    def test_convert_convert_error(self, fake_anydoc, tmp_path: Path) -> None:
        """ConvertError debe traducirse a DocumentConversionError con path y reason."""
        pdf = tmp_path / "raro.pdf"
        pdf.write_bytes(b"data")
        fake_anydoc.to_markdown.side_effect = fake_anydoc.UnsupportedError("formato desconocido")

        with pytest.raises(DocumentConversionError) as excinfo:
            AnyDocConverter().convert(pdf)

        assert excinfo.value.path == pdf
        assert "UnsupportedError" in excinfo.value.reason
        assert "raro.pdf" in str(excinfo.value)

    def test_convert_value_error(self, fake_anydoc, tmp_path: Path) -> None:
        """ValueError de anydoc debe traducirse a DocumentConversionError."""
        pdf = tmp_path / "bad.pdf"
        pdf.write_bytes(b"x")
        fake_anydoc.to_markdown.side_effect = ValueError("formato invalido")

        with pytest.raises(DocumentConversionError) as excinfo:
            AnyDocConverter().convert(pdf)

        assert excinfo.value.path == pdf
        assert "ValueError" in excinfo.value.reason

    def test_convert_os_error_archivo_inexistente(self, fake_anydoc) -> None:
        """OSError (p.ej. archivo inexistente) debe traducirse a DocumentConversionError."""
        missing = Path("no_existe.pdf")
        fake_anydoc.to_markdown.side_effect = FileNotFoundError(
            "El sistema no puede encontrar el archivo especificado. (os error 2)"
        )

        with pytest.raises(DocumentConversionError) as excinfo:
            AnyDocConverter().convert(missing)

        assert excinfo.value.path == missing
        assert "OSError" in excinfo.value.reason
        assert "no_existe.pdf" in str(excinfo.value)

    def test_convert_import_error_mensaje_claro(self, no_anydoc, tmp_path: Path) -> None:
        """Sin anydoc, convert() debe lanzar DocumentConversionError con WHAT+WHY+WHERE."""
        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"%PDF")

        with pytest.raises(DocumentConversionError) as excinfo:
            AnyDocConverter().convert(pdf)

        assert excinfo.value.path == pdf
        assert "anydoc" in excinfo.value.reason
        assert "firecrawl-anydoc" in excinfo.value.reason


class TestDocumentConversionError:
    """Tests de la excepcion de dominio."""

    def test_es_runtime_error(self) -> None:
        """DocumentConversionError debe heredar de RuntimeError."""
        assert issubclass(DocumentConversionError, RuntimeError)

    def test_atributos_path_y_reason(self, tmp_path: Path) -> None:
        """Debe exponer path y reason como atributos."""
        err = DocumentConversionError(tmp_path / "a.pdf", "causa X")
        assert err.path == tmp_path / "a.pdf"
        assert err.reason == "causa X"