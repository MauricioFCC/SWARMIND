"""Constantes del AdaptivePlanner (extraidas tal cual del modulo original)."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Umbrales para decisión de re-planificar
# ---------------------------------------------------------------------------
REPLAN_FAILURE_RATE = 0.5       # Si >50% de subtasks fallan → re-plan
REPLAN_STALLED_LEVELS = 2       # Si 2+ niveles seguidos sin progreso → re-plan
REPLAN_MIN_SUBTASKS = 1         # Mínimo subtasks en un plan

# Modos de plan
MODE_SINGLE_AGENT = "single_agent"
MODE_SEQUENTIAL = "sequential"
MODE_PARALLEL = "parallel"
MODE_HYBRID = "hybrid"          # Mezcla de sequential + parallel

# PSMAS: Fases angulares por agente (grados)
PHASE_BUILDER = 0.0      # Siempre activo
PHASE_SCIENTIST = 120.0  # Fase de investigación/análisis
PHASE_GUARDIAN = 240.0   # Fase de revisión/calidad

# Ventana angular por defecto para activación (grados)
PSMAS_DEFAULT_WINDOW = 60.0

# Umbral de agentes para activar phase scheduling
PSMAS_MIN_AGENTS = 3

# Agentes siempre activos (fase 0)
ALWAYS_ACTIVE_AGENTS = {"builder", "planner", "coordinator", "orchestrator"}
