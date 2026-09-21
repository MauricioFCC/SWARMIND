"""capability_profiles.py — Routing por capacidades con calibracion (ADR-0086).

WHAT: Perfiles de capacidad por modelo (coding/reasoning/math/multilingual/
agentic 0..1 desde benchmarks + trust calibrable) + clasificador de tarea
por keywords + `route_by_capability` (score = dot(caps, weights) * trust;
conf >= 0.65 -> local, si no cloud).
WHY: Mesa (2-1, hibrido): prior barato (benchmarks) + calibracion online
(EWMA trust via veredictos del supervisor) + fallback congelado si el
supervisor cae. Atacante: staleness + deriva -> trust con auditoria.
WHERE: Delante de `LocalExecutor`/tiers; `ollama_local.yaml` (gitignored)
sobreescribe caps/trust sin tocar el repo.

Uso:
    profiles = load_profiles(Path(".opencode/config/ollama_local.yaml"))
    out = route_by_capability("implementar test", profiles)
    calibrated = chosen.calibrate(success=True)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("harness.model_router.capability_profiles")

#: Umbral de confianza para ruta local (mesa: 0.65).
LOCAL_CONFIDENCE = 0.65
#: Dimensiones de capacidad (LXT 2026: reasoning/coding/math/language/agentic + vision).
CAP_DIMS: tuple[str, ...] = ("coding", "reasoning", "math", "multilingual", "agentic", "vision")

#: Keywords por dimension (ES/EN, clasificador <5ms sin LLM).
_DIM_KEYWORDS: dict[str, frozenset[str]] = {
    "coding": frozenset({
        "implementar", "implement", "pytest", "refactor", "debug", "codigo",
        "code", "funcion", "function", "endpoint", "test", "testing",
        "casos", "bug", "fix", "class ", "sql", "query", "genera",
    }),
    "reasoning": frozenset({
        "disenar", "design", "arquitectura", "architecture", "tradeoff",
        "estrategia", "planificar", "planning", "razonamiento", "reasoning",
        "sintesis", "synthesis", "auditoria", "audit",
    }),
    "math": frozenset({
        "calcula", "calculate", "estadistica", "statistics", "probabilidad",
        "optimiza", "optimize", "formula", "math", "metric", "cuenta",
        "percentil",
    }),
    "multilingual": frozenset({
        "traduce", "translate", "resume", "resumen", "redacta", "escribe",
        "documento", "formatea", "format", "extrae", "extract", "convierte",
        "convert", "lista", "explica",
    }),
    "agentic": frozenset({
        "investiga", "research", "busca", "search", "compara", "analiza",
    }),
    "vision": frozenset({
        "imagen", "image", "describe", "foto", "screenshot", "diagrama visual",
    }),
}

#: Perfiles builtin de los instalados (priors por benchmark; calibrables).
#: Fuentes: Qwen2.5/3 reports (MMLU/HumanEval; GSM8K deprecado por saturacion/
#: contaminacion — usar MATH-500/AIME como gate), MiniCPM-SALA 0.951
#: HumanEval (llm-stats), LXT (solo 4/15 predicen prod).
_BUILTIN: tuple[tuple[str, float, str, dict[str, float]], ...] = (
    ("hf.co/Jackrong/Qwopus3.5-9B-Coder-GGUF:Qwopus3.5-9B-coder-Exp-Q4_K_M",
     9.0, "Q4", {"coding": 0.90, "reasoning": 0.70, "math": 0.65,
                 "multilingual": 0.70, "agentic": 0.65}),
    ("hf.co/empero-ai/Qwen3.8-9B-Distill-GGUF:Q4_K_M",
     9.0, "Q4", {"coding": 0.75, "reasoning": 0.85, "math": 0.85,
                 "multilingual": 0.80, "agentic": 0.75}),
    ("hf.co/Jackrong/Qwen3.5-9B-DeepSeek-V4-Flash-GGUF:Q4_K_M",
     9.0, "Q4", {"coding": 0.80, "reasoning": 0.85, "math": 0.80,
                 "multilingual": 0.80, "agentic": 0.80}),
    ("hf.co/unsloth/GLM-Z1-9B-0414-GGUF:UD-Q4_K_XL",
     9.0, "Q4", {"coding": 0.70, "reasoning": 0.90, "math": 0.85,
                 "multilingual": 0.75, "agentic": 0.75}),
    ("qwen2.5-coder:7b", 7.0, "Q4",
     {"coding": 0.80, "reasoning": 0.65, "multilingual": 0.65, "agentic": 0.60}),
    ("deepseek-r1:8b", 8.0, "Q4",
     {"coding": 0.70, "reasoning": 0.85, "math": 0.80,
      "multilingual": 0.75, "agentic": 0.70}),
    ("qwen3:4b", 4.0, "Q4",
     {"coding": 0.60, "reasoning": 0.65, "multilingual": 0.65, "agentic": 0.60}),
    ("hf.co/LiquidAI/LFM2.5-2.6B-GGUF:Q8_0", 2.6, "Q8",
     {"coding": 0.55, "reasoning": 0.55, "multilingual": 0.60, "agentic": 0.50}),
    ("hf.co/openbmb/MiniCPM5-2B-GGUF:Q8_0", 2.0, "Q8",
     {"coding": 0.60, "reasoning": 0.60, "multilingual": 0.65, "agentic": 0.55}),
    ("llama3.2:3b", 3.0, "Q4",
     {"coding": 0.50, "reasoning": 0.50, "multilingual": 0.55, "agentic": 0.50}),
    ("hf.co/mradermacher/OLMoE-1B-7B-0125-Instruct-Distill-ot114k-batch32-i1-GGUF:IQ4_NL",
     7.0, "Q4", {"coding": 0.50, "reasoning": 0.55, "multilingual": 0.55, "agentic": 0.50}),
    ("qwen3-vl:4b", 4.0, "Q4",
     {"coding": 0.50, "reasoning": 0.60, "multilingual": 0.60,
      "agentic": 0.55, "vision": 0.90}),
    ("qwen2.5-coder:7b-instruct", 7.0, "Q4",
     {"coding": 0.80, "reasoning": 0.65, "multilingual": 0.65, "agentic": 0.60}),
)


@dataclass(frozen=True)
class CapabilityProfile:
    """Perfil de capacidad de un modelo (inmutable; calibrate retorna copia).

    Attributes:
        model_id: Tag Ollama.
        params_b: Parametros en miles de millones.
        quant: Cuantizacion (Q4/Q8).
        caps: Mapa dimension -> score 0..1.
        trust: Confianza calibrada 0..1 (1.0 = prior sin evidencia).
    """

    model_id: str
    params_b: float
    quant: str
    caps: dict[str, float] = field(default_factory=dict)
    trust: float = 1.0

    def score(self, weights: dict[str, float]) -> float:
        """Score ponderado por la tarea (dot(caps, weights) * trust).

        Args:
            weights: Peso por dimension (del clasificador).

        Returns:
            Score >= 0 (comparable entre modelos).
        """
        total = sum(self.caps.get(dim, 0.0) * w for dim, w in weights.items())
        return total * self.trust

    def calibrate(self, success: bool) -> CapabilityProfile:
        """Ajusta trust con EWMA 0.9/0.1 (veredicto del supervisor).

        Args:
            success: True si el veredicto fue positivo.

        Returns:
            Copia con trust actualizado.
        """
        updated = 0.9 * self.trust + 0.1 * (1.0 if success else 0.0)
        return CapabilityProfile(
            model_id=self.model_id, params_b=self.params_b,
            quant=self.quant, caps=dict(self.caps), trust=updated,
        )


@dataclass(frozen=True)
class RoutingDecision:
    """Decision de ruteo por capacidades.

    Attributes:
        model_id: Modelo elegido o "cloud".
        confidence: Score normalizado 0..1 (max score / suma scores).
        local: True si va a local (conf >= LOCAL_CONFIDENCE).
    """

    model_id: str
    confidence: float
    local: bool


def classify_task(task: str) -> dict[str, float]:
    """Clasifica la tarea en pesos por dimension (keywords, <5ms, sin LLM).

    Args:
        task: Descripcion (case-insensitive).

    Returns:
        Mapa dimension -> peso (0.0 si no matchea; vector denso).
    """
    lowered = task.lower()
    weights: dict[str, float] = {dim: 0.0 for dim in CAP_DIMS}
    for dim, keywords in _DIM_KEYWORDS.items():
        weights[dim] = float(sum(1 for kw in keywords if kw in lowered))
    return weights


def route_by_capability(
    task: str,
    profiles: tuple[CapabilityProfile, ...],
    threshold: float = LOCAL_CONFIDENCE,
) -> RoutingDecision:
    """Rutea por capacidades: mejor score, local si conf >= umbral.

    Args:
        task: Descripcion de la tarea.
        profiles: Perfiles candidatos.
        threshold: Umbral de confianza local.

    Returns:
        RoutingDecision (model_id o "cloud").
    """
    weights = classify_task(task)
    if not any(weights.values()) or not profiles:
        return RoutingDecision(model_id="cloud", confidence=0.0, local=False)
    scored = [(p.score(weights), p) for p in profiles]
    perfect = sum(weights.values())  # score con caps 1.0 y trust 1.0
    best_score, best = max(scored, key=lambda pair: (pair[0], pair[1].model_id))
    confidence = (best_score / perfect) if perfect > 0 else 0.0
    if confidence >= threshold:
        return RoutingDecision(model_id=best.model_id, confidence=confidence, local=True)
    return RoutingDecision(model_id="cloud", confidence=confidence, local=False)


def load_profiles(yaml_path: str | Path | None) -> tuple[CapabilityProfile, ...]:
    """Carga perfiles: builtin siempre + overrides del YAML local si existe.

    El YAML local (`ollama_local.yaml`, gitignored) puede ajustar caps y
    trust por model_id sin tocar el repo. Sin archivo: solo builtin.

    Args:
        yaml_path: Ruta del YAML local (None = solo builtin).

    Returns:
        Tupla de perfiles (builtin + overrides aplicados).
    """
    profiles = [
        CapabilityProfile(model_id=m, params_b=p, quant=q, caps=dict(c))
        for m, p, q, c in _BUILTIN
    ]
    if yaml_path is None:
        return tuple(profiles)
    path = Path(yaml_path)
    if not path.is_file():
        logger.debug("capability_profiles: sin YAML local (%s), solo builtin", path)
        return tuple(profiles)
    try:
        import yaml  # type: ignore[import-not-found]

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001 - YAML opcional, fallback a builtin
        logger.warning("capability_profiles: YAML ilegible (%s), solo builtin", exc)
        return tuple(profiles)
    overrides = data.get("models", {}) if isinstance(data, dict) else {}
    by_id = {p.model_id: p for p in profiles}
    for model_id, patch in overrides.items():
        if not isinstance(patch, dict) or model_id not in by_id:
            continue
        base = by_id[model_id]
        merged_caps = dict(base.caps)
        caps_patch = patch.get("caps", {})
        if isinstance(caps_patch, dict):
            merged_caps.update({k: float(v) for k, v in caps_patch.items()})
        trust = float(patch.get("trust", base.trust))
        by_id[model_id] = CapabilityProfile(
            model_id=base.model_id, params_b=base.params_b,
            quant=base.quant, caps=merged_caps, trust=trust,
        )
    logger.info("capability_profiles: %d overrides desde %s", len(overrides), path)
    return tuple(by_id.values())
