# FDD — capa de entrega por feature (SWARMIND)

Esta carpeta es la **capa de entrega** de los principios universales
(`DOM`, `FIC`, `HIT`, `FRC`, `OWN`, `DEC`). No reemplaza el N1: lo
operacionaliza para que una sesión nueva pueda retomar el trabajo sin el chat.

## Artefactos

| Archivo | Rol | Se actualiza |
|---|---|---|
| `docs/fdd/dominio.md` | Mapa de dominio vivo (entidades, agregados, lenguaje ubicuo) | con cada feature que toca el dominio |
| `docs/fdd/ficha-template.md` | Plantilla de ficha por feature | al crear una feature |
| `docs/fdd/features/<slug>.md` | Ficha concreta de la feature | en cada hito, no en cada herramienta |
| `docs/fdd/estado.md` | Estado para retomar (olas, hechos, pendientes) | al cerrar cada ola |

Una ficha se crea solo cuando la feature lo amerita. Un bug puntual se resuelve
con fix + test de regresión; una migración irreversible exige spec + ADR +
rollback además de la ficha.

## Flujo

1. **Objetivo** → se descompone en features con nombre de resultado.
2. **Ficha** → objetivo, alcance, criterios demostrables, dominio, archivos con
   dueño, decisiones, evidencia y próximo paso.
3. **Olas** → solo la próxima se detalla del todo; cada ola entrega algo usable
   de punta a punta y termina con un criterio observable.
4. **Hitos** → `diseñado → implementado → verificado → integrado`.
   *Integrado* lo marca una persona, nunca el agente.
5. **Cierre** → evidencia observada + revisión + nota de estado. Afirmar sin
   evidencia cuenta como no hecho.

## Selección de metodología («-DD»)

| Requisito | Enfoque | Artefacto mínimo |
|---|---|---|
| Feature de usuario con valor | FDD | ficha + criterios demostrables |
| Dominio con reglas complejas | DDD | `dominio.md` (entidades, agregados, lenguaje ubicuo) |
| API pública o contrato entre servicios | CDD/SDD | OpenAPI/AsyncAPI + spec del cambio |
| Cambio de comportamiento | TDD/ATDD | test rojo con criterio de aceptación |
| Comportamiento de negocio acordado | BDD | escenario condición→acción→resultado |
| Migración irreversible o de datos | SDD | spec + ADR + rollback |
| Librería, SDK o CLI pública | RDD | README de uso antes del código |
| Bug puntual | Fix + regresión | test que reproduce + fix |
| Cambio visual | Maqueta + BDD | recorrido con estados + escenario |
| Infraestructura interna | FDD (ola 0) | ficha/tarea con criterio observable |

La fricción crece con el costo de equivocarse, no con el gusto del agente.

## Constitución y arquitectura

Nada se sale de la constitución ni de la arquitectura, por chico que sea el
cambio. Las reglas viven en `.opencode/core/base_principles.md` (N1/N2) y el
detalle en `_full.md` (N3). Las decisiones cerradas de una feature se anotan en
su ficha (`DEC`); las decisiones de arquitectura del proyecto, en un ADR.

## Verificación

La capa está protegida por `harness/tests/test_principles_fdd.py`:

- N1 con los 6 códigos y presupuesto ≤60 líneas;
- taxonomía biyectiva con el N1;
- artefactos FDD presentes y ficha con los 4 hitos;
- guard de duplicados O(n) equivalente al oráculo O(n²).
