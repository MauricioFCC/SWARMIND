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
