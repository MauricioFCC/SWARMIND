"""
Cognition store synchronisation.

Manages the ``asi_cognition_store`` collection — a persistent knowledge base
of lessons, insights, and cognition artefacts produced by the evolve loop.
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np

from harness.memory_rag.lance_vector_store import LanceVectorStore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_COGNITION_COLLECTION = "asi_cognition_store"
_EMBEDDING_DIM = 384


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class CognitionLesson:
    """A single cognition artefact / lesson stored in the collection."""

    id: str
    title: str
    content: str
    domain: str
    tags: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    access_count: int = 0
    last_accessed: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "domain": self.domain,
            "tags": self.tags,
            "metrics": self.metrics,
            "created_at": self.created_at,
            "access_count": self.access_count,
            "last_accessed": self.last_accessed,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CognitionLesson:
        return cls(
            id=data.get("id", ""),
            title=data.get("title", ""),
            content=data.get("content", ""),
            domain=data.get("domain", ""),
            tags=data.get("tags", []),
            metrics=data.get("metrics", {}),
            created_at=data.get("created_at", ""),
            access_count=data.get("access_count", 0),
            last_accessed=data.get("last_accessed", ""),
        )


# ---------------------------------------------------------------------------
# CognitionSync
# ---------------------------------------------------------------------------


class CognitionSync:
    """
    Synchronises cognition artefacts with the vector store.

    Provides CRUD-style operations on the ``asi_cognition_store`` collection,
    with automatic vector embedding and search.
    """

    def __init__(
        self,
        vector_store: Optional[LanceVectorStore] = None,
        embedding_fn: Optional[callable] = None,
    ) -> None:
        """
        Args:
            vector_store: A ``LanceVectorStore`` instance.  Defaults to a new one.
            embedding_fn: Optional text -> np.ndarray embedding function.
        """
        self.store = vector_store or LanceVectorStore()
        self._embedding_fn = embedding_fn or self._default_embedding

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_lesson(
        self,
        title: str,
        content: str,
        domain: str,
        tags: Optional[List[str]] = None,
        metrics: Optional[Dict[str, Any]] = None,
    ) -> CognitionLesson:
        """
        Create a new cognition lesson and persist it to the store.

        Args:
            title: Short title for the lesson.
            content: Full lesson text / insight.
            domain: Knowledge domain (e.g. ``"trading"``, ``"ml"``, ``"infra"``).
            tags: Optional list of tags for filtering.
            metrics: Optional dict of numeric or categorical metrics.

        Returns:
            The newly created ``CognitionLesson``.
        """
        lesson = CognitionLesson(
            id=str(uuid.uuid4()),
            title=title,
            content=content,
            domain=domain,
            tags=tags or [],
            metrics=metrics or {},
            created_at=datetime.now(timezone.utc).isoformat(),
            access_count=0,
            last_accessed="",
        )

        # Build embedding from title + content
        text_for_embedding = f"{title} {content}"
        vector = self._embedding_fn(text_for_embedding).reshape(1, -1)

        # Build metadata payload
        metadata = {
            "id": lesson.id,
            "title": lesson.title,
            "content": lesson.content,
            "domain": lesson.domain,
            "tags": lesson.tags,
            "metrics": lesson.metrics,
            "created_at": lesson.created_at,
            "access_count": lesson.access_count,
            "last_accessed": lesson.last_accessed,
        }

        try:
            self.store.insert(
                _COGNITION_COLLECTION, vector, [metadata]
            )
            logger.info(
                "Lesson added — id=%s domain=%s title=%s",
                lesson.id, domain, title,
            )
        except Exception:
            logger.exception("Failed to persist lesson to vector store.")

        return lesson

    def search_lessons(
        self,
        query: str,
        top_k: int = 5,
    ) -> List[CognitionLesson]:
        """
        Search cognition lessons by semantic similarity.

        Args:
            query: Natural language query string.
            top_k: Maximum number of results to return.

        Returns:
            List of ``CognitionLesson`` instances ordered by relevance.
        """
        query_vec = self._embedding_fn(query)

        try:
            results = self.store.search(
                _COGNITION_COLLECTION, query_vec, top_k=top_k
            )
        except Exception:
            logger.exception("Cognition lesson search failed.")
            return []

        lessons: List[CognitionLesson] = []
        for r in results:
            meta = r.get("metadata", {})
            lesson = CognitionLesson.from_dict(meta)
            lessons.append(lesson)

        # Bump access_count for retrieved lessons
        for lesson in lessons:
            self._bump_access(lesson.id)

        return lessons

    def get_lesson_by_id(self, lesson_id: str) -> Optional[CognitionLesson]:
        """
        Retrieve a single cognition lesson by its ID.

        Args:
            lesson_id: The UUID of the lesson.

        Returns:
            The ``CognitionLesson`` or ``None`` if not found.
        """
        try:
            # Use a dummy vector and rely on metadata filter
            dummy = np.zeros(_EMBEDDING_DIM, dtype=np.float32)
            results = self.store.search(
                _COGNITION_COLLECTION,
                dummy,
                top_k=1,
                filters={"id": lesson_id},
            )
        except Exception:
            logger.exception("Failed to retrieve lesson %s", lesson_id)
            return None

        if not results:
            return None

        meta = results[0].get("metadata", {})
        lesson = CognitionLesson.from_dict(meta)
        self._bump_access(lesson.id)
        return lesson

    def get_lessons_by_domain(
        self, domain: str, top_k: int = 20
    ) -> List[CognitionLesson]:
        """
        Retrieve all lessons belonging to a given domain.

        Args:
            domain: Domain string to filter by.
            top_k: Maximum results.

        Returns:
            List of ``CognitionLesson`` instances.
        """
        try:
            dummy = np.zeros(_EMBEDDING_DIM, dtype=np.float32)
            results = self.store.search(
                _COGNITION_COLLECTION,
                dummy,
                top_k=top_k,
                filters={"domain": domain},
            )
        except Exception:
            logger.exception(
                "Failed to retrieve lessons for domain '%s'", domain
            )
            return []

        lessons: List[CognitionLesson] = []
        for r in results:
            meta = r.get("metadata", {})
            lesson = CognitionLesson.from_dict(meta)
            lessons.append(lesson)

        return lessons

    def get_all_tags(self) -> List[str]:
        """
        Return a flat list of all unique tags across stored lessons.
        """
        try:
            dummy = np.zeros(_EMBEDDING_DIM, dtype=np.float32)
            # Request a large batch to get a representative tag set
            results = self.store.search(
                _COGNITION_COLLECTION, dummy, top_k=100
            )
        except Exception:
            return []

        seen: set = set()
        for r in results:
            tags = r.get("metadata", {}).get("tags", [])
            seen.update(tags)
        return sorted(seen)

    def delete_lesson(self, lesson_id: str) -> bool:
        """
        Remove a lesson by ID.

        .. note::
            LanceVectorStore does not yet support single-record deletion;
            this is a no-op placeholder until that feature is added.

        Returns:
            ``True`` if deletion was performed (currently always ``False``).
        """
        logger.warning(
            "Single-record deletion not yet implemented in LanceVectorStore. "
            "Lesson %s was not removed.",
            lesson_id,
        )
        return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _bump_access(self, lesson_id: str) -> None:
        """Increment the access counter for a lesson (best-effort)."""
        # In a full implementation this would update the record in place.
        # For now we log that the lesson was accessed.
        logger.debug("Lesson %s accessed.", lesson_id)

    @staticmethod
    def _default_embedding(text: str) -> np.ndarray:
        """
        Fallback embedding: character-level frequency vector.

        Produces a fixed-size normalised vector from printable-ASCII
        character counts.  Not semantically meaningful but keeps the
        system functional without an external embedding model.
        """
        vec = np.zeros(_EMBEDDING_DIM, dtype=np.float32)
        for i, ch in enumerate(text.encode("utf-8", errors="replace")):
            idx = (i * 7 + ch) % _EMBEDDING_DIM
            vec[idx] += 1.0
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        return vec
