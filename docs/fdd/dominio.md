# Mapa de dominio (plantilla viva)

> Copiar a `docs/fdd/dominio.md` en el proyecto destino y mantenerlo vivo.
> Crece con cada feature; no se hace un relevamiento aparte. Si una entidad no
> aparece aquí, la sesión nueva no la conoce sin explorar el repo.

## Lenguaje ubicuo

| Término | Significado en este proyecto | No confundir con |
|---|---|---|
| `<término>` | `<definición de negocio, no técnica>` | `<término parecido>` |

## Entidades y agregados

| Entidad / agregado | Dueño (bounded context) | Dónde vive | Invariantes |
|---|---|---|---|
| `<Entidad>` | `<contexto>` | `<ruta/módulo>` | `<regla que nunca se rompe>` |

## Flujos de dominio

| Flujo | Entrada | Resultado observable | Entidades que toca |
|---|---|---|---|
| `<verbo + objeto>` | `<evento/acción>` | `<lo que ve la persona>` | `<entidades>` |

## Límites (bounded contexts)

| Contexto | Responsabilidad | Contratos con otros contextos |
|---|---|---|
| `<contexto>` | `<qué decide>` | `<evento/API/esquema>` |

## Decisiones de dominio cerradas

| Tema | Decisión | Por qué | Fecha |
|---|---|---|---|
| `<tema>` | `<decisión>` | `<evidencia o motivo>` | `<AAAA-MM-DD>` |

## Registro de cambios

| Fecha | Feature | Qué cambió en el mapa |
|---|---|---|
| `<AAAA-MM-DD>` | `<ficha>` | `<entidad/flujo agregado o corregido>` |
