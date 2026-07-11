# Guía del Sistema AGENTIC — Swiss Watch Multi-Agente

## 📋 Índice
1. [Filosofía del Sistema](#-filosofía-del-sistema)
2. [Cómo Usar AGENTIC Correctamente](#-cómo-usar-agentic-correctamente)
3. [Estrategias para que el LLM no pierda memoria](#-estrategias-para-que-el-llm-no-pierda-memoria)
4. [Máximo Provecho del Sistema](#-máximo-provecho-del-sistema)
5. [Estándares Automáticos (sin mencionarlos)](#-estándares-automáticos-sin-mencionarlos)
6. [El Patrón Swiss Watch](#-el-patrón-swiss-watch)
7. [Estructura del Proyecto](#-estructura-del-proyecto)
8. [Cómo Modificar Archivos Correctamente](#-cómo-modificar-archivos-correctamente)
9. [Agentes y sus Responsabilidades](#-agentes-y-sus-responsabilidades)
10. [Optimización de Tokens](#-optimización-de-tokens)
11. [Exportación y Backup](#-exportación-y-backup)
12. [Checklist de Calidad](#-checklist-de-calidad)

---

## 🎯 Filosofía del Sistema

AGENTIC es un **sistema multi-agente evolutivo** diseñado para operar como un **reloj suizo**: múltiples especialistas trabajando en paralelo, sincronizados, sin fricción.

### Principios Clave

| Principio | Significado |
|-----------|-------------|
| **Swiss Watch** | Todos los agentes relevantes arrancan SIMULTÁNEAMENTE |
| **Zero Preamble** | No necesitas mencionar estándares — ya están embebidos |
| **Quality by Default** | Clean Code, DRY, KISS, SSOT, <900LC, patrones, DocStrings ES-UTF8, tests >80% |
| **Speed at Scale** | Paralelismo máximo, fan-out, consolidación al final |

---

## 🚀 Cómo Usar AGENTIC Correctamente

### ✅ FORMA CORRECTA (sin preámbulo)

Simplemente escribe tu tarea en lenguaje natural. **No necesitas agregar:**

```
❌ "Delega a especialistas aplicando .opencode y harness..."
❌ "Aplica buenas practicas de programacion, <900LC..."
❌ "Patrones de disenio, Clean Code, KISS, SSOT, DRY..."
❌ "documentacion actualizada, DocString ES-UTF8..."
```

**Ejemplos correctos:**

| Tarea | Resultado |
|-------|-----------|
| `"implementa una API REST en Rust"` | ✅ Builder escribe API + Scientist investiga + Guardian testea/documenta |
| `"crea un modulo de trading con risk management"` | ✅ Todos los agentes en paralelo con calidad automática |
| `"refactoriza el modulo de auth"` | ✅ Scientist analiza + Builder refactoriza + Guardian verifica |
| `"investiga patrones de diseño para microservicios"` | ✅ Scientist investiga + Builder prototipa + Guardian documenta |
| `"audita seguridad del código"` | ✅ Guardian audita + Builder corrige + Guardian verifica |

### ❌ FORMA INCORRECTA

```
❌ "@builder: implementa X con clean code y test"
   → No hace falta, @builder ya aplica todo automáticamente

❌ "@scientist: investiga X y documenta los hallazgos"
   → El coordinator ya asigna guardian para documentar
```

### La Magia

El sistema AGENTIC **ya tiene todo configurado** en los prompts de los agentes:

- `coordinator.md` → Orquestación Swiss Watch, delega en paralelo
- `builder.md` → Escribe código con Clean Code, DRY, KISS, SSOT, <900LC, patrones, DocStrings ES-UTF8, tests >80%
- `scientist.md` → Investiga con rigurosidad académica
- `guardian.md` → Calidad, seguridad, tests, documentación

No necesitas recordarle nada al sistema. Solo describe **qué** hacer, no **cómo** hacerlo.

---

## 🧠 Estrategias para que el LLM no pierda memoria

Uno de los mayores desafíos al trabajar con LLMs es la **pérdida de contexto** entre sesiones.
AGENTIC está diseñado con mecanismos para mitigar esto, pero hay estrategias que el usuario
(es decir, TÚ leyendo este documento) puede aplicar para mantener la memoria del sistema.

### 📌 Estrategia 1: Este documento como prompt de sistema

Cuando inicies una nueva sesión con el LLM, **este documento debe ser el contexto inicial**.

El LLM que lee este documento DEBE:
1. Recordar que existe un sistema AGENTIC con 5 agentes especializados
2. Recordar que los estándares de calidad están embebidos (no necesita mencionarlos)
3. Recordar que debe delegar al coordinator para tareas multi-agente
4. Recordar la estructura del proyecto (.opencode, harness/)
5. Recordar que existe `export_archive.py` para backups

**Forma correcta de iniciar una sesión:**
```
He leído y comprendo la GUIA_AGENTIC.md. 
Soy un sistema AGENTIC Swiss Watch con 5 agentes (coordinator, builder, scientist, guardian, evolve).
Tengo estándares automáticos: Clean Code, DRY, KISS, SSOT, <900LC, patrones, DocStrings ES-UTF8, tests >80%.
Mi proyecto está en C:\Users\USUARIO\Documents\DEV-SPACE\AGENTIC
```

### 📌 Estrategia 2: Recordatorios estructurados al iniciar tareas

Para tareas largas o complejas, incluir un **brief recordatorio** al inicio:

```
Contexto actual del proyecto AGENTIC:
- .opencode/agents/ → perfiles de 5 agentes
- harness/ → motor de ejecución con 327 tests
- skills disponibles: 10 skills en .opencode/skills/
- export: scripts/export_archive.py
- commit reciente: d102c2f (optimización tokens + Swiss Watch)
```

### 📌 Estrategia 3: Usar el sistema de skills como memoria externa

Los skills en `.opencode/skills/` actúan como **memoria externa del LLM**.
Cada skill contiene conocimiento especializado que el LLM puede consultar.

```bash
# Los skills disponibles son:
ls .opencode/skills/
# alpha-research/  evolve/  hedgefund/  math-doc/  quant-trading/
# risk-execution/  science-doc/  healthtech/  legal-doc/  pos-retail/
```

### 📌 Estrategia 4: El archivo cognition_store como memoria persistente

AGENTIC usa `asi_cognition_store` en LanceDB para persistir lecciones aprendidas.
Cada vez que completas una tarea importante, el sistema guarda:

- Qué funcionó (patrones de éxito)
- Qué no funcionó (patrones de fracaso)
- Decisiones técnicas tomadas
- Lecciones aprendidas

**Para consultar la memoria del sistema:**
```python
from harness.evolve_loop.cognition_sync import CognitionSync
store = LanceVectorStore()
cog = CognitionSync(store)
lecciones = cog.get_lessons_by_domain("harness.routing")
```

### 📌 Estrategia 5: Resiliencia ante pérdida de contexto

Si el LLM "olvida" el contexto del proyecto:

1. **Re-leer este documento** — Especialmente las secciones de agentes y estándares
2. **Consultar los agentes** — `cat .opencode/agents/coordinator.md` para recordar el patrón Swiss Watch
3. **Ejecutar el health check** — `python harness/run.py '!health'` para verificar que el sistema está vivo
4. **Revisar el último commit** — `git log --oneline -5` para saber el estado actual
5. **Usar el export como snapshot** — `python scripts/export_archive.py --dry-run` para ver el estado del proyecto

### 📌 Estrategia 6: Mantener un archivo SESSION_LOG.md

Para sesiones largas, mantener un log de decisiones:

```markdown
# Session Log - AGENTIC
## 2026-07-10

## Tarea: Optimización de tokens
- Se modificó prompt_compressor.py (modo ligero)
- Se minificaron agent prompts (-35%)
- Se refactorizó task_orchestrator.py (<900LC)
- Commit: d102c2f

## Tarea: Exportación
- 5 proyectos recibieron mejoras
- Export AGENTIC: 650 KB, 30.3% compresión
```

---

## 🚀 Máximo Provecho del Sistema

### ⚡ Modo Turbo — Para veteranos

Una vez que conoces el sistema, puedes usar **comandos directos** sin pasar por el coordinator:

```bash
# Delegación directa a un agente específico
python harness/run.py "@builder: implementa modulo X en Rust"
python harness/run.py "@scientist: investiga algoritmo Y"
python harness/run.py "@guardian: audita seguridad de Z"

# Sin preámbulo — los estándares ya están en los agentes
python harness/run.py "@builder: API REST en Python con FastAPI"
# Esto automaticamente produce: código limpio + tests >80% + DocStrings ES-UTF8
```

### ⚡ Atajos de Productividad

| Acción | Comando |
|--------|---------|
| Health check rápido | `python harness/run.py '!health'` |
| Ver métricas | `python harness/run.py '!metrics'` |
| Exportar proyecto | `python scripts/export_archive.py --format zip` |
| Ver tests | `python -m pytest harness/tests/ -q` |
| Ver agentes | `ls .opencode/agents/` |
| Ver skills | `ls .opencode/skills/` |

### ⚡ Orquestación Avanzada

Para tareas que requieren máxima potencia, usa el **patrón SWARM explícito**:

```
Quiero que hagas lo siguiente como equipo SWARM:
1. [builder] Implementa el módulo de procesamiento de señales
2. [scientist] Investiga la mejor técnica de filtrado
3. [guardian] Prepara el plan de tests y seguridad
4. [coordinator] Consolida todo al final
```

Esto fuerza el lanzamiento simultáneo de los 3 agentes desde el nivel 0.

### ⚡ Pipeline Completo (Todo en uno)

```bash
# 1. Implementar con calidad automática
python harness/run.py "implementa un modulo de risk management"

# 2. Verificar salud
python harness/run.py '!health'

# 3. Exportar backup
python scripts/export_archive.py --format zip

# 4. Ver estado de git
git status
```

---

## 📜 Estándares Automáticos (sin mencionarlos)

Estos estándares se aplican SIEMPRE a toda tarea delegada. **No requieren mención explícita.**

### 🏗️ Código

| Estándar | Descripción |
|----------|-------------|
| **Clean Code** | Nombres expresivos, funciones <30 líneas, sin side effects, sin comentarios obvios |
| **DRY** | Cero duplicación. Toda lógica repetida → función/módulo reutilizable |
| **KISS** | Mínima complejidad necesaria. Claridad > "elegancia" |
| **SSOT** | Una sola fuente de verdad para cada dato. No redundancia |
| **<900LC** | Ningún archivo supera 900 líneas. Refactorizar si es necesario |
| **Patrones de Diseño** | Strategy, Factory, Repository, Observer según corresponda |
| **YAGNI** | No implementar nada que no se necesite AHORA |
| **Clean Architecture** | Dominio puro. Infraestructura en capas. Dependencias hacia adentro |

### 📝 Documentación

| Estándar | Descripción |
|----------|-------------|
| **DocStrings ES-UTF8** | Toda función pública documentada en español con UTF-8 |
| **Formato** | `"""Descripción. Args: x (tipo): desc. Returns: tipo. Raises: Error. """` |
| **README** | Documentar setup, uso, ejemplos, arquitectura si es nuevo módulo |
| **Commits** | Convencionales (feat/fix/docs/refactor/test/chore), en español |

### 🔬 Testing

| Estándar | Descripción |
|----------|-------------|
| **Cobertura mínima** | >80% en código nuevo |
| **Tests unitarios** | Función por función, casos normales + borde + error |
| **Tests de integración** | Flujos completos que cruzan módulos |
| **Regression** | Verificar que tests existentes sigan pasando |

### 🔒 Seguridad

| Estándar | Descripción |
|----------|-------------|
| **Validación** | Toda entrada validada (inyección, XSS, path traversal) |
| **Secrets** | Nunca hardcodear API keys, contraseñas, tokens |
| **SQL** | Siempre parametrizado, nunca concatenado |
| **Logging** | Sin datos sensibles (PII, credenciales) |

---

## 🧠 El Patrón Swiss Watch

### Antes (Secuencial)

```
Usuario -> Coordinator -> [builder] codigo -> [guardian] tests -> [guardian] docs
                         1 agente a la vez        4 ciclos secuenciales
```

### Después (Swiss Watch - ACTUAL)

```
Usuario -> Coordinator -> SWARM (Nivel 0) --------------------------------
                          | [builder]   Implementa código                |
                          | [scientist] Investiga alternativas           |  ← TODOS EN PARALELO
                          | [guardian]  Plan de testing y seguridad     |
                          |----------------------------------------------|
                                      |
                          Nivel 1: [guardian] Tests + [guardian] Docs
                                      |
                          Nivel 2: [coordinator] Consolidar resultados
```

### Ventajas

| Aspecto | Antes | Ahora |
|---------|-------|-------|
| Agentes simultáneos | 1-2 | 3-6 |
| Tiempo de ejecución | 4 ciclos | 3 niveles paralelos |
| Cobertura de calidad | Solo si se pedía | Siempre automática |
| Tokens desperdiciados | Preámbulo repetitivo | Cero preámbulo |

---

## 📁 Estructura del Proyecto

```
AGENTIC/
├── .opencode/                          # CEREBRO DEL SISTEMA (memoria del LLM)
│   ├── agents/                         # Perfiles de agentes (5)
│   │   ├── coordinator.md              # Orquestador Swiss Watch
│   │   ├── coordinator.agent.min.md    # Versión minificada (<300 chars)
│   │   ├── builder.md                  # Implementador calidad automática
│   │   ├── builder.agent.min.md
│   │   ├── scientist.md                # Investigador técnico
│   │   ├── guardian.md                 # Calidad, seguridad, docs
│   │   └── evolve.md                   # Auto-mejora del sistema
│   ├── skills/                         # MEMORIA ESPECIALIZADA (10 skills)
│   │   ├── alpha-research/             # Factor research, ML, feature engineering
│   │   ├── evolve/                     # Self-improvement loop
│   │   ├── healthtech/                 # Salud, HIPAA, interoperabilidad
│   │   ├── hedgefund/                  # Hedge fund institucional
│   │   ├── legal-doc/                  # Documentos legales, compliance
│   │   ├── math-doc/                   # Documentos matemáticos, LaTeX
│   │   ├── pos-retail/                 # Punto de venta, retail
│   │   ├── quant-trading/              # Trading cuantitativo con CQE Rust
│   │   ├── risk-execution/             # Risk management, position sizing
│   │   └── science-doc/                # Documentos científicos
│   ├── core/                           # Router, guardrails, registry
│   │   ├── router_v2.py               # Enrutamiento multi-agente
│   │   ├── guardrails.py               # Seguridad y validaciones
│   │   ├── registry.py                 # Registro de skills con contratos
│   │   └── base_principles.md          # Principios universales
│   └── config/                         # Config del proyecto
│       ├── project_config.yaml          # Metadata del proyecto
│       ├── routing_rules.yaml           # Reglas de enrutamiento por intent
│       └── token_budgets.yaml           # Presupuestos de tokens por rol
├── harness/                            # MOTOR DE EJECUCIÓN
│   ├── orchestrator/                   # Corazón: planner, dispatcher, health
│   │   ├── task_orchestrator.py        # Orquestador (<900LC ✅)
│   │   ├── task_planner.py             # Planificador con templates SWARM
│   │   ├── difficulty_router.py        # Clasifica complejidad
│   │   ├── structured_log.py           # Logging estructurado
│   │   ├── self_healing.py             # Circuit breaker + timeouts
│   │   ├── orchestration_result.py     # Resultados
│   │   ├── agent_bus.py                # Comunicación entre agentes
│   │   ├── agent_dispatcher.py         # Dispatch asíncrono batch
│   │   ├── session_context.py          # Contexto de sesión
│   │   ├── federated_memory.py         # Memoria entre proyectos
│   │   ├── health.py                   # Health check 3 niveles
│   │   ├── telemetry.py                # KPIs y telemetría
│   │   └── ... (adaptive_planner, debate, confidence, etc.)
│   ├── memory_rag/                     # MEMORIA VECTORIAL (LanceDB)
│   │   ├── lance_vector_store.py       # Vector store principal
│   │   ├── prompt_compressor.py        # Compresor ligero (19% ahorro)
│   │   ├── semantic_cache.py           # Cache semántico (evita LLM calls)
│   │   ├── token_budget.py             # Presupuesto de tokens por pool
│   │   ├── context_assembler.py        # Ensambla contexto RAG
│   │   ├── context_window_manager.py   # Gestión de ventana de contexto
│   │   ├── agent_kpi_tracker.py        # KPIs por agente y sesión
│   │   ├── skill_loader.py             # Carga skills desde .opencode
│   │   └── trajectory_compressor.py    # Compresión de trayectorias
│   ├── model_router/                   # Enrutamiento local/cloud
│   ├── evolve_loop/                    # Auto-mejora ASI-Evolve
│   ├── gateway/                        # CLIs, Slack, Telegram
│   ├── db/                             # Migración y persistencia
│   │   ├── migrate_engine.py           # Motor de migración
│   │   ├── migrate_discovery.py        # Descubrimiento de colecciones
│   │   └── migrate_cli.py              # CLI de migración
│   └── tests/                          # 327 tests de integración
├── scripts/
│   ├── export_archive.py               # Script universal de exportación
│   ├── hermes_bridge.py                # Puente con Hermes_Memory_Proyects
│   └── ... (ingest, consolidation, etc.)
└── GUIA_AGENTIC.md                     # Este documento
```

---

## 🔧 Cómo Modificar Archivos Correctamente

### Regla #1: Respetar <900LC

Ningún archivo Python debe superar **900 líneas**. Si un archivo crece demasiado:

```python
# MAL: 1138 líneas en un archivo
task_orchestrator.py  # ❌

# BIEN: Extraer a módulos
task_orchestrator.py          # 752 líneas ✅
structured_log.py             # 62 líneas  ✅
self_healing.py               # 168 líneas ✅
orchestration_result.py       # 60 líneas  ✅
```

### Regla #2: No duplicar estándares en prompts

Los estándares ya están en los agentes. No los repitas en templates:

```python
# MAL: Descripción enorme repitiendo estándares
{"description": "Implementar codigo siguiendo Clean Code DRY KISS SSOT <900LC..."}

# BIEN: Descripción corta, el estándar está en builder.md
{"description": "Implementar (estandares automaticos en builder.md)"}
```

### Regla #3: Usar el export_archive.py

Para respaldar el proyecto comprimido:

```bash
python scripts/export_archive.py                 # tar.gz por defecto
python scripts/export_archive.py --format zip    # ZIP
python scripts/export_archive.py --output ../backups/  # Destino personalizado
python scripts/export_archive.py --dry-run       # Vista previa
```

### Regla #4: DocStrings en ES-UTF8

Toda función pública debe tener DocString en español:

```python
def procesar_orden(orden_id: str, monto: float) -> dict:
    \"\"\"
    Procesa una orden de trading.

    Args:
        orden_id: Identificador unico de la orden.
        monto: Monto de la operacion en USD.

    Returns:
        Dict con estado de la orden y confirmacion.

    Raises:
        ValueError: Si el monto es negativo o cero.
    \"\"\"
    ...
```

### Regla #5: Commits Convencionales

```
feat: nueva funcionalidad para el modulo X
fix: correccion de bug en el login
docs: actualizar documentacion de la API
refactor: extraer modulo de autenticacion
test: agregar tests para el modulo de pagos
chore: actualizar dependencias
```

---

## 🤖 Agentes y sus Responsabilidades

| Agente | Rol | Se activa con keywords |
|--------|-----|------------------------|
| **@coordinator** | Orquestador Swiss Watch | plan, organize, coordinate, delegate |
| **@builder** | Implementador calidad automática | implement, build, code, api, rust, python |
| **@scientist** | Investigador técnico | research, paper, architecture, design, algorithm |
| **@guardian** | Calidad, seguridad, documentación | test, security, audit, risk, doc, quality |
| **@evolve** | Auto-mejora del sistema | evolve, improve, optimize, skill, cognition |

Los agentes **intercambian información en tiempo real** via AgentBus:
- Builder comunica decisiones técnicas → Scientist ajusta investigación
- Scientist comparte hallazgos → Builder optimiza implementación
- Guardian monitorea calidad → Los demás corrigen automáticamente

---

## 💰 Optimización de Tokens

### Ahorro por Componente

| Componente | Técnica | Ahorro |
|-----------|---------|:------:|
| **Prompts de agentes** | Minificación (sin perder semántica) | 35% |
| **Templates de subtareas** | Descripciones cortas + abreviaciones | 24% |
| **Compresor ligero** | Regex + abreviaciones en runtime | 19% |
| **Compresor LLMLingua** | Compresión por IA (opcional) | 40-60% |
| **Semantic Cache** | Evita LLM calls repetidas | 50-80% |
| **Token Budget** | Prioridad por pool de tokens | 30-50% |

### Consejos para Ahorrar Tokens

1. **Sé específico, no verboso**: `"implementa API REST en Rust"` usa menos tokens que describir cada detalle
2. **No repitas estándares**: El sistema ya los conoce
3. **Prefiere español**: Algunos tokens se comprimen mejor en español
4. **Usa el semantic cache**: Preguntas similares se responden desde caché

---

## 📦 Exportación y Backup

### Script Universal

```bash
python scripts/export_archive.py
```

| Flag | Uso |
|------|-----|
| `--format zip` | Exporta en ZIP (más compatible Windows) |
| `--format tar.gz` | Exporta en tar.gz (más comprimido) |
| `--output DIR` | Directorio destino personalizado |
| `--dry-run` | Solo muestra qué se incluiría |
| `--verbose` | Muestra cada archivo incluido |
| `--project NAME` | Nombre personalizado del proyecto |

### Ejemplos

```bash
# Exportar a Google Drive
python scripts/export_archive.py --format zip --output "C:\Users\USUARIO\Mi unidad\DEV\SIDEPROYECT"

# Backup rápido
python scripts/export_archive.py --format zip

# Solo ver qué se exportaría
python scripts/export_archive.py --dry-run
```

---

## ✅ Checklist de Calidad

Antes de dar una tarea por completada, verificar:

- [ ] **<900LC**: Ningún archivo supera 900 líneas
- [ ] **Clean Code**: Nombres descriptivos, funciones <30 líneas
- [ ] **DRY**: Sin código duplicado
- [ ] **KISS**: Solución más simple posible
- [ ] **SSOT**: Cada dato en un solo lugar
- [ ] **DocStrings ES-UTF8**: Toda función pública documentada
- [ ] **Tests**: Cobertura >80% en código nuevo
- [ ] **Patrones**: Strategy, Factory, Repository según el caso
- [ ] **Seguridad**: Sin secrets hardcodeados, inputs validados
- [ ] **Commits**: Convencionales en español

---

## 🏁 Conclusión

AGENTIC está diseñado para que **no tengas que pensar en la infraestructura**.
Solo describe **qué** necesitas, y el sistema se encarga de:

1. **Orquestar** los agentes correctos en paralelo
2. **Aplicar** todos los estándares de calidad automáticamente
3. **Coordinar** la comunicación entre especialistas
4. **Consolidar** resultados en una entrega unificada
5. **Auto-mejorarse** con cada iteración

**No escribas preámbulos. Solo describe tu tarea. El sistema hace el resto.**

---

*Documento generado: 2026-07-10 | AGENTIC Harness v2.0*  
*Commit: `d102c2f` — feat: optimizacion tokens + purga <900LC + Swiss Watch multi-agente*
