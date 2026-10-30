"""Tests del KNN binario RaBitQ (quantize + search_bq + tuning)."""

from __future__ import annotations

import numpy as np
import pytest

from harness.memory_rag.binary_tuning import OversampleTuner
from harness.memory_rag.ruscadb import capabilities, quantize
from harness.memory_rag.ruscadb_store import RuscaDBStore

try:
    from harness.memory_rag.ruscadb import load_library

    load_library()
    _RUSCADB_AVAILABLE = True
except Exception:  # noqa: BLE001
    _RUSCADB_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _RUSCADB_AVAILABLE, reason="RuscaDB C-ABI dll not available"
)

N = 24
DIM = 16


@pytest.fixture
def store(tmp_path):
    """Store con una coleccion de vectores gaussianos deterministas."""
    s = RuscaDBStore(db_path=str(tmp_path / "bq.db"))
    s.create_collection("vec")
    rng = np.random.default_rng(7)
    data = rng.normal(size=(N, DIM)).astype(np.float32)
    s.insert(
        "vec",
        data,
        [{"i": index} for index in range(N)],
        texts=[f"v{index}" for index in range(N)],
    )
    s._data = data
    yield s
    s.close()


def test_capabilities_expose_binary_search():
    """La DLL actual expone quantize, search_bq y alter_table."""
    caps = capabilities()
    assert caps["ruscadb_quantize"] is True
    assert caps["ruscadb_search_bq"] is True
    assert caps["ruscadb_alter_table"] is True


def test_quantize_code_len_and_norms(store):
    """code_len(384) = 48 B (32x) y las normas siguen la norma L2."""
    data = store._data[:3]
    codes, norms = quantize(data, DIM)
    assert len(codes) == 3 * (DIM // 8)
    expected = np.linalg.norm(data, axis=1)
    assert np.allclose(norms, expected, rtol=1e-4)


def test_search_binary_recall_with_full_oversample(store):
    """Con oversample suficiente el top-k coincide con el KNN exacto."""
    query = store._data[5]
    exact = store.search("vec", query, top_k=5)
    binary = store.search_binary("vec", query, top_k=5, oversample=N)
    assert [item["id"] for item in binary] == [item["id"] for item in exact]
    assert binary[0]["distance"] == pytest.approx(0.0, abs=1e-5)


def test_search_binary_is_deterministic(store):
    """Misma query -> mismos ids (desempate estable por id)."""
    query = store._data[3]
    runs = [
        [item["id"] for item in store.search_binary("vec", query, top_k=5, oversample=3)]
        for _ in range(3)
    ]
    assert runs[0] == runs[1] == runs[2]


def test_search_binary_falls_back_without_capability(store, monkeypatch):
    """Sin el simbolo degrada al KNN exacto con warning."""
    monkeypatch.setitem(store._caps, "ruscadb_search_bq", False)
    query = store._data[2]
    assert store.search_binary("vec", query, top_k=3) == store.search(
        "vec", query, top_k=3
    )


def test_search_binary_marks_quarantined_entries(store):
    """La gobernanza se aplica tambien al KNN binario."""
    store.insert(
        "vec",
        [[0.0] * DIM],
        [{"i": 99, "trust_tier": "quarantined"}],
        texts=["cuarentena"],
    )
    query = np.zeros(DIM, dtype=np.float32)
    visible = store.search_binary("vec", query, top_k=3, oversample=2)
    assert all(item["metadata"].get("i") != 99 for item in visible)
    audit = store.search_binary(
        "vec", query, top_k=3, oversample=2, allow_quarantined=True
    )
    assert any(item["metadata"].get("i") == 99 for item in audit)


def test_calibration_samples_and_updates_tuner(store):
    """Con calibracion activa se mide recall y se actualiza el tuner."""
    store._calibration_rate = 1.0
    query = store._data[9]
    store.search_binary("vec", query, top_k=5, oversample=1, calibrate=True)
    stats = store.binary_search_stats()
    assert stats["queries"] == 1
    assert stats["calibrations"] == 1
    assert stats["tuner"]["samples"]["vec"] == 1
    assert stats["tuner"]["values"]["vec"] >= 1


def test_tuner_value_used_when_oversample_is_none(store):
    """oversample=None toma el valor ajustado por el tuner."""
    store._oversample_tuner._values["vec"] = 4
    results = store.search_binary("vec", store._data[0], top_k=3)
    assert results
    assert results[0]["oversample"] == 4


def test_legacy_table_is_migrated_with_alter_table(tmp_path):
    """Una tabla legacy recibe las columnas de gobernanza via ALTER TABLE."""
    from harness.memory_rag.ruscadb import create_table

    store = RuscaDBStore(db_path=str(tmp_path / "migrate.db"))
    try:
        create_table(
            store._handle,
            "legacy",
            [
                {"name": "id", "type": "Text"},
                {"name": "text", "type": "Text"},
                {"name": "metadata", "type": "Text"},
                {"name": "created_at", "type": "Text"},
            ],
        )
        store._collections.add("legacy")
        store.insert(
            "legacy",
            [[1.0, 0.0]],
            [{"trust_tier": "user_stated", "session_id": "s-1"}],
            texts=["hola"],
        )
        raw = store.execute("SELECT * FROM legacy")
        assert "session_id" in raw
        assert "s-1" in raw
        assert "legacy" in store._governance_ready
        assert "legacy" not in store._legacy_tables
    finally:
        store.close()


def test_governance_indexes_are_opt_in(tmp_path, monkeypatch):
    """Los indices de gobernanza solo se crean si el consumidor los pide."""
    import harness.memory_rag.ruscadb_store as store_module

    calls: list[tuple[str, str]] = []

    def _spy(handle, collection, column):
        calls.append((collection, column))

    monkeypatch.setattr(store_module, "create_index", _spy)

    default = RuscaDBStore(db_path=str(tmp_path / "idx_off.db"))
    try:
        default.create_collection("sin_indices")
    finally:
        default.close()
    assert ("sin_indices", "trust_tier") not in calls

    calls.clear()
    opted = RuscaDBStore(db_path=str(tmp_path / "idx_on.db"), index_governance=True)
    try:
        opted.create_collection("con_indices")
    finally:
        opted.close()
    assert ("con_indices", "trust_tier") in calls
    assert ("con_indices", "session_id") in calls


def test_tuner_clamps_and_reacts():
    """El tuner sube con recall bajo y baja con recall alto (con topes)."""
    tuner = OversampleTuner(target_recall=0.9, min_oversample=1, max_oversample=4)
    assert tuner.value_for("c") == 1
    assert tuner.observe("c", 0.2) >= 2
    for _ in range(20):
        tuner.observe("c", 0.2)
    assert tuner.value_for("c") == 4
    for _ in range(40):
        tuner.observe("c", 1.0)
    assert tuner.value_for("c") == 1


def test_tuner_persists_value(store):
    """El oversample ajustado sobrevive a una nueva instancia."""
    tuner = OversampleTuner(store=store)
    for _ in range(10):
        tuner.observe("vec", 0.1)
    value = tuner.value_for("vec")
    assert value > 1

    reloaded = OversampleTuner(store=store)
    assert reloaded.value_for("vec") == value
