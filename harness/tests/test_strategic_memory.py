"""
Tests para StrategicMemory — Memoria con forget estrategico (SF-AMS).

Cubre:
  - store y recall basico
  - recall de clave inexistente
  - busqueda por tags y entidades
  - olvido estrategico (utility-driven eviction)
  - actualizacion de importancia por re-acceso
  - estadisticas (get_stats)
  - persistencia a disco (save/load)
  - edge cases (valor complejo, serializacion, clear)
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from harness.memory_rag.strategic_memory import MemoryItem, StrategicMemory


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def sm(tmp_path: Path) -> StrategicMemory:
    """StrategicMemory con path temporal y capacidad reducida para tests."""
    return StrategicMemory(max_items=10, path=tmp_path / "test_strategic.json")


@pytest.fixture
def sm_small(tmp_path: Path) -> StrategicMemory:
    """StrategicMemory con capacidad minima (3 items) para forzar olvido."""
    return StrategicMemory(max_items=3, path=tmp_path / "small_memory.json")


# ===========================================================================
# Tests: Store y Recall basico
# ===========================================================================


class TestStoreRecall:
    """Almacenar y recuperar valores de StrategicMemory."""

    def test_store_and_recall(self, sm: StrategicMemory) -> None:
        """Store seguido de recall retorna el valor almacenado."""
        sm.store("alpha", "hello")
        assert sm.recall("alpha") == "hello"

    def test_store_overwrite(self, sm: StrategicMemory) -> None:
        """Sobrescribir una clave existente actualiza valor y metadatos."""
        sm.store("key1", "original")
        sm.store("key1", "updated", tags=["nuevo"], entities=["e1"])
        result = sm.recall("key1")
        assert result == "updated"

    def test_store_complex_value(self, sm: StrategicMemory) -> None:
        """Almacenar dicts y listas como valor."""
        complex_val = {"nested": [1, 2, 3], "flag": True, "text": "data"}
        sm.store("complex", complex_val, tags=["json"])
        result = sm.recall("complex")
        assert result == complex_val

    def test_store_none_value(self, sm: StrategicMemory) -> None:
        """Almacenar value=None es valido."""
        sm.store("null_key", None)
        assert sm.recall("null_key") is None


# ===========================================================================
# Tests: Recall de clave inexistente
# ===========================================================================


class TestRecallNonexistent:
    """Recuperar claves que no existen en StrategicMemory."""

    def test_recall_nonexistent(self, sm: StrategicMemory) -> None:
        """Recall de clave no almacenada retorna None."""
        assert sm.recall("no_such_key") is None

    def test_recall_empty_store(self, sm: StrategicMemory) -> None:
        """Recall en memoria vacia retorna None."""
        assert sm.recall("anything") is None

    def test_contains_false(self, sm: StrategicMemory) -> None:
        """contains retorna False para clave inexistente."""
        assert sm.contains("ghost") is False

    def test_contains_true(self, sm: StrategicMemory) -> None:
        """contains retorna True para clave existente."""
        sm.store("present", "value")
        assert sm.contains("present") is True


# ===========================================================================
# Tests: Busqueda por tags y entidades
# ===========================================================================


class TestSearchByTags:
    """Busqueda de items por etiquetas semanticas y entidades."""

    def test_search_by_tags_match(self, sm: StrategicMemory) -> None:
        """search_by_tags encuentra items con etiquetas coincidentes."""
        sm.store("a", 1, tags=["urgente", "importante"])
        sm.store("b", 2, tags=["urgente"])
        sm.store("c", 3, tags=["info"])
        results = sm.search_by_tags(["urgente"])
        assert len(results) == 2

    def test_search_by_tags_no_match(self, sm: StrategicMemory) -> None:
        """search_by_tags sin coincidencias retorna lista vacia."""
        sm.store("only", "val", tags=["alpha"])
        assert sm.search_by_tags(["beta"]) == []

    def test_search_by_tags_multiple_or(self, sm: StrategicMemory) -> None:
        """search_by_tags usa OR logico entre etiquetas."""
        sm.store("x", "x", tags=["a"])
        sm.store("y", "y", tags=["b"])
        sm.store("z", "z", tags=["c"])
        results = sm.search_by_tags(["a", "b"])
        assert len(results) == 2

    def test_search_by_entities(self, sm: StrategicMemory) -> None:
        """search_by_entities encuentra items por entidades compartidas."""
        sm.store("e1", 10, entities=["usuario", "sesion_1"])
        sm.store("e2", 20, entities=["usuario"])
        sm.store("e3", 30, entities=["admin"])
        results = sm.search_by_entities(["usuario"])
        assert len(results) == 2
        results_admin = sm.search_by_entities(["admin"])
        assert len(results_admin) == 1


# ===========================================================================
# Tests: Olvido estrategico (utility-driven eviction)
# ===========================================================================


class TestStrategicForgetting:
    """Olvido estrategico basado en puntaje de utilidad."""

    def test_forget_evicts_low_utility(self, sm_small: StrategicMemory) -> None:
        """Al superar max_items se eliminan los items de menor utilidad."""
        # max_items=3; insertar 5 items
        for i in range(5):
            sm_small.store(f"key{i}", i, tags=["baja"])
        # Deben quedar solo 3 items
        stats = sm_small.get_stats()
        assert stats["total_items"] == 3

    def test_forget_keeps_high_importance(self, sm_small: StrategicMemory) -> None:
        """Items con alta importancia/access_count sobreviven al olvido."""
        sm_small.store("keeper", "valioso", tags=["critico"])
        # Re-acceder para subir importancia
        sm_small.recall("keeper")
        sm_small.recall("keeper")
        sm_small.recall("keeper")

        # Llenar hasta forzar olvido
        for i in range(5):
            sm_small.store(f"filler{i}", i, tags=["baja"])

        # keeper debe sobrevivir por su alta importancia + accesos
        assert sm_small.contains("keeper")
        assert sm_small.recall("keeper") == "valioso"

    def test_forget_keeps_items_with_entities(self, sm_small: StrategicMemory) -> None:
        """Items con entidades compartidas tienen mayor utilidad."""
        sm_small.store("con_entidad", "data", entities=["e1", "e2"], tags=["t1"])
        sm_small.store("sin_entidad", "data", tags=["t1"])

        # Re-acceder a con_entidad una vez
        sm_small.recall("con_entidad")

        # Llenar hasta forzar olvido
        for i in range(5):
            sm_small.store(f"filler{i}", i)

        # Debe sobrevivir con_entidad por tener mas diversidad de entidades
        assert sm_small.contains("con_entidad")

    def test_forget_empty_does_nothing(self, sm: StrategicMemory) -> None:
        """forget no debe fallar cuando la memoria esta vacia."""
        # Acceder directamente al metodo interno
        sm._forget()  # No debe lanzar excepcion
        assert sm.get_stats()["total_items"] == 0

    def test_forget_exact_capacity(self, sm: StrategicMemory) -> None:
        """Con exactamente max_items no se debe olvidar nada."""
        for i in range(10):
            sm.store(f"key{i}", i)
        stats = sm.get_stats()
        assert stats["total_items"] == 10


# ===========================================================================
# Tests: Actualizacion de importancia por re-acceso
# ===========================================================================


class TestImportanceUpdate:
    """El puntaje de importancia se actualiza con cada recall."""

    def test_importance_increases_on_recall(self, sm: StrategicMemory) -> None:
        """Cada recall incrementa importance_score hasta 1.0."""
        sm.store("imp", "value")
        initial = sm._items["imp"].importance_score

        # Varios re-accesos
        for _ in range(5):
            sm.recall("imp")

        final = sm._items["imp"].importance_score
        assert final > initial
        assert final <= 1.0

    def test_importance_caps_at_one(self, sm: StrategicMemory) -> None:
        """importance_score no supera 1.0 por muchos accesos."""
        sm.store("cap", "val")
        # Forzar importancia al maximo
        sm._items["cap"].importance_score = 0.99
        for _ in range(10):
            sm.recall("cap")
        assert sm._items["cap"].importance_score == 1.0

    def test_access_count_increments(self, sm: StrategicMemory) -> None:
        """access_count refleja el numero de recalls."""
        sm.store("cnt", "val")
        for _ in range(3):
            sm.recall("cnt")
        assert sm._items["cnt"].access_count == 3

    def test_last_accessed_updates(self, sm: StrategicMemory) -> None:
        """last_accessed se actualiza en cada recall."""
        sm.store("ts", "val")
        t1 = sm._items["ts"].last_accessed
        time.sleep(0.01)
        sm.recall("ts")
        t2 = sm._items["ts"].last_accessed
        assert t2 > t1


# ===========================================================================
# Tests: Estadisticas (get_stats)
# ===========================================================================


class TestStats:
    """Estadisticas de StrategicMemory."""

    def test_stats_empty(self, sm: StrategicMemory) -> None:
        """Memoria vacia tiene stats en cero y top_tags vacio."""
        stats = sm.get_stats()
        assert stats["total_items"] == 0
        assert stats["max_items"] == 10
        assert stats["avg_importance"] == 0.0
        assert stats["top_tags"] == []

    def test_stats_with_data(self, sm: StrategicMemory) -> None:
        """Stats reflejan los items almacenados."""
        sm.store("a", 1, tags=["urgente", "importante"])
        sm.store("b", 2, tags=["urgente"])
        sm.store("c", 3, tags=["info"])
        sm.recall("a")
        sm.recall("b")

        stats = sm.get_stats()
        assert stats["total_items"] == 3
        assert stats["max_items"] == 10
        assert stats["avg_importance"] > 0.0
        assert "urgente" in stats["top_tags"]

    def test_stats_avg_importance_precision(self, sm: StrategicMemory) -> None:
        """avg_importance se calcula con 4 decimales de precision."""
        sm.store("x", 1)
        sm.store("y", 2)
        stats = sm.get_stats()
        # Ambos importance_score = 0.5 inicial
        assert stats["avg_importance"] == 0.5


# ===========================================================================
# Tests: Persistencia a disco (save/load)
# ===========================================================================


class TestPersistence:
    """Persistencia save/load desde archivo JSON."""

    def test_save_creates_file(self, tmp_path: Path) -> None:
        """store escribe el archivo JSON en disco."""
        path = tmp_path / "persist.json"
        sm = StrategicMemory(max_items=10, path=path)
        sm.store("k", "v", tags=["tag1"], entities=["e1"])
        assert path.exists()
        content = json.loads(path.read_text(encoding="utf-8"))
        assert "k" in content
        assert content["k"]["value"] == "v"
        assert content["k"]["semantic_tags"] == ["tag1"]
        assert content["k"]["entities"] == ["e1"]

    def test_load_restores_data(self, tmp_path: Path) -> None:
        """Cargar desde archivo existente restaura items y metadatos."""
        path = tmp_path / "restore.json"

        # Primera instancia guarda datos
        sm1 = StrategicMemory(max_items=10, path=path)
        sm1.store("a", 1, tags=["alpha"], entities=["ea"])
        sm1.store("b", 2, tags=["beta"])
        sm1.recall("a")
        del sm1

        # Segunda instancia carga los mismos datos
        sm2 = StrategicMemory(max_items=10, path=path)
        assert sm2.recall("a") == 1
        assert sm2.recall("b") == 2
        assert sm2._items["a"].semantic_tags == ["alpha"]
        assert sm2._items["a"].entities == ["ea"]
        assert sm2._items["a"].access_count >= 1
        stats = sm2.get_stats()
        assert stats["total_items"] == 2

    def test_load_nonexistent_file(self, tmp_path: Path) -> None:
        """Cargar desde archivo inexistente inicia memoria vacia."""
        path = tmp_path / "nonexistent.json"
        sm = StrategicMemory(max_items=10, path=path)
        assert sm.get_stats()["total_items"] == 0

    def test_load_corrupted_file(self, tmp_path: Path) -> None:
        """Archivo corrupto no rompe la carga (inicia vacio y no explota)."""
        path = tmp_path / "corrupt.json"
        path.write_text("{not valid json}", encoding="utf-8")
        sm = StrategicMemory(max_items=10, path=path)
        assert sm.get_stats()["total_items"] == 0

    def test_save_and_clear(self, tmp_path: Path) -> None:
        """clear elimina items y persiste el estado vacio."""
        path = tmp_path / "clear.json"
        sm = StrategicMemory(max_items=10, path=path)
        sm.store("x", 1, tags=["t"])
        sm.clear()
        assert sm.recall("x") is None
        assert sm.get_stats()["total_items"] == 0
        # Archivo persistido debe reflejar vacio
        content = json.loads(path.read_text(encoding="utf-8"))
        assert content == {}

    def test_roundtrip_complex_value(self, tmp_path: Path) -> None:
        """Valores complejos (dict/anidados) sobreviven al ciclo save/load."""
        path = tmp_path / "roundtrip.json"
        complex_val = {"level1": {"level2": [1, 2, 3]}, "flag": False}

        sm1 = StrategicMemory(max_items=10, path=path)
        sm1.store("complex", complex_val, tags=["anidado"])
        del sm1

        sm2 = StrategicMemory(max_items=10, path=path)
        restored = sm2.recall("complex")
        assert restored == complex_val


# ===========================================================================
# Tests: Edge cases y validacion
# ===========================================================================


class TestEdgeCases:
    """Casos borde de StrategicMemory."""

    def test_invalid_max_items(self, tmp_path: Path) -> None:
        """max_items < 1 debe lanzar ValueError."""
        with pytest.raises(ValueError, match="max_items debe ser >= 1"):
            StrategicMemory(max_items=0, path=tmp_path / "invalid.json")

    def test_non_serializable_value(self, sm: StrategicMemory) -> None:
        """Almacenar valor no JSON-serializable lanza TypeError."""

        class NonSerializable:
            pass

        with pytest.raises(TypeError, match="no es JSON-serializable"):
            sm.store("bad", NonSerializable())

    def test_search_by_tags_empty_list(self, sm: StrategicMemory) -> None:
        """search_by_tags con lista vacia retorna lista vacia."""
        sm.store("a", 1, tags=["tag"])
        assert sm.search_by_tags([]) == []

    def test_search_by_entities_empty_list(self, sm: StrategicMemory) -> None:
        """search_by_entities con lista vacia retorna lista vacia."""
        sm.store("a", 1, entities=["e1"])
        assert sm.search_by_entities([]) == []

    def test_key_with_special_chars(self, sm: StrategicMemory) -> None:
        """Claves con caracteres especiales funcionan correctamente."""
        special_key = "path/with:slashes and spaces"
        sm.store(special_key, "val")
        assert sm.recall(special_key) == "val"
        assert sm.contains(special_key)

    def test_clear_empty(self, sm: StrategicMemory) -> None:
        """clear en memoria vacia no debe fallar."""
        sm.clear()  # No debe lanzar excepcion
        assert sm.get_stats()["total_items"] == 0

    def test_max_items_default(self) -> None:
        """El valor por defecto de max_items es 1000."""
        with patch.object(StrategicMemory, "_load", lambda self: None):
            sm = StrategicMemory()
            assert sm._max_items == 1000

    def test_default_path(self) -> None:
        """El path por defecto es data/strategic_memory.json."""
        with patch.object(StrategicMemory, "_load", lambda self: None):
            sm = StrategicMemory()
            assert str(sm._path) == "data\\strategic_memory.json"
