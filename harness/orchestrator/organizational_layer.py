"""
OrganizationalLayer — Capa organizacional para sistemas multi-agente (arXiv:2607.25446).

Separa WHO (rol Belbin), HOW (coordinación Mintzberg) y WHICH (protocolo de
colaboración) en capas ortogonales e intercambiables. Implementa RACI como
mecanismo de rendición de cuentas transversal.

Basado en IMACS (Intelligent Multi-Agent Collaboration System):
  - WHO  → BelbinRole: identidad del agente en el equipo
  - HOW  → MintzbergCoordination: mecanismo de alineación
  - WHICH → CollaborationProtocol: algoritmo de fusión

Referencia:
    Chen et al. "Toward an Organizational Science of Multi-Agent LLM Systems:
    Decoupling Who, How, and Which Algorithm" arXiv:2607.25446 (2026).
"""
from __future__ import annotations

import json
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


# ---------------------------------------------------------------------------
# OrganizationalLayer — Capa principal
# ---------------------------------------------------------------------------


class OrganizationalLayer:
    """Capa organizacional orquestando WHO/HOW/WHICH (arXiv:2607.25446).

    Gestiona roles Belbin, matrices RACI y especificaciones de equipo.
    Sirve como punto único de entrada para la configuración organizacional
    del sistema multi-agente.

    Examples:
        >>> layer = OrganizationalLayer()
        >>> layer.assign_role("agent-a", BelbinRole.SHAPER)
        >>> layer.get_role("agent-a")
        <BelbinRole.SHAPER: 'shaper'>
        >>> raci = layer.create_raci("build-api", "agent-a", "agent-b")
        >>> raci.accountable
        'agent-b'
    """

    def __init__(self) -> None:
        """Inicializa la capa organizacional vacía."""
        self._roles: dict[str, BelbinRole] = {}
        self._raci: dict[str, RACIMatrix] = {}
        self._coordination: MintzbergCoordination = (
            MintzbergCoordination.MUTUAL_ADJUSTMENT
        )
        self._model_binding: dict[str, str] = {}
        self._team_name: str = "default"

    # ── WHO: Roles Belbin ──────────────────────────────────────────────

    def assign_role(self, agent: str, role: BelbinRole) -> None:
        """Asigna un rol Belbin a un agente.

        Args:
            agent: Identificador del agente.
            role: Rol Belbin a asignar.

        Raises:
            TypeError: Si ``role`` no es instancia de BelbinRole.
        """
        if not isinstance(role, BelbinRole):
            raise TypeError(
                f"role debe ser BelbinRole, recibido: {type(role).__name__}"
            )
        self._roles[agent] = role

    def get_role(self, agent: str) -> BelbinRole | None:
        """Obtiene el rol Belbin de un agente.

        Args:
            agent: Identificador del agente.

        Returns:
            BelbinRole del agente o ``None`` si no tiene rol asignado.
        """
        return self._roles.get(agent)

    def remove_role(self, agent: str) -> bool:
        """Remueve el rol de un agente.

        Args:
            agent: Identificador del agente.

        Returns:
            ``True`` si el agente tenía rol, ``False`` en caso contrario.
        """
        return self._roles.pop(agent, None) is not None

    def list_roles(self) -> dict[str, BelbinRole]:
        """Lista todas las asignaciones de roles actuales.

        Returns:
            Dict mapeando agente → BelbinRole.
        """
        return dict(self._roles)

    def has_role(self, agent: str, role: BelbinRole) -> bool:
        """Verifica si un agente tiene un rol específico.

        Args:
            agent: Identificador del agente.
            role: Rol Belbin a verificar.

        Returns:
            ``True`` si el agente tiene exactamente ese rol.
        """
        return self._roles.get(agent) == role

    # ── HOW: Coordinación Mintzberg ────────────────────────────────────

    @property
    def coordination(self) -> MintzbergCoordination:
        """Mecanismo de coordinación activo."""
        return self._coordination

    @coordination.setter
    def coordination(self, mechanism: MintzbergCoordination) -> None:
        """Establece el mecanismo de coordinación.

        Args:
            mechanism: Mecanismo Mintzberg a utilizar.

        Raises:
            TypeError: Si no es instancia de MintzbergCoordination.
        """
        if not isinstance(mechanism, MintzbergCoordination):
            raise TypeError(
                f"mechanism debe ser MintzbergCoordination, "
                f"recibido: {type(mechanism).__name__}"
            )
        self._coordination = mechanism

    # ── WHICH: Protocolo de colaboración ──────────────────────────────

    def get_active_protocol(self) -> CollaborationProtocol:
        """Obtiene el protocolo de colaboración por defecto.

        Returns:
            CollaborationProtocol activo (VOTING por defecto).
        """
        return CollaborationProtocol.VOTING

    # ── RACI ──────────────────────────────────────────────────────────

    def create_raci(
        self,
        task: str,
        responsible: str,
        accountable: str,
        consulted: list[str] | None = None,
        informed: list[str] | None = None,
    ) -> RACIMatrix:
        """Crea y registra una matriz RACI para una tarea.

        Args:
            task: Identificador de la tarea.
            responsible: Agente responsable de ejecutar.
            accountable: Agente que rinde cuentas.
            consulted: Agentes a consultar (opcional).
            informed: Agentes a informar (opcional).

        Returns:
            RACIMatrix creada y registrada.

        Raises:
            ValueError: Si la matriz no pasa validación.
        """
        raci = RACIMatrix(
            responsible=responsible,
            accountable=accountable,
            consulted=consulted or [],
            informed=informed or [],
        )
        raci.validate()
        self._raci[task] = raci
        return raci

    def get_raci(self, task: str) -> RACIMatrix | None:
        """Obtiene la matriz RACI de una tarea.

        Args:
            task: Identificador de la tarea.

        Returns:
            RACIMatrix o ``None`` si no existe.
        """
        return self._raci.get(task)

    def remove_raci(self, task: str) -> bool:
        """Remueve la matriz RACI de una tarea.

        Args:
            task: Identificador de la tarea.

        Returns:
            ``True`` si la tarea tenía RACI, ``False`` en caso contrario.
        """
        return self._raci.pop(task, None) is not None

    def list_raci(self) -> dict[str, RACIMatrix]:
        """Lista todas las matrices RACI registradas.

        Returns:
            Dict mapeando tarea → RACIMatrix.
        """
        return dict(self._raci)

    # ── Model binding ─────────────────────────────────────────────────

    def bind_model(self, agent: str, model: str) -> None:
        """Asigna un modelo LLM a un agente.

        Args:
            agent: Identificador del agente.
            model: Identificador del modelo (ej. ``"deepseek-v4-flash"``).
        """
        self._model_binding[agent] = model

    def get_model(self, agent: str) -> str | None:
        """Obtiene el modelo asignado a un agente.

        Args:
            agent: Identificador del agente.

        Returns:
            Nombre del modelo o ``None`` si no tiene asignación.
        """
        return self._model_binding.get(agent)

    # ── TeamSpec ──────────────────────────────────────────────────────

    def load_spec(self, spec: TeamSpec) -> None:
        """Carga una especificación completa de equipo.

        Reemplaza toda la configuración actual con la del spec.

        Args:
            spec: Especificación del equipo a cargar.

        Raises:
            ValueError: Si la especificación no pasa validación.
        """
        errors = spec.validate()
        if errors:
            raise ValueError(
                "TeamSpec inválido:\n  " + "\n  ".join(errors)
            )
        self._team_name = spec.name
        self._roles = dict(spec.roles)
        self._coordination = spec.coordination
        self._model_binding = dict(spec.model_binding)
        self._raci = {
            task: RACIMatrix(
                responsible=r.responsible,
                accountable=r.accountable,
                consulted=list(r.consulted),
                informed=list(r.informed),
            )
            for task, r in spec.raci_assignments.items()
        }

    def to_spec(self) -> TeamSpec:
        """Exporta la configuración actual como TeamSpec.

        Returns:
            TeamSpec con el estado actual de la capa organizacional.
        """
        return TeamSpec(
            name=self._team_name,
            roles=dict(self._roles),
            coordination=self._coordination,
            model_binding=dict(self._model_binding),
            raci_assignments={
                task: RACIMatrix(
                    responsible=r.responsible,
                    accountable=r.accountable,
                    consulted=list(r.consulted),
                    informed=list(r.informed),
                )
                for task, r in self._raci.items()
            },
        )

    def to_dict(self) -> dict[str, Any]:
        """Serializa toda la capa organizacional a diccionario.

        Returns:
            Dict con team_name, roles, coordination, model_binding y raci.
        """
        return {
            "team_name": self._team_name,
            "roles": {
                agent: role.value for agent, role in self._roles.items()
            },
            "coordination": self._coordination.value,
            "model_binding": dict(self._model_binding),
            "raci": {
                task: raci.to_dict() for task, raci in self._raci.items()
            },
        }

    def to_json(self, indent: int = 2) -> str:
        """Serializa la capa organizacional a JSON.

        Args:
            indent: Nivel de indentación (default 2).

        Returns:
            String JSON con toda la configuración organizacional.
        """
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    # ── Presets ───────────────────────────────────────────────────────

    @classmethod
    def from_preset_belbin(cls) -> OrganizationalLayer:
        """Crea capa con preset organizacional Belbin (default).

        Asigna los cinco roles Belbin a agentes con coordinación por
        ajuste mutuo. Es el preset por defecto en IMACS.

        Returns:
            OrganizationalLayer configurada con roles Belbin.
        """
        layer = cls()
        layer._team_name = "belbin"
        layer._coordination = MintzbergCoordination.MUTUAL_ADJUSTMENT
        layer.assign_role("coordinator", BelbinRole.SHAPER)
        layer.assign_role("builder", BelbinRole.IMPLEMENTER)
        layer.assign_role("guardian", BelbinRole.COMPLETER)
        layer.assign_role("scientist", BelbinRole.SPECIALIST)
        layer.assign_role("evolver", BelbinRole.TEAMWORKER)
        return layer

    @classmethod
    def from_preset_adhocracy(cls) -> OrganizationalLayer:
        """Crea capa con preset Adhocracy.

        Equipo flexible con supervisión directa, ideal para generación
        abierta y tareas exploratorias.

        Returns:
            OrganizationalLayer configurada como adhocracy.
        """
        layer = cls()
        layer._team_name = "adhocracy"
        layer._coordination = MintzbergCoordination.DIRECT_SUPERVISION
        layer.assign_role("lead", BelbinRole.SHAPER)
        layer.assign_role("creator", BelbinRole.SPECIALIST)
        layer.assign_role("reviewer", BelbinRole.COMPLETER)
        return layer

    @classmethod
    def from_preset_three_departments(cls) -> OrganizationalLayer:
        """Crea capa con preset Three Departments (Tang dynasty).

        Inspirado en el sistema ministerial Tang con roles jerárquicos
        y supervisión directa. Útil para tareas complejas descomponibles.

        Returns:
            OrganizationalLayer configurada como three-departments.
        """
        layer = cls()
        layer._team_name = "three-departments"
        layer._coordination = MintzbergCoordination.DIRECT_SUPERVISION
        layer.assign_role("chancellor", BelbinRole.SHAPER)
        layer.assign_role("secretary", BelbinRole.IMPLEMENTER)
        layer.assign_role("censor", BelbinRole.COMPLETER)
        layer.assign_role("advisor", BelbinRole.SPECIALIST)
        return layer

    # ── Query ─────────────────────────────────────────────────────────

    def find_agents_by_role(self, role: BelbinRole) -> list[str]:
        """Encuentra todos los agentes con un rol específico.

        Args:
            role: Rol Belbin a buscar.

        Returns:
            Lista de identificadores de agentes con ese rol.
        """
        return [agent for agent, r in self._roles.items() if r == role]

    def get_accountable_for_task(self, task: str) -> str | None:
        """Obtiene el agente accountable para una tarea.

        Args:
            task: Identificador de la tarea.

        Returns:
            Nombre del agente accountable o ``None``.
        """
        raci = self._raci.get(task)
        return raci.accountable if raci else None

    def get_responsible_for_task(self, task: str) -> str | None:
        """Obtiene el agente responsable para una tarea.

        Args:
            task: Identificador de la tarea.

        Returns:
            Nombre del agente responsible o ``None``.
        """
        raci = self._raci.get(task)
        return raci.responsible if raci else None

    def clear(self) -> None:
        """Limpia toda la configuración organizacional."""
        self._roles.clear()
        self._raci.clear()
        self._model_binding.clear()
        self._coordination = MintzbergCoordination.MUTUAL_ADJUSTMENT
        self._team_name = "default"

    @property
    def team_name(self) -> str:
        """Nombre del preset organizacional activo."""
        return self._team_name

    @property
    def agent_count(self) -> int:
        """Cantidad de agentes con rol asignado."""
        return len(self._roles)

    def __repr__(self) -> str:
        return (
            f"OrganizationalLayer(team='{self._team_name}', "
            f"agents={self.agent_count}, "
            f"coordination={self._coordination.value})"
        )
