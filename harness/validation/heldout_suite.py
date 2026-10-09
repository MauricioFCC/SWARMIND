"""heldout_suite.py — Held-out suite para trabajo de agentes (SpecBench).

WHAT: ejecuta nodos pytest RESERVADOS (que el agente nunca vio) y emite
veredicto por caso; `evaluate_fix` solo acepta si todo lo oculto pasa.
WHY: SpecBench (arXiv:2605.21384): los tests visibles no equivalen a la
intencion; un fix puede sobreajustar a lo visible. Esta es la segunda linea
despues de `fix_evidence` (que cubre lo visible).
WHERE: guardian/CI tras aceptar un fix; manifiesto en
`harness/validation/heldout_manifest.json`.

Politica: ningun modulo de `harness/` (salvo tests y este gate) puede
referenciar la ruta del manifiesto — lo verifica
`test_manifest_not_imported_by_source`.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

#: Manifiesto versionado de casos ocultos (auditable, no leer como agente).
MANIFEST_PATH = Path(__file__).with_name("heldout_manifest.json")

#: Codigo de salida de pytest cuando la corrida fue valida y solo hubo rojos.
#: Cualquier otro (2=interrumpido, 3=error interno, 4=uso, 5=sin tests) implica
#: que los nodos no se ejecutaron: el caso es INCOMPLETE, no OVERFIT.
_FAILED_ONLY_CODES = frozenset({1})

#: Lineas finales de la salida que se citan en el error (contexto accionable).
_ERROR_TAIL_LINES = 3

#: Timeout por defecto de cada corrida pytest de un caso oculto.
DEFAULT_TIMEOUT_S = 120

#: Maximo de caracteres citados en el detalle de error.
ERROR_TAIL_CHARS = 300


@dataclass(frozen=True)
class HeldoutCase:
    """Caso oculto: nodos pytest que deben pasar.

    Attributes:
        id: Identificador estable del caso.
        node_ids: Nodos `path::test` a ejecutar.
        description: Que cubre el caso (sin spoilear el oraculo).
    """

    id: str
    node_ids: tuple[str, ...]
    description: str


@dataclass(frozen=True)
class HeldoutVerdict:
    """Veredicto de un caso.

    Attributes:
        case_id: Caso evaluado.
        passed: True si todos sus nodos pasaron.
        failed_nodes: Nodos que fallaron (vacio si paso).
        error: Detalle si el caso no pudo ejecutarse (INCOMPLETE).
    """

    case_id: str
    passed: bool
    failed_nodes: tuple[str, ...] = ()
    error: str = ""


def load_manifest(path: str | Path = MANIFEST_PATH) -> tuple[HeldoutCase, ...]:
    """Carga casos desde el manifiesto JSON.

    Args:
        path: Ruta del manifiesto.

    Returns:
        Tupla inmutable de casos normalizados.

    Raises:
        ValueError: Si el manifiesto no es JSON valido o le faltan claves
            obligatorias (`id`, `node_ids`).
    """
    manifest = Path(path)
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        return tuple(
            HeldoutCase(
                id=str(item["id"]),
                node_ids=tuple(item["node_ids"]),
                description=str(item.get("description", "")),
            )
            for item in data
        )
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError(f"manifiesto held-out invalido en {manifest}: {exc}") from exc


def _run_nodes(repo_root: Path, nodes: tuple[str, ...], timeout_s: int) -> tuple[bool, tuple[str, ...], str]:
    """Ejecuta nodos pytest en subproceso y clasifica el resultado."""
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *nodes],
            cwd=repo_root, capture_output=True, text=True, timeout=timeout_s,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, nodes, f"no ejecutable: {exc}"
    output = proc.stdout + proc.stderr
    if proc.returncode == 0:
        return True, (), ""
    if proc.returncode not in _FAILED_ONLY_CODES:
        return False, (), f"pytest no ejecuto los nodos (rc={proc.returncode}): {_tail(output)}"
    failed = _failed_nodes(output, nodes)
    if not failed:
        return False, nodes, f"sin nodos fallidos identificables: {_tail(output)}"
    return False, failed, ""


def _tail(output: str) -> str:
    """Resumen compacto de las ultimas lineas de la salida de pytest.

    Args:
        output: Texto combinado de stdout+stderr de pytest.

    Returns:
        Hasta `_ERROR_TAIL_LINES` lineas no vacias, unidas y truncadas.
    """
    lines = [line for line in output.strip().splitlines() if line.strip()]
    return " | ".join(lines[-_ERROR_TAIL_LINES:])[:ERROR_TAIL_CHARS]


def _failed_nodes(output: str, nodes: tuple[str, ...]) -> tuple[str, ...]:
    """Extrae del resumen FAILED los nodos que fallaron por igualdad exacta.

    Comparar por igualdad (y no por substring) evita atribuir el fallo de
    `test_x_extra` al nodo `test_x` cuando uno es prefijo del otro.
    """
    reported = {
        line.split("FAILED", 1)[1].strip().split(" - ", 1)[0].strip()
        for line in output.splitlines() if "FAILED" in line
    }
    return tuple(node for node in nodes if node in reported)


@dataclass(frozen=True)
class HeldoutSuite:
    """Suite de casos ocultos sobre un arbol.

    Attributes:
        cases: Casos a ejecutar.
        repo_root: Directorio donde corre pytest.
        timeout_s: Timeout por caso.
    """

    cases: Sequence[HeldoutCase]
    repo_root: Path
    timeout_s: int = DEFAULT_TIMEOUT_S

    def run(self) -> list[HeldoutVerdict]:
        """Ejecuta cada caso y devuelve sus veredictos (uno por caso)."""
        verdicts: list[HeldoutVerdict] = []
        for case in self.cases:
            passed, failed, error = _run_nodes(self.repo_root, case.node_ids, self.timeout_s)
            verdicts.append(HeldoutVerdict(case.id, passed, failed, error))
        return verdicts


def evaluate_fix(visible_ok: bool, verdicts: Sequence[HeldoutVerdict]) -> str:
    """Veredicto final del fix.

    Args:
        visible_ok: True si lo visible (fix_evidence) paso.
        verdicts: Veredictos de los casos ocultos.

    Returns:
        "ACCEPT" (todo verde), "OVERFIT" (visible ok pero oculto rojo, o
        visible rojo) o "INCOMPLETE" (algun caso no ejecutable o sin casos).
        Un conjunto vacio de casos es INCOMPLETE: sin oraculo oculto no se
        puede aceptar nada (evita el ACCEPT vacuo).
    """
    if not verdicts:
        return "INCOMPLETE"
    if any(v.error for v in verdicts):
        return "INCOMPLETE"
    if not visible_ok or any(not v.passed for v in verdicts):
        return "OVERFIT"
    return "ACCEPT"
