# Ronda evolutiva 2 — `hedgefund` (ciclo GEPA)

> Oráculo determinista: `scripts/evolve_skills_gepa.py` (sin LLM). Ciclo
> EVO/GEPA (arXiv:2507.19457): learn → design → experiment → analyze.
> Objetivos Pareto: **activabilidad** (disparo/router) × **ejecutabilidad**.

## 1. LEARN (diagnóstico del original)

| Heurística | Valor | Observación |
|-----------|-------|-------------|
| H1 brevedad (≤120 líneas) | 1.0 | 84 líneas |
| H2 SDO (`Usar cuando`) | 1.0 | correcto |
| H3 anti-trigger explícito | 0.0 | solo `Alcance:`, no `Cuando NO usar` |
| H4 apertura con acción | 0.0 | el body abre con `PERSONA & CANON` |
| H5 checklist/guardrails | 1.0 | ✅ tabla de violaciones + checklist |
| H6 ejemplo fenced | 1.0 | memo de mandato presente |
| H7 keywords de dominio | 1.0 | riesgo/reward, mandato, stop-loss… |
| H8 accionabilidad | 0.33 | 6 instrucciones imperativas |
| H9 tabla de decisión | 1.0 | ya tenía tabla de severidad |
| H10 unicidad de router | 0.24 | solape con `quant-trading`/`risk-execution` |

**Score original**: activabilidad **0.567** · ejecutabilidad **0.833** · composite **0.700**.

**Feedback textual**: *"description sin anti-trigger explícito; el body abre con
PERSONA & CANON, no con acción; pocas instrucciones imperativas (6)."*

## 2. DESIGN (2 mutantes propositivos, una responsabilidad c/u)

- **Variante A — refuerza la activabilidad**: anti-trigger explícito
  (`Cuando NO usar: …`) + primera sección `## Activación inmediata: decide como
  un fondo` con 4 pasos imperativos (exige datos → BLOCK, tesis, sizing, OOS).
- **Variante B — refuerza la ejecutabilidad**: añade `## Tabla de decisión —
  go/no-go institucional` y convierte `## Ejemplo` en **ejemplo trabajado**
  `input → pasos → output` (memo original conservado verbatim).

## 3. EXPERIMENT (heuristicas deterministas + feedback)

| Candidato | Activabilidad | Ejecutabilidad | Composite | Pareto | Feedback (gap restante) |
|-----------|--------------:|---------------:|----------:|:------:|-------------------------|
| original | 0.567 | 0.833 | 0.700 | no | sin anti-trigger, sin apertura de acción, 6 imperativas |
| A | 0.944 | 0.889 | 0.916 | **Sí** | pocas instrucciones imperativas (10) |
| B | 0.567 | 0.875 | 0.721 | **Sí** | sin anti-trigger ni apertura de acción |
| **A+B (crossover)** | **0.967** | **0.931** | **0.949** | **Sí (único)** | sin gaps |

## 4. ANALYZE (Pareto)

- A **domina** al original (activabilidad 0.567→0.944, ejecutabilidad 0.833→0.889).
- B **domina** al original (activabilidad igual, ejecutabilidad 0.833→0.875).
- A y B son complementarias; **A+B** domina a ambas → crossover. Estado final =
  única frontera.

**Variantes rechazadas como estado final**: A y B aisladas, por dominancia
estricta de A+B (A: ejecutabilidad 0.889 < 0.931; B: activabilidad 0.567 < 0.944).

## 5. Promoción

- `SKILL.md` actualizado (A+B), contenido original conservado (`git diff`).
- Description: cambio **aditivo** — `Cuando NO usar: ver Alcance.` (compactado
  al presupuesto ≤320 chars de `test_opencode_config_sync.py`).
- `SKILL.min.md`: description sincronizada.
- Digest sha256 refrescado.
