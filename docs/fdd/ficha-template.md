# <acción + resultado + objeto>

Hito: diseñado | implementado | verificado | integrado
Pendiente: <enlace a la lista de trabajo existente>

> Copiar a `docs/fdd/features/<slug>.md`. No copiar código, firmas ni
> pseudocódigo: apuntar al repo. La ficha guarda lo que el código no dice.

## Objetivo

Qué cambia para la persona y por qué.

## Alcance

Qué incluye y qué queda fuera.

## Criterios y demostración

| # | Condición | Acción | Resultado observable | Evidencia |
|---|---|---|---|---|
| 1 | `<estado inicial>` | `<acción>` | `<lo que ve la persona>` | `<test/log/medición>` |

Un adjetivo («seguro», «rápido», «usable») no es criterio: se convierte a
condición → acción → resultado antes de diseñar, o se pregunta.

## Dominio, constitución y arquitectura

Entidades y flujos de `docs/fdd/dominio.md` que toca, reglas de la constitución
que la afectan y partes de la arquitectura que reusa. Si cambia alguna, qué
cambia.

## Archivos y dueños

| Archivo | Dueño (sesión/frente) |
|---|---|
| `<ruta>` | `<dueño>` |

Nadie más edita un archivo mientras la ficha esté abierta.

## Efectos compartidos

Contratos, formatos, hashes sellados, pruebas medidas, pines y esquemas
compartidos que el cambio mueve: quién los actualiza y cuándo.

## Olas

| Ola | Termina con (criterio observable) | Pruebas que la cierran | Depende de | Estado |
|---|---|---|---|---|
| 1 | `<resultado usable>` | `<tests>` | `<nada>` | `<pendiente>` |

## Decisiones y preguntas HITL

| Tema | Decisión | Por qué |
|---|---|---|
| `<tema>` | `<decisión cerrada>` | `<evidencia>` |

Preguntas que esperan a la persona: qué se preguntó, con qué opciones, qué
tarea frenó y con qué se siguió mientras tanto.

## Evidencia

Qué pasó, qué falló y qué no se corrió, con la condición en que se midió y los
commits. Lo citado no se borra al limpiar temporales.

## Próximo paso

Una acción concreta para quien retome.
