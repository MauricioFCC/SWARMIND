# Spec — Kernel event-driven (NautilusTrader) + actores ractor/kameo

> Estado: proposed — Dueño: harness (docs/specs) — Frontera: 2026-10-30.
> Scope: módulo del kernel del patrón NautilusTrader aplicado a SWARMIND
> y a la bmw reconstrucción de CQE. Spec generado tras 2 horizontes de research
> (sesiones desde CQE + esto desde SWARMIND).

## 1. Proposal

Formalizar en SWARMIND un módulo de **kernel event-driven** para el motor
resultante (CQE Ola 3/4): un kernel canónico con MessageBus, Cache, DataEngine
y ExecutionEngine en single-loop determinista (sin ractor-supervision en el core) y
actores supervisados para la periferia I/O. Aplicable también como patrón de
supervisión de SWARMIND (todos los agentes con su cola).

## 2. Estado del arte verificado (2025-2026)

### 2.1 NautilusTrader

- `NautilusKernel` es el único límite de ciclo de vida: inicializa
  cache/portfolio/engines/trader/clock/bus y decide el clock por entorno.
  **Backtest, sandbox y live comparten el mismo struct `nautilus-system`**.
  [docs.nautilustrader.io/concepts/architecture]
- **Default del core: single-threaded.** Consume y dispatch desde el mismo hilo;
  red y adapters marchan en Tokio aparte.
- **Bus síncrono por prioridad y tipo**. Dos planos: ruteo *typed*
  (`subscribe_quotes`, `publish_quote`, sin type-check, buffer interno de 64
  handlers) y *any routing* (`&dyn Any`) para custom/Python. Storage **thread-local
  por runtime** (un bus por hilo, cero sincronización).
- **Routing por topics**: `AHashSet<Subscription>` + `is_matching_backtracking`
  (glob `*`/`?`, doble puntero greedy O(n+m)); **cachea** el match (no descarta
  el recalculo de la tabla). Los topics usan `data.quotes.BINANCE.BTCUSDT.`
  path con prioridad; no mejora a O(log n).
- **Req/resp correlacionado**: `correlation_index: AHashMap<UUID4, TypedHandler<...>>`
  (respuestas entregadas por *correlation_id*, no por `data.response` / topic).
- **Principios declarados** (fuente design_principles): Reliability >
  Performance > Modularity > Testability; **fail-fast** (panic, no valor
  inválido silencioso); **mensajes inmutables** (contrato de replay); CI ejecuta
  unit + PBT + fuzz + static asserts; **crash-only** (recovery por replay de
  estado, no rollback ad-hoc). Resumen en [docs.nautilustrader.io/concepts/architecture]().
- **Event store**: captura **en el boundary de dispatch** antes de los handlers,
  `seq` asignado en un writer thread sobre canal **bounded**; ante backpressure >
  `halt_threshold` dispara **fail-stop** (no descarta).
  [docs.nautilustrader.io/concepts/event_sourcing]().
- **DST para determinismo**: sustituyen Tokio por **`madsim`** bajo `cfg(madsim)`,
  `IndexMap` en lugar de hashes aleatorios, `select!{ biased; }` y un `clock` seam.
  Mismo seed + binario → misma ejecución. [docs.nautilustrader.io/concepts/dst]().
- **Cache** es proyección write-through, no fuente de verdad. **Lock-free NO es el
  objetivo**; en un core single-writer el `&mut` del hilo da el orden total barato.

### 2.2 Ractor y actores en Rust

| Librería | Versión | Supervisión | Mailbox bounded |
|---|---|---|---|
| **ractor 0.16.5** | 12-oct-2026, MSRV 1.85 | fuera del core (crate `ractor-supervisor`: OneForOne / OneForAll / RestForOne + `max_restarts_ resets/duration` y **meltdown**) | sí, solo primitives `mpsc_bounded` |
| **kameo 0.22.2** | 28-sep-2026 | **RestartPolicy** + Estrategia + restart_limit(n, window) | sí, bounded con backpressure |
| **spawned 2026** | LambdaClass; production en ethrex/ethlambda | trees SOLO en roadmap | sí |
| **actix 0.13.5** | jul-2025 | supervision no-OTP | bounded, 16 por defecto |
| **coerce 0.8.11** | 2026 | tracing/event sourcing | sí, clustering — buggy: solo 6.1 % doc |

`panic = 'abort'` en el repositorio es compatible con crash-only pero **deshabilita
la captura de supervisión de ractor**: los panics matan el proceso, no devuelven
`Err`. Si se quiere supervisión de un actor I/O se debe declarar `panic='unwind'`
**solo para crates I/O** y dejar `'abort'` para el kernel.

### 2.3 Estrategia de supervisión por responsabilidad

| Actor o kernel | Estrategia |
|---|---|
| Kernel CQE | sin supervisión OTP (loop determinista, crash-only, replay) |
| Actors I/O | `OneForOne` (un feed caído no tumba el resto) |
| Chains ordenadas (feed → publisher) | `RestForOne` (respeta dependency topológica) |
| `OneForAll` | **NO** en el kernel: reinicia componentes sanos y rompe el orden de eventos |

## 3. Criterios de aceptación

| Crit | Requisito |
|---|---|
| AC-KN1 | Módulo/kernel va como crate `cqe-kernel`: MessageBus (pub/sub por topic + req/resp + comandos), Cache (proyección write-through), DataEngine, ExecutionEngine, RiskEngine, Portfolio, SupervisionTree. |
| AC-KN2 | `crates/cqe-kernel/**` sin imports de adapters (compile-check). |
| AC-KN3 | Orden canónico determinista_verificado con DST (madsim): mismo seed + binario + config → misma schedule y mismo output. |
| AC-KN4 | `Backtest == Live` por inyección de `Clock` y clients (mismo `ExecutionEngine`). |
| AC-KN5 | `Backpressure` real: bounded MPSC en adapters; sink stall (no drop) hasta que el kernel tenga `halt_threshold`, sin descartes en silencio. |
| AC-KN6 | Supervision tree solo para I/O, ractor con feature `otp` (`unwind`) y kernel con `panic='abort'`. |
| AC-KN7 | Gate de complejidad (_invariantes del kernel de benchmark_), bancada en `Ir` por N/2N/4N: ratio < 2.4 para O(n). |
| AC-KN8 | 0fix battery (`cargo test --lib --doc`, `cargo clippy --lib --docs`), `cargo fmt --check`, 7.5k tests, 0 failed. |

## 4. Referencias (resumen)

- [docs.nautilustrader.io/concepts/architecture](https://nautilustrader.io/docs/latest/concepts/architecture/)
- [docs.nautilustrader.io/concepts/message_bus](https://nautilustrader.io/docs/latest/concepts/message_bus/)
- [docs.nautilustrader.io/concepts/event_sourcing](https://nautilustrader.io/docs/latest/concepts/event_sourcing/)
- [docs.nautilustrader.io/concepts/dst](https://nautilustrader.io/docs/latest/concepts/dst/)
- [docs.rs/ractor-supervisor](https://docs.rs/ractor-supervisor/latest/ractor_supervisor/supervisor.rs.html)
- [docs.rs/kameo/supervision](https://docs.rs/kameo/latest/kameo/supervision/index.html)
- [github.com/actix/actix master/src/mailbox.rs](https://raw.githubusercontent.com/actix/actix/master/actix/src/mailbox.rs)
- [lambdaclass/spawned README](https://raw.githubusercontent.com/lambdaclass/spawned/main/README.md)
