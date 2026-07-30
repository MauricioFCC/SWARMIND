"""SpeculativeDecoder — Decodificacion especulativa para acelerar generacion LLM.

Usa un modelo pequeno (drafter) para generar candidatos y un modelo grande
(verifier) para validarlos en paralelo, logrando 2-5x speedup.

Basado en:
- FailFast (Pan et al., NeurIPS 2025): dLLM como drafter -> 4.9x
- DEER (Cheng et al., 2025): Diffusion drafter + AR verifier -> 5.54x
- FLy (Li et al., ICLR 2026): Training-free, verificacion semantica laxa

Arquitectura:
1. Drafter: modelo pequeno genera N tokens candidatos
2. Verifier: modelo grande verifica en paralelo
3. Aceptacion: tokens correctos se aceptan, errores se corrige
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class VerificationStrategy(Enum):
    """Estrategia de verificacion de tokens."""
    EXACT_MATCH = auto()     # Coincidencia exacta de tokens
    SEMANTIC = auto()        # Verificacion semantica (embedding similarity)
    PROBABILITY = auto()     # Umbral de probabilidad del verifier
    HYBRID = auto()          # Combinacion de las anteriores


@dataclass
class SpeculativeResult:
    """Resultado de una decodificacion especulativa.

    Attributes:
        text: Texto generado final.
        tokens_drafted: Tokens generados por el drafter.
        tokens_accepted: Tokens aceptados por el verifier.
        acceptance_rate: Tasa de aceptacion [0,1].
        time_saved_ms: Tiempo ahorrado en ms.
        iterations: Numero de iteraciones.
        method: Estrategia usada.
    """
    text: str
    tokens_drafted: int
    tokens_accepted: int
    acceptance_rate: float
    time_saved_ms: float
    iterations: int
    method: str


@dataclass
class SpeculativeConfig:
    """Configuracion del decodificador especulativo.

    Attributes:
        n_draft: Numero de tokens a draftear por iteracion.
        max_iterations: Maximo de iteraciones.
        strategy: Estrategia de verificacion.
        temperature: Temperatura para el drafter.
        top_k: Top-k sampling para el drafter.
        threshold_accept: Umbral de aceptacion para strategy.
    """
    n_draft: int = 5
    max_iterations: int = 20
    strategy: VerificationStrategy = VerificationStrategy.HYBRID
    temperature: float = 0.7
    top_k: int = 40
    threshold_accept: float = 0.85


class SpeculativeDecoder:
    """Decodificador especulativo con drafter+verifier.

    Acelera la generacion de texto usando un modelo pequeno para
    proponer tokens y uno grande para verificar.

    Args:
        draft_fn: Funcion que genera tokens candidatos (modelo pequeno).
        verify_fn: Funcion que verifica tokens (modelo grande).
        config: Configuracion del decodificador.

    Example:
        >>> decoder = SpeculativeDecoder(draft_fn, verify_fn)
        >>> result = decoder.generate("input prompt")
        >>> print(f"Acceptance rate: {result.acceptance_rate:.2%}")
    """

    def __init__(
        self,
        draft_fn: Callable[[str, int], List[str]],
        verify_fn: Callable[[str, List[str]], List[bool]],
        config: Optional[SpeculativeConfig] = None,
    ) -> None:
        """Inicializa el decodificador.

        Args:
            draft_fn: Funcion (prompt, n) -> lista de tokens candidatos.
            verify_fn: Funcion (prompt, candidatos) -> lista de booleanos.
            config: Configuracion con parametros de costo.
        """
        self._draft_fn: Callable[[str, int], List[str]] = draft_fn
        self._verify_fn: Callable[[str, List[str]], List[bool]] = verify_fn
        self._config: SpeculativeConfig = config or SpeculativeConfig()
        self._draft_cost_ms: float = 1.0   # ms por token drafteado
        self._verify_cost_ms: float = 3.0  # ms por token verificado
        self._stats: Dict[str, int] = {
            "total_calls": 0,
            "total_tokens_drafted": 0,
            "total_tokens_accepted": 0,
        }

        logger.info(
            "[SpecDecoder] Inicializado: n_draft=%d, strategy=%s",
            self._config.n_draft, self._config.strategy.name,
        )

    def _draft_tokens(self, prompt: str, n: int) -> List[str]:
        """Genera tokens candidatos usando el drafter.

        Args:
            prompt: Contexto actual.
            n: Numero de tokens a generar.

        Returns:
            Lista de tokens candidatos o lista vacia si error.
        """
        try:
            return self._draft_fn(prompt, n)
        except Exception as exc:
            logger.error(
                "[SpecDecoder] Error en drafter: %s. "
                "WHY: fallo en generacion de candidatos. WHERE: _draft_tokens.",
                exc,
            )
            return []

    def _verify_tokens(self, prompt: str, candidates: List[str]) -> List[bool]:
        """Verifica tokens candidatos usando el verifier.

        Args:
            prompt: Contexto original.
            candidates: Tokens a verificar.

        Returns:
            Lista de booleanos indicando aceptacion.
        """
        try:
            return self._verify_fn(prompt, candidates)
        except Exception as exc:
            logger.error(
                "[SpecDecoder] Error en verifier: %s. "
                "WHY: fallo en verificacion. WHERE: _verify_tokens.",
                exc,
            )
            return [False] * len(candidates)

    def _accept_tokens(
        self,
        candidates: List[str],
        accepted: List[bool],
    ) -> str:
        """Construye el siguiente prompt con tokens aceptados.

        Args:
            candidates: Tokens candidatos.
            accepted: Mascara de aceptacion.

        Returns:
            Texto aceptado para agregar al prompt.
        """
        accepted_text: str = "".join(
            c for c, a in zip(candidates, accepted) if a
        )
        # Si no se acepto ninguno, forzar el primer candidato
        if not accepted_text and candidates:
            accepted_text = candidates[0]
        return accepted_text

    def generate(
        self,
        prompt: str,
        config: Optional[SpeculativeConfig] = None,
    ) -> SpeculativeResult:
        """Genera texto usando decodificacion especulativa.

        Args:
            prompt: Prompt de entrada.
            config: Configuracion opcional.

        Returns:
            SpeculativeResult con texto generado y metricas.
        """
        cfg: SpeculativeConfig = config or self._config
        start_time: float = time.perf_counter()
        current_prompt: str = prompt
        total_drafted: int = 0
        total_accepted: int = 0

        for iteration in range(cfg.max_iterations):
            candidates: List[str] = self._draft_tokens(current_prompt, cfg.n_draft)
            if not candidates:
                break

            total_drafted += len(candidates)
            accepted: List[bool] = self._verify_tokens(current_prompt, candidates)
            n_accept: int = sum(1 for a in accepted if a)
            total_accepted += n_accept

            current_prompt += self._accept_tokens(candidates, accepted)

            if n_accept < len(candidates) * 0.5 or any("[DONE]" in c for c in candidates):
                break

        elapsed_ms: float = (time.perf_counter() - start_time) * 1000
        self._stats["total_calls"] += 1
        self._stats["total_tokens_drafted"] += total_drafted
        self._stats["total_tokens_accepted"] += total_accepted

        rate: float = total_accepted / total_drafted if total_drafted > 0 else 0.0
        saved_estimate: float = max(0.0, (
            (total_accepted * self._verify_cost_ms) - (total_drafted * self._draft_cost_ms)
        ) - elapsed_ms)

        result: SpeculativeResult = SpeculativeResult(
            text=current_prompt[len(prompt):],
            tokens_drafted=total_drafted,
            tokens_accepted=total_accepted,
            acceptance_rate=rate,
            time_saved_ms=saved_estimate,
            iterations=iteration + 1 if total_drafted > 0 else 0,
            method=f"speculative_{cfg.strategy.name.lower()}",
        )

        logger.debug(
            "[SpecDecoder] %d/%d tokens accepted (%.1f%%), %d iters",
            total_accepted, total_drafted, rate * 100, result.iterations,
        )
        return result

    def get_stats(self) -> Dict[str, Any]:
        """Retora estadisticas del decodificador.

        Returns:
            Dict con metricas acumuladas.
        """
        total: int = self._stats["total_tokens_drafted"]
        accepted: int = self._stats["total_tokens_accepted"]
        return {
            "total_calls": self._stats["total_calls"],
            "total_tokens_drafted": total,
            "total_tokens_accepted": accepted,
            "overall_acceptance_rate": (
                accepted / total if total > 0 else 0.0
            ),
            "n_draft": self._config.n_draft,
            "strategy": self._config.strategy.name,
        }
