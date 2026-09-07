# ADR 0071: Patrón PEC — Persona-Expert + Canon en Skills de Dominio Estético

## Estado
Aplicado | `frontend-uiux`, `diagram-design`, `creative-design` + `test_skill_pec.py` | Propietario: @coordinator | Fecha: 2026-09-07

## Contexto
Las skills actuales definen ROL técnico (ej. "UI/UX Architect") pero sin persona experta rica ni nivel de referencia de calidad. El output estético varía run-to-run porque no hay anclas de qué es "nivel empresarial".

**Research frontera (sep-2026)**:
- **arXiv 2605.29420** (persona prompting): ayuda *condicionalmente* — la SELECCIÓN del rol especialista importa más que añadir la persona; specialist framing aporta valor cuando la tarea lo necesita. Tradeoff: expertise-depth ↑ vs claridad (hedging/verbosidad).
- **arXiv 2603.18507 (PRISM)**: personas expertas MEJORAN alignment pero **DAÑAN accuracy cuando son genéricas** ("eres un experto") — introducen hedging, verbosidad y jargon sin anclaje.
- Referencia del usuario: "eres un diseñador de sistemas UI/UX experto con X años..." + "busca diseños de nivel empresarial como https://design.ricoui.com/brands" (verificada: RICOUI multi-brand editor, Beta).

## Decisión
**Patrón PEC (Persona-Expert + Canon)** — sección obligatoria en skills cuyo output depende de juicio estético/dominio:

```md
## PERSONA & CANON (patrón PEC, ADR-0071)
- **PERSONA**: rol senior + años (10+) + especialización específica + stack.
- **CANON**: ≥2 referencias https de nivel empresarial — estudiar ANTES de
  generar (regla RSF aplicada a diseño).
- **ANTI-HEDGING**: decisiones firmes con rationale; UNA recomendación.
```

Aplicado a 3 skills (las de output estético): `frontend-uiux` (diseñador de systems
senior multi-brand + RICOUI/Material3/Polaris/Carbon/Primer/Atlassian),
`diagram-design` (information designer editorial + Tufte/Storytelling with Data/Mermaid),
`creative-design` (director creativo de agencia + Brand New/Awwwards).

TDD: `harness/tests/test_skill_pec.py` 13 tests (sección presente, años,
≥2 https, anti-persona-genérica, presupuesto description).

## Consecuencias
### Positivas
- Output anclado a nivel empresarial verificable (el canon es URL-checkable).
- Persona específica evita el daño de accuracy de personas genéricas (PRISM).
- Anti-hedging ataca el tradeoff expertise↔claridad con regla explícita.
- Patrón replicable: nuevas skills estéticas heredan la estructura.

### Negativas
- URLs del canon pueden caducar (mitigable: revisión en validate_skills).
- +~150 tokens por skill activa (aceptable: 3 skills, no standing tax global).

## Alternatives Considered
1. **Persona genérica ("experto con 20 años")**: PRISM demuestra daño a accuracy.
2. **Canon en frontmatter `metadata.canon`**: no lo leen los modelos en el cuerpo; el patrón va donde el modelo lee.
3. **Sólo frontend-uiux**: el patrón vale para todo output estético (diagramas, branding).

## Relacionado
- ADR-0052 (habilidades agente), ADR-0053 (presupuesto residencia skills)
- arXiv 2605.29420, arXiv 2603.18507, RICOUI Brands (referencia usuario)
