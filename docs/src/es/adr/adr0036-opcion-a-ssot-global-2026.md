# ADR-0036 — Opción A: SSOT Global OpenCode + Mirror Local por Proyecto

- **Estado**: ACEPTADO
- **Fecha**: 2026-08-01
- **Decisores**: Coordinador Swiss Watch, Builder, Guardian
- **Categoría**: Infraestructura / Distribución

## Contexto

Swarmind es el **repositorio central del framework** multi-agente: su cerebro
(`.opencode/` con agents, skills, core y skills_registry) debe estar disponible
en TODOS los proyectos de DEV-SPACE para que el harness Python y los editores
(OpenCode, Cursor, VS Code, Claude Code) funcionen con la misma potencia total.

El modelo anterior distribuía copias manuales e inconsistentes: cada proyecto
tenía versiones distintas de agents/skills, skills obsoletas (`software-engineer`,
`data-architect`, ...) sin limpiar, y no existía un flujo automático de
propagación. Editar el cerebro requería re-copiar a mano en cada destino.

Además, la configuración global de OpenCode (`~/.config/opencode/`) no estaba
sincronizada con el cerebro del repo, por lo que la experiencia fuera de
SWARMIND era degradada (menos agents/skills).

## Decisión

Implementar la **Opción A**: SSOT global + mirror local por proyecto.

### 1. SSOT global en `~/.config/opencode/`

El cerebro del framework vive **una vez** en la config global de OpenCode:

```
~/.config/opencode/
├── agents/              ← 20 agentes (40 archivos con .min.md)
├── skills/              ← 31 skills (63 archivos SKILL.md + SKILL.min.md)
├── core/                ← 13 modulos core
└── skills_registry.yaml ← Registro completo
```

Nuevo script `scripts/sync_opencode_global.py`: copia `agents/`, `skills/`,
`core/` y `skills_registry.yaml` desde `SWARMIND/.opencode/` al global.
**Idempotente** y **best-effort** (si falla, no bloquea).

### 2. Sync automático en cada commit (pre-commit hook)

El hook `harness/scripts/install_hooks.py` (portable, sh) se extendió para
ejecutar, tras el QA rápido, el sync global de forma **no bloqueante**:

```
1) harness/scripts/end_of_iteration.py --pre-commit --quick   (QA rápido)
2) scripts/sync_opencode_global.py --quiet                     (sync global, best-effort)
```

Así, **cada commit de SWARMIND** propaga el cerebro al global sin fricción.

### 3. Mirror local completo por proyecto (proyecto abierto)

Cada proyecto de DEV-SPACE conserva un **mirror local completo** (NO se borra
el cerebro local) porque el harness Python lo lee en runtime:

- `harness/run.py`, `agent_discovery.py`, `delegate.py`, `run_commands.py`,
  `compile_agents.py`, `compile_skills.py` leen `.opencode/agents/` y
  `.opencode/skills/` del proyecto.
- Otros editores (Cursor, VS Code, Claude Code) leen el mirror local.

El script `scripts/deploy_all.py` (local, en `.gitignore`) despliega:

- `.opencode/` (125 archivos) + `harness/` (8451 archivos)
- Las **31 skills** (potencia total) + `skills_registry.yaml`
- Limpieza de skills obsoletas (`data-architect`, `documentation-specialist`,
  `quality-gate`, `software-engineer`)
- README.md regenerado por proyecto

### 4. Preservación de la configuración propia del proyecto

El deploy **nunca sobrescribe** la config específica del proyecto:

- `.opencode/config/{project_config,routing_rules,token_budgets}.yaml`
- `.env`, `.env.example`
- `.opencode/federated/`, `.opencode/agents/auto`, `.opencode/skills/auto`
- `.opencode/memory/`, `.opencode/db/`, `harness/db/`

### 5. Hermes Memory (caso especial)

`Hermes_Memory_Proyects` es la memoria central compartida. El deploy solo
actualiza `.opencode/`, `harness/` y README — **nunca** los 13 directorios de
memoria (`knowledge`, `syntheses`, `99_Hermes_Brain`, `personal`, `sessions`,
`projects`, `inbox`, `templates`, `infra`, `quality`, `core`, `scripts`,
`memory_rag`).

### 6. Portabilidad (ADR-0035)

Todas las rutas usan `Path.home()` con override por env vars:

| Variable | Default |
|----------|---------|
| `DEV_SPACE_ROOT` | `<home>/Documents/DEV-SPACE` |
| `HERMES_ROOT` | `<home>/Documents/DEV-SPACE/Hermes_Memory_Proyects` |
| `OPENCODE_GLOBAL_DIR` | `<home>/.config/opencode` |

Nunca `$HOME` literal ni rutas personales (verificado por ADR-0035 scanner).

## Consecuencias

### Positivas
- **Un solo lugar para editar** el cerebro (SWARMIND `.opencode/`).
- **Sync automático** en cada commit — sin pasos manuales.
- **Proyectos abiertos**: mirror local completo + config propia intacta.
- **Potencia total**: 31 skills + 20 agents + registry en todos los proyectos.
- **Portable** entre máquinas y usuarios (env vars + `Path.home()`).

### Negativas
- `deploy_all.py` contiene la estructura del workspace del autor → se mantiene
  en `.gitignore` (documentado en la guía, no publicado).
- Reiniciar OpenCode tras el primer sync (config se carga al inicio).
- Los mirrors locales duplican archivos (espacio en disco).

### Riesgos y mitigaciones
- **Hook roto** (sh portable): probado con `uv`, fallback a `python3`/`python`.
- **Deploy interrumpido**: backup previo de config propia antes de sincronizar.
- **Overwrite accidental**: la config propia se respalda y restaura en el
  mismo deploy.

## Alternativas consideradas

1. **Solo global, sin mirror local** (borrar `.opencode/` del proyecto):
   rechazado — el harness Python y otros editores leen el mirror en runtime,
   el proyecto dejaría de funcionar.
2. **Solo mirror, sin global** (modelo anterior): rechazado — copias
   inconsistentes, sin sync automático, experiencia degradada fuera de SWARMIND.
3. **Symlinks del global al proyecto**: rechazado — Windows y otros editores
   no resuelven bien symlinks; el mirror real es más robusto.

## Verificación

```bash
# 1. Sync global (idempotente)
uv run python scripts/sync_opencode_global.py
# → agents 42 · skills 63 · core 13 · skills_registry.yaml

# 2. Deploy simulado
uv run python scripts/deploy_all.py --dry-run
# → 7 proyectos + Hermes, 31 skills cada uno

# 3. Scanner de seguridad (ADR-0035)
uv run python harness/qa/security_policy.py
# → 0 violaciones

# 4. Tests
uv run python -m pytest harness/tests/ -q
# → 3674 passed
```

## Referencias

- ADR-0035 (Política de Seguridad: Paths Portables + Detección de Secretos)
- Guía: [docs/src/es/guide/opcion-a-ssot-global.md](../guide/opcion-a-ssot-global.md)
- `scripts/sync_opencode_global.py`
- `harness/scripts/install_hooks.py`
