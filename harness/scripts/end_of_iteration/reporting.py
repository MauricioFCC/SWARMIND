"""Persistencia de reportes de iteracion.

Submodulo interno del paquete :mod:`harness.scripts.end_of_iteration`.

Extraido de forma mecanica desde ``__init__.py`` (regla AGR: archivos
< 500 lineas). Define ``_save_report_to_lancedb`` y ``_save_report_to_json``.
Los cuerpos son identicos al original; solo cambia la ubicacion fisica del
codigo.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import UTC, datetime

from .config import HARNESS_ROOT, IterationReport, TokenReport, _ok, _safe_print, _warn


def _save_report_to_lancedb(report: IterationReport) -> bool:
    """Save the iteration report to LanceDB (best-effort, silent fail)."""
    import numpy as np
    try:
        sys.path.insert(1, str(HARNESS_ROOT.parent))
        from harness.memory_rag.lance_vector_store import LanceVectorStore

        store = LanceVectorStore()
        report_id = f"iter_{int(time.time())}"
        existing = store.list_collections()

        if "iteration_reports" not in existing:
            import lancedb
            import pyarrow as pa
            db_path = store._uri if hasattr(store, '_uri') else str(store._db_path)
            db = lancedb.connect(db_path)
            schema = pa.schema([
                ("vector", pa.list_(pa.float32(), 384)),
                ("id", pa.string()), ("timestamp", pa.string()),
                ("bugs_found", pa.int32()), ("bugs_fixed", pa.int32()),
                ("bugs_needs_review", pa.int32()), ("security_issues", pa.int32()),
                ("secrets_found", pa.int32()), ("docs_updated", pa.int32()),
                ("docs_stale", pa.int32()), ("token_input", pa.int32()),
                ("token_output", pa.int32()), ("costo_estimado", pa.float64()),
                ("eficiencia", pa.string()), ("commit_message_suggested", pa.string()),
                ("files_changed", pa.string()), ("elapsed_seconds", pa.float64()),
            ])
            db.create_table("iteration_reports", schema=schema, mode="overwrite")

        vector = np.ones((1, 384), dtype=np.float32) * 0.001
        metadata = {
            "id": report_id, "timestamp": report.timestamp,
            "bugs_found": report.bugs_found, "bugs_fixed": report.bugs_fixed,
            "bugs_needs_review": report.bugs_needs_review,
            "security_issues": report.security_issues,
            "secrets_found": report.secrets_found,
            "docs_updated": report.docs_updated, "docs_stale": report.docs_stale,
            "token_input": report.token_report.tokens_input_total if report.token_report else 0,
            "token_output": report.token_report.tokens_output_total if report.token_report else 0,
            "costo_estimado": report.token_report.costo_estimado_usd if report.token_report else 0.0,
            "eficiencia": json.dumps(report.token_report.eficiencia if report.token_report else {}),
            "commit_message_suggested": report.commit_message_suggested[:500],
            "files_changed": json.dumps(report.files_changed),
            "elapsed_seconds": report.elapsed_seconds,
        }
        store.insert("iteration_reports", vector, [metadata])
        return True
    except Exception:  # noqa: BLE001
        return False


def _save_report_to_json(report: IterationReport) -> bool:
    """Save the iteration report as JSON in harness/db/iteration_reports/."""
    from dataclasses import asdict
    reports_dir = HARNESS_ROOT / "db" / "iteration_reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(reports_dir.glob("report_*.json"))
    iter_num = len(existing) + 1
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    filename = f"report_{timestamp}_iter{iter_num:04d}.json"
    filepath = reports_dir / filename

    data = asdict(report)
    if data.get("token_report") and isinstance(data["token_report"], TokenReport):
        data["token_report"] = asdict(data["token_report"])

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        _safe_print(f"    {_ok('[OK]')} Reporte guardado: {filepath}")
        return True
    except Exception as exc:  # noqa: BLE001
        _safe_print(f"    {_warn('[WARN]')} No se pudo guardar reporte JSON: {exc}")
        return False
