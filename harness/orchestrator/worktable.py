"""
Mesa de Trabajo — Multi-agent software quality debate system.

Organiza un debate estructurado entre N agentes especializados en diferentes
atributos de calidad de software (SoC, Low Coupling, High Cohesion, etc.).

Cada agente representa un principio y defiende su perspectiva.
Un moderador (Worktable) orquesta el debate en rondas.
Al final se produce un compendio con las decisiones acordadas.

Flujo:
1. RONDA 1: Cada agente presenta su postura inicial
2. RONDA 2: Los agentes se critican entre si
3. RONDA 3: Refinamiento de posturas
4. COMPENDIO: Sintesis final con acuerdos y trade-offs

Usage:
    wt = Worktable()
    compendio = wt.debate("Disenar una API REST para un sistema de pagos")
    print(compendio.summary)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class DebateRound(Enum):
    """Rondas del debate estructurado."""
    OPENING = "opening"          # Ronda 1: Postura inicial
    CRITIQUE = "critique"        # Ronda 2: Critica cruzada
    REFINEMENT = "refinement"    # Ronda 3: Refinamiento
    COMPENDIUM = "compendium"    # Final: Sintesis


@dataclass
class AgentPosition:
    """
    Postura de un agente en el debate.
    
    Attributes:
        agent_name: Nombre del principio/atributo.
        stance: Postura (a favor/en contra/neutral).
        arguments: Argumentos principales.
        concerns: Preocupaciones sobre otras posturas.
        vote: Voto final (aceptar/rechazar/abstencion).
    """
    agent_name: str
    stance: str = "neutral"
    arguments: List[str] = field(default_factory=list)
    concerns: List[str] = field(default_factory=list)
    vote: str = "abstencion"


@dataclass
class Compendium:
    """
    Compendio final del debate.
    
    Attributes:
        summary: Resumen ejecutivo de la decision.
        agreements: Puntos de acuerdo entre agentes.
        trade_offs: Compromisos identificados.
        rejected: Opciones rechazadas y por que.
        recommendations: Recomendaciones finales.
        participants: Agentes participantes.
        rounds: Numero de rondas realizadas.
    """
    summary: str = ""
    agreements: List[str] = field(default_factory=list)
    trade_offs: List[Dict[str, str]] = field(default_factory=list)
    rejected: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    participants: List[str] = field(default_factory=list)
    rounds: int = 0


# ---------------------------------------------------------------------------
# Expertos disponibles (cada uno es un skill/principio)
# ---------------------------------------------------------------------------

AGENT_PROFILES: Dict[str, Dict[str, Any]] = {
    "soc": {
        "name": "Separation of Concerns",
        "abbr": "SoC",
        "description": "Separacion por responsabilidades claras",
        "bias": "Prefiere modulos pequenos y enfocados, cada uno con una unica responsabilidad. Tiende a dividir problemas en mas partes de las necesarias.",
        "questions": [
            "Cada modulo tiene una unica responsabilidad?",
            "Los cambios en un requisito afectan a un solo modulo?",
            "Hay overlapping de funcionalidades entre modulos?",
        ],
    },
    "coupling": {
        "name": "Low Coupling",
        "abbr": "L.Coupling",
        "description": "Bajo acoplamiento entre modulos",
        "bias": "Prioriza interfaces claras y minimas dependencias. Puede pecar de sobre-abstraccion para evitar acoplamiento.",
        "questions": [
            "Los modulos pueden ser modificados independientemente?",
            "Los cambios en un modulo cascada a otros?",
            "Las interfaces son estables y bien definidas?",
        ],
    },
    "cohesion": {
        "name": "High Cohesion",
        "abbr": "H.Cohesion",
        "description": "Alta cohesion dentro de modulos",
        "bias": "Prefiere agrupar funcionalidades relacionadas. Puede crear modulos demasiado grandes.",
        "questions": [
            "Los elementos dentro de un modulo estan logicamente relacionados?",
            "El modulo tiene un proposito claro y unico?",
            "Las funciones dentro del modulo colaboran entre si?",
        ],
    },
    "resilience": {
        "name": "Fault Tolerance & Resilience",
        "abbr": "Resilience",
        "description": "Capacidad de resistir y recuperarse de fallos",
        "bias": "Prioriza la estabilidad sobre la velocidad. Anade redundancia y circuit breakers incluso donde no son estrictamente necesarios.",
        "questions": [
            "Que pasa si este componente falla?",
            "Hay mecanismos de recuperacion automatica?",
            "Los fallos estan aislados o pueden cascada?",
        ],
    },
    "scalability": {
        "name": "Scalability & Elasticity",
        "abbr": "Scalability",
        "description": "Capacidad de crecer horizontal y verticalmente",
        "bias": "Disena para el pico maximo. Puede sobre-dimensionar para cargas que nunca ocurren.",
        "questions": [
            "Puede manejar 10x la carga actual?",
            "Los componentes son stateless o stateful?",
            "Se puede escalar horizontalmente?",
        ],
    },
    "observability": {
        "name": "Observability",
        "abbr": "Observability",
        "description": "Capacidad de entender el estado interno del sistema",
        "bias": "Quiere metricas de todo, logs de todo, trazas de todo. Puede generar overhead excesivo de observacion.",
        "questions": [
            "Podemos diagnosticar un problema en produccion?",
            "Hay metricas de latency, throughput, errores?",
            "Las trazas permiten seguir una request completa?",
        ],
    },
    "clean_code": {
        "name": "Clean Code",
        "abbr": "Clean Code",
        "description": "Codigo legible, mantenible y consistente",
        "bias": "Prioriza legibilidad sobre eficiencia. Puede rechazar soluciones pragmaticas por no ser 'elegantes'.",
        "questions": [
            "El codigo es facil de leer y entender?",
            "Los nombres de variables y funciones son claros?",
            "Sigue convenciones consistentes?",
        ],
    },
    "maintainability": {
        "name": "Maintainability",
        "abbr": "Maintainability",
        "description": "Facilidad de mantener y hacer cambios a largo plazo",
        "bias": "Prioriza la estructura a largo plazo sobre la entrega rapida. Puede sobre-disenar para escenarios futuros inciertos.",
        "questions": [
            "Un nuevo desarrollador puede entender esto en 1 hora?",
            "Los cambios se pueden hacer sin romper otras partes?",
            "La documentacion esta actualizada?",
        ],
    },
    "testability": {
        "name": "Testability",
        "abbr": "Testability",
        "description": "Facilidad de escribir y ejecutar tests",
        "bias": "Quiere que todo sea testeable. Puede forzar DI y abstracciones solo para poder hacer mock en tests.",
        "questions": [
            "Podemos escribir tests unitarios para esto?",
            "Las dependencias se pueden mockear facilmente?",
            "Hay un alto coverage de codigo?",
        ],
    },
    "interoperability": {
        "name": "Interoperability",
        "abbr": "Interop",
        "description": "Capacidad de integrarse con otros sistemas",
        "bias": "Prefiere estandares abiertos y APIs genericas. Puede sobre-generalizar para cubrir casos de integracion hipoteticos.",
        "questions": [
            "Se puede integrar con otros sistemas via APIs estandar?",
            "Usa formatos y protocolos estandar?",
            "Los contratos son estables y versionados?",
        ],
    },
    "security": {
        "name": "Security (Defense in Depth)",
        "abbr": "Security",
        "description": "Seguridad en multiples capas mas alla de CID",
        "bias": "Ve amenazas en todas partes. Puede rechazar soluciones que no cumplan estandares de seguridad estrictos aunque el riesgo sea aceptable.",
        "questions": [
            "Cual es el threat model?",
            "Hay defensa en profundidad o solo un factor?",
            "Que pasa si un atacante compromete una capa?",
        ],
    },
    "devops": {
        "name": "DevOps Principles",
        "abbr": "DevOps",
        "description": "Integracion continua, despliegue automatico y operaciones",
        "bias": "Quiere automatizacion total. Puede subestimar el valor de procesos manuales controlados.",
        "questions": [
            "Se puede deployar automaticamente?",
            "Hay CI/CD pipeline completo?",
            "Los entornos son reproducibles?",
        ],
    },
    "tradeoffs": {
        "name": "Trade-offs Manager",
        "abbr": "Trade-offs",
        "description": "Gestion de compromisos entre atributos de calidad",
        "bias": "Busca equilibrio. Puede no tomar partido y diluir decisiones importantes.",
        "questions": [
            "Cual es el costo de cada decision?",
            "Que atributo se sacrifica y por cual?",
            "Hay metricas para evaluar cada opcion?",
        ],
    },
}


class Worktable:
    """
    Mesa de Trabajo — Debate multi-agente sobre calidad de software.
    
    Organiza un torneo de debate entre N agentes especializados
    para llegar a un compendio sobre un tema de software.
    
    Usage:
        wt = Worktable()
        compendio = wt.debate(
            topic="Disenar API REST para pagos",
            agents=["soc", "coupling", "security", "scalability"],
            rounds=2,
        )
        print(compendio.summary)
    """

    def __init__(self, dispatch_fn: Optional[Callable] = None) -> None:
        """
        Args:
            dispatch_fn: Funcion para obtener respuestas de agentes.
                Si es None, usa respuestas simuladas (modo offline).
        """
        self._dispatch = dispatch_fn or self._mock_dispatch
        self._positions: Dict[str, AgentPosition] = {}
        self._round = 0
        self._log: List[Dict[str, Any]] = []

    def debate(
        self,
        topic: str,
        agents: Optional[List[str]] = None,
        rounds: int = 3,
    ) -> Compendium:
        """
        Ejecutar un debate completo sobre un tema.
        
        Args:
            topic: Tema a debatir (ej: "Disenar API REST para pagos").
            agents: Lista de agentes participantes. Si es None, usa todos.
            rounds: Numero de rondas (1-3, default 3).
            
        Returns:
            Compendium con el resultado del debate.
        """
        if agents is None:
            agents = list(AGENT_PROFILES.keys())
        else:
            agents = [a for a in agents if a in AGENT_PROFILES]
        
        if not agents:
            logger.warning("No valid agents provided")
            return Compendium()
        
        logger.info(f"Worktable debate iniciado: {topic}")
        logger.info(f"Participantes: {', '.join(agents)}")
        
        # Inicializar posiciones
        self._positions = {a: AgentPosition(agent_name=a) for a in agents}
        self._log = []
        self._round = 0
        
        # Ronda 1: Postura inicial
        self._round = 1
        logger.info(f"--- Ronda {self._round}: Postura Inicial ---")
        for agent in agents:
            profile = AGENT_PROFILES[agent]
            response = self._dispatch(
                agent=agent,
                topic=topic,
                round_type=DebateRound.OPENING,
                profile=profile,
                positions=self._positions,
            )
            self._positions[agent].arguments = response.get("arguments", [])
            self._positions[agent].stance = response.get("stance", "neutral")
            self._log.append({
                "round": 1, "agent": agent, "type": "opening",
                "content": response,
            })
        
        # Ronda 2: Critica (si rounds >= 2)
        if rounds >= 2:
            self._round = 2
            logger.info(f"--- Ronda {self._round}: Critica Cruzada ---")
            for agent in agents:
                profile = AGENT_PROFILES[agent]
                other_agents = [a for a in agents if a != agent]
                response = self._dispatch(
                    agent=agent,
                    topic=topic,
                    round_type=DebateRound.CRITIQUE,
                    profile=profile,
                    positions=self._positions,
                    other_agents=other_agents,
                )
                self._positions[agent].concerns = response.get("concerns", [])
                self._log.append({
                    "round": 2, "agent": agent, "type": "critique",
                    "content": response,
                })
        
        # Ronda 3: Refinamiento (si rounds >= 3)
        if rounds >= 3:
            self._round = 3
            logger.info(f"--- Ronda {self._round}: Refinamiento ---")
            for agent in agents:
                profile = AGENT_PROFILES[agent]
                response = self._dispatch(
                    agent=agent,
                    topic=topic,
                    round_type=DebateRound.REFINEMENT,
                    profile=profile,
                    positions=self._positions,
                )
                self._positions[agent].arguments = response.get("arguments", self._positions[agent].arguments)
                self._positions[agent].vote = response.get("vote", "abstencion")
                self._log.append({
                    "round": 3, "agent": agent, "type": "refinement",
                    "content": response,
                })
        
        # Generar compendio
        compendium = self._generate_compendium(topic, agents)
        return compendium

    def _generate_compendium(
        self,
        topic: str,
        agents: List[str],
    ) -> Compendium:
        """Generar compendio final a partir de las posiciones de los agentes."""
        comp = Compendium(
            participants=list(agents),
            rounds=self._round,
        )
        
        # Resumen: puntos de acuerdo
        agreements = set()
        trade_offs = []
        recommendations = []
        
        for agent in agents:
            pos = self._positions[agent]
            if pos.vote == "aceptar":
                agreements.add(f"{AGENT_PROFILES[agent]['abbr']}: acepta")
            elif pos.vote == "rechazar":
                recommendations.append(
                    f"{AGENT_PROFILES[agent]['name']} recomienda rechazar "
                    f"por: {'; '.join(pos.concerns[:2])}"
                )
            
            # Identificar trade-offs
            for concern in pos.concerns[:3]:
                trade_offs.append({
                    "from": AGENT_PROFILES[agent]['abbr'],
                    "concern": concern,
                })
        
        comp.agreements = list(agreements)
        comp.trade_offs = trade_offs[:5]
        comp.recommendations = recommendations
        
        # Summary generado con IA o por defecto
        accept_count = sum(1 for a in agents if self._positions[a].vote == "aceptar")
        reject_count = sum(1 for a in agents if self._positions[a].vote == "rechazar")
        total = len(agents)
        
        if accept_count > total * 0.6:
            comp.summary = (
                f"COMPENDIO APROBADO: {accept_count}/{total} agentes aceptan "
                f"la propuesta para '{topic}'. "
                f"Se identificaron {len(trade_offs)} trade-offs y "
                f"{len(recommendations)} recomendaciones de mejora."
            )
        elif reject_count > total * 0.6:
            comp.summary = (
                f"COMPENDIO RECHAZADO: {reject_count}/{total} agentes rechazan "
                f"la propuesta para '{topic}'. "
                f"Se requiere rediseno considerando: "
                f"{'; '.join(r[:50] for r in recommendations[:3])}"
            )
        else:
            comp.summary = (
                f"COMPENDIO EN DISCUSION: {accept_count}/{total} aceptan, "
                f"{reject_count}/{total} rechazan. "
                f"Se requieren mas iteraciones para alcanzar consenso."
            )
        
        return comp

    def _mock_dispatch(
        self,
        agent: str,
        topic: str,
        round_type: DebateRound,
        profile: Dict[str, Any],
        positions: Optional[Dict[str, AgentPosition]] = None,
        other_agents: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Dispatch simulado para modo offline."""
        bias = profile.get("bias", "")
        questions = profile.get("questions", [])
        
        if round_type == DebateRound.OPENING:
            return {
                "stance": "a favor" if len(topic) % 2 == 0 else "en contra",
                "arguments": [
                    f"Desde {profile['abbr']}: {questions[0] if questions else 'Analisis requerido'}",
                    f"Recomiendo: {bias[:100]}",
                ],
            }
        elif round_type == DebateRound.CRITIQUE:
            concerns = []
            if other_agents:
                for other in other_agents[:2]:
                    other_profile = AGENT_PROFILES.get(other, {})
                    concerns.append(
                        f"Preocupacion sobre {other_profile.get('abbr', other)}: "
                        f"su enfoque podria comprometer {profile['abbr']}"
                    )
            return {"concerns": concerns}
        else:
            return {
                "arguments": [f"{profile['abbr']}: Propuesta refinada para {topic[:50]}"],
                "vote": "aceptar" if len(agent) % 2 == 0 else "rechazar",
            }

    def get_log(self) -> List[Dict[str, Any]]:
        """
        Obtener el log completo del debate.
        
        Returns:
            Copia del log interno para evitar mutacion externa.
        """
        return list(self._log)

    def get_positions(self) -> Dict[str, AgentPosition]:
        """Obtener posiciones actuales de los agentes."""
        return self._positions
