"""Multi-Harness Adapter Layer — Compatibilidad con 5+ runtimes.

Permite que Swarmind funcione nativamente desde OpenCode, Claude Code, Codex CLI,
Cursor y Gemini CLI sin perder compatibilidad con .opencode/ como SSOT.
"""

from __future__ import annotations

from harness.orchestrator.multi_harness.converter_base import HarnessConverter
from harness.orchestrator.multi_harness.runtime_detector import (
    RuntimeInfo,
    detect_runtime,
    get_detected_runtimes,
)

__all__ = [
    "HarnessConverter",
    "RuntimeInfo",
    "detect_runtime",
    "get_detected_runtimes",
]
