# AGENTIC — Multi-Agent Evolutionary Harness

**Template portable de sistema multi-agente evolutivo con LanceDB, RAG, auto-mejora, enrutamiento híbrido local/cloud, supervisión humana (HITL) y conectividad MCP universal.**

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
│   ├── orchestrator/            # Planificador, delegacion, sandbox, HITL
│   │   ├── agent_bus.py
│   │   ├── agent_dispatcher.py
│   │   ├── scheduler.py
│   │   ├── task_manager.py
│   │   ├── delegation_engine.py
│   │   ├── sandbox_loop.py
│   │   ├── hitl_guard.py        # Human-in-the-Loop
│   │   └── hitl/                # Config HITL
│   ├── memory_rag/              # Memoria vectorial LanceDB
│   │   ├── lance_vector_store.py
│   │   ├── doc_ingester.py
│   │   └── context_assembler.py
│   ├── model_router/            # Enrutamiento hibrido local/cloud
│   │   ├── router.py
│   │   └── router_config.yaml
│   ├── evolve_loop/             # Auto-mejora ASI-Evolve
│   │   ├── self_improver.py
│   │   ├── skill_generator.py
│   │   ├── prompt_evolver.py
│   │   ├── procedural_memory.py
│   │   ├── gepa_mutator.py
│   │   ├── cognition_sync.py
│   │   └── evaluator.py
│   ├── tools_sandbox/           # MCP Client + Executor
│   │   ├── mcp_client.py        # Cliente MCP universal (JSON-RPC 2.0)
│   │   ├── mcp_manager.py       # Pool de conexiones MCP
│   │   ├── mcp_servers.yaml     # Servidores MCP preconfigurados
│   │   └── mcp_executor.py      # Ejecucion sandboxeada de herramientas
│   ├── gateway/                 # Gateways (CLI, Slack, Telegram)
│   │   ├── gateway.py
│   │   └── gateway_config.yaml
│   ├── db/                      # Datos persistentes
│   │   ├── lancedb/             # Base vectorial LanceDB
│   │   ├── import/              # BDs Legacy para migrar
│   │   ├── _archived/           # Colecciones archivadas
│   │   └── migrate_db.py        # Migrador automatico
│   ├── scripts/                 # Utilidades del Harness
│   │   ├── init.py              # Bootstrap del proyecto
│   │   ├── generate_llms_txt.py # Genera /llms.txt para LLMs externos
│   │   └── check_ollama.py      # Health check de Ollama
│   ├── run.py                   # Punto de entrada CLI
│   ├── reset_state.py
│   ├── README.md                # Esta documentacion
│   └── AGENTS.md                # Manifiesto completo de agentes
└── llms.txt                     # Contexto curado para LLMs externos
```

---

## Requisitos

- **Python 3.10+**
- **LanceDB** (se instala automaticamente con `init.py` o manual: `pip install lancedb`)
- **Ollama** (opcional, para modo local) — [https://ollama.com](https://ollama.com)
- Dependencias adicionales: `numpy`, `schedule`, `pyyaml`, `requests`

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

# 4. (Opcional) Verificar Ollama para modo local
python harness/scripts/check_ollama.py

# 5. (Opcional) Forzar modo cloud
python harness/run.py --force-cloud "@software-engineer: implementar API"
```

### Entrada Rápida (Delegate)

El módulo `delegate.py` reduce la fricción de entrada: no necesitas escribir `@rol:` manualmente.

```bash
# Detección automática de rol según la tarea
python harness/delegate.py "implementa una API REST"
# → detecta @software-engineer automáticamente

# Delegación explícita (igual que run.py)
python harness/delegate.py "@software-engineer: crea un endpoint"

# Listar roles disponibles
python harness/delegate.py --list

# Modo chat interactivo
python harness/delegate.py --interactive

# Usando -m harness (entrypoint directo)
python -m harness "implementa API"
```

**También disponible en `run.py`** con el flag `--simplified` / `-s`:

```bash
python harness/run.py -s "implementa una API REST"
# Internamente: detecta rol, envía como @rol: X

python harness/run.py --simplified "migrar base de datos"
# → detecta @data-architect automáticamente
```

**Comportamiento:**
- Si el texto empieza con `@rol:`, se envía directamente a ese rol
- Si NO empieza con `@rol:`, el sistema detecta el mejor rol según la tarea
- Si no puede detectar el rol, pregunta al usuario
- Modo `--interactive`: chat continuo con historial (flechas arriba/abajo)

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
# ─── Delegacion directa ───
python harness/run.py "@software-engineer: Implementa <tu-tarea>"

# ─── Entrada simplificada (Delegate) ───
python harness/delegate.py "implementa una API REST"                    # Detecta rol automaticamente
python harness/delegate.py "@swe: crea un endpoint"                    # Delegacion explicita con alias
python harness/delegate.py --list                                      # Lista roles disponibles
python harness/delegate.py --interactive                                # Modo chat interactivo
python harness/run.py -s "implementa una API REST"                      # Simplified flag en run.py

# ─── Flags de enrutamiento ───
python harness/run.py --force-cloud "@software-engineer: crear API"     # Override: siempre cloud
python harness/run.py --auto-pilot "@data-architect: migrar DB"        # Desactiva HITL
python harness/run.py --hitl-sensitive "@devops-sre: deploy"           # HITL solo critico

# ─── Scheduler ───
python harness/run.py --daemon                                          # Iniciar en background
python harness/run.py '!schedule add daily-check --cron "0 9 * * 1-5" --task "@quality-gate: validar sistema"'
python harness/run.py '!schedule list'

# ─── Gateway interactivo ───
python harness/run.py --gateway cli

# ─── Evolucion de prompts ───
python harness/run.py '!evolve mutate @software-engineer "<tu-tarea-de-prueba>"'

# ─── Migracion de BD ───
python harness/run.py '!db migrate'                                    # Migrar todas las BDs
python harness/run.py '!db migrate --path <ruta>'                       # Migrar BD especifica
python harness/run.py '!db list-imports'                                # Listar BDs disponibles
python harness/run.py '!db stats'                                       # Estadisticas de BD activa
python harness/run.py '!db rollback <backup>'                           # Restaurar desde backup

# ─── Fin de Iteracion ───
python harness/run.py '!iteration end'                                  # Pipeline completo
python harness/run.py '!iteration end --dry-run'                        # Simulacion
python harness/run.py '!iteration end --skip-bugs'                      # Salta bug hunting
python harness/run.py '!iteration end --skip-sec'                       # Salta security
python harness/run.py '!iteration end --skip-docs'                      # Salta docs
python harness/run.py '!iteration report'                               # Ultimo reporte
python harness/scripts/end_of_iteration.py                              # Directo (sin run.py)
python harness/scripts/end_of_iteration.py --dry-run                    # Directo dry-run
python harness/scripts/end_of_iteration.py --report                     # Directo reporte
python harness/scripts/end_of_iteration.py --pre-commit                 # Modo pre-commit (staged files)
python harness/scripts/end_of_iteration.py --watch                      # Modo watch (fases 1,2,4)

# --- Pre-commit Hook ---
python harness/run.py '!hooks install'                                  # Instala pre-commit hook
python harness/run.py '!hooks uninstall'                                # Desinstala pre-commit hook
python harness/run.py '!hooks status'                                   # Muestra estado del hook

# --- Watch Mode ---
python harness/run.py --watch                                           # Monitorea cambios en tiempo real

# ─── Utilidades ───
python harness/reset_state.py                                           # Resetear estado
python harness/scripts/check_ollama.py                                  # Health check Ollama
```

### Tabla de comandos

| Comando | Descripcion |
|---------|-------------|
| `@rol: mensaje` | Delegacion directa a un agente |
| `--force-cloud` | Override: fuerza todas las tareas a cloud API |
| `--auto-pilot` | Desactiva HITL (solo entornos de confianza) |
| `--hitl-sensitive` | HITL solo para acciones criticas |
| `--daemon` | Inicia scheduler en background |
| `--watch` | Monitorea cambios en `harness/` y `.opencode/` en tiempo real |
| `--gateway <type>` | Modo gateway (cli, slack, telegram) |
| `!db migrate` | Migra BDs desde `harness/db/import/` |
| `!db migrate --path <ruta>` | Migra una BD especifica |
| `!db list-imports` | Lista las BDs disponibles para importar |
| `!db stats` | Muestra estadisticas de la BD activa |
| `!db rollback <backup>` | Restaura desde un backup pre-migracion |
| `-s, --simplified` | Entrada simplificada: detecta rol automaticamente |
| `!evolve mutate @<a> "<t>"` | Muta y evalua prompt de un agente |
| `!schedule add <n> --cron "<c>" --task "<t>"` | Programa job recurrente (cron) |
| `!schedule add <n> --interval "30m" --task "<t>"` | Programa job por intervalo |
| `!schedule list` | Lista jobs programados |
| `!iteration end` | Pipeline fin de iteracion (bugs, security, docs, tokens, commit) |
| `!iteration end --dry-run` | Simulacion del pipeline |
| `!iteration end --skip-bugs` | Salta bug hunting |
| `!iteration end --skip-sec` | Salta security review |
| `!iteration end --skip-docs` | Salta docs update |
| `!iteration report` | Muestra ultimo reporte de iteracion |
| `!hooks install` | Instala pre-commit hook con pipeline automatico |
| `!hooks uninstall` | Desinstala pre-commit hook |
| `!hooks status` | Muestra estado del pre-commit hook |

---

## Workflow de Fin de Iteración

El pipeline `!iteration end` automatiza el cierre de cada ciclo de desarrollo,
ejecutando 5 fases secuenciales sobre los archivos modificados desde el último commit.

### Uso

```bash
# Pipeline completo (bugs → security → docs → tokens → commit)
python harness/run.py '!iteration end'

# Simulación (no modifica nada)
python harness/run.py '!iteration end --dry-run'

# Saltar fases específicas
python harness/run.py '!iteration end --skip-bugs'
python harness/run.py '!iteration end --skip-sec'
python harness/run.py '!iteration end --skip-docs'

# Ver el último reporte guardado
python harness/run.py '!iteration report'
```

O directamente:

```bash
python harness/scripts/end_of_iteration.py
python harness/scripts/end_of_iteration.py --dry-run
python harness/scripts/end_of_iteration.py --skip-bugs
python harness/scripts/end_of_iteration.py --report
```

### Fases del Pipeline

| Fase | Acción | Descripción |
|------|--------|-------------|
| 🔍 Bug Hunting | Escanea `git diff` en busca de bugs comunes | `except: pass`, `print()` en vez de logging, `TODO`/`FIXME`/`HACK`, funciones sin docstring/type hints, archivos >500 líneas |
| 🛡️ Security Review | Revisa seguridad en archivos modificados | API keys/tokens hardcodeados, `eval()`/`exec()`, `shell=True`, HTTP URLs, `os.system()` |
| 📄 Docs Update | Actualiza documentación según cambios | `memory_rag/` → regenera `llms.txt`, `model_router/` u `orchestrator/` → avisa actualizar `README.md`, `.opencode/agents/` → avisa actualizar `AGENTS.md` |
| 💰 Token Report | Reporta consumo estimado de tokens | Líneas diff → tokens (~4 chars/token), ahorro por routing (~65%), ahorro por skills (~60%), costo estimado ($0 si todo local) |
| 📝 Commit Seguro | Prepara commit con mensaje estructurado | Verifica `.env` no en staging, verifica sin secretos en diff, muestra mensaje, pregunta `¿Commit? [Y/n/--edit]` |

### Formato del mensaje de commit

```
<tipo>: <resumen>

- Bug fixes: X corregidos, Y pendientes
- Security: Z hallazgos (0 critical)
- Docs: actualizados [lista]
- Tokens: ~X input / ~Y output
```

**Tipos:** `feat`, `fix`, `refactor`, `docs`, `security`, `chore`, `style`

### Reportes

Cada ejecución guarda un reporte JSON en `harness/db/iteration_reports/`:

```
harness/db/iteration_reports/
├── report_20260613_120000_iter0001.json
├── report_20260613_123000_iter0002.json
└── ...
```

Para ver el último reporte:

```bash
python harness/run.py '!iteration report'
```

### Comandos disponibles

| Comando | Descripción |
|---------|-------------|
| `!iteration end` | Ejecuta pipeline completo |
| `!iteration end --dry-run` | Muestra qué haría sin modificar nada |
| `!iteration end --skip-bugs` | Salta bug hunting |
| `!iteration end --skip-sec` | Salta security review |
| `!iteration end --skip-docs` | Salta docs update |
| `!iteration report` | Muestra el último reporte guardado |

---

## Pre-commit Hook Automático

El pre-commit hook ejecuta el pipeline de fin de iteración **automáticamente en cada commit**,
revisando solo los archivos staged (los que vas a commitear).

### Instalación

```bash
# Instalar hook (crea .git/hooks/pre-commit)
python harness/run.py '!hooks install'

# Verificar estado
python harness/run.py '!hooks status'
```

### ¿Qué hace el hook?

Cuando haces `git commit`, el hook ejecuta 3 fases rápidas (<5 segundos):

| Fase | Acción | ¿Bloquea? |
|------|--------|-----------|
| 🔍 Bug Hunting | Escanea staged files en `harness/` y `.opencode/` | ❌ CRITICAL bugs → aborta commit |
| 🛡️ Security Scan | Busca secrets hardcodeados | ❌ Secrets encontrados → aborta commit |
| 💰 Token Report | Estima tokens input/output | No bloquea |

### Comportamiento

- **Si encuentra CRITICAL bugs o SECRETS**: el commit se aborta con instrucciones para corregir
- **Si encuentra issues menores (MAJOR/MINOR)**: permite el commit con una advertencia
- **Timeout de 5 segundos**: si el hook tarda más, permite el commit y loguea un warning
- **Saltar el hook**: `git commit --no-verify`

### Desinstalación

```bash
python harness/run.py '!hooks uninstall'
```

Restaura el hook original (si existía) o elimina el hook de Agentic.

### Alcance del hook

| Revisa | No revisa |
|--------|-----------|
| `harness/` — todos los .py, .md, .yaml | `harness/db/` — datos persistentes |
| `.opencode/` — agentes, skills, config | `__pycache__/` — caché de Python |
| | `.git/` — metadatos de git |

---

## Watch Mode (Monitoreo en Tiempo Real)

El modo `--watch` monitorea cambios en `harness/` y `.opencode/` y ejecuta
automáticamente el pipeline de calidad cuando detecta modificaciones.

### Uso

```bash
python harness/run.py --watch
```

### Comportamiento

1. Escanea cada 2 segundos usando `os.stat()` para detectar cambios
2. Cuando detecta archivos .py, .md, .yaml modificados:
   - Espera 3 segundos de inactividad (evita ejecutar mientras se sigue escribiendo)
   - Ejecuta `end_of_iteration.py --watch` (solo fases 1, 2, 4)
   - Muestra resumen en consola
   - Vuelve a esperar cambios
3. Presiona `Ctrl+C` para detener

### Ejemplo de salida

```
[Harness] Watch mode activado — monitoreando:
  - C:\proyecto\harness
  - C:\proyecto\.opencode
  Excluyendo: harness/db/, __pycache__/, .git/

  [WATCH] Waiting for changes...

  [2026-06-13 20:00] change detected: harness/run.py
  [2026-06-13 20:00] Running check...
    🔍 Bug hunting: 0 issues
    🛡️ Security scan: 0 issues
    💰 Tokens: ~1,200 input / ~400 output
    Done in 0.34s
  [WATCH] Waiting for changes...
```

### Diferencia con `--daemon`

| Flag | Propósito | Frecuencia |
|------|-----------|------------|
| `--daemon` | Scheduler en background para tareas programadas | Cada 60s (jobs cron) |
| `--watch` | Monitoreo de cambios para development loop | Cada 2s (polling) |

---

## Arquitectura

### Model Router: Enrutamiento Híbrido Local/Nube

El `ModelRouter` decide automaticamente si una tarea se ejecuta localmente (Ollama, gratis) o en cloud (API externa, paga).

**Logica de decision (prioridad):**

1. **Keywords destructivas** → cloud (seguridad): `DROP`, `DELETE`, `rm -rf`, `terraform destroy`, `format C:`, `dd if=`, `kubectl delete --force`
2. **Default del rol** → configurable: roles complejos van a cloud, roles simples van a local
3. **Tarea corta** (< 200 chars) → local (eficiente para consultas simples)
4. **Wildcard `*`** → local (default para roles no listados)

**Tabla de ruteo por defecto:**

| Rol | Destino | Motivo |
|-----|---------|--------|
| @software-engineer | ☁️ cloud | Codigo complejo |
| @enterprise-architect | ☁️ cloud | Documentacion tecnica |
| @quant-developer | ☁️ cloud | Estrategias cuantitativas |
| @ai-engineer | ☁️ cloud | ML/AI pipelines |
| @security-engineer | ☁️ cloud | Hardening, compliance |
| @data-architect | ☁️ cloud | Schemas, migraciones |
| @devops-sre | ☁️ cloud | CI/CD, infraestructura |
| @evolve-researcher | ☁️ cloud | Investigacion |
| @evolve-engineer | ☁️ cloud | Ejecucion de mejoras |
| @context-engineer | 🖥️ local | RAG, curacion contexto |
| @documentation-specialist | 🖥️ local | Documentacion |
| @tool-mcp-engineer | 🖥️ local | Herramientas MCP |
| @quality-gate | 🖥️ local | QA, tests |
| *otros* | 🖥️ local | Default |

**Flags:**
- `--force-cloud`: Override total → todas las tareas a cloud
- Fallback automatico: si local falla → cloud (configurable)

**Health check:**
```bash
python harness/scripts/check_ollama.py
```

---

### MCP: Conexión Universal a Herramientas (Model Context Protocol)

`tools_sandbox` ahora funciona como **cliente MCP universal** que se conecta a servidores MCP comunitarios via JSON-RPC 2.0.

**Componentes:**
- `mcp_client.py` — Cliente MCP individual: connect, list_tools, execute_tool
- `mcp_manager.py` — Pool de conexiones: registra servers, descubre herramientas, ejecuta
- `mcp_servers.yaml` — Configuracion de servidores (todos deshabilitados por defecto)
- `mcp_executor.py` — Ejecutor sandboxeado con timeouts, whitelist, y validacion de schemas

**Servidores preconfigurados:**

| Servidor | URL | Tools | Instalacion |
|----------|-----|-------|-------------|
| filesystem | localhost:3100 | read_file, write_file, list_directory | `npx @modelcontextprotocol/server-filesystem` |
| github | localhost:3101 | get_repo, list_issues, create_pr, search_code | `npx @modelcontextprotocol/server-github` |
| postgres | localhost:3102 | query, list_tables, describe_table | `npx @modelcontextprotocol/server-postgres` |
| memory | localhost:3104 | store_memory, recall_memory, list_memories | `npx @modelcontextprotocol/server-memory` |
| brave_search | localhost:3105 | web_search, web_fetch | `npx @modelcontextprotocol/server-brave-search` |

**Uso:**
```bash
# 1. Instalar un servidor MCP comunitario
npx @modelcontextprotocol/server-filesystem

# 2. Habilitarlo en mcp_servers.yaml
#    (cambiar enabled: false → enabled: true)

# 3. El MCPManager lo conecta automaticamente al iniciar el harness
```

Ver: [https://github.com/modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers)

---

### HITL: Supervisión Humana en Acciones Críticas

El `HITLGuard` (Human-in-the-Loop) intercepta acciones destructivas y requiere aprobacion humana antes de ejecutarlas.

**3 modos de operacion:**

| Modo | Flag | Comportamiento |
|------|------|----------------|
| `hitl` | *(default)* | Pregunta para TODA accion destructiva |
| `auto_pilot` | `--auto-pilot` | Salta todos los chequeos (solo entornos de confianza) |
| `hitl_sensitive` | `--hitl-sensitive` | Solo bloquea acciones de severidad `critical` |

**18 patrones destructivos configurables** en `harness/orchestrator/hitl/hitl_config.yaml`:

| Categoria | Patrones | Severidad |
|-----------|----------|-----------|
| Base de datos | DROP TABLE, DELETE sin WHERE, TRUNCATE, ALTER DROP | critical/high |
| Filesystem | rm -rf, mkfs/format, dd if=, > /dev/ | critical |
| Infraestructura | terraform apply/destroy, kubectl delete --force, docker rm -f | critical/high |
| Git/Deploy | git push --force, npm publish, pip --no-verify | high/medium |
| Sistema | kill -9, > /etc/, sudo | medium/high |

**Timeout fail-safe:** 300 segundos (5 min). Si no respondes, la accion se **deniega automaticamente**.

**Comportamiento:**
```
  ⚠️  HUMAN-IN-THE-LOOP — Accion Destructiva Detectada

  Agente: @data-architect
  Accion propuesta:
    | DROP TABLE users

  Opciones:
    [Y] Aprobar — Permitir la ejecucion
    [N] Rechazar — Bloquear + feedback opcional al agente
    [S] Saltar — No preguntar mas en esta sesion

  Timeout: 300s (denegado automaticamente)
```

---

### Memoria Vectorial (LanceDB)

- **LanceDB** es el nucleo de memoria del sistema: almacena vectores de embedding, metadatos, y permite busqueda semantica.
- **Obligatorio**: El sistema falla con un mensaje claro si LanceDB no esta instalado.
- **Fallback in-memory**: Solo disponible con `LanceVectorStore(allow_fallback=True)` para emergencias/test.
- **Nuevo nombre**: La base se almacena en `harness/db/lancedb/` (el directorio legacy se migra automaticamente durante `init.py` si usaba el nombre anterior).

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

## Migración de Base de Datos

Al actualizar el harness en un proyecto existente (ej. copias un nuevo `harness/` sobre uno viejo), tus datos de LanceDB pueden necesitar migración si la estructura de colecciones cambió entre versiones.

**Nota:** El directorio de la BD ahora es `harness/db/lancedb/`. Si tenés una BD del esquema anterior (con el nombre de directorio legacy), el `init.py` la migra automaticamente al nuevo nombre.

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
python harness/run.py "!db rollback harness/db/_backup_20260101_120000/"
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
- **Hibrido:** Enrutamiento inteligente local/cloud para optimizar costos.
- **Seguro:** HITL Guard intercepta acciones destructivas antes de ejecutarlas.
- **Extensible:** Cliente MCP universal para conectar cualquier herramienta del ecosistema.
- **Documentacion viva:** Toda decision tecnica se documenta en ADR.
