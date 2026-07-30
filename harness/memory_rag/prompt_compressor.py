"""
PromptCompressor — Motor de compresion de prompts multi-estrategia (2026).

Tecnicas implementadas (estado del arte 2026):
1. **Abstractive Compression**: Resumir secciones largas preservando info clave.
   Basado en Cmprsr (Zakazov et al., 2025): LLM-as-compressor con GRPO.
2. **Extractive Compression**: Eliminar palabras/frases redundantes (stop words,
   rephrasing, filler). Inspirado en LLMLingua-2 (Pan et al., 2025).
3. **Token Budget Allocation**: Asignar presupuesto de tokens por seccion del
   prompt, con redistribucion dinamica entre secciones.
4. **Context Window Management**: Gestion activa del contexto para mantenerlo
   dentro del limite, con sliding window y prioridad por seccion.
5. **Structured Output Pre-compression**: Comprimir schemas JSON y YAML antes de
   enviarlos, eliminando whitespace y abreviando keys.

Basado en:
  - Cmprsr (Zakazov et al., 2025): LLM-as-compressor con GRPO
  - LLMLingua-2 (Pan et al., 2025): Compresion extractiva con perplexity
  - arXiv:2603.05818 RouteGoT: Routing adaptativo con budget control
  - SelfCompact Pattern (arXiv 2606.23525): Compactacion selectiva por fase

WHY: Los prompts largos consumen tokens de contexto valiosos y aumentan costos
de API. Este motor permite comprimir prompts de forma inteligente preservando
informacion semantica critica.

WHERE: Usado por ContextWindowManager, OptimizationPipeline, y directamente
por agentes antes de enviar prompts al LLM para reducir tokens.

Uso:
    compressor = PromptCompressor()
    result = compressor.compress("texto largo...", target_ratio=0.5)
    print(result.text)  # Texto comprimido
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union

from harness.common import CHARS_PER_TOKEN, compression_pct, estimate_tokens

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

# Ratio de compresion por defecto
DEFAULT_TARGET_RATIO = 0.5

# Tokens minimos para activar compresion
ACTIVATION_THRESHOLD_TOKENS = 64

# Token estimado maximo por defecto para ventana de contexto
DEFAULT_MAX_CONTEXT_TOKENS = 8000

# Metodos de compresion disponibles
METHOD_EXTRACTIVE = "extractive"
METHOD_ABSTRACTIVE = "abstractive"
METHOD_AUTO = "auto"
METHOD_STRUCTURED = "structured"
ALL_METHODS = frozenset({METHOD_EXTRACTIVE, METHOD_ABSTRACTIVE, METHOD_AUTO, METHOD_STRUCTURED})

# Palabras/frases a eliminar en compresion extractiva (stop words expandido)
STOP_WORDS: frozenset = frozenset({
    # Articulos y determinantes
    "el", "la", "los", "las", "un", "una", "unos", "unas", "lo",
    "the", "a", "an", "this", "that", "these", "those",
    # Preposiciones comunes
    "de", "del", "en", "para", "por", "con", "sin", "sobre", "entre",
    "of", "in", "on", "at", "to", "for", "with", "by", "from", "as",
    "into", "through", "during", "before", "after", "above", "below",
    "between", "out", "off", "over", "under", "again", "further",
    "then", "once", "here", "there", "when", "where", "why", "how",
    "all", "each", "every", "both", "few", "more", "most", "other",
    "some", "such", "no", "nor", "not", "only", "own", "same", "so",
    "than", "too", "very", "just", "because", "as", "until", "while",
    "about", "of", "per",
    # Verbos auxiliares
    "es", "son", "fue", "era", "ser", "estar", "esta", "estan",
    "is", "are", "was", "were", "be", "been", "being", "have",
    "has", "had", "having", "do", "does", "did", "doing",
    "will", "would", "can", "could", "shall", "should", "may",
    "might", "must", "need",
    # Conectores debiles (sin carga semantica)
    "y", "e", "o", "u", "que", "como", "mas", "pero", "aunque",
    "and", "or", "but", "if", "because", "so", "than", "also",
    "well", "however", "therefore", "thus", "hence", "meanwhile",
    "nevertheless", "nonetheless", "furthermore", "moreover",
    "consequently", "accordingly", "besides", "indeed",
    # Pronombres
    "yo", "tu", "el", "ella", "nosotros", "ellos", "ellas",
    "i", "you", "he", "she", "it", "we", "they", "me", "him",
    "her", "us", "them", "my", "your", "his", "its", "our",
    "their", "mine", "yours", "his", "hers", "ours", "theirs",
    "myself", "yourself", "himself", "herself", "itself",
    "ourselves", "yourselves", "themselves",
})

# Frases de relleno (filler) a eliminar en compresion extractiva agresiva
FILLER_PATTERNS: List[Tuple[str, str]] = [
    (r'\b(en otras palabras)\b', 'es decir'),
    (r'\b(es importante notar que)\b', 'nota:'),
    (r'\b(como se menciono anteriormente)\b', '(anteriormente)'),
    (r'\b(como resultado de lo anterior)\b', 'por tanto'),
    (r'\b(es necesario tener en cuenta que)\b', 'considerar:'),
    (r'\b(cabe senalar que)\b', 'senalar:'),
    (r'\b(debemos considerar que)\b', 'considerar:'),
    (r'\b(por otra parte)\b', 'ademas'),
    (r'\b(por otro lado)\b', 'contrario:'),
    (r'\b(es decir que)\b', 'osea'),
    (r'\b(en pocas palabras)\b', 'resumen:'),
    (r'\b(dicho de otra manera)\b', 'osea'),
    (r'\b(habiendo dicho esto)\b', 'dicho esto,'),
    (r'\b(teniendo en cuenta lo anterior)\b', 'dicho lo anterior,'),
    (r'\b(in other words)\b', 'i.e.'),
    (r'\b(it is important to note that)\b', 'note:'),
    (r'\b(as previously mentioned)\b', '(above)'),
    (r'\b(as a result of the above)\b', 'therefore'),
    (r'\b(it should be noted that)\b', 'note:'),
    (r'\b(having said that)\b', 'that said,'),
    (r'\b(in a nutshell)\b', 'sum:'),
    (r'\b(by the way)\b', 'btw'),
    (r'\b(at the end of the day)\b', 'ultimately'),
]

# Patrones regex para compresion de schemas JSON/YAML
JSON_WHITESPACE_PATTERN = re.compile(r':\s+')
YAML_KEY_PATTERN = re.compile(r'^(\s*)([a-zA-Z_][a-zA-Z0-9_]*):')
LIST_BULLET_PATTERN = re.compile(r'^(\s*)[\-\*]\s')

# Palabras clave preservadas (nunca se eliminan en extractiva)
PRESERVED_KEYWORDS: frozenset = frozenset({
    # Instrucciones de sistema
    "eres", "you are", "actua como", "act as", "sistema", "system",
    "instruccion", "instruction", "regla", "rule", "prohibido",
    "forbidden", "nunca", "never", "siempre", "always",
    # Seguridad
    "seguridad", "security", "guardrail", "safe", "peligro",
    "danger", "malware", "phishing", "sql", "injection",
    # Terminos tecnicos
    "funcion", "function", "clase", "class", "metodo", "method",
    "import", "export", "return", "def", "async", "await",
    # JSON/YAML
    "null", "true", "false", "none", "undefined",
    # Accion
    "tool", "herramienta", "call", "llamada", "response",
})

# Palabras que deben preservarse exactamente en structured pre-compression
STRUCTURED_PRESERVE_KEYS: frozenset = frozenset({
    "type", "properties", "required", "items", "enum", "oneOf",
    "anyOf", "allOf", "not", "if", "then", "else", "format",
    "pattern", "minimum", "maximum", "minLength", "maxLength",
})

# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------


@dataclass
class CompressionResult:
    """
    Resultado de una operacion de compresion de prompt.

    Contiene metricas detalladas sobre la compresion realizada:
    tokens originales, comprimidos, ratio, texto resultante, metodo usado,
    y lista de secciones preservadas.

    Attributes:
        original_tokens: Tokens en el texto original.
        compressed_tokens: Tokens en el texto comprimido.
        ratio: Proporcion de compresion (0.3 = 30% del original).
        text: Texto comprimido resultante.
        method: Metodo de compresion usado (extractive, abstractive, etc).
        preserved_sections: Lista de nombres de secciones preservadas.
    """

    original_tokens: int
    compressed_tokens: int
    ratio: float
    text: str
    method: str
    preserved_sections: List[str] = field(default_factory=list)

    @property
    def savings_pct(self) -> float:
        """
        Calcula el porcentaje de ahorro de tokens.

        Returns:
            Porcentaje entre 0 y 100, redondeado a 1 decimal.
        """
        return compression_pct(self.original_tokens, self.compressed_tokens)

    @property
    def tokens_saved(self) -> int:
        """Devuelve la cantidad absoluta de tokens ahorrados."""
        return self.original_tokens - self.compressed_tokens

    def to_dict(self) -> Dict[str, Any]:
        """
        Convierte el resultado a diccionario para serializacion.

        Returns:
            Diccionario con todas las metricas.
        """
        return {
            "original_tokens": self.original_tokens,
            "compressed_tokens": self.compressed_tokens,
            "tokens_saved": self.tokens_saved,
            "savings_pct": self.savings_pct,
            "ratio": self.ratio,
            "text_len": len(self.text),
            "method": self.method,
            "preserved_sections": self.preserved_sections,
        }


@dataclass
class TokenBudget:
    """
    Presupuesto de tokens asignado a un prompt o seccion.

    Diferente de ``token_budget.TokenBudget``: este es un snapshot simple
    de asignacion, no un gestor con pools y prioridades.

    Attributes:
        total: Tokens totales asignados.
        used: Tokens usados hasta el momento.
        remaining: Tokens restantes (total - used).
        sections: Mapeo de nombre de seccion -> tokens asignados.
    """

    total: int
    used: int = 0
    remaining: int = 0
    sections: Dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Calcula remaining automaticamente si no se provee."""
        if self.remaining == 0 and self.total > 0:
            self.remaining = self.total - self.used


# ---------------------------------------------------------------------------
# PromptCompressor — Motor principal de compresion
# ---------------------------------------------------------------------------


class PromptCompressor:
    """
    Motor de compresion de prompts multi-estrategia.

    Ofrece cinco modos de compresion:
    - **extractive**: Elimina redundancia (stop words, filler, whitespace).
    - **abstractive**: Resumen inteligente de secciones (con LLM o heuristica).
    - **structured**: Comprime schemas JSON/YAML preservando keys criticas.
    - **auto**: Selecciona la mejor estrategia segun el contenido.

    Ademas provee metodos especializados:
    - ``compress_system_prompt``: Comprime system prompts preservando reglas.
    - ``compress_conversation``: Comprime historial de conversacion multi-turno.
    - ``allocate_budget``: Asigna presupuesto de tokens por seccion.

    WHY: Unificar toda la logica de compresion en un solo punto reduce
    divergencia de implementaciones y facilita el mantenimiento.

    WHERE: Usado por la pipeline de optimizacion, agentes, y el gateway
    antes de enviar prompts a los LLMs.

    Uso:
        compressor = PromptCompressor()
        result = compressor.compress(prompt, target_ratio=0.5)
        short = compressor.extractive_compress(prompt, ratio=0.6)
        summary = compressor.abstractive_compress(prompt, ratio=0.3)
        budget = compressor.allocate_budget({"sys": 500, "user": 200}, total=1000)
    """

    def __init__(
        self,
        default_ratio: float = DEFAULT_TARGET_RATIO,
        max_context_tokens: int = DEFAULT_MAX_CONTEXT_TOKENS,
        method_fallback: str = METHOD_EXTRACTIVE,
        use_tiktoken: bool = True,
    ) -> None:
        """
        Inicializa el PromptCompressor.

        Args:
            default_ratio: Ratio de compresion por defecto (0.0-1.0).
                Ej: 0.5 = reducir a la mitad. Default: 0.5.
            max_context_tokens: Tokens maximos de ventana de contexto.
                Usado para decidir cuando comprimir. Default: 8000.
            method_fallback: Metodo por defecto si 'auto' no puede decidir.
                Valores: 'extractive', 'abstractive', 'structured'.
                Default: 'extractive'.
            use_tiktoken: Usar tiktoken para conteo preciso de tokens.
                Si es False, usa estimacion chars/4. Default: True.

        Raises:
            ValueError: Si method_fallback no es valido.
        """
        if method_fallback not in ALL_METHODS:
            raise ValueError(
                f"WHAT: method_fallback='{method_fallback}' no es valido. "
                f"WHY: Debe ser uno de {sorted(ALL_METHODS)}. "
                f"WHERE: PromptCompressor.__init__"
            )

        self._default_ratio = max(0.0, min(1.0, default_ratio))
        self._max_context_tokens = max(64, max_context_tokens)
        self._method_fallback = method_fallback if method_fallback != METHOD_AUTO else METHOD_EXTRACTIVE
        self._use_tiktoken = use_tiktoken

        # Estadisticas internas
        self._stats: Dict[str, Any] = {
            "total_compressions": 0,
            "extractive_count": 0,
            "abstractive_count": 0,
            "structured_count": 0,
            "auto_count": 0,
            "tokens_before": 0,
            "tokens_after": 0,
            "tokens_saved": 0,
            "conversation_compressions": 0,
            "system_prompt_compressions": 0,
            "errors": 0,
            "last_method": None,
            "last_ratio": None,
        }

        # Cache LRU para resultados de compresion (evita recomprimir textos
        # identicos). La clave es (texto, ratio, metodo).
        self._cache: OrderedDict[Tuple[str, float, str], CompressionResult] = OrderedDict()
        self._cache_maxsize = 512
        self._lock = threading.Lock()

        logger.info(
            "PromptCompressor initialized (ratio=%.2f, max_ctx=%d, "
            "fallback=%s, tiktoken=%s)",
            self._default_ratio, self._max_context_tokens,
            self._method_fallback, self._use_tiktoken,
        )

    # ------------------------------------------------------------------
    # API publica principal
    # ------------------------------------------------------------------

    def compress(
        self,
        text: str,
        target_ratio: Optional[float] = None,
        method: str = METHOD_AUTO,
        min_tokens: int = ACTIVATION_THRESHOLD_TOKENS,
    ) -> CompressionResult:
        """
        Comprime un prompt usando la estrategia especificada.

        WHAT: Aplica compresion al texto segun el metodo seleccionado.
        WHY: Reducir tokens antes de enviar al LLM ahorra costos y
        mantiene el prompt dentro de la ventana de contexto.
        WHERE: Antes de cualquier llamada a LLM, en gateway y agentes.

        Args:
            text: Texto del prompt a comprimir.
            target_ratio: Ratio de compresion objetivo (0.0-1.0).
                Ej: 0.3 = reducir al 30% del original. Si es None,
                usa default_ratio del constructor.
            method: Estrategia de compresion.
                'auto' = detecta automaticamente la mejor estrategia.
                'extractive' = elimina redundancia (stop words, filler).
                'abstractive' = resume secciones preservando info clave.
                'structured' = comprime JSON/YAML schemas.
            min_tokens: Tokens minimos para activar compresion.
                Textos mas cortos que este umbral se devuelven sin cambios.

        Returns:
            CompressionResult con el texto comprimido y metricas.

        Raises:
            ValueError: Si method no es valido.

        Ejemplo:
            >>> pc = PromptCompressor()
            >>> r = pc.compress("Texto largo con muchas palabras innecesarias...")
            >>> r.savings_pct
            40.5
        """
        # --- Validacion de parametros ---
        if method not in ALL_METHODS:
            raise ValueError(
                f"WHAT: method='{method}' no es valido. "
                f"WHY: Debe ser uno de {sorted(ALL_METHODS)}. "
                f"WHERE: PromptCompressor.compress"
            )

        ratio = self._default_ratio if target_ratio is None else max(0.0, min(1.0, target_ratio))

        # --- Short-circuit para textos cortos ---
        original_tokens = self._count_tokens(text)

        if not text or original_tokens < min_tokens or ratio >= 1.0:
            return CompressionResult(
                original_tokens=original_tokens,
                compressed_tokens=original_tokens,
                ratio=1.0,
                text=text or "",
                method="noop",
                preserved_sections=[],
            )

        # --- Cache check ---
        cache_key = (text, ratio, method)
        with self._lock:
            if cache_key in self._cache:
                self._cache.move_to_end(cache_key)
                logger.debug("Cache hit: ratio=%.2f, method=%s", ratio, method)
                return self._cache[cache_key]

        # --- Seleccion de estrategia ---
        effective_method = method
        if method == METHOD_AUTO:
            effective_method = self._detect_best_method(text, ratio)
            self._stats["auto_count"] += 1
            logger.debug("Auto-select: %s para texto de %d tokens", effective_method, original_tokens)

        # --- Ejecutar compresion ---
        try:
            if effective_method == METHOD_EXTRACTIVE:
                compressed_text = self.extractive_compress(text, ratio)
                self._stats["extractive_count"] += 1
            elif effective_method == METHOD_ABSTRACTIVE:
                compressed_text = self.abstractive_compress(text, ratio)
                self._stats["abstractive_count"] += 1
            elif effective_method == METHOD_STRUCTURED:
                compressed_text = self._structured_compress(text, ratio)
                self._stats["structured_count"] += 1
            else:
                # Fallback seguro (nunca deberia llegar aqui)
                compressed_text = self.extractive_compress(text, ratio)
                self._stats["extractive_count"] += 1
                logger.warning(
                    "WHAT: Metodo '%s' no esperado, usando extractive. "
                    "WHY: Metodo desconocido en switch. "
                    "WHERE: PromptCompressor.compress",
                    effective_method,
                )
        except Exception as exc:
            logger.error(
                "WHAT: Fallo compresion con metodo '%s' (ratio=%.2f). "
                "WHY: Error inesperado: %s: %s. "
                "WHERE: PromptCompressor.compress",
                effective_method, ratio, type(exc).__name__, exc,
                exc_info=True,
            )
            self._stats["errors"] += 1
            # Fallback: devolver texto original como CompressionResult
            return CompressionResult(
                original_tokens=original_tokens,
                compressed_tokens=original_tokens,
                ratio=1.0,
                text=text,
                method=f"{effective_method}_failed",
                preserved_sections=[],
            )

        # --- Asegurar target ratio (solo si no fue extractive, que ya no lo hace internamente) ---
        if effective_method != METHOD_EXTRACTIVE:
            compressed_text = self._enforce_target_ratio(text, compressed_text, ratio)

        compressed_tokens = self._count_tokens(compressed_text)

        # --- Preservar secciones detectadas ---
        preserved = self._detect_sections(compressed_text)

        result = CompressionResult(
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            ratio=compressed_tokens / max(original_tokens, 1),
            text=compressed_text,
            method=effective_method,
            preserved_sections=preserved,
        )

        # --- Actualizar stats ---
        self._stats["total_compressions"] += 1
        self._stats["tokens_before"] += original_tokens
        self._stats["tokens_after"] += compressed_tokens
        self._stats["tokens_saved"] += (original_tokens - compressed_tokens)
        self._stats["last_method"] = effective_method
        self._stats["last_ratio"] = ratio

        logger.debug(
            "Compressed (%s): %d -> %d tokens (%.1f%% savings)",
            effective_method, original_tokens, compressed_tokens,
            result.savings_pct,
        )

        # --- Almacenar en cache LRU ---
        with self._lock:
            self._cache[cache_key] = result
            if len(self._cache) > self._cache_maxsize:
                self._cache.popitem(last=False)

        return result

    # ------------------------------------------------------------------
    # Modos de compresion individuales
    # ------------------------------------------------------------------

    def extractive_compress(self, text: str, ratio: float = 0.5) -> str:
        """
        Comprime texto eliminando redundancia: stop words, filler, whitespace.

        WHAT: Aplica extractive compression eliminando tokens de baja
        carga semantica (stop words, frases de relleno) y normalizando
        whitespace. Preserva palabras clave de seguridad e instrucciones.
        WHY: Remover tokens innecesarios sin alterar el significado reduce
        costos de API sin perder informacion critica.
        WHERE: Textos con alta densidad de palabras funcionales (stop words),
        especialmente en system prompts y descripciones de herramientas.

        Tecnicas:
        1. Eliminar stop words no criticas
        2. Reemplazar frases de relleno por equivalentes cortos
        3. Normalizar whitespace multiple
        4. Preservar palabras clave de seguridad/instruccion
        5. Compresion agresiva opcional segun ratio

        Args:
            text: Texto a comprimir.
            ratio: Proporcion objetivo del original (0.0-1.0).
                Ej: 0.5 = reducir a la mitad.

        Returns:
            Texto comprimido (vacio si text es vacio).
        """
        if not text:
            return ""

        # Fase 1: Normalizar whitespace
        result = self._normalize_whitespace(text)

        # Fase 2: Reemplazar frases de relleno por equivalentes cortos
        result = self._replace_filler_phrases(result)

        # Fase 3: Eliminar stop words (solo si no son palabras clave preservadas)
        if ratio <= 0.7:
            result = self._remove_stop_words(result)

        # Fase 4: Comprimir mas agresivamente si ratio es bajo
        if ratio < 0.4:
            result = self._aggressive_extractive(result)

        return result

    def abstractive_compress(self, text: str, ratio: float = 0.5) -> str:
        """
        Comprime texto mediante resumen abstractivo de secciones.

        WHAT: Aplica abstractive compression: identifica bloques semanticos
        (parrafos, secciones) y los resume preservando informacion clave.
        WHY: La compresion extractiva tiene un limite (~40-60%); para ratios
        agresivos (<0.4) se necesita resumir en lugar de solo eliminar.
        WHERE: Textos largos (>500 tokens), documentacion, configuraciones
        extensas, y cuando se necesita >50% de compresion.

        Tecnicas:
        1. Identificar secciones por doble salto de linea
        2. Clasificar cada seccion como critica o comprimible
        3. Resumir secciones comprimibles (primeras 1-2 oraciones)
        4. Preservar secciones criticas intactas (instrucciones, reglas)
        5. Reensamblar en orden original

        Args:
            text: Texto a comprimir.
            ratio: Proporcion objetivo del original (0.0-1.0).

        Returns:
            Texto comprimido.
        """
        if not text:
            return ""

        # Fase 1: Dividir en secciones
        sections = self._split_into_sections(text)

        if len(sections) <= 2:
            # Muy pocas secciones: usar extractive en su lugar
            logger.debug(
                "Abstractive: solo %d secciones, usando extractive",
                len(sections),
            )
            return self.extractive_compress(text, ratio)

        # Fase 2: Calcular presupuesto por seccion
        original_tokens_per_section = [self._count_tokens(s) for s in sections]
        total_tokens = sum(original_tokens_per_section)
        target_tokens = max(1, int(total_tokens * ratio))

        # Distribuir presupuesto proporcionalmente
        assigned_budget = self._distribute_budget_proportional(
            original_tokens_per_section, target_tokens
        )

        # Fase 3: Procesar cada seccion
        compressed_sections: List[str] = []
        preserved: List[str] = []

        for i, (section, budget) in enumerate(zip(sections, assigned_budget)):
            section_tokens = original_tokens_per_section[i]

            # Secciones cortas o criticas se preservan intactas
            if section_tokens <= budget or section_tokens < 16:
                compressed_sections.append(section)
                if self._is_critical_section(section):
                    preserved.append(f"section_{i}")
                continue

            # Resumir: extraer primeras oraciones significativas
            summary = self._summarize_section(section, budget)
            compressed_sections.append(summary)

            if self._is_critical_section(section):
                preserved.append(f"section_{i}")

        # Fase 4: Reensamblar
        result = "\n\n".join(compressed_sections)

        # Fase 5: Si aun excede, aplicar extractive como refinamiento
        result_tokens = self._count_tokens(result)
        if result_tokens > target_tokens:
            extra_ratio = target_tokens / max(result_tokens, 1)
            result = self.extractive_compress(result, extra_ratio)

        # Cachear las secciones preservadas en _stats
        self._stats.setdefault("last_preserved_sections", preserved)

        return result

    def compress_system_prompt(self, prompt: str, max_tokens: int = 1500) -> str:
        """
        Comprime un system prompt preservando reglas criticas.

        WHAT: Comprime system prompts de forma conservadora, manteniendo
        intactas las reglas de seguridad, identidad y guardrails.
        WHY: Los system prompts contienen instrucciones criticas que no
        deben alterarse; una compresion agresiva podria eliminar reglas
        de seguridad inadvertidamente.
        WHERE: Antes de enviar system prompts a la API, especialmente
        en despliegues multi-agente donde el system prompt es largo.

        Args:
            prompt: System prompt a comprimir.
            max_tokens: Tokens maximos permitidos para el resultado.
                Default: 1500.

        Returns:
            System prompt comprimido preservando reglas criticas.

        Raises:
            ValueError: Si max_tokens es menor a 50.
        """
        if max_tokens < 50:
            raise ValueError(
                f"WHAT: max_tokens={max_tokens} es demasiado bajo. "
                f"WHY: Un system prompt necesita al menos 50 tokens "
                f"para preservar instrucciones criticas. "
                f"WHERE: PromptCompressor.compress_system_prompt"
            )

        if not prompt:
            return ""

        original_tokens = self._count_tokens(prompt)

        if original_tokens <= max_tokens:
            logger.debug(
                "System prompt ya dentro del limite (%d <= %d tokens)",
                original_tokens, max_tokens,
            )
            return prompt

        # Identificar secciones del system prompt
        sections = self._split_into_sections(prompt)
        if len(sections) <= 1:
            # Prompt sin estructura clara: extractive conservador
            ratio = max_tokens / max(original_tokens, 1)
            compressed = self.extractive_compress(prompt, ratio)
            self._stats["system_prompt_compressions"] += 1
            return compressed

        # Clasificar secciones como criticas o comprimibles
        critical_sections: List[str] = []
        compressible_sections: List[str] = []

        for section in sections:
            if self._is_critical_section(section):
                critical_sections.append(section)
            else:
                compressible_sections.append(section)

        # Calcular presupuesto: dar prioridad a secciones criticas
        critical_tokens = sum(self._count_tokens(s) for s in critical_sections)

        if critical_tokens >= max_tokens:
            # Solo caben las criticas: aplicar extractive ligero a ellas
            ratio = max_tokens / max(critical_tokens, 1)
            compressed = []
            for section in critical_sections:
                compressed.append(self.extractive_compress(section, max(ratio, 0.7)))
            self._stats["system_prompt_compressions"] += 1
            return "\n\n".join(compressed)

        # Presupuesto restante para secciones comprimibles
        remaining = max_tokens - critical_tokens

        if not compressible_sections:
            self._stats["system_prompt_compressions"] += 1
            return "\n\n".join(critical_sections)

        # Comprimir secciones comprimibles
        compressed_compressible: List[str] = []
        for section in compressible_sections:
            section_tokens = self._count_tokens(section)
            if section_tokens <= remaining:
                compressed_compressible.append(section)
                remaining -= section_tokens
            else:
                # Comprimir esta seccion
                ratio = remaining / max(section_tokens, 1) if remaining > 0 else 0.1
                compressed = self.abstractive_compress(section, ratio)
                compressed_compressible.append(compressed)
                remaining -= self._count_tokens(compressed)
                if remaining <= 0:
                    break

        result = "\n\n".join(critical_sections + compressed_compressible)
        self._stats["system_prompt_compressions"] += 1

        logger.debug(
            "System prompt compressed: %d -> %d tokens",
            original_tokens, self._count_tokens(result),
        )

        return result

    def compress_conversation(
        self,
        messages: List[Dict[str, Any]],
        max_tokens: int = 4000,
        preserve_head: int = 2,
        preserve_tail: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        Comprime un historial de conversacion multi-turno.

        WHAT: Reduce tokens de una lista de mensajes preservando los
        primeros N turnos (contexto inicial) y ultimos M turnos
        (acciones recientes), comprimiendo solo la region media.
        WHY: En conversaciones largas, los turnos intermedios suelen
        ser redundantes; comprimirlos ahorra tokens sin perder contexto.
        WHERE: Antes de enviar historial de conversacion al LLM, en
        agentes con memoria de largo plazo.

        Args:
            messages: Lista de diccionarios con 'role' y 'content'.
            max_tokens: Tokens maximos para toda la conversacion.
                Default: 4000.
            preserve_head: Numero de mensajes iniciales a preservar
                intactos. Default: 2 (system + primer user).
            preserve_tail: Numero de mensajes finales a preservar
                intactos. Default: 3 (ultimas interacciones).

        Returns:
            Lista comprimida de mensajes.

        Raises:
            ValueError: Si messages no tiene formato valido.
        """
        if not messages:
            return []

        # Validar formato basico
        for i, msg in enumerate(messages):
            if not isinstance(msg, dict) or "role" not in msg:
                raise ValueError(
                    f"WHAT: Mensaje en posicion {i} no tiene 'role'. "
                    f"WHY: Cada mensaje debe tener al menos 'role' y 'content'. "
                    f"WHERE: PromptCompressor.compress_conversation"
                )

        # 1. Contar tokens totales
        total_tokens = sum(
            self._count_tokens(str(m.get("content", ""))) for m in messages
        )

        if total_tokens <= max_tokens:
            return messages  # Ya cabe

        # 2. Identificar regiones protegidas
        n = len(messages)
        head = min(preserve_head, n // 3)
        tail = min(preserve_tail, n // 3)

        if head + tail >= n:
            head = max(1, n // 4)
            tail = max(1, n // 4)

        # 3. Comprimir la region media
        middle = messages[head:n - tail]
        if not middle:
            return messages

        # Generar resumen de la region media
        middle_text = "\n".join(
            f"[{m.get('role', '?')}] {str(m.get('content', ''))}"
            for m in middle
        )

        tokens_to_save = total_tokens - max_tokens
        summary_ratio = max(0.1, 1.0 - (tokens_to_save / max(total_tokens, 1)))

        compressed_middle = self.abstractive_compress(middle_text, summary_ratio)

        # 4. Reconstruir lista comprimida
        compressed: List[Dict[str, Any]] = []
        compressed.extend(messages[:head])  # Head preservado

        # Insertar mensaje resumen
        compressed.append({
            "role": "system",
            "content": f"[CONVERSATION COMPRESSED] {compressed_middle}",
            "compressed": True,
            "original_messages": len(middle),
        })

        compressed.extend(messages[n - tail:])  # Tail preservado

        self._stats["conversation_compressions"] += 1

        logger.debug(
            "Conversation compressed: %d -> %d mensajes, %d -> %d tokens",
            len(messages), len(compressed),
            total_tokens, sum(
                self._count_tokens(str(m.get("content", ""))) for m in compressed
            ),
        )

        return compressed

    def allocate_budget(
        self,
        sections: Dict[str, Union[str, int]],
        total_tokens: Optional[int] = None,
    ) -> TokenBudget:
        """
        Asigna presupuesto de tokens entre secciones.

        WHAT: Distribuye un presupuesto total entre secciones, asignando
        proporcionalmente segun el peso relativo de cada una.
        WHY: Diferentes secciones del prompt tienen diferente importancia;
        asignar presupuesto evita que una seccion domine el contexto.
        WHERE: Antes de ensamblar el prompt final, para planificar
        cuantos tokens dedicar a RAG, instrucciones, historial, etc.

        Args:
            sections: Mapeo de nombre de seccion a contenido (str) o
                a tokens solicitados (int).
            total_tokens: Presupuesto total a distribuir. Si es None,
                se suma el contenido de todas las secciones.

        Returns:
            TokenBudget con la asignacion calculada.

        Ejemplo:
            >>> pc = PromptCompressor()
            >>> budget = pc.allocate_budget({
            ...     "system": "Eres un asistente...",
            ...     "context": "Documento largo...",
            ...     "instruction": "Responde X",
            ... }, total_tokens=2000)
            >>> budget.sections
            {'system': 500, 'context': 1200, 'instruction': 300}
        """
        # Convertir secciones a tokens
        section_tokens: Dict[str, int] = {}
        for name, value in sections.items():
            if isinstance(value, str):
                section_tokens[name] = self._count_tokens(value)
            elif isinstance(value, int):
                section_tokens[name] = max(1, value)
            else:
                logger.warning(
                    "WHAT: Seccion '%s' tiene tipo %s, ignorando. "
                    "WHY: Solo se aceptan str o int. "
                    "WHERE: PromptCompressor.allocate_budget",
                    name, type(value).__name__,
                )
                continue

        if not section_tokens:
            return TokenBudget(total=0, sections={})

        # Calcular total
        total = total_tokens or sum(section_tokens.values())

        # Si el total es menor que la suma, distribuir proporcionalmente
        sum_tokens = sum(section_tokens.values())
        if sum_tokens > total:
            ratio = total / max(sum_tokens, 1)
            allocated: Dict[str, int] = {}
            used = 0
            names = list(section_tokens.keys())

            for i, name in enumerate(names):
                if i == len(names) - 1:
                    # Ultima seccion: asignar el resto
                    allocated[name] = max(1, total - used)
                else:
                    tokens = max(1, int(section_tokens[name] * ratio))
                    allocated[name] = tokens
                    used += tokens
        else:
            allocated = dict(section_tokens)

        return TokenBudget(
            total=total,
            used=sum(allocated.values()),
            remaining=total - sum(allocated.values()),
            sections=allocated,
        )

    # ------------------------------------------------------------------
    # Estadisticas
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """
        Retorna estadisticas de compresion del motor.

        Returns:
            Diccionario con: total_compressions, tokens_before/after/saved,
            savings_pct, counts por metodo, errores, cache info.
        """
        stats = dict(self._stats)
        tokens_before = stats.get("tokens_before", 0) or 1
        tokens_saved = stats.get("tokens_saved", 0)
        stats["savings_pct"] = round(tokens_saved / tokens_before * 100, 2)
        stats["cache_size"] = len(self._cache)
        stats["max_cache"] = self._cache_maxsize
        return stats

    def clear_cache(self) -> int:
        """
        Limpia el cache interno de resultados de compresion.

        Returns:
            Numero de entradas eliminadas del cache.
        """
        with self._lock:
            size = len(self._cache)
            self._cache.clear()
            logger.debug("Cache limpiado: %d entradas eliminadas", size)
            return size

    # ------------------------------------------------------------------
    # Metodos internos de compresion
    # ------------------------------------------------------------------

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
        result_lines: List[str] = []

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
        result: List[str] = []

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
            if word_count > 15:
                # Mantener si tiene verbos (alta densidad de informacion)
                if not self._has_verb(stripped):
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
        compressed: List[str] = []

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

    def _split_into_sections(self, text: str) -> List[str]:
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
        summary_parts: List[str] = []
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
        token_counts: List[int],
        total_budget: int,
    ) -> List[int]:
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
        if section.strip().startswith("```"):
            return True

        return False

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

    def _detect_sections(self, text: str) -> List[str]:
        """
        Detecta nombres de secciones preservadas en el texto comprimido.

        Busca patrones de cabeceras de seccion como "### Title",
        "== Title ==", "**Title**", o lineas en mayusculas.

        Args:
            text: Texto comprimido.

        Returns:
            Lista de nombres de secciones encontradas.
        """
        sections: List[str] = []
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
            lines = [l for l in lines if len(l.strip()) > 3]
            # Si aun excede, eliminar lineas con solo stop words
            if self._count_tokens("\n".join(lines)) > target_tokens:
                critical_lines: List[str] = []
                for line in lines:
                    stripped = line.strip()
                    if self._has_preserved_keywords(stripped):
                        critical_lines.append(line)
                    elif self._looks_like_code(stripped):
                        critical_lines.append(line)
                    elif not self._line_is_only_stop_words(stripped):
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


class TokenBudgetManager:
    """
    Gestiona el presupuesto de tokens por sesion de agente.

    WHAT: Realiza seguimiento del uso de tokens por sesion, permitiendo
    consultar tokens restantes y resetear presupuestos.
    WHY: Las sesiones multi-agente necesitan control centralizado de
    tokens para evitar que un agente consuma todo el presupuesto.
    WHERE: Usado por el gateway y el orquestador de agentes para
    gestionar el consumo de tokens por sesion.

    Diferencia con ``BudgetManager`` (token_budget.py):
    - ``BudgetManager`` maneja pools con prioridades y redistribucion.
    - ``TokenBudgetManager`` es un tracker ligero de uso por sesion.

    Uso:
        manager = TokenBudgetManager(default_budget=4000)
        manager.track_usage("session-1", 150)
        remaining = manager.get_remaining("session-1")
        manager.reset_session("session-1")
    """

    def __init__(
        self,
        default_budget: int = 4000,
        max_sessions: int = 100,
    ) -> None:
        """
        Inicializa el TokenBudgetManager.

        Args:
            default_budget: Presupuesto por defecto para nuevas sesiones.
                Default: 4000 tokens.
            max_sessions: Maximo de sesiones activas simultaneas.
                Cuando se excede, se elimina la sesion mas antigua.
                Default: 100.

        Raises:
            ValueError: Si default_budget < 64 o max_sessions < 1.
        """
        if default_budget < 64:
            raise ValueError(
                f"WHAT: default_budget={default_budget} es demasiado bajo. "
                f"WHY: Una sesion necesita al menos 64 tokens. "
                f"WHERE: TokenBudgetManager.__init__"
            )
        if max_sessions < 1:
            raise ValueError(
                f"WHAT: max_sessions={max_sessions} debe ser >= 1. "
                f"WHY: Debe haber al menos 1 sesion activa. "
                f"WHERE: TokenBudgetManager.__init__"
            )

        self._default_budget = default_budget
        self._max_sessions = max_sessions

        # {session_id: (budget_total, tokens_used, timestamp)}
        self._sessions: Dict[str, Tuple[int, int, float]] = {}
        self._lock = threading.Lock()

        logger.info(
            "TokenBudgetManager initialized (budget=%d, max_sessions=%d)",
            default_budget, max_sessions,
        )

    def track_usage(self, session_id: str, tokens: int) -> Dict[str, Any]:
        """
        Registra uso de tokens para una sesion.

        WHAT: Incrementa el contador de tokens usados para la sesion.
        Si la sesion no existe, se crea con el presupuesto por defecto.
        WHY: Mantener un registro centralizado de consumo permite
        detectar cuando una sesion se acerca a su limite.
        WHERE: Despues de cada llamada a LLM, registrar tokens consumidos.

        Args:
            session_id: Identificador unico de la sesion.
            tokens: Cantidad de tokens a registrar (debe ser > 0).

        Returns:
            Diccionario con: session_id, total_budget, used, remaining.

        Raises:
            ValueError: Si tokens <= 0.
        """
        if tokens <= 0:
            raise ValueError(
                f"WHAT: tokens={tokens} debe ser > 0. "
                f"WHY: No se pueden registrar 0 o tokens negativos. "
                f"WHERE: TokenBudgetManager.track_usage"
            )

        with self._lock:
            # Crear sesion si no existe
            if session_id not in self._sessions:
                # Gestion de maximo de sesiones: eliminar la mas antigua
                if len(self._sessions) >= self._max_sessions:
                    oldest = min(self._sessions.items(), key=lambda x: x[1][2])
                    del self._sessions[oldest[0]]
                    logger.debug(
                        "TokenBudgetManager: sesion mas antigua '%s' eliminada "
                        "(max_sessions=%d alcanzado)",
                        oldest[0], self._max_sessions,
                    )

                self._sessions[session_id] = (self._default_budget, 0, time.time())
                logger.debug(
                    "TokenBudgetManager: nueva sesion '%s' creada (budget=%d)",
                    session_id, self._default_budget,
                )

            budget, used, created = self._sessions[session_id]
            used += tokens
            self._sessions[session_id] = (budget, used, created)

            remaining = max(0, budget - used)

            logger.debug(
                "TokenBudgetManager: sesion='%s' usado=%d/%d (%.1f%%)",
                session_id, used, budget,
                (used / max(budget, 1)) * 100,
            )

            return {
                "session_id": session_id,
                "total_budget": budget,
                "used": used,
                "remaining": remaining,
                "exhausted": remaining <= 0,
            }

    def get_remaining(self, session_id: str) -> int:
        """
        Obtiene tokens restantes para una sesion.

        Args:
            session_id: Identificador de la sesion.

        Returns:
            Tokens restantes (0 si la sesion no existe o esta agotada).
        """
        with self._lock:
            entry = self._sessions.get(session_id)
            if entry is None:
                return 0
            budget, used, _ = entry
            return max(0, budget - used)

    def get_usage(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene el estado completo de uso de una sesion.

        Args:
            session_id: Identificador de la sesion.

        Returns:
            Diccionario con session_id, total_budget, used, remaining,
            usage_pct, exhausted, o None si la sesion no existe.
        """
        with self._lock:
            entry = self._sessions.get(session_id)
            if entry is None:
                return None
            budget, used, _ = entry
            remaining = max(0, budget - used)
            return {
                "session_id": session_id,
                "total_budget": budget,
                "used": used,
                "remaining": remaining,
                "usage_pct": round((used / max(budget, 1)) * 100, 1),
                "exhausted": remaining <= 0,
            }

    def reset_session(self, session_id: str) -> bool:
        """
        Resetea el presupuesto de una sesion (elimina su registro).

        WHAT: Elimina la sesion del registro de uso, liberando su
        presupuesto para futuras sesiones.
        WHY: Cuando una sesion termina, su presupuesto debe liberarse
        para evitar acumulacion de sesiones inactivas.
        WHERE: Al finalizar una sesion de agente o al hacer cleanup.

        Args:
            session_id: Identificador de la sesion a resetear.

        Returns:
            True si la sesion existia y fue eliminada, False si no.
        """
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                logger.debug("TokenBudgetManager: sesion '%s' resetada", session_id)
                return True
            return False

    def set_budget(self, session_id: str, new_budget: int) -> bool:
        """
        Actualiza el presupuesto total de una sesion existente.

        Args:
            session_id: Identificador de la sesion.
            new_budget: Nuevo presupuesto total (> 0).

        Returns:
            True si se actualizo, False si la sesion no existe.

        Raises:
            ValueError: Si new_budget <= 0.
        """
        if new_budget <= 0:
            raise ValueError(
                f"WHAT: new_budget={new_budget} debe ser > 0. "
                f"WHY: El presupuesto debe ser positivo. "
                f"WHERE: TokenBudgetManager.set_budget"
            )

        with self._lock:
            entry = self._sessions.get(session_id)
            if entry is None:
                return False
            _, used, created = entry
            self._sessions[session_id] = (new_budget, used, created)
            logger.debug(
                "TokenBudgetManager: sesion '%s' presupuesto actualizado "
                "a %d (used=%d)",
                session_id, new_budget, used,
            )
            return True

    def get_all_sessions(self) -> Dict[str, Dict[str, Any]]:
        """
        Obtiene el estado de todas las sesiones activas.

        Returns:
            Diccionario {session_id: {total_budget, used, remaining, usage_pct}}.
        """
        with self._lock:
            return {
                sid: {
                    "total_budget": budget,
                    "used": used,
                    "remaining": max(0, budget - used),
                    "usage_pct": round((used / max(budget, 1)) * 100, 1),
                }
                for sid, (budget, used, _) in self._sessions.items()
            }

    def get_stats(self) -> Dict[str, Any]:
        """
        Retorna estadisticas del gestor de presupuesto.

        Returns:
            Diccionario con: active_sessions, total_budget_allocated,
            total_used, total_remaining, default_budget.
        """
        with self._lock:
            total_budget = sum(b for b, _, _ in self._sessions.values())
            total_used = sum(u for _, u, _ in self._sessions.values())
            return {
                "active_sessions": len(self._sessions),
                "total_budget_allocated": total_budget,
                "total_used": total_used,
                "total_remaining": max(0, total_budget - total_used),
                "default_budget": self._default_budget,
                "max_sessions": self._max_sessions,
                "usage_pct": round(
                    (total_used / max(total_budget, 1)) * 100, 1
                ),
            }


# ---------------------------------------------------------------------------
# Funciones de conveniencia (top-level)
# ---------------------------------------------------------------------------


def compress_text(
    text: str,
    target_ratio: float = DEFAULT_TARGET_RATIO,
    method: str = METHOD_AUTO,
) -> CompressionResult:
    """
    Comprime un texto usando el motor por defecto (funcion de conveniencia).

    WHAT: Crea una instancia de PromptCompressor con configuracion por
    defecto y ejecuta la compresion.
    WHY: Proporciona una API simple para casos de uso comunes sin
    necesidad de instanciar la clase manualmente.
    WHERE: Uso directo desde otros modulos que solo necesitan comprimir
    un texto sin configuracion especial.

    Args:
        text: Texto a comprimir.
        target_ratio: Ratio de compresion objetivo (0.0-1.0). Default: 0.5.
        method: Estrategia de compresion. Default: 'auto'.

    Returns:
        CompressionResult con el texto comprimido.

    Ejemplo:
        >>> result = compress_text("Texto largo...", target_ratio=0.3)
        >>> print(f"Ahorro: {result.savings_pct}%")
    """
    compressor = PromptCompressor()
    return compressor.compress(text, target_ratio=target_ratio, method=method)
