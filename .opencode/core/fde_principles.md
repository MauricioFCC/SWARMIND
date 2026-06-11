---
name: fde-principles
description: Forward Deployment Engineering universal principles - multi-layer for any domain
version: 2.0.0
project_agnostic: true
---

# FDE PRINCIPIOS UNIVERSALES | Forward Deployment Engineering

Integración de Forward Deployment Engineering en el ecosistema .opencode.
Cada skill hereda estos principios para operar en cualquier dominio, lenguaje y arquitectura.

---

## NIVEL 1 — ESENCIAL FDE (siempre inyectado)

```
FDE: bridge product↔reality | delta = gap to close
MISSION: solve stakeholder problem, not user persona
GLUE: 50% integration + 50% strategy
VALUE: speed-to-value > feature-complete
```

---

## NIVEL 2 — ESTÁNDAR FDE (7 pilares)

| Pilar | Principio |
|-------|-----------|
| **DELTA** | Identificar el gap entre producto ideal y realidad del cliente. Resolver solo el delta, no todo el sistema. |
| **MISSION** | Cada tarea es una misión con stakeholder definido, métrica de éxito y criterio de "Day 2" (post-entrega). |
| **GLUE** | 50% del código es integración/adaptación. Priorizar contratos (APIs, schemas) sobre implementación. |
| **VALUE** | Speed-to-value primero. MVA (Minimum Viable Architecture) en <30 días. 80/20 scope. |
| **DIPLOMACY** | El problema técnico es 50% político. Identificar Champion, Blocker, Success Metric antes de codificar. |
| **RESILIENCE** | Air-gap ready. Circuit breakers en datos. VPC-grade security. Zero-trust por defecto. |
| **EVOLVE** | Cada entrega genera cognition. Cada fallo produce lección reusable. El sistema se mejora solo. |

---

## NIVEL 3 — CHECKLIST FDE DETALLADO

### DELTA - Análisis del Gap
- [ ] Identificar System of Record (fuente de verdad)
- [ ] Documentar el gap entre producto y necesidad real
- [ ] Proponer glue code mínimo para cerrar el gap
- [ ] Validar que el delta resuelve el problema de negocio

### MISSION - Definición de Misión
- [ ] Stakeholder identificado (CTO, CEO, operador, etc.)
- [ ] Métrica de éxito definida (latencia, accuracy, reducción de costo)
- [ ] Day 2 definido (¿quién mantiene esto cuando termine?)
- [ ] Cost of Inaction calculado

### GLUE - Integración
- [ ] Contratos API definidos antes de implementar
- [ ] Soporte para legacy systems (adapters)
- [ ] Data pipeline con medallion architecture (bronze/silver/gold)
- [ ] Formato de datos universal (Parquet/JSONL)

### VALUE - Entrega de Valor
- [ ] MVA definido: la versión más simple que prueba valor
- [ ] 80/20 scope: 20% del esfuerzo → 80% del valor
- [ ] Quick win identificado para primera iteración
- [ ] Demo preparada como narrativa de valor, no tour de features

### DIPLOMACY - Diplomacia Técnica
- [ ] Champion identificado dentro de la organización
- [ ] Blocker potencial identificado (IT, Legal, Compliance)
- [ ] Plan de comunicación con stakeholders
- [ ] Estrategia de adopción (train the trainer)

### RESILIENCE - Resiliencia
- [ ] Timeouts en toda operación I/O
- [ ] Retry con exponential backoff
- [ ] Circuit breaker en dependencias externas
- [ ] Logging JSON con trace_id
- [ ] Plan de fallback documentado
- [ ] Zero-trust security por defecto

### EVOLVE - Auto-mejora
- [ ] Cognition store actualizado con lecciones
- [ ] Experiment DB registra cada intento
- [ ] Análisis de cada resultado (incluso fallos)
- [ ] Best snapshot promovido automáticamente

---

## MAPA DE ROLES → PILARES FDE

| Rol | Pilares FDE |
|-----|-------------|
| software-engineer | GLUE, RESILIENCE, DELTA |
| frontend-engineer | VALUE, DIPLOMACY, DELTA |
| data-architect | DELTA, GLUE, RESILIENCE |
| devops-sre | RESILIENCE, GLUE, VALUE |
| security-engineer | RESILIENCE, DIPLOMACY, MISSION |
| quant-developer | DELTA, GLUE, EVOLVE |
| risk-manager | RESILIENCE, MISSION, DELTA |
| trading-operations | MISSION, VALUE, RESILIENCE |
| documentation-specialist | DIPLOMACY, MISSION, VALUE |
| project-manager | MISSION, DIPLOMACY, VALUE |
| mobile-engineer | VALUE, GLUE, DELTA |
| quality-gate | GLUE, RESILIENCE, EVOLVE |
| enterprise-architect | DELTA, GLUE, DIPLOMACY |
| ai-engineer | DELTA, EVOLVE, VALUE |
| evolve | EVOLVE, GLUE, VALUE |

---

---

## GLOSARIO FDE — Términos, Conceptos y Patrones

| Término | Definición | Uso |
|---------|-----------|-----|
| **C.A.S.E.** | Clarify → Architect → Solve → Evaluate. Marco universal de razonamiento para agentes. | Toda respuesta de skill debe pasar las 4 etapas. |
| **MVA** | Minimum Viable Architecture. Versión más simple que prueba valor. <30 días. | Definir antes de codificar. Quick win visible. |
| **Medallion Architecture** | Bronze (raw) → Silver (cleaned) → Gold (curated). Pipeline de datos en 3 capas. | data-architect, cualquier pipeline ETL. |
| **MECE** | Mutually Exclusive, Collectively Exhaustive. Descomposición sin solapamiento ni omisión. | Estructurar argumentos, requisitos, tareas. |
| **Pyramid Principle** | Conclusión primero (SCQ: Situation, Complication, Question), luego argumentos MECE, datos al final. | Formato de reportes, PRDs, executive summaries. |
| **Three Whys** | 1st Why (síntoma) → 2nd Why (causa directa) → 3rd Why (raíz sistémica). | Post-mortem, análisis de fallo, guardrails. |
| **Delta (Δ)** | Gap entre producto ideal y realidad del cliente. Lo único que hay que resolver. | Cada misión FDE tiene un delta. |
| **Delta vs Echo** | **Delta**: el que construye, cierra gaps. **Echo**: el que replica, mantiene estándares. | Roles del equipo: diferenciar construcción de mantenimiento. |
| **Stakeholder vs User** | **Stakeholder**: quien define éxito (paga, decide). **User**: quien opera el sistema. | MISSION siempre refiere al stakeholder. |
| **Speed-to-Value** | Entregar valor rápido > feature-complete. 80/20 scope. | Priorización, MVA, quick wins. |
| **Cost of Inaction (CoI)** | ¿Qué cuesta NO resolver este problema? En dinero, tiempo, riesgo. | Justificar prioridad en PRDs y reports. |
| **Day 2** | Plan post-entrega: ¿quién mantiene? ¿cómo escala? ¿qué pasa si falla? | Toda misión FDE define Day 2. |
| **Glue Code** | Código de integración/adaptación entre sistemas. 50% del esfuerzo total. | Priorizar contratos sobre implementación. |
| **Zero-Trust** | No confiar en nada por defecto. Validar todo, autenticar todo. | RESILIENCE pillar, seguridad por diseño. |
| **Discovery Checklist** | Admin (reglas/SLAs) + Data (fuentes/schemas) + Infra (target/deps). Pre-flight gate. | Ejecutar antes de implementar cualquier cambio. |
| **A2A Protocol** | Agent-to-Agent estándar de descubrimiento, capability advertisement y handoff formal entre agentes. | `router_v2.py` → `A2ARegistry`, `A2ACard`, `A2AHandoffRequest`. |
| **RAG Triad** | Groundedness (fundamentado en fuentes) + Context Relevance (usa el contexto) + Faithfulness (no alucina). | `guardrails.py` → `RAG-001/002/003`. Evaluación de calidad de respuestas RAG. |
| **Inner Loop** | Evaluación rápida en entorno de desarrollo: lint, type narrow, tests unitarios, diff review. <30s. | `quality-gate.md` → IL-1 a IL-5. Mandatory pre-commit. |
| **Outer Loop** | Evaluación completa en CI/CD: test full suite, lint completo, type check, seguridad, performance, integración. | `quality-gate.md` → OL-1 a OL-7. Mandatory pre-merge. |
| **Pairwise Evaluation** | Comparar candidate vs baseline con Model-as-a-Judge en correctness, efficiency, readability, security. | `quality-gate.md` → Pairwise mode. Cognition store feedback. |
| **Pointwise Evaluation** | Evaluar candidate contra rúbrica fija (1-5) en groundedness, clarity, completeness, safety. | `quality-gate.md` → Pointwise mode. Scoring absoluto. |
| **AutoSxS** | Auto Side-by-Side. Evaluación automática comparativa de dos respuestas por un LLM judge. | Pairwise evaluation con prompt estructurado. |
| **ASI-Evolve Pipeline** | 3-agent loop: Researcher (propone) → Engineer (ejecuta) → Analyzer (destila). 2 memorias: Experiment DB + Cognition Store. | `evolve_loop.py` → `EvolveLoop`, `ExperimentDB`, `CognitionStore`. |
| **Diff-Based Evolution** | Evolución vía parches SEARCH/REPLACE en lugar de reescritura completa. max_code_length limita el diff. | `evolve_loop.py` → `diff_based_evolution: true`. |
| **Island Sampling** | Muestreo multi-isla con parámetros de migración (rate/interval) y ratio exploración/explotación. | `evolve_loop.py` → `IslandSamplingConfig`. |
| **Judge Model** | LLM externo para scoring final de candidatos. ratio controla qué % de rounds se juzgan. | `evolve_loop.py` → `JudgeConfig`. |
| **FAISS Index** | Índice vectorial para búsqueda semántica en cognition. Index type: IP (Inner Product) por defecto. | `evolve_loop.py` → `FaissConfig`. Embedding: all-MiniLM-L6-v2, 384 dim. |

---

## CHECKLIST OPERATIVO — Por Fase del Ciclo FDE

### Discovery Phase
- [ ] Site Survey completado (admin/data/infra)
- [ ] Stakeholder identificado con métrica de éxito
- [ ] Cost of Inaction calculado
- [ ] Delta documentado: gap actual vs deseado
- [ ] Discovery Checklist (Admin+Data+Infra) pasado

### Architect Phase
- [ ] Technical PRD redactado con MVA
- [ ] Pyramid Principle aplicado a la justificación
- [ ] MECE applied a descomposición de requisitos
- [ ] Medallion Architecture para pipelines de datos
- [ ] Contratos API definidos antes de implementar
- [ ] 80/20 scope: 20% esfuerzo → 80% valor

### Delivery Phase
- [ ] MVA entregado en <30 días
- [ ] Quick win funcional desde iteración 1
- [ ] Glue code implementado para integración legacy
- [ ] Day 2 plan documentado y asignado
- [ ] Three Whys aplicado si hubo fallos

### Evaluate Phase
- [ ] Executive Report generado para stakeholders
- [ ] Delta recalculado: ¿cuánto gap se cerró?
- [ ] Cognition item registrado (lección aprendida)
- [ ] Experiments DB actualizado con métricas
- [ ] Best snapshot promovido si aplica

---

> Fuente: `.opencode/core/fde_principles.md` — Skills, agents y loop referencian este archivo.
> Para extender: agregar nuevo pilar en los 3 niveles + GLOSARIO + CHECKLIST OPERATIVO.
