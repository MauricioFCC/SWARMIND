"""Tipos, IDs canónicos y validación del catálogo de conocimiento.

WHAT: esquema inmutable del catálogo (``CatalogEntry``/``CatalogLink``),
normalización de IDs (arXiv/DOI/GitHub), texto indexable, hash de contenido y
metadata. Separado de ``knowledge_catalog.py`` para mantener cada módulo bajo
el límite F3 (500 líneas) y aislar los tipos puros (sin I/O).

WHY: el catálogo mezclaba esquema + persistencia + búsqueda en 612 líneas y el
gate de arquitectura lo marcaba como deuda nueva. Los tipos puros son además
reutilizables por el CLI, los tests y cualquier exportador sin abrir el store.

WHERE: ``harness/memory_rag/knowledge_catalog_types.py``; consumido por
``knowledge_catalog.py`` y ``scripts/knowledge_catalog.py``.

Invariantes: validación al construir (título/URL/año/privacidad), IDs
idempotentes y deterministas, sin I/O de red ni de disco.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

#: Relaciones permitidas entre entradas del catálogo.
RELATIONS: frozenset[str] = frozenset(
    {"cites", "implements", "uses", "extends", "evaluates", "related_to"}
)

_ARXIV_RE = re.compile(
    r"(?:arxiv[:/]|arxiv\.org/(?:abs|pdf)/)(\d{4}\.\d{4,5})(?:v\d+)?"
)
_DOI_RE = re.compile(r"(?:doi:|doi\.org/)(10\.\d{4,9}/[^\s]+)")
_GITHUB_RE = re.compile(r"github\.com/([^/\s#?]+)/([^/\s#?]+?)(?:\.git)?/?$")
_CANONICAL_RE = re.compile(
    r"^(?:repo|paper|article|technique|architecture|algorithm):[a-z0-9._/:-]+$"
)
_PERSONAL_PATH_RE = re.compile(
    r"(?:[A-Za-z]:\\Users\\(?!<|\$|u\\|user\\|username\\|usuario\\|your)[^\\\s\"']+"
    r"|(?<![\w./\-])/Users/(?!<|\$|u/|user/|username/|usuario/|your)[^/\"']+"
    r"|(?<![\w./\-])/home/(?!<|\$|u/|user/|username/|usuario/|your)[^/\"']+)"
)
_SLUG_RE = re.compile(r"[^a-z0-9]+")


class EntryKind(str, Enum):
    """Tipo de conocimiento catalogado."""

    REPO = "repo"
    PAPER = "paper"
    ARTICLE = "article"
    TECHNIQUE = "technique"
    ARCHITECTURE = "architecture"
    ALGORITHM = "algorithm"


class EntryStatus(str, Enum):
    """Estado de adopción de una entrada."""

    ADOPTED = "adopted"
    EVALUATED = "evaluated"
    UNVERIFIED = "unverified"
    REJECTED = "rejected"


@dataclass(frozen=True)
class CatalogLink:
    """Arista tipada entre dos entradas del catálogo.

    Args:
        relation: Relación semántica (ver :data:`RELATIONS`).
        target: ``catalog_id`` de la entrada destino.
    """

    relation: str
    target: str

    def __post_init__(self) -> None:
        """Valida relación y destino (no acepta aristas vacías)."""
        if self.relation not in RELATIONS:
            raise ValueError(
                f"WHAT: relación '{self.relation}' inválida. "
                f"WHY: el grafo solo admite {sorted(RELATIONS)}. "
                "WHERE: CatalogLink.relation"
            )
        if not self.target.strip():
            raise ValueError(
                "WHAT: arista sin destino. WHY: el grafo quedaría incompleto. "
                "WHERE: CatalogLink.target"
            )


@dataclass(frozen=True)
class CatalogEntry:
    """Entrada del catálogo (inmutable y validada al construir).

    Args:
        kind: Tipo de conocimiento.
        title: Título legible (no vacío).
        url: URL/DOI/arXiv de la fuente.
        summary: Resumen de 1-3 frases.
        authors: Autores (si se conocen).
        year: Año de publicación (1900-2100) o ``None``.
        tags: Etiquetas libres normalizables.
        concepts: Conceptos estructurantes para el grafo.
        complexity_before: Complejidad previa ``O(·)`` (si aplica).
        complexity_after: Complejidad propuesta ``O(·)`` (si aplica).
        status: Estado de adopción.
        source: Procedencia legible (arxiv, github, ...).
        retrieved_at: ISO-8601 de la lectura (vacío = ahora).
        links: Aristas hacia otras entradas del catálogo.
    """

    kind: EntryKind
    title: str
    url: str
    summary: str = ""
    authors: tuple[str, ...] = ()
    year: int | None = None
    tags: tuple[str, ...] = ()
    concepts: tuple[str, ...] = ()
    complexity_before: str = ""
    complexity_after: str = ""
    status: EntryStatus = EntryStatus.UNVERIFIED
    source: str = ""
    retrieved_at: str = ""
    links: tuple[CatalogLink, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        """Normaliza enums/tuplas y valida título, URL, año y privacidad."""
        object.__setattr__(self, "kind", EntryKind(self.kind))
        object.__setattr__(self, "status", EntryStatus(self.status))
        for nombre in ("authors", "tags", "concepts", "links"):
            object.__setattr__(self, nombre, tuple(getattr(self, nombre)))
        if not self.title.strip():
            raise ValueError(
                "WHAT: entrada sin título. WHY: no es recuperable ni citable. "
                "WHERE: CatalogEntry.title"
            )
        if not self.url.strip():
            raise ValueError(
                "WHAT: entrada sin URL. WHY: no hay fuente verificable. "
                "WHERE: CatalogEntry.url"
            )
        if _PERSONAL_PATH_RE.search(self.url):
            raise ValueError(
                "WHAT: URL con ruta personal. WHY: privacidad del equipo "
                "(SEG). WHERE: CatalogEntry.url"
            )
        if self.year is not None and not 1900 <= self.year <= 2100:
            raise ValueError(
                f"WHAT: año {self.year} fuera de rango. WHY: metadato inválido. "
                "WHERE: CatalogEntry.year"
            )

    @property
    def catalog_id(self) -> str:
        """ID canónico ``<kind>:<slug>`` derivado de la URL."""
        return canonical_id(self.kind, self.url)


def _slug(texto: str, limite: int = 80) -> str:
    """Convierte texto a slug estable (minúsculas, ``-``)."""
    limpio = _SLUG_RE.sub("-", texto.strip().lower()).strip("-")
    return (limpio or hashlib.sha256(texto.encode("utf-8")).hexdigest()[:16])[:limite]


def canonical_id(kind: EntryKind | str, ref: str) -> str:
    """Normaliza una referencia a un ID canónico e idempotente.

    Reconoce arXiv, DOI y GitHub; para el resto usa ``<kind>:<host><path>``.

    Args:
        kind: Tipo de entrada (enum o su valor).
        ref: URL, DOI, ``arXiv:...`` o un ID ya canónico.

    Returns:
        ID canónico estable ``<kind>:<slug>`` (nunca vacío).
    """
    tipo = EntryKind(kind) if not isinstance(kind, EntryKind) else kind
    texto = ref.strip()
    if _CANONICAL_RE.match(texto):
        return texto
    arxiv = _ARXIV_RE.search(texto.lower())
    if arxiv is not None:
        return f"paper:arxiv-{arxiv.group(1)}"
    doi = _DOI_RE.search(texto.lower())
    if doi is not None:
        return f"paper:doi-{doi.group(1).rstrip('.')}".replace("/", "-")
    github = _GITHUB_RE.search(texto)
    if github is not None:
        owner, repo = github.group(1).lower(), github.group(2).lower()
        return f"repo:{owner}/{repo}"
    host_path = re.sub(r"^[a-z]+://", "", texto.lower())
    host_path = re.sub(r"^www\.", "", host_path).rstrip("/")
    return f"{tipo.value}:{_slug(host_path)}"


def catalog_text(entry: CatalogEntry) -> str:
    """Construye el texto indexable (título, resumen, tags y conceptos)."""
    partes = [entry.title, entry.summary]
    if entry.tags:
        partes.append("tags: " + ", ".join(entry.tags))
    if entry.concepts:
        partes.append("concepts: " + ", ".join(entry.concepts))
    if entry.authors:
        partes.append("autores: " + ", ".join(entry.authors))
    if entry.year is not None:
        partes.append(f"año: {entry.year}")
    return ". ".join(p for p in partes if p)


def content_hash(entry: CatalogEntry) -> str:
    """SHA-256 del contenido canónico (detecta actualizaciones)."""
    payload = {
        "kind": entry.kind.value,
        "title": entry.title,
        "url": entry.url,
        "summary": entry.summary,
        "authors": list(entry.authors),
        "year": entry.year,
        "tags": list(entry.tags),
        "concepts": list(entry.concepts),
        "complexity_before": entry.complexity_before,
        "complexity_after": entry.complexity_after,
        "status": entry.status.value,
        "source": entry.source,
        "links": [(link.relation, link.target) for link in entry.links],
    }
    crudo = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(crudo.encode("utf-8")).hexdigest()


def entry_metadata(entry: CatalogEntry) -> dict[str, Any]:
    """Metadata JSON-serializable que viaja con el vector."""
    return {
        "catalog_id": entry.catalog_id,
        "kind": entry.kind.value,
        "title": entry.title,
        "url": entry.url,
        "summary": entry.summary,
        "authors": list(entry.authors),
        "year": entry.year,
        "tags": list(entry.tags),
        "concepts": list(entry.concepts),
        "complexity_before": entry.complexity_before,
        "complexity_after": entry.complexity_after,
        "status": entry.status.value,
        "source": entry.source,
    }


def entry_from_json(item: dict[str, Any]) -> CatalogEntry:
    """Convierte un dict JSON (seed) en ``CatalogEntry`` validada."""
    links = tuple(
        CatalogLink(relation=str(link["relation"]), target=str(link["target"]))
        for link in item.get("links") or ()
    )
    return CatalogEntry(
        kind=EntryKind(str(item["kind"])),
        title=str(item["title"]),
        url=str(item["url"]),
        summary=str(item.get("summary", "")),
        authors=tuple(item.get("authors") or ()),
        year=item.get("year"),
        tags=tuple(item.get("tags") or ()),
        concepts=tuple(item.get("concepts") or ()),
        complexity_before=str(item.get("complexity_before", "")),
        complexity_after=str(item.get("complexity_after", "")),
        status=EntryStatus(str(item.get("status", "unverified"))),
        source=str(item.get("source", "")),
        retrieved_at=str(item.get("retrieved_at", "")),
        links=links,
    )
