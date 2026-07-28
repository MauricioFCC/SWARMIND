"""
InstinctSystem — Comportamientos aprendidos para agentes (inspirado en ECC instincts).

Los instintos son patrones de comportamiento que los agentes aprenden
y reutilizan automaticamente. Similar a reflejos condicionados.
Cada instinto asocia un patron de activacion (trigger) con una accion
predefinida, permitiendo respuestas rapidas sin razonamiento completo.

Tipico uso:
    >>> system = InstinctSystem()
    >>> system.learn("cache_hit", "cache", "usar cache compartida", "optimizacion")
    >>> instinto = system.recall("usar cache para mejorar rendimiento")
    >>> instinto.name
    'cache_hit'
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Instinct:
    """Representa un instinto aprendido por un agente.

    Cada instinto encapsula un patron de activacion, una accion a ejecutar
    y metadatos de uso para evaluar su efectividad.

    Args:
        name: Nombre unico del instinto (ej: "cache_hit", "error_retry").
        trigger_pattern: Palabra o frase que activa el instinto (case-insensitive).
        action: Descripcion de la accion a ejecutar al activarse.
        context: Contexto o dominio donde aplica (ej: "optimizacion", "seguridad").
        success_rate: Tasa de exito historica del instinto (0.0 a 1.0).
        times_used: Contador de veces que el instinto ha sido activado.

    Returns:
        Una instancia de Instinct lista para ser registrada en InstinctSystem.
    """

    name: str
    trigger_pattern: str
    action: str
    context: str = ""
    success_rate: float = 0.0
    times_used: int = 0


class InstinctSystem:
    """Sistema de instintos para agentes autonomos.

    Permite aprender, recordar y evaluar instintos. Los instintos se activan
    cuando el contexto de entrada contiene el patron de activacion definido.

    Ejemplo:
        >>> system = InstinctSystem()
        >>> instinto = system.learn("error_retry", "timeout",
        ...     "reintentar con backoff exponencial", "resiliencia")
        >>> system.recall("se produjo un timeout en la conexion") is not None
        True
        >>> stats = system.get_stats()
        >>> stats["total_instincts"]
        1
    """

    def __init__(self) -> None:
        """Inicializa el sistema de instintos vacio.

        Crea una lista interna para almacenar los instintos aprendidos.
        """
        self._instincts: List[Instinct] = []

    def learn(
        self,
        name: str,
        pattern: str,
        action: str,
        context: str = "",
    ) -> Instinct:
        """Registra un nuevo instinto en el sistema.

        Args:
            name: Nombre unico del instinto. Si ya existe, se omite
                  (idempotencia garantizada).
            pattern: Palabra o frase que activara el instinto. Se busca
                     como substring case-insensitive en el contexto.
            action: Descripcion de la accion a ejecutar.
            context: Contexto opcional que describe el dominio de aplicacion.

        Returns:
            El instinto recien creado (o el existente si ya estaba registrado).

        Raises:
            ValueError: Si name o pattern estan vacios.

        Ejemplo:
            >>> system = InstinctSystem()
            >>> i = system.learn("test", "error", "loggear error", "debug")
            >>> i.name
            'test'
            >>> i.times_used
            0
        """
        if not name or not name.strip():
            logger.error("learn: name vacio -> ValueError")
            raise ValueError("El nombre del instinto no puede estar vacio")
        if not pattern or not pattern.strip():
            logger.error("learn: pattern vacio -> ValueError")
            raise ValueError("El patron de activacion no puede estar vacio")

        # Idempotencia: si ya existe, retornar el existente
        existing = self._find_by_name(name)
        if existing is not None:
            logger.debug(
                "learn: instinto '%s' ya existe, retornando existente",
                name,
            )
            return existing

        instinct = Instinct(
            name=name.strip(),
            trigger_pattern=pattern.strip().lower(),
            action=action.strip(),
            context=context.strip(),
        )
        self._instincts.append(instinct)
        logger.info(
            "learn: instinto '%s' registrado con patron '%s'",
            name,
            pattern,
        )
        return instinct

    def recall(self, context: str) -> Optional[Instinct]:
        """Busca un instinto que coincida con el contexto dado.

        Recorre los instintos registrados y retorna el primero cuyo
        patron de activacion aparezca en el contexto (case-insensitive).
        Incrementa el contador de uso del instinto encontrado.

        Args:
            context: Texto de contexto donde buscar el patron de activacion.

        Returns:
            El instinto coincidente, o None si no hay ninguna coincidencia.

        Raises:
            ValueError: Si context es None.

        Ejemplo:
            >>> system = InstinctSystem()
            >>> system.learn("r", "urgente", "priorizar", "gestion")
            >>> inst = system.recall("esto es urgente")
            >>> inst is not None
            True
            >>> inst.name
            'r'
        """
        if context is None:
            logger.error("recall: context es None -> ValueError")
            raise ValueError("El contexto no puede ser None")

        context_lower = context.lower()
        for instinct in self._instincts:
            if instinct.trigger_pattern in context_lower:
                instinct.times_used += 1
                logger.debug(
                    "recall: instinto '%s' activado por patron '%s' en contexto",
                    instinct.name,
                    instinct.trigger_pattern,
                )
                return instinct

        logger.debug("recall: ningun instinto activado para el contexto dado")
        return None

    def get_stats(self) -> Dict[str, Any]:
        """Retorna estadisticas de uso del sistema de instintos.

        Returns:
            Dict con las siguientes claves:
                - total_instincts: numero total de instintos registrados.
                - total_uses: suma de veces que todos los instintos se han usado.

        Ejemplo:
            >>> system = InstinctSystem()
            >>> system.learn("a", "error", "log", "ops")
            >>> system.recall("hubo un error grave")
            >>> stats = system.get_stats()
            >>> stats["total_instincts"]
            1
            >>> stats["total_uses"]
            1
        """
        total_uses = sum(i.times_used for i in self._instincts)
        logger.debug(
            "get_stats: total_instincts=%d, total_uses=%d",
            len(self._instincts),
            total_uses,
        )
        return {
            "total_instincts": len(self._instincts),
            "total_uses": total_uses,
        }

    def _find_by_name(self, name: str) -> Optional[Instinct]:
        """Busca un instinto por su nombre (uso interno).

        Args:
            name: Nombre del instinto a buscar.

        Returns:
            El instinto si se encuentra, None en caso contrario.
        """
        for instinct in self._instincts:
            if instinct.name == name:
                return instinct
        return None

    def __len__(self) -> int:
        """Retorna la cantidad de instintos registrados.

        Returns:
            Entero con el numero de instintos en el sistema.
        """
        return len(self._instincts)

    def __repr__(self) -> str:
        """Representacion legible del sistema de instintos.

        Returns:
            String con formato 'InstinctSystem(N instintos)'.
        """
        return f"InstinctSystem({len(self._instincts)} instintos)"
