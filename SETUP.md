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
# Python 3.11+ (recomendado: via uv)
winget install astral-sh.uv
uv python install 3.11

# Git
winget install Git.Git

# Editor
winget install OpenCode
```

### 2. Clonar e Investigar

```powershell
# Clonar
git clone <repo-url> Swarmind
cd Swarmind

# 🔬 RESEARCH FIRST: Antes de instalar, investiga
# ?Que ha cambiado desde la ultima vez?
# ?Hay nuevas herramientas de virtualenv/package management?
# Buscar: "uv pip vs poetry 2026", "python package management best practices 2026"
```

### 3. Entorno Virtual + Dependencias

```powershell
# Crear entorno con uv (mas rapido que pip)
uv venv
.venv\Scripts\activate

# Instalar dependencias
uv pip install -e ".[dev]"

# 🔬 INVESTIGAR: ?Sigue siendo ruff el mejor linter?
# ?Hay herramientas mejores que pytest para testing?
```

### 4. Configuracion

```powershell
# Copiar .env y configurar
cp .env.example .env
# Editar .env con tus API keys (ZENFREE_API_KEY, etc.)

# Verificar config
python -c "from pathlib import Path; print('✅ Path OK')"
python -c "import harness; print(f'✅ Harness v{harness.__version__}')"
```

### 5. Verificar Instalacion

```powershell
# 🔬 RESEARCH FIRST: Antes de ejecutar tests, investiga
# ?Sigue siendo pytest la mejor opcion?
# Buscar: "pytest alternatives 2026", "python testing tools 2026"

# Ejecutar tests
uv run python -m pytest harness/tests/ -x -q

# Health check
uv run python -c "
from harness.orchestrator.health import HealthChecker
hc = HealthChecker()
print(hc.check_liveness())
"
```

### 6. Opcion A — SSOT Global OpenCode + Mirror Local (NUEVO)

Swarmind centraliza su cerebro (agents/skills/core) en `~/.config/opencode/`
(**SSOT global**) y mantiene un **mirror local** completo en cada proyecto de
DEV-SPACE para que sigan abiertos a otros editores.

```powershell
# 1. Instalar el hook pre-commit (QA rapido + sync global automatico en cada commit)
uv run python harness/scripts/install_hooks.py --install

# 2. Sincronizar el cerebro al global opencode (~/.config/opencode/)
uv run python scripts/sync_opencode_global.py

# 3. Desplegar mirror local + 31 skills + config propia a todos los proyectos
uv run python scripts/deploy_all.py --dry-run    # Ver que va a hacer
uv run python scripts/deploy_all.py              # Ejecutar deploy completo
```

> **Reinicia opencode** despues del primer sync (la config se carga al inicio).
> Guia completa: [docs/src/es/guide/opcion-a-ssot-global.md](docs/src/es/guide/opcion-a-ssot-global.md)

### 7. Investigar Mejoras (Research First Loop)

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
├── harness/               # Motor de orquestacion Python
│   ├── orchestrator/      # Planificador, health, telemetria, self-healing
│   ├── memory_rag/        # Memoria vectorial LanceDB + Token Economics
│   ├── evolve_loop/       # Auto-mejora ASI-Evolve
│   ├── model_router/      # Routing local/cloud
│   ├── tools_sandbox/     # MCP tools
│   ├── tests/             # 3674 tests
│   ├── scripts/           # install_hooks.py (pre-commit), end_of_iteration, ...
│   └── qa/                # security_policy.py (scanner ADR-0035)
├── scripts/               # sync_opencode_global.py (sync global SSOT)
├── docs/                  # ADRs (0001-0035) + guias + manuales
├── SETUP.md               # Este archivo
└── .opencode/  → ~/.config/opencode/  (SSOT global, sync en cada commit)
```

> **Opcion A**: `.opencode/` de Swarmind es la fuente; se sincroniza al global
> `~/.config/opencode/` en cada commit y se propaga como mirror local a todos
> los proyectos de DEV-SPACE. Ver
> [docs/src/es/guide/opcion-a-ssot-global.md](docs/src/es/guide/opcion-a-ssot-global.md).

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

- `docs/src/adr/` — Architecture Decision Records (0001-0010)
- `.opencode/core/base_principles.md` — 9 categorias universales
- `.opencode/core/fde_principles.md` — Forward Deployment Engineering
- `harness/common.py` — SSOT: embedding, tokens, compression
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
