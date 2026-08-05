"""TokenBudgetManager — Gestion de presupuesto de tokens por sesion."""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any

import yaml

from harness.memory_rag.token_budget import (
    DEFAULT_AGENT_BUDGET,
    DEFAULT_SESSION_BUDGET,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes de configuracion (ADR-0040 H6)
# ---------------------------------------------------------------------------

# Ruta por defecto del SSOT de budgets, relativa al repo root (SWARMIND/).
DEFAULT_TOKEN_BUDGETS_PATH = (
    Path(__file__).resolve().parent.parent.parent / ".opencode" / "config" / "token_budgets.yaml"
)

# Umbral de compresion por defecto (mismo valor que defaults.compression_threshold del YAML).
DEFAULT_COMPRESSION_THRESHOLD = 0.85

# Nivel de compresion neutro para roles sin configuracion explicita.
DEFAULT_COMPRESSION_LEVEL = "none"


def load_yaml(path: str | Path) -> dict[str, Any]:
    """Carga un archivo YAML de configuracion.

    WHAT: Lee el archivo en ``path`` (UTF-8) y retorna su contenido como
    un diccionario plano.
    WHY: Centralizar el parsing YAML evita duplicar la logica en cada
    consumidor y garantiza un unico punto de error con contexto WHAT+WHY+WHERE.
    WHERE: ``TokenBudgetManager`` — carga del SSOT token_budgets.yaml.

    Args:
        path: Ruta del archivo YAML.

    Returns:
        Contenido del YAML como dict.

    Raises:
        FileNotFoundError: Si el archivo no existe.
        TypeError: Si el contenido no es un mapping plano.
        ValueError: Si el YAML esta mal formado.
    """
    yaml_path = Path(path)
    if not yaml_path.is_file():
        raise FileNotFoundError(
            f"WHAT: No se encontro el archivo YAML '{yaml_path}'. "
            f"WHY: El SSOT de budgets debe existir para cargar configuracion. "
            f"WHERE: load_yaml()"
        )
    try:
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(
            f"WHAT: El YAML '{yaml_path}' esta mal formado ({exc}). "
            f"WHY: Un SSOT corrupto degradaria silenciosamente los budgets. "
            f"WHERE: load_yaml()"
        ) from exc
    if not isinstance(data, dict):
        raise TypeError(
            f"WHAT: El YAML '{yaml_path}' no contiene un mapping en la raiz "
            f"(tipo: {type(data).__name__}). "
            f"WHY: El SSOT de budgets debe ser un dict de secciones. "
            f"WHERE: load_yaml()"
        )
    return data


class TokenBudgetManager:
    """
    Gestiona el presupuesto de tokens por sesion de agente.

    WHAT: Realiza seguimiento del uso de tokens por sesion, permitiendo
    consultar tokens restantes y resetear presupuestos.
    WHY: Las sesiones multi-agente necesitan control centralizado de
    tokens para evitar que un agente consuma todo el presupuesto.
    WHERE: Usado por el gateway y el orquestador de agentes para
    gestionar el consumo de tokens por sesion.

    Desde ADR-0040 H6, ademas carga el SSOT ``.opencode/config/token_budgets.yaml``
    y expone budgets por rol (role_budgets), nivel de compresion
    (compression_level) y umbral de compresion (compression_threshold).
    Si el YAML no existe, opera con las constantes historicas
    (DEFAULT_AGENT_BUDGET / DEFAULT_SESSION_BUDGET).

    Diferencia con ``BudgetManager`` (token_budget.py):
    - ``BudgetManager`` maneja pools con prioridades y redistribucion.
    - ``TokenBudgetManager`` es un tracker ligero de uso por sesion + SSOT.

    Uso:
        manager = TokenBudgetManager(default_budget=4000)
        manager.track_usage("session-1", 150)
        remaining = manager.get_remaining("session-1")
        manager.reset_session("session-1")
        budget = manager.get_agent_budget("guardian")   # 2048 (SSOT)
        level = manager.get_compression_level("guardian")  # 'high'
    """

    def __init__(
        self,
        default_budget: int = 4000,
        max_sessions: int = 100,
        yaml_path: str | Path | None = None,
    ) -> None:
        """
        Inicializa el TokenBudgetManager.

        Args:
            default_budget: Presupuesto por defecto para nuevas sesiones.
                Default: 4000 tokens.
            max_sessions: Maximo de sesiones activas simultaneas.
                Cuando se excede, se elimina la sesion mas antigua.
                Default: 100.
            yaml_path: Ruta del SSOT de budgets (token_budgets.yaml).
                Default: ``.opencode/config/token_budgets.yaml`` relativo al
                repo root. Si el archivo no existe, el manager opera con las
                constantes historicas.

        Raises:
            ValueError: Si default_budget < 64, max_sessions < 1, o el YAML
                existe pero esta mal formado o contiene budgets invalidos.
            TypeError: Si el YAML tiene secciones con tipos incorrectos.
        """
        if default_budget < 64:
            raise ValueError(
                f"WHAT: default_budget={default_budget} es demasiado bajo. "
                f"WHY: Una sesion necesita al menos 64 tokens. "
                f"WHERE: TokenBudgetManager.__init__"
            )
        if max_sessions < 1:
            raise ValueError(
                f"WHAT: max_sessions={max_sessions} debe ser >= 1. "
                f"WHY: Debe haber al menos 1 sesion activa. "
                f"WHERE: TokenBudgetManager.__init__"
            )

        self._default_budget = default_budget
        self._max_sessions = max_sessions

        # {session_id: (budget_total, tokens_used, timestamp)}
        self._sessions: dict[str, tuple[int, int, float]] = {}
        self._lock = threading.Lock()

        # Estado cargado del SSOT (ADR-0040 H6)
        self._budgets_path: Path | None = None
        self._role_budgets: dict[str, dict[str, Any]] = {}
        self._base_budget: int = DEFAULT_AGENT_BUDGET
        self._session_budget: int = DEFAULT_SESSION_BUDGET
        self._compression_threshold: float = DEFAULT_COMPRESSION_THRESHOLD
        self._yaml_loaded = False

        self._load_budget_config(Path(yaml_path) if yaml_path is not None else DEFAULT_TOKEN_BUDGETS_PATH)

        logger.info(
            "TokenBudgetManager initialized (budget=%d, max_sessions=%d, yaml=%s)",
            default_budget, max_sessions, self._budgets_path or "none",
        )

    # ------------------------------------------------------------------
    # SSOT: carga de token_budgets.yaml (ADR-0040 H6)
    # ------------------------------------------------------------------

    def _load_budget_config(self, path: Path) -> None:
        """Carga el SSOT de budgets por rol.

        WHAT: Lee ``token_budgets.yaml`` y extrae defaults, role_budgets y
        session_budget; valida que los budgets sean enteros positivos.
        WHY: El YAML es la unica fuente (SSOT) de presupuestos; el runtime
        debe aplicarlos en vez del flat 4000 historico.
        WHERE: ``TokenBudgetManager.__init__`` — una vez por instancia.

        Si el archivo no existe, se conserva el comportamiento historico
        (constantes DEFAULT_AGENT_BUDGET / DEFAULT_SESSION_BUDGET).

        Raises:
            TypeError: Si role_budgets o una entrada de rol no es un mapping.
            ValueError: Si el YAML existe pero tiene budgets invalidos.
        """
        if not path.is_file():
            logger.info(
                "TokenBudgetManager: YAML '%s' no existe; usando constantes historicas "
                "(agent=%d, session=%d)",
                path, DEFAULT_AGENT_BUDGET, DEFAULT_SESSION_BUDGET,
            )
            return

        data = load_yaml(path)
        defaults = data.get("defaults") or {}
        role_budgets = data.get("role_budgets") or {}
        if not isinstance(role_budgets, dict):
            raise TypeError(
                f"WHAT: role_budgets en '{path}' no es un mapping "
                f"(tipo: {type(role_budgets).__name__}). "
                f"WHY: El SSOT requiere role_budgets como dict de roles. "
                f"WHERE: TokenBudgetManager._load_budget_config"
            )

        base_budget = defaults.get("base_budget", DEFAULT_AGENT_BUDGET)
        session_budget = data.get("session_budget", DEFAULT_SESSION_BUDGET)
        threshold = defaults.get("compression_threshold", DEFAULT_COMPRESSION_THRESHOLD)
        self._validate_budget("defaults.base_budget", base_budget)
        self._validate_budget("session_budget", session_budget)
        for role, spec in role_budgets.items():
            if not isinstance(spec, dict):
                raise TypeError(
                    f"WHAT: role_budgets.{role} no es un mapping "
                    f"(tipo: {type(spec).__name__}). "
                    f"WHY: Cada rol declara budget, compression_level e include_principles. "
                    f"WHERE: TokenBudgetManager._load_budget_config"
                )
            self._validate_budget(f"role_budgets.{role}.budget", spec.get("budget"))

        self._base_budget = int(base_budget)
        self._session_budget = int(session_budget)
        self._compression_threshold = float(threshold)
        self._role_budgets = role_budgets
        self._budgets_path = path
        self._yaml_loaded = True
        logger.info(
            "TokenBudgetManager: SSOT '%s' cargado (base=%d, session=%d, threshold=%.2f, roles=%d)",
            path, self._base_budget, self._session_budget, self._compression_threshold,
            len(self._role_budgets),
        )

    @staticmethod
    def _validate_budget(label: str, value: Any) -> None:
        """Valida que un budget sea un entero positivo.

        WHAT: Rechaza budgets no enteros, booleanos o menores a 64 tokens.
        WHY: Budgets invalidos causarian pools con cero tokens o
        comportamiento impredecible en el runtime.
        WHERE: ``TokenBudgetManager._load_budget_config`` — por cada campo.

        Raises:
            TypeError: Si el budget no es un entero.
            ValueError: Si el budget es menor a 64 tokens.
        """
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(
                f"WHAT: {label}={value!r} debe ser un entero. "
                f"WHY: Los budgets se expresan en tokens enteros. "
                f"WHERE: TokenBudgetManager._validate_budget"
            )
        if value < 64:
            raise ValueError(
                f"WHAT: {label}={value} es demasiado bajo. "
                f"WHY: Un agente necesita al menos 64 tokens. "
                f"WHERE: TokenBudgetManager._validate_budget"
            )

    # ------------------------------------------------------------------
    # API SSOT: budgets por rol (ADR-0040 H6)
    # ------------------------------------------------------------------

    def get_agent_budget(self, agent_name: str) -> int:
        """Retorna el budget de tokens para un agente.

        WHAT: Budget declarado en ``role_budgets[agent].budget`` o, si el rol
        no esta declarado, ``defaults.base_budget`` del SSOT.
        WHY: Cada rol tiene un presupuesto diferencial (ADR-0040 H6) en
        lugar del flat 4000 historico.
        WHERE: Runtime de orquestacion — presupuesto por rol.

        Args:
            agent_name: Nombre del rol/agente (ej. 'guardian').

        Returns:
            Tokens asignados al agente.
        """
        role_budget = self.get_role_budget(agent_name)
        if role_budget is not None:
            return role_budget
        return self._base_budget

    def get_role_budget(self, agent_name: str) -> int | None:
        """Retorna el budget declarado explicitamente para un rol.

        WHAT: ``role_budgets[agent].budget`` o None si el rol no esta
        declarado en el SSOT.
        WHY: El integrador (BudgetManager) necesita distinguir rol conocido
        de rol desconocido para conservar el default historico.
        WHERE: ``harness.memory_rag.token_budget.BudgetManager.register_agent``.

        Args:
            agent_name: Nombre del rol/agente.

        Returns:
            Budget declarado, o None si no hay entrada para el rol.
        """
        role = self._role_budgets.get(agent_name)
        if role is None:
            return None
        return int(role["budget"])

    def get_session_budget(self) -> int:
        """Retorna el presupuesto por sesion del SSOT.

        WHAT: ``session_budget`` del YAML si esta declarado; si no,
        DEFAULT_SESSION_BUDGET (16000).
        WHY: El tope de sesion limita el consumo agregado multi-agente.
        WHERE: Orquestacion — validacion de sesion.

        Returns:
            Presupuesto de tokens por sesion.
        """
        return self._session_budget

    def get_compression_level(self, agent_name: str) -> str:
        """Retorna el nivel de compresion declarado para un agente.

        WHAT: ``role_budgets[agent].compression_level`` (low|medium|high)
        o 'none' si el rol no esta declarado.
        WHY: Roles ligeros (guardian, token-budget-auditor) usan compresion
        agresiva; scientist preserva detalle (low).
        WHERE: Compresion de contexto previa al envio al LLM.

        Args:
            agent_name: Nombre del rol/agente.

        Returns:
            Nivel de compresion ('none', 'low', 'medium', 'high').
        """
        role = self._role_budgets.get(agent_name)
        if role is None:
            return DEFAULT_COMPRESSION_LEVEL
        return str(role.get("compression_level", DEFAULT_COMPRESSION_LEVEL))

    def get_threshold(self) -> float:
        """Retorna el umbral de compresion del SSOT.

        WHAT: ``defaults.compression_threshold`` del YAML (0.85 por defecto).
        WHY: Define cuando se activa la compresion de contexto.
        WHERE: Compresion de contexto — decision de activacion.

        Returns:
            Umbral de compresion (0.0 - 1.0).
        """
        return self._compression_threshold

    def has_budget_config(self) -> bool:
        """Indica si el SSOT fue cargado exitosamente.

        WHAT: True si token_budgets.yaml fue cargado; False si se opera
        con constantes historicas.
        WHY: Los integradores pueden decidir logging o metricas segun la
        fuente de verdad activa.
        WHERE: Diagnostico y telemetria del runtime.

        Returns:
            True si el YAML fue cargado, False en caso contrario.
        """
        return self._yaml_loaded

    # ------------------------------------------------------------------
    # Seguimiento de sesiones (comportamiento historico)
    # ------------------------------------------------------------------

    def track_usage(self, session_id: str, tokens: int) -> dict[str, Any]:
        """
        Registra uso de tokens para una sesion.

        WHAT: Incrementa el contador de tokens usados para la sesion.
        Si la sesion no existe, se crea con el presupuesto por defecto.
        WHY: Mantener un registro centralizado de consumo permite
        detectar cuando una sesion se acerca a su limite.
        WHERE: Despues de cada llamada a LLM, registrar tokens consumidos.

        Args:
            session_id: Identificador unico de la sesion.
            tokens: Cantidad de tokens a registrar (debe ser > 0).

        Returns:
            Diccionario con: session_id, total_budget, used, remaining.

        Raises:
            ValueError: Si tokens <= 0.
        """
        if tokens <= 0:
            raise ValueError(
                f"WHAT: tokens={tokens} debe ser > 0. "
                f"WHY: No se pueden registrar 0 o tokens negativos. "
                f"WHERE: TokenBudgetManager.track_usage"
            )

        with self._lock:
            # Crear sesion si no existe
            if session_id not in self._sessions:
                # Gestion de maximo de sesiones: eliminar la mas antigua
                if len(self._sessions) >= self._max_sessions:
                    oldest = min(self._sessions.items(), key=lambda x: x[1][2])
                    del self._sessions[oldest[0]]
                    logger.debug(
                        "TokenBudgetManager: sesion mas antigua '%s' eliminada "
                        "(max_sessions=%d alcanzado)",
                        oldest[0], self._max_sessions,
                    )

                self._sessions[session_id] = (self._default_budget, 0, time.time())
                logger.debug(
                    "TokenBudgetManager: nueva sesion '%s' creada (budget=%d)",
                    session_id, self._default_budget,
                )

            budget, used, created = self._sessions[session_id]
            used += tokens
            self._sessions[session_id] = (budget, used, created)

            remaining = max(0, budget - used)

            logger.debug(
                "TokenBudgetManager: sesion='%s' usado=%d/%d (%.1f%%)",
                session_id, used, budget,
                (used / max(budget, 1)) * 100,
            )

            return {
                "session_id": session_id,
                "total_budget": budget,
                "used": used,
                "remaining": remaining,
                "exhausted": remaining <= 0,
            }

    def get_remaining(self, session_id: str) -> int:
        """
        Obtiene tokens restantes para una sesion.

        Args:
            session_id: Identificador de la sesion.

        Returns:
            Tokens restantes (0 si la sesion no existe o esta agotada).
        """
        with self._lock:
            entry = self._sessions.get(session_id)
            if entry is None:
                return 0
            budget, used, _ = entry
            return max(0, budget - used)

    def get_usage(self, session_id: str) -> dict[str, Any] | None:
        """
        Obtiene el estado completo de uso de una sesion.

        Args:
            session_id: Identificador de la sesion.

        Returns:
            Diccionario con session_id, total_budget, used, remaining,
            usage_pct, exhausted, o None si la sesion no existe.
        """
        with self._lock:
            entry = self._sessions.get(session_id)
            if entry is None:
                return None
            budget, used, _ = entry
            remaining = max(0, budget - used)
            return {
                "session_id": session_id,
                "total_budget": budget,
                "used": used,
                "remaining": remaining,
                "usage_pct": round((used / max(budget, 1)) * 100, 1),
                "exhausted": remaining <= 0,
            }

    def reset_session(self, session_id: str) -> bool:
        """
        Resetea el presupuesto de una sesion (elimina su registro).

        WHAT: Elimina la sesion del registro de uso, liberando su
        presupuesto para futuras sesiones.
        WHY: Cuando una sesion termina, su presupuesto debe liberarse
        para evitar acumulacion de sesiones inactivas.
        WHERE: Al finalizar una sesion de agente o al hacer cleanup.

        Args:
            session_id: Identificador de la sesion a resetear.

        Returns:
            True si la sesion existia y fue eliminada, False si no.
        """
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                logger.debug("TokenBudgetManager: sesion '%s' resetada", session_id)
                return True
            return False

    def set_budget(self, session_id: str, new_budget: int) -> bool:
        """
        Actualiza el presupuesto total de una sesion existente.

        Args:
            session_id: Identificador de la sesion.
            new_budget: Nuevo presupuesto total (> 0).

        Returns:
            True si se actualizo, False si la sesion no existe.

        Raises:
            ValueError: Si new_budget <= 0.
        """
        if new_budget <= 0:
            raise ValueError(
                f"WHAT: new_budget={new_budget} debe ser > 0. "
                f"WHY: El presupuesto debe ser positivo. "
                f"WHERE: TokenBudgetManager.set_budget"
            )

        with self._lock:
            entry = self._sessions.get(session_id)
            if entry is None:
                return False
            _, used, created = entry
            self._sessions[session_id] = (new_budget, used, created)
            logger.debug(
                "TokenBudgetManager: sesion '%s' presupuesto actualizado "
                "a %d (used=%d)",
                session_id, new_budget, used,
            )
            return True

    def get_all_sessions(self) -> dict[str, dict[str, Any]]:
        """
        Obtiene el estado de todas las sesiones activas.

        Returns:
            Diccionario {session_id: {total_budget, used, remaining, usage_pct}}.
        """
        with self._lock:
            return {
                sid: {
                    "total_budget": budget,
                    "used": used,
                    "remaining": max(0, budget - used),
                    "usage_pct": round((used / max(budget, 1)) * 100, 1),
                }
                for sid, (budget, used, _) in self._sessions.items()
            }

    def get_stats(self) -> dict[str, Any]:
        """
        Retorna estadisticas del gestor de presupuesto.

        Returns:
            Diccionario con: active_sessions, total_budget_allocated,
            total_used, total_remaining, default_budget.
        """
        with self._lock:
            total_budget = sum(b for b, _, _ in self._sessions.values())
            total_used = sum(u for _, u, _ in self._sessions.values())
            return {
                "active_sessions": len(self._sessions),
                "total_budget_allocated": total_budget,
                "total_used": total_used,
                "total_remaining": max(0, total_budget - total_used),
                "default_budget": self._default_budget,
                "max_sessions": self._max_sessions,
                "usage_pct": round(
                    (total_used / max(total_budget, 1)) * 100, 1
                ),
            }


# ---------------------------------------------------------------------------
# Funciones de conveniencia (top-level)
# ---------------------------------------------------------------------------


