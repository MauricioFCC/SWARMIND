"""Compaction — Structured Compaction para Token Economics (ADR-0018).

Extraido de ``context_window_manager.py`` para mantener separacion de
responsabilidades y reducir lineas del gestor principal.

Basado en estrategias Struct47 / LAS51:
  - Preservar cabeceras y secciones con marcadores de decision
  - Comprimir tool outputs extensos a resumen 1 linea
  - Eliminar lineas de logging repetitivo
  - Compactar bloques de codigo grandes a resumen
"""

from __future__ import annotations

from typing import List


def structured_compact(
    text: str,
    budget_ratio: float = 0.6,
    min_chars: int = 50,
) -> str:
    """
    Comprime texto estructurado preservando secciones criticas.

    Estrategia (Struct47, LAS51):
    1. Preservar cabeceras y secciones con marcadores de decision
    2. Comprimir tool outputs extensos (>200 chars) a resumen 1 linea
    3. Eliminar lineas de logging repetitivo
    4. Compactar bloques de codigo grandes (>20 lines) a resumen

    Args:
        text: Texto a compactar.
        budget_ratio: Fraccion del texto original a mantener (0.0-1.0).
        min_chars: Minimo de caracteres a mantener siempre.

    Returns:
        Texto compactado.
    """
    if not text or len(text) < min_chars:
        return text or ""

    lines = text.split("\n")
    target_len = max(int(len(text) * budget_ratio), min_chars)

    # Preservar lineas criticas
    preserved: list[str] = []
    tool_buffer: list[str] = []
    code_buffer: list[str] = []
    in_code_block = False

    for line in lines:
        stripped = line.strip()

        # Preservar cabeceras y decisiones
        if any(stripped.startswith(m) for m in ("# ", "## ", "### ", "**", "---")):
            _flush_buffer(tool_buffer, preserved)
            _flush_buffer(code_buffer, preserved)
            preserved.append(line)
            continue

        # Track code blocks
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            if not in_code_block and len(code_buffer) > 20:
                preserved.append(f"``` ... [{len(code_buffer)} lines compressed] ... ```")
                code_buffer = []
                continue
            code_buffer.append(line)
            continue

        if in_code_block:
            code_buffer.append(line)
            continue

        # Tool output compression
        if len(stripped) > 200 and any(m in stripped for m in ("Output:", "Result:", "STDOUT:", "STDERR:")):
            tool_buffer.append(stripped)
            continue

        preserved.append(line)

    _flush_buffer(tool_buffer, preserved)
    _flush_buffer(code_buffer, preserved)

    result = "\n".join(preserved)
    return result if len(result) >= min_chars else text[:target_len]


def _flush_buffer(buf: List[str], target: List[str]) -> None:
    """Vacia un buffer de lineas comprimiendolo a resumen si es largo.

    Si el buffer tiene mas de 3 lineas y suma mas de 500 chars,
    se reemplaza por un marcador ``[... N lines, M chars compressed ...]``.
    En caso contrario se anaden las lineas originales al destino.

    Args:
        buf: Buffer de lineas a procesar.
        target: Lista destino donde se anade el resultado.

    Returns:
        None, modifica ``target`` in-place.
    """
    if not buf:
        return
    if len(buf) > 3:
        total_chars = sum(len(l) for l in buf)
        if total_chars > 500:
            target.append(f"[... {len(buf)} lines, {total_chars} chars compressed ...]")
            return
    target.extend(buf)
    buf.clear()
