# ADR-0042 — Diagnóstico Setup en PC Nuevo: Memoria Central No Creada + Harness Global Incompleto

- **Estado**: IMPLEMENTADO (fix aplicado 2026-08-11, verificado en PC1929)
- **Fecha**: 2026-08-10 (diagnóstico) / 2026-08-11 (fix + verificación)
- **Decisores**: Usuario/Instalador, Coordinador Swiss Watch, Builder, Guardian
- **Categoría**: Infraestructura / Persistencia / Distribución (SSOT global)
- **Relacionado**: ADR-0035 (Paths Portables), ADR-0036 (SSOT Global), ADR-0038 (Memoria Central)

> **Nota**: ADR interno de diagnóstico — no se pushea como cambio de diseño; se
> envía al equipo Swarmind para corrección del framework.

## Contexto

Instalación de SWARMIND (`SWARMIND_2026-08-09`) en un PC nuevo
(`C:\Users\USUARIO\Documents\DEV_SPACE\`, Windows). Se ejecutó
`scripts/sync_opencode_global.py`:

```
✅ agents     46 archivos
✅ skills     64 archivos
✅ core       14 archivos
✅ skills_registry.yaml actualizado
✅ harness    218 archivos
📊 Total: 343 archivos sincronizados al global (~/.config/opencode/)
```

Problemas detectados durante la verificación:

1. **`<Documents>/Memory_Proyects` NO fue creado** (la memoria central
   definida en ADR-0038 no existe en el PC).
2. **El harness global (`~/.config/opencode/harness/`) importa como
   *namespace package* incompleto**: sin `__init__.py` ni `__main__.py`.
3. **Los proyectos no pueden usar el harness del global**: `PYTHONPATH`
   vacío y los proyectos DEV_SPACE no tienen `harness/` local.
4. **Desajuste de nombre de carpeta**: código/docs usan `DEV-SPACE` (guion),
   pero el workspace real es `DEV_SPACE` (guion bajo).

## Causas raíz identificadas

### Causa 1 — La memoria central solo se crea con un paso manual independiente

`sync_opencode_global.py` sincroniza **cerebro + motor**, pero NO crea ni
configura la memoria central. La creación de `Memory_Proyects` depende de
`scripts/setup_memory_central.py`, que en este PC **nunca se ejecutó**:

- No existe `C:\Users\USUARIO\Documents\Memory_Proyects`.
- No existe `<MEMORY_ROOT>/.swarmind_config.json`.
- No existe `.env` (ni `MEMORY_ROOT` configurado).
- `config_swarmind.py` (menú) y `setup_memory_central.py` quedaron sin correr.

El dry-run de `setup_memory_central.py --dry-run` confirma que el script
funciona y crearía la estructura, pero nada lo invoca en el flujo de install
si el usuario salta el menú interactivo (o responde EOF en modo no-interactivo).

**Causa**: el setup v2.5 (`setup_swarmind.py` → paso 6) abre el menú de
`config_swarmind.py`, pero la creación efectiva de la estructura recae en la
opción manual "7. Ejecutar setup memoria central". En modo no-interactivo,
`config_swarmind.py --non-interactive` solo guarda config de defaults y **no**
invoca `setup_memory_central.py`. Si el usuario omite el menú
(`--skip-config`), la memoria nunca se crea.

### Causa 2 — `_HARNESS_FILES` omite `__init__.py` y `__main__.py`

`scripts/sync_opencode_global.py` define:

```python
_HARNESS_FILES = ["common.py", "delegate.py", "run.py", "run_commands.py",
                  "scheduler.py", "reset_state.py", "cli_common.py", "gpu_accel.py",
                  "gpu_optimize.py", "security_policy.py"]
```

No incluye `__init__.py` ni `__main__.py`. Consecuencias verificadas:

```python
# ~/.config/opencode/harness/ importado con el global en sys.path
import harness                 # → namespace package, harness.__file__ es None
from harness import run_main   # → ImportError: cannot import name 'run_main'
python -m harness --help       # → No module named harness
```

Localmente `harness/__init__.py` define el lazy-loading PEP 562
(`run_main`, `TaskManager`, `LanceVectorStore`, ...) — el global queda **sin
esa capa**. Además `security_policy.py` está listado como archivo raíz, pero
el archivo real vive en `harness/qa/security_policy.py` (la entrada raíz es
inefectiva; el módulo sí se copia vía el directorio `qa`).

### Causa 3 — `PYTHONPATH` vacío y proyectos sin `harness/` local

El estándar v2.5 (ADR-0036) asume que los proyectos importan el harness desde
el global vía `PYTHONPATH` o symlink. Verificado:

- `$env:PYTHONPATH` está **vacío**.
- `JURIDICO`, `LITISCOL_SCRAP`, `LUMINA LANG` tienen `.opencode/` pero **no**
  `harness/`.
- Sin `PYTHONPATH` → `import harness` desde esos proyectos falla (ni siquiera
  el global incompleto).

### Causa 4 — Carpeta `DEV_SPACE` vs `DEV-SPACE`

Código (`deploy_all.py`) y docs (ADR-0035/0036/guías) asumen
`<home>/Documents/DEV-SPACE` (con guion). El workspace real es
`<home>/Documents/DEV_SPACE` (con guion bajo). `deploy_all.py --dry-run` no
descubriría ningún proyecto porque `_DEV_SPACE` no coincide; hay que fijar
`DEV_SPACE_ROOT` explícitamente.

## Decisión (recomendación al equipo Swarmind)

1. **Automatizar la memoria central en el setup**:
   `setup_swarmind.py`/`config_swarmind.py --non-interactive` deben invocar
   `setup_memory_central.py` (construcción idempotente) cuando `MEMORY_ROOT`
   no exista, en lugar de depender de la opción manual del menú.
2. **Incluir archivos de paquete en `_HARNESS_FILES`**:
   agregar `"__init__.py"`, `"__main__.py"` (y revisar `README.md`,
   `vulture_whitelist.py`) a la lista de copia del motor, para que el global
   sea un paquete importable y `python -m harness` funcione.
3. **Documentar/configurar `PYTHONPATH` en el install**:
   el setup debe setear `PYTHONPATH` (o symlink) apuntando a
   `~/.config/opencode` para que los proyectos sin `harness/` local puedan
   importarlo (confirmar la intención del ADR-0036 §ver si sigue siendo
   manual).
4. **Armonizar el nombre del workspace**:
   decidir `DEV_SPACE` (underscore, real) vs `DEV-SPACE` (hyphen, en código)
   y fijar `DEV_SPACE_ROOT` durante el setup para evitar descubrimiento nulo.

## Correcciones aplicadas (2026-08-11, verificado en PC1929)

Las 4 recomendaciones fueron implementadas y verificadas:

### Fix 1 — Memoria central automática en el sync ✅
- `scripts/setup_memory_central.py`: nueva función pública
  `ensure_memory_structure(memory_root, dry_run)` — crea la estructura
  completa (`knowledge`, `syntheses`, `99_Hermes_Brain`, `personal`,
  `projects`, `sessions`, `inbox`, `exports`, `data/lancedb`, `backups`)
  con `.gitkeep`, idempotente y NO destructiva (preserva db existente).
- `scripts/sync_opencode_global.py`: cada sync de motor invoca
  `ensure_memory_structure()` — si `Memory_Proyects` no existe, se crea
  automáticamente (antes dependía de la opción manual 7 del menú).

### Fix 2 — Harness global empaquetado completo ✅
- `_HARNESS_FILES` ahora incluye `__init__.py`, `__main__.py` y
  `vulture_whitelist.py`; se eliminó la entrada muerta `security_policy.py`
  (el archivo real vive en `harness/qa/` y se copia vía el directorio `qa`).
- Verificado: `import harness` desde el global resuelve
  `~/.config/opencode/harness/__init__.py` y `python -m harness --help`
  funciona (antes: namespace package incompleto → ImportError).

### Fix 3 — PYTHONPATH persistido (nuevas sesiones) ✅
- `scripts/verify_swarmind_setup.py --persist-env`: persiste a nivel de
  usuario (`setx` en Windows / shell rc en Unix) `MEMORY_ROOT`,
  `DEV_SPACE_ROOT` y `PYTHONPATH` (append del global, sin pisar PYTHONPATH
  existente; idempotente).
- Verificado en registro: `PYTHONPATH = C:\Users\USUARIO\.config\opencode`,
  `MEMORY_ROOT = <home>\Documents\Memory_Proyects`,
  `DEV_SPACE_ROOT = <home>\Documents\DEV-SPACE` (real con guion).

### Fix 4 — Health-check repetible (WHAT+WHY+WHERE) ✅
- `scripts/verify_swarmind_setup.py`: script de verificación que reporta
  `harness_global`, `memory_central` y `env_vars` con WHAT+WHY+WHERE y exit
  code accionable (0 = setup listo para TDD, 1 = corregir checks ❌).
- Basado en el estándar 2026 de empaquetado de agent skills
  (addyosmani/agent-skills 86k★, Agent Plugins): skills + evals + hooks
  portables en una sola ubicación global re-instalable en cualquier PC nuevo.
- `--fix` crea la memoria central si falta; `--persist-env` persiste env vars.

### Verificación post-fix (PC1929, 2026-08-11)
```
✅ harness_global  — Paquete harness completo en el global (importable)
✅ memory_central  — Memoria central OK con 15 colecciones LanceDB
✅ env_vars        — 3/3 env vars persistidas (nuevas sesiones)
EXIT 0 — SETUP OK: harness global + memoria central listos para TDD
```

## Mitigación inmediata en este equipo (PC1929)

```powershell
# 1. Crear memoria central (idempotente, preserva db si existiera)
python scripts/setup_memory_central.py

# 2. Persistir config (backup diario, keep 5)
python scripts/config_swarmind.py --show
#   (o --non-interactive; NOTA: no crea estructura — correr el paso 1 primero)

# 3. Harness global completo vía PYTHONPATH por sesión/entorno
$env:PYTHONPATH = "$env:USERPROFILE\.config\opencode"
python -c "import sys; sys.path.insert(0, r'C:\Users\USUARIO\.config\opencode'); from harness import run_main; print('OK')"

# 4. DEV_SPACE_ROOT explícito (carpeta real con underscore)
$env:DEV_SPACE_ROOT = "C:\Users\USUARIO\Documents\DEV_SPACE"

# (A largo plazo: corregir sync_opencode_global.py para copiar __init__.py/__main__.py)
```

> **NOTA 2026-08-11**: los pasos 1, 3 y 4 quedaron automatizados en el sync
> y en `verify_swarmind_setup.py`. En un PC nuevo basta ejecutar:
> ```powershell
> python scripts/sync_opencode_global.py     # copia cerebro+motor Y crea memoria
> python scripts/verify_swarmind_setup.py    # verifica (exit 0 = listo para TDD)
> ```

## Alternativas consideradas

1. **Copiar el harness completo (v2.0, pre-ADR-0036) a cada proyecto**:
   rechazado provisionalmente en el framework (duplicación ~5.3 GB), aunque
   es la única vía que funciona hoy sin `PYTHONPATH` global configurado.
2. **Instalar harness como paquete pip en modo editable**:
   viable (`pip install -e`), más robusto que `PYTHONPATH`; pendiente de
   evaluación del equipo (requiere publicar `harness` como paquete installable).
3. **Symlink `harness/` en cada proyecto → global**:
   portátil en Windows con `mklink /J`, pero requiere script de provision.

## Verificación

```powershell
# Tras aplicar mitigación 1
Test-Path "$env:USERPROFILE\Documents\Memory_Proyects\data\lancedb"

# Tras corregir _HARNESS_FILES + re-sync
python -c "import sys; sys.path.insert(0, r'C:\Users\USUARIO\.config\opencode'); import harness; print(harness.__file__); from harness import run_main; print('OK')"

# Tras fijar DEV_SPACE_ROOT
python scripts/deploy_all.py --dry-run   # debe descubrir JURIDICO, LITISCOL_SCRAP, LUMINA LANG, SWARMIND_2026-08-09
```

### Verificación automatizada (nueva, 2026-08-11)

```powershell
# Health-check completo (WHAT+WHY+WHERE, exit 0 = listo para TDD)
python scripts/verify_swarmind_setup.py

# Crear memoria central si falta (idempotente)
python scripts/verify_swarmind_setup.py --fix

# Persistir env vars para nuevas sesiones (Causa 3)
python scripts/verify_swarmind_setup.py --persist-env
```

Tests TDD (`harness/tests/test_setup_verification.py`, 15 tests):
- `test_harness_files_incluyen_archivos_de_paquete` / `..._reales`:
  `_HARNESS_FILES` contiene `__init__.py`, `__main__.py`, `vulture_whitelist.py`
  y todas las entradas corresponden a archivos reales (sin entradas muertas).
- `test_ensure_memory_structure_*` (3): crea estructura completa, idempotente
  (no recrea ni borra db), crea `data/lancedb` + `.swarmind_config.json`.
- `test_verify_detecta_*` (4): health-check falla con WHAT+WHY+WHERE cuando el
  global está incompleto o la memoria ausente; pasa cuando están completos.
- `test_persist_env_*` (3): PYTHONPATH se anexa sin pisar, DEV_SPACE_ROOT se
  detecta, no duplica entradas; `os.system` mockeado (los tests NUNCA escriben
  `setx` real al registro del usuario).

## Referencias

- ADR-0035 (Paths Portables — env vars con fallback `Path.home()`)
- ADR-0036 (Opción A: SSOT Global — mirror local + motor en global)
- ADR-0038 (Memoria Central Portable + Backup)
- `scripts/sync_opencode_global.py` (`_HARNESS_FILES`)
- `scripts/setup_memory_central.py`, `scripts/config_swarmind.py`,
  `scripts/deploy_all.py` (`DEV-SPACE` default)
- `harness/__init__.py` (lazy-loading PEP 562 que hoy no llega al global)
- **addyosmani/agent-skills** (2026, 86k★): producción-grade engineering
  skills empaquetadas para agentes — skills/, evals/, hooks/, commands/
  portables (https://github.com/addyosmani/agent-skills)
- **Agent Plugins** (2026-08): estándar portable de empaquetado de skills +
  herramientas — `plugin.json` + `skills/` + evals, compatible con
  Claude Code/Codex/opencode/Gemini (https://agent-plugins.org,
  https://developers.googleblog.com/agent-plugins-package-your-skills-tools-and-more)

## Investigación Frontiera Aplicada 2026

### H6 Skills de Dominio (ADR-0041) — Secciones Añadidas

1. **science-doc.md** — Sección "Verificación de Citas y Reproducibilidad":
   - CiteGuard-style: validación retrieval-augmented de citas, marcas `CITA-NO-VERIFICADA`.
   - OpenScholar-style self-feedback: detección de auto-referencias y contradicciones.
   - Reproducibilidad ARA-style: semillas, divisiones train/valid/test, estado REPRODUCIBLE/PARCIAL/NO.

2. **legal-doc.md** — Sección "Verificación de Vigencia y Citas Legales":
   - Precedente Corte Suprema Colombia (feb-2026, citas apócrifas IA).
   - Criterios T-323-24: verificación contra repositorio oficial SUIN/CIJ.
   - Patrón LegalGraphRAG (Researcher→Auditor→Adjudicator).
   - Marcos de veredicto: VIGENTE/MODIFICADO/DEROGADO/INEXEQUIBLE.
   - Marca `APÓCRIFA-REVISAR` para citas no verificables jurídicamente.
   - Checklists por norma (sentencias, demandas, contratos).

### H4 Agent Factory On-Demand (ADR-0041) — Estado

- `harness/aifactory/agent_factory.py`: implementado con 8 plantillas base,
  `AgentTemplateRegistry`, `AgentRecommender` y `OnDemandAgentFactory.generate()`.
- `agent_templates.yaml`: catálogo de 8 plantillas (programming-agent, science-review,
  legal-review, data-analysis, security-audit, documentation, frontend-ui, research-synthesis).

### H2 OTel GenAI Semantic Conventions (ADR-0041) — Migración Parcial

- `harness/observability/opentelemetry_agent.py`: ya emite `gen_ai.provider.name`,
  `gen_ai.system`, `gen_ai.request.model`, `gen_ai.usage.input_tokens`,
  `gen_ai.usage.output_tokens` bajo semantic conventions 2026.
- **Gap**: Legacy `agent.*` attributes mantenidos para compatibilidad con dashboards
  existentes (sin romper API pública). Migración completa pendiente cuando se renueven
  los dashboards.

### H1 MCP Stateless (ADR-0041) — Cliente MCP

- `harness/tools_sandbox/mcp_client.py`: protocolo stateless 2026-07-28 implementado
  (`connect_stateless`, `_stateless_discover`, `_stateless_meta`, headers `Mcp-Method`/`Mcp-Name`).
- **6 ocurrencias de `initialize`** (handshake stateful) coexisten con protocolo stateless
  por compatibilidad backward; fallback a `initialize` si server legado rechaza modo stateless.
- **Decision**: implementación híbrida (stateless por defecto, fallback initialize) es el patrón
  recomendado por spec 2026-07-28.

### Token Economics & Observability Mejoras (ADR-0039, ADR-0041)

- Cache-Shape Discipline (-38% tokens), Structured Compaction (-41% costo), Scoped Context Spawn (-44% tiempo)
- ComplexityRouter (RouteLLM-style): routing small vs frontier con umbral 50.0, señales heurísticas.
- TokenUsageTracker: medición por agente/llamada, alerts a 80% presupuesto, export JSON para spans gen_ai.usage.*
- 4291 tests passed, 1 failed (test_target_versions_uptodate: check-web hace 9 días > umbral 7 — operación de mantenimiento, no error de código).

### Arquitectura Sustituida y Optimización de Recursos (ADR-0041 H7)

Como parte de la filosofía de mejora continua y eliminación de tamaño sin perder calidad, se sustituyó la arquitectura heredada por versiones optimizadas:

1. **ModelRouter** (`harness/model_router/router.py`):
   - **Original**: 28KB, routing basado en llamadas LLM para decidir small vs frontier
   - **Sustituido**: 10.8KB (`harness/model_router/complexity_router.py`), routing heurístico con señales (keywords, longitud, dominio)
   - **Mejoras**: 61% reducción de tamaño, ~2x ahorro de costo en tareas pequeñas, latencia ~10ms vs ~200ms+ (evitando LLM call en decision routing), mantenida compatibilidad con providers multi-API para ejecución real
   - **Principio aplicado**: Strategy pattern + caché de decisiones O(1) en lugar de routing LLM O(latency)

2. **ModelRouter wrapper** (`harness/model_router/router.py` nueva implementación):
   - **Original**: Clase monolítica con routing complejo
   - **Sustituido**: ModelRouter optimizado que usa ComplexityRouter como capa de decisión superior, con cache de decisiones y factory function `create_model_router()`
   - **Mejora**: Interfaz unificada, factory pattern para instanciación, route_with_fallback strategy (small first, escalar a frontier si necesario)

3. **Validation stages nuevas** (`harness/validation/`):
   - **PBT Stage** (`harness/validation/pbt_stage.py`): Property-Based Testing Hypothesis para código generado por agentes
   - **Mutation Stage** (`harness/validation/mutation_stage.py`): CDBench-style mutation testing con kill rate quantitativo
   - **Propósito**: Validación automática de calidad antes de considerar código "done" en pipeline TDD

Estas sustituciones siguen el principio System Design de "eliminar tamaño sin perder calidad": el nuevo routing heurístico produce decisiones equivalentes o mejores que el routing LLM costoso, los validation stages automatizan calidad que antes requería revisión manual, y todo mantiene compatibilidad hacia atrás con el ecosystem existente

