"""MetaClaw — núcleo del meta-aprendiz (extraccion mecanica).

Clase publica MetaClaw: inicializacion del contextual bandit,
registro de outcomes y actualizacion de posteriors/embeddings.
La seleccion se hereda del mixin en el submódulo contiguo.
"""
from __future__ import annotations

import logging
import math
import threading
import time
from collections import defaultdict
from typing import Any

from .constants import (
    ALPHA_PRIOR,
    BETA_PRIOR,
    COST_PENALTY_THRESHOLD,
    DEFAULT_WINDOW_SIZE,
    LATENCY_PENALTY_THRESHOLD,
    TASK_VECTOR_DIM,
    WEIGHT_CONFIDENCE,
    WEIGHT_COST,
    WEIGHT_LATENCY,
    WEIGHT_SUCCESS,
)
from .models import SelectionRecord, ToolRecord
from .selection import _SelectionMixin

logger = logging.getLogger(__name__)

class MetaClaw(_SelectionMixin):
    """Selector adaptativo de herramientas con meta-aprendizaje.

    WHAT: Implementa un meta-aprendizaje contextual (contextual bandit)
    que aprende la herramienta optima para cada tipo de tarea basado en
    resultados historicos.
    WHY: No todas las herramientas son igualmente efectivas para cada
    tipo de tarea; la seleccion adaptativa mejora tasa de exito, reduce
    latencia y minimiza costo total.
    WHERE: Usado en el orquestador de agentes para elegir que herramienta
    (LLM, API, script, sandbox) ejecuta cada tarea.

    El algoritmo usa Thompson Sampling con distribuciones Beta para
    modelar la incertidumbre sobre la tasa de exito de cada
    herramienta. El reward compuesto integra exito, latencia, costo
    y confianza del agente.

    Uso:
        metaclaw = MetaClaw()

        # Registrar herramientas disponibles
        metaclaw.register_tool("gpt-4")
        metaclaw.register_tool("claude-3")
        metaclaw.register_tool("local-llama")

        # Seleccionar y registrar outcomes
        tool = metaclaw.select_tool("code_generation", {"lang": "rust"})
        metaclaw.record_outcome("code_generation", {"lang": "rust"}, tool,
                                success=True, latency=2.3, cost=450)
    """

    def __init__(
        self,
        alpha_prior: float = ALPHA_PRIOR,
        beta_prior: float = BETA_PRIOR,
        window_size: int = DEFAULT_WINDOW_SIZE,
        task_vector_dim: int = TASK_VECTOR_DIM,
        learning_rate: float = 0.1,
        exploration_rate: float = 0.15,
    ) -> None:
        """Inicializa el meta-aprendiz MetaClaw.

        Args:
            alpha_prior: Hiperparametro alpha de la distribucion Beta
                prior. Default: 1.0.
            beta_prior: Hiperparametro beta de la distribucion Beta
                prior. Default: 1.0.
            window_size: Tamano de la ventana deslizante para metricas
                de rendimiento. Default: 100.
            task_vector_dim: Dimension del vector de embedding de tarea.
                Default: 16.
            learning_rate: Tasa de aprendizaje para actualizacion de
                pesos. Default: 0.1.
            exploration_rate: Probabilidad de exploracion aleatoria.
                Default: 0.15.

        Raises:
            ValueError: Si alpha_prior <= 0, beta_prior <= 0,
                window_size < 10, task_vector_dim < 4,
                learning_rate fuera de [0, 1], o exploration_rate
                fuera de [0, 1].
        """
        if alpha_prior <= 0:
            raise ValueError(
                f"WHAT: alpha_prior={alpha_prior} <= 0. "
                f"WHY: El prior Beta requiere parametros positivos. "
                f"WHERE: MetaClaw.__init__"
            )
        if beta_prior <= 0:
            raise ValueError(
                f"WHAT: beta_prior={beta_prior} <= 0. "
                f"WHY: El prior Beta requiere parametros positivos. "
                f"WHERE: MetaClaw.__init__"
            )
        if window_size < 10:
            raise ValueError(
                f"WHAT: window_size={window_size} < 10. "
                f"WHY: La ventana deslizante debe tener al menos 10 muestras. "
                f"WHERE: MetaClaw.__init__"
            )
        if task_vector_dim < 4:
            raise ValueError(
                f"WHAT: task_vector_dim={task_vector_dim} < 4. "
                f"WHY: El vector de tarea debe tener al menos 4 dimensiones. "
                f"WHERE: MetaClaw.__init__"
            )
        if not 0.0 <= learning_rate <= 1.0:
            raise ValueError(
                f"WHAT: learning_rate={learning_rate} fuera de [0, 1]. "
                f"WHY: La tasa de aprendizaje debe estar normalizada. "
                f"WHERE: MetaClaw.__init__"
            )
        if not 0.0 <= exploration_rate <= 1.0:
            raise ValueError(
                f"WHAT: exploration_rate={exploration_rate} fuera de [0, 1]. "
                f"WHY: La tasa de exploracion debe estar normalizada. "
                f"WHERE: MetaClaw.__init__"
            )

        self._alpha_prior = alpha_prior
        self._beta_prior = beta_prior
        self._window_size = window_size
        self._task_vector_dim = task_vector_dim
        self._learning_rate = learning_rate
        self._exploration_rate = exploration_rate

        self._lock = threading.Lock()

        # {tool_name: ToolRecord}
        self._tool_records: dict[str, ToolRecord] = {}

        # {task_type: {tool_name: (alpha, beta)}} — posteriors por tarea
        self._posteriors: dict[str, dict[str, tuple[float, float]]] = (
            defaultdict(dict)
        )

        # {task_type: {tool_name: [reward_1, ...]}} — historial ventana
        self._reward_history: dict[str, dict[str, list[float]]] = (
            defaultdict(lambda: defaultdict(list))
        )

        # Vocabulario aprendido de tipos de tarea
        self._known_task_types: dict[str, int] = defaultdict(int)

        # Historial de selecciones
        self._selection_history: list[SelectionRecord] = []

        # Embeddings de tarea aprendidos (task_type -> vector)
        self._task_embeddings: dict[str, list[float]] = {}

        logger.info(
            "MetaClaw initialized (alpha=%.2f, beta=%.2f, "
            "window=%d, lr=%.3f, explore=%.2f)",
            alpha_prior, beta_prior,
            window_size, learning_rate, exploration_rate,
        )

    def record_outcome(
        self,
        task_type: str,
        context: dict[str, Any],
        tool_name: str,
        success: bool,
        latency: float,
        cost: float,
        confidence: float = 0.0,
    ) -> SelectionRecord:
        """Registra el resultado de una ejecucion y actualiza el modelo.

        WHAT: Actualiza los posteriors Beta (alpha/beta) de la
        combinacion task_type+tool_name, calcula reward compuesto, y
        almacena el historial para metrica offline.
        WHY: El meta-aprendizaje necesita retroalimentacion continua
        para mejorar sus predicciones y adaptarse a cambios en el
        rendimiento de las herramientas.
        WHERE: Inmediatamente despues de que una herramienta completa
        su ejecucion (exitosa o fallida).

        Args:
            task_type: Tipo de tarea ejecutada.
            context: Contexto original de la tarea.
            tool_name: Nombre de la herramienta utilizada.
            success: True si la ejecucion fue exitosa.
            latency: Latencia en segundos.
            cost: Costo en tokens consumidos.
            confidence: Confianza del agente [0, 1]. Default: 0.0.

        Returns:
            ``SelectionRecord`` con el resultado registrado.

        Raises:
            ValueError: Si tool_name no esta registrado, latency < 0,
                cost < 0, o confidence fuera de [0, 1].
        """
        # --- Validaciones ---
        if tool_name not in self._tool_records:
            raise ValueError(
                f"WHAT: tool_name='{tool_name}' no esta registrada. "
                f"WHY: Solo se pueden registrar outcomes de herramientas conocidas. "
                f"WHERE: MetaClaw.record_outcome. "
                f"REGISTERED: {list(self._tool_records.keys())}"
            )
        if latency < 0:
            raise ValueError(
                f"WHAT: latency={latency} < 0. "
                f"WHY: La latencia no puede ser negativa. "
                f"WHERE: MetaClaw.record_outcome"
            )
        if cost < 0:
            raise ValueError(
                f"WHAT: cost={cost} < 0. "
                f"WHY: El costo no puede ser negativo. "
                f"WHERE: MetaClaw.record_outcome"
            )
        if not 0.0 <= confidence <= 1.0:
            raise ValueError(
                f"WHAT: confidence={confidence} fuera de [0, 1]. "
                f"WHY: La confianza debe estar normalizada. "
                f"WHERE: MetaClaw.record_outcome"
            )

        # --- Calcular reward compuesto ---
        reward = self._compute_reward(success, latency, cost, confidence)

        with self._lock:
            # --- Actualizar ToolRecord ---
            record = self._tool_records[tool_name]
            record.total_calls += 1
            if success:
                record.successes += 1
            else:
                record.failures += 1
            record.total_latency += latency
            record.total_cost += cost
            record.last_used = time.time()
            record.task_types[task_type] += 1

            # --- Actualizar posterior Beta ---
            self._update_posterior(task_type, tool_name, success)

            # --- Actualizar reward history (ventana deslizante) ---
            hist = self._reward_history[task_type][tool_name]
            hist.append(reward)
            if len(hist) > self._window_size:
                hist.pop(0)

            # --- Crear SelectionRecord ---
            selection = SelectionRecord(
                task_type=task_type,
                context=dict(context),
                selected_tool=tool_name,
                success=success,
                latency=latency,
                cost=cost,
                confidence=confidence,
                reward=reward,
            )
            self._selection_history.append(selection)

            # Limitar historial de selecciones
            max_history = self._window_size * len(self._tool_records) * 2
            if len(self._selection_history) > max_history:
                self._selection_history = self._selection_history[-max_history:]

        logger.debug(
            "MetaClaw: outcome registrado (tarea='%s', tool='%s', "
            "success=%s, reward=%.4f, latency=%.2fs, cost=%.0f)",
            task_type, tool_name, success, reward, latency, cost,
        )

        return selection

    def _get_posterior(
        self,
        task_type: str,
        tool_name: str,
    ) -> tuple[float, float]:
        """Obtiene los parametros Beta del posterior para tarea+herramienta.

        Si no existe, retorna el prior uniforme.

        Args:
            task_type: Tipo de tarea.
            tool_name: Nombre de la herramienta.

        Returns:
            Tupla (alpha, beta) del posterior Beta.
        """
        posteriors_for_task = self._posteriors.get(task_type, {})
        return posteriors_for_task.get(
            tool_name, (self._alpha_prior, self._beta_prior),
        )

    def _update_posterior(
        self,
        task_type: str,
        tool_name: str,
        success: bool,
    ) -> None:
        """Actualiza el posterior Beta con un nuevo outcome.

        Args:
            task_type: Tipo de tarea.
            tool_name: Nombre de la herramienta.
            success: True si fue exitoso, False si fallo.
        """
        alpha, beta = self._get_posterior(task_type, tool_name)

        if success:
            alpha += self._learning_rate
        else:
            beta += self._learning_rate

        self._posteriors[task_type][tool_name] = (alpha, beta)

    def _update_task_embedding(
        self,
        task_type: str,
        context: dict[str, Any],
    ) -> None:
        """Actualiza incrementalmente el embedding de un tipo de tarea.

        Los embeddings se construyen a partir del contexto de la tarea
        usando caracteristicas numericas y codificacion one-hot
        simplificada de atributos categoricos.

        Args:
            task_type: Tipo de tarea.
            context: Contexto de la tarea con metadatos.
        """
        if task_type not in self._task_embeddings:
            # Inicializar embedding
            self._task_embeddings[task_type] = [0.0] * self._task_vector_dim

        embedding = self._task_embeddings[task_type]

        # Extraer caracteristicas del contexto
        features = []
        for key, value in context.items():
            if isinstance(value, (int, float)):
                features.append(float(value))
            elif isinstance(value, str):
                # Hash a un valor en [0, 1]
                h = hash(f"{key}:{value}") % 10000
                features.append(h / 10000.0)

        # Mezclar features en el embedding (promedio movil)
        if features:
            for i in range(min(len(features), self._task_vector_dim)):
                embedding[i] = (
                    0.9 * embedding[i] + 0.1 * features[i]
                )

    @staticmethod
    def _compute_reward(
        success: bool,
        latency: float,
        cost: float,
        confidence: float,
    ) -> float:
        """Calcula el reward compuesto de una ejecucion.

        Formula:
            reward = w_s * success + w_l * latency_score
                     + w_c * cost_score + w_conf * confidence

        Donde:
            - success: 1.0 si exito, 0.0 si fallo.
            - latency_score: exp(-latency / threshold).
            - cost_score: exp(-cost / threshold).
            - confidence: valor directo [0, 1].

        Args:
            success: Indicador de exito.
            latency: Latencia en segundos.
            cost: Costo en tokens.
            confidence: Confianza del agente [0, 1].

        Returns:
            Reward compuesto en [0, 1].
        """
        success_term = 1.0 if success else 0.0

        # Latencia: penalizacion exponencial
        latency_score = math.exp(-latency / max(LATENCY_PENALTY_THRESHOLD, 0.1))

        # Costo: penalizacion exponencial
        cost_score = math.exp(-cost / max(COST_PENALTY_THRESHOLD, 0.1))

        reward = (
            WEIGHT_SUCCESS * success_term
            + WEIGHT_LATENCY * latency_score
            + WEIGHT_COST * cost_score
            + WEIGHT_CONFIDENCE * confidence
        )

        return min(max(reward, 0.0), 1.0)
