# ADR-0005: Memoria Portable — Paths Universales

## Estado
**ACEPTADO** — Implementado en commit cebe7be.

## Contexto
El sistema tenia paths absolutos (C:\Users\USUARIO\...) que rompian al cambiar de maquina o usuario.

## Decision
Crear _resolve_hermes_root() con 3 niveles de fallback:
1. HERMES_ROOT env var
2. ~/Documents/Hermes_Memory_Proyects/
3. ~/Documents/AGENTIC_MEMORY/ (auto-creado)

## Resultado
- Funciona desde cualquier usuario/maquina
- Sin paths absolutos en configuracion

> **DEPRECADO** — Este ADR ha sido integrado en ADRs posteriores.
> - Contenido de este ADR ahora forma parte de [ADR-0001](adr0001-mejoras.md) (Fundacion)
> - Ver [SUMMARY.md](../SUMMARY.md) para la estructura actualizada de ADRs.

## Deprecacion
**Fecha:** Julio 2026
**Razon:** Compactacion de ADRs para eliminar fragmentacion.
**Reemplazado por:** ADR-0001 (Fundacion del Sistema)
