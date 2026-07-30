"""
Agent Cost Controller — Monitoreo y control de costos de agentes.

Previene cost explosion por loops infinitos, llamadas redundantes
y consumo anomalo de tokens.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any


@dataclass
class AgentCostRecord:
    """Registro de costos de un agente individual.

    Almacena el consumo de tokens, numero de llamadas y deteccion
    de repeticiones (posibles loops infinitos).

    Args:
        agent: Nombre del agente.
        tokens_used: Total de tokens consumidos por el agente.
        calls_made: Numero de llamadas realizadas por el agente.
        last_call_hash: Hash MD5 del ultimo prompt enviado.
        repeat_count: Contador de repeticiones consecutivas del mismo prompt.
        session_id: Identificador de la sesion a la que pertenece el agente.
    """
    agent: str
    tokens_used: int = 0
    calls_made: int = 0
    last_call_hash: str = ""
    repeat_count: int = 0
    session_id: str = ""


class AgentCostController:
    """Controlador de costos de agentes.

    Monitorea el consumo de tokens y detecta patrones anomalos
    como loops infinitos (mismo prompt repetido) o exceso de presupuesto.

    Args:
        max_tokens_per_session: Maximo de tokens permitidos por sesion.
            Por defecto 50000.
        max_repeat_calls: Maximo de llamadas repetidas consecutivas
            antes de considerar que hay un loop. Por defecto 5.

    Raises:
        ValueError: Si max_tokens_per_session o max_repeat_calls son
            menores o iguales a cero.
    """

    def __init__(
        self,
        max_tokens_per_session: int = 50000,
        max_repeat_calls: int = 5,
    ) -> None:
        """Inicializa el controlador de costos.

        Args:
            max_tokens_per_session: Maximo de tokens por sesion.
            max_repeat_calls: Maximo de repeticiones consecutivas.

        Raises:
            ValueError: Si los parametros de limite son invalidos.
        """
        if max_tokens_per_session <= 0:
            raise ValueError(
                f"max_tokens_per_session debe ser > 0, recibido: {max_tokens_per_session}"
            )
        if max_repeat_calls <= 0:
            raise ValueError(
                f"max_repeat_calls debe ser > 0, recibido: {max_repeat_calls}"
            )
        self._max_tokens = max_tokens_per_session
        self._max_repeat = max_repeat_calls
        self._records: dict[str, AgentCostRecord] = {}

    def register_call(
        self,
        agent: str,
        prompt: str,
        tokens: int,
        session_id: str = "default",
    ) -> bool:
        """Registra una llamada de agente y verifica limites de costo.

        Calcula el hash del prompt para detectar llamadas repetidas.
        Retorna False si se supera el limite de tokens o se detecta
        un posible loop infinito.

        Args:
            agent: Nombre del agente que realiza la llamada.
            prompt: Texto del prompt enviado al agente.
            tokens: Cantidad de tokens consumidos en la llamada.
            session_id: Identificador de sesion. Por defecto 'default'.

        Returns:
            True si la llamada esta dentro de los limites,
            False si debe detenerse por costo excesivo o loop detectado.
        """
        call_hash = hashlib.md5(prompt.encode()).hexdigest()[:16]
        if agent not in self._records:
            self._records[agent] = AgentCostRecord(
                agent=agent,
                session_id=session_id,
            )
        rec = self._records[agent]
        if rec.last_call_hash == call_hash:
            rec.repeat_count += 1
            if rec.repeat_count > self._max_repeat:
                return False  # Loop detected
        else:
            rec.repeat_count = 0
        rec.last_call_hash = call_hash
        rec.tokens_used += tokens
        rec.calls_made += 1
        return rec.tokens_used <= self._max_tokens  # Budget exceeded

    def get_stats(self) -> dict[str, Any]:
        """Retorna estadisticas de uso de todos los agentes registrados.

        Returns:
            Diccionario con agente como clave y dict con 'tokens',
            'calls' y 'loops' como valores.
        """
        return {
            k: {
                "tokens": v.tokens_used,
                "calls": v.calls_made,
                "loops": v.repeat_count,
            }
            for k, v in self._records.items()
        }

    def reset(self, agent: str | None = None) -> None:
        """Reinicia los registros de costo.

        Args:
            agent: Si se especifica, reinicia solo ese agente.
                Si es None, reinicia todos los registros.
        """
        if agent is not None:
            self._records.pop(agent, None)
        else:
            self._records.clear()
