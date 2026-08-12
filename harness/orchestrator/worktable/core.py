"""Worktable — Debate multi-agente sobre calidad de software (core).

Submodulo del paquete :mod:`harness.orchestrator.worktable`.

Contiene la clase ``Worktable`` (moderador del debate), extraida de forma
mecanica desde ``worktable.py`` (regla AGR: archivos < 500 lineas).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from harness.orchestrator.skill_bundler import SkillBundler

from .creative import CreativeWorktable
from .models import AgentPosition, Compendium, DebateRound
from .profiles import AGENT_PROFILES

logger = logging.getLogger(__name__)


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

    def __init__(self, dispatch_fn: Callable | None = None) -> None:
        """
        Args:
            dispatch_fn: Funcion para obtener respuestas de agentes.
                Si es None, usa respuestas simuladas (modo offline).
        """
        self._dispatch = dispatch_fn or self._mock_dispatch
        self._positions: dict[str, AgentPosition] = {}
        self._round = 0
        self._log: list[dict[str, Any]] = []

    def compose_agents(
        self,
        topic: str,
        available_agents: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Componer agentes dinamicamente usando SkillBundler (SIGMA pattern).

        Para temas NO relacionados con software, usa los 13 perfiles clasicos.
        Para temas de software, compone agentes desde skills del registry.

        Args:
            topic: Tema del debate.
            available_agents: Agentes disponibles para componer.

        Returns:
            Lista de perfiles de agente compuestos.
        """
        # Detectar si el tema es de software
        software_keywords = [
            "software", "api", "web", "app", "codigo", "code", "rust", "python",
            "javascript", "typescript", "frontend", "backend", "database", "arquitectura",
            "architecture", "testing", "test", "devops", "deploy", "microservicio",
            "microservice", "algoritmo", "algorithm", "sistema", "system",
        ]
        topic_lower = topic.lower()
        is_software = any(kw in topic_lower for kw in software_keywords)

        if not is_software:
            # Usar perfiles clasicos de AGENT_PROFILES
            if available_agents:
                return [
                    {**AGENT_PROFILES[a], "agent_name": a}
                    for a in available_agents if a in AGENT_PROFILES
                ]
            return [
                {**p, "agent_name": name}
                for name, p in AGENT_PROFILES.items()
            ]

        # Componer desde skills usando SkillBundler
        bundler = SkillBundler()
        configs = bundler.compose(topic, available_agents=available_agents or [
            "coordinator", "builder", "scientist", "guardian", "evolve",
        ])

        # Convertir a formato de perfiles de Worktable
        profiles = []
        for config in configs:
            skills_str = ", ".join(config.bundled_skills[:3])
            profiles.append({
                "agent_name": config.name,
                "name": config.name.capitalize(),
                "abbr": config.name[:4].upper(),
                "description": f"{config.name} con skills: {skills_str}",
                "bias": f"Especializado en {config.domain} via {config.lead_skill}",
                "questions": [
                    f"Como {config.name}, cual es tu enfoque?",
                    f"Que skills ({skills_str}) aplicas?",
                ],
            })

        return profiles

    def debate(
        self,
        topic: str,
        agents: list[str] | None = None,
        rounds: int = 3,
        use_bundler: bool = False,
        creative_mode: bool = False,
    ) -> Compendium:
        """
        Ejecutar un debate completo sobre un tema.

        Args:
            topic: Tema a debatir (ej: "Disenar API REST para pagos").
            agents: Lista de agentes participantes. Si es None, usa todos.
            rounds: Numero de rondas (1-3, default 3).
            use_bundler: Usar SkillBundler para componer agentes dinamicamente.
            creative_mode: Usar pipeline divergente→convergente (ReDNA).

        Returns:
            Compendium con el resultado del debate.
        """
        if creative_mode:
            return self._creative_debate(topic, agents)

        # Componer agentes desde SkillBundler si se solicita
        if use_bundler:
            # Obtener perfiles desde SkillBundler
            bundle_agents = self.compose_agents(topic, agents)
            # Mapear a nombres de agentes (usar los que existen en AGENT_PROFILES)
            valid_agents = [a["agent_name"] for a in bundle_agents if a["agent_name"] in AGENT_PROFILES]
            # Agregar agentes del bundler que no estan en AGENT_PROFILES
            for ba in bundle_agents:
                aname = ba["agent_name"]
                if aname not in AGENT_PROFILES:
                    # Crear perfil temporal
                    AGENT_PROFILES[aname] = {
                        "name": ba.get("name", aname),
                        "abbr": ba.get("abbr", aname[:4].upper()),
                        "description": ba.get("description", ""),
                        "bias": ba.get("bias", ""),
                        "questions": ba.get("questions", []),
                    }
            if valid_agents:
                agents = valid_agents

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
        agents: list[str],
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

    def _creative_debate(self, topic: str, agents: list[str] | None = None) -> Compendium:
        """
        Debate en modo creativo usando pipeline divergente→convergente (ReDNA).

        Args:
            topic: Tema para el debate creativo.
            agents: Agentes participantes.

        Returns:
            Compendium con la propuesta integrada.
        """
        cw = CreativeWorktable()

        # Fase divergente: ideas libres
        ideas = cw.divergent_phase(topic, agents)

        # Fase convergente: seleccion bajo restricciones
        selected = cw.convergent_phase(ideas,
            constraints=["debe ser innovador", "debe ser factible"])

        # Fase de integracion
        proposal = cw.integration_phase(selected)

        return Compendium(
            summary=proposal,
            agreements=[f"{len(selected)} ideas seleccionadas de {len(ideas)} generadas"],
            trade_offs=[{"from": "Creatividad", "concern": "Novedad vs Factibilidad"}],
            recommendations=["Ejecutar segunda iteracion si es necesario"],
            participants=list({i.agent for i in ideas}),
            rounds=3,
        )

    def _mock_dispatch(
        self,
        agent: str,
        topic: str,
        round_type: DebateRound,
        profile: dict[str, Any],
        positions: dict[str, AgentPosition] | None = None,
        other_agents: list[str] | None = None,
    ) -> dict[str, Any]:
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

    def get_log(self) -> list[dict[str, Any]]:
        """
        Obtener el log completo del debate.

        Returns:
            Copia del log interno para evitar mutacion externa.
        """
        return list(self._log)

    def get_positions(self) -> dict[str, AgentPosition]:
        """Obtener posiciones actuales de los agentes."""
        return self._positions
