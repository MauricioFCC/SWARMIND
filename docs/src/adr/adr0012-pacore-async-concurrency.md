# ADR-0012: PaCoRe Async Concurrency

## Estado
**IMPLEMENTADO** — Commits: `061e114`.

## Contexto
El sistema original operaba 100% sincrónico: agentes ejecutaban en serie, el bus de mensajes era bloqueante, y el debate multi-agente secuenciaba rondas una tras otra. Para tareas complejas con +5 agentes, la latencia total era la suma de latencias individuales (fenómeno **Serial Stalling**).

Papers 2026 identifican patrones de concurrencia críticos:
- **PaCoRe** (Parallel Coordination + RL message-passing): reduce latencia multi-agente 4.8x (MPAC95)
- **LTS + Helium**: shared memory con scheduler RL decide qué contexto compartir
- **Symphony-Coord**: bandit-based routing con regret bounds
- **Struct47**: structured state spaces para coordinación paralela

## Decisión e Implementación

### 1. AsyncAgentBus — Bus de mensajes asíncrono
**Archivo:** `harness/orchestrator/agent_bus.py` (líneas 626–689)

```python
class AsyncAgentBus:
    """
    AgentBus asincrono con asyncio.Queue para coordinacion PaCoRe.
    
    Permite post/consume de mensajes sin bloqueo, con timeout y cancelacion.
    Cada canal tiene su propia cola asincrona.
    """
```

**API pública:**
| Método | Descripción |
|--------|-------------|
| `async post_message(channel, message)` | Publicar mensaje en canal (non-blocking) |
| `async consume(channel, timeout=30.0)` | Consumir mensaje con timeout (`asyncio.TimeoutError` si expira) |
| `get_queue_size(channel)` | Tamaño actual de la cola de un canal |

**Implementación:**
- Canales independientes con `asyncio.Queue` por canal
- `asyncio.Lock` para thread-safety en creación de canales
- Timeout configurable en `consume()` via `asyncio.wait_for`
- Sin dependencia de LanceDB (no persiste mensajes — responsabilidad del caller)

**Tests:** `harness/tests/test_async_agent_bus.py` (5 tests):
| Test | Descripción |
|------|-------------|
| `test_post_and_consume` | Post + consume en mismo canal |
| `test_consume_timeout` | TimeoutError en canal vacío |
| `test_multiple_channels` | Canales independientes no interfieren |
| `test_get_queue_size` | Tracking correcto de tamaño de cola |
| `test_concurrent_post` | 10 posts concurrentes sin race condition (asyncio.gather) |

**Dependencia:** `pytest-asyncio>=0.23` añadida para tests asíncronos.

### 2. DebateOrchestrator paralelo con asyncio.gather
**Archivo:** `harness/orchestrator/debate_orchestrator.py` (líneas 327–418)

```python
async def _execute_consensus_async(self, task, agents, max_rounds, dispatch_fn, session_id):
    """
    Version asincrona de consenso: agentes responden en paralelo.
    
    Usa asyncio.gather para ejecutar dispatch de todos los agentes
    simultaneamente, reduciendo latencia de O(n) a O(1).
    """
    responses = []
    for _round in range(max_rounds):
        round_responses = await asyncio.gather(
            *[self._run_async_dispatch(agent, task, dispatch_fn) 
              for agent in agents],
            return_exceptions=True,
        )
        valid = [r for r in round_responses if isinstance(r, str)]
        responses.extend(valid)
        if len(valid) == len(agents):
            agreement = self._compute_agreement(valid)
            if agreement > 0.9:
                break  # Convergencia temprana
```

**Mecanismo:**
- `_execute_consensus_async()`: ejecuta dispatch de todos los agentes simultáneamente
- `_run_async_dispatch()`: ejecuta `dispatch_fn` en thread executor para no bloquear el event loop
- Convergencia temprana: si el acuerdo entre agentes > 0.9, corta rondas restantes
- Reduce latencia de O(n·r) a O(r) donde n=número de agentes, r=rondas

### 3. LTS Shared Memory — WriteAheadLog para consistencia
**Archivo nuevo:** `harness/orchestrator/write_ahead_log.py` (239 líneas)

```python
class WriteAheadLog:
    """
    Write-Ahead Log para operaciones multi-agente con retry idempotente.
    
    Basado en patron WAL de sistemas de bases de datos.
    Provee reintento con backoff exponencial, cancelacion first-class,
    y recuperacion de estado tras crash.
    """
```

**API:**
| Método | Descripción |
|--------|-------------|
| `begin(type, payload, max_retries=3)` | Inicia operación, retorna `WALEntry` |
| `execute(entry, fn, *args)` | Ejecuta fn con retry + backoff exponencial (0.1s, 0.2s, 0.4s) |
| `cancel(operation_id)` | Cancela operación pendiente (solo PENDING → CANCELLED) |
| `recover_pending()` | Recupera operaciones pendientes tras crash |
| `get_status(operation_id)` | Consulta estado (`WALStatus`) |
| `_persist()` / `load_from_disk()` | Persistencia JSON a disco opcional |

**Estados (WALStatus):** `PENDING → COMMITTED | FAILED | CANCELLED`

**Tests:** `harness/tests/test_write_ahead_log.py` (10 tests):
- begin crea entry con UUID y PENDING
- execute exitoso marca COMMITTED
- execute reintenta hasta max_retries con backoff
- agotar reintentos lanza RuntimeError
- cancel pendiente (PENDING → CANCELLED)
- cancel en COMMITTED es no-op
- recover_pending filtra solo PENDING
- get_status retorna estado correcto o None
- persistencia y carga desde disco con tmp_path
- to_dict serializa todos los campos

## Referencias
- **PaCoRe**: Parallel Coordination + RL message-passing (MPAC95: 95% overhead reduction, 4.8x speedup)
- **LTS + Helium**: Long-Term Shared Memory con scheduler RL para contexto compartido
- **MPAC95**: arXiv, reduce overhead de coordinación multi-agente 95%

## Consecuencias

### Positivas
- Reducción de latencia O(n) → O(1) en rondas de debate
- API asíncrona preparada para escalar a +11 agentes
- WriteAheadLog da resiliencia con retry/cancelación/recovery
- Compatibilidad backward: clases originales no modificadas

### Negativas
- El sistema principal (AgentBus síncrono, TaskOrchestrator) aún no usa async
- AsyncAgentBus no está integrado en el pipeline principal — requiere migración gradual
- asyncio añade complejidad de debugging (tracebacks menos claros)
- `pytest-asyncio` requerido como dependencia adicional

### Pendiente
- Migrar `AgentBus.post_message` a `AsyncAgentBus.post_message` en `TaskOrchestrator`
- Integrar `WriteAheadLog.execute` en operaciones críticas (LLM calls, DB writes)
- Implementar LTS Shared Memory con controller RL
