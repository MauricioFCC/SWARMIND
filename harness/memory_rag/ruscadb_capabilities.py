"""Informe de capacidades de RuscaDB: qué expone la DLL y qué usa Swarmind.

El C-ABI creció por SPECs (blobs, backup, 3VL, prepared, KNN USING...). Una DLL
antigua sigue funcionando porque ``ruscadb._bind_extended`` enlaza solo lo que
existe, pero el operador necesita **saber qué está aprovechando y qué no**.

Este módulo produce un informe determinista (sin red, sin escribir) con:
- símbolos del C-ABI detectados en la DLL cargada;
- features de Swarmind y qué símbolos requieren;
- faltantes y recomendación de rebuild.

Complejidad O(F·S) con F features y S símbolos (constantes pequeñas).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import ruscadb

#: Feature -> símbolos del C-ABI que necesita (vacío = implementada en el store).
FEATURES: dict[str, tuple[str, ...]] = {
    "sql_core": (),
    "vector_search": (),
    "full_text_search": (),
    "hybrid_search": (),
    "graph_traversal": (),
    "semantic_cache": (),
    "query_cache": (),
    "colbert_rerank": (),
    "timeseries": (),
    "async_io": (),
    "blob_store": ("ruscadb_put_blob", "ruscadb_get_blob", "ruscadb_gc_blobs"),
    "backup": ("ruscadb_backup",),
    "integrity_check": ("ruscadb_integrity_check",),
    "time_travel": ("ruscadb_execute_at",),
    "encryption": ("ruscadb_open_encrypted",),
    "alter_table": ("ruscadb_alter_table",),
    "explain": ("ruscadb_explain",),
    "lsn": ("ruscadb_last_lsn",),
    "binary_quantized": ("ruscadb_quantize", "ruscadb_search_bq"),
    "prepared_native": ("ruscadb_prepare", "ruscadb_execute_prepared"),
    "knn_filtered": ("ruscadb_search_filtered",),
    "knn_quantized": ("ruscadb_search_quantized",),
}


@dataclass(frozen=True)
class FeatureStatus:
    """Estado de una feature respecto de la DLL cargada."""

    name: str
    available: bool
    required: tuple[str, ...]
    missing: tuple[str, ...] = ()


@dataclass
class CapabilityReport:
    """Informe completo de capacidades de la DLL y su aprovechamiento."""

    dll: dict[str, bool] = field(default_factory=dict)
    features: dict[str, FeatureStatus] = field(default_factory=dict)

    @property
    def missing_symbols(self) -> list[str]:
        """Símbolos que la DLL no exporta (contrato extendido incompleto)."""
        return sorted({name for item in self.features.values() for name in item.missing})

    @property
    def available_features(self) -> list[str]:
        """Features aprovechables con la DLL actual."""
        return sorted(name for name, item in self.features.items() if item.available)

    def as_dict(self) -> dict[str, object]:
        """Vista serializable (para CLI/JSON)."""
        return {
            "missing_symbols": self.missing_symbols,
            "available_features": self.available_features,
            "features": {
                name: {
                    "available": item.available,
                    "missing": list(item.missing),
                }
                for name, item in sorted(self.features.items())
            },
        }


def probe(dll: dict[str, bool] | None = None) -> CapabilityReport:
    """Construye el informe de capacidades.

    Args:
        dll: Mapa símbolo->disponible (DI/tests); ``None`` consulta la DLL real.

    Returns:
        ``CapabilityReport`` con features y faltantes.
    """
    symbols = dll if dll is not None else ruscadb.capabilities()
    features: dict[str, FeatureStatus] = {}
    for name, required in FEATURES.items():
        missing = tuple(symbol for symbol in required if not symbols.get(symbol, False))
        features[name] = FeatureStatus(
            name=name,
            available=not missing,
            required=required,
            missing=missing,
        )
    return CapabilityReport(dll=dict(symbols), features=features)


def recommendations(report: CapabilityReport) -> list[str]:
    """Recomendaciones legibles según los símbolos faltantes."""
    missing = report.missing_symbols
    if not missing:
        return ["DLL al día: todo el contrato extendido está disponible."]
    return [
        "Faltan símbolos del C-ABI: " + ", ".join(missing),
        (
            "Recompila con `cargo build -p ruscadb-ffi` y copia la DLL "
            "(`python scripts/setup_swarmind.py`)."
        ),
        "Mientras tanto, Swarmind degrada las features afectadas sin romper.",
    ]
