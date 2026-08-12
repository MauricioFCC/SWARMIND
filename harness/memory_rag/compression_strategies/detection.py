"""Mixin de deteccion de metodo para ``CompressionStrategies``.

Extraido mecanicamente de ``compression_strategies.py`` (regla AGR < 500
lineas). Contiene la deteccion automatica del mejor metodo de
compresion, conteo de tokens, division en secciones, resumen por
presupuesto y distribucion proporcional de budgets.
"""
from __future__ import annotations

import re

from harness.memory_rag.compression_types import (
    CHARS_PER_TOKEN,
    METHOD_ABSTRACTIVE,
    METHOD_EXTRACTIVE,
    METHOD_STRUCTURED,
    STOP_WORDS,
    estimate_tokens,
)


class _MethodDetectionMixin:
    """Metodos de deteccion de metodo, tokenizacion y secciones."""

    # ------------------------------------------------------------------
    # Metodos internos de soporte
    # ------------------------------------------------------------------

    def _count_tokens(self, text: str) -> int:
        """
        Cuenta tokens de un texto usando tiktoken o chars/4 fallback.

        Args:
            text: Texto a contar.

        Returns:
            Numero de tokens (minimo 1).
        """
        if not text:
            return 1
        if self._use_tiktoken:
            return estimate_tokens(text)
        return max(1, len(text) // int(CHARS_PER_TOKEN))

    def _detect_best_method(self, text: str, ratio: float) -> str:
        """
        Detecta automaticamente la mejor estrategia de compresion.

        Reglas:
        - Si el texto parece JSON/YAML -> structured
        - Si ratio < 0.4 (compresion agresiva) -> abstractive
        - Si el texto tiene baja densidad semantica (muchas stop words) -> extractive
        - Si el texto es largo (>200 tokens) y estructurado en secciones -> abstractive
        - Default -> extractive

        Args:
            text: Texto a analizar.
            ratio: Ratio de compresion objetivo.

        Returns:
            Nombre del metodo recomendado.
        """
        stripped = text.strip()

        # JSON/YAML detection
        if stripped.startswith(("{", "[")):
            return METHOD_STRUCTURED

        # YAML detection (lineas con key: value)
        yaml_lines = sum(1 for line in stripped.split("\n") if re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*:', line))
        if yaml_lines > 3 and yaml_lines > len(stripped.split("\n")) * 0.3:
            return METHOD_STRUCTURED

        # Compresion agresiva -> abstractive
        if ratio < 0.4:
            return METHOD_ABSTRACTIVE

        # Texto largo con secciones -> abstractive
        tokens = self._count_tokens(stripped)
        sections = self._split_into_sections(stripped)
        if tokens > 200 and len(sections) >= 3:
            return METHOD_ABSTRACTIVE

        # Alta densidad de stop words -> extractive
        words = stripped.split()
        if words:
            stop_word_ratio = sum(
                1 for w in words if w.lower().strip(".,;:!?") in STOP_WORDS
            ) / len(words)
            if stop_word_ratio > 0.4:
                return METHOD_EXTRACTIVE

        return self._method_fallback

    def _split_into_sections(self, text: str) -> list[str]:
        """
        Divide texto en secciones semanticas (separadas por doble newline).

        Args:
            text: Texto a dividir.

        Returns:
            Lista de secciones (strings).
        """
        # Separar por doble o triple newline
        sections = re.split(r'\n\n+', text)
        return [s.strip() for s in sections if s.strip()]

    def _summarize_section(self, section: str, budget_tokens: int) -> str:
        """
        Resume una seccion para que quepa dentro de budget_tokens.

        Estrategia:
        1. Extraer primera oracion (topic sentence)
        2. Si cabe, anadir segunda oracion
        3. Si aun hay presupuesto, anadir palabras clave del resto
        4. Marcar como resumen

        Args:
            section: Seccion a resumir.
            budget_tokens: Tokens maximos permitidos.

        Returns:
            Seccion resumida.
        """
        if not section:
            return ""

        original_tokens = self._count_tokens(section)
        if original_tokens <= budget_tokens:
            return section

        # Dividir en oraciones (separador basico: . + espacio)
        sentences = re.split(r'(?<=[.!?])\s+', section)

        if len(sentences) <= 1:
            # Una sola oracion: truncar
            ratio = budget_tokens / max(original_tokens, 1)
            return self.extractive_compress(section, ratio)

        # Acumular oraciones hasta llenar presupuesto
        summary_parts: list[str] = []
        used = 0
        for sentence in sentences:
            sent_tokens = self._count_tokens(sentence)
            if used + sent_tokens <= budget_tokens:
                summary_parts.append(sentence)
                used += sent_tokens
            else:
                # Comprimir esta oracion parcialmente
                if used < budget_tokens:
                    remaining = budget_tokens - used
                    ratio = remaining / max(sent_tokens, 1)
                    compressed = self.extractive_compress(sentence, ratio)
                    if compressed.strip():
                        summary_parts.append(compressed)
                break

        result = " ".join(summary_parts)

        # Si aun excede, aplicar extractive
        if self._count_tokens(result) > budget_tokens:
            ratio = budget_tokens / max(self._count_tokens(result), 1)
            result = self.extractive_compress(result, ratio)

        return result

    def _distribute_budget_proportional(
        self,
        token_counts: list[int],
        total_budget: int,
    ) -> list[int]:
        """
        Distribuye un presupuesto proporcionalmente entre secciones.

        Usa el algoritmo de Hamilton (mayor resto) para分配
        de forma justa sin perder tokens por redondeo.

        Args:
            token_counts: Lista de tokens por seccion.
            total_budget: Presupuesto total disponible.

        Returns:
            Lista de tokens asignados por seccion (mismo orden).
        """
        if not token_counts:
            return []

        total_tokens = sum(token_counts)
        if total_tokens <= total_budget:
            return list(token_counts)

        # Distribucion proporcional con algoritmo de mayor resto
        base_allocation = [t * total_budget // total_tokens for t in token_counts]
        remainders = [
            (t * total_budget / total_tokens) - base_allocation[i]
            for i, t in enumerate(token_counts)
        ]
        remainder_sum = total_budget - sum(base_allocation)

        # Asignar resto a las secciones con mayor fraccion decimal
        if remainder_sum > 0:
            indices = sorted(
                range(len(token_counts)),
                key=lambda i: remainders[i],
                reverse=True,
            )
            for i in indices[:remainder_sum]:
                base_allocation[i] += 1

        return [max(1, a) for a in base_allocation]

    def _is_critical_section(self, section: str) -> bool:
        """
        Determina si una seccion es critica (debe preservarse intacta).

        Criterios:
        - Contiene palabras clave de seguridad/identidad
        - Contiene instrucciones imperativas
        - Contiene formato de tool definition
        - Es corta (< 50 tokens)

        Args:
            section: Texto de la seccion.

        Returns:
            True si la seccion se considera critica.
        """
        lower = section.lower()

        # Palabras clave de secciones criticas
        critical_triggers = [
            "eres", "you are", "actua como", "act as",
            "importante", "important", "regla", "rule",
            "prohibido", "forbidden", "nunca", "never",
            "siempre", "always", "seguridad", "security",
            "guardrail", "peligro", "danger",
            "debes", "must", "debes de",
            "tool", "function", "herramienta",
            "system", "sistema",
        ]

        for trigger in critical_triggers:
            if trigger in lower:
                return True

        # Secciones muy cortas (< 50 tokens) se consideran criticas
        if self._count_tokens(section) < 50:
            return True

        # Secciones que parecen definiciones de herramientas
        if '"""' in section or "'''" in section:
            return True
        return bool(section.strip().startswith("```"))

    def _detect_sections(self, text: str) -> list[str]:
        """
        Detecta nombres de secciones preservadas en el texto comprimido.

        Busca patrones de cabeceras de seccion como "### Title",
        "== Title ==", "**Title**", o lineas en mayusculas.

        Args:
            text: Texto comprimido.

        Returns:
            Lista de nombres de secciones encontradas.
        """
        sections: list[str] = []
        for line in text.split("\n"):
            stripped = line.strip()
            # Detectar cabeceras markdown
            header_match = re.match(r'^#{1,4}\s+(.+)$', stripped)
            if header_match:
                sections.append(header_match.group(1).strip())
                continue
            # Detectar cabeceras con == o --
            if re.match(r'^==+.+==+$', stripped) or re.match(r'^--+.+--+$', stripped):
                sections.append(stripped.strip("=- "))
                continue
            # Detectar lineas en MAYUSCULAS que parezcan titulos
            if stripped.isupper() and len(stripped) > 3 and len(stripped.split()) <= 6:
                sections.append(stripped)
        return sections
