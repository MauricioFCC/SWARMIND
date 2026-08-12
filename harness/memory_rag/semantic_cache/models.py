"""Modelo de entrada de cache del paquete ``semantic_cache``.

Extraido mecanicamente de ``semantic_cache.py`` (regla AGR < 500 lineas).
Sin cambios de logica: misma dataclass, mismos campos y metodos.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .constants import DEFAULT_TTL_SECONDS


@dataclass
class CacheEntry:
    """A single cache entry."""

    prompt_hash: str
    prompt_text: str
    response: str
    agent_role: str
    similarity: float = 0.0
    hit_count: int = 1
    created_at: str = ""
    last_accessed: str = ""
    ttl_seconds: int = DEFAULT_TTL_SECONDS
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_expired(self) -> bool:
        """Check if this entry has exceeded its TTL."""
        if not self.created_at:
            return True
        try:
            created = datetime.fromisoformat(self.created_at)
            elapsed = (datetime.now(UTC) - created).total_seconds()
            return elapsed > self.ttl_seconds
        except (ValueError, TypeError):
            return True

    def to_dict(self) -> dict[str, Any]:
        """Serialize for LanceDB storage."""
        return {
            "prompt_hash": self.prompt_hash,
            "prompt_text": self.prompt_text[:500],  # truncar para storage
            "response": self.response,
            "agent_role": self.agent_role,
            "hit_count": self.hit_count,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
            "ttl_seconds": self.ttl_seconds,
            "metadata": json.dumps(self.metadata),
        }
