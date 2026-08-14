"""Ejecucion con failover (mixin ``_ExecutionMixin``).

Extraccion mecanica de los metodos de ejecucion/failover y delegados de
``MultiAPIProvider`` del modulo original (sin cambios de logica ni firmas).

Classes:
    _ExecutionMixin: Mixin con execute, execute_with_fallback,
        _execute_with_chain, _execute_on_provider y los delegados a
        provider_executors/provider_health usados por ``MultiAPIProvider``.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from harness.model_router.multi_provider_types import (
    LATENCY_WINDOW_SIZE,
    MAX_TOKENS_BY_AGENT,
    ExecutionResult,
    ProviderConfig,
)

logger = logging.getLogger("harness.model_router.multi_provider")


class _ExecutionMixin:
    """Mixin con la ejecucion multi-proveedor y el failover."""

    def execute(
        self,
        model: str,
        prompt: str,
        fallback: bool = True,
        agent_role: str = "*",
        max_tokens: int | None = None,
    ) -> ExecutionResult:
        """Ejecuta un prompt en el modelo solicitado con failover opcional.

        Busca el proveedor que ofrece el modelo especificado. Si falla y
        `fallback=True`, intenta con otros proveedores del mismo tier y luego
        de tiers inferiores.

        Args:
            model: Nombre del modelo a ejecutar.
            prompt: Texto de entrada para el modelo.
            fallback: Si es True, intenta failover a otros proveedores.
            agent_role: Rol del agente (para lÃ­mite de tokens).
            max_tokens: MÃ¡ximo de tokens de salida (opcional, sobreescribe
                el valor por rol).

        Returns:
            ExecutionResult con el resultado de la ejecuciÃ³n.

        WHY: Abstrae la complejidad de elegir proveedor, manejar fallos
        y reintentar automÃ¡ticamente.
        WHERE: execute en MultiAPIProvider.
        """
        if max_tokens is None:
            max_tokens = MAX_TOKENS_BY_AGENT.get(agent_role, MAX_TOKENS_BY_AGENT["*"])

        # 1. Buscar proveedor primario que ofrezca este modelo
        primary = self._find_provider_for_model(model)
        if primary is None:
            return ExecutionResult(
                success=False,
                output="",
                source="cloud",
                model=model,
                duration_ms=0,
                error=(
                    f"Model '{model}' no encontrado en ningÃºn proveedor registrado. "
                    "WHY: El modelo debe estar listado en algÃºn ProviderConfig.models. "
                    "WHERE: execute"
                ),
            )

        # 2. Ejecutar con failover chain
        return self._execute_with_chain(
            model=model,
            prompt=prompt,
            primary_provider=primary,
            fallback=fallback,
            agent_role=agent_role,
            max_tokens=max_tokens,
        )

    def execute_with_fallback(
        self,
        model: str,
        prompt: str,
        agent_role: str = "*",
        max_tokens: int | None = None,
    ) -> ExecutionResult:
        """Ejecuta un modelo intentando mÃºltiples proveedores en orden.

        A diferencia de execute(), este mÃ©todo ITERA sobre todos los
        proveedores registrados que tengan el modelo, en orden de tier
        (premium > standard > budget), hasta que uno responda exitosamente.

        Args:
            model: Nombre del modelo a ejecutar.
            prompt: Texto de entrada.
            agent_role: Rol del agente para lÃ­mite de tokens.
            max_tokens: MÃ¡ximo de tokens de salida.

        Returns:
            ExecutionResult con el primer resultado exitoso, o el Ãºltimo
            error si todos fallan.
        """
        return self.execute(
            model=model,
            prompt=prompt,
            fallback=True,
            agent_role=agent_role,
            max_tokens=max_tokens,
        )

    def _execute_with_chain(
        self,
        model: str,
        prompt: str,
        primary_provider: str,
        fallback: bool,
        agent_role: str,
        max_tokens: int,
    ) -> ExecutionResult:
        """Ejecuta en cadena: primario + failover ordenado por tier.

        Args:
            model: Modelo a ejecutar.
            prompt: Prompt de entrada.
            primary_provider: Proveedor primario.
            fallback: Habilitar failover.
            agent_role: Rol del agente.
            max_tokens: LÃ­mite de tokens de salida.

        Returns:
            ExecutionResult del primer Ã©xito o Ãºltimo error.
        """
        # Construir la secuencia de proveedores a intentar
        candidates = [primary_provider]

        if fallback:
            # Agregar resto de proveedores con este modelo, ordenados por tier
            rest = self._get_other_providers_for_model(model, primary_provider)
            candidates.extend(rest)

        last_error: str | None = None
        start = time.perf_counter()

        for provider_name in candidates:
            with self._lock:
                config = self._providers.get(provider_name, {}).get("config")
            if config is None:
                continue

            health = self._health.get(provider_name)
            if health is not None and not health.available:
                logger.debug(
                    "Skipping provider '%s' (unavailable). WHERE: _execute_with_chain",
                    provider_name,
                )
                continue

            logger.debug(
                "Attempting provider '%s' for model '%s'. WHERE: _execute_with_chain",
                provider_name, model,
            )

            result = self._execute_on_provider(
                provider_name=provider_name,
                config=config,
                model=model,
                prompt=prompt,
                max_tokens=max_tokens,
            )

            if result.success:
                elapsed = (time.perf_counter() - start) * 1000
                result.duration_ms = round(elapsed, 2)
                result.provider = provider_name
                self._record_success(provider_name, elapsed)
                return result

            last_error = result.error
            self._record_error(provider_name, result.error or "Unknown error")
            logger.warning(
                "Provider '%s' fallÃ³ para modelo '%s': %s. "
                "WHY: Failover al siguiente proveedor. "
                "WHERE: _execute_with_chain",
                provider_name, model, result.error,
            )

        elapsed = (time.perf_counter() - start) * 1000
        return ExecutionResult(
            success=False,
            output="",
            source="cloud",
            model=model,
            duration_ms=round(elapsed, 2),
            error=(
                f"Todos los proveedores fallaron para modelo '{model}'. "
                f"Ãšltimo error: {last_error}. "
                "WHY: La cadena de failover se agotÃ³. "
                "WHERE: _execute_with_chain"
            ),
        )

    def _execute_on_provider(
        self,
        provider_name: str,
        config: ProviderConfig,
        model: str,
        prompt: str,
        max_tokens: int,
    ) -> ExecutionResult:
        """Ejecuta el prompt en un proveedor especÃ­fico usando su API.

        Args:
            provider_name: Nombre del proveedor.
            config: ConfiguraciÃ³n del proveedor.
            model: Modelo a usar.
            prompt: Prompt de entrada.
            max_tokens: MÃ¡ximo de tokens de salida.

        Returns:
            ExecutionResult del proveedor.
        """
        api_key = os.environ.get(config.api_key_env, "")
        if not api_key:
            return ExecutionResult(
                success=False,
                output="",
                source="cloud",
                model=model,
                duration_ms=0,
                error=(
                    f"API key '{config.api_key_env}' no configurada para "
                    f"provider '{provider_name}'. "
                    "WHY: La variable de entorno debe estar definida. "
                    "WHERE: _execute_on_provider"
                ),
                provider=provider_name,
            )

        # Normalizar nombre a minÃºsculas para identificar tipo de API
        pname = provider_name.lower()

        try:
            if pname == "anthropic":
                result = self._execute_anthropic(config, api_key, model, prompt, max_tokens)
            elif pname == "google":
                result = self._execute_google(config, api_key, model, prompt, max_tokens)
            elif pname in ("openai", "mistral", "deepseek", "zenfree"):
                result = self._execute_openai_compat(config, api_key, model, prompt, max_tokens)
            else:
                # Intento genÃ©rico OpenAI-compatible
                logger.debug(
                    "Provider '%s' no tiene handler especÃ­fico, usando OpenAI-compat. "
                    "WHERE: _execute_on_provider",
                    provider_name,
                )
                result = self._execute_openai_compat(config, api_key, model, prompt, max_tokens)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Error no manejado en provider '%s' modelo '%s': %s. "
                "WHERE: _execute_on_provider",
                provider_name, model, exc,
            )
            return ExecutionResult(
                success=False,
                output="",
                source="cloud",
                model=model,
                duration_ms=0,
                error=f"Unhandled error in {provider_name}: {exc}",
                provider=provider_name,
            )

        # Trackear costos si fue exitoso
        if result.success and result.tokens_used > 0:
            cost = self._track_cost(provider_name, model, result.tokens_used)
            logger.debug(
                "Provider '%s' cost: $%.6f for %d tokens. WHERE: _execute_on_provider",
                provider_name, cost, result.tokens_used,
            )

        result.provider = provider_name
        return result

    def _execute_openai_compat(self, config, api_key, prompt, max_tokens, temperature):
        from harness.model_router.provider_executors import execute_openai_compat
        return execute_openai_compat(self, config, api_key, prompt, max_tokens, temperature)

    def _execute_anthropic(self, config, api_key, prompt, max_tokens, temperature):
        from harness.model_router.provider_executors import execute_anthropic
        return execute_anthropic(self, config, api_key, prompt, max_tokens, temperature)

    def _execute_google(self, config, api_key, prompt, max_tokens, temperature):
        from harness.model_router.provider_executors import execute_google
        return execute_google(self, config, api_key, prompt, max_tokens, temperature)

    def _start_health_checks(self) -> None:
        """Inicia health checks en background (delegado)."""
        from harness.model_router.provider_health import _start_health_checks as _hc
        _hc(self)

    def stop_health_checks(self) -> None:
        """Detiene health checks (delegado)."""
        from harness.model_router.provider_executors import stop_health_checks as _shc
        _shc(self)

    def _track_cost(self, provider, model, tokens):
        """Trackea costos (delegado)."""
        from harness.model_router.provider_executors import _track_cost as _tc
        return _tc(self, provider, model, tokens)

    def _calculate_cost(self, provider, tokens):
        """Calcula costo (delegado)."""
        from harness.model_router.provider_executors import _calculate_cost as _cc
        return _cc(self, provider, tokens)

    def _find_provider_for_model(self, model: str) -> str | None:
        """Busca proveedor optimo para un modelo (delegado)."""
        from harness.model_router.provider_executors import (
            _find_provider_for_model as _fp,
        )
        return _fp(self, model)

    def get_stats(self) -> dict[str, Any]:
        """Retorna estadisticas completas (delegado)."""
        from harness.model_router.provider_health import get_stats as _gs
        return _gs(self)
