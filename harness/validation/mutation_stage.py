"""
Mutation Testing Stage — CDBench-style mutation testing for LLM-generated code
(ADR-0041 H3: durable execution & gate enforcement).

Inspirado en CDBench (Springer 2026-06-13): zero-sum 'Code Defenders' game donde
el attacker muta un fragmento de código y el defensor crea una assertion/test que
lo mata. Reporta 'kill rate' quantitativo para cada ronda de code generation.

Flujo Swarmind (oraculo mecanico, nunca un LLM juzgando a otro):
  1. Agent genera código Python.
  2. Mutation stage muta N variantes del código (operadores aritmeticos,
     comparacion, booleanos, literales) aplicando la mutacion REAL al AST.
  3. Se ejecuta el test del usuario (o un differential test de stdout) contra
     cada mutante en subprocess aislado con timeout.
  4. Test pasa sobre el original y falla sobre el mutante -> 'mutante muerto' (kill).
  5. Test pasa sobre ambos -> 'mutante sobreviviente' (escape).
  6. Kill rate = mutantes muertos / total mutantes.

Seguridad (SEG): NUNCA se usa exec()/eval() en el proceso principal; cada
mutante se ejecuta en subprocess aislado desde un archivo temporal
(tempfile.TemporaryDirectory), nunca /tmp hardcodeado (ADR-0035 paths portables).

Referencias:
  - CDBench: 2,636 mutated variants, 9 languages. LLM verification rate 10.20%.
  - Swarmind mutation strategy: reduce detection rate 71.04% → 39.81%.
  - PROBE/AdverTest: adversarial testing loop generator↔validator.
"""

from __future__ import annotations

import ast
import logging
import random
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes (sin magic numbers)
# ---------------------------------------------------------------------------

# Maximo de tipos de mutacion probados por nodo (0..5)
MAX_MUTATION_TYPES: int = 6

# Timeout de ejecucion de cada mutante (segundos)
EXEC_TIMEOUT_S: float = 5.0

# Operadores aritmeticos alternativos al mutar un BinOp
ARITHMETIC_ALTERNATIVES: tuple[str, ...] = ("+", "-", "*", "/", "%")

# Mapeo de operadores de comparacion mutados
COMPARE_MUTATIONS: dict[type, tuple[Any, ...]] = {
    ast.Eq: (ast.NotEq(), ast.Lt(), ast.Gt()),
    ast.NotEq: (ast.Eq(),),
    ast.Lt: (ast.Gt(), ast.LtE(), ast.GtE()),
    ast.LtE: (ast.Gt(), ast.Lt()),
    ast.Gt: (ast.Lt(), ast.GtE(), ast.LtE()),
    ast.GtE: (ast.Lt(), ast.Gt()),
}

# ---------------------------------------------------------------------------
# Tipos de nodos mutables
# ---------------------------------------------------------------------------

MUTABLE_NODE_TYPES: tuple[type[ast.AST], ...] = (
    ast.BinOp,     # operacion binaria (a + b)
    ast.Compare,   # comparacion (a > b)
    ast.BoolOp,    # and / or
    ast.UnaryOp,   # not, -x
    ast.Constant,  # literal (1, "hola", True)
)


def _mutate_node(node: ast.AST, mutation_idx: int) -> ast.AST | None:
    """Aplica una mutacion REAL a un nodo AST segun su tipo.

    Args:
        node: Nodo AST original a mutar.
        mutation_idx: Indice de tipo de mutacion (0..5).

    Returns:
        Nodo mutado, o None si este tipo de mutacion no aplica al nodo.
    """
    mut_type = mutation_idx % MAX_MUTATION_TYPES

    if mut_type == 0 and isinstance(node, ast.BinOp):
        # Cambiar operador binario (excluyendo el original)
        current = _binop_symbol(node.op)
        alternatives = [
            op for op in ARITHMETIC_ALTERNATIVES if op != current
        ]
        if not alternatives:
            return None
        return ast.BinOp(
            left=node.left,
            op=_make_binop(random.choice(alternatives)),
            right=node.right,
        )

    if mut_type == 1 and isinstance(node, ast.Compare):
        # Cambiar operador de comparacion por uno distinto
        if not node.ops:
            return None
        original_op = type(node.ops[0])
        alternatives = COMPARE_MUTATIONS.get(original_op)
        if not alternatives:
            return None
        new_ops = list(node.ops)
        new_ops[0] = random.choice(alternatives)
        return ast.Compare(left=node.left, ops=new_ops, comparators=node.comparators)

    if mut_type == 2 and isinstance(node, ast.BoolOp):
        # Cambiar and por or o viceversa
        new_op = ast.Or() if isinstance(node.op, ast.And) else ast.And()
        return ast.BoolOp(op=new_op, values=node.values)

    if mut_type == 3 and isinstance(node, ast.UnaryOp):
        # Cambiar not por negativo o viceversa
        new_op = ast.USub() if isinstance(node.op, ast.Not) else ast.Not()
        return ast.UnaryOp(op=new_op, operand=node.operand)

    if mut_type == 4 and isinstance(node, ast.Constant):
        # Cambiar literal: 1 -> 0, True -> False, etc.
        val = node.value
        if isinstance(val, bool):
            new_val = not val
        elif isinstance(val, (int, float)):
            new_val = val + random.choice((-1, 1))
        else:
            new_val = val
        if new_val == val:
            return None
        return ast.Constant(value=new_val)

    return None


def _binop_symbol(op_node: ast.operator) -> str:
    """Devuelve el simbolo del operador binario ("+", "-", ...)."""
    symbols: dict[type[ast.operator], str] = {
        ast.Add: "+",
        ast.Sub: "-",
        ast.Mult: "*",
        ast.Div: "/",
        ast.Mod: "%",
    }
    return symbols.get(type(op_node), "+")


def _make_binop(op_name: str) -> ast.operator:
    """Crea un nodo ast.operator a partir de un nombre de operador.

    Args:
        op_name: Nombre del operador ("+", "-", "*", "/", "%").

    Returns:
        Nodo ast.operator correspondiente.
    """
    operators: dict[str, type[ast.operator]] = {
        "+": ast.Add,
        "-": ast.Sub,
        "*": ast.Mult,
        "/": ast.Div,
        "%": ast.Mod,
    }
    cls = operators.get(op_name, ast.Add)
    return cls()  # type: ignore[no-any-return]


def _replace_node(tree: ast.Module, original: ast.AST, replacement: ast.AST) -> None:
    """Reemplaza un nodo por su mutante dentro del árbol (mutacion real).

    Recorre el arbol y sustituye la primera ocurrencia idéntica del nodo
    original por el reemplazo. Al ser nodos con la misma identidad por
    estructura, se usa el parent tracking via ast.walk + filtrado por tipo.

    Args:
        tree: Arbol AST del codigo fuente.
        original: Nodo a reemplazar.
        replacement: Nodo mutado que lo sustituye.
    """
    for parent in ast.walk(tree):
        for field_name, field_value in ast.iter_fields(parent):
            if field_value is original:
                setattr(parent, field_name, replacement)
                return
            if isinstance(field_value, list):
                for i, item in enumerate(field_value):
                    if item is original:
                        field_value[i] = replacement
                        return


def mutate_source(source: str, num_mutants: int = 5) -> list[str]:
    """
    Genera N variantes mutadas REALES del codigo fuente Python.

    Aplica cada mutacion al AST (reemplazo real del nodo) y re-serializa el
    arbol mutado. Los mutantes resultantes SIEMPRE difieren del original.

    Args:
        source: Código fuente Python (string).
        num_mutants: Numero de mutantes a generar (default 5).

    Returns:
        Lista de strings con codigo mutado (diferente del original).

    Raises:
        ValueError: Si source está vacío o no es str.
    """
    if not isinstance(source, str) or not source.strip():
        raise ValueError(
            "source must be a non-empty string. "
            "WHY: Sin codigo fuente no hay nodos que mutar. "
            "WHERE: mutation_stage.mutate_source"
        )
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        logger.error(
            "Invalid Python source for mutation (WHAT=parse_error WHY=%s "
            "WHERE=mutate_source)", e,
        )
        return []

    mutants: list[str] = []
    seen: set[str] = set()

    mutable_nodes: list[ast.AST] = [
        node for node in ast.walk(tree) if isinstance(node, MUTABLE_NODE_TYPES)
    ]
    if not mutable_nodes:
        logger.warning("No mutable nodes found in source")
        return []

    sampled_count = min(len(mutable_nodes), num_mutants)
    sampled_nodes = random.sample(mutable_nodes, sampled_count)

    for original_node in sampled_nodes:
        for mut_idx in range(MAX_MUTATION_TYPES):
            mutated = _mutate_node(original_node, mut_idx)
            if mutated is None:
                continue

            # Aplicar mutacion REAL al arbol (copia para no contaminar)
            import copy

            tree_copy = copy.deepcopy(tree)
            # Encontrar el nodo equivalente en la copia por tipo+posicion
            original_in_copy = _find_equivalent(tree_copy, original_node)
            if original_in_copy is None:
                continue
            _replace_node(tree_copy, original_in_copy, mutated)

            try:
                new_source = ast.unparse(ast.fix_missing_locations(tree_copy))
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "Mutation unparse failed (WHAT=unparse_error WHY=%s "
                    "WHERE=mutate_source)", e,
                )
                continue

            # Solo mutantes que realmente difieren del original (sin duplicados)
            if new_source != source and new_source not in seen:
                seen.add(new_source)
                mutants.append(new_source)
                break  # un mutante por nodo

    return mutants


def _find_equivalent(tree: ast.Module, original: ast.AST) -> ast.AST | None:
    """Localiza en la copia del arbol el nodo equivalente al original.

    Usa type + col_offset + lineno como identidad estructural estable
    (deepcopy preserva los offsets del arbol original).

    Args:
        tree: Arbol AST copiado.
        original: Nodo original (del arbol sin copiar).

    Returns:
        Nodo equivalente en el arbol copiado, o None.
    """
    target = (type(original), getattr(original, "lineno", None),
              getattr(original, "col_offset", None))
    for node in ast.walk(tree):
        if (
            type(node) is target[0]
            and getattr(node, "lineno", None) == target[1]
            and getattr(node, "col_offset", None) == target[2]
        ):
            return node
    return None


def _run_in_subprocess(code: str) -> tuple[int, str]:
    """Ejecuta codigo Python en subprocess aislado desde archivo temporal.

    Args:
        code: Codigo Python completo (source + test).

    Returns:
        (returncode, stdout+stderr combinado).

    Raises:
        TimeoutExpired: Si la ejecucion excede EXEC_TIMEOUT_S.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        script_path = Path(tmp_dir) / "mutant_check.py"
        script_path.write_text(code, encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            timeout=EXEC_TIMEOUT_S,
            check=False,
        )
        return result.returncode, (result.stdout + result.stderr)


def run_mutation_stage(
    source: str,
    agent_name: str,
    num_mutants: int = 5,
    test_source: str | None = None,
) -> dict[str, Any]:
    """
    Ejecuta el stage de Mutation Testing sobre el codigo generado.

    Flujo (oraculo mecanico):
      1. Generar N mutantes REALES del source (mutate_source).
      2. Baseline: ejecutar source + test -> debe pasar (returncode 0).
      3. Para cada mutante: ejecutar mutante + test en subprocess aislado.
         - Test falla sobre mutante (returncode != 0) -> KILLED.
         - Test pasa sobre mutante -> ESCAPED.
      4. Si no hay test_source, se usa differential testing de stdout:
         mutante con stdout != baseline -> KILLED.

    Args:
        source: Código fuente Python a testear.
        agent_name: Nombre del agente generador (para logging).
        num_mutants: Numero de mutantes a generar (default 5).
        test_source: Codigo del test/assertion del usuario. Si es None,
            se usa differential testing de stdout.

    Returns:
        Dict con reporte de mutation testing:
        {
            "kill_rate": float,  # mutantes muertos / total
            "total_mutants": int,
            "killed_mutants": int,
            "escaped_mutants": int,
            "mutant_details": [
                {"mutant_idx": i, "killed": bool, "mutant_source": "...", "error": "..."}
            ]
        }
    """
    logger.info(
        "Running mutation stage for agent=%s (mutants=%d)", agent_name, num_mutants
    )

    mutants = mutate_source(source, num_mutants)
    total = len(mutants)

    if total == 0:
        return {
            "kill_rate": 0.0,
            "total_mutants": 0,
            "killed_mutants": 0,
            "escaped_mutants": 0,
            "mutant_details": [],
            "note": "No se pudieron generar mutantes.",
        }

    # Baseline: el source + test debe ejecutar sin error
    baseline_code = source
    if test_source:
        baseline_code = f"{source}\n\n# === TEST ===\n{test_source}\n"
    baseline_rc, baseline_out = _run_in_subprocess(baseline_code)

    killed = 0
    escaped = 0
    details: list[dict[str, Any]] = []

    for i, mutant_source in enumerate(mutants):
        mutant_code = mutant_source
        if test_source:
            mutant_code = f"{mutant_source}\n\n# === TEST ===\n{test_source}\n"
        error_msg = ""
        try:
            mut_rc, mut_out = _run_in_subprocess(mutant_code)
        except subprocess.TimeoutExpired:
            # Timeout del mutante = comportamiento distinto -> killed
            killed += 1
            killed_flag = True
            error_msg = "timeout"
        except Exception as e:  # noqa: BLE001
            killed += 1
            killed_flag = True
            error_msg = f"{type(e).__name__}: {e}"[:100]
        else:
            if test_source:
                # Oráculo por test: baseline pasa y mutante falla -> killed
                killed_flag = baseline_rc == 0 and mut_rc != 0
            else:
                # Oráculo differential: stdout distinto al baseline -> killed
                killed_flag = baseline_out != mut_out
            if killed_flag:
                killed += 1
            else:
                escaped += 1

        details.append(
            {
                "mutant_idx": i,
                "killed": killed_flag,
                "mutant_source": mutant_source[:100]
                + ("..." if len(mutant_source) > 100 else ""),
                "error": error_msg,
            }
        )

    kill_rate = killed / total if total > 0 else 0.0

    report: dict[str, Any] = {
        "kill_rate": kill_rate,
        "total_mutants": total,
        "killed_mutants": killed,
        "escaped_mutants": escaped,
        "mutant_details": details,
    }

    logger.info(
        "Agent %s mutation stage complete: kill_rate=%.2f (%d/%d killed)",
        agent_name,
        kill_rate,
        killed,
        total,
    )

    return report
