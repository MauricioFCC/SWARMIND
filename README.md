# README.md

# Onyx Multi-Agent Harness

**Portable, language-agnostic, self-evolving multi-agent system base.**

Copia esta carpeta a cualquier proyecto y ejecuta `python harness/scripts/init.py` para
inicializar el entorno. El Harness orquesta agentes, gestiona memoria via
LanceDB (con fallback en memoria), y evoluciona sus prompts automaticamente.

## Estructura

```
mi-proyecto/
├── .opencode/                   # Cerebro: reglas, perfiles, skills
│   ├── agents/                  # Perfiles de agentes
│   ├── skills/                  # Skills del sistema
│   │   └── auto/                # Skills auto-generadas (memoria procedural)
│   └── config/                  # Reglas de enrutamiento
├── harness/                     # Motor de ejecucion
│   ├── orchestrator/            # Planificador y delegacion
│   ├── memory_rag/              # Memoria vectorial (LanceDB + fallback)
│   ├── evolve_loop/             # Auto-mejora C.A.S.E. + GEPA
│   ├── tools_sandbox/           # Ejecucion segura de herramientas
│   ├── scripts/                  # Utilidades del Harness
│   │   ├── init.py               # Bootstrap del proyecto
│   │   └── generate_llms_txt.py  # Genera /llms.txt
│   ├── mkdocs.yml                # Configuracion de documentacion
│   └── run.py                    # Punto de entrada CLI
├── docs/                         # Documentacion tecnica
├── src/                          # Codigo fuente de tu proyecto
├── tests/                        # Tests
├── AGENTS.md                     # Manifest de agentes (estilo Hermes)
└── llms.txt                      # Contexto curado para LLMs externos
```

## Uso rapido

```bash
# Inicializar en un proyecto nuevo
python harness/scripts/init.py

# Delegar una tarea a un agente
python harness/run.py "@software-engineer: Crea un endpoint REST"

# Generar /llms.txt para consumo por LLMs externos
python harness/scripts/generate_llms_txt.py

# Iniciar el bucle de auto-mejora
python -c "from harness.evolve_loop.self_improver import SelfImprover; SelfImprover().run_round('software-engineer', rounds=3)"
```

## Agentes

21 agentes especializados disponibles. Ver `AGENTS.md` para el manifesto completo.

## Principios

- **Portable:** Sin dependencias de sistema operativo. Funciona en Windows, macOS y Linux.
- **Agnostico:** Sin preferencia de lenguaje o framework. Se adapta a tu proyecto.
- **Evolutivo:** GEPA mutation + C.A.S.E. evaluation + procedural memory.
- **Memoria persistente:** LanceDB con fallback automatico a SQLite/dict in-memory.

## Inspiracion

- Hermes Agent (NousResearch) — memoria procedural, GEPA, /llms.txt
- Arquitectura de Integracion Actualizada — harness + context + hermes
