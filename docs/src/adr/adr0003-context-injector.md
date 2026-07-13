# ADR-0003: Context Injector — Estandares en Cada Subtarea

## Estado
ACEPTADO — Implementado en commit aef61d3.

## Contexto
Durante sesiones largas de refactorizacion, el LLM pierde los estandares de calidad porque el contexto se llena de codigo. El usuario tenia que repetir un preambulo de ~400 tokens en cada mensaje.

## Decision
Crear ContextInjector que inyecta un recordatorio ultra-compacto (~23 tokens, ~92 chars) en CADA subtarea, no solo al inicio.

## Formato
[F]CleanCode+DRY+KISS+SSOT+<900LC+Patrones+CompRoot+Resiliencia+DoD+DocStringsES+tests>80+Seg

## Resultado
- 351 tests pasando
- 0 necesidad de preambulo
- 23 tokens vs 400 tokens ahorrados por sesion
