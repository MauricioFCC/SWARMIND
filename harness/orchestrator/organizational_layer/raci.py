"""OrganizationalLayer raci — mixin con matrices RACI y model binding.

Extraccion mecanica del modulo original
``harness/orchestrator/organizational_layer.py`` (sin cambios de logica
ni firmas): creacion/consulta de matrices RACI, asignacion de modelos
y consultas de responsabilidad por tarea.
"""

from __future__ import annotations

import json
from typing import Any

from .models import RACIMatrix, TeamSpec


class _RACIMixin:
    """Mixin con la gestion de matrices RACI y model binding."""

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

    # ── Query RACI ────────────────────────────────────────────────────

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

    def load_spec(self, spec: TeamSpec) -> None:
        """Reemplaza toda la configuración actual con la del spec.

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
