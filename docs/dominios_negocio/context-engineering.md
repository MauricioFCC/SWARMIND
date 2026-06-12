# Context Engineering

!!! abstract "Resumen"

    Basado en el artículo de Anthropic (Sep 2025) sobre ingeniería de contexto para
    sistemas multi-agente. El Context Engineering es la disciplina de **curar, compactar
    y optimizar el contexto** que reciben los agentes para maximizar la precisión de
    sus respuestas minimizando el consumo de tokens.

---

## Principios Fundamentales

### 1. Minimal Viable Tokens

Usar **solo los tokens necesarios** para la tarea actual. Cada token adicional en el
contexto diluye la atención del modelo y aumenta el costo.

!!! tip "Regla práctica"

    Si puedes resolver la tarea con 500 tokens, no uses 1000. El contexto extra no
    mejora la calidad — la empeora por "atención diluida".

**Estrategias:**
- Eliminar instrucciones redundantes
- Usar abreviaciones estándar (OOS, WFV, MVA, FDE)
- Comprimir ejemplos a lo esencial

### 2. Sectioned Prompts

Estructurar los prompts en **secciones claramente delimitadas** (XML o Markdown).
Esto permite que el agente navegue el contexto eficientemente y que el sistema
pueda comprimir/eliminar secciones según el presupuesto de tokens.

```markdown
## Rol
Eres un software engineer especializado en APIs REST.

## Contexto del Proyecto
Proyecto: Onyx
Stack: Python + FastAPI

## Tarea
Implementa el endpoint POST /usuarios con:
- Validación Pydantic
- Autenticación JWT
- Tests unitarios

## Restricciones
- Timeout: 30s
- Retry: 3x backoff
- Sin secrets hardcodeados
```

### 3. JIT Retrieval (Just-In-Time)

Recuperar contexto **en el momento exacto** en que se necesita, no pre-cargar todo
el contexto disponible.

| Enfoque | Ventaja | Desventaja |
|---------|---------|------------|
| **Pre-loaded** | Rápido acceso | Consume tokens aunque no se use |
| **JIT Retrieval** | Solo tokens necesarios | Latencia de recuperación |

**Implementación en Onyx:**

El `@context-engineer` utiliza el `memory_rag/` del harness para recuperar chunks
relevantes de LanceDB justo antes de cada invocación de agente:

1. El usuario envía un mensaje
2. El router detecta la intención
3. El context-engineer consulta LanceDB con búsqueda híbrida (vector + keyword)
4. Recupera solo los 3-5 chunks más relevantes
5. Ensambla el contexto final con esos chunks

### 4. Compaction

Compactar el contexto eliminando información redundante pero **preservando decisiones
arquitectónicas, bugs activos y detalles críticos**.

**Niveles de Compacción:**

| Nivel | Acciones | Cuándo Usarlo |
|-------|----------|---------------|
| **Low** | Sin compresión, contexto completo | Tareas críticas de seguridad, compliance |
| **Medium** | Eliminar frases redundantes, abreviar términos | Tareas técnicas generales |
| **High** | Eliminar ejemplos, truncar agresivamente | Tareas simples, comandos, configs |

**Técnicas de Compacción:**

```yaml
# .opencode/config/token_budgets.yaml
compression:
  remove_redundant_phrases: true
  abbreviate_terms:
    "out-of-sample": "OOS"
    "walk-forward validation": "WFV"
    "stop loss": "SL"
  collapse_lists: true
  remove_examples_if_tight: true
```

### 5. Structured Note-Taking

Para tareas multi-turno, mantener **notas estructuradas persistentes** que acumulan
información relevante sin repetir todo el historial del contexto.

```markdown
# Task Notes: Módulo de Facturación
## Decisiones
- DB: PostgreSQL con esquema de facturas
- Auth: JWT con refresh tokens
- API: REST en FastAPI

## Bugs Activos
- Bug #42: Timeout en POST /facturas cuando >100 items

## Pendientes
- [ ] Tests de integración para el endpoint de creación
- [ ] Documentación de API
```

### 6. Tool Call Clearing

Limpiar los resultados de tool calls después de una profundidad de anidamiento >5.
Los resultados raw de herramientas consumen mucho contexto y rara vez son necesarios
después de varios turnos.

!!! warning "Tool Call Bloat"

    Después de 5+ tool calls anidadas, el contexto puede contener kilobytes de
    resultados de herramientas que ya no son relevantes. El `@context-engineer`
    debe limpiar estos resultados, manteniendo solo un resumen.

---

## Optimización del Presupuesto de Tokens

### Budgets por Rol

Cada rol tiene un presupuesto de tokens definido en `token_budgets.yaml`:

| Rol | Budget | Nivel Compresión | Incluir Principios |
|-----|--------|-------------------|-------------------|
| `project-manager` | 2500 | low | always |
| `quant-developer` | 2048 | medium | space_available |
| `quant-scientist` | 2500 | low | always |
| `risk-manager` | 1800 | medium | space_available |
| `software-engineer` | 2048 | medium | space_available |
| `devops-sre` | 1800 | high | minimal |
| `security-engineer` | 2048 | low | always |
| `quality-gate` | 1800 | medium | space_available |
| `data-architect` | 2048 | medium | space_available |
| `frontend-engineer` | 1800 | high | minimal |
| `mobile-engineer` | 1800 | high | minimal |
| `trading-operations` | 2048 | low | always |
| `documentation-specialist` | 2500 | low | always |
| `ai-engineer` | 2048 | medium | space_available |
| `context-engineer` | 2048 | medium | space_available |

### Decisiones Técnicas (IF-THEN)

El `@context-engineer` aplica estas reglas de decisión:

| Condición | Acción |
|-----------|--------|
| `context_window > 80%` | Activar compactación |
| `tool_call_depth > 5` | Limpiar resultados, mantener resumen |
| `nuevo_agente` | Auditar prompt: seccionado + minimal + ejemplos canónicos |
| `tool_overlap` | Fusionar tools o rediseñar |
| `token_budget_exceeded` | Comprimir secciones no críticas |
| `long_horizon_task` | Notas estructuradas + compactación periódica |
| `context_rot` | Reducir contexto, priorizar alta señal |

---

## JIT vs Pre-loaded Context

### Cuándo usar JIT Retrieval

| Situación | Estrategia | Ejemplo |
|-----------|------------|---------|
| Documentación extensa | **JIT** | 10,000 líneas de docs — recuperar solo 3 chunks relevantes |
| Código base grande | **JIT** | Buscar definiciones de funciones relacionadas |
| Tareas específicas | **JIT** | "Agrega campo a la tabla usuarios" → solo schema relevante |

### Cuándo usar Pre-loaded Context

| Situación | Estrategia | Ejemplo |
|-----------|------------|---------|
| Reglas críticas de seguridad | **Pre-loaded** | Reglas de compliance, secretos prohibidos |
| Configuración del proyecto | **Pre-loaded** | `project_config.yaml`, stack tecnológico |
| Principios del sistema | **Pre-loaded** | FDE Principles, base_principles.md (versión compacta) |

### Estrategia Híbrida (Recomendada)

```
Contexto Total = Pre-loaded (crítico) + JIT (bajo demanda)

Pre-loaded (~20% del budget):
- Rol del agente
- Reglas críticas (seguridad, arquitectura)
- Configuración del proyecto

JIT Retrieval (~80% del budget):
- Chunks de documentación relevantes
- Código relacionado
- Historial de tareas similares
- Cognition store (lecciones aprendidas)
```

---

## Implementación en Harness

El `@context-engineer` orquesta la recuperación de contexto a través del
`memory_rag/context_assembler.py`:

```
1. Recibir mensaje del usuario
2. Extraer entidades e intención
3. Consultar LanceDB (búsqueda híbrida):
   - Vector embedding del mensaje
   - Filtro por metadatos (dominio, tipo)
4. Recuperar top-k chunks (k=3-5)
5. Compactar según budget disponible
6. Ensamblar contexto final:
   [System Prompt] + [Pre-loaded] + [JIT Chunks] + [Mensaje Usuario]
7. Validar contra guardrails (RAG Triad)
```

### RAG Triad (Guardrails)

Tres validaciones sobre el contexto recuperado:

| Check | Descripción | Código |
|-------|-------------|--------|
| **Groundedness** | El contexto está fundamentado en fuentes reales | `RAG-001` |
| **Context Relevance** | El contexto recuperado es relevante para la consulta | `RAG-002` |
| **Faithfulness** | La respuesta no alucina ni contradice el contexto | `RAG-003` |

---

## Referencias

- [Artículo de Anthropic sobre Context Engineering (Sep 2025)](https://anthropic.com/)
- [Configuración de Token Budgets](https://github.com/onyx-project/onyx/blob/main/.opencode/config/token_budgets.yaml)
- [Agente Context Engineer](https://github.com/onyx-project/onyx/blob/main/.opencode/agents/context-engineer.md)
- [FDE Principles - VALUE Pillar](https://github.com/onyx-project/onyx/blob/main/.opencode/core/fde_principles.md)
