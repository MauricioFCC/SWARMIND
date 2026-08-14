---
name: diagram-design
domain: frontend
description: "Usar cuando el usuario pide un diagrama visual editorial. arquitectura, flowchart, sequence, state machine, ER, timeline, swimlane, quadrant, radar, org chart, mermaid, drawio, SVG, diagrama. | UPG·NAM·FRS (reglas en base_principles.md)"
license: MIT
version: 1.0.0
project_agnostic: true
---

# Diagram-design (min)

## Responsabilidades
- Generar diagramas editoriales autocontenidos (HTML + inline SVG + CSS, sin dependencias externas)
- Seleccionar el tipo visual correcto segun el mensaje: flujo, estado, datos, jerarquia, comparacion, proceso
- Aplicar design system editorial: paleta de marca, tipografia, grid 4px, densidad 4/10
- Seguir primitivas SVG: markers de flecha, conectores obligatorios, labels con margen, leyenda
- Redibujar .drawio/.mmd existentes a tamano/detalle elegido (scripts drawio_extract/mermaid_extract)
- Importar tokens de marca desde URL/skill/carpeta (onboarding.md) y generar PNG/SVG

## Comandos
- `!diagram <tipo> <descripcion>` — Genera diagrama del tipo indicado
- `!diagram import <file.drawio|file.mmd>` — Redibuja desde fuente externa
- `!diagram export <file.html> [--png]` — Exporta a SVG/PNG
- `!diagram onboard <url|folder>` — Extrae tokens de marca al style-guide
- `!diagram check` — Self-check de calidad (self_check.py)

## Referencias
- `references/style-guide.md` — Design tokens (customizar antes del primer uso)
- `references/type-*.md` — 27 especificaciones de tipos visuales
- `references/semantic-patterns.md` — Patrones de comportamiento
- `references/output-spec.md` — Especificacion de salida
- `references/onboarding.md` — Onboarding de marca
