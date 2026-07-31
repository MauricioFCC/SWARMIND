"""CCR reversible — Compress-Cache-Retrieve (Headroom, ADR-0033).

Capa reversible sobre ``structured_compact`` (harness.memory_rag.compaction):
el original se cachea en disco como JSON y se recupera por hash, con busqueda
BM25-like opcional. No modifica ``compaction.py``; lo importa y reutiliza
(DRY).
"""

from __future__ import annotations

import hashlib
import json
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from harness.memory_rag.compaction import structured_compact

logger = logging.getLogger(__name__)

RETRIEVE_MARKER = "swarmind_retrieve"
_HASH_LEN = 12
_TOP_K_DEFAULT = 5

_KEY_HASH = "hash"
_KEY_ORIGINAL = "original"
_KEY_CREATED = "created_at"


def _hash_id(text: str) -> str:
    """Calcula el id legible SHA-256 (primeros 12 caracteres) de un texto.

    Args:
        text: Texto a hashear.

    Returns:
        Primeros 12 caracteres hexadecimales del SHA-256 del texto.
    """
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return digest[:_HASH_LEN]


def bm25_like_search(original: str, query: str, top_k: int = 5) -> list[str]:
    """Busqueda BM25-like simple: puntua lineas por tokens de query presentes.

    Tokeniza la query en palabras (lowercase) y puntua cada linea del original
    por el numero de tokens de query que aparecen en ella. Retorna las lineas
    mejor puntuadas; en caso de empate se conserva el orden original. Si
    ninguna linea coincide, retorna las primeras ``top_k`` lineas.

    Args:
        original: Texto sobre el que buscar.
        query: Consulta; se tokeniza por espacios en minusculas.
        top_k: Numero maximo de lineas a retornar.

    Returns:
        Lista de lineas relevantes (subconjunto de las lineas del original).
    """
    lines = original.splitlines()
    tokens = [tok.lower() for tok in query.split() if tok.strip()]
    if not original or not tokens:
        return lines[:top_k]

    scored: list[tuple[int, int, str]] = []
    for idx, line in enumerate(lines):
        line_lower = line.lower()
        matches = sum(1 for tok in tokens if tok in line_lower)
        if matches > 0:
            scored.append((matches, idx, line))

    if not scored:
        return lines[:top_k]

    scored.sort(key=lambda item: (-item[0], item[1]))
    return [line for _, _, line in scored[:top_k]]


class ReversibleCompactor:
    """CCR reversible: compacta, cachea el original y permite recuperarlo.

    Extiende ``structured_compact`` anadiendo reversibilidad: el texto
    compactado lleva un marcador con el hash y el original queda cacheado en
    JSON para recuperacion byte-exacta o busqueda BM25-like.
    """

    def __init__(self, cache_dir: str | Path | None = None) -> None:
        """Inicializa el compactor y garantiza que exista el directorio de cache.

        Args:
            cache_dir: Directorio para el cache JSON. Si es None se crea un
                directorio temporal del sistema.

        Returns:
            None.
        """
        if cache_dir is None:
            cache_dir = tempfile.mkdtemp(prefix="swarmind_ccr_")
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._retrievals = 0
        self._hits = 0
        self._misses = 0

    # ------------------------------------------------------------------
    # Compress
    # ------------------------------------------------------------------

    def compact(
        self,
        text: str,
        budget_ratio: float = 0.6,
        min_chars: int = 50,
    ) -> tuple[str, str, str]:
        """Compacta el texto, cachea el original y retorna (compacto, hash, original).

        Compress-Cache-Retrieve:
        1. Calcula el hash SHA-256 (id de 12 caracteres) del original.
        2. Si el texto es corto (< min_chars) no cachea y retorna el texto tal
           cual (tercer elemento igual al texto).
        3. En caso contrario cachea el original en ``{hash}.json`` y compacta
           con ``structured_compact`` anadiendo el marcador de recuperacion.

        Args:
            text: Texto a compactar.
            budget_ratio: Fraccion del original a mantener al compactar.
            min_chars: Umbral de longitud; textos mas cortos no se cachean.

        Returns:
            Tupla (texto_compacto, hash, original_cacheado).
        """
        hash_id = _hash_id(text)
        if not text or len(text) < min_chars:
            return text, hash_id, text

        self._cache_original(hash_id, text)
        compacted = structured_compact(text, budget_ratio, min_chars)
        marker = f"[Comprimido. Recupera con: {RETRIEVE_MARKER}({hash_id}, <query>)]"
        if compacted.endswith("\n"):
            return compacted + marker, hash_id, text
        return compacted + "\n" + marker, hash_id, text

    def _cache_original(self, hash_id: str, original: str) -> Path:
        """Persiste el original en ``{hash_id}.json`` (sobrescribe si existe).

        Args:
            hash_id: Hash del texto, usado como nombre de archivo.
            original: Texto original a persistir.

        Returns:
            Ruta del archivo de cache escrito.
        """
        path = self._cache_dir / f"{hash_id}.json"
        payload = {
            _KEY_HASH: hash_id,
            _KEY_ORIGINAL: original,
            _KEY_CREATED: datetime.now(timezone.utc).isoformat(),
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    # ------------------------------------------------------------------
    # Retrieve
    # ------------------------------------------------------------------

    def retrieve(self, hash_id: str, query: str = "") -> str | None:
        """Recupera el original por hash, con busqueda BM25-like opcional.

        Args:
            hash_id: Hash (id) del texto cacheado.
            query: Consulta opcional; si se provee, retorna las lineas mas
                relevantes del original en vez del texto completo.

        Returns:
            Original completo (sin query), lineas relevantes (con query) o
            None si el hash no existe en el cache.
        """
        self._retrievals += 1
        original = self._lookup(hash_id)
        if original is None:
            return None
        if query:
            return "\n".join(bm25_like_search(original, query, top_k=_TOP_K_DEFAULT))
        return original

    def retrieve_full(self, hash_id: str) -> str | None:
        """Recupera el original completo por hash.

        Args:
            hash_id: Hash (id) del texto cacheado.

        Returns:
            Texto original completo o None si el hash no existe.
        """
        self._retrievals += 1
        return self._lookup(hash_id)

    def _lookup(self, hash_id: str) -> str | None:
        """Busca el original en cache actualizando los contadores de stats.

        Args:
            hash_id: Hash del texto a buscar.

        Returns:
            Original cacheado, o None con log WHAT+WHY+WHERE si no existe.
        """
        original = self._read_original(hash_id)
        if original is None:
            self._misses += 1
            logger.warning(
                "WHAT: hash '%s' no encontrado en cache. "
                "WHY: el texto nunca fue compactado, el cache fue limpiado "
                "o el hash es invalido. WHERE: cache_dir=%s",
                hash_id,
                self._cache_dir,
            )
            return None
        self._hits += 1
        return original

    def _read_original(self, hash_id: str) -> str | None:
        """Lee el original desde el archivo de cache JSON.

        Args:
            hash_id: Hash (id) del archivo a leer.

        Returns:
            Texto original o None si el archivo no existe o esta corrupto.
        """
        path = self._cache_dir / f"{hash_id}.json"
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                "WHAT: archivo de cache '%s' ilegible o corrupto. "
                "WHY: %s. WHERE: path=%s",
                hash_id,
                exc,
                path,
            )
            return None
        return payload.get(_KEY_ORIGINAL)

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def stats(self) -> dict:
        """Resume las metricas del compactor.

        Returns:
            Dict con total_cached (archivos JSON en disco), total_retrievals,
            hits, misses y cache_size_bytes (suma del tamano de los archivos).
        """
        files = list(self._cache_dir.glob("*.json"))
        size_bytes = sum(path.stat().st_size for path in files)
        return {
            "total_cached": len(files),
            "total_retrievals": self._retrievals,
            "hits": self._hits,
            "misses": self._misses,
            "cache_size_bytes": size_bytes,
        }
