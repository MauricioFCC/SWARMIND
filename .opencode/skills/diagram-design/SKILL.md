---
name: diagram-design
domain: frontend
description: "Usar cuando el usuario pide un diagrama visual editorial. arquitectura, flowchart, sequence, state machine, ER, timeline, swimlane, quadrant, radar, org chart, mermaid, drawio, SVG, diagrama. | UPG·NAM·FRS (reglas en base_principles.md)"
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

Create visual diagrams as self-contained HTML files with inline SVG and CSS, following an opinionated editorial design system.

Twenty-seven visual types. Semantic patterns describe behavior independently; type references describe layout. Details load from `references/` only when selected.

## PERSONA & CANON (patrón PEC universal, ADR-0072)

- **PERSONA**: Eres un/a **Information designer editorial senior (10+ anos), estilo Tufte/Storytelling with Data: claridad first, cero chartjunk.**
- **CANON** (estudiar ANTES de generar, regla RSF):
  - RICOUI Brands — https://design.ricoui.com/brands
  - Mermaid — https://mermaid.js.org
  - Storytelling with Data — https://www.storytellingwithdata.com
- **ANTI-HEDGING**: Elige UNA forma visual y justificala en 1 linea.
---

## 0. First-time setup — style guide gate

**Before generating your first diagram in a new project, verify the style guide has been customized.**

Don't silently ship default-skinned diagrams into a branded project.

Open [`references/style-guide.md`](references/style-guide.md) and check the default tokens. If they're still the shipped defaults (paper `#f5f5f5`, ink `#2d3142`, accent `#eb6c36` atomic-tangerine), **pause and ask the user**:

> *"This is your first Schematic in this project. The style guide is still at the default (neutral white-smoke + atomic-tangerine). Do you want to customize it to match your brand first? Options: (a) pull from your website URL, (b) extract from an installed skill, (c) extract from a local folder / design-system directory, (d) paste tokens manually, (e) proceed with the default for now."*

Then branch:

- **(a)** → follow [`references/onboarding.md § URL`](references/onboarding.md)
- **(b)** → follow [`references/onboarding.md § Skill`](references/onboarding.md)
- **(c)** → follow [`references/onboarding.md § Folder`](references/onboarding.md)
- **(d)** → accept the user's tokens and write them into `style-guide.md`
- **(e)** → proceed; optionally remind the user they can run onboarding later.

**Once customized** (or user opted for default), skip this gate on subsequent runs. Detection: if the `accent` value differs from `#eb6c36`, assume custom.

---

## 1. Philosophy

**The highest-quality move is usually deletion.**

- Every node represents a distinct idea. Two nodes that always travel together are one node.
- Every connection carries information. If the relationship is obvious from layout, remove the line.
- Coral is **editorial, not a flag.** 1–2 focal nodes per diagram.
- The schematic isn't done when everything is added. It's done when nothing can be removed.

**Target density: 4/10.** Above 9 nodes, it's probably two diagrams.

---

## 2. When to Use

Use for any of the 27 visual types (§3) when a reader will learn more from a visual than from prose, a table, or a bulleted list.

**Don't use for:** quick unicode diagrams (use **wiretext**), lists (table/bullets), simple before/after (table), one-shape "diagrams" (just write the sentence).

Before drawing, ask: *Would the reader learn more from this than from a well-written paragraph?* If no, don't draw.

---

## 3. Selection: semantic pattern, then visual type

When behavior, state, enforcement, or risk carries the meaning, first load [`references/semantic-patterns.md`](references/semantic-patterns.md) and choose one primary pattern. Then choose the nearest visual type for layout.

| Behavioral trigger | Semantic pattern → nearest type |
|---|---|
| Fan-in, queue depth, finite capacity, bottleneck | **Fan-in queue / bottleneck** → Data flow |
| Repeated Question / Input / Governance / Output slots across stages | **Stage framework with semantic slots** → Process |
| Conversation or loose input becomes a structured durable artifact | **Unstructured input → structured artifact** → Data flow |
| Two rule traces need pass/fail/skipped/not-reached and first divergence | **Paired policy-evaluation traces** → Flowchart |
| Trust boundaries plus permitted/forbidden ingress or deploy paths | **Secure paved road** → Architecture |
| Controls grouped by where they are enforced | **Governance / control catalog** → Layer stack |
| Defenses compensate for prior gaps and residual risk propagates | **Compensating security layers** → Layer stack |

Use [`references/animation.md`](references/animation.md) only when motion is requested; static remains the default.

### Visual-type guide (27)

| If you're showing… | Use | Reference |
|---|---|---|
| Components + connections in a system | **Architecture** | [type-architecture.md](references/type-architecture.md) |
| Legacy IT landscape grouped by phase/department | **IT current-state** | [type-it-state.md](references/type-it-state.md) |
| Decision logic with branches | **Flowchart** | [type-flowchart.md](references/type-flowchart.md) |
| Time-ordered messages between actors | **Sequence** | [type-sequence.md](references/type-sequence.md) |
| States + transitions + guards | **State machine** | [type-state.md](references/type-state.md) |
| Entities + fields + relationships | **ER / data model** | [type-er.md](references/type-er.md) |
| Events positioned in time | **Timeline** | [type-timeline.md](references/type-timeline.md) |
| Cross-functional process with handoffs | **Swimlane** | [type-swimlane.md](references/type-swimlane.md) |
| Two-axis positioning / prioritization | **Quadrant** | [type-quadrant.md](references/type-quadrant.md) |
| Multiple entities scored across 3–5 quantitative criteria | **Radar / Spider** | [type-radar.md](references/type-radar.md) |
| Reinforcing cycle / flywheel with shared hub | **Loop** | [type-loop.md](references/type-loop.md) |
| Hierarchy through containment / scope | **Nested** | [type-nested.md](references/type-nested.md) |
| Parent → children relationships | **Tree** | [type-tree.md](references/type-tree.md) |
| Human/agent/team ownership, reporting, routing, escalation | **Org chart** | [type-org-chart.md](references/type-org-chart.md) |
| Stacked abstraction levels | **Layer stack** | [type-layers.md](references/type-layers.md) |
| Overlap between sets | **Venn** | [type-venn.md](references/type-venn.md) |
| Ranked hierarchy or conversion drop-off | **Pyramid / funnel** | [type-pyramid.md](references/type-pyramid.md) |
| Quantitative comparison across categories | **Bar chart** | [type-bar.md](references/type-bar.md) |
| Continuous trends over time | **Line chart** | [type-line.md](references/type-line.md) |
| Tasks and phases on a timeline | **Gantt** | [type-gantt.md](references/type-gantt.md) |
| Distribution and correlation between two variables | **Scatter plot** | [type-scatter.md](references/type-scatter.md) |
| End-to-end data stack on a container cluster | **High-Level** | [type-high-level.md](references/type-high-level.md) |
| Multi-actor sequential process with data handoffs | **Process** | [type-process.md](references/type-process.md) |
| Multi-tier data storage with quality levels and access policies | **Medallion** | [type-medallion.md](references/type-medallion.md) |
| Role-scoped data flow: who does what at each pipeline step | **Data flow** | [type-data-flow.md](references/type-data-flow.md) |
| Integration topology of a data platform — sources → core → consumers | **DP integration** | [type-dp-integration.md](references/type-dp-integration.md) |
| Per-role / per-component access permissions matrix | **DP security matrix** | [type-dp-security-matrix.md](references/type-dp-security-matrix.md) |

**Always load the chosen `references/type-*.md` before drawing.** When routed above, also load `semantic-patterns.md`; when animation is chosen, load `animation.md`.

### Confirm before drawing

Before rendering, state the plan in one short message: the chosen visual type (and semantic pattern, if routed), the size preset, and anything the complexity budget (see core.md §7) will force out. If the user is reachable, let them redirect before you draw; if not, proceed and note the assumptions beside the deliverable.

---

## 4. Universal Anti-patterns (resumen — tabla completa en core.md)

These mark "AI slop" schematics of any type:

- Dark mode + cyan/purple glow; JetBrains Mono as blanket "dev" font; identical boxes for every node
- Legend floating inside the diagram area; arrow labels with no masking rect; vertical `writing-mode` text
- Shadow on any element (shadows are out, borders are in); `rounded-2xl` on boxes; coral on every node
- Diagonal connectors between off-axis nodes (rounded right-angle elbows are mandatory)
- Label on its connector (needs 6–10px gap); two connectors overlapping or sharing an attach point

Type-specific anti-patterns live in each `references/type-*.md`.

---

## 5. Design System (resumen — detalle en core.md)

**The design system is skinnable.** All colors, typography, and tokens live in [`references/style-guide.md`](references/style-guide.md) — semantic roles (`paper`, `ink`, `muted`, `accent`, `link`, …). Default: white-smoke paper, jet-black ink, atomic-tangerine accent.

- **Focal rule:** `accent` goes on 1–2 elements max.
- **Typography:** Title = Instrument Serif; node names = Geist sans; technical sublabels = Geist Mono. Mono is for technical content only.
- **Node treatment:** Focal = `accent-tint`/`accent`; Backend/API = white/ink; Store/State = `ink@0.05`/muted; External = `ink@0.03`/`ink@0.30`; Security = `accent@0.05`/`accent@0.50` dashed.

---

## 6. Reglas innegociables (detalle en core.md §6)

1. **Rounded right-angle (orthogonal) connectors are mandatory.** No diagonal slants between off-axis nodes. Quarter-arc `r=8` (min `r=6`).
2. **Label-to-connector margin: 6–10px gap, always** — label never sits *on* its arrow.
3. **No overlapping connectors.** Crossings use the bridge/hop primitive; parallel arrows ≥12px apart.
4. **Shared edge → fan the attach points** (≥12px apart, formula `L * k / (N+1)`).
5. **No connector passes behind a non-endpoint box** — except the dashed-transit exception for geometrically unavoidable boxes.
6. **A label mask must not overlap a node drawn after it.**

Draw arrows before boxes. Every arrow label needs an opaque mask rect.

---

## 7. Complexity budget (resumen — tabla completa en core.md §7)

Max nodes 9 · max arrows 12 · max coral 2 · max lanes 5 · max ER entities 8 · max radar axes 5 · max bars 8 · max scatter points 30 · max annotation callouts 2. If exceeded, split into overview + detail.

**4px grid:** all font sizes, padding, node dimensions, gaps, x/y coords divisible by 4.

---

## 8. Output

Always produce a single self-contained `.html` file: embedded CSS, inline SVG, static by default. Accessible SVG contract: `<svg role="img">` + `aria-labelledby` + `<title>` first child + prefixed IDs.

Export to PNG/SVG, imports (drawio/mermaid), templates and the full pre-output checklist: see [`advanced.md`](advanced.md).

---

## Rutas de carga (progressive disclosure)

- [`core.md`](core.md) — Design system completo, primitivas SVG, layout & spacing, checklist de composición.
- [`advanced.md`](advanced.md) — Checklist pre-output completo, templates & variants, imports (drawio/mermaid), export PNG/SVG.
- [`references/`](references/) — style-guide, semantic-patterns, type-*.md, primitives, animation, onboarding, output-spec.