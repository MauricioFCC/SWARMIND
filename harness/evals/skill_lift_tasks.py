"""skill_lift_tasks.py — Catalogo determinista de tareas para Skill Lift (paired eval).

WHAT: define :class:`LiftTask` (una tarea con verifier PURO) y
:class:`SkillLiftCatalog`, con un set por defecto de 7 tareas ligadas a skills
REALES del repo. Cada tarea trae ``prompt``, ``reference`` (respuesta-contrato) y
``verifier`` determinista (regex/estructura, SIN LLM).

WHY: :class:`harness.evals.skill_lift.SkillLiftEvaluator` mide el lift pareado
skill-on vs skill-off, pero no traia CATALOGO ni runner; sin tareas con verifier
determinista el lift no es reproducible en CI. Este modulo aporta el catalogo;
el runner real vive en :mod:`harness.evals.skill_lift_runner`.

WHERE: consumido por ``scripts/skill_lift.py`` y ``scripts/evolve_close_loop.py``
(via el runner). Los verifiers son PUROS: misma salida => mismo PASS/FAIL.

IDP: complementa —no reemplaza— ``swebench_mini`` (fixes de codigo con pytest) y
``builtin_evals`` (metricas por capa). Aqui la unidad es (tarea, skill) con
verifier estructural.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

#: Raiz del repo (``harness/evals/skill_lift_tasks.py`` -> parents[2]).
_REPO_ROOT: Path = Path(__file__).resolve().parents[2]
#: Directorio SSOT de skills del repo (usado por los runners y por los tests).
SKILLS_DIR: Path = _REPO_ROOT / ".opencode" / "skills"
#: Nombre del archivo de skill dentro de cada directorio.
SKILL_FILE_NAME: str = "SKILL.md"

#: Verifier inyectado en una tarea: recibe la salida del sistema y decide PASS/FAIL.
Verifier = Callable[[str], bool]


@dataclass(frozen=True)
class LiftTask:
    """Tarea de Skill Lift con verifier determinista.

    Args:
        id: Identificador estable y unico de la tarea.
        skill: Skill del repo a la que pertenece la tarea (nombre de directorio).
        prompt: Instruccion dada al solver (con o sin contexto de skill).
        verifier: Funcion PURA ``(salida: str) -> bool``; mismo input, mismo output.
        reference: Respuesta-contrato que satisface el verifier (lift positivo).
    """

    id: str
    skill: str
    prompt: str
    verifier: Verifier
    reference: str


# ---------------------------------------------------------------------------
# Verifiers PUROS (regex/estructura; SIN LLM, SIN red, SIN IO)
# ---------------------------------------------------------------------------


def _contains_all(text: str, *needles: str) -> bool:
    """Indica si TODAS las agujas aparecen en el texto (case-insensitive).

    Args:
        text: Salida a inspeccionar.
        *needles: Fragmentos que deben estar presentes.

    Returns:
        True si cada aguja aparece (ignorando mayusculas); False en caso contrario.
    """
    lowered = text.casefold()
    return all(needle.casefold() in lowered for needle in needles)


def verify_atdd_cycle(output: str) -> bool:
    """Verifica el ciclo Spec->Test->Code con evidencia RED/GREEN.

    Args:
        output: Salida a verificar.

    Returns:
        True si menciona las 4 fases (spec, test, code, refactor) y RED/GREEN.
    """
    return _contains_all(output, "spec", "test", "code", "refactor", "red", "green")


def verify_agent_rigor_evidence(output: str) -> bool:
    """Verifica la disciplina pre-merge: check ejecutable + evidencia cruda.

    Args:
        output: Salida a verificar.

    Returns:
        True si cita un check (pytest y ruff) y su evidencia (passed/exit code).
    """
    has_tools = _contains_all(output, "pytest", "ruff")
    has_evidence = _contains_all(output, "passed") or _contains_all(output, "exit code")
    return has_tools and has_evidence


def verify_skill_frontmatter(output: str) -> bool:
    """Verifica un SKILL.md con frontmatter valido y description pushy.

    Args:
        output: Salida a verificar.

    Returns:
        True si abre con ``---``, declara ``name:`` y ``description:`` y la
        descripcion dispara con "Usar cuando".
    """
    if not output.lstrip().startswith("---"):
        return False
    return _contains_all(output, "name:", "description:", "usar cuando")


def verify_security_finding(output: str) -> bool:
    """Verifica un hallazgo de seguridad accionable (estandar + amenaza + severidad).

    Args:
        output: Salida a verificar.

    Returns:
        True si cita OWASP y STRIDE y ademas una referencia CWE o severidad.
    """
    has_frameworks = _contains_all(output, "owasp", "stride")
    has_severity = (
        _contains_all(output, "cwe")
        or _contains_all(output, "severidad")
        or _contains_all(output, "severity")
    )
    return has_frameworks and has_severity


def verify_architecture_decision(output: str) -> bool:
    """Verifica un ADR con patron, trade-offs explicitos y veredicto.

    Args:
        output: Salida a verificar.

    Returns:
        True si cita un ADR, un patron (hexagonal) y sus trade-offs.
    """
    return _contains_all(output, "adr", "hexagonal", "trade-off")


def verify_evolve_loop(output: str) -> bool:
    """Verifica el loop ASI-Evolve (Learn -> Design -> Experiment -> Analyze).

    Args:
        output: Salida a verificar.

    Returns:
        True si nombra las 4 fases del loop de auto-mejora.
    """
    return _contains_all(output, "learn", "design", "experiment", "analyze")


def verify_data_science_eval(output: str) -> bool:
    """Verifica un plan ML con split, metrica y baseline declarados antes de entrenar.

    Args:
        output: Salida a verificar.

    Returns:
        True si declara split, metrica y baseline (anti-leakage / anti-hedging).
    """
    return _contains_all(output, "split", "metric", "baseline")


# ---------------------------------------------------------------------------
# Catalogo por defecto (7 tareas ligadas a skills REALES del repo)
# ---------------------------------------------------------------------------

DEFAULT_TASKS: tuple[LiftTask, ...] = (
    LiftTask(
        id="atdd-spec-cycle",
        skill="atdd-spec",
        prompt="Describe el ciclo para implementar una feature con TDD guiado por IA.",
        verifier=verify_atdd_cycle,
        reference=(
            "Ciclo Spec->Test->Code: (1) SPEC: acceptance criteria en lenguaje natural "
            "con ejemplos concretos; (2) TEST: 1 test = 1 criterio, escrito ANTES del "
            "codigo; (3) CODE: implementacion minima (KISS) para pasar; (4) REFACTOR: "
            "limpiar con tests verdes. Evidencia RED: el test falla primero con el "
            "motivo correcto. GREEN: la implementacion minima lo hace pasar."
        ),
    ),
    LiftTask(
        id="agent-rigor-gate",
        skill="agent-rigor",
        prompt="Define el gate pre-merge y como demostrarlo.",
        verifier=verify_agent_rigor_evidence,
        reference=(
            "Gate T1: ejecuta `uv run python -m pytest harness/tests/test_x.py -q` y "
            "`uv run ruff check harness/x.py`. Evidencia cruda: pytest '12 passed', "
            "ruff 'All checks passed' (exit code 0). Ningun merge con check rojo."
        ),
    ),
    LiftTask(
        id="skill-engineering-frontmatter",
        skill="skill-engineering",
        prompt="Escribe el esqueleto valido de un SKILL.md nuevo.",
        verifier=verify_skill_frontmatter,
        reference=(
            "---\n"
            "name: mi-skill\n"
            "description: \"Usar cuando el usuario necesite X; keywords: x, y.\"\n"
            "license: MIT\n"
            "---\n\n"
            "# Mi Skill\n\n## Criterios de exito verificables\n- ...\n"
        ),
    ),
    LiftTask(
        id="security-audit-finding",
        skill="security-audit",
        prompt="Reporta un hallazgo de seguridad en un endpoint de login.",
        verifier=verify_security_finding,
        reference=(
            "Hallazgo SAST: inyeccion SQL en el login. Estandar OWASP Top 10 "
            "(A03:2021). STRIDE: Tampering. CWE-89. Severidad: ALTA. Remediacion: "
            "consultas parametrizadas y validacion de entrada."
        ),
    ),
    LiftTask(
        id="architecture-adr",
        skill="architecture",
        prompt="Recomienda una arquitectura para un servicio con puertos y adaptadores.",
        verifier=verify_architecture_decision,
        reference=(
            "ADR-0042: adoptar arquitectura HEXAGONAL (ports/adapters) sobre capas. "
            "Trade-off: +testabilidad y dominio puro, -indireccion en adapters. "
            "Veredicto: hexagonal. Diagrama C4 pendiente."
        ),
    ),
    LiftTask(
        id="evolve-loop",
        skill="evolve",
        prompt="Explica el loop de auto-mejora del sistema.",
        verifier=verify_evolve_loop,
        reference=(
            "Loop ASI-Evolve: LEARN (cognition store) -> DESIGN (hipotesis con metrica) "
            "-> EXPERIMENT (evaluar) -> ANALYZE (distillar lecciones). Persiste cognition."
        ),
    ),
    LiftTask(
        id="data-science-plan",
        skill="data-science",
        prompt="Disena el plan de evaluacion de un modelo de clasificacion.",
        verifier=verify_data_science_eval,
        reference=(
            "Plan ML: define SPLIT temporal ANTES de entrenar, declara METRICA (F1) y "
            "BASELINE (clase mayoritaria). Sin leakage. Reporta baseline vs modelo."
        ),
    ),
)


class SkillLiftCatalog:
    """Catalogo inmutable de tareas de Skill Lift con busqueda por id/skill.

    Defensivo (VAL): valida ids unicos y no vacios al construir; inyectable (DI)
    para tests con tareas sinteticas.
    """

    def __init__(self, *, tasks: list[LiftTask] | None = None) -> None:
        """Construye el catalogo con las tareas dadas o el set por defecto.

        Args:
            tasks: Tareas explícitas; ``None`` usa :data:`DEFAULT_TASKS`.

        Raises:
            ValueError: Si la lista esta vacia o hay ids duplicados/vacios.
        """
        materialized = tuple(tasks) if tasks is not None else DEFAULT_TASKS
        if not materialized:
            raise ValueError(
                "tasks no puede estar vacio. WHAT: catalogo sin tareas | "
                "WHERE: SkillLiftCatalog.__init__()"
            )
        by_id = {task.id: task for task in materialized}
        if len(by_id) != len(materialized):
            raise ValueError(
                "ids de tarea duplicados. WHAT: id no unico | WHY: la busqueda por "
                "id seria ambigua | WHERE: SkillLiftCatalog.__init__()"
            )
        if any(not task.id for task in materialized):
            raise ValueError(
                "tarea con id vacio. WHAT: id faltante | WHERE: SkillLiftCatalog.__init__()"
            )
        self._tasks: tuple[LiftTask, ...] = materialized
        self._by_id: dict[str, LiftTask] = by_id

    def get(self, task_id: str) -> LiftTask:
        """Devuelve la tarea por id.

        Args:
            task_id: Identificador de la tarea.

        Returns:
            La :class:`LiftTask` solicitada.

        Raises:
            KeyError: Si ``task_id`` no existe en el catalogo.
        """
        task = self._by_id.get(task_id)
        if task is None:
            raise KeyError(
                f"tarea desconocida '{task_id}'. WHAT: id inexistente en el catalogo "
                "| WHERE: SkillLiftCatalog.get()"
            )
        return task

    def tasks_for_skill(self, skill: str) -> list[LiftTask]:
        """Lista las tareas asociadas a una skill (preserva orden del catalogo).

        Args:
            skill: Nombre de la skill.

        Returns:
            Lista (posiblemente vacia) de tareas de esa skill.
        """
        return [task for task in self._tasks if task.skill == skill]

    def all_tasks(self) -> list[LiftTask]:
        """Devuelve todas las tareas en orden de definicion.

        Returns:
            Copia de la lista de tareas del catalogo.
        """
        return list(self._tasks)

    def skills(self) -> list[str]:
        """Lista las skills presentes en el catalogo (unicas, preservando orden).

        Returns:
            Nombres de skill sin duplicados en orden de primera aparicion.
        """
        seen: dict[str, None] = {}
        for task in self._tasks:
            seen.setdefault(task.skill, None)
        return list(seen)

    def task_ids(self) -> list[str]:
        """Lista los identificadores de todas las tareas.

        Returns:
            Lista de ids en orden de definicion.
        """
        return [task.id for task in self._tasks]


__all__ = [
    "DEFAULT_TASKS",
    "SKILLS_DIR",
    "SKILL_FILE_NAME",
    "LiftTask",
    "SkillLiftCatalog",
    "Verifier",
    "verify_agent_rigor_evidence",
    "verify_architecture_decision",
    "verify_atdd_cycle",
    "verify_data_science_eval",
    "verify_evolve_loop",
    "verify_security_finding",
    "verify_skill_frontmatter",
]
