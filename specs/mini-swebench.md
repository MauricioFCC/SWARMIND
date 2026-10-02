# Spec — Mini-SWE-bench interno (benchmark de fixes con issues reales)

## Outcome medible

Formato de instancias + runner que evalua un fix contra FAIL_TO_PASS y
PASS_TO_PASS reales, y valida la calidad del oraculo inyectando la falla
(modo mutante). Metrica: `resolve-rate` + `oracle-quality`.

Criterio de exito: `run_instance` reporta `RESOLVED` en el arbol sano,
`UNRESOLVED` con la falla inyectada, y `evaluate_patch` acepta un parche
bueno y rechaza uno que rompe PTP. Semillas: 3 fixes reales del repo.

## Contexto

SWE-bench (arXiv:2310.06770): FAIL_TO_PASS/PASS_TO_PASS sobre issues
reales. R2E-Gym: verifiers hibridos + entornos sinteticos. SWARMIND mide
mutation score pero no tiene benchmark de fixes end-to-end ni validacion de
que sus tests cazarían la regresion (oracle-quality). Este modulo es el
mini-benchmark honesto: pocas instancias reales + modo mutante que prueba
los tests, no solo el codigo.

## Requisitos funcionales

- FR1: `SWEInstance(id, issue, fail_to_pass, pass_to_pass, fault)` donde
  `fault = FaultSpec(file, old, new)` (reemplazo de texto reversible).
- FR2: `validate_oracle(instance, repo_root)` -> inyecta la falla (con
  restore en `finally`), corre FTP (espera >=1 fallo), restaura, corre
  FTP+PTP (espera todo verde). Reporta `ORACLE_OK | ORACLE_WEAK | ERROR`.
- FR3: `evaluate_patch(instance, patch_text, repo_root)` -> aplica el parche
  con `git apply` (restore despues), corre FTP+PTP, reporta
  `RESOLVED | UNRESOLVED | ERROR`.
- FR4: `MINI_SWE_BENCH`: 3 instancias de fixes reales del repo con sus
  nodos de test.

## Requisitos no funcionales

- NF1: usa `sys.executable -m pytest -q` en subproceso con timeout.
- NF2: restore garantizado (`try/finally` + `git checkout --` si aplica).

## Invariantes (tests TDD, sobre repo fixture en tmp_path)

1. `validate_oracle` con falla que rompe el test -> ORACLE_OK.
2. `validate_oracle` con falla que NO rompe nada -> ORACLE_WEAK.
3. `evaluate_patch` con parche bueno -> RESOLVED.
4. `evaluate_patch` con parche que rompe PTP -> UNRESOLVED.
5. Restore: el fixture queda intacto tras cada modo (hash igual).

## Fuera de alcance

- Dataset de 40-60 issues (esto es la infraestructura + 3 semillas).
- Ejecucion en Docker (corre en el arbol local; sandbox es otra capa).
