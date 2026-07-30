# Agentes y Skills — Sistema Multi-Agente Swarmind

> **Version:** Julio 2026 | **20 agentes** | **31 skills** | **5 nuevos modulos**

---

## Agentes (20)

El sistema Swarmind opera con **20 perfiles de agente** organizados en 4 categorias. Cada agente tiene dominio, triggers de activacion y capacidades especificas. Los agentes principales (coordinator, builder, scientist, guardian, evolve) son el nucleo; los agentes especializados complementan areas especificas.

### Agentes Principales (5)

| Nombre | Rol | Descripcion |
|--------|-----|-------------|
| **coordinator** | Orquestador | Default (priority=1). Swiss Watch orchestrator — recibe mensajes, analiza complejidad, delega a builder/scientist/guardian, consolida resultados. |
| **builder** | Ejecutor | Calidad automatica institucional — implementa codigo con Clean Code, DRY, KISS, SSOT, <900LC, patrones, DocStrings ES-UTF8, tests >80%. |
| **scientist** | Investigador | Cientifico e investigador — papers, patrones arquitectonicos, AI/ML, experimentos, sistemas agenticos, token economics. |
| **guardian** | Validador | Guardian universal — calidad, seguridad, riesgo, documentacion, testing adversarial (PROBE/AdverTest), mutation testing, property-based testing. |
| **evolve** | Meta-agente | Meta-agente de auto-mejora del sistema — orquesta el ciclo ASI-Evolve con Token Economics, RL Scaling, FDE y Autobuilder. |

### Agentes de Soporte (9)

| Nombre | Rol | Descripcion |
|--------|-----|-------------|
| **architect** | Diseno | Arquitecto de software especializado en diseno de sistemas, C4 modeling, ADRs y decisiones arquitectonicas con fitness functions. |
| **backend-engineer** | Backend | Backend engineer especializado en APIs (REST/GraphQL/gRPC), servidores, bases de datos y microservicios con calidad institucional. |
| **frontend-engineer** | Frontend | Frontend engineer especializado en UI/UX, React 19, componentes responsive, accesibilidad WCAG 2.2 AA y Generative UI 2026. |
| **data-engineer** | Datos | Ingeniero de datos especializado en pipelines ETL/ELT, data warehouses (Snowflake, BigQuery), streaming y orquestacion. |
| **database-administrator** | DBA | DBA especializado en modelado, optimizacion de consultas, indexing y administracion de BD relacionales (PostgreSQL 18, MySQL 9) y NoSQL. |
| **devops** | DevOps | Ingeniero DevOps especializado en CI/CD, IaC (Terraform, Pulumi), Kubernetes, Helm, GitOps, monitoreo y practicas SRE. |
| **mobile-engineer** | Mobile | Mobile engineer especializado en apps iOS/Android nativas y cross-platform con React Native, Flutter y Kotlin Multiplatform. |
| **qa-engineer** | Calidad | QA engineer especializado en testing automatizado (Playwright, Vitest), mutation testing, property-based testing y TDAD. |
| **security-engineer** | Seguridad | Ingeniero de seguridad especializado en auditorias, pentesting, threat modeling, SAST/DAST, SBOM y compliance OWASP/STRIDE/SOC2. |

### Agentes de Gestion (3)

| Nombre | Rol | Descripcion |
|--------|-----|-------------|
| **product-manager** | Producto | Product manager especializado en requerimientos, roadmaps, OKRs, priorizacion (RICE/WSJF), user research y stakeholder management. |
| **researcher** | Investigacion | Investigador academico especializado en revision de literatura (PRISMA), analisis de papers, escritura academica y meta-analisis. Complementa a scientist. |
| **reviewer** | Revision | Revisor de codigo especializado en pull requests, code review, analisis estatico (SonarQube, CodeQL, Semgrep) y deteccion de regresiones. Complementa a guardian. |

### Sub-agentes Evolve (3)

| Nombre | Rol | Descripcion |
|--------|-----|-------------|
| **evolve-researcher** | Auto-mejora | Sub-agente ASI-Evolve que lee la cognition store, analiza patrones de mejora y propone la siguiente hipotesis de evolucion para cualquier skill del sistema. |
| **evolve-engineer** | Auto-mejora | Sub-agente ASI-Evolve que ejecuta el candidato propuesto por el Researcher, evaluandolo contra metricas universales de calidad. |
| **evolve-analyzer** | Auto-mejora | Sub-agente ASI-Evolve que analiza resultados del Engineer, compara con baseline y destila lecciones transferibles para la cognition store. |

---

## Skills (31)

Los skills se organizan por categoria funcional. Cada skill tiene formato dual: `SKILL.md` (completo) y `SKILL.min.md` (minificado para carga rapida). El registro central esta en `.opencode/skills/skills_registry.yaml`.

### Desarrollo y Tecnologia

| Skill | Categoria | Descripcion |
|-------|-----------|-------------|
| **architecture** | Arquitectura | Patrones GoF, SOLID, Clean Architecture, Hexagonal, DDD, C4 model, ADRs, fitness functions, domain-driven design. |
| **rust-lang** | Sistemas | Rust: ownership, borrowing, lifetimes, async runtimes (tokio, smol), web frameworks (axum, actix), FFI con Python via PyO3/maturin, performance optimization. |
| **frontend-uiux** | Frontend | UI/UX con Generative UI 2026: design tokens AI-native (Geeklego 3-tier, 7onic, useVyre, StyleSeed), Semantic Guidance jerarquico, A2UI/OpenUI, Bayesian preference learning, WCAG 2.2 AA. |
| **responsive-ui** | Frontend | UI responsive: WCAG 2.2 AA/AAA, mobile-first, design tokens, component libraries, CSS Grid/Flexbox/Container Queries, Core Web Vitals, axe-core auditing. |
| **data-science** | Datos | Data Science & ML: pandas, numpy, polars, scikit-learn, PyTorch, feature engineering, GPU acceleration (AMP, DDP, torch.compile), pipelines reproducibles. |
| **devops-infra** | DevOps | CI/CD, IaC (Terraform, Pulumi, CDK), Docker, Kubernetes, Helm, ArgoCD, GitOps, OpenTelemetry, Prometheus, Grafana, SRE practices. |

### Seguridad

| Skill | Categoria | Descripcion |
|-------|-----------|-------------|
| **security-audit** | Seguridad | SAST, DAST, threat modeling (STRIDE), SBOM, OWASP Top 10, CWE Top 25, MITRE ATT&CK, compliance SOC2/ISO27001, hardening, secure code review. |

### Negocio y Estrategia

| Skill | Categoria | Descripcion |
|-------|-----------|-------------|
| **hedgefund** | Finanzas | Doctrina hedge fund institucional: riesgo/reward, capital allocation, stop-loss, position sizing, Harness Effect token economics, circuit breaker patterns, failure-spend governance. |
| **business-strategy** | Negocio | DOFA, Porter, Canvas, OKR, ROI, planes de negocio, analisis de mercado, modelos de negocio, toma de decisiones estrategicas. |
| **project-management** | Gestion | Scrum, Kanban, WBS, planificacion, seguimiento, riesgos, estimaciones, comunicacion con stakeholders, metodologias agiles. |
| **communication** | Comunicacion | Escritura ejecutiva, presentaciones, storytelling, negociacion, comunicacion intercultural, liderazgo profesional. |

### Finanzas y Trading

| Skill | Categoria | Descripcion |
|-------|-----------|-------------|
| **quant-trading** | Trading | Estrategias cuantitativas con CQE Rust, PaCoRe parallel exploration, Helium workflow scheduling, Agentix program-level optimization, LTS shared memory, backtesting, execution algorithms. |
| **risk-execution** | Riesgo | Risk management, position sizing, market making, TCA, circuit breaker patterns, failure classification (6 tipos), Token Budget Governance, structured compaction, WAL. |
| **behavioral-economics** | Economia | Teoria de juegos (cooperativos/no-cooperativos), sesgos cognitivos, heuristicas, diseno de incentivos, mecanismos, toma de decisiones bajo incertidumbre. |

### Ciencia e Investigacion

| Skill | Categoria | Descripcion |
|-------|-----------|-------------|
| **alpha-research** | Investigacion | Factor research, feature engineering, ML avanzado, validacion estadistica, PaCoRe parallel exploration, LTS shared memory, Harness Effect token optimization. |
| **math-doc** | Academico | Documentos matematicos, LaTeX, proofs, estadistica, PaCoRe parallel reasoning, REPOREASON diagnostic metrics, catalogo de 38 metricas. |
| **science-doc** | Academico | Documentos cientificos, peer review, revisiones sistematicas, LTS shared memory, Token Maxing analysis, Doc-Researcher multimodal parsing, Arg-LLaDA summarization. |
| **physical-sciences** | Ciencias | Ciencias naturales experimentales: fisica, quimica, biologia, metodo cientifico, diseno experimental, analisis de datos cientificos. |

### Humanidades y Ciencias Sociales

| Skill | Categoria | Descripcion |
|-------|-----------|-------------|
| **psychology** | Psicologia | Psicologia aplicada a sistemas multi-agente: psicologia cognitiva, organizacional, del aprendizaje y positiva para mejorar interaccion y efectividad de agentes. |
| **education** | Educacion | Diseno instruccional (ADDIE, SAM, Agile), taxonomia de Bloom, andragogia, microlearning, spaced repetition, evaluacion educativa. |
| **ethics** | Filosofia | Etica de IA y filosofia aplicada: marcos eticos para agentes (deontologia, utilitarismo, virtud), alineamiento de valores, auditoria etica. |
| **linguistics** | Linguistica | Linguistica cognitiva, semiotica, pragmatica (Grice, Searle), analisis del discurso (RST, Toulmin), argumentacion y linguistica computacional. |
| **sociology** | Sociologia | Sociologia y antropologia para sistemas multi-agente: dinamicas de grupo (Tuckman, Belbin), teoria de redes (SNA), cultura digital, SECI. |
| **creative-design** | Diseno | Design Thinking, ideacion divergente/convergente, prototipado, branding, identidad visual, experiencia de usuario (no-code), creatividad aplicada. |

### Salud, Legal y Retail

| Skill | Categoria | Descripcion |
|-------|-----------|-------------|
| **healthtech** | Salud | Sistemas clinicos, interoperabilidad HL7/FHIR, HIPAA, datos clinicos, cumplimiento regulatorio, clinical decision support. |
| **legal-doc** | Legal | Analisis juridico colombiano multi-especialidad, RTF+C methodology, derecho comparado, Corte Constitucional, AOSE Hybrid Roles, structured output contracts, argument mining. |
| **pos-retail** | Retail | Punto de venta, operaciones retail, inventario, facturacion, pagos, logistica, TDAD test-driven compilation, SpecOps, FuzzAgent, TDFlow iterative fix. |

### Marketing y Riesgo

| Skill | Categoria | Descripcion |
|-------|-----------|-------------|
| **ads-optimizer** | Marketing | Optimizacion end-to-end de campanas Meta Ads con 12 sub-skills: BOAD para diseno automatico de estructura, ShapleyFlow para atribucion, MetaClaw para clasificacion de creativos, RL Bidding para pujas. |
| **risk-intelligence** | Riesgo | Identificacion y analisis de riesgos emergentes basado en CRO Forum 2026: riesgos tecnologicos (AI concentration, cyber), geopoliticos, climaticos, de salud y financieros. |

### Sostenibilidad y Meta

| Skill | Categoria | Descripcion |
|-------|-----------|-------------|
| **sustainability** | Sostenibilidad | ESG, huella de carbono (Scope 1/2/3), economia circular, cambio climatico, reportes GRI/SASB/TCFD, doble materialidad. |
| **evolve** | Meta | Auto-mejora continua del sistema: ciclo ASI-Evolve (Learn -> Design -> Experiment -> Analyze -> Deploy), Token Economics, Swarmind RL Scaling (KAT-Coder, PaCoRe Train), Spec Evolution (TDAD), Role Evolution (AOSE Hybrid), FDE, Autobuilder. |

---

## Nuevos Modulos (Julio 2026)

### Multi-Harness Adapter Layer

**Ubicacion:** `harness/orchestrator/multi_harness/`

Facilita la compatibilidad nativa con **5+ runtimes** sin perder `.opencode/` como SSOT:

| Runtime | Archivo | Estado |
|---------|---------|--------|
| **OpenCode** | `adapters/opencode_adapter.py` | Nativo |
| **Claude Code** | `adapters/claude_adapter.py` | Adaptado |
| **Codex CLI** | `adapters/codex_adapter.py` | Adaptado |
| **Cursor** | `adapters/cursor_adapter.py` | Adaptado |
| **Gemini CLI** | `adapters/gemini_adapter.py` | Adaptado |

**Componentes:**
- `RuntimeDetector`: Detecta automaticamente el runtime activo via variables de entorno, archivos de configuracion y firmas de CLI.
- `HarnessConverter`: Convierte comandos y configuraciones entre formatos de harness manteniendo el SSOT en `.opencode/`.
- `CLI Multi-Harness`: Comando `harness multi` para gestionar proyectos multi-runtime.

### Hook System

**Ubicacion:** `harness/hooks/`

Sistema de **hooks deterministas** que se ejecutan antes/despues de operaciones clave. A diferencia de los agentes LLM, los hooks son **100% deterministas** y no pueden ser controlados por el modelo.

| Tipo | Timing | Proposito |
|------|--------|-----------|
| `PRE_TOOL` | Antes de herramienta | Validar, rechazar o modificar comandos peligrosos |
| `POST_TOOL` | Despues de herramienta | Validar resultados de ejecucion |
| `ON_EDIT` | Post-escritura | Formatear, lintear, validar archivos modificados |
| `ON_NOTIFICATION` | Eventos del sistema | Responder a eventos asincronos |

**Arquitectura:**
- `HookRegistry`: Registro central de hooks (singleton thread-safe).
- `HookManager`: Orquestador que ejecuta hooks en orden de prioridad.
- **Prioridades:** CRITICAL (fail-fast), HIGH, NORMAL, LOW.
- **Builtin Hooks:** `security_validator_hook`, `permission_checker_hook`, `audit_logger_hook`, `metrics_collector_hook`.

**Ejemplo:**
```python
from harness.hooks import HookRegistry, HookManager, HookType

registry = HookRegistry()
registry.register(
    name="validate_sql",
    hook_type=HookType.PRE_TOOL,
    priority=HookPriority.CRITICAL,
    func=lambda ctx: "DROP" not in ctx.tool_input,
    description="Bloquea DROP statements en produccion"
)
manager = HookManager(registry)
results = manager.execute_pre_tool(context)
```

### Zero Trust Architecture

**Ubicacion:** `harness/security/zero_trust.py`

Modelo de **confianza cero** donde cada agente debe autenticarse, tener permisos explicitos y ser validado en cada interaccion. Basado en Google BeyondCorp y NIST SP 800-207.

**Principios:**
1. **Autenticacion obligatoria:** Cada agente tiene `AgentIdentity` unica.
2. **Minimo privilegio:** Permisos granulares por operacion y recurso.
3. **Validacion continua:** No confianza implicita — cada interaccion se evalua.
4. **Tokens rotativos:** Sesiones con expiracion automatica y renovacion.

**Componentes:**
- `AgentIdentity`: Identidad con `agent_id`, `role`, `public_key_hash`, `permissions`, `expires_at`.
- `SecureContext`: Contexto seguro con validacion HMAC de operaciones.
- `PermissionValidator`: Evaluacion de permisos contra politicas.
- `AuthenticationManager`: Gestion de identidades, tokens y rotacion.

### Federated Memory / Federated Vector Search

**Ubicacion:** `harness/orchestrator/federated_memory.py`

Sincronizacion automatica de conocimiento entre proyectos. Cada proyecto mantiene su base LanceDB local pero puede exportar/importar conocimiento federado.

**Tipos de conocimiento federado:**
| Tipo | Descripcion |
|------|-------------|
| `PATTERN` | Patrones de exito/fracaso por tipo de tarea |
| `PROMPT` | Prompts optimizados por agente |
| `ADR` | Decisiones arquitectonicas |
| `METRIC` | Metricas de rendimiento por skill |
| `EMBEDDING` | Vectores de conocimiento (search sharing) |
| `SKILL` | Skills y su efectividad medida |

**Arquitectura:**
```
  Proyecto A         Proyecto B         Proyecto C
  LanceDB_A          LanceDB_B          LanceDB_C
       \                 |                 /
        \                |                /
         ┌───────────────┴───────────────┐
         │      Federated Store          │
         │   (shared dir / S3 / Redis)   │
         └───────────────────────────────┘
```

**Funcionalidades:**
- Exportacion/importacion automatica via `FederatedMemory`.
- Sincronizacion en segundo plano con `BackgroundSync`.
- Busqueda paralela en 3 backends: LanceDB local, Federated Store, SQLite-vec.
- Vectores semanticos compartidos entre proyectos del mismo ecosistema.

### SQLite-vec Backend

**Ubicacion:** `harness/memory_rag/sqlite_vec_adapter.py`

Backend vectorial **portable** basado en sqlite-vec (extension vectorial para SQLite). Ideal para edge computing, dispositivos sin GPU y entornos offline.

| Caracteristica | Descripcion |
|----------------|-------------|
| **Dependencias** | Solo sqlite3 + numpy (sin servidores externos) |
| **Portabilidad** | Base de datos en un solo `.db` archivo |
| **Sincronizacion** | Compatible con Git (archivos pequenos) |
| **CI/CD** | Ideal para tests sin infraestructura |
| **Dimension default** | 384 (sentence-transformers all-MiniLM-L6-v2) |

**Componentes:**
- `SQLiteVecAdapter`: Adaptador principal con CRUD de vectores.
- `CollectionManager`: Gestion de colecciones vectoriales.
- `VectorIndex`: Indices IVF/PQ para busqueda aproximada.
- `SimilaritySearch`: Busqueda por similitud coseno con filtros.
- Fallback automatico a implementacion Python pura si sqlite-vec no esta instalado.

**Uso:**
```python
from harness.memory_rag.sqlite_vec_adapter import SQLiteVecAdapter

adapter = SQLiteVecAdapter("memory.db", dimension=384)
adapter.create_collection("knowledge")
adapter.insert("knowledge", vector=[0.1, 0.2, ...], metadata={"type": "pattern"})
results = adapter.search("knowledge", query_vector=[0.1, 0.2, ...], top_k=5)
```

---

## Asignacion Agente -> Skills

Cada agente carga los skills necesarios segun su dominio. La asignacion es gestionada por el `SkillBundler` (patron SIGMA).

| Agente | Skills que utiliza |
|--------|-------------------|
| **coordinator** | evolve, project-management, communication, risk-intelligence |
| **builder** | architecture, rust-lang, frontend-uiux, responsive-ui, data-science, devops-infra, security-audit, ads-optimizer |
| **scientist** | alpha-research, math-doc, science-doc, physical-sciences, behavioral-economics, ethics, linguistics |
| **guardian** | security-audit, risk-execution, risk-intelligence, devops-infra, legal-doc |
| **evolve** | evolve (meta), alpha-research, risk-intelligence, behavioral-economics |
| **architect** | architecture, evolve, communication |
| **backend-engineer** | rust-lang, architecture, security-audit, devops-infra |
| **frontend-engineer** | frontend-uiux, responsive-ui, creative-design, communication |
| **data-engineer** | data-science, devops-infra, architecture |
| **database-administrator** | architecture, security-audit, devops-infra |
| **devops** | devops-infra, security-audit, communication |
| **mobile-engineer** | frontend-uiux, responsive-ui, rust-lang, architecture |
| **qa-engineer** | security-audit, devops-infra, risk-execution |
| **security-engineer** | security-audit, risk-intelligence, devops-infra |
| **product-manager** | business-strategy, project-management, communication, behavioral-economics, creative-design |
| **researcher** | science-doc, math-doc, alpha-research, psychology, sociology |
| **reviewer** | architecture, security-audit, communication |
| **evolve-researcher** | evolve, alpha-research, science-doc, math-doc |
| **evolve-engineer** | evolve, devops-infra, data-science, ethics |
| **evolve-analyzer** | evolve, psychology, sociology, education, linguistics |

### Carga de Skills por Tipo de Proyecto

| Tipo de Proyecto | Skills incluidas |
|------------------|------------------|
| **Trading** (CQE, Onyx) | evolve, hedgefund, quant-trading, alpha-research, risk-execution, risk-intelligence, math-doc, science-doc |
| **Healthtech** (HC) | evolve, hedgefund, healthtech, legal-doc, science-doc, data-science, security-audit |
| **Retail** (PDV) | evolve, hedgefund, pos-retail, legal-doc, data-science, devops-infra |
| **Marketing** (Ads) | evolve, hedgefund, ads-optimizer, alpha-research, data-science, creative-design |
| **General** (Hermes) | evolve, hedgefund, math-doc, legal-doc, science-doc, healthtech, pos-retail, quant-trading, risk-execution |

---

## Ejemplos de Uso

### Activacion de Agentes por Palabra Clave

| Mensaje | Agente | Skills que carga |
|---------|--------|------------------|
| "implementa una API REST en Rust con autenticacion" | builder | rust-lang, architecture, security-audit |
| "disena la arquitectura del sistema de pagos" | architect | architecture, communication |
| "investiga papers sobre transformers eficientes" | scientist | alpha-research, science-doc |
| "audita la seguridad del sistema contra OWASP" | guardian | security-audit, risk-intelligence |
| "mejora el rendimiento del sistema multi-agente" | evolve | evolve (meta), alpha-research |
| "crea un dashboard financiero con graficos" | builder | frontend-uiux, responsive-ui, quant-trading |
| "analiza este contrato legal colombiano" | coordinator -> scientist | legal-doc |
| "genera campana de Meta Ads para ecommerce" | builder | ads-optimizer, data-science, creative-design |
| "despliega la aplicacion en Kubernetes" | devops | devops-infra, security-audit |
| "escribe tests para el modulo de pagos" | qa-engineer | security-audit, risk-execution |
| "revisa este PR de la rama feature/login" | reviewer | architecture, security-audit |
| "analiza riesgos emergentes del mercado" | guardian | risk-intelligence, behavioral-economics |
| "optimiza consultas SQL en PostgreSQL" | database-administrator | architecture, security-audit |
| "crea pipeline de datos para analytics" | data-engineer | data-science, devops-infra |

### Uso del Hook System

```python
from harness.hooks import HookRegistry, HookManager, HookType, HookPriority

# Registrar un hook personalizado
registry = HookRegistry()
registry.register(
    name="validate_api_key",
    hook_type=HookType.PRE_TOOL,
    priority=HookPriority.CRITICAL,
    func=lambda ctx: "API_KEY" not in ctx.tool_input or ctx.tool_input.startswith("sk-"),
    description="Valida que las API keys tengan formato correcto"
)

# Ejecutar hooks antes de cualquier tool call
manager = HookManager(registry)
results = manager.execute_pre_tool(context)
if any(r.status == HookResultStatus.BLOCKED for r in results):
    print("Operacion bloqueada por hook de seguridad")
```

### Uso del Sistema Zero Trust

```python
from harness.security.zero_trust import AgentIdentity, SecureContext, AgentRole, Permission

# Crear identidad de agente
identity = AgentIdentity(
    agent_id="builder-001",
    role=AgentRole.BUILDER,
    public_key_hash="a1b2c3d4...",
    permissions={"write:src/*", "read:hooks/*"}
)

# Validar operacion en contexto seguro
ctx = SecureContext(identity)
if ctx.has_permission("write:src/api/main.py"):
    ctx.execute_operation("write", "src/api/main.py")
```

### Uso de Federated Memory

```python
from harness.orchestrator.federated_memory import FederatedMemory, KnowledgeType

fm = FederatedMemory(project_dir=".", federated_dir="../shared_knowledge")

# Exportar conocimiento local
fm.export_knowledge(KnowledgeType.PATTERN, {
    "key": "task_planner:subtask_count",
    "value": {"avg": 5.2, "max": 12, "optimal": 4},
    "confidence": 0.92
})

# Importar conocimiento de otros proyectos
patterns = fm.import_knowledge(KnowledgeType.PATTERN, tags=["task_planner"])
```

### Uso de SQLite-vec

```python
from harness.memory_rag.sqlite_vec_adapter import SQLiteVecAdapter

# Inicializar almacen vectorial portable
adapter = SQLiteVecAdapter("Swarmind_memory.db", dimension=384)

# Crear colecciones
adapter.create_collection("tactical")   # Memoria a corto plazo
adapter.create_collection("strategic")  # Memoria a largo plazo
adapter.create_collection("learned")    # Conocimiento aprendido

# Insertar vectores
adapter.insert("tactical", vector=[0.1, 0.5, ...], metadata={
    "agent": "builder", "task": "API design", "timestamp": "2026-07-29T10:00:00Z"
})

# Busqueda por similitud
results = adapter.search("strategic", query_vector=[...], top_k=10, filters={"agent": "scientist"})
```

### Uso del SkillBundler (Composicion Dinamica)

```python
from harness.orchestrator.skill_bundler import SkillBundler

bundler = SkillBundler()
bundle = bundler.compose("Desarrollar API REST en Rust con PostgreSQL")
# Resultado: Agent('builder') con skills ['rust-lang', 'architecture', 'security-audit', 'devops-infra']
```

### Ciclo ASI-Evolve Completo

```bash
# 1. Investigar patrones de mejora
!evolve run --mode research --domain token-economics

# 2. Ejecutar candidato de mejora
!evolve run --mode engineer --candidate "structured-compaction-v2"

# 3. Analizar resultados y destilar lecciones
!evolve run --mode analyze --experiment "compaction-optimization"
```

---

## Sistema de Archivos

```
.opencode/
├── agents/              # 20 perfiles de agente (.md + .agent.min.md)
│   ├── coordinator.md
│   ├── builder.md
│   ├── scientist.md
│   ├── guardian.md
│   ├── evolve.md
│   ├── architect.md
│   ├── backend-engineer.md
│   ├── frontend-engineer.md
│   ├── data-engineer.md
│   ├── database-administrator.md
│   ├── devops.md
│   ├── mobile-engineer.md
│   ├── product-manager.md
│   ├── qa-engineer.md
│   ├── researcher.md
│   ├── reviewer.md
│   ├── security-engineer.md
│   ├── evolve-researcher.md
│   ├── evolve-engineer.md
│   ├── evolve-analyzer.md
│   └── auto/              # (agentes generados por evolve)
├── skills/              # 31 skills (SKILL.md + SKILL.min.md)
│   ├── skills_registry.yaml
│   ├── architecture/
│   ├── rust-lang/
│   ├── frontend-uiux/
│   ├── responsive-ui/
│   ├── data-science/
│   ├── devops-infra/
│   ├── security-audit/
│   ├── hedgefund/
│   ├── business-strategy/
│   ├── project-management/
│   ├── communication/
│   ├── quant-trading/
│   ├── risk-execution/
│   ├── behavioral-economics/
│   ├── alpha-research/
│   ├── math-doc/
│   ├── science-doc/
│   ├── physical-sciences/
│   ├── psychology/
│   ├── education/
│   ├── ethics/
│   ├── linguistics/
│   ├── sociology/
│   ├── creative-design/
│   ├── healthtech/
│   ├── legal-doc/
│   ├── pos-retail/
│   ├── sustainability/
│   ├── ads-optimizer/
│   ├── risk-intelligence/
│   └── evolve/
├── core/
│   ├── base_principles.md
│   ├── guardrails.yaml
│   ├── routing_rules.yaml
│   └── config/
└── config/
    ├── routing_rules.yaml
    ├── project_config.yaml
    └── token_budgets.yaml

harness/
├── orchestrator/
│   ├── task_orchestrator.py
│   ├── agent_bus.py
│   ├── worktable.py
│   ├── skill_bundler.py
│   ├── token_optimizer.py
│   ├── federated_memory.py        # (NUEVO)
│   ├── difficulty_router.py
│   ├── adaptive_planner.py
│   ├── task_planner.py
│   ├── multi_harness/             # (NUEVO)
│   │   ├── __init__.py
│   │   ├── runtime_detector.py
│   │   ├── converter_base.py
│   │   └── adapters/
│   │       ├── opencode_adapter.py
│   │       ├── claude_adapter.py
│   │       ├── codex_adapter.py
│   │       ├── cursor_adapter.py
│   │       └── gemini_adapter.py
│   ├── scheduler.py
│   ├── write_ahead_log.py
│   └── ...
├── hooks/                        # (NUEVO)
│   ├── __init__.py
│   ├── hook_manager.py
│   ├── hook_registry.py
│   └── builtin_hooks.py
├── security/                     # (NUEVO)
│   ├── __init__.py
│   └── zero_trust.py
├── memory_rag/
│   ├── ...
│   ├── sqlite_vec_adapter.py     # (NUEVO)
│   └── ...
├── tools_sandbox/
├── evolve_loop/
├── tests/                        # 1894+ tests (52+ suites)
└── ...
```

---

## Worktable: Sistema de Debate Multi-Agente

El **Worktable** implementa un sistema de debate donde 13 expertos en calidad de software discuten propuestas y llegan a un compendio. Soporta dos modos.

### Modo Critico (13 Expertos en Calidad)

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

**3 rondas:** Opening -> Critique -> Refinement -> Compendium

### Modo Creativo (ReDNA Pipeline)

Activa el pipeline divergente -> convergente para generacion de ideas innovadoras.

```python
wt = Worktable()
compendio = wt.debate("Disenar una API innovadora", creative_mode=True)
```

**Fases:**
- **Divergente:** Agentes generan N ideas libremente, sin compartir, de forma aislada.
- **Convergente:** Ideas evaluadas por novedad (40%) y factibilidad (60%).
- **Integracion:** Top 3 ideas se combinan en propuesta final.

**Proteccion contra Diversity Collapse:**
- Topologia sparse (no acoplamiento estructural).
- 2 rondas de generacion aislada antes de compartir.
- Presion divergente del 30% para opiniones disidentes.
- Penalizacion del 10% a deferencia de autoridad.

---

## Token Optimizer

El `TokenOptimizer` implementa tres tecnicas de optimizacion:

| Tecnica | Impacto | Descripcion |
|---------|---------|-------------|
| **Structured Output** | -40% tokens | Reemplaza texto libre con JSON Schema tipado en respuestas |
| **DAG Pipeline Parallelism** | 1.5-2.4x speedup | Grafo de dependencias con algoritmo de Kahn, ejecucion paralela |
| **Token Budget Manager** | Control granular | Presupuestos diferenciables por rol de agente |

---

## Command Reference

```bash
# Gestion de agentes
harness agent list                          # Listar agentes disponibles
harness agent show <nombre>                 # Mostrar detalle de agente
harness agent compile                       # Compilar agentes (minificacion)

# Gestion de skills
harness skill list                          # Listar skills disponibles
harness skill show <nombre>                 # Mostrar detalle de skill
harness skill compile                       # Compilar skills (minificacion)

# Multi-harness
harness multi detect                        # Detectar runtime activo
harness multi convert <origen> <destino>    # Convertir entre formatos de harness

# Hooks
harness hooks list                          # Listar hooks registrados
harness hooks test                          # Ejecutar test de hooks

# Memoria federada
harness memory federated export             # Exportar conocimiento local
harness memory federated import             # Importar conocimiento federado

# Auto-mejora (Evolve)
!evolve run --mode research --domain <dominio>
!evolve run --mode engineer --candidate <id>
!evolve run --mode analyze --experiment <id>

# Zero Trust
harness security identity list              # Listar identidades de agentes
harness security identity create <agent>    # Crear identidad para agente

# Debate
harness debate <topic>                      # Ejecutar debate critico
harness debate <topic> --creative           # Ejecutar debate creativo
```

---

*Documentacion generada el 29 Julio 2026. Sistema Swarmind v4.0 — 20 agentes, 31 skills, 5 nuevos modulos.*
