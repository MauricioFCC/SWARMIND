"""Aprovechamiento de capacidades de RuscaDB por Swarmind.

WHAT: el informe de capacidades (`probe`) y los comandos `!db` nativos
(capabilities/health/stats/backup/gc/reconcile) deben usar las APIs reales del
store y degradar con un mensaje claro cuando la DLL no exporta un símbolo.

WHY: el store implementa integridad, backup, LSN, cache, grafo y búsqueda
binaria, pero el operador no tenía forma de saber qué aprovecha ni qué falta;
un `!db stats` basado solo en el migrador ocultaba esas capacidades.

WHERE: harness/tests — store falso y DLL por DI; sin tocar datos reales.
"""

from __future__ import annotations

from typing import Any

import pytest

from harness.memory_rag import ruscadb
from harness.memory_rag.ruscadb_capabilities import probe, recommendations
from harness.run_commands import (
    _COMMAND_TABLE,
    _handle_db_backup,
    _handle_db_capabilities,
    _handle_db_explain,
    _handle_db_gc,
    _handle_db_health,
    _handle_db_reconcile,
    _handle_db_stats,
    _handle_db_time_travel,
)


class FakeStore:
    """Store mínimo con la superficie que usan los comandos."""

    def __init__(self) -> None:
        self.backups: list[str] = []
        self.gc_calls = 0
        self.blobs: list[tuple[str, str, bytes]] = []
        self.fts_calls: list[tuple[str, str]] = []
        self.rerank_calls = 0

    def fts_search_mode(self, collection: str, query: str, mode: str = "exact", top_k: int = 10):
        self.fts_calls.append((query, mode))
        return [{"text": "hit", "score": 1.0}]

    def rerank(self, collection: str, query: str, candidates: list[dict], top_k: int = 5):
        self.rerank_calls += 1
        return candidates[:top_k]

    def explain(self, sql: str) -> list[str]:
        return ["SCAN table memory"]

    def execute_at(self, sql: str, snapshot_tx_id: int = 0) -> list[dict]:
        return [{"id": "x", "snapshot": snapshot_tx_id}]


    def attach_blob(self, collection: str, logical_id: str, data: bytes) -> str:
        self.blobs.append((collection, logical_id, data))
        return "blob-hash"

    def list_collections(self) -> list[str]:
        return ["memory", "rag_chunks"]

    def get_collection_stats(self, name: str) -> dict[str, Any]:
        return {"item_count": 3 if name == "memory" else 7}

    def integrity(self) -> dict[str, Any]:
        return {"ok": True}

    def current_lsn(self) -> int:
        return 42

    def query_cache_stats(self) -> dict[str, int]:
        return {"hits": 1, "misses": 2}

    def binary_search_stats(self) -> dict[str, Any]:
        return {"oversample": 4}

    def graph_stats(self, name: str) -> dict[str, int]:
        return {"nodes": 2, "edges": 1}

    def backup(self, destination: str) -> int:
        self.backups.append(destination)
        return 1024

    def gc_blobs(self) -> int:
        self.gc_calls += 1
        return 3

    def reconcile(self) -> dict[str, Any]:
        return {"checked": 2, "fixed": 0}


class TestCapabilities:
    """Informe de features vs símbolos del C-ABI."""

    def test_dll_completa(self) -> None:
        """Con todos los símbolos, no hay faltantes ni recomendación de rebuild."""
        report = probe({name: True for name in ruscadb._CAPABILITY_NAMES})
        assert report.missing_symbols == []
        assert "prepared_native" in report.available_features
        assert "DLL al día" in recommendations(report)[0]

    def test_dll_antigua(self) -> None:
        """Una DLL vieja marca las features afectadas y recomienda rebuild."""
        report = probe({"ruscadb_quantize": True, "ruscadb_search_bq": True})
        assert report.features["binary_quantized"].available is True
        assert report.features["prepared_native"].available is False
        assert "ruscadb_prepare" in report.missing_symbols
        assert any("Recompila" in line for line in recommendations(report))

    def test_capabilities_incluye_simbolos_nuevos(self) -> None:
        """El probe real reporta prepare/KNN USING aunque la DLL no los tenga."""
        caps = ruscadb.capabilities()
        for symbol in ("ruscadb_prepare", "ruscadb_execute_prepared",
                       "ruscadb_search_quantized", "ruscadb_search_filtered"):
            assert symbol in caps


class TestBlobIngest:
    """El binario original se adjunta como blob sin inflar la base."""

    def test_attach_source_blob(self, tmp_path: Any) -> None:
        """Adjunta el archivo y devuelve el hash."""
        from harness.memory_rag.doc_ingester import attach_source_blob

        source = tmp_path / "doc.pdf"
        source.write_bytes(b"%PDF-1.7 demo")
        store = FakeStore()
        assert attach_source_blob(store, "rag_chunks", "rec-1", source) == "blob-hash"
        assert store.blobs == [("rag_chunks", "rec-1", b"%PDF-1.7 demo")]

    def test_omite_blob_grande(self, tmp_path: Any) -> None:
        """Por encima del límite no se adjunta (anti-inflado)."""
        from harness.memory_rag.doc_ingester import attach_source_blob

        source = tmp_path / "big.bin"
        source.write_bytes(b"x" * 32)
        store = FakeStore()
        assert attach_source_blob(store, "rag_chunks", "rec-1", source, max_bytes=8) is None
        assert store.blobs == []


class TestDbCommands:
    """Comandos que exponen las capacidades al operador."""

    def test_capabilities(self, caplog: pytest.LogCaptureFixture) -> None:
        """`!db capabilities` lista features y recomendaciones."""
        caplog.set_level("INFO", logger="harness.run_commands")
        _handle_db_capabilities()
        assert "Capacidades RuscaDB" in caplog.text
        assert "prepared_native" in caplog.text

    def test_health(self, caplog: pytest.LogCaptureFixture) -> None:
        """`!db health` muestra integridad, LSN, cache y grafo."""
        caplog.set_level("INFO", logger="harness.run_commands")
        _handle_db_health(FakeStore())
        for expected in ("integridad", "lsn", "query cache", "grafo[memory]"):
            assert expected in caplog.text

    def test_stats_usa_store(self, caplog: pytest.LogCaptureFixture) -> None:
        """`!db stats` cuenta colecciones del store activo."""
        caplog.set_level("INFO", logger="harness.run_commands")
        _handle_db_stats(FakeStore())
        assert "2 colecciones" in caplog.text
        assert "memory" in caplog.text

    def test_backup_y_gc(self, caplog: pytest.LogCaptureFixture, tmp_path: Any) -> None:
        """`!db backup` escribe y `!db gc` recolecta blobs."""
        caplog.set_level("INFO", logger="harness.run_commands")
        store = FakeStore()
        _handle_db_backup(store, f"!db backup {tmp_path}")
        _handle_db_gc(store)
        assert store.backups == [str(tmp_path)]
        assert store.gc_calls == 1
        assert "Backup creado" in caplog.text

    def test_reconcile(self, caplog: pytest.LogCaptureFixture) -> None:
        """`!db reconcile` reporta el resultado."""
        caplog.set_level("INFO", logger="harness.run_commands")
        _handle_db_reconcile(FakeStore())
        assert "Reconciliación" in caplog.text

    def test_comandos_en_la_tabla(self) -> None:
        """Los comandos nuevos están registrados en el despacho canónico."""
        prefixes = {prefix for prefix, _, _ in _COMMAND_TABLE}
        for command in ("!db capabilities", "!db health", "!db backup", "!db gc",
                        "!db reconcile", "!db explain", "!db time-travel"):
            assert command in prefixes

    def test_explain_y_time_travel(self, caplog: pytest.LogCaptureFixture) -> None:
        """`!db explain` imprime el plan y `!db time-travel` cuenta filas."""
        caplog.set_level("INFO", logger="harness.run_commands")
        _handle_db_explain(FakeStore(), "!db explain SELECT * FROM memory")
        _handle_db_time_travel(FakeStore(), "!db time-travel 7 SELECT * FROM memory")
        assert "SCAN table memory" in caplog.text
        assert "Snapshot 7: 1 filas" in caplog.text

    def test_rag_search_mode_y_rerank(self, caplog: pytest.LogCaptureFixture) -> None:
        """`!rag search --mode fuzzy --rerank` usa FTS y reranker del store."""
        from harness.run_commands.handlers_other import _handle_rag_search

        caplog.set_level("INFO", logger="harness.run_commands")
        store = FakeStore()
        _handle_rag_search(store, "!rag search hola --mode fuzzy --rerank")
        assert store.fts_calls == [("hola", "fuzzy")]
        assert store.rerank_calls == 1

