# AGENTIC — Multi-Agent Evolutionary Harness

**Template portable de sistema multi-agente autónomo con LanceDB, RAG, y auto-mejora.**

> Copia las carpetas `harness/` y `.opencode/` a la raíz de tu proyecto.
> Listo para usar en minutos.

---

## Estructura

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
└── llms.txt                     # Contexto curado para LLMs externos
```

---

## Requisitos

- **Python 3.10+**
- **LanceDB** (se instala automaticamente con `init.py` o manual: `pip install lancedb`)
- Dependencias adicionales: `numpy`, `schedule`, `pyyaml`

---

## Inicio rapido

```bash
# 1. Copiar a tu proyecto
# cp -r AGENTIC/harness/   /tu-proyecto/harness/
# cp -r AGENTIC/.opencode/ /tu-proyecto/.opencode/

# 2. Inicializar el entorno
cd /tu-proyecto/
python harness/scripts/init.py

# 3. Iniciar el harness
python harness/run.py "@project-manager: planificar proyecto"

# 4. (Opcional) Resetear estado para empezar limpio
python harness/reset_state.py
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

## Comandos CLI

```bash
# Delegar tarea a un agente
python harness/run.py "@software-engineer: Implementa <tu-tarea>"

# Iniciar scheduler en background
python harness/run.py --daemon

# Modo gateway interactivo
python harness/run.py --gateway cli

# Programar job recurrente
python harness/run.py '!schedule add daily-check --cron "0 9 * * 1-5" --task "@quality-gate: validar sistema"'

# Listar jobs programados
python harness/run.py '!schedule list'

# Mutar y evolucionar prompt de un agente
python harness/run.py '!evolve mutate @software-engineer "<tu-tarea-de-prueba>"'

# Resetear estado del harness
python harness/reset_state.py
```

---

## Arquitectura

### Memoria Vectorial (LanceDB)
- **LanceDB** es el nucleo de memoria del sistema: almacena vectores de embedding, metadatos, y permite busqueda semantica.
- **Obligatorio**: El sistema falla con un mensaje claro si LanceDB no esta instalado.
- **Fallback in-memory**: Solo disponible con `LanceVectorStore(allow_fallback=True)` para emergencias/test.

### RAG (Retrieval-Augmented Generation)
- Los documentos en `harness/`, y `.opencode/` se ingieren automaticamente.
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

## 🔄 Migración de Base de Datos

Al actualizar el harness en un proyecto existente (ej. copias un nuevo `harness/` sobre uno viejo), tus datos de LanceDB pueden necesitar migración si la estructura de colecciones cambió entre versiones.

### Flujo recomendado

```bash
# 1. Backup: Copia tu BD actual a la carpeta de import
cp -r harness/db/lancedb/ harness/db/import/mi-proyecto-v1/

# O si ya sobrescribiste el harness y la BD está en la ubicación vieja:
mv harness/db/lancedb/ harness/db/import/mi-proyecto-v1/

# 2. Migrar: Ejecuta init.py (lo detecta automáticamente)
python harness/scripts/init.py

# O manualmente:
python harness/run.py "!db migrate"

# 3. Verificar:
python harness/run.py "!db stats"

# 4. Rollback (si algo falla):
python harness/run.py "!db rollback harness/db/import/_backup_20260101_120000/"
```

### Comandos disponibles

| Comando | Descripción |
|---------|-------------|
| `!db migrate` | Migra todas las BDs encontradas en `harness/db/import/` |
| `!db migrate --path <ruta>` | Migra una BD específica |
| `!db list-imports` | Lista las BDs disponibles para importar |
| `!db stats` | Muestra estadísticas de la BD activa |
| `!db rollback <backup>` | Restaura desde un backup pre-migración |

### ¿Qué maneja el migrador?

- ✅ **Colecciones con schema exacto** → copia directa de datos
- ✅ **Colecciones con schema modificado** → transformación automática de campos (rellena defaults, renombra si es necesario)
- ✅ **Nuevas colecciones** → creadas vacías automáticamente
- ✅ **Colecciones obsoletas** → archivadas como JSON con advertencia
- ✅ **Vectores de distinta dimensión** → truncado/padding automático
- ✅ **Backups automáticos** → cada migración genera un backup en `_backup_<timestamp>/`
- ✅ **Rollback** → restaurar desde backup si algo sale mal

### Ejemplo de migración

```bash
# Preparar BD de prueba (simula BD vieja)
mkdir -p harness/db/import/vieja/
python -c "
from harness.memory_rag.lance_vector_store import LanceVectorStore
store = LanceVectorStore('harness/db/import/vieja/')
import numpy as np
store.insert('rag_chunks', np.random.rand(3, 384), [
    {'id': '1', 'domain': 'test', 'chunk': 'test data', 'source': 'old'},
    {'id': '2', 'domain': 'test', 'chunk': 'more data', 'source': 'old'},
    {'id': '3', 'domain': 'test', 'chunk': 'extra data', 'source': 'old'},
])
print('BD de prueba creada en import/')
"

# Listar imports disponibles
python harness/run.py "!db list-imports"

# Migrar
python harness/run.py "!db migrate"

# Verificar datos migrados
python harness/run.py "!db stats"
```

---

## Principios

- **Portable:** Sin dependencias de sistema operativo. Windows, macOS y Linux.
- **Agnostico:** Sin preferencia de lenguaje o framework. Se adapta a tu proyecto.
- **Evolutivo:** GEPA mutation + C.A.S.E. evaluation + procedural memory.
- **Memoria persistente:** LanceDB como unico storage default.
- **Documentacion viva:** Toda decision tecnica se documenta en ADR.
