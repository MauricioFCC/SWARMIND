"""compaction_pipeline.py — Compactacion en 2 fases: prune luego summarize (ADR-0077).

WHAT: Fase 1 evicta tool-results grandes a artifacts (preview + handle);
fase 2 compacta lo restante con structured_compact.
WHY: deepseek-harness (tool-result-pruner + compaction-basic): podar
outputs primero evita que el summarizer gaste atencion en ruido; el
resumen trabaja sobre senal densa. Orden: prune -> summarize, nunca al reves.
WHERE: Pipeline de compaction del orquestador antes de reanchor.

Uso:
    compacted = prune_then_summarize(session_text, budget_ratio=0.6)
"""

from __future__ import annotations

import logging

from harness.memory_rag.artifact_store import ArtifactStore
from harness.memory_rag.compaction import structured_compact

logger = logging.getLogger("harness.memory_rag.compaction_pipeline")

#: Lineas candidatas a eviction (tool outputs y logs largos).
_TOOL_LINE_MARKERS: tuple[str, ...] = ("tool result", "tool_result", "[tool")


def prune_then_summarize(
    session_text: str,
    budget_ratio: float = 0.6,
    store: ArtifactStore | None = None,
) -> str:
    """Evicta tool-results grandes a artifacts y compacta el resto.

    Args:
        session_text: Texto completo de la sesion (puede ser vacio).
        budget_ratio: Fraccion a mantener en la fase 2.
        store: ArtifactStore inyectable (default: uno nuevo en memoria).

    Returns:
        Texto compactado con previews+handles en lugar de outputs crudos.
    """
    active_store = store or ArtifactStore()
    kept_lines: list[str] = []
    for line in session_text.splitlines():
        lowered = line.lower()
        if any(marker in lowered for marker in _TOOL_LINE_MARKERS) and len(line) > 500:
            # Tool output largo: ruido por construccion -> evict forzado
            # (el threshold del store es para contenido general, no ruido).
            evicted = active_store.evict(line, force=True)
            kept_lines.append(evicted.inline if evicted.persisted else line)
        else:
            kept_lines.append(line)
    pruned = "\n".join(kept_lines)
    compacted = structured_compact(pruned, budget_ratio)
    logger.info(
        "compaction_pipeline: %d -> %d chars (prune+summarize)",
        len(session_text), len(compacted),
    )
    return compacted
