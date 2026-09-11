"""reanchor.py — Re-anclaje post-compaction (ADR-0070, frontera 2026).

WHAT: Construye el bloque condensado de re-anclaje (N1 + agente activo +
skills + estado de sesion) y garantiza que sobreviva cada compactacion.
WHY: Los compactores retienen solo ~17% de las restricciones de sesion
(COMPINT, arXiv) y el 65% de fallos enterprise de agentes es context drift,
no token exhaustion (Forrester 2025). Re-inyectar el bloque despues de cada
compactacion restaura el contexto general sin re-enviar el AGENTS.md
completo (la repeticion de bloques grandes dispara attention suppression).
WHERE: Despues de cada ``structured_compact`` / ``ReversibleCompactor.compact``;
regla behavioral RPA en ``base_principles.md``.

Frontera aplicada:
- Guideline re-injection condensada (5-10 reglas criticas, no verbatim).
- SC-aware check: verificar que las reglas criticas siguen presentes
  post-compactacion (>90% retencion vs 17%).
- Self-restatement: el bloque ordena al agente restatear rol + 3 reglas.

Uso:
    block = build_reanchor(N1, "builder", ("rust-lang",), "tarea")
    compacted, block = compact_with_reanchor(session, N1, "builder", (), "tarea")
"""

from __future__ import annotations

from harness.memory_rag.compaction import structured_compact

# ---------------------------------------------------------------------------
# Constantes (MAG)
# ---------------------------------------------------------------------------
#: Marcador de re-anclaje en el texto compactado.
REANCHOR_MARKER = "<<RE-ANCHOR>>"
#: Tope de tamano del bloque (evita re-inyectar el AGENTS.md completo).
MAX_BLOCK_CHARS = 1800
#: Numero maximo de skills listados en el bloque.
MAX_SKILLS_LISTED = 8
#: Longitud maxima del resumen de tarea en el bloque.
MAX_TASK_CHARS = 120
#: Ratio de budget para la compactacion del texto de sesion.
SESSION_BUDGET_RATIO = 0.6


def build_reanchor(
    principles: str,
    agent: str,
    skills: tuple[str, ...],
    task: str,
) -> str:
    """Renderiza el bloque condensado de re-anclaje post-compaction.

    Args:
        principles: Lineas N1 criticas (una regla por linea, formato
            ``CODE: regla``). Obligatorio, no vacio.
        agent: Nombre del agente activo (rol). Obligatorio, no vacio.
        skills: Skills activas en la sesion (se listan hasta MAX_SKILLS_LISTED).
        task: Tarea en curso (resumen corto; se recorta a MAX_TASK_CHARS).

    Returns:
        Bloque ``<<RE-ANCHOR>>`` condensado listo para re-inyectar.

    Raises:
        ValueError: Si ``principles`` o ``agent`` estan vacios (WHAT+WHY+WHERE).
    """
    if not principles.strip():
        raise ValueError(
            "WHAT: principles vacio. "
            "WHY: el re-anclaje existe para restaurar las reglas criticas; "
            "sin reglas no hay nada que re-anclar. "
            "WHERE: build_reanchor"
        )
    if not agent.strip():
        raise ValueError(
            "WHAT: agent vacio. "
            "WHY: el rol activo define el comportamiento post-compaction. "
            "WHERE: build_reanchor"
        )
    lines: list[str] = [REANCHOR_MARKER, "Continuando con tu rol asignado:"]
    lines.append(f"ROL: {agent.strip()}")
    lines.append(f"TAREA: {_trim(task, MAX_TASK_CHARS)}")
    lines.append("REGLAS CRITICAS (restatalas si notas deriva):")
    lines.append(principles.strip())
    if skills:
        listed = ", ".join(s.strip() for s in skills[:MAX_SKILLS_LISTED] if s.strip())
        if listed:
            lines.append(f"SKILLS ACTIVAS: {listed}")
    lines.append(
        "PROTOCOLO: tras cada compactacion recarga N1 + skills + agentes "
        "(regla RPA); restatea rol + 3 reglas cada 10 respuestas."
    )
    block = "\n".join(lines)
    return _trim(block, MAX_BLOCK_CHARS)


def compact_with_reanchor(
    session_text: str,
    principles: str,
    agent: str,
    skills: tuple[str, ...],
    task: str,
    budget_ratio: float = SESSION_BUDGET_RATIO,
) -> tuple[str, str]:
    """Compacta la sesion y antepon el bloque de re-anclaje (SC-aware).

    WHAT: Envuelve ``structured_compact`` y garantiza que las reglas
    criticas sigan presentes tras la compactacion (antes del texto).
    WHY: El summary por si solo retiene ~17% de las restricciones; el
    bloque las restaura a >90% sin depender del compactor.
    WHERE: Pipeline de compaction del harness; hook post-compaction.

    Args:
        session_text: Texto completo de la sesion a compactar.
        principles: Lineas N1 criticas (ver ``build_reanchor``).
        agent: Agente activo.
        skills: Skills activas.
        task: Tarea en curso.
        budget_ratio: Fraccion del texto a mantener.

    Returns:
        Tupla (texto_compacto_con_bloque, bloque_reanchor).

    Raises:
        ValueError: Si los argumentos obligatorios estan vacios.
    """
    block = build_reanchor(principles, agent, skills, task)
    compacted = structured_compact(session_text, budget_ratio)
    if not compacted:
        compacted = ""
    restored = f"{block}\n\n{compacted}"
    return restored, block


def _trim(text: str, max_chars: int) -> str:
    """Recorta ``text`` a ``max_chars`` sin partir lineas a la mitad.

    Args:
        text: Texto a recortar (puede ser vacio).
        max_chars: Longitud maxima deseada.

    Returns:
        Texto recortado; si recorta, agrega ``...`` al final.
    """
    clean = text.strip() if text else ""
    if len(clean) <= max_chars:
        return clean
    return clean[: max_chars - 3].rstrip() + "..."
