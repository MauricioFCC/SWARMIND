# Spec: ADR-0098 — Convenciones de código como principios base (CLA, VAL, FST, AAA, ATM)

- **Estado:** propuesta + test RED (2026-10-08)
- **Principio rector:** `SPE` (Spec-First / Proof-or-Stop) + `TST` (TDD adversarial/mutante)
- **ADR de origen:** ADR-0098 (`.opencode/core/base_principles.md`, taxonomía ARC/SEC/GOV/QLT/PRC)
- **Alcance:** `.opencode/core/base_principles.md` (N1 + taxonomía + N2), `.opencode/core/base_principles.min.md` (N1), `.opencode/core/base_principles_full.md` (N3), `.opencode/agents/*.md`, `.opencode/core/base_skill_template.md`
- **Relación:** consume `DOC`, `SVE`, `GATE`, `VAL`, `FST`, `AAA`, `ATM`; verificada por `harness/tests/test_principles_adr0098.py`

---

## 1. Problema (WHY)

El ADR-0098 define 5 convenciones de código (Clean Architecture, validación de
input, fail-fast tipado, patrón AAA y cambios atómicos) que **no están
promovidas a los principios base** (`N1`/`N2`/`N3`). Sin promoción:

- Los agentes y skills no citan las reglas por ID (`CLA`, `VAL`, `FST`, `AAA`, `ATM`).
- La taxonomía de adherencia queda incompleta (ARC/SEC/GOV/QLT/PRC sin estas reglas).
- No hay un gate determinista que impida que el N1 y su versión `min.md` diverjan (drift).
- La versión del principio (`3.4.0`) no refleja la doctrina vigente.

**Hipótesis:** promover los 5 códigos con tests de fitness deterministas
(integridad, anti-drift, atomicidad, presupuesto de líneas) elimina el drift y
hace verificable la adherencia sin depender de un LLM juez.

---

## 2. Outcome medible (qué es "hecho")

1. El bloque **N1** de `base_principles.md` contiene las 5 líneas `CLA:`, `VAL:`, `FST:`, `AAA:`, `ATM:`.
2. La **taxonomía** asigna `CLA→ARC`, `VAL→SEC`, `FST→GOV`, `AAA→QLT`, `ATM→PRC`.
3. El conjunto de códigos **N1 de `min.md` == N1 de `base_principles.md`** (anti-drift).
4. El frontmatter `version` de `base_principles.md` y `min.md` es `>= 3.5.0`.
5. **Cada** `.opencode/agents/*.md` (excluyendo `*.agent.min.md`) referencia `ADR-0098`.
6. `python scripts/validate_skills.py --strict` termina con **exit 0**.
7. La suite `harness/tests/test_principles_adr0098.py` pasa **GREEN** con mutation-style asserts que demuestran poder discriminante.

---

## 3. Requisitos funcionales (FR)

- **FR-1**: `base_principles.md` — añadir los 5 códigos al bloque N1 con línea atómica (sin " y "/" and ").
- **FR-2**: `base_principles.md` — registrar los 5 códigos en la tabla de taxonomía, en la categoría correcta (ARC/SEC/GOV/QLT/PRC) y modo `CHECK`.
- **FR-3**: `base_principles.md` — añadir la fila/entrada correspondiente en N2.
- **FR-4**: `base_principles.min.md` — replicar EXACTAMENTE los códigos de N1 (mismo conjunto).
- **FR-5**: `base_principles_full.md` — documentar los 5 códigos en el checklist N3.
- **FR-6**: cada agente `.opencode/agents/<name>.md` recibe una fila `ADR-0098`.
- **FR-7**: `base_skill_template.md` menciona `ADR-0098`.
- **FR-8**: bump de `version` a `3.5.0` en `base_principles.md` y `min.md`.

## 4. Requisitos no funcionales (NF)

- **NF-1 (atomicidad)**: las 5 líneas N1 nuevas son criterios atómicos (`NAM`/`DRFR`: 1 regla = 1 criterio).
- **NF-2 (anti-bloat)**: el bloque N1 no excede **60 líneas** tras la adición.
- **NF-3 (no-drift)**: N1 de `min.md` y `base_principles.md` son idénticos en conjunto de códigos.
- **NF-4 (idempotencia)**: re-ejecutar la suite no muta archivos; solo lee.
- **NF-5 (determinismo)**: el único proceso externo permitido es `validate_skills.py --strict`; sin red.
- **NF-6 (docstrings)**: el test usa docstrings ES, AAA y type hints.

---

## 5. Diseño (mapping canónico)

| Código | Categoría | Nombre de la regla | Fuente ADR-0098 | Verificación |
|:------:|:---------:|--------------------|:---------------:|:-------------|
| **CLA** | ARC | Clean Architecture (Presentation→Application→Domain←Infrastructure) | §1.1 | `test_base_principles_n1_has_adr0098_codes`, `test_taxonomy_maps_adr0098_codes` |
| **VAL** | SEC | Input Validation (todo input externo validado contra schema) | §4.3 | idem |
| **FST** | GOV | Fail-Fast tipado (error tipado con cause + contexto) | §2.2.A | idem |
| **AAA** | QLT | Test AAA (Arrange-Act-Assert, 1 test = 1 criterio) | §3.2 | idem |
| **ATM** | PRC | Atomic Changes (1 commit/PR = 1 preocupación lógica) | §0.3 | idem |

Archivos y workstreams paralelos (asumidos completos al cierre):

- **WS-A (principios):** `base_principles.md`, `base_principles.min.md`, `base_principles_full.md`.
- **WS-B (agentes/template):** `.opencode/agents/*.md`, `base_skill_template.md`.
- **WS-C (guardian, este):** `specs/adr0098-principles.md` + `harness/tests/test_principles_adr0098.py`.

---

## 6. Exit criteria (Evidence-Gated, `GATE`)

- [ ] `uv run ruff check harness/tests/test_principles_adr0098.py` → 0 errores.
- [ ] `uv run python -m pytest harness/tests/test_principles_adr0098.py -q` → GREEN.
- [ ] Bloque N1 contiene los 5 códigos (`CLA:`, `VAL:`, `FST:`, `AAA:`, `ATM:`).
- [ ] Taxonomía asigna cada código a su categoría.
- [ ] `min.md` N1 == `base_principles.md` N1 (anti-drift).
- [ ] `version >= 3.5.0` en ambos archivos.
- [ ] 100% de agentes `.md` (no `.agent.min.md`) contienen `ADR-0098`.
- [ ] `python scripts/validate_skills.py --strict` → exit 0.
- [ ] N1 <= 60 líneas; sin códigos duplicados; 5 líneas atómicas.
- [ ] Mutation-style: el checker RECHAZA un N1 sin `CLA` y una taxonomía con `CLA` mal asignada.

## 7. Sandbox y rollback

- **Sandbox (`SBX`)**: solo se editan/escriben `.opencode/core/*.md`,
  `.opencode/agents/*.md`, `.opencode/core/base_skill_template.md`,
  `specs/` y `harness/tests/test_principles_adr0098.py`. **No** se toca código
  de producción (`harness/` fuera de tests). Sin red; único subprocess:
  `validate_skills.py --strict` (timeout 120s).
- **Rollback**: los cambios son aditivos (principios + tests). `git revert` del
  commit de integración restaura `3.4.0`; borrar el test no rompe nada más.
  Plan B: si mutmut no es viable (Windows), los mutation-style asserts son el
  oráculo sustituto (documentado en §9).

---

## 8. Tareas (tasks)

- [x] **T1** Investigar estado de N1/N2/N3, agentes y `validate_skills.py` (`RSF`, `IDP`).
- [x] **T2** Escribir spec SDD (este archivo).
- [x] **T3** Escribir `harness/tests/test_principles_adr0098.py` (RED esperado).
- [ ] **T4** WS-A: promover códigos en `base_principles.md` / `min.md` / `full.md`.
- [ ] **T5** WS-B: fila `ADR-0098` en agentes + `base_skill_template.md`.
- [ ] **T6** Verificar GREEN + mutation-style; registrar evidencia.
- [ ] **T7** Commit `feat(principles): ADR-0098 ...` (`CMT`, `ATM`).

---

## 9. Verificación de test y mutation testing

**Comando determinista (permitido):**
```bash
uv run python -m pytest harness/tests/test_principles_adr0098.py -q
```

**Mutation testing — intento y resultado:**
```bash
uvx mutmut --version
# -> "To run mutmut on Windows, please use the WSL. Native windows support is
#     tracked in https://github.com/boxed/mutmut/issues/397"
```
`mutmut` **no es viable en Windows nativo** (requiere WSL). Mitigación
equivalente aplicada en el test: asserts **mutation-style** que prueban el
poder discriminante del checker sin tocar producción:

1. `test_mutation_detects_missing_cla_code`: un N1 sintético sin `CLA` es RECHAZADO.
2. `test_mutation_detects_swapped_taxonomy_mapping`: taxonomía con `CLA→SEC` es RECHAZADA.
3. `test_mutation_checker_rejects_absent_code`: exigir un código ausente falla.
4. `test_mutation_min_extra_code_is_detected`: un `min.md` con código extra rompe el anti-drift.

---

## 10. Anti-patrones (prohibidos)

- Duplicar un código en N1 o dejar N1 y `min.md` divergentes (drift silencioso).
- Añadir líneas N1 no atómicas (con " y "/" and "), violando `DRFR`.
- Inflar N1 con prosa (presupuesto > 60 líneas).
- Aprobar con `validate_skills --strict` rojo.
- Ablandar los tests para "pintar verde" cuando están RED (`VER` anti-patrón).
- Añadir procesos de red o efectos secundarios en la suite.

## 11. Fuentes

- `.opencode/core/base_principles.md` v3.4.0 (estado actual).
- `docs/adr/adr-0098-Convenciones-codigo-principios-doce.md` (ADR interno, no se pushea).
- `.opencode/core/base_skill_template.md`.
- `scripts/validate_skills.py` (gate T1 de skills, ADR-0046/0047).