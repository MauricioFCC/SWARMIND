# ADR 0072: PEC Universal — Persona-Expert + Canon en TODAS las Skills

## Estado
Aplicado | 34/34 skills + `scripts/apply_pec.py` + `test_skill_pec.py` (171 tests) | Propietario: @coordinator | Fecha: 2026-09-07

## Contexto
ADR-0071 aplicó el patrón PEC solo a 3 skills estéticas. El usuario lo generaliza: **la esencia
aplicable a cualquier skill** — cada skill debe quedar envebida con persona experta rica y
referencias canónicas frontera POR ESPECIALIDAD (no solo estética): el modelo consulta e
implementa las técnicas más top de cada dominio, no sus hábitos de entrenamiento.

Research que lo sustenta (ya citado en ADR-0071):
- arXiv 2605.29420: persona prompting ayuda condicionalmente — la especialización y el anclaje importan.
- arXiv 2603.18507 (PRISM): personas genéricas dañan accuracy (hedging/verbosidad) — persona específica + anti-hedging.
- RICOUI Brands (verificada): ejemplo de canon multi-brand por especialidad.

## Decisión
1. **Sección estándar `## PERSONA & CANON (patrón PEC universal, ADR-0072)`** en las 34 skills:
   - **PERSONA**: rol senior + años (10/12/15+) + especialización específica del dominio.
   - **CANON**: ≥2 referencias https frontera/empresarial por especialidad (OWASP para
     security, HL7 FHIR para healthtech, Rust API Guidelines para rust-lang, DORA para
     devops, CFA para hedgefund, DIAN para pos-retail, etc.) — estudiar ANTES de generar (RSF).
   - **ANTI-HEDGING**: regla de decisión firme específica de la especialidad.
2. **`scripts/apply_pec.py`**: aplicador idempotente (reemplaza sección existente; inserta
   tras el primer heading si no existe) — regenerable cuando cambie el canon.
3. **`test_skill_pec.py`**: 171 tests parametrizados (sección, seniority, ≥2 https,
   anti-genérica, anti-hedging, budget de description) — el gate en CI.
4. **Regla RSF amplificada**: "estudiar el canon ANTES de generar" convierte el Research First
   en un requisito con referencias concretas por especialidad.

## Consecuencias
### Positivas
- 34 skills con anclas de calidad por dominio (output consistentemente de frontera).
- Gate verificable: si una skill nueva no trae PEC, CI falla.
- Canon centralizado en un script (SSOT) — actualizar una URL = 1 edit + re-run.

### Negativas
- +150-300 tokens por skill leída (mitigado: tiers de residencia ADR-0053; solo se cargan bajo demanda).
- URLs pueden caducar (revisión periódica via validator).

## Alternatives Considered
1. **Solo 3 skills estéticas (ADR-0071)**: el usuario lo generaliza — la necesidad de anclas
   de frontera es dominio-agnóstica (OWASP importa tanto como Material 3).
2. **Canon en frontmatter**: los modelos no lo leen en el cuerpo; PEC vive donde se lee.
3. **Sin script (edición manual)**: 34 files × drift = innegociable; el script es el SSOT.

## Relacionado
- ADR-0071 (superseded — versión inicial de 3 skills), ADR-0052/0053 (skills/tiers)
- arXiv 2605.29420, arXiv 2603.18507, RICOUI Brands
