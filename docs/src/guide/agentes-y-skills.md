# Agentes y Skills — Sistema Multi-Agente AGENTIC

## Arquitectura General

AGENTIC opera con **8 agentes** que ejecutan **30 skills** especializados. Cada agente es un perfil con capacidades y responsabilidades definidas. Los skills son módulos de conocimiento que los agentes pueden cargar según la tarea.

### Los 8 Agentes

```
coordinator → Punto de entrada. Recibe el mensaje, analiza complejidad, delega.
    ├── builder → Implementa código con calidad automática.
    ├── scientist → Investiga papers, diseña experimentos, analiza arquitecturas.
    ├── guardian → Verifica calidad, seguridad, testing de vanguardia.
    └── evolve → Meta-agente de auto-mejora continua (ASI-Evolve).
         ├── evolve-researcher → Analiza cognition store, propone hipótesis.
         ├── evolve-engineer → Implementa mutaciones, ejecuta experimentos.
         └── evolve-analyzer → Analiza resultados, decide promoción/descartes.
```

### Coordinator
El coordinator es el punto de entrada único. Implementa el patrón **Swiss Watch**: recibe el mensaje, lo clasifica por complejidad y lo delega al agente especializado.

**Flujo de trabajo:**
1. **RECEIVE**: Usuario envía mensaje (con o sin @agente)
2. **ROUTE**: `DifficultyRouter` clasifica la complejidad (trivial → very_complex)
3. **PLAN**: `TaskPlanner` descompone en DAG de subtasks (11 templates)
4. **TRACK**: `SessionContext` preserva estado entre iteraciones
5. **ADAPT**: `AdaptivePlanner` ajusta estrategia según historial
6. **EXECUTE**: Niveles independientes se ejecutan en paralelo
7. **CONSOLIDATE**: Resultados se consolidan y presentan

**Triggers:** plan, organize, coordinate, delegate, manage, orchestrate, task, project, swarm, pipeline, workflow

### Builder
Implementa código siguiendo estándares automáticos. Es el ejecutor principal de tareas técnicas.

**Estándares que aplica:**
- **Clean Code**: Código legible, funciones cortas, nombres semánticos
- **DRY/KISS/SSOT/YAGNI**: Sin duplicación, simple, fuente única de verdad
- **DocStrings ES-UTF8**: Cada función con Args/Returns/Raises
- **Tests >80%**: Cobertura obligatoria con PBT + guardrails
- **Errores Accionables**: WHAT+WHY+WHERE, sin except:pass

**Triggers:** implement, build, create, code, refactor, api, endpoint, rust, go, python, web, frontend, ui, component

### Scientist
Investigador y arquitecto. Analiza papers, diseña experimentos y evalúa arquitecturas.

**Técnicas que aplica:**
- **Research First**: Investiga estado del arte antes de proponer
- **MetaClaw**: +32% accuracy en tareas complejas
- **MARS**: Metacognitive reflection de un solo ciclo
- **ShapleyFlow**: Atribución game-theoretic con Shapley values
- **ERL**: Extracción de heurísticas (+7.8% Gaia2)

**Triggers:** research, paper, architecture, design-pattern, methodology, algorithm, study, analysis, experiment, validate, benchmark

### Guardian
Verificador de calidad, seguridad y riesgo. Aplica **Verify First**: su función es validar lo que otros construyen.

**Técnicas de testing:**
- **PROBE**: Mutation testing con validación adversarial
- **muTON/mewt**: Testing language-agnostic (Trail of Bits 2026)
- **AdverTest**: Testing adversarial (+8.56% fault detection)
- **CDBench**: Zero-sum game evaluation (57-80% fail rate)
- **SMART**: Property-based testing con invariantes

**Triggers:** test, security, audit, quality, review, check, validate, ci, compliance, hardening

### Evolve (con Creative AI)
Meta-agente de auto-mejora. Orquesta el ciclo **ASI-Evolve**. Incorpora **Creative AI** (ADR-0023) para generacion divergente de ideas.

**Modo Creativo (ReDNA pipeline):**
- `debate(topic, creative_mode=True)` — Activa el pipeline divergente→convergente
- **Divergente**: Agentes generan ideas libremente, sin restricciones, de forma aislada
- **Convergente**: Las ideas se evaluan contra restricciones (novedad*0.4 + factibilidad*0.6)
- **Integracion**: Top 3 ideas se combinan en una propuesta final

**Proteccion contra Diversity Collapse:**
- Topologia sparse (no fully-connected)
- Rondas de generacion aislada antes de compartir
- Presion divergente para opiniones disidentes
- Penalizacion a deferencia de autoridad

**Ciclo ASI-Evolve:**
```
Learn → Design → Experiment → Analyze → Deploy
  │         │          │           │          │
  │    evolve-    evolve-     evolve-      Forward
  │    researcher engineer    analyzer   Deployment
  │                                        │
  cognition store                    despliegue gradual
```

**Triggers:** evolve, self-improve, improve, optimize, skill, cognition, learn, adapt, upgrade, meta

---

## Los 30 Skills (27 ADRs)

Los skills se organizan por dominio. Cada skill tiene formato dual: `SKILL.md` (completo) y `SKILL.min.md` (minificado para carga rápida).

### 💻 Tecnología y Desarrollo

| Skill | Dominio | Propósito |
|-------|---------|-----------|
| **architecture** | architecture | Patrones GoF, Clean Architecture, Hexagonal, DDD, C4 model |
| **rust-lang** | systems | Rust: ownership, async, FFI con Python, crates, performance |
| **frontend-uiux** | frontend | Generative UI 2026, design tokens, A2UI/OpenUI, WCAG 2.2 |
| **responsive-ui** | frontend | UI responsive, mobile-first, Core Web Vitals, accesibilidad |
| **data-science** | data | ML pipelines, PyTorch, GPU acceleration, feature engineering |
| **devops-infra** | devops | CI/CD, Docker, Kubernetes, Terraform, monitoreo |

### 🔒 Seguridad

| Skill | Dominio | Propósito |
|-------|---------|-----------|
| **security-audit** | security | SAST, DAST, threat modeling, SBOM, compliance OWASP/STRIDE |

### 💼 Negocio y Gestión

| Skill | Dominio | Propósito |
|-------|---------|-----------|
| **hedgefund** | finance | Doctrina hedge fund: riesgo/reward, allocation, stop-loss |
| **business-strategy** | business | DOFA, Porter, Canvas, OKR, ROI, planificación estratégica |
| **project-management** | management | Scrum, Kanban, WBS, riesgos, estimaciones |
| **communication** | communication | Escritura ejecutiva, presentaciones, storytelling, negociación |

### 📈 Finanzas y Trading

| Skill | Dominio | Propósito |
|-------|---------|-----------|
| **quant-trading** | trading | Estrategias cuantitativas con CQE Rust, backtesting |
| **risk-execution** | trading | Risk management, position sizing, market making, TCA |
| **behavioral-economics** | economics | Teoría de juegos, sesgos cognitivos, incentivos |

### 🔬 Ciencia e Investigación

| Skill | Dominio | Propósito |
|-------|---------|-----------|
| **alpha-research** | research | Factor research, ML, feature engineering, validación estadística |
| **math-doc** | academic | Documentos matemáticos, LaTeX, proofs, estadística |
| **science-doc** | academic | Documentos científicos, peer review, revisiones sistemáticas |
| **physical-sciences** | science | Física, química, biología, método científico |

### 🧠 Humanidades y Ciencias Sociales

| Skill | Dominio | Propósito |
|-------|---------|-----------|
| **psychology** | psychology | Psicología cognitiva, organizacional, del aprendizaje |
| **education** | education | Diseño instruccional, pedagogía, andragogía, Bloom |
| **ethics** | philosophy | Ética de IA, alineamiento de valores, filosofía de la mente |
| **linguistics** | linguistics | Lingüística cognitiva, semiótica, pragmática |
| **sociology** | sociology | Dinámicas de grupo, teoría de redes, cultura digital |
| **creative-design** | design | Design Thinking, branding, prototipado, ideación |

### 🏥 Salud y Legal

| Skill | Dominio | Propósito |
|-------|---------|-----------|
| **healthtech** | health | Sistemas clínicos, interoperabilidad, HIPAA |
| **legal-doc** | legal | Análisis jurídico colombiano multi-especialidad |

### 🛒 Retail

| Skill | Dominio | Propósito |
|-------|---------|-----------|
| **pos-retail** | retail | Punto de venta, operaciones retail, inventario |

### 🌱 Sostenibilidad

| Skill | Dominio | Propósito |
|-------|---------|-----------|
| **sustainability** | environment | ESG, huella de carbono, reportes GRI/SASB/TCFD |

### 🔄 Meta

| Skill | Dominio | Propósito |
|-------|---------|-----------|
| **evolve** | meta | Auto-mejora continua, ASI-Evolve loop, FDE |

---

## Cómo se Activan los Agentes

Los agentes se activan por **detección de palabras clave** en el mensaje del usuario:

1. El `coordinator` recibe el mensaje (es el default, priority=1)
2. `DifficultyRouter` analiza la complejidad del mensaje
3. `TaskPlanner` descompone en subtareas con agentes asignados
4. Cada agente ejecuta su subtarea y reporta resultados
5. Los resultados se consolidan y presentan al usuario

### Ejemplos de Activación

| Mensaje | Agente | Skill que carga |
|---------|--------|-----------------|
| "implementa una API REST en Rust" | builder | rust-lang, architecture, security-audit |
| "investiga papers sobre transformers" | scientist | alpha-research, science-doc |
| "audita la seguridad del sistema" | guardian | security-audit |
| "mejora el rendimiento del sistema" | evolve | evolve (meta) |
| "analiza este contrato legal" | coordinator → scientist | legal-doc |
| "crea un dashboard financiero" | builder | frontend-uiux, responsive-ui, quant-trading |

---

## Carga de Skills por Proyecto

Los skills se despliegan selectivamente según el tipo de proyecto:

| Tipo | Skills incluidas |
|------|-----------------|
| **Trading** (CQE, Onyx) | evolve, hedgefund, quant-trading, alpha-research, risk-execution, math-doc, science-doc |
| **Healthtech** (HC) | evolve, hedgefund, healthtech, legal-doc, science-doc |
| **Retail** (PDV) | evolve, hedgefund, pos-retail, legal-doc |
| **General** (Hermes) | evolve, hedgefund, math-doc, legal-doc, science-doc, healthtech, pos-retail, quant-trading, risk-execution |

---

## Sistema de Debate: Worktable

El **Worktable** es un sistema de debate multi-agente donde 13 expertos en calidad de software discuten una propuesta y llegan a un compendio. Soporta dos modos: **critico** (debate tradicional) y **creativo** (generacion de ideas).

### Modo Crítico (13 expertos en calidad)
1. Separation of Concerns (SoC)
2. Low Coupling
3. High Cohesion
4. Fault Tolerance & Resilience
5. Scalability & Elasticity
6. Observability
7. Clean Code
8. Maintainability
9. Testability
10. Interoperability
11. Security (Defense in Depth)
12. DevOps Principles
13. Trade-offs Manager

**3 rondas:** Opening → Critique → Refinement → Compendium

### Modo Creativo (ReDNA pipeline)
Activa el pipeline divergente→convergente para generacion de ideas innovadoras:

```python
# Uso programatico
wt = Worktable()
compendio = wt.debate("Disenar una API innovadora", creative_mode=True)
```

**Fase Divergente:** Agentes generan N ideas libremente (independientes, sin compartir aun)
**Fase Convergente:** Ideas evaluadas por novedad (40%) y factibilidad (60%)
**Fase Integracion:** Top 3 ideas se combinan en propuesta final

**Proteccion contra Diversity Collapse:**
- Topologia sparse (no acoplamiento estructural)
- 2 rondas de generacion aislada antes de compartir
- Presion divergente del 30% para opiniones disidentes
- Penalizacion del 10% a deferencia de autoridad

**Resultado:** Compendium con propuesta integrada, ideas seleccionadas y metricas de innovacion.

---

## SkillBundler: Composición Dinámica de Agentes

El **SkillBundler** implementa el patrón SIGMA: dado un texto de tarea, detecta el dominio, selecciona skills relevantes del registry y compone agentes como bundles de skills.

**Flujo:**
1. Recibe tarea: "Desarrollar API REST en Rust"
2. Detecta dominio: `api`
3. Selecciona skills: `rust-lang`, `architecture`, `security-audit`
4. Compone agente: `builder` con skills `[rust-lang, architecture, security-audit]`
5. Asigna a `builder` como agente principal

---

## Token Optimizer

El **TokenOptimizer** implementa tres técnicas de optimización:

### 1. Structured Output (-40% tokens)
Reemplaza texto libre con JSON Schema tipado en las respuestas de los agentes.

### 2. DAG Pipeline Parallelism (1.5-2.4x speedup)
Construye un grafo de dependencias entre subtareas y las ejecuta en paralelo cuando es posible, usando el algoritmo de Kahn.

### 3. Token Budget Manager
Asigna presupuestos de tokens diferenciables por rol de agente, permitiendo control granular del consumo.

---

## Sistema de Archivos

```
.opencode/
├── agents/           ← 8 perfiles de agente (coordinator, builder, scientist, guardian, evolve + 3 sub)
├── skills/           ← 30 skills especializados (cada uno con SKILL.md)
├── core/             ← Principios base, guardrails, router, registry
└── config/           ← routing_rules.yaml, project_config.yaml, token_budgets.yaml

harness/
├── orchestrator/     ← TaskOrchestrator, AgentBus, Worktable, SkillBundler, TokenOptimizer
├── memory_rag/       ← LanceDB vector store, semantic cache, context management
├── tools_sandbox/    ← MCP client/manager/executor
└── tests/            ← 1894 tests (52 suites)
```
