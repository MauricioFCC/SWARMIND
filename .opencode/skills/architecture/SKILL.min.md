---
name: architecture
domain: architecture
description: "Usar cuando se disena o evalúa la arquitectura de un sistema. GoF, clean architecture, hexagonal, DDD, C4, SOLID, decisiones arquitectonicas, diagramas, patrones. | UPG·NAM·FRS (reglas en base_principles.md)"
license: MIT
version: 1.0.0
project_agnostic: true
---

# Architecture (min)

## Responsabilidades
- Disenar arquitectura hexagonal, clean architecture o DDD segun contexto
- Aplicar principios SOLID, patrones GoF (23 clasicos) y GRASP
- Documentar decisiones con ADRs y visualizar con C4 model (structurizr)
- Definir fitness functions arquitectonicas y validarlas en CI
- Gobernar dependencias entre modulos, evitar acoplamiento ciclico

## Comandos
- `!arch analyze <path>` — Analiza estructura del proyecto
- `!arch diagram` — Genera diagrama C4 del sistema
- `!arch violations` — Lista violaciones arquitectonicas
- `!arch adr new/list/show` — Gestion de ADRs
- `!arch pattern suggest <problem>` — Sugiere patron arquitectonico
