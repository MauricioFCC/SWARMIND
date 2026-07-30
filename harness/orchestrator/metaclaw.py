"""MetaClaw — Seleccion adaptativa de herramientas basada en meta-aprendizaje.

Aprende que herramienta es mejor para cada tipo de tarea basado en
resultados historicos (exito, latencia, costo).

El algoritmo central es un meta-aprendizaje contextual de tipo bandido
(contextual bandit) que:
  1. Clasifica cada tarea entrante en un perfil semantico (task_vector).
  2. Selecciona la herramienta con mayor expected reward dada esa tarea.
  3. Actualiza las creencias (posteriors) con cada resultado observado.
  4. Usa Thompson Sampling para balancear exploracion vs. explotacion.

Registra todas las decisiones y outcomes para analisis offline y
reduccion de sesgo (bias-aware feedback).

Basado en: MetaClaw (ADR-0010, S26) — arXiv:2603.17187.
Skill-driven fast adaptation + opportunistic policy optimization via RL
con process reward model.

Uso:
    metaclaw = MetaClaw()
    task = "generar_test_unitario"
    context = {"file_type": "python", "complexity": 0.7}
    selected = metaclaw.select_tool(task, context)
    result = metaclaw.record_outcome(task, context, selected, success=True, latency=1.2)
    best = metaclaw.get_best_tool(task)
"""

from __future__ import annotations

import logging
import math
import random
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Parametros del modelo Thompson Sampling
ALPHA_PRIOR: float = 1.0      # Prior alpha para distribucion Beta (exitos)
BETA_PRIOR: float = 1.0       # Prior beta para distribucion Beta (fallos)
EXPLORATION_NOISE: float = 0.05  # Ruido gaussiano para exploracion adicional

# Pesos para el calculo de reward compuesto
WEIGHT_SUCCESS: float = 0.50      # Peso del exito en el reward
WEIGHT_LATENCY: float = 0.25      # Peso de la latencia (inverso)
WEIGHT_COST: float = 0.15         # Peso del costo (inverso)
WEIGHT_CONFIDENCE: float = 0.10   # Peso de la confianza del agente

# Penalizaciones
LATENCY_PENALTY_THRESHOLD: float = 5.0  # segundos, por encima penaliza
COST_PENALTY_THRESHOLD: float = 100.0    # tokens, por encima penaliza

# Tamanos de ventana para统计
DEFAULT_WINDOW_SIZE: int = 100  # Ventana deslizante para metricas

# Dimension del vector de contexto para embedding de tareas
TASK_VECTOR_DIM: int = 16


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ToolRecord:
    """Registro de rendimiento historico de una herramienta.

    Attributes:
        tool_name: Identificador unico de la herramienta.
        total_calls: Numero total de invocaciones.
        successes: Numero de invocaciones exitosas.
        failures: Numero de invocaciones fallidas.
        total_latency: Suma acumulada de latencia (segundos).
        total_cost: Suma acumulada de costo (tokens).
        last_used: Timestamp de la ultima invocacion.
        task_types: Contador de tipos de tarea atendidos.
    """

    tool_name: str
    total_calls: int = 0
    successes: int = 0
    failures: int = 0
    total_latency: float = 0.0
    total_cost: float = 0.0
    last_used: float = 0.0
    task_types: dict[str, int] = field(default_factory=lambda: defaultdict(int))


@dataclass
class SelectionRecord:
    """Registro de una decision de seleccion de herramienta.

    Attributes:
        task_type: Tipo de tarea clasificado.
        context: Vector/contexto de la tarea.
        selected_tool: Herramienta elegida.
        success: Si la ejecucion fue exitosa.
        latency: Latencia de la ejecucion (segundos).
        cost: Costo en tokens.
        confidence: Confianza reportada por el agente.
        reward: Reward compuesto calculado.
        timestamp: Momento de la decision.
    """

    task_type: str
    context: dict[str, Any]
    selected_tool: str
    success: bool
    latency: float
    cost: float
    confidence: float = 0.0
    reward: float = 0.0
    timestamp: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# MetaClaw
# ---------------------------------------------------------------------------


class MetaClaw:
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

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register_tool(self, tool_name: str) -> None:
        """Registra una herramienta en el MetaClaw.

        WHAT: Anade una herramienta al conjunto de opciones disponibles.
        Si ya existe, no hace nada.
        WHY: El MetaClaw solo puede seleccionar entre herramientas
        registradas. El registro permite inicializar sus estadisticas.
        WHERE: Durante la inicializacion del sistema o al anadir una
        nueva herramienta.

        Args:
            tool_name: Identificador unico de la herramienta
                (ej: "gpt-4", "sandbox-python", "code-executor").

        Raises:
            ValueError: Si tool_name esta vacio o es solo espacios.
        """
        if not tool_name or not tool_name.strip():
            raise ValueError(
                f"WHAT: tool_name='{tool_name}' esta vacio. "
                f"WHY: Toda herramienta necesita un identificador valido. "
                f"WHERE: MetaClaw.register_tool"
            )

        with self._lock:
            if tool_name not in self._tool_records:
                self._tool_records[tool_name] = ToolRecord(tool_name=tool_name)
                # Indicar que no hay sesgo: prior uniforme
                logger.info("MetaClaw: herramienta '%s' registrada", tool_name)

    def select_tool(
        self,
        task_type: str,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Selecciona la mejor herramienta para una tarea usando meta-aprendizaje.

        WHAT: Usa Thompson Sampling con posteriors Beta para balancear
        exploracion y explotacion. Con probabilidad exploration_rate,
        explora aleatoriamente. Sino, selecciona la herramienta con
        mayor muestra del posterior.
        WHY: Thompson Sampling converge al optimo con garantias
        teoricas de regret sublineal, y maneja naturalmente la
        incertidumbre sobre herramientas nuevas.
        WHERE: Cada vez que el orquestador necesita delegar una tarea
        a una herramienta.

        Args:
            task_type: Tipo de tarea (ej: "code_generation",
                "test_generation", "analysis", "research").
            context: Diccionario con metadatos de la tarea
                (ej: {"lang": "python", "complexity": 0.8}).
                Puede ser None para tareas simples.

        Returns:
            Nombre de la herramienta seleccionada.

        Raises:
            RuntimeError: Si no hay herramientas registradas.
        """
        if context is None:
            context = {}

        with self._lock:
            if not self._tool_records:
                raise RuntimeError(
                    "WHAT: No hay herramientas registradas en MetaClaw. "
                    "WHY: No se puede seleccionar sin opciones disponibles. "
                    "WHERE: MetaClaw.select_tool. "
                    "SUGGEST: Registrar al menos una herramienta con register_tool()."
                )

            tool_names = list(self._tool_records.keys())

            # Registrar tipo de tarea
            self._known_task_types[task_type] += 1

            # Actualizar embedding de la tarea (aprendizaje incremental)
            self._update_task_embedding(task_type, context)

            # Decidir si explorar o explotar
            if random.random() < self._exploration_rate:
                selected = random.choice(tool_names)
                logger.debug(
                    "MetaClaw: exploracion -> herramienta='%s' para tarea='%s'",
                    selected, task_type,
                )
            else:
                # Thompson Sampling: muestrear del posterior de cada herramienta
                best_tool = tool_names[0]
                best_sample = float("-inf")

                for tool_name in tool_names:
                    alpha, beta = self._get_posterior(task_type, tool_name)
                    # Muestrear de Beta(alpha, beta)
                    sample = random.betavariate(alpha, beta)

                    # Agregar ruido de exploracion
                    sample += random.gauss(0, EXPLORATION_NOISE)

                    if sample > best_sample:
                        best_sample = sample
                        best_tool = tool_name

                selected = best_tool
                logger.debug(
                    "MetaClaw: explotacion -> herramienta='%s' "
                    "(sample=%.4f) para tarea='%s'",
                    selected, best_sample, task_type,
                )

            return selected

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

    def get_best_tool(self, task_type: str) -> str | None:
        """Obtiene la mejor herramienta para un tipo de tarea.

        Args:
            task_type: Tipo de tarea a consultar.

        Returns:
            Nombre de la herramienta con mayor expected reward, o None
            si no hay datos para ese tipo de tarea.
        """
        with self._lock:
            best: str | None = None
            best_score = float("-inf")

            for tool_name in self._tool_records:
                alpha, beta = self._get_posterior(task_type, tool_name)
                expected = alpha / max(alpha + beta, 1)

                if expected > best_score:
                    best_score = expected
                    best = tool_name

            return best

    def get_tool_stats(self, tool_name: str) -> dict[str, Any] | None:
        """Obtiene estadisticas detalladas de una herramienta.

        Args:
            tool_name: Nombre de la herramienta.

        Returns:
            Diccionario con: tool_name, total_calls, success_rate,
            avg_latency, avg_cost, last_used, task_types, o None
            si la herramienta no existe.
        """
        with self._lock:
            record = self._tool_records.get(tool_name)
            if record is None:
                return None

            return {
                "tool_name": record.tool_name,
                "total_calls": record.total_calls,
                "success_rate": (
                    record.successes / max(record.total_calls, 1)
                ),
                "avg_latency": (
                    record.total_latency / max(record.total_calls, 1)
                ),
                "avg_cost": (
                    record.total_cost / max(record.total_calls, 1)
                ),
                "last_used": record.last_used,
                "task_types": dict(record.task_types),
                "failures": record.failures,
                "successes": record.successes,
            }

    def get_task_performance(
        self,
        task_type: str,
    ) -> dict[str, Any] | None:
        """Obtiene el rendimiento agregado para un tipo de tarea.

        Args:
            task_type: Tipo de tarea a consultar.

        Returns:
            Diccionario con: task_type, total_calls, success_rate,
            avg_reward, tools_used, best_tool, o None si no hay datos.
        """
        with self._lock:
            tools_data = {}
            total_calls = 0
            total_rewards = 0.0
            reward_count = 0

            for tool_name in self._tool_records:
                hist = self._reward_history[task_type].get(tool_name, [])
                if not hist:
                    continue

                alpha, beta = self._get_posterior(task_type, tool_name)
                tools_data[tool_name] = {
                    "calls": len(hist),
                    "success_rate_estimate": alpha / max(alpha + beta, 1),
                    "avg_reward": sum(hist) / max(len(hist), 1),
                }
                total_calls += len(hist)
                total_rewards += sum(hist)
                reward_count += len(hist)

            if not tools_data:
                return None

            # Mejor herramienta por expected reward
            best_tool = max(
                tools_data.keys(),
                key=lambda t: tools_data[t]["success_rate_estimate"],
            )

            return {
                "task_type": task_type,
                "total_calls": total_calls,
                "tools_used": tools_data,
                "best_tool": best_tool,
                "avg_reward": total_rewards / max(reward_count, 1),
                "known_frequency": self._known_task_types.get(task_type, 0),
            }

    def get_all_stats(self) -> dict[str, Any]:
        """Retorna estadisticas completas del MetaClaw.

        Returns:
            Diccionario con: tools, task_types, total_selections,
            exploration_rate, learning_rate, posteriors size.
        """
        with self._lock:
            return {
                "tools": {
                    name: {
                        "total_calls": r.total_calls,
                        "success_rate": (
                            r.successes / max(r.total_calls, 1)
                        ),
                        "avg_latency": (
                            r.total_latency / max(r.total_calls, 1)
                        ),
                        "avg_cost": (
                            r.total_cost / max(r.total_calls, 1)
                        ),
                    }
                    for name, r in self._tool_records.items()
                },
                "task_types": dict(self._known_task_types),
                "total_selections": len(self._selection_history),
                "exploration_rate": self._exploration_rate,
                "learning_rate": self._learning_rate,
                "posterior_pairs": sum(
                    len(pts) for pts in self._posteriors.values()
                ),
                "known_tasks": len(self._known_task_types),
                "registered_tools": len(self._tool_records),
            }

    def reset_tool(self, tool_name: str) -> bool:
        """Resetea las estadisticas de una herramienta.

        WHAT: Elimina todos los datos y posteriors asociados a la
        herramienta. Vuelve a registrarla con prior uniforme.
        WHY: Util cuando una herramienta cambia de version o se
        detecta que sus estadisticas estan desactualizadas.
        WHERE: Despues de actualizar una herramienta.

        Args:
            tool_name: Nombre de la herramienta a resetear.

        Returns:
            True si se reseteo, False si no existia.
        """
        with self._lock:
            if tool_name not in self._tool_records:
                return False

            # Limpiar posteriors asociados
            for task_type in list(self._posteriors.keys()):
                self._posteriors[task_type].pop(tool_name, None)

            # Limpiar reward history
            for task_type in list(self._reward_history.keys()):
                self._reward_history[task_type].pop(tool_name, None)

            # Re-registrar
            self._tool_records[tool_name] = ToolRecord(tool_name=tool_name)

            logger.info("MetaClaw: herramienta '%s' reseteada", tool_name)
            return True

    # ------------------------------------------------------------------
    # Metodos internos
    # ------------------------------------------------------------------

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

    def get_selection_history(
        self,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Obtiene el historial de selecciones recientes.

        Args:
            limit: Maximo de entradas a retornar. Default: 50.

        Returns:
            Lista de diccionarios con datos de seleccion.
        """
        with self._lock:
            recent = self._selection_history[-limit:]
            return [
                {
                    "task_type": s.task_type,
                    "selected_tool": s.selected_tool,
                    "success": s.success,
                    "latency": s.latency,
                    "cost": s.cost,
                    "reward": round(s.reward, 4),
                    "timestamp": s.timestamp,
                }
                for s in recent
            ]
