"""
prompt_compressor.py — Compresion de prompts via LLMLingua-2.

Reduce tokens de entrada 40-60% usando un modelo BERT destilado
que clasifica tokens como 'preservar' o 'eliminar'.

Uso:
    compressor = PromptCompressor()
    compressed = compressor.compress(long_prompt, rate=0.5, force_tokens=[...])

Nota: LLMLingua-2 requiere ~500MB de descarga inicial del modelo.
Si no esta instalado, el compressor funciona en modo NO-OP (devuelve el prompt original).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Tokens que NUNCA deben ser eliminados durante la compresion
FORCE_TOKENS = [
    "##", "[", "]", "import", "def", "class", "return",
    "{{", "}}", "{%", "%}", "{#", "#}",
    "FDE", "EVO", "GUARDRAILS", "CHECKLIST",
    "```python", "```yaml", "```bash", "```json",
    "file://", "http://", "https://",
    "✅", "⚠️", "❌", "📌",
]


class PromptCompressor:
    """
    Compresor de prompts usando LLMLingua-2.

    Si LLMLingua no esta instalado, funciona como NO-OP
    (devuelve el prompt original sin cambios).

    Threshold de activacion: solo comprime prompts > 2000 caracteres.
    Para prompts cortos, la compression agregaria latencia sin beneficio.
    """

    ACTIVATION_THRESHOLD_CHARS = 2000

    def __init__(
        self,
        model_name: str = "microsoft/llmlingua-2-xlm-roberta-large-meetingbank",
        use_llmlingua2: bool = True,
        auto_download: bool = False,
    ):
        """
        Args:
            model_name: Modelo LLMLingua-2 de HuggingFace.
            use_llmlingua2: Usar v2 (True) o v1 (False).
            auto_download: Descargar modelo si no esta disponible.
        """
        self._model_name = model_name
        self._use_llmlingua2 = use_llmlingua2
        self._compressor: Any = None
        self._available: bool = False

        # Intentar importar
        self._try_init()

    def _try_init(self) -> None:
        """Intentar inicializar LLMLingua; fallar silenciosamente si no disponible."""
        try:
            from llmlingua import PromptCompressor as LLMPromptCompressor

            self._compressor = LLMPromptCompressor(
                model_name=self._model_name,
                use_llmlingua2=self._use_llmlingua2,
            )
            self._available = True
            logger.info(
                "PromptCompressor initialized with %s (v2=%s)",
                self._model_name, self._use_llmlingua2,
            )
        except ImportError:
            logger.warning(
                "LLMLingua not installed. PromptCompressor running in NO-OP mode. "
                "Install with: pip install llmlingua"
            )
        except Exception as exc:
            logger.warning(
                "LLMLingua init failed: %s. Running in NO-OP mode.", exc
            )

    @property
    def available(self) -> bool:
        """Return True if LLMLingua compressor is available."""
        return self._available

    def compress(
        self,
        prompt: str,
        rate: float = 0.5,
        force_tokens: Optional[List[str]] = None,
        min_tokens: int = 100,
    ) -> str:
        """
        Comprimir un prompt usando LLMLingua-2.

        Args:
            prompt: El prompt a comprimir.
            rate: Tasa de compresion objetivo (0.0-1.0). 0.5 = 50% mas corto.
            force_tokens: Lista de tokens que deben preservarse obligatoriamente.
            min_tokens: Numero minimo de tokens a mantener.

        Returns:
            Prompt comprimido (o el original si LLMLingua no esta disponible
            o el prompt es muy corto).
        """
        # NO-OP si no disponible
        if not self._available or self._compressor is None:
            return prompt

        # NO-OP para prompts cortos
        if len(prompt) < self.ACTIVATION_THRESHOLD_CHARS:
            return prompt

        # NO-OP si la tasa es 1.0 (sin compresion)
        if rate >= 1.0:
            return prompt

        effective_force = (force_tokens or []) + FORCE_TOKENS

        try:
            result = self._compressor.compress_prompt(
                prompt,
                rate=rate,
                force_tokens=effective_force,
                # Asegurar que no baje de min_tokens
                min_tokens=min_tokens,
            )
            compressed = result.get("compressed_prompt", prompt)

            logger.debug(
                "Compressed prompt: %d -> %d chars (%.1f%%)",
                len(prompt), len(compressed),
                (1 - len(compressed) / max(len(prompt), 1)) * 100,
            )
            return compressed

        except Exception as exc:
            logger.warning("Prompt compression failed: %s. Using original.", exc)
            return prompt

    def get_stats(self) -> Dict[str, Any]:
        """Return compressor status."""
        return {
            "available": self._available,
            "model": self._model_name,
            "use_v2": self._use_llmlingua2,
            "activation_threshold": self.ACTIVATION_THRESHOLD_CHARS,
            "force_tokens_count": len(FORCE_TOKENS),
        }
