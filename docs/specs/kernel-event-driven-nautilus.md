# Spec — Kernel event-driven para SWARMIND (mensaje/actor + determinismo)

> Estado: **implemented** (núcleo + bus del orchestrator) — Dueño: harness/orchestrator — Frontera: 2026-10-30.
> Evidencia: `harness/kernel/` (envelope/mailbox/event_log/loop, 20 tests) y
> `harness/orchestrator/agent_bus/kernel_bus.py` (KernelBus, 11 tests).
> Scope: patrón de kernel que unifica mensajes/actores en la infraestructura de
> SWARMIND (no el comando de un proyecto cliente). El análisis referencia
> NautilusTrader / actix / ractor / kameo como instancias del patrón, pero el
> dominio de aplicación es SWARMIND.

## 1. Proposal

Unificar el **dispatch de mensajes entre agentes SWARMIND** en un kernel
determinista (single-loop, FIFO por cola, sin spawneos por mensaje). Aplica
mismo patrón para la cola de tareas, los handlers CLI y bus, el event store
local y el regrant de `bounded-queue-mailbox`. Se aplica también como **patrón
de supervisión de agentes** (SWARMIND `orchestrator/agent_*` ya ocupa el rol
correspondiente pero sin kernel formal).

La idea es que **cualquier sistema con cola y línea de comunicación** (CQE es
solo un cliente de SWARMIND) se beneficie del mismo patrón de kernel; SWARMIND
debe adoptarlo en su propio orchestrator antes de proponerlo a terceros.

## 2. Estado del arte verificado (2025-2026)

### 2.1 NautilusTrader — el referente de kernel event-driven

- `NautilusKernel` es el **único** límite de ciclo de vida: inicializa
  cache/portfolio/engines/trader/clock/bus y decide el clock por entorno.
  Backtest/sandbox/live comparten el mismo struct `nautilus-system`.
  [docs.nautilustrader.io/concepts/architecture]
- **Core default single-threaded**: consume y dispatch del mismo hilo, con red
  y adapters en Tokio aparte. [docs.nautilustrader.io/concepts/architecture]
- **Bus síncrono por prioridad y tipo**, dos planos: ruteo *typed* (buffer de
  64 handlers) y *any routing* (`&dyn Any`); **thread-local por runtime**.
- **Ruteo por topics**: `AHashSet<Subscription>` + matching con glob; cache
  del match (sin recompute por publish). Prefijo de topic `data.quotes.BINANCE.`.
- **Req/resp correlacionado**: `correlation_index: AHashMap<UUID4, Handler>`.
- **Principios declarados** (Reliability > Performance > Modularidad >
  Testabilidad); **fail-fast** (error/panic, no valor inválido silencioso);
  **mensajes inmutables** (contrato de replay); CI ejecuta unit+PBT+fuzz.
  [docs.nautilustrader.io/design_principles]
- **Event store**: captura en el boundary de dispatch (antes de handlers), `seq`
  por writer thread sobre canal **bounded**; al exceder `halt_threshold`
  dispara **fail-stop** (no descarta).
- **DST para determinismo**: sustituyen Tokio por **madsim** bajo `cfg(madsim)`,
  `IndexMap` en lugar de hashes aleatorios, `select!{ biased; }`, y clock en seam.
  Mismo seed → misma ejecución.
- **Cache es proyección write-through, no fuente de verdad.** Lock-free NO es el
  objetivo; en core single-writer el `&mut` del hilo da el orden total barato.

### 2.2 Actores en Rust

| Librería | Supervisión | Mailbox bounded |
|---|---|---|
| **ractor 0.16.5** | dentro de `ractor-supervisor` (OneForOne/OneForAll/RestForOne + `max_restarts`) | sí |
| **kameo 0.22.2** | **RestartPolicy** + strategy + limit n/window | sí, con backpressure |
| **spawned 2026** | supervision trees SOLO en roadmap | sí |
| **actix 0.13.5** | no-OTP | bounded, 16 por defecto |
| **coerce 0.8.11** | event sourcing/clustering | sí, 6.1 % docs |

`panic='abort'` desactiva la captura de supervisión (ractor): los panics matan
el proceso. Para supervisión I/O se necesita `'unwind'` y para el kernel `'abort'`.

### 2.3 Estrategia de supervisión por responsabilidad

| Componente | Estrategia |
|---|---|
| Kernel en sí (loop) | sin supervisión OTP (determinista, crash-only, replay) |
| Agents I/O | `OneForOne` (uno caído no tumba el resto) |
| Chains secuenciales (A → B → C) | `RestForOne` (respeta dependencia topológica) |
| `OneForAll` | **NO** en kernel: reinicia componentes sanos y rompe orden canónico |

## 3. Criterios de aceptación para SWARMIND

| Crit | Requisito | Estado / evidencia |
|---|---|---|
| AC-KN1 | SWARMIND `harness/orchestrator/**` formaliza su kernel actual en un solo loop determinista (cada agente como actor, mensajes como payload, cola FIFO por handler). | **Cumplido**: `harness/kernel/loop.py` (`KernelLoop`) + `KernelBus` en `harness/orchestrator/agent_bus/kernel_bus.py` (subscribe/publish/drain). |
| AC-KN2 | Handlers no hace `spawn()` por mensaje (patrón fail-fast de kernel single-loop). Se acepta `spawn` solo si declara servicios I/O (con su propia cola). | **Cumplido**: `KernelLoop.run()` consume el buzón en el hilo llamador; `test_kernel.py` prueba orden FIFO sin procesos. |
| AC-KN3 | Cabecera de mensaje **inmutable**: SWARMIND conserva el rastro de cada envío/mensaje en el event store basado en la serie `swarmind::msg::{ts, seq, kind, trace_id, payload}`. | **Cumplido**: `MessageEnvelope` frozen + `MappingProxyType`, `EventLog.append/replay` (`seq/kind/payload/trace_id/source/created_at`). |
| AC-KN4 | `bounded-queue-mailbox`: la esfera de entrada tiene capacidad limitada con backpressure real. Nada se descarta silenciosamente; cuando se retrase y `halt_threshold` se cumpla, el system aborta. | **Cumplido**: `BoundedMailbox.put` → `MailboxFullError` tipado; el mensaje rechazado no consume `seq` ni entra al log. |
| AC-KN5 | SWARMIND `run_commands` y `agent dispatcher` integran el modelo con *trace_id* correlacionado para req/resp y timeouts con clases de error What/Why/Where. | **Cumplido**: `RequestTracker` (`harness/orchestrator/request_tracker.py`) correlaciona req/resp por `trace_id` con timeout tipado y reloj inyectable; `AgentDispatcher.dispatch` publica `agent.dispatch` y devuelve `trace_id`; `run_command` emite `command.start/end/error` con el mismo `trace`. |
| AC-KN6 | Determinismo: runs aceptan `seed` y reproduccen el misma secuencia (azim no requiere madsim, solo el schema de task_queue). | **Cumplido para el kernel**: secuencia canónica = `seq` monotónica + FIFO; `replay()` reconstruye el orden exacto. |
| AC-KN7 | En CQE-style restructuración, el patrón se aplica desde SWARMIND a kernels de terceros (por ejemplo CQE Ola 4.5), pero con kernel SWARMIND como componente de supervisión; el patrón de kernel es el mismo. | **Habilitado**: kernel agnóstico del dominio (0 imports de agentes/tools); CQE lo consume como cliente, no como comparación. |

## 4. Referencias

- [docs.nautilustrader.io/concepts/architecture](https://nautilustrader.io/docs/latest/concepts/architecture/)
- [docs.nautilustrader.io/concepts/message_bus](https://nautilustrader.io/docs/latest/concepts/message_bus/)
- [docs.nautilustrader.io/concepts/event_sourcing](https://nautilustrader.io/docs/latest/concepts/event_sourcing/)
- [docs.nautilustrader.io/concepts/dst](https://nautilustrader.io/docs/latest/concepts/dst/)
- [docs.rs/ractor-supervisor](https://docs.rs/ractor-supervisor/latest/ractor_supervisor/supervisor.rs.html)
- [docs.rs/kameo/supervision](https://docs.rs/kameo/latest/kameo/supervision/index.html)
- [github.com/actix/actix master/src/mailbox.rs](https://raw.githubusercontent.com/actix/actix/master/actix/src/mailbox.rs)
- [lambdaclass/spawned README](https://raw.githubusercontent.com/lambdaclass/spawned/main/README.md)
