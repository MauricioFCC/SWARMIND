# Onyx Multi-Agent Harness

**Template portable de sistema multi-agente autónomo** con LanceDB, RAG, y auto-mejora.

Copia la carpeta `AGENTIC/` a cualquier proyecto como asistente de desarrollo inteligente.
El Harness orquesta 21 agentes especializados, gestiona memoria vectorial via LanceDB,
y evoluciona sus propios prompts automaticamente mediante el loop ASI-Evolve.

---

## Estructura (lo que se pega en tu proyecto)

```
tu-proyecto/
├── .opencode/                   # Cerebro: reglas, perfiles, skills
│   ├── agents/                  # Perfiles de 21 agentes
│   ├── skills/                  # Skills del sistema (19 skills)
│   │   └── auto/                # Skills auto-generadas (memoria procedural)
│   ├── core/                    # Router v2, guardrails, registry
│   └── config/                  # Reglas de enrutamiento, budgets
├── harness/                     # Motor de ejecucion (ESTE DIRECTORIO)
│   ├── orchestrator/            # Planificador, delegacion, sandbox
│   ├── memory_rag/              # Memoria vectorial LanceDB
│   │   ├── lance_vector_store.py  # Interface unificada con LanceDB
│   │   ├── doc_ingester.py        # Ingesta de documentos para RAG
│   │   └── context_assembler.py   # Ensamblador de contexto RAG
│   ├── evolve_loop/             # Auto-mejora ASI-Evolve
│   │   ├── self_improver.py       # Loop de mejora continua
│   │   └── cognition_sync.py      # Sincronizacion de cognicion
│   ├── tools_sandbox/           # Ejecucion segura de herramientas
│   ├── scripts/                 # Utilidades del Harness
│   │   ├── init.py               # Bootstrap del proyecto
│   │   └── generate_llms_txt.py  # Genera /llms.txt para LLMs externos
│   ├── db/                      # Datos persistentes
│   │   └── lancedb_store/        # Base vectorial LanceDB
│   ├── run.py                   # Punto de entrada CLI
│   ├── README.md                # Esta documentacion
│   └── AGENTS.md                # Manifiesto completo de agentes
├── docs/                         # Documentacion tecnica
├── src/                          # Codigo fuente de tu proyecto
├── tests/                        # Tests
└── llms.txt                      # Contexto curado para LLMs externos
```

---

## Requisitos

- **Python 3.10+**
- **LanceDB** (se instala automaticamente con `init.py` o manual: `pip install lancedb`)
- Dependencias adicionales: `numpy`, `pyyaml`

---

## Uso rapido

```bash
# 1. Inicializar el entorno (instala LanceDB + crea estructura)
python harness/scripts/init.py

# 2. Delegar una tarea a un agente
python harness/run.py "@software-engineer: Crea un endpoint REST para usuarios"

# 3. Generar /llms.txt para consumo por LLMs externos
python harness/scripts/generate_llms_txt.py

# 4. Iniciar el bucle de auto-mejora sobre un skill
python -c "from harness.evolve_loop.self_improver import SelfImprover; SelfImprover().run_round('software-engineer', rounds=3)"
```

---

## Agentes Disponibles (21)

| Rol | Dominio principal | Delegacion |
|-----|------------------|------------|
| @project-manager | Orquestacion F.R.A.M.E., planificacion | `@pm` |
| @context-engineer | Curation de contexto, token budget, RAG | `@context` |
| @tool-mcp-engineer | Ecosistema MCP, herramientas | `@mcp` |
| @software-engineer | APIs, servicios, full-stack | `@swe` |
| @data-architect | Schemas, modelos, migraciones | `@data` |
| @devops-sre | CI/CD, Docker, infraestructura | `@devops` |
| @security-engineer | Seguridad, compliance, hardening | `@sec` |
| @frontend-engineer | UI/UX, dashboards | `@frontend` |
| @mobile-engineer | Apps iOS/Android | `@mobile` |
| @ai-engineer | ML/AI, pipelines, LLMOps | `@ai` |
| @quality-gate | QA, tests, cobertura | `@qa` |
| @documentation-specialist | Documentacion tecnica | `@docs` |
| @requirements-analyst | Analisis de requerimientos | `@ra` |
| @enterprise-architect | Arquitectura de sistemas, ADR | `@architect` |
| @quant-developer | Estrategias cuantitativas, brokers | `@quant` |
| @quant-scientist | Validacion estadistica, experimentos | `@scientist` |
| @risk-manager | Gestion de riesgo, position sizing | `@risk` |
| @trading-operations | Monitoreo en vivo, alertas | `@ops` |
| @evolve-researcher | Investigacion de mejoras | `!evolve run` |
| @evolve-engineer | Ejecucion de mejoras | `!evolve run` |
| @evolve-analyzer | Analisis de resultados | `!evolve run` |

Ver `harness/AGENTS.md` para el manifiesto detallado.

---

## Arquitectura

### Memoria Vectorial (LanceDB)
- **LanceDB** es el nucleo de memoria del sistema: almacena vectores de embedding, metadatos, y permite busqueda semantica.
- **Obligatorio**: El sistema falla con un mensaje claro si LanceDB no esta instalado.
- **Fallback in-memory**: Solo disponible con `LanceVectorStore(allow_fallback=True)` para emergencias/test.

### RAG (Retrieval-Augmented Generation)
- Los documentos en `docs/`, `harness/`, y `.opencode/` se ingieren automaticamente.
- Los chunks se vectorizan y almacenan en la coleccion `rag_chunks` de LanceDB.
- El `ContextAssembler` recupera los chunks mas relevantes segun la tarea.

### Auto-mejora (ASI-Evolve)
- El loop `SelfImprover` ejecuta rondas de mejora sobre cualquier skill.
- Usa GEPA mutation + C.A.S.E. evaluation + procedural memory.
- Los resultados se almacenan en `asi_cognition_store`.

### Enrutamiento Multi-Agente
- Router v2 con grafo de estado: single-agent, secuencial, paralelo, o loop.
- Guardrails pre/post con 19 checks de seguridad y calidad.

---

## Comandos

```bash
python harness/run.py "@rol:描述"          # Delegar tarea
python harness/scripts/init.py              # Bootstrap
python harness/scripts/generate_llms_txt.py # Generar contexto LLM
```

### Evolve Loop
```bash
python -c "from harness.evolve_loop.self_improver import SelfImprover; SelfImprover().run_round('software-engineer', rounds=3)"
```

---

## Principios

- **Portable:** Sin dependencias de sistema operativo. Windows, macOS y Linux.
- **Agnostico:** Sin preferencia de lenguaje o framework. Se adapta a tu proyecto.
- **Evolutivo:** GEPA mutation + C.A.S.E. evaluation + procedural memory.
- **Memoria persistente:** LanceDB como unico storage default. Sin fallback silencioso.
- **Documentacion viva:** Toda decision tecnica se documenta en ADR.

---

## Inspiracion

- Hermes Agent (NousResearch) — memoria procedural, GEPA, /llms.txt
- Arquitectura de Integracion Actualizada — harness + context + hermes
- FDE (Forward Deployment Engineering) — 7 pilares para skills robustos
