# Swarmind — Onboarding Seguro + Research First

> **Research First**: Antes de ejecutar cualquier comando en este proyecto,
> INVESTIGA el estado del arte. Busca mejoras, herramientas, frameworks
> mas recientes. Este proyecto es atemporal: cada setup comienza con
> investigacion, no con automatismo ciego.

## ⚡ Filosofia de Implementacion

### Research First (Regla #1)
```
ANTES DE HACER CUALQUIER COSA:
1. Buscar estado del arte actual (web search, papers, herramientas)
2. Identificar si hay mejoras disponibles sobre lo documentado
3. Documentar brevemente la fuente y por que es la mejor opcion
4. Solo entonces ejecutar
```

Esto hace el sistema **atemporal**: la vanguardia se renueva sola porque
cada tarea comienza con investigacion actual.

### Idempotencia (Regla #2)
```
SI YA ESTA IMPLEMENTADO, NO REIMPLEMENTAR:
1. Verificar si la funcionalidad ya existe (git log, ADRs, cognition store)
2. Si existe y funciona → pasar a la siguiente tarea
3. Solo reimplementar si hay una MEJORA demostrable (delta > 0)
4. Documentar el delta: que mejora, en cuanto, por que es superior
```

Esto evita **redundancia**: el sistema no hace trabajo repetido.
Cada ejecucion agrega valor nuevo o no se ejecuta.

### Seguridad por Defecto
- 0 secretos hardcodeados (siempre `os.getenv()`)
- `.env` en `.gitignore` — jamas se commitea
- `sys.path.insert(1, ...)` nunca `insert(0, ...)` — no sobreescribe rutas del sistema
- Todas las rutas con `pathlib.Path`, nunca strings crudos
- Todos los `except Exception:` tienen `logger.warning()` — 0 excepciones silenciosas

---

## 📦 Instalacion en PC Nuevo

### 1. Pre-requisitos

```powershell
# Python 3.12+ (3.10 EOL 2026-10-31, 3.11 EOL 2027-10-31)
winget install astral-sh.uv
uv python install 3.12

# Git
winget install Git.Git

# Editor (OpenCode recomendado)
winget install OpenCode
```

### 2. Clonar e Investigar

```powershell
# Clonar
git clone <repo-url> Swarmind
cd Swarmind

# 🔬 RESEARCH FIRST: Antes de instalar, investiga
# ?Que ha cambiado desde la ultima vez?
# Buscar: "uv pip vs poetry 2026", "python package management best practices 2026"
```

### 3. ⚡ Setup Automático (estándar v2.5 — recomendado)

Un solo comando configura todo: verifica Python >= 3.12, instala uv,
instala dependencias, sincroniza cerebro + motor a opencode global y
verifica la instalación.

```powershell
# Configuracion inicial completa
python scripts/setup_swarmind.py

# (Opcional) solo simular
python scripts/setup_swarmind.py --dry-run
```

### 4. Configuración Manual (alternativa paso a paso)

```powershell
# Entorno + dependencias
uv sync --extra dev

# Copiar .env y configurar API keys
cp .env.example .env

# Instalar hook pre-commit (QA rapido + sync global automatico en cada commit)
uv run python harness/scripts/install_hooks.py --install

# Sincronizar CEREBRO + MOTOR a opencode global (~/.config/opencode/)
uv run python scripts/sync_opencode_global.py

# Verificar config
python -c "import harness; print(f'✅ Harness OK')"
```

### 5. Verificar Instalacion

```powershell
# Ejecutar tests
uv run python -m pytest harness/tests/ -x -q

# Reglas universales + auto-mejora (ADR-0037)
uv run pytest harness/tests/test_universal_rules.py -q
uv run pytest harness/tests/test_opencode_config_sync.py -q

# Health check
uv run python -c "
from harness.orchestrator.health import HealthChecker
hc = HealthChecker()
print(hc.check_liveness())
"
```

### 6. Opción A v2.5 — OpenCode Global = Fuente de Verdad Total

Swarmind centraliza **cerebro** (agents/skills/core) y **motor** (harness/)
en `~/.config/opencode/` (**SSOT global**). Los proyectos de DEV-SPACE
conservan solo `.opencode/` + skills + config propia (sin copiar harness,
eliminando ~5.3 GB de duplicación).

```powershell
# 1. Sync cerebro + motor al global opencode
uv run python scripts/sync_opencode_global.py

# 2. Solo cerebro (si ya sincronizaste el motor)
uv run python scripts/sync_opencode_global.py --cerebro

# 3. Solo motor (harness)
uv run python scripts/sync_opencode_global.py --motor

# 4. Desplegar a proyectos DEV-SPACE (.opencode/ + skills, sin harness)
uv run python scripts/deploy_all.py --dry-run    # Ver que va a hacer
uv run python scripts/deploy_all.py              # Ejecutar deploy completo
```

> **Reinicia opencode** despues del primer sync (la config se carga al inicio).
> **Proyectos que importen harness**: usa PYTHONPATH al global.
> Guia completa: [docs/src/es/guide/opcion-a-ssot-global.md](docs/src/es/guide/opcion-a-ssot-global.md)
> ADR: [ADR-0036](docs/src/es/adr/adr0036-opcion-a-ssot-global-2026.md)

### 7. Memoria Central + Backup Automático (estándar v3.x)

La memoria vive **UNA vez** en `<Documents>/Memory_Proyects` (portable via
`MEMORY_ROOT`). Antes era local por proyecto (duplicada); ahora es central.

```powershell
# 1. Configurar memoria central (construye estructura + preserva db LanceDB)
uv run python scripts/setup_memory_central.py

# 2. Menú de configuración interactivo (MEMORY_ROOT, backup, frecuencia, rotación)
uv run python scripts/config_swarmind.py

# 3. Backup manual + ver backups
uv run python scripts/backup_memory.py --force     # backup inmediato
uv run python scripts/backup_memory.py --list      # listar backups

# 4. Registrar tarea programada (Windows Task Scheduler / Linux cron)
uv run python scripts/backup_memory.py --schedule
```

**Seguridad de datos (ADR-0038)**:
- NUNCA se borra la db sin backup previo.
- Backup automático cada N horas/días/commit (configurable en el menú).
- Rotación automática: conserva los N backups más recientes.
- Restaurar: `python scripts/backup_memory.py --restore <dir>`.

### 8. Investigar Mejoras (Research First Loop)

```powershell
# Antes de empezar a trabajar, investiga el estado del arte:
# 1. Token Economics: ?Sigue siendo el Harness Effect lo mas avanzado?
#    Buscar: "token optimization Swarmind systems 2026"
# 2. Competitive Programming: ?Hay algoritmos mejores que Stoer-Wagner?
#    Buscar: "competitive programming algorithms 2026 state of the art"
# 3. Text Analysis: ?Sigue Doc-Researcher siendo el mejor?
#    Buscar: "multi-modal document understanding 2026"
# 4. OpenCode: ?Hay nuevas versiones con features que podamos usar?
#    Buscar: "opencode 2026 changelog"
```

---

## 🧠 Arquitectura del Sistema

```
Swarmind/
├── .opencode/             # CEREBRO SSOT (20 agents, 31 skills, core, registry)
│   ├── agents/            # coordinator, builder, scientist, guardian, evolve, ...
│   ├── config/            # project_config, routing_rules, token_budgets (config propia del proyecto)
│   ├── core/              # router, guardrails, registry, base_principles, prompt_optimizer
│   ├── federated/         # memoria federada entre proyectos
│   └── skills/            # 31 skills (SKILL.md + SKILL.min.md + skills_registry.yaml)
├── harness/               # Motor de orquestacion Python (VIVE EN OPENCODE GLOBAL, v2.5)
│   ├── orchestrator/      # Planificador, health, telemetria, self-healing
│   ├── memory_rag/        # Memoria vectorial LanceDB + Token Economics
│   ├── evolve_loop/       # Auto-mejora ASI-Evolve
│   ├── model_router/      # Routing local/cloud
│   ├── tools_sandbox/     # MCP tools
│   ├── tests/             # 3937 tests + TDD + universal_rules + config_sync
│   ├── scripts/           # install_hooks.py (pre-commit), end_of_iteration, ...
│   └── qa/                # security_policy.py (scanner ADR-0035)
├── scripts/               # setup_swarmind.py, sync_opencode_global.py, setup_memory_central.py,
│                          # backup_memory.py, config_swarmind.py, deploy_all.py
├── docs/                  # ADRs (0001-0037) + guias + manuales
├── SETUP.md               # Este archivo
├── ~/.config/opencode/    # SSOT GLOBAL: cerebro (.opencode/) + motor (harness/)
└── <Documents>/Memory_Proyects/  # MEMORIA CENTRAL portable (MEMORY_ROOT)
    ├── knowledge/         # conocimiento por dominio
    ├── syntheses/         # sintesis de sesiones
    ├── 99_Hermes_Brain/   # cerebro central
    ├── data/lancedb/      # db central (con backup automatico)
    └── backups/           # copias de seguridad (rotacion automatica)
```

> **Opción A v2.5**: opencode global (`~/.config/opencode/`) es la fuente de
> verdad TOTAL. Cerebro (.opencode/) y motor (harness/) viven UNA vez ahí.
> Los proyectos reciben solo `.opencode/` + skills. Ver
> [docs/src/es/guide/opcion-a-ssot-global.md](docs/src/es/guide/opcion-a-ssot-global.md)
> y [ADR-0036](docs/src/es/adr/adr0036-opcion-a-ssot-global-2026.md).

### Reglas Universales (ADR-0037)

El sistema aplica 10 reglas universales de código, validadas por tests con
auto-mejora:

| Regla | Qué valida | Test |
|-------|-----------|------|
| UPG | Últimas versiones estables | test_universal_rules.py |
| NAM | Naming (snake_case, PascalCase) | test_universal_rules.py |
| TYP | Type hints PEP 604/585 | test_universal_rules.py |
| IMM | Immutability (frozen, NamedTuple) | test_universal_rules.py |
| SOL | SOLID principles | test_universal_rules.py |
| MAG | Sin magic numbers | test_universal_rules.py |
| FSZ | Function size (umbral gradual) | test_universal_rules.py |
| CMP | Composition over inheritance | test_universal_rules.py |
| DEM | Law of Demeter | test_universal_rules.py |
| CFG | Config YAML sync con realidad | test_opencode_config_sync.py |

### Agentes Core

| Agente | Responsabilidad | Cutting-Edge 2026 |
|--------|----------------|-------------------|
| **coordinator** | Swiss Watch orchestrator | Token Economics, Dynamic Scaling, Failure Governance |
| **builder** | Implementacion + CP | TDAD, PaCoRe, 30+ tecnicas CP |
| **scientist** | Investigacion + AI/ML | PaCoRe/LTS, 38-metric catalogue, Doc-Researcher |
| **guardian** | Calidad + Testing | PROBE, SpecOps, AdverTest, SMART, FuzzAgent |
| **evolve** | Auto-mejora | RL Scaling, Spec Evolution, FDE |

### Token Economics (6 mecanismos)

| Mecanismo | Impacto | Donde |
|-----------|---------|-------|
| Cache-Shape Discipline | -38% tokens | context_window_manager.py |
| Structured Compaction | -41% costo | optimization_pipeline.py |
| Scoped Context Spawn | -44% tiempo | adaptive_planner.py |
| Phase-Scheduled MAS | -27.3% tokens | adaptive_planner.py |
| Observation Masking | -60% obs. tokens | context_window_manager.py |
| Failure-Spend Governance | Elimina runaway | token_budget.py |

---

## 🔒 Seguridad

### Secrets
```powershell
# NUNCA hardcodear API keys
# Usar siempre variables de entorno:
from os import getenv
API_KEY = getenv("ZENFREE_API_KEY")  # ✅ Correcto
API_KEY = "sk-..."                    # ❌ Nunca
```

### Paths
```python
# SIEMPRE usar pathlib:
from pathlib import Path
Path(__file__).resolve().parent  # ✅ Correcto
os.path.dirname(os.path.abspath(__file__))  # ❌ Obsoleto
```

### Error Handling
```python
# SIEMPRE loggear excepciones:
try:
    risky_operation()
except Exception as exc:
    logger.warning("Contexto: %s", exc)  # ✅ Correcto
except Exception:
    pass  # ❌ Nunca
```

### sys.path
```python
# Usar insert(1, ...) no insert(0, ...):
sys.path.insert(1, str(Path(__file__).resolve().parent))  # ✅ Correcto
sys.path.insert(0, ...)  # ❌ No sobreescribir rutas del sistema
```

---

## 🔬 Research First — Ejemplos Concretos

### Al empezar una tarea de codigo:
```powershell
# MAL: Ir directo a codificar
python harness/run.py "@builder: implementa un segment tree"

# BIEN: Investigar primero
# Buscar: "segment tree implementations 2026 optimized"
# Buscar: "best segment tree library python 2026"
# Elegir la mas avanzada, documentar fuente, luego codificar
```

### Al diagnosticar un error:
```powershell
# MAL: Asumir la causa y aplicar fix conocido

# BIEN: Investigar el error actual
# Buscar: error message exacto
# Buscar: "python {error_type} 2026 fix"
# Solo despues de entender, aplicar solucion
```

### Al proponer mejora:
```powershell
# MAL: "Hay que refactorizar X porque esta feo"

# BIEN:
# 1. Investigar patrones actuales para el problema
# 2. Buscar papers/frameworks/herramientas 2026
# 3. Documentar por que la nueva opcion es superior
# 4. Implementar con fallback plan (SURS >= 90%)
```

---

## 📚 Referencias

- `docs/src/adr/` — Architecture Decision Records (0001-0037)
- `.opencode/core/base_principles.md` — 9+ categorias universales (v2.4.0)
- `.opencode/core/fde_principles.md` — Forward Deployment Engineering
- `harness/common.py` — SSOT: embedding, tokens, compression
- `harness/tests/test_universal_rules.py` — Reglas universales + auto-mejora (ADR-0037)
- `harness/tests/test_opencode_config_sync.py` — Config YAML sync (ADR-0037)
- `.env.example` — Variables de entorno documentadas

---

## 🚀 Proximo Paso

```powershell
# 🔬 RESEARCH FIRST: Investiga antes de ejecutar
# Buscar: "Swarmind project improvements 2026"
# Buscar: "opencode multi-agent framework latest"
# Buscar: "token economics for LLM agents 2026"

# Luego:
uv run python -m pytest harness/tests/ -x -q
uv run python scripts/deploy_all.py --dry-run
```

*"Cada setup comienza con investigacion. La vanguardia se renueva sola."*
