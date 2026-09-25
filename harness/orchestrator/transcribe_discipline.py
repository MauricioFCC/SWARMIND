"""transcribe_discipline.py — Dictado en 2 pasos con exactitud (ADR-0089).

WHAT: Genera la instruccion de transcripcion: paso 1 verbatim (Sync API),
paso 2 rewrite via LLM (<1s) FIJANDO nombres, numeros y fechas exactos.
WHY: AssemblyAI: el dictado en 2 pasos separa fidelidad (verbatim) de
legibilidad (rewrite); sin fijar entidades, el rewrite "arregla" nombres
y fechas (alucinacion silenciosa).
WHERE: Captura por voz (Whisper/second-brain) y pipeline de ingesta.

Uso:
    instruction = transcribe_instruction()  # al system prompt del rewrite
"""

from __future__ import annotations


def transcribe_instruction() -> str:
    """Retorna la instruccion de transcripcion exacta en 2 pasos.

    Returns:
        Texto listo para inyectar al prompt de rewrite.
    """
    return (
        "Transcripcion en 2 pasos: "
        "1) verbatim: transcribe EXACTAMENTE lo dicho, sin corregir ni resumir; "
        "2) rewrite: reescribe legible en menos de 1 segundo MANTENIENDO "
        "verbatim los nombres propios, los numeros (cantidades, fechas, horas) "
        "y las fechas exactas — nunca los 'arregles' ni los redondees."
    )
