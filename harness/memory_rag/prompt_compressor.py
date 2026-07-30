"""PromptCompressor — Core orchestration of prompt compression.

Arquitectura Hexagonal:
- Core: PromptCompressor (orquestador con API publica)
- Strategies: CompressionStrategies (implementaciones en compression_strategies.py)
- Types: CompressionResult, TokenBudget (en compression_types.py)
"""

from __future__ import annotations

import logging
import re
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from harness.memory_rag.compression_types import (
    CompressionResult, TokenBudget,
    DEFAULT_TARGET_RATIO, DEFAULT_MAX_CONTEXT_TOKENS,
)
from harness.memory_rag.compression_strategies import CompressionStrategies

logger = logging.getLogger(__name__)


class PromptCompressor(CompressionStrategies):
    """Motor de compresion de prompts multi-estrategia.

    Orquesta multiples estrategias de compresion para reducir tokens
    en prompts de sistema, conversaciones y documentos estructurados.

    Args:
        default_ratio: Ratio de compresion por defecto [0,1].
        max_context_tokens: Maximo de tokens de contexto.
        cache_size: Tamano del cache LRU (0 = sin cache).
    """

    def __init__(
        self,
        default_ratio: float = DEFAULT_TARGET_RATIO,
        max_context_tokens: int = DEFAULT_MAX_CONTEXT_TOKENS,
        cache_size: int = 50,
    ) -> None:
        """Inicializa el compresor.

        Args:
            default_ratio: Ratio de compresion por defecto.
            max_context_tokens: Limite de tokens de contexto.
            cache_size: Tamano del cache LRU.

        Raises:
            ValueError: Si default_ratio fuera [0,1].
        """
        if not 0.0 <= default_ratio <= 1.0:
            raise ValueError(
                f"[PromptCompressor] default_ratio={default_ratio} fuera de [0,1]. "
                f"WHERE: __init__."
            )
        self._default_ratio: float = default_ratio
        self._max_context_tokens: int = max(max_context_tokens, 512)
        self._cache: Dict[str, CompressionResult] = {}
        self._cache_max: int = cache_size
        self._stats: Dict[str, int] = {
            "total_compressions": 0,
            "extractive_count": 0,
            "abstractive_count": 0,
            "structured_count": 0,
        }
        # Try to use tiktoken for accurate token counting
        self._use_tiktoken: bool = False
        try:
            import tiktoken
            self._tiktoken_enc = tiktoken.get_encoding("cl100k_base")
            self._use_tiktoken = True
        except ImportError:
            self._tiktoken_enc = None
        # Estrategias de compresion (usadas por CompressionStrategies)
        self._method_fallback: str = "extractive"
        self._current_original: str = ""
        self._current_ratio: float = default_ratio

    def compress(
        self,
        text: str,
        target_ratio: Optional[float] = None,
        method: str = "auto",
    ) -> CompressionResult:
        """Comprime un texto usando la mejor estrategia disponible.

        Args:
            text: Texto a comprimir.
            target_ratio: Ratio objetivo. Usa default_ratio si None.
            method: Estrategia: 'extractive', 'abstractive', 'auto'.

        Returns:
            CompressionResult con texto comprimido y metricas.
        """
        ratio: float = target_ratio if target_ratio is not None else self._default_ratio
        if not text:
            return CompressionResult(
                original_tokens=0, compressed_tokens=0, ratio=1.0,
                text="", method=method,
            )

        # Cache check
        cache_key: str = f"{hash(text)}_{ratio}_{method}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        original_tokens: int = self._count_tokens(text)
        actual_method: str = method if method != "auto" else self._detect_best_method(text, ratio)

        if actual_method == "extractive":
            compressed: str = self.extractive_compress(text, ratio)
            self._stats["extractive_count"] += 1
        else:
            compressed = self.abstractive_compress(text, ratio)
            self._stats["abstractive_count"] += 1

        compressed_tokens: int = self._count_tokens(compressed)
        actual_ratio: float = compressed_tokens / original_tokens if original_tokens > 0 else 1.0

        result: CompressionResult = CompressionResult(
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            ratio=actual_ratio,
            text=compressed,
            method=actual_method,
        )

        # Cache management
        self._stats["total_compressions"] += 1
        if self._cache_max > 0:
            self._cache[cache_key] = result
            if len(self._cache) > self._cache_max:
                self._cache.pop(next(iter(self._cache)))

        return result

    def extractive_compress(self, text: str, ratio: float = 0.5) -> str:
        """Compresion extractiva: elimina redundancia preservando informacion.

        Args:
            text: Texto a comprimir.
            ratio: Ratio objetivo [0,1].

        Returns:
            Texto comprimido.
        """
        text = self._normalize_whitespace(text)
        text = self._replace_filler_phrases(text)
        text = self._remove_stop_words(text)

        target_tokens: int = max(1, int(self._count_tokens(text) * ratio))
        if self._count_tokens(text) <= target_tokens:
            return text

        # Agresividad progresiva
        text = self._aggressive_extractive(text)
        return self._enforce_target_ratio(text, text, ratio)

    def abstractive_compress(self, text: str, ratio: float = 0.5) -> str:
        """Compresion abstractiva: resume secciones preservando informacion clave.

        Args:
            text: Texto a comprimir.
            ratio: Ratio objetivo [0,1].

        Returns:
            Texto comprimido.
        """
        if self._count_tokens(text) <= 50:
            return text

        sections: List[str] = self._split_into_sections(text)
        budget: int = max(1, int(self._count_tokens(text) * ratio))
        budgets: List[int] = self._distribute_budget_proportional(sections, budget)

        compressed_sections: List[str] = []
        for section, sec_budget in zip(sections, budgets):
            if self._is_critical_section(section):
                compressed_sections.append(section)
            else:
                summarized: str = self._summarize_section(section, sec_budget)
                compressed_sections.append(summarized)

        result: str = "\n".join(compressed_sections)
        return self._enforce_target_ratio(text, result, ratio)

    def compress_system_prompt(self, prompt: str, max_tokens: int = 1500) -> str:
        """Comprime un system prompt preservando reglas y rol.

        Args:
            prompt: System prompt a comprimir.
            max_tokens: Maximo de tokens deseado.

        Returns:
            System prompt comprimido.
        """
        lines: List[str] = prompt.split("\n")
        preserved: List[str] = []
        compressed: List[str] = []

        for line in lines:
            if self._is_critical_section(line) or self._has_preserved_keywords(line):
                preserved.append(line)
            else:
                compressed.append(line)

        base: str = "\n".join(preserved)
        current_tokens: int = self._count_tokens(base)
        remaining: int = max_tokens - current_tokens

        if remaining > 0:
            extra: str = "\n".join(compressed)
            extra_compressed: str = self._aggressive_extractive(extra)
            extra_truncated: str = extra_compressed[:remaining * 4]
            base = base + "\n" + extra_truncated if extra_truncated else base

        return base[:max_tokens * 4]

    def compress_conversation(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 4000,
        preserve_system: bool = True,
    ) -> List[Dict[str, str]]:
        """Comprime una conversacion multi-turno.

        Args:
            messages: Lista de mensajes {role, content}.
            max_tokens: Maximo de tokens total.
            preserve_system: Preservar mensajes system.

        Returns:
            Lista de mensajes comprimidos.
        """
        if not messages:
            return messages

        # Preservar system messages
        system_msgs: List[Dict[str, str]] = []
        other_msgs: List[Dict[str, str]] = []
        for msg in messages:
            if preserve_system and msg.get("role") == "system":
                system_msgs.append(msg)
            else:
                other_msgs.append(msg)

        system_tokens: int = sum(self._count_tokens(m.get("content", "")) for m in system_msgs)
        remaining: int = max(64, max_tokens - system_tokens)

        # Comprimir mensajes del centro (preservar primero y ultimo)
        if len(other_msgs) > 4:
            head: List[Dict[str, str]] = other_msgs[:2]
            tail: List[Dict[str, str]] = other_msgs[-2:]
            middle: List[Dict[str, str]] = other_msgs[2:-2]

            for msg in middle:
                content: str = msg.get("content", "")
                compressed: str = self._aggressive_extractive(content)
                msg["content"] = compressed[:100]

            other_msgs = head + middle + tail

        # Presupuesto proporcional
        total_other: int = sum(self._count_tokens(m.get("content", "")) for m in other_msgs)
        if total_other > remaining:
            ratio: float = remaining / total_other if total_other > 0 else 1.0
            for msg in other_msgs:
                content = msg.get("content", "")
                target: int = max(10, int(self._count_tokens(content) * ratio))
                if self._count_tokens(content) > target:
                    msg["content"] = self._aggressive_extractive(content)[:target * 4]

        return system_msgs + other_msgs

    def allocate_budget(
        self,
        sections: Dict[str, str],
        total_tokens: int,
    ) -> TokenBudget:
        """Asigna presupuesto de tokens entre secciones.

        Args:
            sections: Mapa de nombre -> contenido.
            total_tokens: Tokens totales disponibles.

        Returns:
            TokenBudget con asignacion por seccion.
        """
        total: int = sum(self._count_tokens(v) for v in sections.values())
        if total == 0:
            return TokenBudget(total=total_tokens, used=0, remaining=total_tokens)

        budgets: Dict[str, int] = {}
        used: int = 0
        for name, content in sections.items():
            proportion: float = self._count_tokens(content) / total
            allocated: int = max(10, int(total_tokens * proportion))
            budgets[name] = allocated
            used += allocated

        remaining: int = max(0, total_tokens - used)
        return TokenBudget(
            total=total_tokens,
            used=used,
            remaining=remaining,
            sections=budgets,
        )

    def get_stats(self) -> Dict[str, int]:
        """Retorna estadisticas de compresion.

        Returns:
            Dict con total_compressions, extractive_count, etc.
        """
        return dict(self._stats)

    def clear_cache(self) -> int:
        """Limpia el cache interno.

        Returns:
            Numero de entradas eliminadas.
        """
        count: int = len(self._cache)
        self._cache.clear()
        return count
