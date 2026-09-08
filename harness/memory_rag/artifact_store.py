"""artifact_store.py — Eviction de tool results grandes a disco (ADR-0074).

WHAT: Persiste tool results > threshold a JSON en disco y devuelve al
contexto un resumen compacto: primeras lineas + handle + tamano original.
WHY: Frontera 2026 (artifact-backed eviction, tier 1) — el observation
masking OCULTA (sin acceso); la eviction CONSERVA el acceso por handle
(offsets), manteniendo el contexto chico sin degradar al agente.
WHERE: Wrapper del tool executor; ``retrieve`` on-demand (con offset).

Uso:
    store = ArtifactStore()
    out = store.evict(big_tool_output)
    if out.persisted:
        tail = store.retrieve(out.handle, offset=10)
"""

from __future__ import annotations

import hashlib
import json
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("harness.memory_rag.artifact_store")

#: Umbral default (chars) para considerar un tool result "grande".
DEFAULT_THRESHOLD_CHARS = 4000
#: Lineas que se conservan inline como preview.
HEAD_LINES = 3
#: Sufijo del preview cuando se persiste.
PREVIEW_SUFFIX = "[artifact-persisted: use retrieve]"
_HASH_LEN = 12


@dataclass(frozen=True)
class EvictionResult:
    """Resultado de una eviction.

    Attributes:
        inline: Texto que entra al contexto (original o preview+handle).
        persisted: True si el contenido fue persistido a disco.
        handle: Identificador del artifact (vacio si no persistio).
        original_chars: Tamano del contenido original.
    """

    inline: str
    persisted: bool
    handle: str = ""
    original_chars: int = 0


def _handle_for(content: str) -> str:
    """Genera el handle (hash 12 chars) del contenido.

    Args:
        content: Contenido del tool result.

    Returns:
        Handle hexadecimal corto (determinista por contenido).
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:_HASH_LEN]


class ArtifactStore:
    """Store de artifacts en disco con preview + handle en contexto.

    Args:
        cache_dir: Directorio de persistencia (None -> tmp del sistema).
        threshold_chars: Umbral de eviction (chars).
    """

    def __init__(
        self,
        cache_dir: str | Path | None = None,
        threshold_chars: int = DEFAULT_THRESHOLD_CHARS,
    ) -> None:
        """Inicializa el store y garantiza el directorio de cache.

        Args:
            cache_dir: Ruta del directorio; None usa un tmp del sistema.
            threshold_chars: Umbral de chars para evictar.
        """
        if cache_dir is None:
            cache_dir = tempfile.mkdtemp(prefix="swarmind_artifacts_")
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._threshold = threshold_chars

    def evict(self, content: str, force: bool = False) -> EvictionResult:
        """Persiste el contenido si excede el umbral y retorna el preview.

        Args:
            content: Contenido crudo del tool result (puede ser vacio).
            force: Persistir aunque este bajo el umbral (testing).

        Returns:
            EvictionResult con el inline a insertar en contexto.
        """
        original = len(content)
        if not force and original <= self._threshold:
            return EvictionResult(inline=content, persisted=False, original_chars=original)
        handle = _handle_for(content)
        path = self._cache_dir / f"{handle}.json"
        payload = {
            "handle": handle,
            "content": content,
            "chars": original,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        head_lines = "\n".join(content.splitlines()[:HEAD_LINES])
        preview = (
            f"{head_lines}\n{PREVIEW_SUFFIX} handle={handle} "
            f"chars={original} (preview: primeras {HEAD_LINES} lineas)"
        )
        logger.info("artifact_store: evicted %d chars -> handle=%s", original, handle)
        return EvictionResult(
            inline=preview, persisted=True, handle=handle, original_chars=original
        )

    def retrieve(self, handle: str, offset: int = 0) -> str:
        """Recupera el contenido completo del artifact desde ``offset``.

        Args:
            handle: Identificador del artifact.
            offset: Linea inicial (0-based) para recupera desde ahi.

        Returns:
            Contenido desde la linea ``offset`` (completo si offset=0).

        Raises:
            FileNotFoundError: Si el handle no existe (WHAT+WHY+WHERE).
            ValueError: Si el offset es negativo.
        """
        if offset < 0:
            raise ValueError(
                f"WHAT: offset negativo ({offset}). "
                "WHY: los offsets son 0-based no negativos. "
                "WHERE: ArtifactStore.retrieve"
            )
        path = self._cache_dir / f"{handle}.json"
        if not path.is_file():
            raise FileNotFoundError(
                f"WHAT: artifact no encontrado: {handle}. "
                f"WHY: el handle no fue evitado en este store (o la cache fue "
                f"limpiada). WHERE: ArtifactStore.retrieve (dir={self._cache_dir})"
            )
        payload = json.loads(path.read_text(encoding="utf-8"))
        lines = str(payload.get("content", "")).splitlines()
        return "\n".join(lines[offset:])
