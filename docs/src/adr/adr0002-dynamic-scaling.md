# ADR-0002: Dynamic Scaling — Cuadrilla que Crece Segun el Trabajo

## Estado
**FUSIONADO** — Contenido integrado en ADR-0001 §3.

## Contenido Original
Este ADR documentaba la creacion de `ScopeAnalyzer` para escalar dinamicamente el numero de agentes segun la complejidad de la tarea.

**Decisión original:** Crear ScopeAnalyzer que analiza el mensaje y determina cuantos agentes lanzar basado en keywords de alcance (simple, sistema, enterprise, microservicios, etc.).

**Detalle técnico original:**
- Archivo: `harness/orchestrator/scope_analyzer.py` (320 lines)
- Clase `ScopeAnalyzer` con metodo `analyze(message) -> ScopeEstimate`
- 4 niveles: small (1b+1g), medium (2b+1g+sci), large (3b+2g+sci+bug), xlarge (5b+3g+sci+bug)
- Se integra en `TaskPlanner.decompose()` cuando el template es `swarm_default`

## Contenido Fusionado En
[ADR-0001 §3: Escalado Dinámico](adr0001-mejoras.md#3-escalado-dinamico-dynamic-scaling)

El contenido completo de este ADR fue integrado directamente en la seccion de Escalado Dinamico de ADR-0001, incluyendo la tabla de niveles con conteo de agentes.
