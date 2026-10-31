"""
Difficulty Router — clasifica la complejidad de una tarea y enruta
al pipeline adecuado (shallow vs deep).

Basado en research 2026:
  - Tareas simples (shallow): 1-2 subtasks, 1 agente, respuesta directa.
  - Tareas complejas (deep): 3+ subtasks, multi-agente, Plan-and-Execute completo.

Heurísticas de clasificación:
  1. Longitud del mensaje (chars)
  2. Cantidad de entidades/verbos técnicos
  3. Keywords de alta complejidad (arquitectura, diseño, investigación)
  4. Cantidad de dominios involucrados
  5. Presencia de ambigüedad o requisitos implícitos
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

# Umbrales de score (exclusivos) que separan los niveles de complejidad.
TRIVIAL_SCORE_MAX = 0.1
SIMPLE_SCORE_MAX = 0.25
MODERATE_SCORE_MAX = 0.45
COMPLEX_SCORE_MAX = 0.7

# Umbrales de longitud del mensaje (chars, exclusivos) que graduan la
# contribucion de tamano al score (MAG: sin literales en las comparaciones).
SHORT_TEXT_THRESHOLD_CHARS = 200
MEDIUM_TEXT_THRESHOLD_CHARS = 500
LONG_TEXT_THRESHOLD_CHARS = 1000


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ComplexityLevel(str, Enum):
    """Nivel de complejidad de una tarea."""
    TRIVIAL = "trivial"        # 1 step, 1 agent, respuesta directa
    SIMPLE = "simple"          # 1-2 subtasks, 1-2 agents
    MODERATE = "moderate"      # 2-3 subtasks, 2-3 agents, 1-2 niveles
    COMPLEX = "complex"        # 3-5 subtasks, 3+ agents, 2-3 niveles
    VERY_COMPLEX = "very_complex"  # 5+ subtasks, 4+ agents, 3+ niveles


class PipelineType(str, Enum):
    """Tipo de pipeline a ejecutar."""
    SHALLOW = "shallow"     # Directo: detect agent → execute → return
    STANDARD = "standard"   # Plan → execute 1-2 levels → return
    DEEP = "deep"           # Plan → execute multi-level → iterate → consolidate


# ---------------------------------------------------------------------------
# Fan-out cap (FR-C3, ADR-0103/WS-C)
# ---------------------------------------------------------------------------
#
# RSV/EDV — por que cap 5 (no 11):
#   - Ringelmann (efecto social): el rendimiento cae al crecer el grupo; 2
#     agentes DIVERSOS superan a 16 homogeneos (la diversidad, no el volumen,
#     es lo que aporta).
#   - "Capability ceiling": el fan-out rinde +45% sobre el baseline single-agent
#     y luego satura; por encima de ~5 agentes el retorno marginal se anula y
#     el ruido no estructurado amplifica errores.
#   (arXiv:2512.08296 — scaling; arXiv:2602.07787 — amplificacion de ruido).
# El escalado XLarge (11) queda disponible SOLO si el operador lo habilita via
# ``SWARMIND_MAX_FANOUT``. Default: 5.

#: Fan-out maximo por defecto (agentes concurrentes) — cap de seguridad.
MAX_FANOUT_DEFAULT = 5
#: Escalado XLarge historico (3-11), tras override explicito del operador.
MAX_FANOUT_XLARGE = 11
#: Env que sobreescribe el cap de fan-out (entero >= 1).
ENV_MAX_FANOUT = "SWARMIND_MAX_FANOUT"

#: Agentes deseados por nivel de complejidad (antes de aplicar el cap).
_COMPLEXITY_TO_AGENTS: dict[ComplexityLevel, int] = {
    ComplexityLevel.TRIVIAL: 1,
    ComplexityLevel.SIMPLE: 2,
    ComplexityLevel.MODERATE: 3,
    ComplexityLevel.COMPLEX: 5,
    ComplexityLevel.VERY_COMPLEX: MAX_FANOUT_XLARGE,
}


def resolve_max_fanout(default: int = MAX_FANOUT_DEFAULT) -> int:
    """Resuelve el cap de fan-out desde ``SWARMIND_MAX_FANOUT`` o el default.

    Args:
        default: Valor a usar si la env no existe, no es entero o es ``< 1``.

    Returns:
        Entero ``>= 1``. Nunca lanza: ante env invalido retorna ``default``.
    """
    raw = os.getenv(ENV_MAX_FANOUT, "")
    if not raw or not raw.strip():
        return default
    try:
        value = int(raw.strip())
    except (TypeError, ValueError) as exc:
        logger.warning(
            "difficulty_router: WHAT: %s='%s' invalido: %s. "
            "WHY: debe ser un entero >= 1. WHERE: resolve_max_fanout",
            ENV_MAX_FANOUT,
            raw,
            exc,
        )
        return default
    if value < 1:
        logger.warning(
            "difficulty_router: WHAT: %s=%d < 1. "
            "WHY: un fan-out no puede ser cero/negativo. WHERE: resolve_max_fanout",
            ENV_MAX_FANOUT,
            value,
        )
        return default
    return value


class ScaleDecider:
    """Decide el tamano del swarm (fan-out) capado por ``MAX_FANOUT_DEFAULT``.

    Traduce ``ComplexityLevel`` a un numero de agentes deseados (1..11) y lo
    limita al cap efectivo (env ``SWARMIND_MAX_FANOUT`` o 5). Nunca devuelve
    mas agentes que el cap.

    Uso:
        ScaleDecider().decide(ComplexityLevel.VERY_COMPLEX)  # -> 5 (cap default)
    """

    def __init__(self, max_fanout: int | None = None) -> None:
        """Inicializa el decider.

        Args:
            max_fanout: Cap explicito; si es ``None`` usa
                :func:`resolve_max_fanout` (env ``SWARMIND_MAX_FANOUT`` o
                ``MAX_FANOUT_DEFAULT``).
        """
        self._max_fanout = (
            max_fanout if max_fanout is not None else resolve_max_fanout()
        )

    @property
    def max_fanout(self) -> int:
        """Cap efectivo de agentes concurrentes."""
        return self._max_fanout

    def decide(self, complexity: ComplexityLevel) -> int:
        """Numero de agentes para ``complexity``, nunca mayor que el cap.

        Args:
            complexity: Nivel de complejidad clasificado por ``DifficultyRouter``.

        Returns:
            Entero en ``[1, max_fanout]`` = ``min(agentes_deseados, cap)``.
        """
        desired = _COMPLEXITY_TO_AGENTS.get(complexity, MAX_FANOUT_XLARGE)
        return min(desired, self._max_fanout)


# ---------------------------------------------------------------------------
# Complexity Features
# ---------------------------------------------------------------------------

# Palabras que indican alta complejidad
HIGH_COMPLEXITY_KEYWORDS = {
    "arquitectura", "architecture", "diseñar", "design",
    "investigar", "research", "analizar", "analyze",
    "optimizar", "optimize", "migrar", "migrate",
    "integrar", "integrate", "refactorizar", "refactor",
    "arquitectónico", "infraestructura", "infrastructure",
    "escalar", "scale", "distribuido", "distributed",
    "microservicio", "microservices", "event driven",
    "dominio", "domain", "ddd", "hexagonal", "clean architecture",
}

# Palabras que indican tarea simple
LOW_COMPLEXITY_KEYWORDS = {
    "hola", "hello", "hi",
    "test", "prueba",
}

# Verbos técnicos que indican acción compleja
TECH_VERBS = {
    "implementar", "implement", "desarrollar", "develop",
    "construir", "build", "crear", "create",
    "desplegar", "deploy", "configurar", "configure",
    "automatizar", "automate", "orquestar", "orchestrate",
}

# Patrones de ambigüedad (tarea mal definida = más compleja)
AMBIGUITY_PATTERNS = [
    r'\b(etc|etcétera)\b',
    r'\.\.\.',
    r'\by\s+otras\b',
    r'\band\s+more\b',
    r'\bentre\s+otras\b',
    r'\bcomo\s+sea\b',
    r'\bwhatever\b',
]

# Dominios detectables
DOMAIN_KEYWORDS = {
    "backend": {"api", "rest", "endpoint", "servicio", "service", "server", "database", "db", "sql", "nosql"},
    "frontend": {"ui", "ux", "frontend", "react", "vue", "angular", "diseño", "componente", "página", "web"},
    "mobile": {"mobile", "android", "ios", "app", "kotlin", "swift", "flutter", "react native"},
    "devops": {"devops", "docker", "kubernetes", "ci/cd", "deploy", "infra", "terraform", "ansible"},
    "data": {"data", "ml", "ai", "modelo", "train", "entrenar", "dataset", "pipeline", "analytics"},
    "security": {"security", "seguridad", "auth", "oauth", "jwt", "hipaa", "pci", "encrypt"},
    "trading": {"trading", "quant", "estrategia", "strategy", "broker", "market", "alpha", "portfolio"},
    "healthtech": {"health", "healthcare", "clinical", "patient", "fhir", "hl7", "hipaa", "ehr"},
    "retail": {"pos", "retail", "ecommerce", "inventory", "stock", "invoice", "checkout", "payment"},
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ComplexityFeatures:
    """Features extraídas de una tarea para clasificación."""
    length_chars: int = 0
    word_count: int = 0
    high_complexity_matches: int = 0
    low_complexity_matches: int = 0
    tech_verb_count: int = 0
    ambiguity_count: int = 0
    domain_count: int = 0
    domains_found: list[str] = field(default_factory=list)
    has_bullet_points: bool = False
    has_code_blocks: bool = False
    estimated_subtasks: int = 1

    def score(self) -> float:
        """
        Puntaje de complejidad (0.0 = trivial, 1.0 = muy complejo).
        
        Contribuciones:
          - Longitud (>SHORT_TEXT_THRESHOLD_CHARS → +0.1;
            >MEDIUM_TEXT_THRESHOLD_CHARS → +0.2;
            >LONG_TEXT_THRESHOLD_CHARS → +0.3)
          - High complexity keywords: +0.15 c/u (max 0.4)
          - Tech verbs: +0.1 c/u (max 0.3)
          - Ambiguity: +0.1 c/u
          - Multi-domain: +0.15 c/u extra (max 0.3)
          - Bullet points: +0.1
          - Code blocks: +0.15
          - Low complexity keywords: -0.1 c/u
        """
        s = 0.0

        # Length
        if self.length_chars > LONG_TEXT_THRESHOLD_CHARS:
            s += 0.3
        elif self.length_chars > MEDIUM_TEXT_THRESHOLD_CHARS:
            s += 0.2
        elif self.length_chars > SHORT_TEXT_THRESHOLD_CHARS:
            s += 0.1

        # High complexity keywords
        s += min(self.high_complexity_matches * 0.15, 0.4)

        # Tech verbs
        s += min(self.tech_verb_count * 0.1, 0.3)

        # Ambiguity
        s += self.ambiguity_count * 0.1

        # Domains
        if self.domain_count >= 3:
            s += 0.3
        elif self.domain_count >= 2:
            s += 0.15

        # Structure
        if self.has_bullet_points:
            s += 0.1
        if self.has_code_blocks:
            s += 0.15

        # Low complexity (discount)
        s -= min(self.low_complexity_matches * 0.1, 0.3)

        return max(0.0, min(1.0, s))

    def to_dict(self) -> dict:
        return {
            "length_chars": self.length_chars,
            "word_count": self.word_count,
            "high_complexity_matches": self.high_complexity_matches,
            "low_complexity_matches": self.low_complexity_matches,
            "tech_verb_count": self.tech_verb_count,
            "ambiguity_count": self.ambiguity_count,
            "domain_count": self.domain_count,
            "domains_found": self.domains_found,
            "has_bullet_points": self.has_bullet_points,
            "has_code_blocks": self.has_code_blocks,
            "score": round(self.score(), 3),
        }


# ---------------------------------------------------------------------------
# DifficultyRouter
# ---------------------------------------------------------------------------

class DifficultyRouter:
    """
    Router de dificultad que clasifica una tarea y determina el pipeline.

    OPTIMIZACION SWISS WATCH: Thresholds reducidos para maximizar paralelismo.
    Por defecto, toda tarea no trivial se enruta a DEEP (multi-agente, fan-out).

    Uso:
        router = DifficultyRouter()
        result = router.route("Implementar API REST con Docker y CI/CD")
        # result.complexity = ComplexityLevel.VERY_COMPLEX (por defecto)
        # result.pipeline = PipelineType.DEEP
    """

    def __init__(
        self,
        shallow_threshold: float = 0.10,
        deep_threshold: float = 0.20,
    ) -> None:
        """
        Args:
            shallow_threshold: Score ≤ este valor → SHALLOW pipeline.
            deep_threshold: Score ≥ este valor → DEEP pipeline.
        """
        self._shallow_threshold = shallow_threshold
        self._deep_threshold = deep_threshold

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def route(self, message: str) -> RoutingDecision:
        """
        Clasifica una tarea y devuelve la decisión de ruteo.

        Args:
            message: La tarea del usuario.

        Returns:
            RoutingDecision con nivel de complejidad, pipeline, y features.
        """
        features = self._extract_features(message)
        score = features.score()
        complexity = self._classify_complexity(score, features)
        pipeline = self._select_pipeline(complexity, features)

        return RoutingDecision(
            message=message,
            complexity=complexity,
            pipeline=pipeline,
            score=score,
            features=features,
        )

    def estimate_subtasks(self, message: str) -> int:
        """Estima cuántas subtasks generará esta tarea."""
        features = self._extract_features(message)
        return self._estimate_subtasks(features)

    def decide_scale(
        self, message: str, decider: ScaleDecider | None = None
    ) -> int:
        """Numero de agentes (fan-out) para ``message``, respetando el cap.

        WHAT: clasifica el mensaje y delega en ``ScaleDecider``. WHY: unifica
        clasificacion + cap de escalado (FR-C3). WHERE: coordinator (escalado).

        Args:
            message: Tarea del usuario.
            decider: Decisor inyectable; si es ``None`` usa ``ScaleDecider()``
                (lee el cap del env o ``MAX_FANOUT_DEFAULT``).

        Returns:
            Entero ``>= 1`` y ``<= max_fanout`` (nunca mayor que el cap).
        """
        decision = self.route(message)
        return (decider or ScaleDecider()).decide(decision.complexity)

    def route_slm(self, message: str, task_type: str = "classification") -> dict:
        """Recomienda la ruta de ejecución SLM-first (ADR-0034).

        Punto de integración con SlmRouter: para tareas de baja complejidad
        (TRIVIAL/SIMPLE -> SHALLOW pipeline) sugiere ejecución con modelo
        pequeño, reservando frontier para planning y razonamiento.

        Args:
            message: La tarea del usuario.
            task_type: tipo de tarea para SlmRouter (ver SLM_FRIENDLY_TASKS).

        Returns:
            Dict con decision (slm/frontier), pipeline, y score.
        """
        decision = self.route(message)
        difficulty = self._complexity_to_difficulty(decision.complexity)
        route = "frontier"
        # SHALLOW + tarea mecánica verificable -> SLM-first.
        if decision.pipeline == PipelineType.SHALLOW:
            try:
                from harness.orchestrator.slm_router import SlmRouter
                route = SlmRouter().decide(task_type, difficulty)
            except ImportError:
                route = "frontier"  # Fallback seguro
        return {
            "route": route,
            "pipeline": decision.pipeline.value,
            "score": round(decision.score, 3),
            "difficulty": difficulty,
        }

    def _complexity_to_difficulty(self, complexity: ComplexityLevel) -> int:
        """Mapea ComplexityLevel (0..4) a la escala 0..4 de SlmRouter."""
        mapping = {
            ComplexityLevel.TRIVIAL: 0,
            ComplexityLevel.SIMPLE: 1,
            ComplexityLevel.MODERATE: 2,
            ComplexityLevel.COMPLEX: 3,
            ComplexityLevel.VERY_COMPLEX: 4,
        }
        return mapping[complexity]

    # ------------------------------------------------------------------
    # Feature Extraction
    # ------------------------------------------------------------------

    def _extract_features(self, message: str) -> ComplexityFeatures:
        """Extrae features de complejidad de un mensaje."""
        if not message:
            return ComplexityFeatures()

        msg_lower = message.lower()
        words = msg_lower.split()

        features = ComplexityFeatures(
            length_chars=len(message),
            word_count=len(words),
        )

        # High complexity keywords
        features.high_complexity_matches = sum(
            1 for kw in HIGH_COMPLEXITY_KEYWORDS if kw in msg_lower
        )

        # Low complexity keywords
        features.low_complexity_matches = sum(
            1 for kw in LOW_COMPLEXITY_KEYWORDS if kw in msg_lower
        )

        # Tech verbs
        features.tech_verb_count = sum(
            1 for v in TECH_VERBS if v in msg_lower
        )

        # Ambiguity patterns
        features.ambiguity_count = sum(
            1 for p in AMBIGUITY_PATTERNS if re.search(p, msg_lower)
        )

        # Domains
        features.domains_found = []
        for domain, keywords in DOMAIN_KEYWORDS.items():
            if any(kw in msg_lower for kw in keywords):
                features.domains_found.append(domain)
        features.domain_count = len(features.domains_found)

        # Structure
        features.has_bullet_points = bool(
            re.search(r'(^|\n)\s*[*-]\s', message)
        )
        features.has_code_blocks = bool(
            re.search(r'```|`[^`]+`', message)
        )

        features.estimated_subtasks = self._estimate_subtasks(features)

        return features

    def _estimate_subtasks(self, features: ComplexityFeatures) -> int:
        """Estima subtasks basado en features."""
        base = 1
        base += features.tech_verb_count
        base += features.high_complexity_matches // 2
        base += max(0, features.domain_count - 1)
        if features.has_code_blocks:
            base += 1
        if features.length_chars > MEDIUM_TEXT_THRESHOLD_CHARS:
            base += 1
        # Cap at 16 subtasks (Swiss Watch: maximo paralelismo)
        return min(base, 16)

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------

    def _classify_complexity(
        self, score: float, features: ComplexityFeatures,
    ) -> ComplexityLevel:
        """Clasifica el nivel de complejidad desde el score."""
        if score < TRIVIAL_SCORE_MAX:
            return ComplexityLevel.TRIVIAL
        elif score < SIMPLE_SCORE_MAX:
            return ComplexityLevel.SIMPLE
        elif score < MODERATE_SCORE_MAX:
            return ComplexityLevel.MODERATE
        elif score < COMPLEX_SCORE_MAX:
            return ComplexityLevel.COMPLEX
        else:
            return ComplexityLevel.VERY_COMPLEX

    def _select_pipeline(
        self, complexity: ComplexityLevel, features: ComplexityFeatures,
    ) -> PipelineType:
        """Selecciona el pipeline combinando score y complejidad.

        Los umbrales del constructor tienen prioridad cuando el score es > 0
        (``deep_threshold`` fuerza DEEP; ``shallow_threshold`` fuerza SHALLOW).
        En la zona intermedia se conserva el mapeo historico por complejidad.
        """
        score = features.score()
        if score > 0 and score >= self._deep_threshold:
            return PipelineType.DEEP
        if score > 0 and score <= self._shallow_threshold:
            return PipelineType.SHALLOW
        if complexity in (ComplexityLevel.TRIVIAL, ComplexityLevel.SIMPLE):
            return PipelineType.SHALLOW
        if complexity is ComplexityLevel.MODERATE:
            return PipelineType.STANDARD
        return PipelineType.DEEP

    # ------------------------------------------------------------------
    # Batch classification
    # ------------------------------------------------------------------

    def classify_batch(self, messages: list[str]) -> dict[str, RoutingDecision]:
        """Clasifica un batch de mensajes."""
        return {msg: self.route(msg) for msg in messages}


# ---------------------------------------------------------------------------
# RoutingDecision
# ---------------------------------------------------------------------------

@dataclass
class RoutingDecision:
    """Decisión completa de ruteo para una tarea."""
    message: str
    complexity: ComplexityLevel
    pipeline: PipelineType
    score: float
    features: ComplexityFeatures

    @property
    def is_deep(self) -> bool:
        return self.pipeline == PipelineType.DEEP

    @property
    def is_shallow(self) -> bool:
        return self.pipeline == PipelineType.SHALLOW

    def to_dict(self) -> dict:
        return {
            "message": self.message[:100],
            "complexity": self.complexity.value,
            "pipeline": self.pipeline.value,
            "score": round(self.score, 3),
            "features": self.features.to_dict(),
        }

    def __repr__(self) -> str:
        return (
            f"RoutingDecision("
            f"complexity={self.complexity.value}, "
            f"pipeline={self.pipeline.value}, "
            f"score={self.score:.2f}, "
            f"domains={self.features.domains_found})"
        )
