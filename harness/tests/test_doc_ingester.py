"""
Tests para harness/memory_rag/doc_ingester.py — chunking de documentos binarios.

Cubre: conversion binario -> Markdown via converter inyectado, skip sin converter,
_EXTENSION_TIPO para documentos, DOC_EXTENSIONS en RAG_EXTENSIONS, flag
--include-docs del CLI y flag --docs del handler interactivo.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from harness.memory_rag.doc_converter import DOC_EXTENSIONS, DocumentConversionError
from harness.memory_rag.doc_ingester import (
    _EXTENSION_TIPO,
    RAG_EXTENSIONS,
    DocumentChunker,
)


class FakeConverter:
    """Converter mock determinista para inyectar en DocumentChunker."""

    def __init__(self, markdown: str = "# Doc\nl1\nl2\nl3\nl4\nl5\n", error: Exception | None = None):
        self.markdown = markdown
        self.error = error

    def convert(self, path: Path) -> str:
        """Simula anydoc.to_markdown."""
        if self.error is not None:
            raise self.error
        return self.markdown


@pytest.fixture
def fake_binary(tmp_path: Path) -> Path:
    """Crea un documento binario dummy."""
    doc = tmp_path / "informe.docx"
    doc.write_bytes(b"PK\x03\x04 fake docx")
    return doc


@pytest.fixture
def no_converter(monkeypatch):
    """Fuerza a AnyDocConverter.is_available() -> False en doc_ingester."""
    class Unavailable:
        def is_available(self) -> bool:
            return False

    monkeypatch.setattr("harness.memory_rag.doc_ingester.AnyDocConverter", Unavailable)


class TestExtensionTipo:
    """_EXTENSION_TIPO debe clasificar los documentos binarios."""

    def test_pdf_es_documento(self) -> None:
        assert _EXTENSION_TIPO[".pdf"] == "documento"

    def test_docx_es_documento(self) -> None:
        assert _EXTENSION_TIPO[".docx"] == "documento"

    def test_epub_es_documento(self) -> None:
        assert _EXTENSION_TIPO[".epub"] == "documento"

    def test_pptx_es_presentacion(self) -> None:
        assert _EXTENSION_TIPO[".pptx"] == "presentacion"

    def test_xlsx_es_hoja_calculo(self) -> None:
        assert _EXTENSION_TIPO[".xlsx"] == "hoja_calculo"

    def test_csv_es_datos_tabulares(self) -> None:
        assert _EXTENSION_TIPO[".csv"] == "datos_tabulares"

    def test_extensiones_texto_no_rotas(self) -> None:
        assert _EXTENSION_TIPO[".py"] == "codigo_fuente"
        assert _EXTENSION_TIPO[".md"] == "documentacion"


class TestDocExtensionsEnRag:
    """DOC_EXTENSIONS debe estar incluida en RAG_EXTENSIONS."""

    def test_doc_extensions_en_rag_extensions(self) -> None:
        assert DOC_EXTENSIONS.issubset(RAG_EXTENSIONS)


class TestChunkFileBinario:
    """DocumentChunker con documentos binarios."""

    def test_binario_con_converter_crea_chunks_desde_markdown(
        self, fake_binary: Path
    ) -> None:
        """Con converter inyectado, el markdown convertido se trocea por lineas."""
        chunker = DocumentChunker(chunk_size=3, overlap=1, converter=FakeConverter())

        chunks = chunker.chunk_file(str(fake_binary))

        assert chunks
        assert chunks[0].start_line == 1
        assert chunks[0].end_line == 3
        assert "# Doc" in chunks[0].text
        assert chunks[0].source_file == str(fake_binary)
        assert chunks[0].tipo_doc == "documento"

    def test_binario_con_converter_markdown_corto_un_chunk(self, tmp_path: Path) -> None:
        """Con pocas lineas, end_line debe ser len(lineas) y un solo chunk."""
        doc = tmp_path / "breve.pdf"
        doc.write_bytes(b"%PDF")
        chunker = DocumentChunker(
            chunk_size=25,
            overlap=3,
            converter=FakeConverter(markdown="# A\n# B\n"),
        )

        chunks = chunker.chunk_file(str(doc))

        assert len(chunks) == 1
        assert chunks[0].start_line == 1
        assert chunks[0].end_line == 2

    def test_binario_sin_converter_devuelve_vacio(self, fake_binary: Path, no_converter, caplog) -> None:
        """Sin converter disponible: warning con WHAT+WHY+WHERE y [] (no falla)."""
        chunker = DocumentChunker()

        with caplog.at_level(logging.WARNING):
            chunks = chunker.chunk_file(str(fake_binary))

        assert chunks == []
        assert any("sin converter" in r.message for r in caplog.records)

    def test_binario_con_converter_que_falla_devuelve_vacio(
        self, fake_binary: Path, caplog
    ) -> None:
        """Converter que lanza DocumentConversionError -> [] con warning."""
        err = DocumentConversionError(fake_binary, "formato corrupto")
        chunker = DocumentChunker(converter=FakeConverter(error=err))

        with caplog.at_level(logging.WARNING):
            chunks = chunker.chunk_file(str(fake_binary))

        assert chunks == []
        assert any("formato corrupto" in r.message for r in caplog.records)

    def test_binario_con_converter_error_inesperado_devuelve_vacio(
        self, fake_binary: Path, caplog
    ) -> None:
        """Converter que lanza RuntimeError generico -> [] con warning (red de seguridad)."""
        chunker = DocumentChunker(converter=FakeConverter(error=RuntimeError("boom")))

        with caplog.at_level(logging.WARNING):
            chunks = chunker.chunk_file(str(fake_binary))

        assert chunks == []
        assert any("boom" in r.message for r in caplog.records)

    def test_markdown_normal_sigue_funcionando_sin_converter(self, tmp_path: Path, no_converter) -> None:
        """El pipeline de texto plano no debe romperse sin converter."""
        md = tmp_path / "notas.md"
        md.write_text("# T\n" * 10, encoding="utf-8")
        chunker = DocumentChunker(chunk_size=4, overlap=1)

        chunks = chunker.chunk_file(str(md))

        assert len(chunks) >= 1
        assert "# T" in chunks[0].text


class TestIngestProjectDirectory:
    """include_docs=True debe anadir DOC_EXTENSIONS al scan."""

    @pytest.fixture(autouse=True)
    def patch_lance(self, monkeypatch):
        """Evita LanceDB real: _ensure_lancedb no-op y store mock."""
        monkeypatch.setattr("harness.memory_rag.doc_ingester._ensure_lancedb", lambda: None)
        monkeypatch.setattr(
            "harness.memory_rag.lance_vector_store.LanceVectorStore",
            lambda: MagicMock(),
        )

    @pytest.fixture
    def seen_extensions(self, monkeypatch) -> list[str]:
        """Registra las extensiones que el chunker intenta procesar."""
        seen: list[str] = []

        def fake_chunk_file(self, filepath: str):
            seen.append(Path(filepath).suffix)
            return []

        monkeypatch.setattr(
            "harness.memory_rag.doc_ingester.DocumentChunker.chunk_file",
            fake_chunk_file,
        )
        return seen

    def test_include_docs_anade_docs_a_extensions_explicitas(self, tmp_path: Path, seen_extensions) -> None:
        """include_docs=True debe anadir DOC_EXTENSIONS a extensions explicitas."""
        (tmp_path / "informe.pdf").write_bytes(b"%PDF-1.4")
        (tmp_path / "codigo.py").write_text("x = 1\n", encoding="utf-8")

        from harness.memory_rag.doc_ingester import ingest_project_directory

        stats = ingest_project_directory(str(tmp_path), extensions={".py"}, include_docs=True)

        assert ".pdf" in seen_extensions
        assert stats["files_processed"] == 2

    def test_sin_include_docs_respeta_extensions_explicitas(self, tmp_path: Path, seen_extensions) -> None:
        """Sin include_docs, extensions explicitas no deben recibir docs."""
        (tmp_path / "informe.pdf").write_bytes(b"%PDF-1.4")
        (tmp_path / "codigo.py").write_text("x = 1\n", encoding="utf-8")

        from harness.memory_rag.doc_ingester import ingest_project_directory

        stats = ingest_project_directory(str(tmp_path), extensions={".py"})

        assert ".pdf" not in seen_extensions
        assert stats["files_processed"] == 1

    def test_default_rag_extensions_incluye_docs(self, tmp_path: Path, seen_extensions) -> None:
        """RAG_EXTENSIONS (default) debe incluir DOC_EXTENSIONS."""
        (tmp_path / "informe.pdf").write_bytes(b"%PDF-1.4")
        (tmp_path / "codigo.py").write_text("x = 1\n", encoding="utf-8")

        from harness.memory_rag.doc_ingester import ingest_project_directory

        stats = ingest_project_directory(str(tmp_path))

        assert ".pdf" in seen_extensions
        assert stats["files_processed"] == 2


class TestRagIngestCli:
    """Flag --include-docs del CLI rag_ingest.py."""

    def test_dry_run_include_docs_cuenta_pdf(self, tmp_path: Path, caplog, monkeypatch) -> None:
        """--include-docs + --dry-run debe detectar archivos PDF."""
        (tmp_path / "doc.pdf").write_bytes(b"%PDF")
        monkeypatch.setattr(sys, "argv", ["rag_ingest.py", "--dir", str(tmp_path), "--include-docs", "--dry-run"])

        from harness.scripts.rag_ingest import main

        with caplog.at_level(logging.INFO):
            main()

        assert "Dry-run: 1 archivos detectados" in caplog.text

    def test_dry_run_sin_include_docs_no_cuenta_pdf(self, tmp_path: Path, caplog, monkeypatch) -> None:
        """Sin --include-docs, el dry-run no debe contar PDFs."""
        (tmp_path / "doc.pdf").write_bytes(b"%PDF")
        monkeypatch.setattr(sys, "argv", ["rag_ingest.py", "--dir", str(tmp_path), "--dry-run"])

        from harness.scripts.rag_ingest import main

        with caplog.at_level(logging.INFO):
            main()

        assert "Dry-run: 0 archivos detectados" in caplog.text


class TestHandleRagIngestDocs:
    """Flag --docs del handler interactivo !rag ingest."""

    def test_handle_rag_ingest_with_docs(self, tmp_path: Path) -> None:
        """!rag ingest --docs debe llamar a ingest_project_directory con include_docs=True."""
        d = tmp_path / "repo"
        d.mkdir()
        with patch("harness.memory_rag.doc_ingester.ingest_project_directory") as m:
            m.return_value = {"files_processed": 2, "chunks_inserted": 10, "errors": 0}
            from harness.run_commands import _handle_rag_ingest
            _handle_rag_ingest(MagicMock(), f"!rag ingest --dir {d} --docs")

        assert m.call_args.kwargs.get("include_docs") is True

    def test_handle_rag_ingest_sin_docs(self, tmp_path: Path) -> None:
        """!rag ingest sin --docs debe usar include_docs por defecto (False)."""
        d = tmp_path / "repo2"
        d.mkdir()
        with patch("harness.memory_rag.doc_ingester.ingest_project_directory") as m:
            m.return_value = {"files_processed": 1, "chunks_inserted": 3, "errors": 0}
            from harness.run_commands import _handle_rag_ingest
            _handle_rag_ingest(MagicMock(), f"!rag ingest --dir {d}")

        assert m.call_args.kwargs.get("include_docs") is False