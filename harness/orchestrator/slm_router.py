"""
SlmRouter — SLM-first workers con escalación por confianza (ADR-0034).

Enruta subtareas de ejecución a modelos pequeños (SLM) cuando la tarea es
mecánica y verificable, reservando el modelo frontier para planning y
razonamiento abierto. Patrón "large model planning + SLM execution"
(RouteLLM UC Berkeley: 95% calidad con -85% costo).

Escalación por confianza: si el SLM responde con confianza < umbral, ESA
llamada se escala al frontier (nunca degrada silenciosamente la calidad).

Determinista: misma entrada -> misma decisión (temperature=0, sin random).
"""

from __future__ import annotations

from dataclasses import dataclass

# Tipos de tarea que un SLM resuelve con alta fiabilidad (95-99%):
# formato JSON, extracción, clasificación, validación de schema, resúmenes.
SLM_FRIENDLY_TASKS: frozenset[str] = frozenset({
    "extraction",
    "classification",
    "formatting",
    "schema_validation",
    "summarization",
    "slot_filling",
    "tool_call_format",
})

# Tipos que SIEMPRE requieren frontier (razonamiento abierto).
FRONTIER_ONLY_TASKS: frozenset[str] = frozenset({
    "planning",
    "synthesis",
    "reasoning",
    "code_review",
    "architecture",
    "security_audit",
    "debugging",
})


@dataclass
class _RouteStats:
    """Estadísticas acumuladas de enrutamiento."""
    slm_requests: int = 0
    frontier_requests: int = 0
    escalations: int = 0


class SlmRouter:
    """
    Router de ejecución SLM-first con escalación por confianza.

    Uso:
        router = SlmRouter(
            slm_backend=mi_slm_local,      # callable(payload) -> dict
            frontier_backend=mi_llm_api,   # callable(payload) -> dict
        )
        route = router.decide("extraction", difficulty=1)
        result = router.execute("extraction", 1, {"text": "..."})
    """

    def __init__(
        self,
        *,
        slm_backend=None,
        frontier_backend=None,
        confidence_threshold: float = 0.85,
        max_slm_difficulty: int = 2,
    ) -> None:
        """
        Inicializa el router.

        Args:
            slm_backend: callable(payload) -> dict con "confidence" y "result".
                None => todo se enruta a frontier (fallback seguro).
            frontier_backend: callable(payload) -> dict con "result".
            confidence_threshold: mínimo de confianza del SLM para aceptar su
                resultado sin escalar (0..1).
            max_slm_difficulty: dificultad máxima (escala DifficultyRouter
                0..4) que puede enrutarse a SLM.
        """
        self._slm_backend = slm_backend
        self._frontier_backend = frontier_backend
        self._confidence_threshold = float(confidence_threshold)
        self._max_slm_difficulty = int(max_slm_difficulty)
        self._stats = _RouteStats()

    # ------------------------------------------------------------------
    # Decisión
    # ------------------------------------------------------------------

    def decide(self, task_type: str, difficulty: int) -> str:
        """Decide la ruta: "slm" | "frontier".

        Reglas (política pura, independiente de la disponibilidad de backends;
        el fallback por backend ausente lo maneja execute()):
          1. Tareas FRONTIER_ONLY siempre -> frontier.
          2. Tareas no whitelisteadas -> frontier (default seguro).
          3. Dificultad > max_slm_difficulty -> frontier.
          4. Si no, -> slm.

        Args:
            task_type: tipo de tarea (ver SLM_FRIENDLY_TASKS).
            difficulty: nivel de dificultad 0..4 (DifficultyRouter).

        Returns:
            "slm" o "frontier".
        """
        if task_type in FRONTIER_ONLY_TASKS:
            return "frontier"
        if task_type not in SLM_FRIENDLY_TASKS:
            return "frontier"
        if difficulty > self._max_slm_difficulty:
            return "frontier"
        return "slm"

    # ------------------------------------------------------------------
    # Ejecución con escalación
    # ------------------------------------------------------------------

    def execute(
        self,
        task_type: str,
        difficulty: int,
        payload: dict,
    ) -> dict:
        """Ejecuta la tarea con la ruta decidida, escalando si es necesario.

        Args:
            task_type: tipo de tarea.
            difficulty: dificultad 0..4.
            payload: datos de entrada para el backend.

        Returns:
            Dict con route ("slm"|"frontier"), escalated (bool), y result
            (respuesta del backend elegido).

        Raises:
            RuntimeError: si la ruta requerida no tiene backend.
        """
        route = self.decide(task_type, difficulty)
        # Fallback seguro: ruta slm sin backend -> frontier (nunca explota).
        if route == "slm" and self._slm_backend is None:
            route = "frontier"
        if route == "slm":
            self._stats.slm_requests += 1
            slm_out = self._call(self._slm_backend, payload, "SLM")
            confidence = float(slm_out.get("confidence", 0.0))
            if confidence >= self._confidence_threshold:
                return {"route": "slm", "escalated": False, "result": slm_out}
            # Escalación por confianza: re-ejecutar en frontier.
            self._stats.escalations += 1
            self._stats.frontier_requests += 1
            frontier_out = self._call(self._frontier_backend, payload, "FRONTIER")
            return {"route": "frontier", "escalated": True, "result": frontier_out}

        self._stats.frontier_requests += 1
        frontier_out = self._call(self._frontier_backend, payload, "FRONTIER")
        return {"route": "frontier", "escalated": False, "result": frontier_out}

    # ------------------------------------------------------------------
    # Estadísticas
    # ------------------------------------------------------------------

    def stats(self) -> dict:
        """Resumen de tráfico para observabilidad (Golden Signals).

        Returns:
            Dict con slm_requests, frontier_requests, escalations, slm_ratio.
        """
        total = self._stats.slm_requests + self._stats.frontier_requests
        return {
            "slm_requests": self._stats.slm_requests,
            "frontier_requests": self._stats.frontier_requests,
            "escalations": self._stats.escalations,
            "slm_ratio": (
                self._stats.slm_requests / total
            ) if total else 0.0,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _call(backend, payload: dict, label: str) -> dict:
        """Invoca un backend y valida que devuelva dict.

        Args:
            backend: callable(payload) -> dict.
            payload: entrada.
            label: nombre del backend para el mensaje de error.

        Returns:
            Dict de respuesta.

        Raises:
            RuntimeError: si el backend es None o devuelve algo no-dict.
        """
        if backend is None:
            raise RuntimeError(
                f"WHAT: backend {label} no configurado. "
                f"WHY: la ruta requiere un backend y no se inyectó ninguno. "
                f"WHERE: _call() en slm_router.py."
            )
        out = backend(payload)
        if not isinstance(out, dict):
            raise TypeError(
                f"WHAT: backend {label} devolvió tipo inválido. "
                f"WHY: se esperaba dict, se obtuvo {type(out).__name__}. "
                f"WHERE: _call() en slm_router.py."
            )
        return out
