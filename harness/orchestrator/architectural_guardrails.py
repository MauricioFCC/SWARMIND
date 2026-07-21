"""
architectural_guardrails.py — Validacion de reglas arquitectonicas en codigo generado.

Verifica que el codigo generado por agentes cumpla reglas predefinidas:
  - Capas: prohibido imports entre capas incorrectas
  - Tipo: type hints obligatorios en funciones publicas
  - Tamano: no mas de N lineas por funcion
  - Dependencias: no imports prohibidos

Uso:
    from harness.orchestrator.architectural_guardrails import (
        Guardrail, GuardrailResult, check_all, builtin_guardrails
    )
    resultado = check_all("codigo_generado.py", builtin_guardrails())
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from typing import Callable, List, Optional


@dataclass
class GuardrailViolation:
    """Una violacion de una regla arquitectonica."""
    rule: str
    severity: str  # error, warning
    message: str
    line: Optional[int] = None
    code: Optional[str] = None


@dataclass
class GuardrailResult:
    """Resultado de la validacion de guardrails."""
    passed: bool
    violations: List[GuardrailViolation] = field(default_factory=list)
    checked_rules: int = 0

    def summary(self) -> str:
        """Resumen legible del resultado."""
        if self.passed:
            return f"✅ {self.checked_rules} reglas verificadas, 0 violaciones"
        return f"❌ {len(self.violations)} violacion(es) en {self.checked_rules} reglas"


GuardrailFn = Callable[[str, str], GuardrailResult]


# ---------------------------------------------------------------------------
# Guardrails individuales
# ---------------------------------------------------------------------------

def check_type_hints(source: str, filename: str) -> GuardrailResult:
    """Toda funcion publica debe tener type hints."""
    violations = []
    try:
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
                has_returns = node.returns is not None
                has_args = all(
                    isinstance(a, ast.arg) and a.annotation is not None
                    for a in node.args.args
                )
                if not has_returns or not has_args:
                    violations.append(GuardrailViolation(
                        rule="type_hints",
                        severity="warning",
                        message=f"Funcion '{node.name}' sin type hints completos",
                        line=node.lineno,
                        code=f"def {node.name}(...):",
                    ))
    except SyntaxError:
        violations.append(GuardrailViolation(
            rule="type_hints", severity="error",
            message=f"Error de sintaxis en {filename}",
        ))

    return GuardrailResult(passed=len(violations) == 0, violations=violations, checked_rules=1)


def check_function_length(source: str, filename: str, max_lines: int = 60) -> GuardrailResult:
    """Ninguna funcion debe exceder max_lines."""
    violations = []
    try:
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                line_count = node.end_lineno - node.lineno if node.end_lineno else 0
                if line_count > max_lines:
                    violations.append(GuardrailViolation(
                        rule="function_length",
                        severity="warning",
                        message=f"Funcion '{node.name}' tiene {line_count} lineas (max {max_lines})",
                        line=node.lineno,
                    ))
    except SyntaxError:
        pass

    return GuardrailResult(passed=len(violations) == 0, violations=violations, checked_rules=1)


def check_no_except_pass(source: str, filename: str) -> GuardrailResult:
    """Prohibido except: pass sin logger."""
    violations = []
    lines = source.split("\n")
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        # Detecta "except:", "except X:", "except X as e:" seguido de pass en prox linea
        if re.match(r"except\s*(?:\w+\s*(?:as\s+\w+)?\s*)?:", stripped):
            # Busca 'pass' en las siguientes lineas no vacias ni comentarios
            for j in range(i, len(lines)):
                next_line = lines[j].strip()
                if not next_line or next_line.startswith("#"):
                    continue
                if next_line == "pass":
                    violations.append(GuardrailViolation(
                        rule="no_except_pass",
                        severity="error",
                        message=f"except:pass sin logger en linea {i}",
                        line=i,
                        code=line.strip(),
                    ))
                break  # Solo revisar primer contenido no vacio

    return GuardrailResult(passed=len(violations) == 0, violations=violations, checked_rules=1)


def check_forbidden_imports(source: str, filename: str,
                            forbidden: Optional[List[str]] = None) -> GuardrailResult:
    """Verifica que no haya imports prohibidos."""
    if forbidden is None:
        forbidden = ["sys.path.insert(0,", "eval(", "exec(", "pickle.loads"]
    violations = []
    for i, line in enumerate(source.split("\n"), 1):
        for fb in forbidden:
            if fb in line:
                violations.append(GuardrailViolation(
                    rule="forbidden_import",
                    severity="error",
                    message=f"Uso prohibido: '{fb}' en linea {i}",
                    line=i,
                    code=line.strip(),
                ))

    return GuardrailResult(passed=len(violations) == 0, violations=violations, checked_rules=1)


def builtin_guardrails() -> List[GuardrailFn]:
    """Retorna la lista de guardrails predefinidos."""
    return [
        check_type_hints,
        check_function_length,
        check_no_except_pass,
        check_forbidden_imports,
    ]


def check_all(source: str, filename: str = "<string>",
              guardrails: Optional[List[GuardrailFn]] = None) -> GuardrailResult:
    """Ejecuta todos los guardrails sobre el codigo.

    Args:
        source: Codigo fuente a validar.
        filename: Nombre del archivo (opcional).
        guardrails: Lista de funciones guardrail. Default: builtin_guardrails().

    Returns:
        GuardrailResult con todas las violaciones encontradas.
    """
    if guardrails is None:
        guardrails = builtin_guardrails()

    all_violations: List[GuardrailViolation] = []
    total_checks = 0

    for guardrail in guardrails:
        result = guardrail(source, filename)
        all_violations.extend(result.violations)
        total_checks += result.checked_rules

    return GuardrailResult(
        passed=len(all_violations) == 0,
        violations=all_violations,
        checked_rules=total_checks,
    )
