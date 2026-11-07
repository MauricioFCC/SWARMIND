# Spec — SWARMIND como instrumento de reestructuración (harness genérico / ejemplo CQE)

> Estado: proposed — Dueño: harness/orchestrator + builder — Frontera: 2026-10-30.
> Scope: SWARMIND como **sistema harness** que orquesta el refactor en repos de
> clientes externos, sin necesidad de seguir el estilístico de un dominio
> concreto (CQE es un ejemplo y no un referente de comparación). El punto
> común es el patrón: un repo con tests y ratchet de deuda que se quiere
> reestructurar con gates automáticos y sin romper tests.

## 1. Proposal

Caso de ejemplo: el cliente `core-quant-engine` (CQE) (monolito con ~250.000
LOC en `src/domain/**`, 6.9k tests) se reestructura vía strangler-fig en un
workspace multi-crate, con kernel event-driven y actores. Esta es una lista
**genérica** de pasos que SWARMIND puede ejecutar por su propia orquestación:
el patrón valdría para cualquier repo Rust/Python/JS con tests de coverage
comparables.

Premisas verificadas:
- *El strangler-fig en Rust es un patrón estable de multi-crate* (ruff, bevy,
  polars entre referentes) [matklad.github.io]().
- SDD: GitHub Spec Kit (sep-2025), "markdown as a programming language"
  [github.com/blog/ai-and-ml/generative-ai/yyy]().
- Límite académico: pocas herramientas académicas y sin métricas
  [doi:10.1016/j.infsof.2024.107590]() (→ la responsabilidad queda en el harness).

## 2. SWARMIND como harness de reestructuración

Lo que SWARMIND orquesta, desde el harness y con agentes:

| Capacidad | Por qué SWARMIND | Evidencia |
|---|---|---|
| **Inventario de módulos + hotspot** | análisis de complejidad (asignaciones SCC, detección de O(n²) por patrón durante el scan) | scripts/ |
| **Administración de repositorio** (clone/branch/sync) | CLI `bash`, `python -c`, `git` | estándar harness |
| **Specs de frontera** | 37-45 (por repos). El *frontier* o una spec por-wave se escribe con orden determinista | docs/specs (regla RSF) |
| **Agentes builder** | implementación de `cqe-*` por ola | agents/builder |
| **Guardian** | verificación de que tests y gates del cliente no rompen | agents/guardian |
| **Researcher, arch / review** | SDD y revisión por rol | agents/architect, agents/reviewer |
| **Orquestado** | cada ola → 1 PR, chain de approve | orchestrator/agent_dispatcher |
| **Aprendizaje continuo** | logs.CQE / guardian de pre-fix | evolve_loop |

### 2.1 CQE como ejemplo de cliente, no patrón

CQE cuenta con su propio informe de arquitectura y olas definidas (6 olas,
teoría de strangler-fig y target de crates `cqe-*`). El harness debe ser
**agnóstico del dominio**: un repo Node.js o de Python puede también
solicitar extracción (var benchmark / coverage / gate).

Este spec inspira el patrón pero **el dominio no es SWARMIND**: no habla de
trading ni de actores para terceros. Habla de SWARMIND como orquestador
multi-agente.

## 3. Criterios de aceptación

| Crit | Requisito |
|---|---|
| AC-HR1 | **SWARMIND inventario** es reversible: se puede aplicar a repo Python sin deploy de módulos extra. |
| AC-HR2 | El *setup de repos* se automatiza con un agente builder + guardian (además de standard). Ejemplo: el paso `ola-0` de CQE (setup de crates `cqe-*`). |
| AC-HR3 | Cada **gate por proyecto** queda documentado en docs (specs del repo cliente, no del harness). |
| AC-HR4 | Una ola se ejecuta por proyecto-composición: cada PR es un PR del repo cliente, no del harness. |
| AC-HR5 | El harness no debe suponer que el cliente sigue un estilo en particular. |
| AC-HR6 | El harness no debe suponer un dominio concreto (trading). |

## 4. Referencias (resumen)

- [matklad.github.io](https://matklad.github.io/2021/08/22/large-rust-workspaces.html) (Large Rust Workspaces).
- [github.com/zenide/cargo-crate-split](https://github.com/zenide/cargo-crate-split) (may-2026).
- [martinfowler.com/bliki/StranglerFigApplication.html](https://martinfowler.com/bliki/StranglerFigApplication.html).
- [github.com/blog/ai-and-ml/spec-driven-development-using-markdown-as-a-programming-language](https://github.blog/ai-and-ml/generative-ai/spec-driven-development-using-markdown-as-a-programming-language-when-building-with-ai/).
- [developer.microsoft.com/blog/spec-driven-development-spec-kit](https://developer.microsoft.com/blog/spec-driven-development-spec-kit/).
- [doi:10.1016/j.infsof.2024.107590](https://doi.org/10.1016/j.infsof.2024.107590) — límite académico.
