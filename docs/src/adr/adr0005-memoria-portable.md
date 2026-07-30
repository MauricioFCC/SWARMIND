# ADR-0005: Memoria Portable — Paths Universales

## Estado
**FUSIONADO** — Contenido integrado en ADR-0033.

## Contenido Original
Este ADR documentaba la creacion de `_resolve_hermes_root()` para eliminar paths absolutos del sistema.

**Decisión original:** Crear funcion con 3 niveles de fallback:
1. `HERMES_ROOT` env var
2. `~/Documents/Hermes_Memory_Proyects/`
3. `~/Documents/AGENTIC_MEMORY/` (auto-creado)

**Resultado original:**
- Funciona desde cualquier usuario/maquina
- Sin paths absolutos en configuracion

## Contenido Fusionado En
[ADR-0033: Federated Vector Search + SQLite-vec](adr0033-federated-vector-sqlite-2026.md)

El contenido fue integrado en ADR-0033 como parte de la capa de memoria portable, ahora expandido con soporte para SQLite-vec como backend edge.
