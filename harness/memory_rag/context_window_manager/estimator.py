"""Estimador de tokens para el paquete ``context_window_manager``.

Extraido mecanicamente de ``context_window_manager.py`` (regla AGR < 500
lineas). Contiene ``TokenEstimator`` con tokenizador real y cache LRU.
"""
from __future__ import annotations

import logging
from collections import OrderedDict
from typing import Any, ClassVar

logger = logging.getLogger("harness.memory_rag.context_window_manager")


# ---------------------------------------------------------------------------
# TokenEstimator
# ---------------------------------------------------------------------------

class TokenEstimator:
    """Estimador de tokens con tokenizador real y cache LRU.

    Soporta multiples familias de modelo y degradacion graceful
    si ``tiktoken`` no esta instalado.

    Uso:
        te = TokenEstimator(model_family="claude")
        tokens = te.count("texto a contar")
        truncado = te.truncate_to_token_limit("texto largo", max_tokens=100)
    """

    _ENCODING_MAP: ClassVar[dict[str, str]] = {
        "claude": "cl100k_base",
        "gpt-4": "gpt-4",
        "gemini": "cl100k_base",
        "llama": "cl100k_base",
    }

    def __init__(self, model_family: str = "claude") -> None:
        """Inicializa el estimador de tokens.

        Args:
            model_family: Familia de modelo ("claude", "gpt-4", "gemini", "llama").
        """
        self.model_family = model_family
        self._cache: OrderedDict[str, int] = OrderedDict()
        self._cache_maxsize = 2048
        self._encoder = self._init_encoder()
        self._warned: bool = False

    def _init_encoder(self) -> Any:
        """Inicializa el encoder tiktoken segun model_family.

        Returns:
            Encoder tiktoken, o None si no esta disponible.
        """
        try:
            import tiktoken  # type: ignore
            if self.model_family == "gpt-4":
                return tiktoken.encoding_for_model("gpt-4")
            encoding_name = self._ENCODING_MAP.get(
                self.model_family, "cl100k_base"
            )
            return tiktoken.get_encoding(encoding_name)
        except ImportError:
            logger.warning(
                "TokenEstimator: tiktoken no instalado, "
                "usando chars/4 como fallback"
            )
            return None
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "TokenEstimator: error inicializando encoder (%s), "
                "usando chars/4 como fallback", e
            )
            return None

    def count(self, text: str) -> int:
        """Cuenta tokens reales usando el tokenizador configurado.

        Resultados cacheados con LRU (max 2048 entradas).

        Args:
            text: Texto a contar.

        Returns:
            Numero estimado de tokens (minimo 1).
        """
        if not text:
            return 1

        if text in self._cache:
            self._cache.move_to_end(text)
            return self._cache[text]

        if self._encoder is not None:
            try:
                count = len(self._encoder.encode(text))
            except Exception:  # noqa: BLE001
                count = max(1, len(text) // 4)
        else:
            count = max(1, len(text) // 4)

        self._cache[text] = count
        if len(self._cache) > self._cache_maxsize:
            self._cache.popitem(last=False)

        return count

    def truncate_to_token_limit(self, text: str, max_tokens: int) -> str:
        """Trunca texto para que no exceda max_tokens.

        Args:
            text: Texto a truncar.
            max_tokens: Maximo de tokens permitidos (min 1).

        Returns:
            Texto truncado que cumple con el limite.
        """
        if not text or max_tokens < 1:
            return ""

        if self.count(text) <= max_tokens:
            return text

        lo, hi = 0, len(text)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self.count(text[:mid]) <= max_tokens:
                lo = mid
            else:
                hi = mid - 1

        return text[:lo]
