"""
prompt_compressor.py — Compression de prompts multi-estrategia.

Estrategias (en orden de aplicacion):
  1. LIGHTWEIGHT (siempre activo): compresion heuristica sin modelo externo
     - Elimina whitespace redundante, acorta frases, remuevo comentarios
     - Ahorro: 20-30% tokens, 0ms latencia
  2. LLMLingua-2 (opcional): compresion por IA si el modelo esta disponible
     - Ahorro: 40-60% tokens, ~500ms latencia
  3. NO-OP: si todo falla, devuelve el prompt original

Uso:
    compressor = PromptCompressor()
    compressed = compressor.compress(prompt, rate=0.5)
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Tokens que NUNCA deben ser eliminados
FORCE_TOKENS = [
    "##", "[", "]", "import", "def", "class", "return",
    "{{", "}}", "{%", "%}", "{#", "#}",
    "```python", "```yaml", "```bash", "```json",
    "file://", "http://", "https://",
]

# Mapa de abreviaciones para frases comunes
ABBREVIATIONS = {
    r'implementacion': 'impl',
    r'documentacion': 'docs',
    r'configuracion': 'config',
    r'arquitectura': 'arq',
    r'funcionalidad': 'fn',
    r'recomendaciones': 'recom',
    r'seguridad': 'seg',
    r'validacion': 'val',
    r'integracion': 'int',
    r'comunicacion': 'comm',
    r'consolidacion': 'consol',
    r'verificacion': 'verif',
    r'utilizando': 'usando',
    r'mediante': 'con',
    r'relacionado': 'rel',
}


class PromptCompressor:
    """
    Compresor multi-estrategia.

    - Siempre aplica compresion LIGHTWEIGHT (sin modelo)
    - Si LLMLingua-2 esta instalado, aplica compresion por IA
    - Threshold: solo comprime prompts > ACTIVATION_THRESHOLD_CHARS
    """

    ACTIVATION_THRESHOLD_CHARS = 500  # Mas bajo = comprime mas seguido

    def __init__(
        self,
        model_name: str = "microsoft/llmlingua-2-xlm-roberta-large-meetingbank",
        use_llmlingua2: bool = True,
        auto_download: bool = False,
        lightweight_only: bool = True,
    ):
        """
        Args:
            model_name: Modelo LLMLingua-2 de HuggingFace.
            use_llmlingua2: Usar v2 (True) o v1 (False).
            auto_download: Descargar modelo si no esta disponible.
            lightweight_only: True = solo compresion ligera (sin LLMLingua).
        """
        self._model_name = model_name
        self._use_llmlingua2 = use_llmlingua2
        self._lightweight_only = lightweight_only
        self._llm_compressor: Any = None
        self._llm_available: bool = False

        if not lightweight_only:
            self._try_init_llmlingua()

    def _try_init_llmlingua(self) -> None:
        """Intentar inicializar LLMLingua; fallar silenciosamente si no disponible."""
        try:
            from llmlingua import PromptCompressor as LLMPromptCompressor

            self._llm_compressor = LLMPromptCompressor(
                model_name=self._model_name,
                use_llmlingua2=self._use_llmlingua2,
            )
            self._llm_available = True
            logger.info(
                "LLMLingua initialized with %s (v2=%s)",
                self._model_name, self._use_llmlingua2,
            )
        except ImportError:
            logger.debug("LLMLingua not installed. Using lightweight mode only.")
        except Exception as exc:
            logger.debug("LLMLingua init failed: %s. Using lightweight mode.", exc)

    @property
    def available(self) -> bool:
        """Return True if ANY compressor is available (lightweight always is)."""
        return True  # lightweight siempre disponible

    @property
    def llm_available(self) -> bool:
        """Return True if LLMLingua compressor is available."""
        return self._llm_available

    def compress(
        self,
        prompt: str,
        rate: float = 0.5,
        force_tokens: Optional[List[str]] = None,
        min_tokens: int = 50,
    ) -> str:
        """
        Comprimir un prompt.

        Args:
            prompt: El prompt a comprimir.
            rate: Tasa de compresion objetivo.
            force_tokens: Tokens que deben preservarse.
            min_tokens: Minimo de tokens a mantener.

        Returns:
            Prompt comprimido.
        """
        if not prompt or len(prompt) < self.ACTIVATION_THRESHOLD_CHARS:
            return prompt

        if rate >= 1.0:
            return prompt

        result = prompt

        # Fase 1: Siempre aplicar compresion LIGHTWEIGHT
        result = self._compress_lightweight(result, rate)

        # Fase 2: Si LLMLingua esta disponible, aplicar compresion adicional
        if self._llm_available and self._llm_compressor is not None and not self._lightweight_only:
            result = self._compress_llmlingua(result, rate, force_tokens, min_tokens)

        logger.debug(
            "Compressed: %d -> %d chars (%.1f%%)",
            len(prompt), len(result),
            (1 - len(result) / max(len(prompt), 1)) * 100,
        )
        return result

    def _compress_lightweight(self, text: str, rate: float) -> str:
        """
        Compresion ligera sin modelo externo.

        Tecnicas:
        1. Eliminar lineas de comentarios de cabecera (---...---)
        2. Acortar llaves de diccionarios en YAML
        3. Eliminar whitespace redundante
        4. Acortar frases comunes via abreviaciones
        5. Comprimir espaciado en listas
        """
        # 1. Acortar frontmatter YAML: eliminar descripciones largas
        text = re.sub(r'description: .{30,}', 'description: (ver nombre)', text)

        # 2. Acortar frases comunes
        for pattern, replacement in ABBREVIATIONS.items():
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

        # 3. Eliminar lineas de comentarios decorativos (====, ----, ####)
        text = re.sub(r'^[=\-#*]{10,}.*$', '', text, flags=re.MULTILINE)

        # 4. Comprimir whitespace multiple
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r'[ \t]{2,}', ' ', text)

        # 5. Eliminar lineas vacias al inicio/fin
        text = text.strip()

        # 6. Si rate es agresivo, acortar mas
        if rate < 0.4:
            # Eliminar lineas que son solo etiquetas vacias
            text = re.sub(r'^[a-z_]+:\s*$', '', text, flags=re.MULTILINE)
            text = re.sub(r'\n{2,}', '\n', text)

        return text

    def _compress_llmlingua(
        self,
        prompt: str,
        rate: float,
        force_tokens: Optional[List[str]],
        min_tokens: int,
    ) -> str:
        """Compresion via LLMLingua-2."""
        if not self._llm_compressor:
            return prompt

        effective_force = (force_tokens or []) + FORCE_TOKENS

        try:
            result = self._llm_compressor.compress_prompt(
                prompt,
                rate=rate,
                force_tokens=effective_force,
                min_tokens=min_tokens,
            )
            return result.get("compressed_prompt", prompt)
        except Exception as exc:
            logger.warning("LLMLingua compression failed: %s", exc)
            return prompt

    def get_stats(self) -> Dict[str, Any]:
        """Return compressor status."""
        return {
            "lightweight": True,
            "llm_available": self._llm_available,
            "model": self._model_name if self._llm_available else "lightweight-only",
            "activation_threshold": self.ACTIVATION_THRESHOLD_CHARS,
            "abbreviations_count": len(ABBREVIATIONS),
        }
