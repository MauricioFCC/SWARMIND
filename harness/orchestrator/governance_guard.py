"""
GovernanceGuard — Constraint Pinning contra Governance Decay.

arXiv:2606.22528: Context compaction puede borrar constraints de seguridad.
Este modulo mantiene invariantes de governance fuera de la compaction lossy,
implementando tecnicas de Constraint Pinning para preservar reglas criticas
a traves de ciclos de compaction y resumen de contexto.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Patrones de violacion por constraint
# ---------------------------------------------------------------------------

VIOLATION_PATTERS: dict[str, list[str]] = {
    "no_except_pass": [
        r"except\s*:\s*\n\s*pass",
        r"except\s+\w+\s*:\s*\n\s*pass",
    ],
    "no_eval_exec": [
        r"\beval\s*\(",
        r"\bexec\s*\(",
    ],
    "docstrings_es": [
        r"^class\s+\w+.*:\s*$",
        r"^def\s+\w+.*:\s*$",
    ],
    "error_what_why_where": [
        r"\blogger\.\w+\(.*\"",
    ],
    "no_print_debug": [
        r"\bprint\s*\(.*debug",
        r"\bprint\s*\(.*DEBUG",
    ],
}


@dataclass
class PinnedConstraint:
    """
    Restriccion de governance anclada (pinned) fuera de compaction.

    Cada instancia representa una invariante que debe preservarse incluso
    despues de operaciones de context compaction o resumen automatico.

    Attributes:
        name: Identificador unico del constraint.
        rule: Descripcion legible de la regla.
        severity: Nivel de severidad ('critical', 'high', 'medium', 'low').
        enabled: Si el constraint esta activo para verificaciones.
    """

    name: str
    rule: str
    severity: str = "high"
    enabled: bool = True


# ---------------------------------------------------------------------------
# Constantes de constraints por defecto
# ---------------------------------------------------------------------------

DEFAULT_CONSTRAINTS: list[dict[str, str]] = [
    {"name": "no_except_pass", "rule": "No usar except:pass en produccion", "severity": "high"},
    {"name": "docstrings_es", "rule": "Docstrings en ES-UTF8 obligatorios en toda funcion/clase publica", "severity": "high"},
    {"name": "error_what_why_where", "rule": "Errores con WHAT+WHY+WHERE en todos los except", "severity": "high"},
    {"name": "no_eval_exec", "rule": "No usar eval/exec en produccion por riesgo de injection", "severity": "critical"},
    {"name": "no_print_debug", "rule": "No usar print para debug en produccion, usar logger", "severity": "medium"},
]


class GovernanceGuard:
    """
    Guardia de governance que implementa Constraint Pinning.

    Mantiene invariantes de seguridad y calidad fuera del alcance de la
    compaction lossy de contexto, asegurando que reglas criticas no se
    pierdan durante operaciones de resumen automatico.

    Basado en: arXiv:2606.22528 — Constraint Pinning for Governance Decay.
    """

    def __init__(self, constraints: list[dict[str, str]] | None = None) -> None:
        """
        Inicializar GovernanceGuard con constraints opcionales.

        Args:
            constraints: Lista opcional de dicts con 'name', 'rule', 'severity'.
                         Si es None, se usan los DEFAULT_CONSTRAINTS.

        Example:
            >>> guard = GovernanceGuard()
            >>> len(guard.get_pinned())
            5
        """
        source = constraints if constraints is not None else DEFAULT_CONSTRAINTS
        self._constraints: list[PinnedConstraint] = [
            PinnedConstraint(
                name=c["name"],
                rule=c["rule"],
                severity=c.get("severity", "high"),
                enabled=c.get("enabled", True),
            )
            for c in source
        ]
        self._audit_log: list[str] = []

    # ------------------------------------------------------------------
    # Metodos de acceso a constraints
    # ------------------------------------------------------------------

    def get_pinned(self) -> list[PinnedConstraint]:
        """
        Retornar copia de la lista de constraints anclados.

        Returns:
            List[PinnedConstraint]: Copia inmutable de constraints activos.
        """
        return self._constraints.copy()

    def get_enabled(self) -> list[PinnedConstraint]:
        """
        Retornar solo los constraints habilitados.

        Returns:
            List[PinnedConstraint]: Constraints con enabled=True.
        """
        return [c for c in self._constraints if c.enabled]

    def get_constraint(self, name: str) -> PinnedConstraint | None:
        """
        Buscar un constraint por nombre.

        Args:
            name: Nombre del constraint.

        Returns:
            Optional[PinnedConstraint]: El constraint si existe, None si no.
        """
        for c in self._constraints:
            if c.name == name:
                return c
        return None

    def add_constraint(self, name: str, rule: str, severity: str = "high", enabled: bool = True) -> None:
        """
        Anadir un nuevo constraint pinneado.

        Args:
            name: Identificador unico del constraint.
            rule: Descripcion de la regla.
            severity: Nivel de severidad ('critical', 'high', 'medium', 'low').
            enabled: Si comienza activo.

        Raises:
            ValueError: Si ya existe un constraint con ese nombre.
        """
        if self.get_constraint(name) is not None:
            raise ValueError(f"Constraint '{name}' ya existe")
        self._constraints.append(PinnedConstraint(name=name, rule=rule, severity=severity, enabled=enabled))
        self._audit_log.append(f"ADD {name} (severity={severity})")
        logger.info("GovernanceGuard: constraint anadido '%s' (severity=%s)", name, severity)

    def remove_constraint(self, name: str) -> None:
        """
        Eliminar un constraint por nombre.

        Args:
            name: Nombre del constraint a eliminar.

        Raises:
            ValueError: Si el constraint no existe.
        """
        idx = next((i for i, c in enumerate(self._constraints) if c.name == name), -1)
        if idx == -1:
            raise ValueError(f"Constraint '{name}' no encontrado")
        self._constraints.pop(idx)
        self._audit_log.append(f"REMOVE {name}")
        logger.info("GovernanceGuard: constraint eliminado '%s'", name)

    def enable_constraint(self, name: str) -> None:
        """
        Habilitar un constraint.

        Args:
            name: Nombre del constraint.

        Raises:
            ValueError: Si el constraint no existe.
        """
        c = self.get_constraint(name)
        if c is None:
            raise ValueError(f"Constraint '{name}' no encontrado")
        if not c.enabled:
            c.enabled = True
            self._audit_log.append(f"ENABLE {name}")

    def disable_constraint(self, name: str) -> None:
        """
        Deshabilitar un constraint.

        Args:
            name: Nombre del constraint.

        Raises:
            ValueError: Si el constraint no existe.
        """
        c = self.get_constraint(name)
        if c is None:
            raise ValueError(f"Constraint '{name}' no encontrado")
        if c.enabled:
            c.enabled = False
            self._audit_log.append(f"DISABLE {name}")

    # ------------------------------------------------------------------
    # Metodo principal de verificacion
    # ------------------------------------------------------------------

    def check(self, code: str) -> list[str]:
        """
        Verificar codigo contra todos los constraints habilitados.

        Analiza el codigo fuente en busqueda de violaciones a las reglas
        de governance ancladas.

        Args:
            code: Codigo fuente a verificar.

        Returns:
            List[str]: Lista de mensajes de violacion con formato '[severity] rule'.
                       Retorna lista vacia si no hay violaciones.
        """
        violations: list[str] = []
        for constraint in self.get_enabled():
            found = self._check_single(code, constraint)
            violations.extend(found)
        return violations

    def _check_single(self, code: str, constraint: PinnedConstraint) -> list[str]:
        """
        Verificar un constraint individual contra el codigo.

        Args:
            code: Codigo fuente a verificar.
            constraint: Constraint a aplicar.

        Returns:
            List[str]: Violaciones encontradas para este constraint.
        """
        patterns = VIOLATION_PATTERS.get(constraint.name, [])
        found: list[str] = []

        if constraint.name == "no_except_pass":
            # Verificacion especifica para except:pass
            if self._has_except_pass(code):
                found.append(f"[{constraint.severity}] {constraint.rule}")

        elif constraint.name == "no_eval_exec":
            # Verificacion de eval/exec
            for pattern in patterns:
                if re.search(pattern, code):
                    found.append(f"[{constraint.severity}] {constraint.rule}")
                    break

        elif constraint.name == "docstrings_es":
            # Verificacion superficial de docstrings en funciones/clases
            violations = self._check_docstrings_es(code)
            if violations:
                found.append(f"[{constraint.severity}] {constraint.rule} ({violations})")

        elif constraint.name == "error_what_why_where":
            # Verificacion de estructura en except
            if self._has_bare_except(code):
                found.append(f"[{constraint.severity}] {constraint.rule}")

        elif constraint.name == "no_print_debug":
            for pattern in patterns:
                if re.search(pattern, code):
                    found.append(f"[{constraint.severity}] {constraint.rule}")
                    break

        # Registrar en audit log si hay violaciones
        if found:
            self._audit_log.append(f"VIOLATION {constraint.name}: {len(found)} hit(s)")

        return found

    # ------------------------------------------------------------------
    # Metodos auxiliares de deteccion
    # ------------------------------------------------------------------

    @staticmethod
    def _has_except_pass(code: str) -> bool:
        """Detectar patron except:pass en codigo."""
        # Eliminar comentarios y strings para evitar falsos positivos
        cleaned = re.sub(r'#.*$', '', code, flags=re.MULTILINE)
        cleaned = re.sub(r'""".*?"""', '', cleaned, flags=re.DOTALL)
        cleaned = re.sub(r"'''.*?'''", '', cleaned, flags=re.DOTALL)
        return bool(re.search(r'except\s*\w*\s*:\s*\n\s*pass\s*$', cleaned, flags=re.MULTILINE))

    @staticmethod
    def _check_docstrings_es(code: str) -> str | None:
        """
        Verificar presencia de docstrings en funciones/clases.

        Retorna descripcion de hallazgo si se detectan funciones o clases
        sin docstring aparente.
        """
        # Buscar definiciones de funcion/clase
        funcs = re.findall(r'^\s*(?:async\s+)?def\s+(\w+)\s*\(', code, flags=re.MULTILINE)
        classes = re.findall(r'^\s*class\s+(\w+)\s*[\(:]', code, flags=re.MULTILINE)

        if not funcs and not classes:
            return None

        # Verificar si hay al menos un docstring en el codigo
        has_docstring = bool(re.search(r'""".*?"""', code, flags=re.DOTALL))
        if not has_docstring and (funcs or classes):
            return f"{len(funcs)} funciones, {len(classes)} clases sin docstring"
        return None

    @staticmethod
    def _has_bare_except(code: str) -> bool:
        """Detectar except sin especificar excepcion."""
        cleaned = re.sub(r'#.*$', '', code, flags=re.MULTILINE)
        cleaned = re.sub(r'""".*?"""', '', cleaned, flags=re.DOTALL)
        cleaned = re.sub(r"'''.*?'''", '', cleaned, flags=re.DOTALL)
        return bool(re.search(r'except\s*:', cleaned))

    # ------------------------------------------------------------------
    # Auditoria y estado
    # ------------------------------------------------------------------

    def get_audit_log(self) -> list[str]:
        """
        Obtener el log de auditoria de operaciones y verificaciones.

        Returns:
            List[str]: Copia del log cronologico de eventos.
        """
        return list(self._audit_log)

    def clear_audit_log(self) -> None:
        """Limpiar el log de auditoria."""
        self._audit_log.clear()

    def get_summary(self) -> dict[str, Any]:
        """
        Obtener resumen del estado actual del guardia.

        Returns:
            Dict con total de constraints, habilitados, deshabilitados,
            y severidades.
        """
        total = len(self._constraints)
        enabled = len(self.get_enabled())
        disabled = total - enabled
        severities: dict[str, int] = {}
        for c in self._constraints:
            severities[c.severity] = severities.get(c.severity, 0) + 1
        return {
            "total": total,
            "enabled": enabled,
            "disabled": disabled,
            "severities": severities,
            "audit_entries": len(self._audit_log),
        }
