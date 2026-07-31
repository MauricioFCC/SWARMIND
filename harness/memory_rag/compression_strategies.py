"""CompressionStrategies - Implementation strategies for prompt compression."""
from __future__ import annotations

import json
import logging
import re

from harness.memory_rag.compression_types import (
    CHARS_PER_TOKEN,
    FILLER_PATTERNS,
    METHOD_ABSTRACTIVE,
    METHOD_EXTRACTIVE,
    METHOD_STRUCTURED,
    PRESERVED_KEYWORDS,
    STOP_WORDS,
    estimate_tokens,
)

logger = logging.getLogger(__name__)

# Keys whose values should not be truncated in YAML/JSON compression
STRUCTURED_PRESERVE_KEYS: set[str] = {
    "name", "description", "version", "title", "summary",
    "instruction", "goal", "purpose", "constraint",
}


class CompressionStrategies:
    """Mixin con estrategias de compresion (hereda PromptCompressor hereda de esta)."""
    
    def _normalize_whitespace(self, text: str) -> str:
        """
        Normaliza whitespace: elimina espacios multiples, lineas vacias
        repetidas, y espacios al inicio/fin de lineas.

        Args:
            text: Texto a normalizar.

        Returns:
            Texto con whitespace normalizado.
        """
        # Colapsar 3+ newlines a 2
        text = re.sub(r'\n{3,}', '\n\n', text)
        # Eliminar espacios al final de cada linea
        text = re.sub(r'[ \t]+\n', '\n', text)
        # Colapsar 2+ espacios a 1
        text = re.sub(r' {2,}', ' ', text)
        # Eliminar lineas que son solo whitespace
        text = re.sub(r'^[ \t]+$', '', text, flags=re.MULTILINE)
        return text.strip()

    def _replace_filler_phrases(self, text: str) -> str:
        """
        Reemplaza frases de relleno por equivalentes mas cortos.

        Args:
            text: Texto a procesar.

        Returns:
            Texto con frases reemplazadas.
        """
        result = text
        for pattern, replacement in FILLER_PATTERNS:
            try:
                result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
            except re.error as exc:
                logger.warning(
                    "WHAT: Error en regex filler '%s' -> '%s': %s. "
                    "WHY: Pattern regex invalido. "
                    "WHERE: PromptCompressor._replace_filler_phrases",
                    pattern, replacement, exc,
                )
                continue
        return result

    def _remove_stop_words(self, text: str) -> str:
        """
        Elimina stop words preservando palabras clave criticas.

        Estrategia:
        - Recorre cada linea del texto.
        - Para cada palabra, verifica si es stop word.
        - NO elimina si la palabra forma parte de una palabra clave preservada.
        - NO elimina si la linea contiene terminos criticos (instrucciones).

        Args:
            text: Texto a procesar.

        Returns:
            Texto con stop words eliminadas.
        """
        lines = text.split("\n")
        result_lines: list[str] = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                result_lines.append(line)
                continue

            # Verificar si la linea contiene palabras clave preservadas
            if self._has_preserved_keywords(stripped):
                result_lines.append(line)
                continue

            # Verificar si la linea parece codigo o estructura
            if self._looks_like_code(stripped):
                result_lines.append(line)
                continue

            # Filtrar stop words
            words = stripped.split()
            filtered = [w for w in words if w.lower().strip(".,;:!?()[]{}'\"") not in STOP_WORDS]

            if filtered:
                result_lines.append(" ".join(filtered))
            else:
                result_lines.append(line)  # Preservar linea original si todo se filtro

        return "\n".join(result_lines)

    def _aggressive_extractive(self, text: str) -> str:
        """
        Compresion extractiva agresiva para ratios bajos (<0.4).

        Ademas de stop words, elimina:
        - Adverbios de modo innecesarios
        - Calificativos debiles
        - Lineas de logging/debug
        - Parentesis con informacion redundante
        - Lineas que contienen solo articulos + sustantivos sin verbo

        Args:
            text: Texto a comprimir agresivamente.

        Returns:
            Texto comprimido agresivamente.
        """
        lines = text.split("\n")
        result: list[str] = []

        # Eliminar lineas de logging
        log_pattern = re.compile(
            r'^\s*(DEBUG|INFO|WARN(ING)?|ERROR|TRACE)\s*(\[.*?\])?\s*:',
            re.IGNORECASE,
        )

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # Eliminar lineas de logging
            if log_pattern.match(stripped):
                continue

            # Eliminar lineas que son solo separadores decorativos
            if re.match(r'^[=\-#*\s]{10,}$', stripped):
                continue

            # Acortar lineas largas a primeras 3 palabras si tienen baja densidad
            word_count = len(stripped.split())
            if word_count > 15 and not self._has_verb(stripped):
                # Mantener solo primeras 8 palabras
                short = " ".join(stripped.split()[:8])
                result.append(short)
                continue

            result.append(line)

        return "\n".join(result)

    def _structured_compress(self, text: str, ratio: float) -> str:
        """
        Comprime texto estructurado (JSON/YAML) preservando keys criticas.

        WHAT: Comprime schemas JSON y YAML eliminando whitespace innecesario,
        acortando keys no criticas, y compactando arrays y objetos.
        WHY: Los schemas estructurados suelen tener mucho whitespace y
        keys descriptivas largas que pueden acortarse sin perder semantica.
        WHERE: Schemas de tools, configuraciones YAML, JSON prompts.

        Args:
            text: Texto estructurado a comprimir.
            ratio: Proporcion objetivo.

        Returns:
            Texto estructurado comprimido.
        """
        if not text:
            return ""

        # Detectar si es JSON o YAML
        is_json = text.strip().startswith(("{", "["))
        if is_json:
            return self._compress_json(text, ratio)
        else:
            return self._compress_yaml(text, ratio)

    def _compress_json(self, text: str, ratio: float) -> str:
        """
        Comprime un JSON (o JSON-like) preservando estructura.

        Args:
            text: Texto JSON a comprimir.
            ratio: Proporcion objetivo.

        Returns:
            JSON comprimido.
        """
        try:
            parsed = json.loads(text)
            # Compactar: separadores minimos
            compact = json.dumps(parsed, separators=(",", ":"), ensure_ascii=False)

            # Si aun excede el target, acortar strings largos
            if ratio < 0.5 and self._count_tokens(compact) > self._count_tokens(text) * ratio:
                compact = self._truncate_json_strings(compact, ratio)

            return compact
        except json.JSONDecodeError:
            # No es JSON valido: aplicar extractive estandar
            logger.debug(
                "Structured: JSON invalido, usando extractive en su lugar"
            )
            return self.extractive_compress(text, ratio)

    def _compress_yaml(self, text: str, ratio: float) -> str:
        """
        Comprime texto YAML preservando estructura jerarquica.

        Args:
            text: Texto YAML a comprimir.
            ratio: Proporcion objetivo.

        Returns:
            YAML comprimido.
        """
        lines = text.split("\n")
        compressed: list[str] = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # Preservar comentarios importantes (# TODO, # NOTE, # SECURITY)
            if stripped.startswith("#") and not any(
                kw in stripped.upper() for kw in ("TODO", "NOTE", "SECURITY", "FIXME", "HACK")
            ):
                continue  # Eliminar comentarios no criticos

            # Acortar valores largos en una linea
            if ":" in stripped and not stripped.startswith("-"):
                key, _, value = stripped.partition(":")
                key_stripped = key.strip()
                value_stripped = value.strip()

                # Si el valor es largo, truncar
                if len(value_stripped) > 100 and key_stripped not in STRUCTURED_PRESERVE_KEYS:
                    value_stripped = value_stripped[:80] + "..."

                compressed.append(f"{key_stripped}: {value_stripped}")
            else:
                compressed.append(stripped)

        return "\n".join(compressed)

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

    def _has_preserved_keywords(self, text: str) -> bool:
        """
        Verifica si un texto contiene palabras clave que deben preservarse.

        Args:
            text: Texto a verificar.

        Returns:
            True si contiene palabras clave preservadas.
        """
        lower = text.lower()
        for keyword in PRESERVED_KEYWORDS:
            if keyword in lower:
                return True
        return False

    def _has_verb(self, text: str) -> bool:
        """
        Heuristico simple: verifica si el texto contiene verbos comunes.

        Args:
            text: Texto a verificar.

        Returns:
            True si contiene al menos un verbo conocido.
        """
        verbs = {
            "es", "son", "fue", "era", "ser", "estar", "tener", "hacer",
            "puede", "debe", "va", "dice", "tiene", "estan", "esta",
            "is", "are", "was", "were", "be", "have", "has", "do",
            "does", "can", "must", "will", "would", "shall", "may",
            "need", "use", "uses", "used", "using",
            "crea", "crear", "creado", "genera", "generar", "generado",
            "procesa", "procesar", "procesado", "ejecuta", "ejecutar",
            "ejecutado", "obtiene", "obtener", "obtenido", "devuelve",
            "devolver", "devuelto", "define", "definir", "definido",
        }
        words = set(text.lower().split())
        return bool(words & verbs)

    def _looks_like_code(self, text: str) -> bool:
        """
        Determina si un texto parece codigo (debe preservarse intacto).

        Args:
            text: Texto a verificar.

        Returns:
            True si parece codigo.
        """
        code_patterns = [
            r'\b(def|class|import|from|return|if __name__|async def)\b',
            r'^\s*(def |class |import |from |return |async )',
            r'[{}]\s*$',  # Termina con llave
            r'^\s*@\w+',  # Decorador
            r'^\s*\/\/',  # Comentario de codigo
            r'^\s*#include',  # C/C++
            r'^\s*(public|private|protected|static|void|int|str|bool)\s',
            r'function\s+\w+\s*\(',
        ]
        for pattern in code_patterns:
            if re.search(pattern, text, re.MULTILINE):
                return True
        return False

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

    @staticmethod
    def _line_is_only_stop_words(line: str) -> bool:
        """
        Verifica si una linea contiene solo stop words.

        Args:
            line: Linea de texto a verificar.

        Returns:
            True si todas las palabras son stop words.
        """
        if not line or not line.strip():
            return True
        words = line.strip().lower().split()
        if not words:
            return True
        # Eliminar signos de puntuacion
        clean_words = [w.strip(".,;:!?()[]{}\"'") for w in words]
        # Si hay al menos una palabra que no es stop word, la linea es util
        non_stop = [w for w in clean_words if w and w not in STOP_WORDS]
        return len(non_stop) == 0

    def _enforce_target_ratio(self, original: str, compressed: str, ratio: float) -> str:
        """
        Asegura que el texto comprimido cumpla con el ratio objetivo.

        Si el texto comprimido es mas largo de lo esperado, aplica
        truncado de lineas de baja prioridad para alcanzar el target.

        NOTA: Este metodo NO llama a extractive_compress() para evitar
        recursion infinita. Usa truncado directo de lineas.

        Args:
            original: Texto original (para referencia).
            compressed: Texto ya comprimido.
            ratio: Ratio objetivo.

        Returns:
            Texto que cumple (o se acerca) al ratio objetivo.
        """
        max_iterations = 3
        iteration = 0
        current = compressed
        target_tokens = max(1, int(self._count_tokens(original) * ratio))

        while iteration < max_iterations:
            current_tokens = self._count_tokens(current)
            if current_tokens <= target_tokens:
                break

            over_pct = current_tokens / max(target_tokens, 1)
            if over_pct <= 1.1:
                break  # Dentro del 10% de margen

            # Truncado directo: eliminar lineas cortas no criticas
            lines = current.split("\n")
            # Eliminar lineas vacias o muy cortas (< 3 chars)
            lines = [line for line in lines if len(line.strip()) > 3]
            # Si aun excede, eliminar lineas con solo stop words
            if self._count_tokens("\n".join(lines)) > target_tokens:
                critical_lines: list[str] = []
                for line in lines:
                    stripped = line.strip()
                    if self._has_preserved_keywords(stripped) or self._looks_like_code(stripped) or not self._line_is_only_stop_words(stripped):
                        critical_lines.append(line)
                # Asegurar que no quedamos vacios
                if len(critical_lines) >= len(lines) // 2:
                    lines = critical_lines
                else:
                    # Si perdimos demasiado, mantener al menos 50% de lineas
                    keep_count = max(len(critical_lines), len(lines) // 2)
                    # Mantener las mas largas (mas informacion)
                    sorted_lines = sorted(lines, key=len, reverse=True)
                    lines = sorted_lines[:keep_count]

            current = "\n".join(lines)
            iteration += 1

        # Si aun excede, truncar caracteres directamente
        if self._count_tokens(current) > target_tokens:
            max_chars = int(target_tokens * CHARS_PER_TOKEN)
            if len(current) > max_chars:
                # Truncar al final, pero no en medio de una palabra
                truncated = current[:max_chars]
                last_space = truncated.rfind(" ")
                if last_space > max_chars * 0.8:
                    truncated = truncated[:last_space]
                current = truncated + "..."

        return current

    def _truncate_json_strings(self, json_str: str, ratio: float) -> str:
        """
        Trunca strings largos dentro de un JSON.

        Args:
            json_str: JSON string.
            ratio: Ratio de compresion.

        Returns:
            JSON con strings truncados.
        """
        # Estrategia: reemplazar strings de mas de 50 chars con version truncada
        def truncate_match(m: re.Match) -> str:
            full = m.group(0)
            # Extraer el string interno (sin comillas)
            inner = full[1:-1]
            if len(inner) > 50:
                truncated = inner[:40] + "..."
                return f'"{truncated}"'
            return full

        return re.sub(r'"[^"]{50,}"', truncate_match, json_str)


    # ---------------------------------------------------------------------------
    # TokenBudgetManager — Seguimiento de presupuesto por sesion
    # ---------------------------------------------------------------------------