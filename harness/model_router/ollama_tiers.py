"""
OllamaTierRouter — Delegación por capacidad a modelos locales (4 tiers + coding).

Enruta tareas a modelos Ollama locales según capacidad, minimizando tokens
cloud (TKN): solo se paga frontier/cloud cuando la tarea lo requiere
(FRONTIER_ONLY_TASKS de harness.orchestrator.slm_router).

Tiers (patrón del usuario, SSOT .opencode/config/ollama_models.yaml):
- 🟢 FAST      (fast):      borradores, tareas simples, extracción, formateo
- 🔵 QUALITY   (quality):   calidad de texto, resúmenes, redacción
- 🟣 EMBEDDING (embedding): RAG, búsqueda semántica (nomic-embed-text)
- 🟡 VISION    (vision):    leer imágenes, alt-text (llava)
- 🟠 CODING    (coding):    implementar, refactorizar, debuggear, tests

Diseño (integra con el repo sin romper):
- Heurística por keywords sin LLM, igual que ModelRouter (router.py).
- Clasificación por keywords en orden EMBEDDING -> VISION -> CODING -> QUALITY -> FAST.
- Degradación controlada a cloud: si client.is_available() es False, los
  métodos de red devuelven dicts con todo False (nunca lanzan excepción).
- __init__/load_from_yaml NO tocan la red (los tests usan mocks).
- Configurable vía YAML (.opencode/config/ollama_models.yaml) con defaults
  inline si el YAML no existe o un tier falta.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

try:
    from harness.model_router.ollama_client import DEFAULT_KEEP_ALIVE, OllamaClient
except ImportError as _import_err:
    # WHAT: no se pudo importar harness.model_router.ollama_client.
    # WHY: lo crea un agente paralelo; este módulo no puede depender del orden
    #      de aterrizaje y debe poder importarse sin red.
    # WHERE: import en ollama_tiers.py — fallback transitorio (stub sin red).
    logging.getLogger(__name__).warning(
        "WHAT: ollama_client no importable. WHY: %s. "
        "WHERE: import en ollama_tiers.py — usando fallback transitorio.",
        _import_err,
    )

    DEFAULT_KEEP_ALIVE = "5m"

    class OllamaClient:
        """Stub transitorio de OllamaClient (API mínima, sin red).

        Solo existe mientras el agente paralelo no aterrice
        harness/model_router/ollama_client.py; reporta Ollama como no
        disponible (degradación a cloud). Cualquier otro uso falla explícito.
        """

        def is_available(self) -> bool:
            """Ollama se considera no disponible sin el cliente real."""
            return False

        def __getattr__(self, name: str) -> Any:
            raise NotImplementedError(
                f"WHAT: stub de OllamaClient sin método '{name}'. "
                f"WHY: ollama_client.py aún no está disponible. "
                f"WHERE: __getattr__ del stub en ollama_tiers.py."
            )


logger = logging.getLogger(__name__)

__all__ = ["CapabilityTier", "OllamaTierRouter", "OllamaTierSpec"]


class CapabilityTier(str, Enum):
    """Nivel de capacidad del modelo local (patrón del usuario)."""

    FAST = "fast"  # 🟢 borradores, tareas simples, formateo
    QUALITY = "quality"  # 🔵 calidad de texto, resúmenes, redacción
    EMBEDDING = "embedding"  # 🟣 RAG, búsqueda semántica
    VISION = "vision"  # 🟡 leer imágenes, alt-text
    CODING = "coding"  # 🟠 implementar, refactorizar, debuggear, tests


@dataclass(frozen=True)
class OllamaTierSpec:
    """Especificación de un tier: modelo Ollama, keep_alive y auto_pull."""

    tier: CapabilityTier
    model: str  # nombre del modelo en Ollama (ej. "llama3.2:3b")
    keep_alive: str = DEFAULT_KEEP_ALIVE  # importa de ollama_client
    auto_pull: bool = True  # si falta, intentar `ollama pull`


# Keywords por tier (heurística sin LLM, case-insensitive). Orden de evaluación
# fijo: EMBEDDING -> VISION -> CODING -> QUALITY -> FAST (FAST es el default).
# CODING va antes que QUALITY: "write a pytest test" contiene "write"
# (quality) pero es codigo — gana la keyword especifica de codigo.
_EMBEDDING_KEYWORDS: frozenset[str] = frozenset({
    "rag", "search", "retriev", "embed", "busc", "index",
})
_VISION_KEYWORDS: frozenset[str] = frozenset({
    "image", "imagen", "alt-text", "ocr", "figure", "diagrama", "screenshot", "photo",
})
_QUALITY_KEYWORDS: frozenset[str] = frozenset({
    "draft", "redact", "write", "summary", "resum", "essay", "prose", "copy", "quality",
})
# NOTA: matching por substring (keyword in task.lower()). Las keywords de
# CODING evitan fragmentos ambiguos: sin "test"/"script"/"api" sueltos
# (colisionan con "latest", "description", "rapid"); se usan formas con
# espacio ("class "), compuestos ("pytest", "unittest") o verbos de código.
_CODING_KEYWORDS: frozenset[str] = frozenset({
    "codigo", "código", "implement", "refactor", "debug", "function",
    "funcion", "función", "class ", "clase", "method", "metodo", "método",
    "bug", "fix", "pytest", "unittest", "tdd", "endpoint", "sql", "query",
    "commit", "python",
})

_TIER_KEYWORDS: dict[CapabilityTier, frozenset[str]] = {
    CapabilityTier.EMBEDDING: _EMBEDDING_KEYWORDS,
    CapabilityTier.VISION: _VISION_KEYWORDS,
    CapabilityTier.CODING: _CODING_KEYWORDS,
    CapabilityTier.QUALITY: _QUALITY_KEYWORDS,
}

# Tareas FRONTIER_ONLY (frontera/slm_router, ADR-0070 gobernanza): si la tarea
# matchea, NO se delega a local (se va cloud). Alineado con FRONTIER_ONLY_TASKS
# de harness.orchestrator.slm_router (planning/synthesis/reasoning/architecture/
# security_audit/code_review). NOTA: "debugging" se EXCLUYE a proposito — ADR-0069
# manda debug→CODING local (modelo coder). Keywords ES/EN sin fragmentos ambiguos.
_FRONTIER_ONLY_KEYWORDS: frozenset[str] = frozenset({
    # design/architecture
    "diseñ", "disen", "architecture", "arquitectura", "hexagonal", "tradeoff",
    # planning
    "planning", "planea", "planificar", "roadmap", "estrategia de migracion",
    "plan the", "migration strategy", "migration plan",
    # synthesis/reasoning
    "sintesis", "synthesis", "razonamiento", "reasoning", "deduce",
    # security_audit / code_review
    "security audit", "auditoria de seguridad", "code review", "revisar codigo",
})


def is_frontier_only(task: str) -> bool:
    """Detecta si una tarea requiere modelo frontier (no delegar a local).

    Args:
        task: Descripcion de la tarea (case-insensitive).

    Returns:
        True si la tarea matchea FRONTIER_ONLY (diseño/arquitectura/planning/
        síntesis/razonamiento/security audit/code review). "debugging" NO
        matchea (ADR-0069: debug va a CODING local).
    """
    task_lower = task.lower()
    return any(kw in task_lower for kw in _FRONTIER_ONLY_KEYWORDS)

# Modelos por defecto por tier (2026, FRS 2026-08-14: qwen3/3-vl/3-embedding;
# configurables via YAML .opencode/config/ollama_models.yaml).
_DEFAULT_TIER_MODELS: dict[CapabilityTier, str] = {
    CapabilityTier.FAST: "qwen3:4b",
    CapabilityTier.QUALITY: "deepseek-r1:8b",
    CapabilityTier.EMBEDDING: "qwen3-embedding:0.6b",
    CapabilityTier.VISION: "qwen3-vl:4b",
    CapabilityTier.CODING: "qwen2.5-coder:7b",
}


def _default_specs() -> dict[CapabilityTier, OllamaTierSpec]:
    """Construye las specs por defecto (modelos del usuario).

    Returns:
        Dict con un OllamaTierSpec por CapabilityTier: modelo de
        _DEFAULT_TIER_MODELS, keep_alive=DEFAULT_KEEP_ALIVE, auto_pull=True.
    """
    return {
        tier: OllamaTierSpec(tier=tier, model=model)
        for tier, model in _DEFAULT_TIER_MODELS.items()
    }


def _as_bool(value: object, default: bool) -> bool:
    """Coacciona un valor YAML a bool, con fallback al default si no es bool.

    Args:
        value: Valor leído del YAML (bool nativo, str "true"/"false", etc.).
        default: Valor a usar si `value` no es un bool nativo de YAML.

    Returns:
        `value` si es bool; si no, `default`.
    """
    return value if isinstance(value, bool) else default


def _ollama_config(raw: object) -> dict:
    """Extrae la config 'ollama' de la raíz del YAML validando tipos.

    Soporta dos formatos (retorna config normalizada con claves opcionales
    base_url/timeout/tiers):
    1. Anidado (config del repo): {'ollama': {base_url, timeout, tiers}}.
    2. Plano (test-writer): claves de tier en la raíz, ej. {fast: {...}}.

    Args:
        raw: Raíz del documento YAML (resultado de yaml.safe_load).

    Returns:
        Dict de config normalizado; {} si no hay bloque 'ollama' ni tiers.

    Raises:
        TypeError: si la raíz no es dict o 'ollama' no es dict.
    """
    if not isinstance(raw, dict):
        raise TypeError(
            "WHAT: raíz del YAML no es dict. "
            "WHY: se esperaba {'ollama': {...}} o claves de tier planas. "
            "WHERE: _ollama_config en ollama_tiers.py."
        )
    if "ollama" in raw:
        ollama_cfg = raw["ollama"]
        if not isinstance(ollama_cfg, dict):
            raise TypeError(
                "WHAT: bloque 'ollama' no es dict. "
                "WHY: se esperaba 'ollama: {base_url, timeout, tiers}'. "
                "WHERE: _ollama_config en ollama_tiers.py."
            )
        return ollama_cfg
    if any(tier.value in raw for tier in CapabilityTier):
        return {"tiers": raw}
    return {}


def _client_from_yaml(ollama_cfg: dict) -> OllamaClient:
    """Crea OllamaClient con base_url/timeout del YAML (defaults si ausentes).

    Args:
        ollama_cfg: Bloque 'ollama' del YAML.

    Returns:
        OllamaClient configurado; el default si el YAML no trae overrides.
    """
    kwargs: dict[str, Any] = {}
    base_url = ollama_cfg.get("base_url")
    if isinstance(base_url, str) and base_url:
        kwargs["base_url"] = base_url
    timeout = ollama_cfg.get("timeout")
    if isinstance(timeout, (int, float)) and not isinstance(timeout, bool) and timeout > 0:
        kwargs["timeout"] = timeout
    if kwargs:
        return OllamaClient(**kwargs)
    return OllamaClient()


def _specs_from_yaml(ollama_cfg: dict) -> dict[CapabilityTier, OllamaTierSpec]:
    """Construye specs por tier desde el bloque 'tiers' del YAML.

    Los tiers ausentes o mal formados conservan el default.

    Args:
        ollama_cfg: Bloque 'ollama' del YAML.

    Returns:
        Dict tier -> OllamaTierSpec (defaults + overrides del YAML).
    """
    specs = _default_specs()
    tiers_cfg = ollama_cfg.get("tiers")
    if not isinstance(tiers_cfg, dict):
        return specs
    for tier in CapabilityTier:
        entry = tiers_cfg.get(tier.value)
        if not isinstance(entry, dict):
            continue
        current = specs[tier]
        specs[tier] = OllamaTierSpec(
            tier=tier,
            model=str(entry.get("model", current.model)),
            keep_alive=str(entry.get("keep_alive", current.keep_alive)),
            auto_pull=_as_bool(entry.get("auto_pull", current.auto_pull), current.auto_pull),
        )
    return specs


class OllamaTierRouter:
    """Enrutador de delegación por capacidad a modelos Ollama locales.

    Sin red en __init__ (los tests lo instancian con mock): la red solo se
    toca en métodos explícitos (ensure_models/warm_all/unload_all/
    loaded_tiers). Si Ollama no está disponible, esos métodos devuelven
    dicts con todo False para degradar a cloud sin excepción.

    Uso:
        router = OllamaTierRouter(client=OllamaClient())
        tier = router.tier_for_task("redactar resumen de calidad")  # QUALITY
        model = router.model_for(tier)  # "qwen2.5:14b"
    """

    def __init__(
        self,
        client: OllamaClient,
        specs: dict[CapabilityTier, OllamaTierSpec] | None = None,
    ) -> None:
        """Inicializa el router sin tocar la red.

        Args:
            client: Instancia de OllamaClient (o mock) para operar Ollama.
            specs: Mapeo tier -> spec. None usa los defaults del usuario.

        Raises:
            TypeError: si client no expone la API mínima (is_available).
        """
        if not hasattr(client, "is_available"):
            raise TypeError(
                "WHAT: client sin API mínima. "
                "WHY: se requiere is_available() para degradar a cloud. "
                "WHERE: __init__ de OllamaTierRouter."
            )
        self._client = client
        self._specs = specs if specs is not None else _default_specs()

    @staticmethod
    def load_from_yaml(path: Path | str) -> OllamaTierRouter:
        """Carga tiers y cliente desde un YAML (ver .opencode/config/ollama_models.yaml).

        Args:
            path: Ruta al YAML con formato 'ollama: {base_url, timeout, tiers}'.

        Returns:
            OllamaTierRouter con cliente (base_url/timeout) y specs del YAML;
            defaults si el YAML no existe, falta el bloque o falta un tier.

        Raises:
            TypeError: si la raíz del YAML no es dict o 'ollama' no es dict.
        """
        yaml_path = Path(path)
        if not yaml_path.is_file():
            logger.info("YAML no encontrado (%s); usando defaults.", yaml_path)
            return OllamaTierRouter(client=OllamaClient())
        try:
            with yaml_path.open(encoding="utf-8") as fh:
                raw = yaml.safe_load(fh)
        except (OSError, yaml.YAMLError) as exc:
            logger.error(
                "WHAT: YAML ilegible (%s). WHY: %s. WHERE: load_from_yaml.",
                yaml_path,
                exc,
            )
            return OllamaTierRouter(client=OllamaClient())
        ollama_cfg = _ollama_config(raw)
        client = _client_from_yaml(ollama_cfg)
        specs = _specs_from_yaml(ollama_cfg)
        return OllamaTierRouter(client=client, specs=specs)

    def model_for(self, tier: CapabilityTier) -> str:
        """Devuelve el nombre del modelo Ollama para un tier.

        Args:
            tier: Tier de capacidad.

        Returns:
            Nombre del modelo (ej. "llama3.2:3b").

        Raises:
            KeyError: si el tier no está configurado en este router.
        """
        spec = self._specs.get(tier)
        if spec is None:
            raise KeyError(
                f"WHAT: tier '{tier.value}' no configurado. "
                f"WHY: specs solo incluyen {sorted(t.value for t in self._specs)}. "
                f"WHERE: model_for() en ollama_tiers.py."
            )
        return spec.model

    def tier_for_task(self, task: str) -> CapabilityTier | None:
        """Clasifica una tarea por capacidad usando keywords (sin LLM).

        Evalúa en orden EMBEDDING -> VISION -> CODING -> QUALITY -> FAST;
        el default es FAST (borradores, extracción, clasificación, formateo).

        Args:
            task: Descripción de la tarea (case-insensitive).

        Returns:
            CapabilityTier del tier local delegado, o None si la tarea es
            FRONTIER_ONLY (diseño/arquitectura/planning/síntesis/razonamiento/
            security audit/code review) y debe ir a cloud.
        """
        if is_frontier_only(task):
            return None
        lowered = task.lower()
        for tier, keywords in _TIER_KEYWORDS.items():
            if any(keyword in lowered for keyword in keywords):
                return tier
        return CapabilityTier.FAST

    def task_uses_local(self, task: str) -> bool:
        """Indica si la tarea se puede delegar a un modelo local.

        False si la tarea matchea FRONTIER_ONLY (diseño/arquitectura/planning/
        síntesis/razonamiento/security audit/code review); True en cualquier
        otro caso (incluido debugging: ADR-0069 manda debug -> CODING local).

        Args:
            task: Descripción de la tarea.

        Returns:
            True si el tier local es suficiente; False si requiere frontier.
        """
        return not is_frontier_only(task)

    def ensure_models(self) -> dict[CapabilityTier, bool]:
        """Garantiza que los modelos de cada tier estén disponibles en Ollama.

        Si Ollama no está disponible devuelve todo False (degradación a cloud,
        sin excepción). Para cada tier: si el modelo falta y auto_pull=True,
        intenta client.pull(); falla -> False con error logueado WHAT+WHY+WHERE.

        Returns:
            Dict tier -> True si el modelo está (o quedó) disponible.
        """
        if not self._client.is_available():
            logger.warning("Ollama no disponible; tiers degradados a cloud.")
            return {tier: False for tier in self._specs}
        known = set(self._client.list_models() or [])
        result: dict[CapabilityTier, bool] = {}
        for tier, spec in self._specs.items():
            if spec.model in known:
                result[tier] = True
                continue
            result[tier] = self._pull_if_needed(spec)
        return result

    def warm_all(self) -> dict[CapabilityTier, bool]:
        """Precarga los modelos de todos los tiers en RAM (client.warm).

        Returns:
            Dict tier -> True si el warm terminó sin excepción (o todo False
            si Ollama no está disponible).
        """
        if not self._client.is_available():
            return {tier: False for tier in self._specs}
        result: dict[CapabilityTier, bool] = {}
        for tier, spec in self._specs.items():
            try:
                self._client.warm(spec.model, spec.keep_alive)
                result[tier] = True
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "WHAT: warm falló para %s. WHY: %s. WHERE: warm_all.",
                    spec.model,
                    exc,
                )
                result[tier] = False
        return result

    def unload_all(self) -> dict[CapabilityTier, bool]:
        """Descarga los modelos de todos los tiers de la RAM (client.unload).

        Returns:
            Dict tier -> True si el unload terminó sin excepción (o todo False
            si Ollama no está disponible).
        """
        if not self._client.is_available():
            return {tier: False for tier in self._specs}
        result: dict[CapabilityTier, bool] = {}
        for tier, spec in self._specs.items():
            try:
                self._client.unload(spec.model)
                result[tier] = True
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "WHAT: unload falló para %s. WHY: %s. WHERE: unload_all.",
                    spec.model,
                    exc,
                )
                result[tier] = False
        return result

    def loaded_tiers(self) -> dict[CapabilityTier, bool]:
        """Indica qué tiers tienen su modelo cargado en RAM.

        Returns:
            Dict tier -> True si el modelo está en client.loaded_models()
            (o todo False si Ollama no está disponible).
        """
        if not self._client.is_available():
            return {tier: False for tier in self._specs}
        loaded = set(self._client.loaded_models() or [])
        return {tier: spec.model in loaded for tier, spec in self._specs.items()}

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

    def _pull_if_needed(self, spec: OllamaTierSpec) -> bool:
        """Descarga el modelo si auto_pull está activo (True si quedó listo).

        Args:
            spec: Spec del tier cuyo modelo puede faltar.

        Returns:
            True si el modelo quedó disponible; False si no hay auto_pull o
            el pull falló (error logueado WHAT+WHY+WHERE, nunca silencioso).
        """
        if not spec.auto_pull:
            logger.info("Modelo %s no disponible y auto_pull=False.", spec.model)
            return False
        try:
            self._client.pull(spec.model)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "WHAT: fallo pull de %s. WHY: %s. WHERE: _pull_if_needed.",
                spec.model,
                exc,
            )
            return False
