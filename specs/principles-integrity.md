# Spec: Integridad de principios (herencia de skills + N1/N3 + ADR-0098 formal)

- **Estado:** propuesta + tests GREEN (2026-10-08; WS-1/WS-2/WS-3 integrados)
- **Principios rectores:** `SPE` (Spec-First / Proof-or-Stop) + `TST` (TDD adversarial/mutante) + `GATE` (Evidence-Gated) + `IDP` (Idempotencia)
- **Alcance (3 workstreams en paralelo):**
  - **WS-1** Herencia real de skills: `harness/context/skill_inherit.py` + `inherit:` en `.opencode/skills/**/SKILL.md`.
  - **WS-2** N3 sin drift: `.opencode/core/base_principles_full.md` (solo N3, `version` == base).
  - **WS-3** ADR-0098 formal: `docs/adr/adr-0098-*.md` (Status/Date/Contexto/Decision/Consecuencias).
- **Verificador:** `harness/tests/test_principles_integrity.py` (solo-lectura; sin red; sin subprocess).

---

## 1. Problema (WHY)

La "integridad de principios" del harness tenia tres grietas independientes:

1. **`inherit:` inerte.** El frontmatter de las skills declaraba dependencias
   (`core/base_principles.md`, `core/fde_principles.md`) que nadie resolvia ni
   validaba: una ruta inexistente pasaba desapercibida (integridad referencial
   rota). Frontera 2026 (Anthropic Agent Skills + progressive disclosure): la
   herencia debe ser **verificable y fail-fast**, no decorativa.
2. **Drift de las copias de principios.** `base_principles.md` (N1+N2, `3.5.0`)
   y `base_principles.min.md` (N1, `3.5.0`) avanzaron, pero
   `base_principles_full.md` quedo en `2.7.0` y conservo un N1 antiguo con el
   token `SEG: 0 secrets | validate input` — regla ya migrada a `VAL`
   (ADR-0098). Sin un gate determinista, las tres copias divergen en silencio.
3. **ADR no formal.** `docs/adr/adr-0098-*.md` contiene un documento tipo
   AGENTS.md pegado, sin las secciones canonicas de un ADR (Nygard):
   Status/Date/Contexto/Decision/Consecuencias. Sin ellas no es trazable ni
   auditable.

**Hipotesis:** con `inherit:` resuelto + validado y con tests de fitness
deterministas (referenciales, anti-drift de version, anti-drift de codigos N1,
token obsoleto, formato de ADR) las tres grietas se vuelven **verificables sin
LLM juez** (`GATE` T1).

---

## 2. Outcome medible (que es "hecho")

1. **Herencia referencial:** `validate_inherit_corpus(skills, .opencode) == []`
   y toda ruta declarada en `inherit:` existe bajo `.opencode/`.
2. **Version coherente:** `version(base_principles.md)` ==
   `version(base_principles_full.md)` == `version(base_principles.min.md)`.
3. **Cero token N1 obsoleto:** ninguna de las 3 copias contiene una linea
   `SEG:` con el fragmento `validate input` (migrado a `VAL`).
4. **ADR formal:** cada `docs/adr/adr-0098-*.md` contiene Status, Date,
   Contexto, Decision y Consecuencias.
5. **Anti-drift N1:** el conjunto de codigos N1 de `full.md` == `base.md` ==
   `min.md`.
6. La suite `harness/tests/test_principles_integrity.py` pasa **GREEN** con
   asserts mutation-style que demuestran el poder discriminante de los checkers.

---

## 3. Requisitos funcionales (FR)

- **FR-1 (WS-1):** resolver `inherit:` con `parse_inherit` / `resolve_inherit` /
  `validate_inherit_corpus`, fail-fast ante ruta ausente y path traversal.
- **FR-2 (WS-1):** el test recorre `.opencode/skills/**/SKILL.md`, extrae
  `inherit:` (reutilizando el resolver; fallback a parser propio) y verifica
  que cada ruta existe bajo `.opencode/`.
- **FR-3 (WS-2):** alinear `base_principles_full.md` a N3 puro (bloque N1
  sincronizado con base) y `version` == `3.5.0`.
- **FR-4 (WS-2):** eliminar de `full.md` el token obsoleto
  `SEG: 0 secrets | validate input`, preservando la regla
  canonica de `SEG` y la de `VAL`.
- **FR-5 (WS-3):** normalizar `docs/adr/adr-0098-*.md` a ADR formal con las 5
  secciones canonicas.
- **FR-6:** tests mutation-style que matan al mutante: (a) borrar una linea N1
  de `min`, (b) romper un `inherit:` a un path inexistente, (c) desincronizar
  una `version`.

> Nota (FR-4): el token exacto bajo vigilancia es
> `SEG: 0 secrets | validate input`. Se escribe aqui sin ambiguedad: la suite
> detecta cualquier linea N1 que empiece con `SEG:` y contenga
> `validate input`.

## 4. Requisitos no funcionales (NF)

- **NF-1 (solo-lectura):** la suite no edita produccion; solo lee/valida.
- **NF-2 (sin red):** cero llamadas de red y cero subprocess.
- **NF-3 (determinismo):** sin dependencias de tiempo/orden/sistema de archivos
  global (usar `tmp_path` para mutaciones).
- **NF-4 (docstrings):** docstrings ES (UTF-8), patron AAA, type hints.
- **NF-5 (idempotencia):** re-ejecutar la suite no muta archivos (`IDP`).
- **NF-6 (errores):** mensajes de fallo con que/por que/donde (WHAT+WHY+WHERE).

---

## 5. Invariantes y diseno

| # | Invariante | Checker | Test |
|---|-----------|---------|------|
| I1 | Toda ruta `inherit:` existe bajo `.opencode/` | `validate_inherit_corpus` (resolver) | `test_all_skills_inherit_paths_exist` |
| I2 | `version(full) == version(base) == version(min)` | `_frontmatter_version` + `_assert_same_version` | `test_full_and_base_versions_consistent` |
| I3 | Cero `SEG:` con `validate input` en base/min/full | `_stale_seg_lines` | `test_no_stale_n1_anywhere` |
| I4 | ADR-0098 con 5 secciones formales | `_missing_adr_sections` | `test_adr0098_formal` |
| I5 | Set de codigos N1 full == base == min | `_n1_codes` + `_assert_same_n1_codes` | `test_no_duplicate_n1_across_files` |

**Reutilizacion (`IDP`):** el resolver `harness/context/skill_inherit.py` ya
existe; la suite lo importa y solo cae a un parser propio si el modulo no esta
disponible. No se reimplementa la resolucion.

**Contrato mutation-style:** los checkers se extraen a funciones puras
(`_assert_same_n1_codes`, `_inherit_corpus_errors`, `_assert_same_version`,
`_stale_seg_lines`, `_missing_adr_sections`) para poder alimentarlos con
entradas mutadas sin tocar produccion.

---

## 6. Exit criteria (Evidence-Gated, `GATE`)

- [x] Spec SDD redactada (este archivo).
- [x] `harness/tests/test_principles_integrity.py` escrito con los 5 tests de
  invariantes + asserts mutation-style.
- [x] `uv run ruff check harness/tests/test_principles_integrity.py` -> 0 errores
  (`All checks passed!`).
- [x] `uv run python -m pytest harness/tests/test_principles_integrity.py -q` -> GREEN
  (`10 passed in 0.62s`; WS-1/WS-2/WS-3 integrados).
- [x] `validate_inherit_corpus` sin errores sobre el corpus real (I1).
- [x] `version(full) == 3.5.0` y sin token obsoleto (I2/I3).
- [x] ADR-0098 con las 5 secciones (I4).
- [x] Anti-drift N1 base/min/full (I5).
- [x] Mutation-style: los checkers rechazan (a) N1 sin linea, (b) inherit roto,
  (c) version desincronizada.

## 7. Sandbox y rollback

- **Sandbox (`SBX`):** solo se crean/editan `specs/principles-integrity.md` y
  `harness/tests/test_principles_integrity.py`. **No** se toca produccion
  (`.opencode/core/*.md`, `harness/context/skill_inherit.py`, ADRs).
- **Sin red / sin procesos reales:** la unica dependencia externa es importar
  `harness.context.skill_inherit` (ya en el repo).
- **Rollback:** eliminar los dos artefactos creados; nada mas queda afectado.
  Los cambios de produccion de WS-1/WS-2/WS-3 los revierte `git revert` de sus
  propios commits.

---

## 8. Tareas (tasks)

- [x] **T1** Investigar estado real (`RSF`, `IDP`): resolver, copias N1/N3, ADR.
- [x] **T2** Escribir este spec SDD.
- [x] **T3** Escribir `harness/tests/test_principles_integrity.py` (RED esperado).
- [x] **T4** Cerrar WS-1/WS-2/WS-3 (otros agentes, en paralelo).
- [x] **T5** Verificar GREEN + mutation-style; registrar evidencia cruda.
- [ ] **T6** Commit `test(principles): integridad de principios ...` (`CMT`, `ATM`).

---

## 9. Verificacion y mutation testing

**Comandos deterministas:**
```powershell
uv run ruff check harness/tests/test_principles_integrity.py
uv run python -m pytest harness/tests/test_principles_integrity.py -q
```

**Mutation testing — intento y resultado:**
```powershell
uvx mutmut --version
# -> "To run mutmut on Windows, please use the WSL. Native windows support is tracked in issue https://github.com/boxed/mutmut/issues/397"
```
`mutmut` **no es viable en Windows nativo** (requiere WSL). Mitigacion
equivalente: asserts **mutation-style** que prueban el poder discriminante de
cada checker sin tocar produccion:

1. `test_mutation_detects_removed_n1_line` (mata al que borra `VAL:` de `min`).
2. `test_mutation_rejects_broken_inherit_path` (mata al que rompe un `inherit:`).
3. `test_mutation_detects_version_mismatch` (mata al que desincroniza `version`).
4. `test_stale_checker_detects_and_ignores` (detecta el token obsoleto sin
   falsos positivos).
5. `test_mutation_adr_missing_section_detected` (mata al que omite una seccion).

**Evidencia cruda (2026-10-08):**
```text
$ uv run ruff check harness/tests/test_principles_integrity.py
All checks passed!

$ uv run python -m pytest harness/tests/test_principles_integrity.py -q
..........                                                               [100%]
10 passed in 0.62s

$ uvx mutmut --version
To run mutmut on Windows, please use the WSL. Native windows support is tracked in issue https://github.com/boxed/mutmut/issues/397
```
Nota: WS-1/WS-2/WS-3 ya estaban integrados al ejecutar la suite, por lo que
el estado final es GREEN (no RED). Los asserts mutation-style se validaron
dentro de la propia suite (10/10).

---

## 10. Anti-patrones (prohibidos)

- Ablandar los tests para "pintar verde" cuando estan RED (`VER` anti-patron).
- Editar produccion desde la suite (viola `SBX`/`NF-1`).
- Reimplementar la resolucion de `inherit:` en vez de reutilizar el resolver (`IDP`).
- Usar red o subprocess en la suite (`NF-2`).
- Aceptar un ADR sin secciones o una copia de principios con drift silencioso.

## 11. Fuentes

- `harness/context/skill_inherit.py` (resolver real, frontmatter `inherit:`).
- `harness/tests/test_skill_inherit.py` (tests del resolver; `IDP`: no se duplican).
- `.opencode/core/base_principles.md` (N1+N2, `3.5.0`).
- `.opencode/core/base_principles.min.md` (N1, `3.5.0`).
- `.opencode/core/base_principles_full.md` (N3; hoy `2.7.0` — drift).
- `docs/adr/adr-0098-Convenciones-codigo-principios-doce.md` (ADR interno).
- `specs/adr0098-principles.md` (spec hermana: promocion ADR-0098 a N1).