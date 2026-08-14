"""OrganizationalLayer models — enums y dataclasses de la capa.

Extraccion mecanica del modulo original
``harness/orchestrator/organizational_layer.py`` (sin cambios de logica
ni firmas): BelbinRole, MintzbergCoordination, CollaborationProtocol,
RACIMatrix y TeamSpec.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# ---------------------------------------------------------------------------
# WHO — Roles organizacionales (Belbin)
# ---------------------------------------------------------------------------


class BelbinRole(str, Enum):
    """Roles de equipo según Belbin (arXiv:2607.25446 §3).

    Belbin define nueve roles agrupados en tres orientaciones. Este sistema
    implementa los cinco roles principales del preset ``belbin``.

    Orientaciones:
        - Acción: SHAPER, IMPLEMENTER, COMPLETER
        - Personas: TEAMWORKER
        - Pensamiento: SPECIALIST
    """
    SHAPER = "shaper"                # Lider que impulsa, supera obstáculos
    IMPLEMENTER = "implementer"      # Ejecuta planes, convierte en acción
    COMPLETER = "completer"          # Revisa, perfecciona, asegura calidad
    TEAMWORKER = "teamworker"        # Colabora, mitiga conflictos
    SPECIALIST = "specialist"        # Aporta conocimiento profundo de dominio

    @classmethod
    def from_str(cls, value: str) -> BelbinRole:
        """Convierte string a BelbinRole, case-insensitive.

        Args:
            value: Nombre del rol (ej. ``"shaper"``, ``"IMPLEMENTER"``).

        Returns:
            BelbinRole correspondiente.

        Raises:
            ValueError: Si el string no coincide con ningún rol.
        """
        for role in cls:
            if role.value == value.lower().strip():
                return role
        raise ValueError(
            f"Rol Belbin desconocido: '{value}'. "
            f"Opciones: {[r.value for r in cls]}"
        )


# ---------------------------------------------------------------------------
# HOW — Mecanismos de coordinación (Mintzberg)
# ---------------------------------------------------------------------------


class MintzbergCoordination(str, Enum):
    """Mecanismos de coordinación de Mintzberg (arXiv:2607.25446 §3).

    Define **cómo** los agentes se alinean dentro de la organización.
    """
    MUTUAL_ADJUSTMENT = "mutual_adjustment"   # Comunicación informal directa
    DIRECT_SUPERVISION = "direct_supervision"  # Un supervisor coordina
    STANDARD_PROCESSES = "standard_processes"   # Procedimientos estandarizados
    STANDARD_OUTPUTS = "standard_outputs"       # Resultados estandarizados
    STANDARD_SKILLS = "standard_skills"         # Habilidades estandarizadas


# ---------------------------------------------------------------------------
# WHICH — Protocolos de colaboración (algoritmo de fusión)
# ---------------------------------------------------------------------------


class CollaborationProtocol(str, Enum):
    """Protocolos de colaboración intercambiables (arXiv:2607.25446 §3).

    Define **qué algoritmo** fusiona las contribuciones individuales en un
    resultado final. Corresponde a la capa L4 del stack IMACS.
    """
    VOTING = "voting"                  # Muestreo + votación (Self-Consistency)
    DEBATE = "debate"                  # Rondas de crítica-revisión
    MOA = "moa"                        # Mixture-of-Agents (proposer/aggregator)
    BLENDER = "blender"                # Rank-and-fuse (LLM-Blender)
    REFLEXION = "reflexion"            # Auto-feedback verbal
    PLAN_EXECUTE = "plan_execute"      # Descomponer → ejecutar


# ---------------------------------------------------------------------------
# RACI — Matriz de rendición de cuentas
# ---------------------------------------------------------------------------


@dataclass
class RACIMatrix:
    """Matriz RACI para una tarea (arXiv:2607.25446 §3).

    Asigna responsabilidades según el estándar:
        - **R**esponsible: quien ejecuta el trabajo.
        - **A**ccountable: quien rinde cuentas (único por tarea).
        - **C**onsulted: quien aporta opinión antes de decidir.
        - **I**nformed: quien recibe notificación después.

    Attributes:
        responsible: Agente responsable de ejecutar.
        accountable: Agente accountable (máximo uno por tarea).
        consulted: Agentes consultados antes de decidir.
        informed: Agentes informados después de la decisión.
    """
    responsible: str = ""
    accountable: str = ""
    consulted: list[str] = field(default_factory=list)
    informed: list[str] = field(default_factory=list)

    def validate(self) -> None:
        """Valida las restricciones de la matriz RACI.

        Verifica:
            - No más de un accountable.
            - Responsible no vacío si hay accountable.
            - Sin duplicados en consulted/informed.

        Raises:
            ValueError: Si alguna restricción se incumple.
        """
        # Single-owner constraint: máximo un Accountable
        if self.accountable and self.accountable.count(",") > 0:
            raise ValueError(
                f"RACI: solo se permite un Accountable por tarea. "
                f"Recibido: '{self.accountable}'"
            )
        # Si hay accountable, debe haber responsible
        if self.accountable and not self.responsible:
            raise ValueError(
                "RACI: si hay Accountable debe haber Responsible."
            )
        # Sin duplicados en consulted
        if len(set(self.consulted)) != len(self.consulted):
            raise ValueError(
                f"RACI: consulted no puede tener duplicados. "
                f"Recibido: {self.consulted}"
            )
        # Sin duplicados en informed
        if len(set(self.informed)) != len(self.informed):
            raise ValueError(
                f"RACI: informed no puede tener duplicados. "
                f"Recibido: {self.informed}"
            )
        # responsible no debe estar en consulted ni informed
        if self.responsible in self.consulted:
            raise ValueError(
                f"RACI: Responsible '{self.responsible}' no debe estar "
                f"en consulted."
            )

    def to_dict(self) -> dict[str, Any]:
        """Convierte la matriz a diccionario serializable.

        Returns:
            Dict con claves: responsible, accountable, consulted, informed.
        """
        return {
            "responsible": self.responsible,
            "accountable": self.accountable,
            "consulted": list(self.consulted),
            "informed": list(self.informed),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RACIMatrix:
        """Construye RACIMatrix desde diccionario.

        Args:
            data: Diccionario con claves del RACI.

        Returns:
            Nueva instancia de RACIMatrix.
        """
        return cls(
            responsible=data.get("responsible", ""),
            accountable=data.get("accountable", ""),
            consulted=data.get("consulted", []),
            informed=data.get("informed", []),
        )


# ---------------------------------------------------------------------------
# TeamSpec — Especificación completa de una organización
# ---------------------------------------------------------------------------


@dataclass
class TeamSpec:
    """Especificación completa de una organización IMACS.

    Agrupa WHO (roles), HOW (coordinación) y la configuración de agentes
    en una sola declaración. Cargable desde YAML/JSON.

    Attributes:
        name: Nombre del preset organizacional.
        roles: Mapeo de agente → BelbinRole.
        coordination: Mecanismo de coordinación Mintzberg.
        model_binding: Mapeo de agente → modelo (opcional).
        raci_assignments: Mapeo de tarea → RACIMatrix.
    """
    name: str = "default"
    roles: dict[str, BelbinRole] = field(default_factory=dict)
    coordination: MintzbergCoordination = MintzbergCoordination.MUTUAL_ADJUSTMENT
    model_binding: dict[str, str] = field(default_factory=dict)
    raci_assignments: dict[str, RACIMatrix] = field(default_factory=dict)

    def validate(self) -> list[str]:
        """Valida la especificación completa del equipo.

        Returns:
            Lista de mensajes de error (vacía si es válida).
        """
        errors: list[str] = []
        # Validar que todo agente con rol tenga modelo (solo si hay bindings
        # definidos; bindings vacío = asignación pendiente = válido)
        if self.model_binding and self.roles:
            for agent in self.roles:
                if agent not in self.model_binding:
                    errors.append(
                        f"Agente '{agent}' tiene rol pero no tiene binding "
                        f"de modelo."
                    )
        # Validar RACI assignments
        for task, raci in self.raci_assignments.items():
            try:
                raci.validate()
            except ValueError as e:
                errors.append(f"RACI para tarea '{task}': {e}")
        # Validar que agentes en RACI existan en roles
        all_agents = set(self.roles.keys())
        for task, raci in self.raci_assignments.items():
            for ref in [raci.responsible, raci.accountable]:
                if ref and ref not in all_agents:
                    errors.append(
                        f"RACI para '{task}': agente '{ref}' no está "
                        f"definido en roles."
                    )
        return errors
