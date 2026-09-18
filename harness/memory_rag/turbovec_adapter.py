"""turbovec_adapter.py — Adapter experimental turbovec (Search 9-13, ADR-0081).

WHAT: Busqueda vectorial con filtrado en tiempo de busqueda (allowlist de
paths) al estilo turbovec (Rust, TurboQuant: 10M docs en ~4GB, ingesta en
linea, guardados crash-safe). Graceful: sin binario -> no disponible.
WHY: Frontera — comprimir 10M docs en 4GB (vs 31GB float32) con allowlists
elimina ruido de documentos obsoletos sin re-embeddings; compañero ligero
de LanceDB para documentacion viva (SPECS/PLAN/ADRs).
WHERE: RAG de documentacion viva; `filter_allowlist` usable ya sin binario.

Uso:
    adapter = TurboVecAdapter()
    if adapter.available: hits = adapter.search("router", top_k=5)
    paths = filter_allowlist(all_paths, allow=("specs/", "plan/"))
"""

from __future__ import annotations

import logging
import shutil
import subprocess

logger = logging.getLogger("harness.memory_rag.turbovec_adapter")

#: Timeout de busqueda (segundos).
SEARCH_TIMEOUT_S = 30.0


def is_available() -> bool:
    """True si el binario turbovec esta en PATH.

    Returns:
        Disponibilidad del backend experimental.
    """
    return shutil.which("turbovec") is not None


def filter_allowlist(paths: list[str], allow: tuple[str, ...]) -> list[str]:
    """Filtra paths por prefijos allowlist (documentos objetivo/recientes).

    Args:
        paths: Rutas candidatas.
        allow: Prefijos permitidos (p. ej. ("specs/", "plan/")).

    Returns:
        Rutas que empiezan por algun prefijo (orden preservado).
    """
    return [p for p in paths if any(p.startswith(prefix) for prefix in allow)]


class TurboVecAdapter:
    """Adapter de busqueda turbovec con degradacion graceful.

    Args:
        timeout_s: Timeout de busqueda.
    """

    def __init__(self, timeout_s: float = SEARCH_TIMEOUT_S) -> None:
        """Inicializa el adapter (detecta disponibilidad).

        Args:
            timeout_s: Timeout por busqueda.
        """
        self._timeout_s = timeout_s
        self._available = is_available()
        if not self._available:
            logger.info(
                "turbovec_adapter: binario no disponible; busqueda no-op "
                "(experimental, ver ADR-0081)"
            )

    @property
    def available(self) -> bool:
        """True si el backend turbovec esta disponible."""
        return self._available

    def search(self, query: str, top_k: int = 5) -> list[str]:
        """Busca con turbovec (vacio si no disponible).

        Args:
            query: Consulta (no vacia).
            top_k: Maximo de hits.

        Returns:
            Paths matcheados (o [] sin binario).

        Raises:
            ValueError: Si la query esta vacia o top_k no positivo.
        """
        if not query.strip():
            raise ValueError(
                "WHAT: query vacia. "
                "WHY: sin consulta no hay busqueda. "
                "WHERE: TurboVecAdapter.search"
            )
        if top_k <= 0:
            raise ValueError(
                f"WHAT: top_k invalido: {top_k}. "
                "WHY: debe ser positivo. "
                "WHERE: TurboVecAdapter.search"
            )
        if not self._available:
            return []
        proc = subprocess.run(
            ["turbovec", "search", query, "--top-k", str(top_k)],
            capture_output=True, text=True,
            timeout=self._timeout_s, check=False,
        )
        return [line.strip() for line in proc.stdout.splitlines() if line.strip()][:top_k]
