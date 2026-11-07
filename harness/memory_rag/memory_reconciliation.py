"""Reconciliacion periodica de memoria (SSGM, Lam et al. 2026).

El write gate valida en la frontera de escritura, pero una entrada legitima
puede volverse peligrosa despues (poisoning diferido, contenido editado fuera
de banda, duplicados que dispersan el ranking). SSGM demuestra que reconciliar
cada N pasos acota el drift a O(N*e) independientemente del horizonte.

Este modulo implementa el job:

  - re-evalua marcadores de injection sobre texto y metadata,
  - verifica ``content_hash`` (tamper detection),
  - detecta duplicados exactos (mismo hash) y marca los mas antiguos,
  - escribe ``reconciled_at``/``reconciliation_status`` en la metadata.

Es **reversible**: nada se borra; las entradas sospechosas pasan a cuarentena
(``trust_tier="quarantined"``), que el retrieval excluye por defecto.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReconciliationReport:
    """Resultado de una pasada de reconciliacion.

    Attributes:
        collection: Coleccion reconciliada.
        scanned: Entradas evaluadas.
        quarantined: Entradas puestas en cuarentena (injection/tamper).
        duplicates: Duplicados exactos marcados.
        ok: Entradas que pasaron sin cambios.
    """

    collection: str
    scanned: int
    quarantined: int
    duplicates: int
    ok: int


@dataclass
class ReconciliationState:
    """Contador de inserciones para disparar la reconciliacion cada N pasos."""

    every_n: int = 0
    counter: int = 0
    reports: list[ReconciliationReport] = field(default_factory=list)

    def should_run(self) -> bool:
        """Indica si toca reconciliar en este paso."""
        return self.every_n > 0 and self.counter >= self.every_n


def reconcile_collection(
    store: Any,
    collection: str,
    now: dt.datetime | None = None,
) -> ReconciliationReport:
    """Reconcilia una coleccion (injection, tamper y duplicados).

    Args:
        store: Store con ``entries`` y ``update_records``.
        collection: Coleccion a reconciliar.
        now: Instante de referencia (default UTC actual).

    Returns:
        ``ReconciliationReport`` con los conteos de la pasada.
    """
    from .ruscadb_store import _looks_like_injection

    reference = now or dt.datetime.now(dt.UTC)
    stamp = reference.isoformat()
    entries = list(store.entries(collection))
    seen_hashes: dict[str, str] = {}
    updates: list[dict[str, Any]] = []
    quarantined = 0
    duplicates = 0
    ok = 0
    for entry in entries:
        entry_id = entry.get("id")
        if not entry_id:
            continue
        meta = dict(entry.get("metadata") or {})
        text = str(entry.get("text") or "")
        current_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        declared = str(meta.get("content_hash") or "")
        suspicious = _looks_like_injection(text) or _looks_like_injection(str(meta))
        tampered = bool(declared) and declared != current_hash
        duplicate = current_hash in seen_hashes and not suspicious
        if suspicious or tampered:
            meta["trust_tier"] = "quarantined"
            meta["reconciliation_status"] = "quarantined"
            meta["write_gate_verdict"] = "quarantined"
            quarantined += 1
        elif duplicate:
            meta["reconciliation_status"] = "duplicate"
            duplicates += 1
        else:
            meta["reconciliation_status"] = "ok"
            ok += 1
        seen_hashes.setdefault(current_hash, str(entry_id))
        meta["content_hash"] = current_hash
        meta["reconciled_at"] = stamp
        updates.append(
            {
                "id": str(entry_id),
                "text": text,
                "metadata": meta,
            }
        )
    if updates:
        store.update_records(collection, updates)
    report = ReconciliationReport(
        collection=collection,
        scanned=len(entries),
        quarantined=quarantined,
        duplicates=duplicates,
        ok=ok,
    )
    logger.info(
        "reconciliacion '%s': %d evaluadas, %d cuarentena, %d duplicados",
        collection, report.scanned, report.quarantined, report.duplicates,
    )
    return report


__all__ = [
    "ReconciliationReport",
    "ReconciliationState",
    "reconcile_collection",
]
