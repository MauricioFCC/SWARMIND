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

import re
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


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
    "hola", "hello", "hi", "test", "prueba",
    "simple", "básico", "basic", "rápido", "quick",
    "duda", "question", "pregunta",
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
    domains_found: List[str] = field(default_factory=list)
    has_bullet_points: bool = False
    has_code_blocks: bool = False
    estimated_subtasks: int = 1

    def score(self) -> float:
        """
        Puntaje de complejidad (0.0 = trivial, 1.0 = muy complejo).
        
        Contribuciones:
          - Longitud (>500 chars → +0.2)
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
        if self.length_chars > 1000:
            s += 0.3
        elif self.length_chars > 500:
            s += 0.2
        elif self.length_chars > 200:
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

    def to_dict(self) -> Dict:
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

    def route(self, message: str) -> "RoutingDecision":
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
        if features.length_chars > 500:
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
        if score < 0.1:
            return ComplexityLevel.TRIVIAL
        elif score < 0.25:
            return ComplexityLevel.SIMPLE
        elif score < 0.45:
            return ComplexityLevel.MODERATE
        elif score < 0.7:
            return ComplexityLevel.COMPLEX
        else:
            return ComplexityLevel.VERY_COMPLEX

    def _select_pipeline(
        self, complexity: ComplexityLevel, features: ComplexityFeatures,
    ) -> PipelineType:
        """Selecciona el pipeline según complejidad."""
        if complexity in (ComplexityLevel.TRIVIAL, ComplexityLevel.SIMPLE):
            return PipelineType.SHALLOW
        elif complexity in (ComplexityLevel.MODERATE,):
            return PipelineType.STANDARD
        else:
            return PipelineType.DEEP

    # ------------------------------------------------------------------
    # Batch classification
    # ------------------------------------------------------------------

    def classify_batch(self, messages: List[str]) -> Dict[str, "RoutingDecision"]:
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

    def to_dict(self) -> Dict:
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
