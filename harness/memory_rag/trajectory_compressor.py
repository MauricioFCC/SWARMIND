"""
Trajectory Compressor — Hermes-inspired conversation compression + SelfCompact.

Comprime trayectorias de conversaciones multi-turno para ahorrar tokens.
Estrategia (tomada de Hermes Agent trajectory_compressor.py):
  1. Protege primeros N turns (system, human, first tool)
  2. Protege ultimos M turns (acciones finales)
  3. Comprime SOLO la region media (turnos redundantes)
  4. Reemplaza region comprimida con un unico mensaje SUMMARY
  5. Mantiene el resto de tool calls intactos

SelfCompact Pattern (arXiv 2606.23525, junio 2026):
  - El propio modelo decide cuando compactar via rubric
  - Compactacion selectiva segun fase de la trayectoria
  - Evita compactar en fases criticas (exploring, stuck)

Ahorro estimado: 30-50% de tokens en historial de conversacion.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Numero de turns a proteger al inicio y final
PROTECT_HEAD_TURNS = 3  # system, human, first tool response
PROTECT_TAIL_TURNS = 4  # ultimas acciones y conclusiones

# Compression targets
SUMMARY_TARGET_TOKENS = 250  # tokens para el summary
MIN_TOKENS_TO_COMPRESS = 500  # minimo para activar compression
CHAR_PER_TOKEN = 4.0  # estimacion rough

# Roles que se comprimen (middle turns)
COMPRESSIBLE_ROLES = {"tool", "gpt", "assistant", "function"}

# Fases de trayectoria para SelfCompact
VALID_PHASES = frozenset({
    "exploring",   # Exploracion activa — NO compactar
    "resolving",   # Resolviendo subtarea — posible compactar
    "converging",  # Convergiendo a solucion — compactar recomendado
    "stuck",       # Atascado — NO compactar (contexto valioso)
    "completed",   # Subtarea resuelta — compactar siempre
})

# Contexto maximo estimado por defecto (8K tokens)
DEFAULT_MAX_CONTEXT_TOKENS = 8000


# ---------------------------------------------------------------------------
# TrajectoryCompressor
# ---------------------------------------------------------------------------


class TrajectoryCompressor:
    """
    Comprime trayectorias de conversacion multi-turno.

    Incorpora SelfCompact Pattern (arXiv 2606.23525): el propio modelo
    decide cuando compactar basado en la fase de la trayectoria y el
    uso de contexto.

    Uso:
        compressor = TrajectoryCompressor()
        compressed = compressor.compress(conversation_history)
        # compressed tiene ~30-50% menos tokens

        # Con SelfCompact:
        compressed = compressor.compress(history, phase="converging")
    """

    def __init__(
        self,
        protect_head: int = PROTECT_HEAD_TURNS,
        protect_tail: int = PROTECT_TAIL_TURNS,
        summary_tokens: int = SUMMARY_TARGET_TOKENS,
        min_tokens: int = MIN_TOKENS_TO_COMPRESS,
    ):
        self.protect_head = protect_head
        self.protect_tail = protect_tail
        self.summary_tokens = summary_tokens
        self.min_tokens = min_tokens
        self._phase: str = "exploring"
        self._stats: Dict[str, Any] = {
            "compressions": 0,
            "skipped": 0,
            "total_tokens_saved": 0,
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compress(
        self,
        conversation: List[Dict[str, Any]],
        target_tokens: Optional[int] = None,
        phase: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Comprime una trayectoria de conversacion.

        Si se proporciona 'phase', aplica SelfCompact rubric para decidir
        si la compactacion es apropiada. Sin 'phase', mantiene el
        comportamiento clasico (comprime siempre que supere el umbral).

        Args:
            conversation: Lista de mensajes en orden cronologico.
                Cada mensaje debe tener al menos 'role' y 'content'.
            target_tokens: Token target opcional (default: auto).
            phase: Fase actual de la trayectoria para SelfCompact.
                Valores: exploring, resolving, converging, stuck, completed.

        Returns:
            Lista comprimida de mensajes (original si rubric dice no compactar).
        """
        if not conversation:
            return conversation

        # --- SelfCompact: verificar rubric si hay fase ---
        if phase is not None:
            if phase in VALID_PHASES:
                self._phase = phase
            context_usage = self._estimate_context_usage(conversation)
            if not self.should_compact(self._phase, context_usage, len(conversation)):
                self._stats["skipped"] += 1
                logger.debug(
                    "SelfCompact: skip compression (phase=%s, ctx=%.1f%%, turns=%d)",
                    self._phase, context_usage, len(conversation),
                )
                return conversation

        # 1. Contar tokens totales
        total_tokens = self._count_tokens_list(conversation)

        # 2. Si esta bajo el target, skip
        if total_tokens < (target_tokens or self.min_tokens):
            self._stats["skipped"] += 1
            return conversation

        # 3. Identificar regiones protegidas
        n = len(conversation)
        head = min(self.protect_head, n // 2)
        tail = min(self.protect_tail, n // 2)

        # Asegurar que no se overlapeen
        if head + tail >= n:
            head = n // 3
            tail = n // 3

        compress_start = head
        compress_end = n - tail

        if compress_start >= compress_end:
            self._stats["skipped"] += 1
            return conversation  # no hay region comprimible

        # 4. Calcular cuantos tokens ahorrar
        region_tokens = self._count_tokens_list(conversation[compress_start:compress_end])
        savings_needed = total_tokens - (target_tokens or self.min_tokens)
        tokens_to_compress = savings_needed + self.summary_tokens

        # 5. Siempre comprimir si la region tiene al menos 3 turns
        #    (aunque no se alcance el target exacto, algo se ahorra)
        if (compress_end - compress_start) < 3:
            self._stats["skipped"] += 1
            return conversation

        # 6. Encontrar el punto optimo de compresion
        # Comenzar desde el inicio de la region, acumular hasta tener savings
        accumulated = 0
        cut_point = compress_start

        for i in range(compress_start, compress_end):
            tokens = self._count_tokens(str(conversation[i].get("content", "")))
            accumulated += tokens
            cut_point = i + 1
            if accumulated >= tokens_to_compress:
                break

        # Asegurar que cut_point no rompa un tool_call pair
        # (no cortar entre tool_call y tool_response)
        while cut_point < n - tail:
            role = conversation[cut_point].get("role", "")
            if role == "function" or role == "tool":
                cut_point += 1  # mover el corte para incluir el tool response
            else:
                break

        cut_point = min(cut_point, compress_end)

        # 7. Generar summary de la region comprimida
        summary = self._generate_summary(conversation[compress_start:cut_point])

        # 8. Construir trayectoria comprimida
        compressed = []
        # Head (protegido)
        for i in range(compress_start):
            compressed.append(dict(conversation[i]))
        # Summary (reemplaza la region media)
        compressed.append({
            "role": "system",
            "content": f"[COMPRESSED] {summary}",
            "compressed": True,
            "original_turns": cut_point - compress_start,
        })
        # Tail (protegido)
        for i in range(cut_point, n):
            compressed.append(dict(conversation[i]))

        # 9. Actualizar stats
        compressed_tokens = self._count_tokens_list(compressed)
        saved = total_tokens - compressed_tokens
        self._stats["compressions"] += 1
        self._stats["total_tokens_saved"] += saved

        logger.debug(
            "Trajectory compressed: %d -> %d turns, %d -> %d tokens (%d%% savings)",
            len(conversation), len(compressed),
            total_tokens, compressed_tokens,
            int(saved / max(total_tokens, 1) * 100),
        )

        return compressed

    def get_stats(self) -> Dict[str, Any]:
        """Return compressor statistics."""
        return dict(self._stats)

    # ------------------------------------------------------------------
    # SelfCompact Pattern (arXiv 2606.23525, junio 2026)
    # ------------------------------------------------------------------

    @staticmethod
    def get_compact_rubric() -> str:
        """
        Retorna un prompt/rubric ligero para que el LLM decida si compactar.

        El rubric sigue las condiciones del paper SelfCompact:
        - Compactar cuando: subtarea resuelta, trayectoria convergiendo,
          >80% contexto usado, >15 turnos
        - NO compactar cuando: mid-derivation, stuck, esperando tool output

        Returns:
            String con el rubric formateado para incluir en system prompt.
        """
        return (
            "## Self-Compact Rubric\n"
            "Decide si compactar la trayectoria actual siguiendo estas reglas:\n\n"
            "### Compactar CUANDO:\n"
            "- La subtarea actual esta resuelta (completed)\n"
            "- La trayectoria esta convergiendo a una solucion (converging)\n"
            "- El uso de contexto es > 80%\n"
            "- El numero de turnos es > 15\n\n"
            "### NO compactar CUANDO:\n"
            "- Estas en medio de una derivacion (mid-derivation)\n"
            "- Estas atascado (stuck) — necesitas contexto para debug\n"
            "- Estas esperando un tool output\n"
            "- Estas explorando activamente (exploring)\n\n"
            "### Fases y decision:\n"
            "- exploring  → NO compactar (exploracion activa)\n"
            "- resolving  → compactar solo si >85% contexto y >20 turnos\n"
            "- converging → compactar recomendado\n"
            "- stuck      → NO compactar (se perderia contexto valioso)\n"
            "- completed  → compactar siempre\n"
        )

    def mark_trajectory_phase(self, phase: str) -> None:
        """
        Marca la fase actual de la trayectoria para decisiones de compactacion.

        Args:
            phase: Fase de la trayectoria.
                Valores: exploring, resolving, converging, stuck, completed.

        Raises:
            ValueError: Si la fase no es valida.
        """
        if phase not in VALID_PHASES:
            raise ValueError(
                f"Fase invalida: '{phase}'. "
                f"Valores validos: {', '.join(sorted(VALID_PHASES))}"
            )
        self._phase = phase
        logger.debug("Trajectory phase marked: %s", phase)

    @staticmethod
    def should_compact(phase: str, context_usage_pct: float, turn_count: int) -> bool:
        """
        Implementa la logica del rubric Self-Compact.

        Decide si se debe compactar segun la fase actual, el porcentaje
        de contexto usado y el numero de turnos.

        Args:
            phase: Fase actual de la trayectoria.
            context_usage_pct: Porcentaje de contexto usado (0-100).
            turn_count: Numero de turnos en la trayectoria.

        Returns:
            True si se debe compactar, False en caso contrario.
        """
        if phase not in VALID_PHASES:
            phase = "exploring"  # Default seguro

        # Nunca compactar en estas fases (se perderia contexto valioso)
        if phase in ("exploring", "stuck"):
            return False

        # Compactar si la fase lo permite Y hay alta presion de contexto
        if phase in ("completed", "converging"):
            if context_usage_pct > 75 or turn_count > 15:
                return True

        # Fase 'resolving': solo si hay mucha presion
        if phase == "resolving" and context_usage_pct > 85 and turn_count > 20:
            return True

        return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _count_tokens(text: str) -> int:
        """Estimacion de tokens (~4 chars por token)."""
        return max(1, len(text) // CHAR_PER_TOKEN)

    @classmethod
    def _count_tokens_list(cls, messages: List[Dict[str, Any]]) -> int:
        """Cuenta tokens totales de una lista de mensajes."""
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += cls._count_tokens(content)
            # Tool calls tambien tienen tokens
            tc = msg.get("tool_calls", "")
            if isinstance(tc, str):
                total += cls._count_tokens(tc)
        return total

    @staticmethod
    def _estimate_context_usage(conversation: List[Dict[str, Any]]) -> float:
        """
        Estima el porcentaje de contexto usado (0-100) asumiendo ventana de 8K tokens.

        Args:
            conversation: Lista de mensajes a evaluar.

        Returns:
            Porcentaje entre 0 y 100.
        """
        total = TrajectoryCompressor._count_tokens_list(conversation)
        pct = (total / DEFAULT_MAX_CONTEXT_TOKENS) * 100
        return min(100.0, pct)

    def _generate_summary(self, turns: List[Dict[str, Any]]) -> str:
        """
        Genera un summary de los turns a comprimir.

        En produccion esto llamaria a un LLM. Por ahora usamos
        una heuristica: extraer puntos clave de cada turn.
        """
        if not turns:
            return ""

        # Extraer contenido relevante de cada turno
        key_points: List[str] = []
        for i, turn in enumerate(turns):
            role = turn.get("role", "unknown")
            content = turn.get("content", "")

            if isinstance(content, str) and content:
                # Truncar y extraer primeras lineas significativas
                lines = [l.strip() for l in content.split("\n") if l.strip()]
                significant = [l for l in lines if len(l) > 20][:2]
                if significant:
                    key_points.append(f"[{role}] {' '.join(significant)}")
                elif lines:
                    key_points.append(f"[{role}] {lines[0][:100]}")

        # Construir summary compacto
        summary_text = "; ".join(key_points) if key_points else "(conversation compressed)"

        # Limitar al target de summary tokens
        max_chars = int(self.summary_tokens * CHAR_PER_TOKEN)
        if len(summary_text) > max_chars:
            summary_text = summary_text[:max_chars] + "..."

        return summary_text


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------


def compress_conversation(
    conversation: List[Dict[str, Any]],
    target_tokens: Optional[int] = None,
    phase: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Comprime una conversacion multi-turno (funcion de conveniencia).

    Args:
        conversation: Lista de mensajes con 'role' y 'content'.
        target_tokens: Target de tokens (default: auto).
        phase: Fase de trayectoria para SelfCompact (opcional).

    Returns:
        Lista comprimida.
    """
    compressor = TrajectoryCompressor()
    return compressor.compress(conversation, target_tokens, phase=phase)
