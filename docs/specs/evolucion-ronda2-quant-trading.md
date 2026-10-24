# Ronda evolutiva 2 — `quant-trading` (ciclo GEPA)

> Oráculo determinista: `scripts/evolve_skills_gepa.py` (sin LLM). Ciclo
> EVO/GEPA (arXiv:2507.19457): learn → design → experiment → analyze.
> Objetivos Pareto: **activabilidad** (disparo/router) × **ejecutabilidad**.

## 1. LEARN (diagnóstico del original)

| Heurística | Valor | Observación |
|-----------|-------|-------------|
| H1 brevedad (≤120 líneas) | 1.0 | 65 líneas, dentro del cap |
| H2 SDO (`Usar cuando`) | 1.0 | correcto |
| H3 anti-trigger explícito | 0.0 | solo tenía `Alcance:`, no `Cuando NO usar` |
| H4 apertura con acción | 0.0 | el body abre con `PERSONA & CANON` |
| H5 checklist/guardrails | 1.0 | ✅ checklist + guardrails + anti-patrones |
| H6 ejemplo fenced | 1.0 | bloque Rust presente |
| H7 keywords de dominio | 1.0 | 9 términos |
| H8 accionabilidad | 0.44 | 8 instrucciones imperativas |
| H9 tabla de decisión | 0.0 | no hay tabla accionable |
| H10 unicidad de router | 0.24 | cierto solape con `alpha-research`/`risk-execution` |

**Score original**: activabilidad **0.566** · ejecutabilidad **0.611** · composite **0.588**.

**Feedback textual**: *"description sin anti-trigger explícito; el body abre con
PERSONA & CANON, no con acción; pocas instrucciones imperativas (8); sin tabla
de decisión accionable."*

## 2. DESIGN (2 mutantes propositivos, una responsabilidad c/u)

- **Variante A — refuerza la activabilidad**: añade anti-trigger explícito
  (`Cuando NO usar: … ver alpha-research / risk-execution`) y una primera
  sección `## Activación inmediata` con 5 pasos imperativos. No toca el ejemplo.
- **Variante B — refuerza la ejecutabilidad**: añade `## Tabla de decisión —
  ¿qué componente del motor usar?` y convierte `## Ejemplo` en un **ejemplo
  trabajado** con contrato `input → pasos → output` (código original conservado
  verbatim). No toca la description.

## 3. EXPERIMENT (heuristicas deterministas + feedback)

| Candidato | Activabilidad | Ejecutabilidad | Composite | Pareto | Feedback (gap restante) |
|-----------|--------------:|---------------:|----------:|:------:|-------------------------|
| original | 0.566 | 0.611 | 0.588 | no | SDO ok, pero sin anti-trigger, sin apertura de acción, sin tabla |
| A | 0.963 | 0.681 | 0.822 | **Sí** | falta tabla de decisión accionable |
| B | 0.566 | 0.861 | 0.713 | **Sí** | sin anti-trigger ni apertura de acción |
| **A+B (crossover)** | **0.966** | **0.931** | **0.948** | **Sí (único)** | sin gaps |

## 4. ANALYZE (Pareto)

- A **domina** al original (mejora activabilidad 0.566→0.963 y ejecutabilidad
  0.611→0.681 sin degradar ningún objetivo).
- B **domina** al original (0.566→0.566 activabilidad, 0.611→0.861 ejecutabilidad).
- A y B son **líneas complementarias** (una mejora el disparo, otra la ejecución)
  → GEPA aplica **crossover**: A+B domina estrictamente a A y a B en el plano
  (activabilidad, ejecutabilidad). El estado final es la **única frontera**.

**Variantes rechazadas como estado final**: A y B aisladas. Motivo de Pareto: A+B
las domina en ambos objetivos (A cae en ejecutabilidad 0.681 < 0.931; B cae en
activabilidad 0.566 < 0.963). Se fusionan, no se descarta doctrina.

## 5. Promoción

- `SKILL.md` actualizado (A+B) — todo el contenido original conservado
  (verificado con `git diff`, solo inserciones y el título `## Ejemplo` → `## Ejemplo trabajado`).
- Description: cambio **aditivo** — `Cuando NO usar: ver Alcance.` (el
  presupuesto de descriptores del repo es **≤320 chars**, gate
  `test_opencode_config_sync.py::TestDescriptionTokenBudget`; la versión larga
  del anti-trigger lo rompía, se compactó al puntero de `Alcance:`).
- `SKILL.min.md`: description sincronizada con el anti-trigger.
- Digest sha256 refrescado en `skills_registry.yaml`.
