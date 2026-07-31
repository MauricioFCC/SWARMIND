"""Success-Correlation Engine — Headroom "learn" (ADR-0033).

Aprende del fallo seguido de exito (no cataloga fallos): correlaciona pares
fallo->exito y deriva lecciones accionables inyectables en el contexto del
agente mediante bloques marcados ``swarmind:learn``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

START_MARKER = "<!-- swarmind:learn:start -->"
END_MARKER = "<!-- swarmind:learn:end -->"

_TEMPLATES: dict[str, str] = {
    "environment_fact": "'{succeeded}' (disponible; '{failed}' no)",
    "path_correction": "'{failed}' no existe; usa '{succeeded}' en su lugar",
    "search_scope": "Busca en '{succeeded}' no en '{failed}'",
    "command_pattern": "Usa '{succeeded}' en vez de '{failed}'",
    "known_large_file": "'{succeeded}' es un archivo grande, evita leerlo completo",
}
_DEFAULT_TEMPLATE = "Preferir '{succeeded}' sobre '{failed}'"


@dataclass
class Lesson:
    """Leccion accionable derivada de una correlacion fallo->exito.

    Attributes:
        category: Categoria de la leccion (path_correction, search_scope,
            command_pattern, environment_fact, known_large_file).
        lesson: Texto de la leccion derivado.
        failed_item: Elemento que fallo.
        succeeded_item: Elemento que funciono.
        source_session: Sesion de origen del aprendizaje.
    """

    category: str
    lesson: str
    failed_item: str
    succeeded_item: str
    source_session: str = ""

    def to_dict(self) -> dict[str, str]:
        """Serializa la leccion a dict.

        Returns:
            Dict con category, lesson, failed_item, succeeded_item y
            source_session.
        """
        return {
            "category": self.category,
            "lesson": self.lesson,
            "failed_item": self.failed_item,
            "succeeded_item": self.succeeded_item,
            "source_session": self.source_session,
        }

    def to_marker_block(self) -> str:
        """Genera el bloque de marcadores swarmind:learn para esta leccion.

        Returns:
            Bloque con marcadores de inicio y fin y la leccion como bullet.
        """
        return f"{START_MARKER}\n- [{self.category}] {self.lesson}\n{END_MARKER}"


class SuccessCorrelationEngine:
    """Motor de Success-Correlation: aprende del fallo seguido de exito.

    Almacena las lecciones en un dict con clave (category, failed_item,
    succeeded_item) para deduplicar y las inyecta idempotentemente en el
    contexto del agente.
    """

    def __init__(self) -> None:
        """Inicializa el motor sin lecciones.

        Returns:
            None.
        """
        self._lessons: dict[tuple[str, str, str], Lesson] = {}

    # ------------------------------------------------------------------
    # Learn
    # ------------------------------------------------------------------

    def learn(
        self,
        failed_item: str,
        succeeded_item: str,
        category: str = "path_correction",
        source_session: str = "",
    ) -> Lesson:
        """Crea y almacena una leccion derivando el texto segun la categoria.

        Args:
            failed_item: Elemento que fallo.
            succeeded_item: Elemento que funciono.
            category: Categoria de la leccion (ver plantillas conocidas).
            source_session: Sesion de origen del aprendizaje.

        Returns:
            La Lesson creada, o la existente si el par ya era conocido.
        """
        template = _TEMPLATES.get(category)
        if template is None:
            logger.warning(
                "WHAT: categoria '%s' desconocida. WHY: solo hay plantillas "
                "para %s. WHERE: learn(failed_item=%r, succeeded_item=%r)",
                category,
                sorted(_TEMPLATES),
                failed_item,
                succeeded_item,
            )
            template = _DEFAULT_TEMPLATE

        key = (category, failed_item, succeeded_item)
        existing = self._lessons.get(key)
        if existing is not None:
            return existing

        lesson = Lesson(
            category=category,
            lesson=template.format(failed=failed_item, succeeded=succeeded_item),
            failed_item=failed_item,
            succeeded_item=succeeded_item,
            source_session=source_session,
        )
        self._lessons[key] = lesson
        return lesson

    def get_lessons(self, category: str | None = None) -> list[Lesson]:
        """Devuelve las lecciones almacenadas, opcionalmente filtradas.

        Args:
            category: Categoria para filtrar; None devuelve todas.

        Returns:
            Lista de Lesson en orden de insercion.
        """
        if category is None:
            return list(self._lessons.values())
        return [lesson for lesson in self._lessons.values() if lesson.category == category]

    # ------------------------------------------------------------------
    # Apply to context
    # ------------------------------------------------------------------

    def apply_to_context(self, text: str) -> str:
        """Inyecta las lecciones en un bloque marcado swarmind:learn.

        Idempotente: si el texto ya contiene los marcadores de inicio y fin,
        solo se reemplaza el contenido entre ambos, preservando el resto del
        texto. Si no los contiene, el bloque completo se anade al final.

        Args:
            text: Contexto del agente a enriquecer.

        Returns:
            Texto con el bloque de lecciones, sin duplicados entre llamadas.
        """
        block = f"{START_MARKER}\n{self._build_bullets()}\n{END_MARKER}"
        start_idx = text.find(START_MARKER)
        end_idx = text.find(END_MARKER)
        if start_idx != -1 and end_idx != -1 and start_idx < end_idx:
            end_pos = end_idx + len(END_MARKER)
            return text[:start_idx] + block + text[end_pos:]
        if not text:
            return block
        return text.rstrip("\n") + "\n\n" + block

    def _build_bullets(self) -> str:
        """Construye los bullets de todas las lecciones para el bloque marcado.

        Returns:
            Bullets separados por salto de linea, en orden de insercion.
        """
        return "\n".join(
            f"- [{lesson.category}] {lesson.lesson}" for lesson in self._lessons.values()
        )

    # ------------------------------------------------------------------
    # Session trace correlation
    # ------------------------------------------------------------------

    def from_session_trace(self, trace: list[dict]) -> list[Lesson]:
        """Analiza un trace de sesion y deriva lecciones path_correction.

        Para cada accion fallida busca la misma accion con status 'succeeded'
        cuyo item sea el mas parecido (misma extension, mismo stem o mismo
        prefijo de directorios) y deriva la leccion con el primer componente
        de ruta que difiere.

        Args:
            trace: Lista de dicts con claves 'action', 'item', 'status' y
                'session'. Entradas malformadas se omiten con log.

        Returns:
            Lecciones derivadas del trace (tambien quedan almacenadas).
        """
        validas: list[dict] = []
        for entry in trace:
            normal = _normalize_entry(entry)
            if normal is None:
                continue  # motivo ya logueado en _normalize_entry
            validas.append(normal)

        fallidas = [e for e in validas if e["status"] == "failed"]
        exitosas = [e for e in validas if e["status"] == "succeeded"]
        lecciones: list[Lesson] = []
        for fallida in fallidas:
            mejor = _best_match(fallida["item"], [e["item"] for e in exitosas])
            if mejor is None:
                continue  # sin correlato exitoso parecido: no hay leccion
            failed_part, succeeded_part = _first_diff_component(fallida["item"], mejor)
            lecciones.append(
                self.learn(
                    failed_part,
                    succeeded_part,
                    category="path_correction",
                    source_session=fallida.get("session", ""),
                )
            )
        return lecciones

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def stats(self) -> dict:
        """Resume el total de lecciones por categoria.

        Returns:
            Dict con 'total' y un conteo por cada categoria presente.
        """
        result: dict[str, int] = {"total": len(self._lessons)}
        for lesson in self._lessons.values():
            result[lesson.category] = result.get(lesson.category, 0) + 1
        return result


# ===========================================================================
# Helpers de correlacion
# ===========================================================================


def _normalize_entry(entry: dict) -> dict | None:
    """Valida una entrada de trace de sesion y extrae las claves utiles.

    Args:
        entry: Entrada candidata con claves action/item/status/session.

    Returns:
        Dict normalizado o None (con log WHAT+WHY+WHERE) si faltan claves.
    """
    action = entry.get("action")
    item = entry.get("item")
    status = entry.get("status")
    if not action or not item or not status:
        logger.warning(
            "WHAT: entrada de trace incompleta. WHY: faltan claves "
            "action/item/status en %r. WHERE: from_session_trace()",
            entry,
        )
        return None
    return {
        "action": str(action),
        "item": str(item),
        "status": str(status),
        "session": entry.get("session", ""),
    }


def _best_match(failed_item: str, succeeded_items: list[str]) -> str | None:
    """Elige el item exitoso mas parecido al item fallido.

    Args:
        failed_item: Item que fallo.
        succeeded_items: Items que funcionaron para la misma accion.

    Returns:
        Item exitoso con mayor similitud, o None si ninguno supera el umbral
        de cero (no comparten extension, stem ni directorio).
    """
    best: str | None = None
    best_score = 0
    for candidate in succeeded_items:
        score = _item_similarity(failed_item, candidate)
        if score > best_score:
            best = candidate
            best_score = score
    if best_score <= 0:
        logger.debug(
            "WHAT: sin candidato exitoso parecido a '%s'. "
            "WHY: ninguno comparte extension, stem o directorio. "
            "WHERE: _best_match()",
            failed_item,
        )
        return None
    return best


def _item_similarity(a: str, b: str) -> int:
    """Puntua la similitud entre dos items de ruta.

    Args:
        a: Primer item.
        b: Segundo item.

    Returns:
        Puntuacion: +2 por extension igual, +2 por stem igual y +1 por cada
        directorio inicial comun.
    """
    score = 0
    pa, pb = Path(a), Path(b)
    if pa.suffix and pa.suffix == pb.suffix:
        score += 2
    if pa.stem and pa.stem == pb.stem:
        score += 2
    score += _common_leading_dirs(pa, pb)
    return score


def _common_leading_dirs(pa: Path, pb: Path) -> int:
    """Cuenta los directorios iniciales comunes entre dos rutas.

    Args:
        pa: Primera ruta.
        pb: Segunda ruta.

    Returns:
        Numero de componentes de directorio iniciales identicos.
    """
    dirs_a = list(pa.parts[:-1])
    dirs_b = list(pb.parts[:-1])
    count = 0
    for da, db in zip(dirs_a, dirs_b):
        if da != db:
            break
        count += 1
    return count


def _first_diff_component(failed_item: str, succeeded_item: str) -> tuple[str, str]:
    """Extrae el primer componente de ruta que difiere entre dos items.

    Args:
        failed_item: Item que fallo.
        succeeded_item: Item que funciono.

    Returns:
        Tupla (componente del item fallido, componente del item exitoso).
    """
    parts_f = Path(failed_item).parts
    parts_s = Path(succeeded_item).parts
    for pf, ps in zip(parts_f, parts_s):
        if pf != ps:
            return pf, ps
    return parts_f[-1], parts_s[-1]
