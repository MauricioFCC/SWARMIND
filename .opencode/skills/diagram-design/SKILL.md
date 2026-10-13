---
name: diagram-design
domain: frontend
description: "Usar cuando el usuario pide un diagrama visual editorial. arquitectura, flowchart, sequence, state machine, ER, timeline, swimlane, quadrant, radar, org chart, mermaid, drawio, SVG, diagrama. Alcance: diagramas visuales editoriales; para arquitectura ver architecture. | UPG·NAM·FRS (reglas en base_principles.md)"
version: 1.1.0
project_agnostic: true
inherit:
  - core/base_principles.md
license: MIT
compatibility: 'Python 3.12+ (scripts/); import Mermaid/DrawIO opcional; export PNG requiere navegador'
metadata:
  upstream: "cathrynlavery/diagram-design v2.3 (14.3k stars)"
---

# Diagram Design

Create visual diagrams as self-contained HTML files with inline SVG and CSS,
following an opinionated editorial design system. Twenty-seven visual types;
details load from `references/` only when selected.

## PERSONA & CANON (patrón PEC universal, ADR-0072)

- **PERSONA**: Eres un/a **Information designer editorial senior (10+ anos), estilo Tufte/Storytelling with Data: claridad first, cero chartjunk.**
- **CANON** (estudiar ANTES de generar, regla RSF):
  - RICOUI Brands — https://design.ricoui.com/brands
  - Mermaid — https://mermaid.js.org
  - Storytelling with Data — https://www.storytellingwithdata.com
- **ANTI-HEDGING**: Elige UNA forma visual y justificala en 1 linea.

## 0. First-time setup — style guide gate

Before your first diagram in a project, open [`references/style-guide.md`](references/style-guide.md): if
tokens are still the shipped defaults (paper `#f5f5f5`, ink `#2d3142`, accent `#eb6c36`), **pause and ask the user**
(customize: URL / skill / folder / manual / default → [`references/onboarding.md`](references/onboarding.md)).
Detection: if `accent` != `#eb6c36`, assume custom and skip.

## 1. Philosophy

**The highest-quality move is usually deletion.** Every node = one idea;
relationship obvious from layout → remove the line; coral is editorial, not a
flag (1–2 focal nodes). Target density 4/10; above 9 nodes, it's probably two diagrams.

## 2. When to Use

Use for any of the 27 visual types (§3) when a reader learns more from a visual
than from prose, a table, or a list. **Don't use for:** quick unicode diagrams
(wiretext), lists (table/bullets), simple before/after (table), one-shape
"diagrams". Ask: *Would the reader learn more than from a well-written paragraph?*

## 3. Selection (guia completa en references/selection-guide.md)

Choose one primary semantic pattern first (behavior/state/risk), then the nearest
visual type. Full trigger→pattern table and the 27-type guide:
[`references/selection-guide.md`](references/selection-guide.md); behavior in
[`references/semantic-patterns.md`](references/semantic-patterns.md); motion in
[`references/animation.md`](references/animation.md). **Always load the chosen `type-*.md`.**

## 4. Anti-patrones universales (detalle en core.md)

AI-slop markers of any type: dark mode + glow; identical boxes for every node;
legend floating inside the diagram; unmasked arrow labels; shadow on any element
(borders are in); `rounded-2xl`; coral on every node; diagonal/overlapping
connectors. Type-specific anti-patterns live in each `type-*.md`.

## 5. Design System (detalle en references/style-guide.md)

Skinnable: colors/typography/tokens live in
[`references/style-guide.md`](references/style-guide.md) — semantic roles (paper,
ink, muted, accent, link). Focal rule: `accent` on 1–2 elements max. Typography:
Title Instrument Serif; node names Geist sans; technical sublabels Geist Mono.
Node treatment: focal accent-tint; backend white/ink; store ink@0.05; external
ink@0.03; security accent@0.05 dashed.

## 6. Reglas innegociables (detalle en core §6)

1. Rounded right-angle (orthogonal) connectors mandatory (quarter-arc `r=8`, min `r=6`).
2. Label-to-connector margin 6–10px, always — label never sits *on* its arrow.
3. No overlapping connectors (bridge/hop; parallel arrows ≥12px apart).
4. Shared edge → fan attach points (≥12px, formula `L * k / (N+1)`).
5. No connector behind a non-endpoint box (dashed-transit exception only).
6. Label mask must not overlap a node drawn after it.
Draw arrows before boxes; every arrow label needs an opaque mask rect.

## 7. Complexity budget (tabla completa en core §7)

Max nodes 9 · arrows 12 · coral 2 · lanes 5 · ER entities 8 · radar axes 5 · bars
8 · scatter points 30 · callouts 2. Exceed → split overview + detail. **4px grid:**
all font sizes, padding, dims, gaps, coords divisible by 4.

## 8. Output

Single self-contained `.html` (embedded CSS, inline SVG, static by default).
Accessible SVG: `<svg role="img">` + `aria-labelledby` + `<title>` first child +
prefixed IDs. Export PNG/SVG, imports (drawio/mermaid), templates and the full
pre-output checklist: [`advanced.md`](advanced.md).

## Checklist

- [ ] Tipo visual (de los 27) y patron semantico elegidos
- [ ] Presupuesto de complejidad respetado (<=9 nodos, <=12 flechas)
- [ ] Conectores ortogonales, sin diagonales ni cruces sin bridge
- [ ] Accesible: role=img, aria-labelledby, title, IDs prefijados
- [ ] Style guide confirmado (no defaults en proyecto con marca)
- [ ] Salida: HTML autocontenido con SVG inline

## Ejemplo trabajado

```
Tarea: "flujo de aprobacion con 3 actores y rework"
-> semantic pattern: Paired policy-evaluation traces | tipo: Flowchart
-> load references/type-flowchart.md -> SVG ortogonal (r=8), arrows antes que boxes
-> presupuesto: 7 nodos, 8 flechas, coral 1 (CTA) | role=img + aria-labelledby -> DONE
```

## Rutas de carga (progressive disclosure)

- [`references/selection-guide.md`](references/selection-guide.md) — trigger→pattern, 27 tipos, confirm-before-drawing.
- [`references/style-guide.md`](references/style-guide.md) · [`references/semantic-patterns.md`](references/semantic-patterns.md) · [`references/output-spec.md`](references/output-spec.md) — tokens, comportamiento, spec de salida.
- [`references/export.md`](references/export.md) · [`references/import-drawio.md`](references/import-drawio.md) · [`references/import-mermaid.md`](references/import-mermaid.md) · [`references/primitive-annotation.md`](references/primitive-annotation.md) · [`references/primitive-icons.md`](references/primitive-icons.md) · [`references/primitive-sketchy.md`](references/primitive-sketchy.md) · [`references/primitive-terminal.md`](references/primitive-terminal.md) — export/import y primitivas SVG.
- [`core.md`](core.md) — design system completo, primitivas, layout y composicion. [`advanced.md`](advanced.md) — checklist pre-output, templates, imports, export.
