# Como Usar Swarmind

Swarmind es un sistema multi-agente que recibe tareas en **lenguaje natural** y las ejecuta con calidad automatica. No necesitas preambulos ni mencionar estandares — todo esta embebido.

## 1. Delegacion Directa con `@`

Usa `@` seguido del nombre del agente para delegar explicitamente:

```bash
python harness/run.py "@builder: implementa una API REST en Rust con endpoints /users CRUD"
```

El sistema enruta directamente al agente indicado. Si la tarea requiere multiples disciplinas, el `coordinator` hara **fan-out** automatico a los otros agentes.

| Agente | Ejemplo |
|--------|---------|
| `@builder` | `@builder: crea un modulo de autenticacion JWT en Python` |
| `@scientist` | `@scientist: investiga arquitecturas event-sourcing vs CQRS` |
| `@guardian` | `@guardian: audita seguridad del codigo en src/auth` |
| `@evolve` | `@evolve: optimiza el skill de trading para reducir latencia` |
| `@coordinator` | `@coordinator: organiza el proyecto completo con pipeline CI/CD` |

### Ejemplos completos

**Construir una API:**

```bash
python harness/run.py "@builder: implementa API REST en Rust con GET/POST /items,
usa Axum, PostgreSQL, y documentacion OpenAPI. Aplica todos los estandares."
```

Builder escribe el codigo, Scientist investiga la mejor arquitectura, Guardian genera tests.

**Auditar seguridad:**

```bash
python harness/run.py "@guardian: audita src/api/ --threat-model STRIDE --owasp-top10"
```

Guardian ejecuta SAST, modela amenazas, y Builder corrige hallazgos automaticamente.

**Proyecto completo de trading:**

```bash
python harness/run.py "@coordinator: disena e implementa un sistema de market making
con CQE Rust, backtesting, y dashboard en tiempo real"
```

Coordinator descompone en DAG, Scientist investiga estrategias, Builder implementa, Guardian testea.

## 2. Sin `@` — Deteccion Automatica de Agente

Si omites `@`, el **DifficultyRouter** analiza el mensaje y asigna automaticamente al agente mas adecuado segun las palabras clave detectadas:

| Mensaje | Agente asignado |
|---------|----------------|
| "implementa una funcion de ordenamiento en Go" | builder |
| "investiga papers sobre transformers 2026" | scientist |
| "audita la seguridad del sistema" | guardian |
| "mejora el rendimiento general del sistema" | evolve |
| "organiza el sprint de la semana" | coordinator |

El sistema aplica **Swiss Watch**: todos los agentes relevantes arrancan simultaneamente y el coordinator consolida al final.

## 3. Comandos del Sistema

| Comando | Descripcion |
|---------|-------------|
| `!health` | Estado del sistema: agentes activos, skills cargados, sesion actual |
| `!metrics` | Metricas de rendimiento: tokens consumidos, latencia, hits de cache |
| `!skill list` | Lista todos los skills disponibles (31 skills en 12 dominios) |
| `!session` | Muestra el estado de la sesion actual y subtareas pendientes |
| `!reset` | Reinicia el contexto de la sesion actual |
| `!help` | Muestra esta guia rapida de comandos |

Ejemplo:

```bash
python harness/run.py "!health"
```

Retorna: agentes activos, skills cargados por agente, y estado del orquestador.

## 4. Flujo de Trabajo Tipico

1. **Escribe tu tarea** en lenguaje natural, con o sin `@agente`
2. **Coordinator analiza** la complejidad (DifficultyRouter) y descompone en DAG de subtareas (TaskPlanner)
3. **Los agentes ejecutan** en paralelo segun dependencias del DAG
4. **Worktable debate** (si aplica): 13 expertos discuten calidad y trade-offs
5. **Consolidacion**: coordinator unifica resultados y presenta el output final

## 5. Modo Iterativo

Swarmind preserva contexto entre interacciones. Puedes refinar:

```bash
python harness/run.py "@builder: anade un endpoint DELETE a la API anterior"
```

El sistema recupera el contexto de la sesion y opera sobre el codigo existente sin partir de cero.
