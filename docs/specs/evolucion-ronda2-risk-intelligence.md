# Ronda evolutiva 2 — `risk-intelligence` (ciclo GEPA)

> Oráculo determinista: `scripts/evolve_skills_gepa.py` (sin LLM). Ciclo
> EVO/GEPA (arXiv:2507.19457): learn → design → experiment → analyze.
> Objetivos Pareto: **activabilidad** (disparo/router) × **ejecutabilidad**.

## 1. LEARN (diagnóstico del original)

| Heurística | Valor | Observación |
|-----------|-------|-------------|
| H1 brevedad (≤120 líneas) | 1.0 | 75 líneas |
| H2 SDO (`Usar cuando`) | 1.0 | correcto |
| H3 anti-trigger explícito | 0.0 | solo `Alcance:`, no `Cuando NO usar` |
| H4 apertura con acción | 0.0 | el body abre con `PERSONA & CANON` |
| H5 checklist/guardrails | 1.0 | ✅ checklist + anti-patrones |
| H6 ejemplo fenced | 1.0 | ficha de radar presente |
| H7 keywords de dominio | 1.0 | CRO Forum, tech, geo, clima, salud, finanzas |
| H8 accionabilidad | 0.33 | 6 instrucciones imperativas |
| H9 tabla de decisión | 0.0 | no hay tabla accionable |
| H10 unicidad de router | 0.26 | solape con `risk-execution` |

**Score original**: activabilidad **0.585** · ejecutabilidad **0.583** · composite **0.584**.

**Feedback textual**: *"description sin anti-trigger explícito; el body abre con
PERSONA & CANON, no con acción; pocas instrucciones imperativas (6); sin tabla de
decisión accionable."*

## 2. DESIGN (2 mutantes propositivos, una responsabilidad c/u)

- **Variante A — refuerza la activabilidad**: anti-trigger explícito
  (`Cuando NO usar: … ver risk-execution / hedgefund`) + primera sección
  `## Activación inmediata (radar de riesgos)` con 4 pasos imperativos.
- **Variante B — refuerza la ejecutabilidad**: añade `## Tabla de decisión —
  fase del radar` (VIGILAR/ALERTA/ESCALAR/RESPONDER) y convierte `## Ejemplo` en
  **ejemplo trabajado** `input → pasos → output` (ficha original conservada).

## 3. EXPERIMENT (heuristicas deterministas + feedback)

| Candidato | Activabilidad | Ejecutabilidad | Composite | Pareto | Feedback (gap restante) |
|-----------|--------------:|---------------:|----------:|:------:|-------------------------|
| original | 0.585 | 0.583 | 0.584 | no | sin anti-trigger, sin apertura de acción, sin tabla |
| A | 0.963 | 0.639 | 0.801 | **Sí** | pocas imperativas (10) + sin tabla |
| B | 0.585 | 0.875 | 0.730 | **Sí** | sin anti-trigger ni apertura de acción |
| **A+B (crossover)** | **0.985** | **0.931** | **0.958** | **Sí (único)** | sin gaps |

## 4. ANALYZE (Pareto)

- A **domina** al original (activabilidad 0.585→0.963, ejecutabilidad 0.583→0.639).
- B **domina** al original (activabilidad igual, ejecutabilidad 0.583→0.875).
- A y B complementarias → **A+B** domina estrictamente a ambas: única frontera.

**Variantes rechazadas como estado final**: A y B aisladas, por dominancia
estricta de A+B (A: ejecutabilidad 0.639 < 0.931; B: activabilidad 0.585 < 0.955).

## 5. Promoción

- `SKILL.md` actualizado (A+B), contenido original conservado (`git diff`).
- Description: cambio **aditivo** — `Cuando NO usar: ver Alcance.` (compactado
  al presupuesto ≤320 chars de `test_opencode_config_sync.py`).
- `SKILL.min.md`: description sincronizada.
- Digest sha256 refrescado.
