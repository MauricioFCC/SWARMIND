"""
StrategicMemory — Memoria con forget estrategico (SF-AMS).

arXiv:2607.22562: Utility-driven survival reemplaza decaimiento heuristico.
+9.65 F1 en multi-hop reasoning.

La memoria prioriza retener informacion basada en:
- Frecuencia de acceso
- Relevancia semantica
- Entidades compartidas entre sesiones
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


@dataclass
class MemoryItem:
    """Item individual de memoria strategic.

    Attributes:
        key: Identificador unico del item.
        value: Valor almacenado (cualquier tipo JSON-serializable).
        access_count: Contador de accesos.
        last_accessed: Timestamp UTC del ultimo acceso.
        importance_score: Puntaje de importancia [0.0, 1.0].
        entities: Lista de entidades compartidas entre sesiones.
        semantic_tags: Etiquetas semanticas para busqueda.
    """

    key: str
    value: Any
    access_count: int = 0
    last_accessed: float = 0.0
    importance_score: float = 0.5
    entities: List[str] = field(default_factory=list)
    semantic_tags: List[str] = field(default_factory=list)


class StrategicMemory:
    """Memoria compartida con olvido estrategico basado en utilidad.

    Implementa SF-AMS (Strategic Forgetting via Adaptive Memory Scoring):
    en lugar de decaimiento heuristico, usa un puntaje de utilidad
    compuesto por frecuencia de acceso, relevancia semantica y
    entidades compartidas para decidir que olvidar.

    Args:
        max_items: Maximo numero de items antes de aplicar olvido.
        path: Ruta al archivo JSON de persistencia.
    """

    def __init__(self, max_items: int = 1000, path: Optional[Path] = None) -> None:
        """Inicializa StrategicMemory con capacidad maxima y ruta de persistencia.

        Args:
            max_items: Limite superior de items en memoria (default 1000).
            path: Ruta al archivo JSON. Si no existe, inicia vacio.

        Raises:
            ValueError: Si max_items es menor a 1.
        """
        if max_items < 1:
            raise ValueError("max_items debe ser >= 1")

        self._max_items = max_items
        self._path = path or Path("data/strategic_memory.json")
        self._items: Dict[str, MemoryItem] = {}
        self._load()

    # ------------------------------------------------------------------
    # API publica
    # ------------------------------------------------------------------

    def store(
        self,
        key: str,
        value: Any,
        tags: Optional[List[str]] = None,
        entities: Optional[List[str]] = None,
    ) -> None:
        """Almacena un valor en memoria asociado a una clave.

        Si la clave ya existe, sobrescribe el valor y resetea los
        metadatos. Si se supera ``max_items``, ejecuta olvido estrategico
        basado en puntaje de utilidad.

        Args:
            key: Identificador unico del item.
            value: Valor a almacenar (debe ser JSON-serializable).
            tags: Etiquetas semanticas opcionales.
            entities: Entidades compartidas opcionales.

        Raises:
            TypeError: Si value no es JSON-serializable.
        """
        # Validar serializabilidad temprano
        self._validate_serializable(value)

        item = MemoryItem(
            key=key,
            value=value,
            last_accessed=datetime.now(timezone.utc).timestamp(),
            semantic_tags=tags or [],
            entities=entities or [],
        )
        self._items[key] = item
        if len(self._items) > self._max_items:
            self._forget()
        self._save()

    def recall(self, key: str) -> Optional[Any]:
        """Recupera un valor por su clave.

        Incrementa el contador de acceso, actualiza el timestamp y
        aumenta ligeramente el puntaje de importancia.

        Args:
            key: Clave del item a recuperar.

        Returns:
            El valor almacenado o None si la clave no existe.
        """
        item = self._items.get(key)
        if item is None:
            return None

        item.access_count += 1
        item.last_accessed = datetime.now(timezone.utc).timestamp()
        # Refuerzo de importancia por re-acceso
        item.importance_score = min(1.0, item.importance_score + 0.05)
        self._save()
        return item.value

    def search_by_tags(self, tags: List[str]) -> List[MemoryItem]:
        """Busca items que contengan al menos una de las etiquetas.

        Args:
            tags: Lista de etiquetas a buscar (OR logico).

        Returns:
            Lista de MemoryItem que coinciden con al menos una etiqueta.
        """
        tag_set = set(tags)
        return [
            item
            for item in self._items.values()
            if tag_set.intersection(item.semantic_tags)
        ]

    def search_by_entities(self, entities: List[str]) -> List[MemoryItem]:
        """Busca items que contengan al menos una de las entidades.

        Args:
            entities: Lista de entidades a buscar (OR logico).

        Returns:
            Lista de MemoryItem que coinciden con al menos una entidad.
        """
        entity_set = set(entities)
        return [
            item
            for item in self._items.values()
            if entity_set.intersection(item.entities)
        ]

    def get_stats(self) -> Dict[str, Any]:
        """Retorna estadisticas actuales de la memoria.

        Returns:
            Dict con total_items, max_items, avg_importance y
            top_tags (top-5 tags mas frecuentes).
        """
        total = len(self._items)
        avg_imp = (
            sum(i.importance_score for i in self._items.values()) / max(total, 1)
        )

        # Top-5 tags
        tag_counter: Dict[str, int] = {}
        for item in self._items.values():
            for tag in item.semantic_tags:
                tag_counter[tag] = tag_counter.get(tag, 0) + 1
        top_tags = sorted(tag_counter, key=tag_counter.get, reverse=True)[:5]

        return {
            "total_items": total,
            "max_items": self._max_items,
            "avg_importance": round(avg_imp, 4),
            "top_tags": top_tags,
        }

    def clear(self) -> None:
        """Elimina todos los items de la memoria y persiste el estado vacio."""
        self._items.clear()
        self._save()

    def contains(self, key: str) -> bool:
        """Verifica si una clave existe en memoria.

        Args:
            key: Clave a verificar.

        Returns:
            True si la clave existe, False en caso contrario.
        """
        return key in self._items

    # ------------------------------------------------------------------
    # Metodos internos
    # ------------------------------------------------------------------

    def _forget(self) -> None:
        """Olvido estrategico: utility-driven survival.

        Calcula un puntaje de utilidad compuesto:
          utilidad = importance * 0.40
                   + normalized_access * 0.30
                   + entity_diversity * 0.20
                   + tag_diversity * 0.10

        Elimina los items con menor puntaje hasta volver al limite.
        """
        if len(self._items) <= self._max_items:
            return

        max_access = max((i.access_count for i in self._items.values()), default=0)

        def _utility(item: MemoryItem) -> float:
            norm_access = min(item.access_count / max(max_access, 1), 1.0)
            entity_div = min(len(item.entities) / 10.0, 1.0)
            tag_div = min(len(item.semantic_tags) / 10.0, 1.0)
            return (
                item.importance_score * 0.40
                + norm_access * 0.30
                + entity_div * 0.20
                + tag_div * 0.10
            )

        sorted_items = sorted(self._items.values(), key=_utility)
        remove_count = len(self._items) - self._max_items

        removed_keys = [item.key for item in sorted_items[:remove_count]]
        for key in removed_keys:
            del self._items[key]

        logger.info(
            "StrategicForget: eliminados %d items de baja utilidad | "
            "memoria: %d -> %d items",
            remove_count,
            len(self._items) + remove_count,
            len(self._items),
        )

    def _validate_serializable(self, value: Any) -> None:
        """Valida que un valor sea JSON-serializable.

        Args:
            value: Valor a validar.

        Raises:
            TypeError: Si el valor no es serializable a JSON.
        """
        try:
            json.dumps(value)
        except (TypeError, ValueError) as exc:
            raise TypeError(
                f"El valor para memoria no es JSON-serializable: {exc}"
            ) from exc

    def _save(self) -> None:
        """Persiste el estado actual de la memoria a disco en JSON."""
        data: Dict[str, Dict[str, Any]] = {}
        for key, item in self._items.items():
            data[key] = {
                "key": item.key,
                "value": item.value,
                "access_count": item.access_count,
                "last_accessed": item.last_accessed,
                "importance_score": item.importance_score,
                "entities": item.entities,
                "semantic_tags": item.semantic_tags,
            }

        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except (OSError, IOError) as exc:
            logger.error(
                "StrategicMemory._save | No se pudo persistir a %s | WHAT=escritura_fallida | "
                "WHY=sistema_archivos | WHERE=_save | error=%s",
                self._path,
                exc,
            )

    def _load(self) -> None:
        """Carga el estado de memoria desde disco si el archivo existe.

        Si el archivo esta corrupto o no existe, la memoria inicia vacia
        y se registra una advertencia.
        """
        if not self._path.exists():
            return

        try:
            raw = self._path.read_text(encoding="utf-8")
            data = json.loads(raw)
            for key, item_data in data.items():
                self._items[key] = MemoryItem(**item_data)
            logger.info(
                "StrategicMemory._load | Cargados %d items desde %s",
                len(self._items),
                self._path,
            )
        except (json.JSONDecodeError, TypeError, KeyError) as exc:
            logger.warning(
                "StrategicMemory._load | Archivo corrupto o invalido: %s | "
                "WHAT=carga_fallida | WHY=json_invalido | WHERE=_load | error=%s",
                self._path,
                exc,
            )
            self._items.clear()
