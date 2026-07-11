# Guía del Sistema AGENTIC — Swiss Watch Multi-Agente

## 📋 Índice
1. [Filosofía del Sistema](#-filosofía-del-sistema)
2. [Cómo Usar AGENTIC Correctamente](#-cómo-usar-agentic-correctamente)
3. [Estándares Automáticos (sin mencionarlos)](#-estándares-automáticos-sin-mencionarlos)
4. [El Patrón Swiss Watch](#-el-patrón-swiss-watch)
5. [Estructura del Proyecto](#-estructura-del-proyecto)
6. [Cómo Modificar Archivos Correctamente](#-cómo-modificar-archivos-correctamente)
7. [Agentes y sus Responsabilidades](#-agentes-y-sus-responsabilidades)
8. [Optimización de Tokens](#-optimización-de-tokens)
9. [Exportación y Backup](#-exportación-y-backup)
10. [Checklist de Calidad](#-checklist-de-calidad)

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
├── .opencode/                    # Cerebro del sistema
│   ├── agents/                   # Perfiles de agentes
│   │   ├── coordinator.md        # Orquestador Swiss Watch
│   │   ├── coordinator.agent.min.md  # Versión minificada
│   │   ├── builder.md            # Implementador con calidad automática
│   │   ├── builder.agent.min.md
│   │   ├── scientist.md          # Investigador
│   │   ├── guardian.md           # Calidad y seguridad
│   │   └── evolve.md             # Auto-mejora
│   ├── skills/                   # Skills del sistema (10)
│   ├── core/                     # Router, guardrails, registry
│   └── config/                   # Config del proyecto + routing + tokens
├── harness/                      # Motor de ejecución
│   ├── orchestrator/             # Corazón: planner, dispatcher, health
│   │   ├── task_orchestrator.py  # Orquestador (<900LC ✅)
│   │   ├── task_planner.py       # Planificador con templates SWARM
│   │   ├── difficulty_router.py  # Clasifica complejidad
│   │   ├── structured_log.py     # Logging estructurado
│   │   ├── self_healing.py       # Circuit breaker + timeouts
│   │   ├── orchestration_result.py  # Resultados
│   │   └── ... (agent_bus, session_context, health, etc.)
│   ├── memory_rag/               # Memoria vectorial LanceDB
│   │   ├── prompt_compressor.py  # Compresor ligero (19% ahorro)
│   │   ├── semantic_cache.py     # Cache semántico
│   │   ├── token_budget.py       # Presupuesto de tokens
│   │   └── lance_vector_store.py # Vector store
│   ├── model_router/             # Enrutamiento local/cloud
│   ├── evolve_loop/              # Auto-mejora ASI-Evolve
│   ├── gateway/                  # CLIs, Slack, Telegram
│   ├── db/                       # Migración y persistencia
│   └── tests/                    # 327 tests
└── scripts/
    ├── export_archive.py         # Script universal de exportación
    └── ... (ingest, consolidation, etc.)
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
