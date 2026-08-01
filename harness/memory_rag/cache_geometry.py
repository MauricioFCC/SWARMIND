"""
CacheGeometry — Cache Geometry Discipline (ADR-0034).

Reordena bloques de prompt para maximizar el prefix-cache del provider:
  - Bloques ESTÁTICOS (instrucciones, skills, constantes) al INICIO.
  - Bloques DINÁMICOS (contexto de tarea, timestamps, UUIDs) al FINAL.

La regla de oro: el prefijo debe ser idéntico byte a byte entre llamadas
consecutivas. Si el contenido variable aparece temprano, el cache se invalida
silenciosamente y el provider cobra prefill completo (Zylos 2026: 87.4% hit
rate con geometría correcta vs 10-20% con contenido variable temprano).

Incluye medición: hash del prefijo estático para detectar invalidación.
"""

from __future__ import annotations

import hashlib
import re

# Marcadores que hacen a un bloque dinámico (cambia entre llamadas).
_DYNAMIC_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"\{\{.*?\}\}"),            # plantillas {{var}}
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),  # fechas ISO
    re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}"),  # timestamps
    re.compile(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        re.IGNORECASE,
    ),                                     # UUIDs
    re.compile(r"\b\d{10,}\b"),            # timestamps epoch / ids numéricos
)


class CacheGeometry:
    """
    Reordenador y medidor de geometría de cache.

    Uso:
        geo = CacheGeometry()
        blocks = ["Contexto: {{tarea}}", "## Instrucciones", "Reglas"]
        prompt = geo.reorder(blocks)          # estáticos primero
        h = geo.static_prefix_hash(blocks)    # detectar invalidación
    """

    def classify(self, text: str) -> str:
        """Clasifica un bloque como "static" o "dynamic".

        Args:
            text: contenido del bloque.

        Returns:
            "static" si no contiene marcadores variables; "dynamic" si cambia
            entre llamadas (plantillas, fechas, UUIDs, timestamps).
        """
        for pattern in _DYNAMIC_PATTERNS:
            if pattern.search(text):
                return "dynamic"
        return "static"

    def reorder(self, blocks: list[str]) -> list[str]:
        """Reordena bloques: estáticos primero, dinámicos después.

        Preserva el contenido completo (solo cambia el orden) y mantiene el
        orden relativo dentro de cada grupo.

        Args:
            blocks: lista de bloques de texto del prompt.

        Returns:
            Lista reordenada con todos los bloques estáticos al inicio.
        """
        statics = [b for b in blocks if self.classify(b) == "static"]
        dynamics = [b for b in blocks if self.classify(b) == "dynamic"]
        return statics + dynamics

    def static_prefix(self, blocks: list[str]) -> list[str]:
        """Retorna solo los bloques estáticos (el prefijo cacheable)."""
        return [b for b in blocks if self.classify(b) == "static"]

    def static_prefix_hash(self, blocks: list[str]) -> str:
        """Hash SHA-256 del prefijo estático concatenado.

        Sirve para detectar invalidación silenciosa: si el hash cambia entre
        requests repetidas, el provider no puede reusar el cache.

        Args:
            blocks: bloques del prompt.

        Returns:
            Hex digest SHA-256 del prefijo estático.
        """
        prefix = "\n".join(self.static_prefix(blocks))
        return hashlib.sha256(prefix.encode("utf-8")).hexdigest()

    def report(self, requests: list[dict]) -> dict:
        """Reporte de geometría sobre una serie de requests.

        Args:
            requests: lista de dicts con clave "blocks" (list[str]).

        Returns:
            Dict con total_requests, static_prefix_changes (cantidad de veces
            que el hash del prefijo cambió entre requests consecutivas) y
            prefix_changed (bool si hubo algún cambio).
        """
        changes = 0
        prev_hash: str | None = None
        for req in requests:
            current_hash = self.static_prefix_hash(req.get("blocks", []))
            if prev_hash is not None and current_hash != prev_hash:
                changes += 1
            prev_hash = current_hash
        return {
            "total_requests": len(requests),
            "static_prefix_changes": changes,
            "prefix_changed": changes > 0,
        }
