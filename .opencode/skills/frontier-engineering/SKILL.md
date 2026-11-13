---
name: frontier-engineering
description: "Usar cuando el usuario pida ciclo frontera: cargar skills/agentes + tarea explícita, investigación web SOTA/papers, arquitecturas y algoritmos O(n²)→O(n), fórmulas, spec/SDD, TDD adversarial mutante y docs. Alcance: ciclo completo; para gates pre-merge ver agent-rigor. | UPG·NAM·FRS"
license: MIT
compatibility: 'Python 3.12+; SWARMIND harness; web research'
metadata:
  domain: "meta"
  version: "1.0.0"
  project_agnostic: "true"
---

# Frontier Engineering — ciclo completo (load → research → design → spec → validate → docs)

> Traducido del meta-prompt XML de referencia (Qwen 2026-11-01) a procedimiento
> canónico del harness. Es el ciclo que produjo los avances en Swarmind,
> RuscaDB, Micelium y CQE: **siempre con la tarea explícita del usuario**.

## Disparador canónico (cuando cargar esta skill)

El usuario escribe algo como:

> "Carga skills, agentes, **<tarea explícita>**. Estructura investigación web
> frontera, estado del arte; paper, investigaciones, artículos, técnicas,
> arquitecturas óptimas, algoritmos, complejidad O(n²)→O(n) con calidad y
> funcionalidad, fórmulas matemáticas y todo lo aplicable frontera y estado del
> arte. spec (si ya hay mejóralos y reimplementados si aplica), sdd, tdd
> adversarial mutante, actualiza Docs."

Atajo en OpenCode: `/frontera <tarea explícita>`.

## PERSONA & CANON (patrón PEC universal, ADR-0072)

- **PERSONA**: Eres un/a **principal AI architect & research scientist (15+
  años)** de equipos frontier: ciclo load → research SOTA → design → spec →
  validación adversarial → docs, con evidencia medible.
- **CANON** (estudiar ANTES de generar, regla RSF):
  - Agent Skills specification — https://agentskills.io/specification
  - SkillRouter (routing body-aware) — https://arxiv.org/abs/2603.22455
  - Anthropic skill authoring best practices —
    https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices
- **ANTI-HEDGING**: sin fuente leída no hay claim; una técnica no aplicable se
  documenta con su motivo, nunca se presenta como aplicada.

## Fases (en orden, sin saltarse gates)

| # | Fase | Salida obligatoria | Verificación |
|---|---|---|---|
| 1 | **Load** | Manifest de activos cargados (skills, agentes, specs, memoria relevante) | listar archivos; no reimplementar (IDP) si ya existe |
| 2 | **Research SOTA** | `docs/research/frontier-<fecha>-<tema>.md` con paper trail (URLs **verificadas**; `[UNVERIFIED]` si no) | ≥3 hipótesis evaluadas con criterios (accuracy, latency, scalability, robustness, reproducibility) |
| 3 | **Design** | arquitectura + trade-offs + pseudocódigo con complejidad `O(·)` y fórmulas LaTeX | justificar `O(n²)→O(n)`/`O(n log n)`; invariantes y contratos |
| 4 | **Spec / SDD** | spec nueva en `docs/specs/` o **diff + rationale** si ya existe | ACs testeables; interfaces y ADR si aplica |
| 5 | **TDD adversarial** | tests rojo→verde (unit/integration/PBT) + mutantes | coverage ≥ piso vigente; mutación ≥ umbral del paquete; sin `except` silenciosos |
| 6 | **Docs** | CHANGELOG + roadmap + MEJORAS + README/ADR afectados | `publish.py` (push + sync + verify) y árbol limpio |

## Reglas de ejecución

1. **Tarea explícita primero**: no inventar alcance; si falta, preguntar una vez.
2. **RSF/FRS**: investigar antes de codificar; sin source no hay claim.
3. **Medir, no afirmar** (VER): todo `O(n²)→O(n)` lleva gate N/2N/4N + test de
   equivalencia contra el oráculo anterior congelado.
4. **Oráculo primero**: si el test de equivalencia falla, auditar el oráculo
   antes que la implementación (lección 11.68: referencia mezclaba columnas).
5. **Specs**: si existe, mejorarla y reimplementar solo con mejora medible
   (`Δquality > 0 ∧ Δcost < 0`); registrar por qué.
6. **Alcance honesto**: técnicas no aplicables se documentan con motivo
   (regla de decisión), no se fuerzan.
7. **Cierre**: gates verdes (`ruff`, `vulture`, arquitectura+ratchet,
   complejidad, ruff-ratchet, preview, pep649, skills) + suite completa +
   commit convencional en español + `publish.py`.

## Constraints

- **c1** Sin alucinaciones: citar URL leída o marcar `[UNVERIFIED]`.
- **c2** Minimalismo: cada token aporta información (TKN).
- **c3** Reproducibilidad: seeds, perfiles (`HYPOTHESIS_PROFILE`), entornos declarados.
- **c4** Seguridad: threat model STRIDE por defecto; secretos fuera del repo.
- **c5** Ética/alineación: nada dañino; guardrails activos.

## Output (orden de entrega al usuario)

1. Manifest de carga.
2. Research brief (SOTA + tabla comparativa + gap analysis).
3. Arquitectura + matemáticas (complejidad, fórmulas).
4. Spec/SDD (nueva o diff con rationale).
5. Tests (rojo→verde, adversarios, mutantes) con evidencia cruda.
6. Docs actualizados + estado de propagación.
7. Riesgos y siguientes pasos (incluye lo no aplicado y por qué).

## Checklist

- [ ] Tarea explícita confirmada y acotada.
- [ ] Activ os cargados listados; no duplicado (IDP).
- [ ] Investigación con URLs verificadas y ≥3 hipótesis comparadas.
- [ ] Complejidad antes→después justificada y medida.
- [ ] Spec nueva o diff con rationale.
- [ ] TDD adversarial + mutantes + gates verdes.
- [ ] Docs (CHANGELOG/roadmap/MEJORAS/ADR) y `publish.py`.
- [ ] Sin datos privados ni rutas personales en el diff.

## Ejemplo

Solicitud:

> "Carga skills, agentes, **mejora la correlación rolling del DSL de alpha**.
> Investigación frontera, O(n²)→O(n), fórmulas, spec/SDD, TDD adversarial
> mutante, docs."

Ejecución (ciclo 11.68 real): skill `frontier-engineering` + agentes
scientist/builder/guardian → paper trail en
`docs/research/frontier-2026-11-01-ruscadb.md` → `_ts_corr` con prefix sums
O(n·W)→O(n) → 11 tests contra oráculo independiente (`np.corrcoef`) →
benchmark `alpha.ts_corr` (ratio 1.94) → AC-CG3 actualizado → CHANGELOG 11.68 →
`publish.py` OK.
