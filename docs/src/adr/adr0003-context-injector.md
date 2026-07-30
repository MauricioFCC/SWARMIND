# ADR-0003: Context Injector — Estándares en Cada Subtarea

## Estado
**FUSIONADO** — Contenido integrado en ADR-0001 §4.

## Contenido Original
Este ADR documentaba la creacion de `ContextInjector` que inyecta un recordatorio ultra-compacto (~23 tokens, ~92 chars) en CADA subtarea, no solo al inicio.

**Decisión original:** Crear ContextInjector que inyecta un recordatorio ultra-compacto de estandares de calidad en cada subtarea para evitar que el LLM pierda el contexto durante sesiones largas.

**Formato original:**
```
[F]CleanCode+DRY+KISS+SSOT+<900LC+Patrones+CompRoot+Resiliencia+DoD+DocStringsES+tests>80+Seg
```

**Resultado original:** 23 tokens vs 400 tokens de preambulo ahorrados por sesion.

## Contenido Fusionado En
[ADR-0001 §4: Memoria de Estándares](adr0001-mejoras.md#4-memoria-de-estandares-contextinjector)

El contenido completo fue integrado en ADR-0001 junto con la evolucion a ContextInjector que ahora maneja estandares por rol (builder, scientist, guardian).
