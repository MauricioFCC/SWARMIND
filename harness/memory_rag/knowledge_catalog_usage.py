"""Registro de uso del catálogo de conocimiento (ciclo de vida).

WHAT: append-only JSONL con cada consulta al catálogo y su resultado
(``useful``/``stale``/``missing``). Permite medir qué entradas se usan, cuáles
quedaron obsoletas y qué **gaps** hay que alimentar. Es el mecanismo que evita
que el catálogo se degrade: sin feedback, el conocimiento envejece y pierde
sentido.

WHY: mandato del usuario 2026-11-11 — el catálogo "siempre se debe consultar,
actualizar, mejorar, comentar; si no se alimenta pierde efectividad". El log
vive junto al índice en la memoria central (``Memory_Proyects/data/``).

WHERE: ``harness/memory_rag/knowledge_catalog_usage.py``; consumido por
``KnowledgeCatalog.record_usage``, ``scripts/knowledge_catalog.py feedback`` y
``gaps``.

Invariantes: append-only (nunca reescribe historia), tolerante a líneas
corruptas, sin datos personales (solo query/ids/nota).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

#: Resultados válidos de una consulta al catálogo.
OUTCOMES: frozenset[str] = frozenset({"useful", "stale", "missing"})
#: Nombre del JSONL de uso (hermano del índice del catálogo).
USAGE_FILE = "knowledge_catalog_usage.jsonl"


@dataclass(frozen=True)
class UsageRecord:
    """Una consulta registrada y su resultado.

    Args:
        query: Necesidad de conocimiento consultada.
        catalog_ids: Entradas devueltas (puede ser vacío en ``missing``).
        outcome: ``useful`` (aplicada), ``stale`` (obsoleta) o ``missing``
            (no había conocimiento: gap a alimentar).
        note: Comentario libre (qué faltó o cómo se aplicó).
        timestamp: ISO-8601 UTC del registro.
    """

    query: str
    catalog_ids: tuple[str, ...] = ()
    outcome: str = "useful"
    note: str = ""
    timestamp: str = ""

    def __post_init__(self) -> None:
        """Normaliza tuplas y valida el resultado."""
        object.__setattr__(self, "catalog_ids", tuple(self.catalog_ids))
        if self.outcome not in OUTCOMES:
            raise ValueError(
                f"WHAT: outcome '{self.outcome}' inválido. "
                f"WHY: solo se admite {sorted(OUTCOMES)}. "
                "WHERE: UsageRecord.outcome"
            )

    def to_dict(self) -> dict[str, object]:
        """Serializa el registro a un dict JSON."""
        return {
            "query": self.query,
            "catalog_ids": list(self.catalog_ids),
            "outcome": self.outcome,
            "note": self.note,
            "timestamp": self.timestamp
            or datetime.now(UTC).isoformat(timespec="seconds"),
        }


def usage_path(index_path: Path | None) -> Path | None:
    """Ruta del JSONL de uso, hermana del índice del catálogo.

    Args:
        index_path: Ruta del índice (``knowledge_catalog.index.json``).

    Returns:
        Ruta del JSONL, o ``None`` si el catálogo es en memoria.
    """
    if index_path is None:
        return None
    return index_path.with_name(USAGE_FILE)


def append_usage(path: Path, record: UsageRecord) -> Path:
    """Añade un registro al JSONL (crea el directorio si falta).

    Args:
        path: Ruta del JSONL.
        record: Registro a añadir.

    Returns:
        La misma ruta (para encadenar).

    Raises:
        OSError: Si no se puede escribir.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
    return path


def read_usage(path: Path | None) -> list[UsageRecord]:
    """Lee el JSONL de uso, ignorando líneas corruptas.

    Args:
        path: Ruta del JSONL (``None`` o inexistente => ``[]``).

    Returns:
        Registros válidos en orden de escritura.
    """
    if path is None or not path.is_file():
        return []
    registros: list[UsageRecord] = []
    for linea in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not linea.strip():
            continue
        try:
            dato = json.loads(linea)
            registros.append(
                UsageRecord(
                    query=str(dato.get("query", "")),
                    catalog_ids=tuple(dato.get("catalog_ids") or ()),
                    outcome=str(dato.get("outcome", "useful")),
                    note=str(dato.get("note", "")),
                    timestamp=str(dato.get("timestamp", "")),
                )
            )
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            logger.warning("uso del catálogo: línea ilegible ignorada (%s)", exc)
    return registros


def summarize_usage(records: list[UsageRecord], top: int = 5) -> dict[str, object]:
    """Resume el uso: total, por resultado, top de entradas y gaps abiertos.

    Args:
        records: Registros leídos del JSONL.
        top: Número de entradas/gaps a listar.

    Returns:
        Dict con ``total``, ``by_outcome``, ``top_ids`` y ``gaps``.
    """
    by_outcome: dict[str, int] = {}
    por_id: dict[str, int] = {}
    gaps: list[dict[str, str]] = []
    resueltas = {record.query for record in records if record.outcome == "useful"}
    for record in records:
        by_outcome[record.outcome] = by_outcome.get(record.outcome, 0) + 1
        for cid in record.catalog_ids:
            por_id[cid] = por_id.get(cid, 0) + 1
        if record.outcome == "missing" and record.query not in resueltas:
            gaps.append({"query": record.query, "note": record.note})
    top_ids = sorted(por_id.items(), key=lambda par: (-par[1], par[0]))[:top]
    return {
        "total": len(records),
        "by_outcome": dict(sorted(by_outcome.items())),
        "top_ids": [{"catalog_id": cid, "usos": usos} for cid, usos in top_ids],
        "gaps": gaps[-top:],
    }
