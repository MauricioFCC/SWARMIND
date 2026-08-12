"""Constantes de MetaClaw (extraccion mecanica)."""

ALPHA_PRIOR: float = 1.0      # Prior alpha para distribucion Beta (exitos)

BETA_PRIOR: float = 1.0       # Prior beta para distribucion Beta (fallos)

EXPLORATION_NOISE: float = 0.05  # Ruido gaussiano para exploracion adicional

WEIGHT_SUCCESS: float = 0.50      # Peso del exito en el reward

WEIGHT_LATENCY: float = 0.25      # Peso de la latencia (inverso)

WEIGHT_COST: float = 0.15         # Peso del costo (inverso)

WEIGHT_CONFIDENCE: float = 0.10   # Peso de la confianza del agente

LATENCY_PENALTY_THRESHOLD: float = 5.0  # segundos, por encima penaliza

COST_PENALTY_THRESHOLD: float = 100.0    # tokens, por encima penaliza

DEFAULT_WINDOW_SIZE: int = 100  # Ventana deslizante para metricas

TASK_VECTOR_DIM: int = 16
