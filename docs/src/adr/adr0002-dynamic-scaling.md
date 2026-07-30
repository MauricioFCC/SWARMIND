# ADR-0002: Dynamic Scaling — Cuadrilla que Crece Segun el Trabajo

## Estado
ACEPTADO — Implementado en commit 908935a.

## Contexto
El sistema tenia templates fijos con numero constante de agentes (siempre 3 builders, 2 guardians). Esto desperdiciaba tokens en tareas pequeñas y se quedaba corto en tareas grandes.

## Decision
Crear ScopeAnalyzer que analiza el mensaje y determina cuantos agentes lanzar basado en keywords de alcance (simple, sistema, enterprise, microservicios, etc.).

## Detalle Tecnico
- archivo: harness/orchestrator/scope_analyzer.py (320 lines)
- Clase ScopeAnalyzer con metodo analyze(message) -> ScopeEstimate
- 4 niveles: small (1b+1g), medium (2b+1g+sci), large (3b+2g+sci+bug), xlarge (5b+3g+sci+bug)
- Se integra en TaskPlanner.decompose() cuando el template es swarm_default

> **DEPRECADO** — Este ADR ha sido integrado en ADRs posteriores.
> - Contenido de este ADR ahora forma parte de [ADR-0001](adr0001-mejoras.md) (Fundacion)
> - Ver [SUMMARY.md](../SUMMARY.md) para la estructura actualizada de ADRs.

## Deprecacion
**Fecha:** Julio 2026
**Razon:** Compactacion de ADRs para eliminar fragmentacion.
**Reemplazado por:** ADR-0001 (Fundacion del Sistema)
