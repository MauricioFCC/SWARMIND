# Opcion A — SSOT Global OpenCode + Mirror Local por Proyecto

> **Estado**: Implementado (commit `f08c672`)
> **ADR relacionados**: [ADR-0035 — Politica de Paths Portables](adr/adr0035-security-policy-portable-paths-2026.md)

## 1. Que es la Opcion A

Swarmind es el **repositorio central del framework**. Su cerebro (`.opencode/`
con agents, skills, core y skills_registry) se distribuye a otros proyectos de
DEV-SPACE mediante un esquema **SSOT (Single Source of Truth)**:

```
~/.config/opencode/          ← CONFIG GLOBAL opencode (SSOT del cerebro)
  ├── agents/                ← 20 agentes (40 archivos con .min.md)
  ├── skills/                ← 31 skills contextuales
  ├── core/                  ← 13 modulos core (registry, base_principles, ...)
  └── skills_registry.yaml   ← Registro completo de skills

C:\Users\<user>\Documents\DEV-SPACE\<proyecto>\
  ├── .opencode/             ← MIRROR LOCAL (cerebro + config propia)
  └── README.md              ← Generado con tipo, skills y config
```

El **pre-commit hook** de SWARMIND sincroniza el cerebro al global en **cada
commit** (best-effort, no bloquea). El script `deploy_all.py` (local, no
versionado) actualiza el mirror de todos los proyectos bajo demanda.

> **Estándar v2.5**: el motor (`harness/`) ya NO se copia a los proyectos.
> Vive una sola vez en `~/.config/opencode/harness`. Si un proyecto necesita
> el motor Python, importa desde el global via PYTHONPATH.

## 2. Por que existe

- **Un solo lugar donde editar** agents/skills/core (SWARMIND `.opencode/`).
- **Proyectos abiertos a otros editores**: Cursor, VS Code, Claude Code, etc.
  leen el mirror local — no dependen del global.
- **El harness Python** (`harness/run.py`, `agent_discovery.py`, `delegate.py`,
  `run_commands.py`, `compile_agents.py`, `compile_skills.py`) lee
  `.opencode/agents` y `.opencode/skills` del proyecto en runtime → el mirror
  local de `.opencode/` es **obligatorio**.
- **Portabilidad (ADR-0035)**: todas las rutas via `Path.home()` o env vars
  (`DEV_SPACE_ROOT`, `MEMORY_ROOT`, `OPENCODE_GLOBAL_DIR`). Nunca `$HOME`
  literal ni rutas personales hardcodeadas.

## 3. Arquitectura de sincronizacion

| Componente | Archivo | Alcance | Trigger |
|------------|---------|---------|---------|
| Sync global | `scripts/sync_opencode_global.py` | SWARMIND `.opencode/` → `~/.config/opencode/` | Pre-commit hook + manual |
| Deploy proyectos | `scripts/deploy_all.py` | SWARMIND → cada proyecto DEV-SPACE (mirror) | Manual (`python scripts/deploy_all.py`) |
| Hook pre-commit | `harness/scripts/install_hooks.py` | QA rapido + sync global | Cada `git commit` |

### Sync global (`sync_opencode_global.py`)

Copia `agents/`, `skills/`, `core/` y `skills_registry.yaml` desde
`SWARMIND/.opencode/` hacia `~/.config/opencode/`. Es **idempotente** y
**best-effort**: si falla, el commit continua (se avisa por stdout).

```bash
uv run python scripts/sync_opencode_global.py          # Sync normal
uv run python scripts/sync_opencode_global.py --quiet  # Modo silencioso (hook)
```

### Deploy a proyectos (`deploy_all.py`)

Actualiza el mirror de todos los proyectos de DEV-SPACE. **Estándar v2.5**:
los proyectos reciben solo `.opencode/` (125 archivos) + las **31 skills** +
`skills_registry.yaml`. El motor (`harness/`) **NO se copia** — vive una sola
vez en opencode global (elimina ~5.3 GB de duplicación). **Preserva siempre
la config propia** del proyecto:

- `.opencode/config/project_config.yaml`
- `.opencode/config/routing_rules.yaml`
- `.opencode/config/token_budgets.yaml`
- `.env`, `.env.example`
- `.opencode/federated/`, `.opencode/agents/auto`, `.opencode/skills/auto`
- `.opencode/memory/`, `.opencode/db/`

```bash
uv run python scripts/deploy_all.py                    # Deploy completo
uv run python scripts/deploy_all.py --dry-run          # Simular sin escribir
uv run python scripts/deploy_all.py --project CQE      # Solo un proyecto (alias o nombre)
uv run python scripts/deploy_all.py --sync-global      # Solo sync del global opencode
uv run python scripts/deploy_all.py --sync-harness-global  # Solo sync harness -> global
```

### Alias de proyectos

| Alias | Carpeta real | Tipo |
|-------|--------------|------|
| `CQE` | `core-quant-engine` | trading |
| `HC` | `Historia Clinica` | healthtech |
| `ONYX` | `Onyx-Quan-AIBot` | trading |
| `PDV` | `PDV Basic` | retail |
| `HERMES` | `Hermes_Memory_Proyects` | memoria por proyecto (deprecated, ver central) |
| `ALFA` | `de_0_a_Alfa` | general |
| `SECURITY` | `sugurityOs` | security |

> **Memoria central (v3.x)**: la memoria ahora vive UNA vez en
> `<Documents>/Memory_Proyects` (portable via `MEMORY_ROOT`). Ver
> [ADR-0038](../adr/adr0038-memoria-central-backup-2026.md) y
> `scripts/setup_memory_central.py`.

### Hermes Memory (caso especial)

`Hermes_Memory_Proyects` es la **memoria central compartida** entre proyectos.
El deploy **nunca toca** sus 13 directorios de memoria: `knowledge`,
`syntheses`, `99_Hermes_Brain`, `personal`, `sessions`, `projects`, `inbox`,
`templates`, `infra`, `quality`, `core`, `scripts`, `memory_rag`. Solo se
actualizan `.opencode/`, `harness/` y el README.

## 4. Como implementar en una maquina nueva

### 4.1 Clonar Swarmind

```powershell
git clone https://github.com/MauricioFCC/SWARMIND.git Swarmind
cd Swarmind
uv sync
```

### 4.2 Instalar el hook pre-commit (QA + sync global automatico)

```powershell
uv run python harness/scripts/install_hooks.py --install
```

Esto instala `.git/hooks/pre-commit` (portable, sh). En cada commit ejecuta:

1. QA rapido: `harness/scripts/end_of_iteration.py --pre-commit --quick`
2. Sync global: `scripts/sync_opencode_global.py --quiet` (best-effort)

### 4.3 Configurar el global opencode (SSOT)

```powershell
# El global se crea/sincroniza automaticamente en el primer commit.
# Para forzarlo manualmente:
uv run python scripts/sync_opencode_global.py
```

Resultado esperado en `~/.config/opencode/`:

```
agents/ (40 archivos) · skills/ (63 archivos) · core/ (13 archivos) · skills_registry.yaml
```

> **Importante**: opencode carga la config al inicio (no hay hot-reload).
> Reinicia opencode despues del primer sync para que tome los cambios.

### 4.4 Desplegar a proyectos de DEV-SPACE

```powershell
uv run python scripts/deploy_all.py --dry-run   # Ver que va a hacer
uv run python scripts/deploy_all.py             # Ejecutar deploy completo
```

### 4.5 Verificar

```powershell
# 1. Scanner de seguridad (ADR-0035): 0 violaciones
uv run python harness/qa/security_policy.py

# 2. Tests: 3674 passed
uv run python -m pytest harness/tests/ -q

# 3. Bandit (produccion): 0 hallazgos
uv run bandit -r harness/ -x harness/tests -ll -q

# 4. Global sincronizado
uv run python scripts/sync_opencode_global.py
```

## 5. Configuracion por entorno (env vars)

| Variable | Default | Uso |
|----------|---------|-----|
| `DEV_SPACE_ROOT` | `<home>/Documents/DEV-SPACE` | Raiz de proyectos |
| `HERMES_ROOT` | `<home>/Documents/DEV-SPACE/Hermes_Memory_Proyects` | Memoria central |
| `OPENCODE_GLOBAL_DIR` | `<home>/.config/opencode` | SSOT global opencode |

Todas las rutas usan `Path.home()` con override por env var — portables entre
maquinas y usuarios (ADR-0035).

## 6. Flujo de trabajo diario

1. **Editar el cerebro** en SWARMIND (`.opencode/agents/`, `.opencode/skills/`,
   `.opencode/core/`).
2. **Commit** → el hook corre QA rapido + sync global.
3. **Opcional**: `uv run python scripts/deploy_all.py` para propagar a todos
   los proyectos de DEV-SPACE.
4. Los proyectos quedan **abiertos** (mirror local + config propia intacta) para
   cualquier editor.

## 7. Seguridad

- **Nunca** versionar `.env` (esta en `.gitignore`).
- **Nunca** hardcodear rutas personales en codigo o docs (scanner ADR-0035 lo
  bloquea en CI y pre-commit).
- **Nunca** escribir `$HOME` literal en Python: usar `Path.home()`.
- Los scripts de propagacion (`deploy_all.py` y similares) estan en
  `.gitignore` porque contienen la estructura del workspace del autor — se
  documentan aqui pero no se publican.
