# Spec — Held-out suite para trabajo de agentes (SpecBench)

## Outcome medible

Un mecanismo que verifica el trabajo de un agente contra tests OCULTOS:
`run_heldout(case_ids)` ejecuta nodos pytest reservados y emite veredicto.
Un fix que pasa lo visible pero falla lo oculto se marca `OVERFIT`.

Criterio de exito: `evaluate_fix(visible_passed=True, heldout=...)` solo
retorna `ACCEPT` si todo lo oculto pasa; y existe un test que demuestra que
ningun modulo de `harness/` (salvo el gate) importa o lee el manifiesto.

## Contexto

SpecBench (arXiv:2605.21384): los tests visibles no equivalen a la intencion.
SWARMIND ya tiene `fix_evidence` (anti-pintar-verde sobre tests visibles);
falta la segunda linea: verificacion contra casos que el agente nunca vio.
Sin esto, un fix puede sobreajustar a lo visible.

## Requisitos funcionales

- FR1: `HeldoutCase(id, node_ids, description)` + `HeldoutSuite(cases)` con
  `run(pytest_args)` que ejecuta los nodos en subproceso y devuelve
  `HeldoutVerdict(case_id, passed, failed_nodes)`.
- FR2: `evaluate_fix(visible_ok, verdicts)` -> `ACCEPT | OVERFIT | INCOMPLETE`
  (INCOMPLETE si algun caso no pudo ejecutarse).
- FR3: aislamiento: test que falla si cualquier `.py` de `harness/` (salvo
  `validation/heldout_suite.py`) referencia la ruta del manifiesto.

## Requisitos no funcionales

- NF1: determinista y sin red; el runner usa `sys.executable -m pytest`.
- NF2: el manifiesto vive en `harness/validation/heldout_manifest.json`
  (versionado, auditable); la politica (no leerlo como agente) se documenta
  en el modulo.

## Invariantes (tests TDD)

1. Caso con nodos que pasan -> veredicto passed.
2. Caso con un nodo que falla -> veredicto failed con el nodo listado.
3. `evaluate_fix(True, [passed])` -> ACCEPT; con un failed -> OVERFIT.
4. Caso no ejecutable -> INCOMPLETE.
5. Ningun modulo de harness/ importa el manifiesto (salvo el gate).

## Fuera de alcance

- Generar los casos ocultos (los provee el guardian como semillas iniciales).
- Juez LLM (eso es T2; esto es T1 determinista).
