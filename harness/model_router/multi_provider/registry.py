"""Registro de proveedores (mixin ``_RegistryMixin``).

Extraccion mecanica de los metodos de registro/eliminacion/listado de
``MultiAPIProvider`` del modulo original (sin cambios de logica ni firmas).

Classes:
    _RegistryMixin: Mixin con register_provider, unregister_provider y
        get_providers usados por ``MultiAPIProvider``.
"""

from __future__ import annotations

import logging

from harness.model_router.multi_provider_types import (
    ProviderConfig,
    ProviderHealth,
    ProviderTier,
)

logger = logging.getLogger("harness.model_router.multi_provider")


class _RegistryMixin:
    """Mixin con el registro dinamico de proveedores."""

    def register_provider(self, config: ProviderConfig) -> None:
        """Registra un nuevo proveedor de modelos LLM.

        Args:
            config: ConfiguraciÃ³n completa del proveedor.

        Raises:
            ValueError: Si el nombre del proveedor ya estÃ¡ registrado
                o la configuraciÃ³n es invÃ¡lida.

        WHY: Cada proveedor necesita configuraciÃ³n individual (API key,
        modelos, costos) para ser invocado correctamente.
        WHERE: register_provider en MultiAPIProvider.
        """
        if not config.name:
            raise ValueError(
                "Provider name cannot be empty. "
                "WHY: Se necesita un nombre Ãºnico para identificar el proveedor. "
                "WHERE: register_provider"
            )
        if not config.models:
            raise ValueError(
                f"Provider '{config.name}' must have at least one model. "
                "WHY: Sin modelos no hay ejecuciÃ³n posible. "
                "WHERE: register_provider"
            )
        if config.tier not in (t.value for t in ProviderTier):
            logger.warning(
                "Provider '%s' tier '%s' no es estÃ¡ndar, usando 'standard'. "
                "WHY: Se esperaba uno de %s. "
                "WHERE: register_provider",
                config.name, config.tier, [t.value for t in ProviderTier],
            )
            config.tier = ProviderTier.STANDARD.value

        with self._lock:
            if config.name in self._providers:
                raise ValueError(
                    f"Provider '{config.name}' already registered. "
                    "WHY: No se permite duplicados. "
                    "WHERE: register_provider"
                )

            self._providers[config.name] = {"config": config}
            self._tier_providers[config.tier].append(config.name)
            self._health[config.name] = ProviderHealth()

            logger.info(
                "Provider '%s' registrado con %d modelos en tier '%s'. "
                "WHERE: register_provider",
                config.name, len(config.models), config.tier,
            )

    def unregister_provider(self, name: str) -> None:
        """Elimina un proveedor registrado.

        Args:
            name: Nombre del proveedor a eliminar.

        WHY: Permite remover proveedores en runtime sin reiniciar la instancia.
        WHERE: unregister_provider en MultiAPIProvider.
        """
        with self._lock:
            if name not in self._providers:
                logger.warning(
                    "Provider '%s' no encontrado para eliminar. "
                    "WHY: El proveedor no estaba registrado. "
                    "WHERE: unregister_provider",
                    name,
                )
                return

            config = self._providers[name]["config"]
            tier = config.tier
            if name in self._tier_providers.get(tier, []):
                self._tier_providers[tier].remove(name)

            del self._providers[name]
            self._health.pop(name, None)
            self._latency_history.pop(name, None)
            self._costs.pop(name, None)
            self._request_counts.pop(name, None)
            self._error_counts.pop(name, None)

            logger.info(
                "Provider '%s' eliminado. WHERE: unregister_provider", name,
            )

    def get_providers(self) -> list[str]:
        """Retorna la lista de nombres de proveedores registrados.

        Returns:
            Lista de nombres de proveedores activos.
        """
        with self._lock:
            return list(self._providers.keys())
