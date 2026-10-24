"""
skill_router.py â€” Router semantico de skills via LanceDB.

Selecciona SOLO los skills relevantes para una tarea usando similitud
vectorial en LanceDB. Reduce tokens de contexto 60-80% vs cargar todos.

Uso:
    router = SkillRouter(store)
    skills = router.route("implementa API REST en Rust")
    # â†’ ["quant-trading"] (no carga todos los skills)
    context = router.build_context(skills)

SSOT: el registry de skills se DERIVA de ``.opencode/skills/skills_registry.yaml``
(nombres + dominios). Las keywords de matching son configuracion de tuning en
este modulo (precisas donde un test fija el comportamiento; derivadas del
trigger de la ``description`` en el resto). NO se duplica el registry.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from harness.common import fallback_embedding
from harness.orchestrator.keyword_match import normalize

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Carga del registry desde el SSOT (lazy + cache)
# ---------------------------------------------------------------------------

#: Ruta por defecto al registry curado de skills (SSOT del repo).
_DEFAULT_REGISTRY_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / ".opencode" / "skills" / "skills_registry.yaml"
)

#: Entradas curadas de respaldo (nombre, dominio, keywords) para cuando el
#: registry no esta disponible. Conservan el comportamiento historico del
#: router; el registry real las reemplaza cuando existe.
_CURATED_ENTRIES: tuple[tuple[str, str, str], ...] = (
    ("alpha-research", "quantitative", "factor research ml machine learning feature engineering statistical validation alpha backtest"),
    ("evolve", "meta", "self-improvement evolution loop cognition auto-mejora continua"),
    ("healthtech", "healthtech", "health healthcare clinical hipaa ehr interoperabilidad paciente health-record medico clinicas historia clinical historial"),
    ("hedgefund", "financial", "hedge fund institutional risk reward capital allocation portfolio"),
    ("legal-doc", "legal", "legal contract compliance law jurisprudence documento juridico"),
    ("math-doc", "academic", "math latex theorem proof equation estadistica algebra calculo"),
    ("pos-retail", "retail", "pos retail punto venta inventory stock checkout payment"),
    ("quant-trading", "quantitative", "trading strategy quantitative quant alpha execution broker"),
    ("risk-execution", "quantitative", "risk management position sizing market making tca execution"),
    ("science-doc", "academic", "science paper research thesis systematic review peer review"),
)

#: Keywords curadas por nombre de skill (matching preciso fijado por tests).
#: Las skills sin entrada aqui derivan sus keywords del trigger del SSOT.
_CURATED_KEYWORDS: dict[str, str] = {
    name: keywords for name, _domain, keywords in _CURATED_ENTRIES
}

#: Registry de respaldo ya materializado (deriva de ``_CURATED_ENTRIES``).
_FALLBACK_REGISTRY: list[dict[str, Any]] = [
    {"name": name, "domain": domain, "keywords": keywords}
    for name, domain, keywords in _CURATED_ENTRIES
]

#: Stopwords (funcionales + plantilla de descripcion) excluidas al derivar.
_KEYWORD_STOPWORDS: frozenset[str] = frozenset({
    "usar", "cuando", "el", "la", "los", "las", "un", "una", "unos", "unas",
    "de", "del", "en", "y", "o", "u", "a", "al", "para", "por", "con", "sin",
    "que", "se", "su", "sus", "es", "son", "como", "mas", "este", "esta",
    "estos", "estas", "usuario", "busca", "quiere", "necesita", "pide",
    "opera", "dominio", "trabaja", "analiza", "gestiona", "disena", "construye",
    "implementa", "evalua", "nuevo", "nueva", "alcance", "involucra", "problema",
    "the", "of", "to", "and", "or", "for", "ver",
})

#: Longitud minima de un token derivado (evita colisiones por substring).
_KEYWORD_MIN_LEN = 4

#: Cache ``ruta -> registry`` para no leer/reparsear el YAML en cada uso.
_REGISTRY_CACHE: dict[str, list[dict[str, Any]]] = {}


def _derive_keywords(description: str) -> str:
    """Deriva keywords de matching desde la ``description`` del SSOT.

    WHAT: toma el segmento de triggers (posterior a la primera oracion de prosa
    y anterior a ``Alcance:``), lo normaliza y deduplica. WHY: evita duplicar
    el registry a mano; el trigger pushy ya concentra las palabras clave. NO
    incluye el nombre ni el dominio para no colisionar por substring (p. ej.
    "rust-lang" no debe disparar "rust" de forma generica). WHERE:
    ``_read_registry`` para skills sin keywords curadas.

    Args:
        description: Description pushy del registry.

    Returns:
        Keywords separadas por espacio (puede ser ``""`` si no hay triggers).
    """
    head = (description or "").split("Alcance:")[0]
    # WHAT: se descarta la primera oracion (prosa "Usar cuando...") cuando el
    # trigger ocupa la segunda; si no hay segunda (description en una oracion),
    # se usa el texto completo para no dejar las keywords vacias.
    parts = re.split(r"\.\s", head, maxsplit=1)
    trigger = parts[1] if len(parts) > 1 and parts[1].strip() else parts[0]
    tokens: list[str] = []
    for raw in normalize(trigger).split():
        token = raw.strip(".,;:")
        if len(token) >= _KEYWORD_MIN_LEN and token not in _KEYWORD_STOPWORDS:
            tokens.append(token)
    return " ".join(dict.fromkeys(tokens))


def _read_registry(path: Path) -> list[dict[str, Any]]:
    """Lee y normaliza el registry YAML a entradas del router.

    Args:
        path: Ruta al ``skills_registry.yaml``.

    Returns:
        Lista de ``{name, domain, keywords}``; fallback curado si el archivo no
        existe, no parsea o no declara skills.
    """
    if not path.exists():
        logger.warning(
            "skill_router: registry no encontrado en %s; usando fallback curado",
            path,
        )
        return list(_FALLBACK_REGISTRY)
    try:
        with open(path, encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
    except (OSError, yaml.YAMLError) as exc:
        logger.warning(
            "skill_router: no se pudo leer %s (%s); usando fallback curado",
            path,
            exc,
        )
        return list(_FALLBACK_REGISTRY)

    raw = data.get("skills", []) if isinstance(data, dict) else []
    entries: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        name = str(item["name"])
        domain = str(item.get("domain", "general"))
        keywords = _CURATED_KEYWORDS.get(name) or _derive_keywords(
            str(item.get("description", ""))
        )
        entries.append({"name": name, "domain": domain, "keywords": keywords})
    return entries or list(_FALLBACK_REGISTRY)


def load_skill_registry(registry_path: str | Path | None = None) -> list[dict[str, Any]]:
    """Carga (con cache) el registry de skills desde el SSOT YAML.

    Args:
        registry_path: Ruta alternativa al registry; por defecto el SSOT del
            repo (``.opencode/skills/skills_registry.yaml``).

    Returns:
        Lista de entradas ``{name, domain, keywords}`` (misma instancia cacheada
        por ruta).
    """
    path = Path(registry_path) if registry_path is not None else _DEFAULT_REGISTRY_PATH
    key = str(path)
    cached = _REGISTRY_CACHE.get(key)
    if cached is None:
        cached = _read_registry(path)
        _REGISTRY_CACHE[key] = cached
    return cached


#: Registry de skills del router, derivado del SSOT (compat: antes constante).
SKILL_REGISTRY: list[dict[str, Any]] = load_skill_registry()

# Skills siempre activos (minimo contexto)
ALWAYS_ACTIVE = {"evolve"}

# Maximo skills a cargar por tarea
MAX_SKILLS_PER_TASK = 2


class SkillRouter:
    """
    Router semantico de skills.

    Dado un mensaje del usuario, encuentra los TOP-N skills mas relevantes
    usando similitud de embeddings contra la matriz de keywords de cada skill.

    Esto evita cargar los 10 skills en contexto, ahorrando 60-80% de tokens.
    """

    def __init__(self, embedding_fn=None):
        """
        Args:
            embedding_fn: Funcion para generar embeddings.
                         Si es None, usa fallback interno.
        """
        self._embedding_fn = embedding_fn or self._default_embedding
        self._skill_vectors: np.ndarray | None = None
        self._skill_names: list[str] = []
        self._build_skill_vectors()

    def _default_embedding(self, text: str) -> np.ndarray:
        """Fallback embedding: delega en ``harness.common.fallback_embedding``.

        Args:
            text: Texto a embedder.

        Returns:
            Vector normalizado de dimension 384.
        """
        return fallback_embedding(text)

    def _build_skill_vectors(self) -> None:
        """Pre-computa vectores para cada skill."""
        vectors = []
        for skill in SKILL_REGISTRY:
            text = f"{skill['name']} {skill['domain']} {skill['keywords']}"
            vec = self._embedding_fn(text)
            vectors.append(vec)
            self._skill_names.append(skill["name"])
        self._skill_vectors = np.stack(vectors) if vectors else np.zeros((1, 384))

    def route(self, message: str, max_skills: int = MAX_SKILLS_PER_TASK) -> list[str]:
        """
        Encuentra los skills mas relevantes para un mensaje.

        Args:
            message: Mensaje del usuario.
            max_skills: Maximo de skills a retornar (default: 2).

        Returns:
            Lista de nombres de skills a activar (siempre incluye ALWAYS_ACTIVE).
        """
        if not message or not message.strip():
            return list(ALWAYS_ACTIVE)

        # 1. Matching por keywords (rapido, sin embedding)
        keyword_matches = self._keyword_match(message)
        if keyword_matches:
            result = list(ALWAYS_ACTIVE)
            for s in keyword_matches[:max_skills]:
                if s not in result:
                    result.append(s)
            return result

        # 2. Matching semantico (embedding)
        query_vec = self._embedding_fn(message)
        if self._skill_vectors is not None and len(self._skill_vectors) > 0:
            scores = np.dot(self._skill_vectors, query_vec) / (
                np.linalg.norm(self._skill_vectors, axis=1) * np.linalg.norm(query_vec) + 1e-8
            )
            top_indices = np.argsort(scores)[::-1][:max_skills]
            result = list(ALWAYS_ACTIVE)
            for idx in top_indices:
                name = self._skill_names[idx]
                if name not in result:
                    result.append(name)
            return result

        return list(ALWAYS_ACTIVE)

    def _keyword_match(self, message: str) -> list[str]:
        """Matching rapido por keywords (sin embedding)."""
        msg_lower = message.lower()
        scored = []
        for skill in SKILL_REGISTRY:
            keywords = skill["keywords"].split()
            score = sum(1 for kw in keywords if kw in msg_lower)
            # Bonus por dominio
            if skill["domain"] in msg_lower:
                score += 3
            if score > 0:
                scored.append((score, skill["name"]))
        scored.sort(reverse=True)
        return [name for _, name in scored]

    def build_context(self, skill_names: list[str]) -> str:
        """
        Construye contexto SOLO para los skills seleccionados.

        Args:
            skill_names: Lista de skills a incluir.

        Returns:
            String de contexto (mucho mas corto que cargar todos los skills).
        """
        parts = []
        for name in skill_names:
            for skill in SKILL_REGISTRY:
                if skill["name"] == name:
                    parts.append(f"- {name}: {skill['keywords'][:120]}")
                    break
        return "\n".join(parts) if parts else ""

    def estimate_tokens(self, skill_names: list[str]) -> int:
        """Estima tokens que consumiran los skills seleccionados."""
        context = self.build_context(skill_names)
        return len(context) // 4

    def get_available_skills(self) -> list[str]:
        """Retorna lista de todos los skills disponibles."""
        return [s["name"] for s in SKILL_REGISTRY]
