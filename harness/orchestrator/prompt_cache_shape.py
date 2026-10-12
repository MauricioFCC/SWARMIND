"""Cache-shape del prompt del coordinador (FR-A2, ADR-0103).

WHAT: ensambla el prompt en el orden canonico ``tools -> system -> static ->
dynamic`` e inserta un breakpoint de cache al final del prefijo estable.
WHY: los proveedores LLM cachean el PREFIJO del prompt. Si el contenido
estable (herramientas, identidad, doctrina) va primero y no cambia entre
llamadas, el prefijo acierta en cache y baja el costo/latencia; el contenido
dinamico (tarea del turno) va al final para no invalidar el prefijo.
WHERE: consumido por el coordinador/orchestrator al construir el prompt;
verificado por ``test_prompt_cache_shape.py``.

Diseno:
    - ``PromptBlock``: bloque inmutable con ``kind``, ``content`` y
      ``priority`` (orden intra-kind).
    - ``ORDER``: orden canonico de los kinds.
    - ``build_cache_shaped_prompt``: prompt completo con breakpoint.
    - ``cache_prefix``: solo el prefijo estable (tools+system+static).

Uso:
    prompt = build_cache_shaped_prompt([
        PromptBlock(kind="dynamic", content=task),
        PromptBlock(kind="tools", content=tool_defs),
        PromptBlock(kind="system", content=system_prompt),
    ])
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

#: Kinds de bloque soportados.
BlockKind = Literal["tools", "system", "static", "dynamic"]

#: Orden canonico de ensamblado (mutation: cambiar el orden rompe el test).
ORDER: tuple[BlockKind, ...] = ("tools", "system", "static", "dynamic")

#: Kinds considerados "estables" (candidatos a prefijo cacheable).
STABLE_KINDS: tuple[BlockKind, ...] = ("tools", "system", "static")

#: Marcador del breakpoint de cache (fin del prefijo estable).
CACHE_BREAKPOINT = "# --- CACHE_BREAKPOINT ---"

#: Separador entre bloques.
JOINER = "\n\n"


@dataclass(frozen=True)
class PromptBlock:
    """Bloque inmutable de un prompt (IMM: frozen dataclass).

    Attributes:
        kind: Categoria del bloque (tools/system/static/dynamic).
        content: Contenido textual del bloque.
        priority: Prioridad de orden dentro del mismo ``kind`` (ascendente).
    """

    kind: BlockKind
    content: str
    priority: int = 0


def _sort_key(block: PromptBlock) -> tuple[int, int]:
    """Clave de orden canonico de un bloque.

    Args:
        block: Bloque a ordenar.

    Returns:
        Tupla ``(indice_de_kind, priority)``; ``sorted`` es estable, por lo
        que los empates conservan el orden original.
    """
    return (ORDER.index(block.kind), block.priority)


def _ordered(blocks: list[PromptBlock]) -> list[PromptBlock]:
    """Ordena los bloques al orden canonico.

    Args:
        blocks: Bloques de entrada (sin mutar).

    Returns:
        Nueva lista ordenada por ``(kind, priority)``.
    """
    return sorted(blocks, key=_sort_key)


def build_cache_shaped_prompt(blocks: list[PromptBlock]) -> str:
    """Ensambla el prompt con orden canonico y breakpoint de cache.

    El orden canonico (``ORDER``) coloca primero el prefijo estable para que
    el proveedor lo cachee; el breakpoint ``CACHE_BREAKPOINT`` se registra al
    final del ultimo bloque estable para delimitar ese prefijo. El resultado
    es determinista (mismo input -> mismo output), requisito de cache-hit.

    Args:
        blocks: Bloques del prompt (cualquier orden de entrada).

    Returns:
        Prompt ensamblado, con ``\\n\\n`` entre bloques y el breakpoint
        insertado tras el ultimo bloque estable.
    """
    ordered = _ordered(blocks)
    parts = [block.content for block in ordered]

    last_stable = -1
    for index, block in enumerate(ordered):
        if block.kind in STABLE_KINDS:
            last_stable = index

    if last_stable >= 0:
        parts.insert(last_stable + 1, CACHE_BREAKPOINT)

    return JOINER.join(parts)


def cache_prefix(blocks: list[PromptBlock]) -> str:
    """Devuelve solo el prefijo estable cacheable (hasta el breakpoint).

    Args:
        blocks: Bloques del prompt (cualquier orden de entrada).

    Returns:
        Cadena con los bloques estables (tools+system+static) seguida del
        breakpoint, o cadena vacia si no hay bloques estables.
    """
    stable = [block.content for block in _ordered(blocks) if block.kind in STABLE_KINDS]
    if not stable:
        return ""
    return JOINER.join([*stable, CACHE_BREAKPOINT])


__all__ = [
    "CACHE_BREAKPOINT",
    "ORDER",
    "STABLE_KINDS",
    "BlockKind",
    "PromptBlock",
    "build_cache_shaped_prompt",
    "cache_prefix",
]
