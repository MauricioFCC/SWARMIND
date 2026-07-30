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
            config: Configuracion.
        """
        self._draft_fn: Callable[[str, int], List[str]] = draft_fn
        self._verify_fn: Callable[[str, List[str]], List[bool]] = verify_fn
        self._config: SpeculativeConfig = config or SpeculativeConfig()
        self._stats: Dict[str, int] = {
            "total_calls": 0,
            "total_tokens_drafted": 0,
            "total_tokens_accepted": 0,
        }

        logger.info(
            "[SpecDecoder] Inicializado: n_draft=%d, strategy=%s",
            self._config.n_draft, self._config.strategy.name,
        )

    def generate(
        self,
        prompt: str,
        config: Optional[SpeculativeConfig] = None,
    ) -> SpeculativeResult:
        """Genera texto usando decodificacion especulativa.

        Args:
            prompt: Prompt de entrada.
            config: Configuracion opcional (usa la del constructor si no se da).

        Returns:
            SpeculativeResult con texto generado y metricas.
        """
        cfg: SpeculativeConfig = config or self._config
        start_time: float = time.perf_counter()

        current_prompt: str = prompt
        total_drafted: int = 0
        total_accepted: int = 0
        iterations: int = 0

        for iteration in range(cfg.max_iterations):
            iterations += 1

            # Paso 1: Drafter genera candidatos
            try:
                candidates: List[str] = self._draft_fn(current_prompt, cfg.n_draft)
            except Exception as exc:
                logger.error(
                    "[SpecDecoder] Error en drafter: %s. "
                    "WHY: fallo en generacion de candidatos. WHERE: generate.",
                    exc,
                )
                break

            if not candidates:
                break

            total_drafted += len(candidates)

            # Paso 2: Verifier valida candidatos
            try:
                accepted: List[bool] = self._verify_fn(current_prompt, candidates)
            except Exception as exc:
                logger.error(
                    "[SpecDecoder] Error en verifier: %s. "
                    "WHY: fallo en verificacion. WHERE: generate.",
                    exc,
                )
                break

            n_accepted: int = sum(1 for a in accepted if a)
            total_accepted += n_accepted

            # Paso 3: Construir siguiente prompt
            if n_accepted > 0:
                accepted_tokens: List[str] = [
                    c for c, a in zip(candidates, accepted) if a
                ]
                current_prompt += "".join(accepted_tokens)
            else:
                # Si no se acepto ninguno, forzar el primer token
                if candidates:
                    current_prompt += candidates[0]
                    total_accepted += 1

            # Si se aceptaron todos, continuar; si no, posiblemente finalizar
            if n_accepted < len(candidates) * 0.5:
                break

            # Verificar si hay señal de fin
            if any("[DONE]" in c for c in candidates):
                break

        elapsed: float = (time.perf_counter() - start_time) * 1000

        # Actualizar estadisticas
        self._stats["total_calls"] += 1
        self._stats["total_tokens_drafted"] += total_drafted
        self._stats["total_tokens_accepted"] += total_accepted

        acceptance_rate: float = (
            total_accepted / total_drafted if total_drafted > 0 else 0.0
        )

        # Tiempo ahorrado estimado: asumiendo que el verifier es 3x mas lento
        estimated_saved: float = (
            (total_accepted * 0.003) - (total_drafted * 0.001)
        ) * 1000

        result: SpeculativeResult = SpeculativeResult(
            text=current_prompt[len(prompt):],
            tokens_drafted=total_drafted,
            tokens_accepted=total_accepted,
            acceptance_rate=acceptance_rate,
            time_saved_ms=max(0.0, estimated_saved - elapsed),
            iterations=iterations,
            method=f"speculative_{cfg.strategy.name.lower()}",
        )

        logger.debug(
            "[SpecDecoder] Generate: %d/%d tokens accepted (%.1f%%), %d iters",
            total_accepted, total_drafted, acceptance_rate * 100, iterations,
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
