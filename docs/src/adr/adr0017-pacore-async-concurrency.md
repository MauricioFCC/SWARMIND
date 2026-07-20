# ADR-0017: PaCoRe Async Concurrency Pattern

## Estado
**PROPUESTO** — Pendiente de implementación.

## Contexto
El sistema actual opera 100% sincrónico: agentes ejecutan en serie, el bus de mensajes es bloqueante, y el debate multi-agente secuencia rondas una tras otra. Para tareas complejas con +5 agentes, la latencia total es la suma de latencias individuales (fenómeno **Serial Stalling**).

Papers 2026 identifican patrones de concurrencia críticos:
- **PaCoRe** (Parallel Coordination + RL message-passing): reduce latencia multi-agente 4.8x (MPAC95)
- **LTS + Helium**: shared memory con scheduler RL decide qué contexto compartir
- **Symphony-Coord**: bandit-based routing con regret bounds
- **Struct47**: structured state spaces para coordinación paralela

## Decisión

### 1. AgentBus asíncrono con asyncio.Queue
```python
class AsyncAgentBus:
    def __init__(self):
        self._queues: Dict[str, asyncio.Queue] = {}
        self._lock = asyncio.Lock()
    
    async def post_message(self, channel, from_agent, to_agent, message, ...):
        async with self._lock:
            # Validación + persistencia paralela
            asyncio.create_task(self._persist_message(msg))
        
    async def consume(self, channel, timeout=30):
        # Non-blocking consume con timeout
```

### 2. DebateOrchestrator paralelo con asyncio.gather
```python
# Rondas de debate en paralelo vs serie
async def _execute_consensus_async(self, task, agents, ...):
    tasks = [self._dispatch(agent, task) for agent in agents]
    responses = await asyncio.gather(*tasks, return_exceptions=True)
```

### 3. LTS Shared Memory para contexto compartido
- Controller RL decide qué experiencias compartir entre agentes paralelos
- Write-Ahead Log para consistencia sin locks
- Cache de shaped observations (-38% tokens)

## Consecuencias
- Positivas: Reducción 3-5x en latencia multi-agente, mejor uso de recursos
- Negativas: Complejidad de debugging asíncrono, migración gradual requerida
- Mitigación: Wrappers sync→async para compatibilidad backward
