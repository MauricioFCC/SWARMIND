"""Provider executors - OpenAI, Anthropic, Google implementations.

Health checks, cost tracking, budget control y metricas extraidos a provider_health.py.
"""
from __future__ import annotations

import logging
from collections import defaultdict

from harness.model_router.multi_provider_types import (
    ExecutionResult,
    ProviderConfig,
    ProviderTier,
)
from harness.model_router.provider_health import (
    stop_health_checks,
)

logger = logging.getLogger(__name__)


def execute_openai_compat(
    self,
    config: ProviderConfig,
    api_key: str,
    model: str,
    prompt: str,
    max_tokens: int,
) -> ExecutionResult:
    """Ejecuta contra APIs OpenAI-compatibles (OpenAI, Mistral, DeepSeek, etc.).

    Args:
        config: Configuracion del proveedor.
        api_key: API key.
        model: Modelo.
        prompt: Prompt.
        max_tokens: Limite de tokens.

    Returns:
        ExecutionResult con la respuesta.
    """
    import requests

    base_url = config.base_url.rstrip("/")
    timeout_s = config.timeout_ms / 1000.0

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": max_tokens,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    headers.update(config.headers_extra)

    try:
        resp = requests.post(
            f"{base_url}/chat/completions",
            json=payload,
            headers=headers,
            timeout=timeout_s,
        )
        resp.raise_for_status()
        data = resp.json()

        content = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        usage = data.get("usage", {})
        total_tokens = usage.get("total_tokens", 0)

        return ExecutionResult(
            success=True,
            output=content,
            source="cloud",
            model=model,
            duration_ms=0.0,
            tokens_used=total_tokens,
        )

    except requests.exceptions.Timeout as exc:
        return ExecutionResult(
            success=False,
            output="",
            source="cloud",
            model=model,
            duration_ms=0.0,
            error=(
                f"Timeout ({timeout_s}s) en provider '{config.name}': {exc}. "
                "WHY: El servidor no respondio dentro del limite. "
                "WHERE: _execute_openai_compat"
            ),
        )
    except requests.exceptions.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else 0
        error_detail = ""
        if exc.response is not None:
            try:
                error_detail = exc.response.json().get("error", {}).get("message", "")
            except Exception:  # noqa: BLE001
                error_detail = exc.response.text[:200]

        return ExecutionResult(
            success=False,
            output="",
            source="cloud",
            model=model,
            duration_ms=0.0,
            error=(
                f"HTTP {status_code} en '{config.name}': {error_detail}. "
                "WHY: La API rechazo la solicitud. "
                "WHERE: _execute_openai_compat"
            ),
        )
    except Exception as exc:  # noqa: BLE001
        return ExecutionResult(
            success=False,
            output="",
            source="cloud",
            model=model,
            duration_ms=0.0,
            error=(
                f"Error en provider '{config.name}': {exc}. "
                f"WHY: Fallo no categorizado en la comunicacion HTTP. "
                f"WHERE: _execute_openai_compat"
            ),
        )


def execute_anthropic(
    self,
    config: ProviderConfig,
    api_key: str,
    model: str,
    prompt: str,
    max_tokens: int,
) -> ExecutionResult:
    """Ejecuta contra la API de Anthropic (Claude).

    Args:
        config: Configuracion del proveedor.
        api_key: API key de Anthropic.
        model: Modelo (ej: "claude-3-5-sonnet-20241022").
        prompt: Prompt de entrada.
        max_tokens: Maximo de tokens de salida.

    Returns:
        ExecutionResult con la respuesta.
    """
    import requests

    base_url = config.base_url.rstrip("/")
    timeout_s = config.timeout_ms / 1000.0

    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
    }
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    headers.update(config.headers_extra)

    try:
        resp = requests.post(
            f"{base_url}/messages",
            json=payload,
            headers=headers,
            timeout=timeout_s,
        )
        resp.raise_for_status()
        data = resp.json()

        content = ""
        content_blocks = data.get("content", [])
        if content_blocks:
            for block in content_blocks:
                if block.get("type") == "text":
                    content += block.get("text", "")

        usage = data.get("usage", {})
        total_tokens = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)

        return ExecutionResult(
            success=True,
            output=content,
            source="cloud",
            model=model,
            duration_ms=0.0,
            tokens_used=total_tokens,
        )

    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else 0
        detail = ""
        if exc.response is not None:
            try:
                err = exc.response.json()
                detail = err.get("error", {}).get("message", str(err))
            except Exception:  # noqa: BLE001
                detail = exc.response.text[:200]
        return ExecutionResult(
            success=False,
            output="",
            source="cloud",
            model=model,
            duration_ms=0.0,
            error=(
                f"Anthropic HTTP {status}: {detail}. "
                "WHY: La API de Anthropic rechazo la solicitud. "
                "WHERE: _execute_anthropic"
            ),
        )
    except Exception as exc:  # noqa: BLE001
        return ExecutionResult(
            success=False,
            output="",
            source="cloud",
            model=model,
            duration_ms=0.0,
            error=(
                f"Anthropic error: {exc}. "
                "WHY: Fallo en la comunicacion con Anthropic. "
                "WHERE: _execute_anthropic"
            ),
        )


def execute_google(
    self,
    config: ProviderConfig,
    api_key: str,
    model: str,
    prompt: str,
    max_tokens: int,
) -> ExecutionResult:
    """Ejecuta contra la API de Google Gemini.

    Args:
        config: Configuracion del proveedor.
        api_key: API key de Google.
        model: Modelo (ej: "gemini-1.5-pro").
        prompt: Prompt de entrada.
        max_tokens: Maximo de tokens de salida.

    Returns:
        ExecutionResult con la respuesta.
    """
    import requests

    base_url = config.base_url.rstrip("/")
    timeout_s = config.timeout_ms / 1000.0

    url = f"{base_url}/v1/models/{model}:generateContent"

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": max_tokens,
        },
    }
    headers = {
        "x-goog-api-key": api_key,
        "Content-Type": "application/json",
    }
    headers.update(config.headers_extra)

    try:
        resp = requests.post(
            url, json=payload, headers=headers, timeout=timeout_s,
        )
        resp.raise_for_status()
        data = resp.json()

        content = ""
        candidates = data.get("candidates", [])
        if candidates:
            content_parts = candidates[0].get("content", {}).get("parts", [])
            for part in content_parts:
                content += part.get("text", "")

        usage = data.get("usageMetadata", {})
        total_tokens = usage.get("totalTokenCount", 0)

        return ExecutionResult(
            success=True,
            output=content,
            source="cloud",
            model=model,
            duration_ms=0.0,
            tokens_used=total_tokens,
        )

    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else 0
        detail = ""
        if exc.response is not None:
            try:
                err = exc.response.json()
                detail = err.get("error", {}).get("message", str(err))
            except Exception:  # noqa: BLE001
                detail = exc.response.text[:200]
        return ExecutionResult(
            success=False,
            output="",
            source="cloud",
            model=model,
            duration_ms=0.0,
            error=(
                f"Google Gemini HTTP {status}: {detail}. "
                "WHY: La API de Gemini rechazo la solicitud. "
                "WHERE: _execute_google"
            ),
        )
    except Exception as exc:  # noqa: BLE001
        return ExecutionResult(
            success=False,
            output="",
            source="cloud",
            model=model,
            duration_ms=0.0,
            error=(
                f"Google Gemini error: {exc}. "
                "WHY: Fallo en la comunicacion con Gemini. "
                "WHERE: _execute_google"
            ),
        )


# ------------------------------------------------------------------
# Round-robin y seleccion de proveedor
# ------------------------------------------------------------------


def _find_provider_for_model(self, model: str) -> str | None:
    """Busca el proveedor optimo para un modelo.

    Prioriza por tier (premium > standard > budget) y hace round-robin
    entre proveedores del mismo tier.

    Args:
        model: Nombre del modelo a buscar.

    Returns:
        Nombre del proveedor seleccionado, o None si no se encuentra.
    """
    with self._lock:
        candidates_by_tier: dict[str, list[str]] = defaultdict(list)
        for pname, entry in self._providers.items():
            cfg = entry["config"]
            health = self._health.get(pname)
            if health is not None and not health.available:
                continue
            if model in cfg.models:
                candidates_by_tier[cfg.tier].append(pname)

        tier_order = [
            ProviderTier.PREMIUM.value,
            ProviderTier.STANDARD.value,
            ProviderTier.BUDGET.value,
        ]

        for tier in tier_order:
            candidates = candidates_by_tier.get(tier, [])
            if not candidates:
                continue

            idx = self._rr_indices[tier] % len(candidates)
            self._rr_indices[tier] = idx + 1
            return candidates[idx]

    return None


def _get_other_providers_for_model(
    self, model: str, exclude: str,
) -> list[str]:
    """Retorna otros proveedores que ofrecen el modelo, ordenados por tier.

    Args:
        model: Modelo a buscar.
        exclude: Proveedor a excluir (el primario).

    Returns:
        Lista ordenada de proveedores alternativos.
    """
    candidates: list[tuple[str, int]] = []
    tier_rank = {
        ProviderTier.PREMIUM.value: 0,
        ProviderTier.STANDARD.value: 1,
        ProviderTier.BUDGET.value: 2,
    }

    with self._lock:
        for pname, entry in self._providers.items():
            if pname == exclude:
                continue
            cfg = entry["config"]
            health = self._health.get(pname)
            if health is not None and not health.available:
                continue
            if model in cfg.models:
                rank = tier_rank.get(cfg.tier, 99)
                candidates.append((pname, rank))

    candidates.sort(key=lambda x: x[1])
    return [c[0] for c in candidates]


# ------------------------------------------------------------------
# Limpieza en destruccion de instancia
# ------------------------------------------------------------------


def __del__(self) -> None:
    """Cleanup: detiene health checks al destruir la instancia."""
    stop_health_checks(self)
