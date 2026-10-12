# Métricas de Evaluación y FDE — detalle bajo demanda

> Migrado de `SKILL.md` a `references/` por política "focused beats comprehensive"
> (SkillsBench 2026, arXiv:2602.12670). El loop, su checklist y el aterrizaje al
> motor permanecen en `SKILL.md`; aquí viven la tabla de métricas y el mapeo FDE.

## 🚀 FDE INTEGRATION

Cada ronda de evolución aplica FDE:

| FDE Pilar | Cómo se aplica en Evolve |
|-----------|--------------------------|
| **DELTA** | Identificar el gap entre el skill actual y el ideal universal |
| **MISSION** | Cada ronda tiene un objetivo medible (score objetivo) |
| **GLUE** | Las mejoras deben ser integrables en cualquier proyecto |
| **VALUE** | Priorizar cambios 80/20 que den más valor por round |
| **DIPLOMACY** | Las mejoras deben mantener compatibilidad hacia atrás |
| **RESILIENCE** | Los skills mejorados deben mantener guardrails activos |
| **EVOLVE** | El meta-loop se retroalimenta de sus propias métricas |

## 📊 MÉTRICAS DE EVALUACIÓN UNIVERSALES

Todo skill es evaluado en estas dimensiones (project-agnostic):

| Métrica | Peso | Descripción |
|---------|------|-------------|
| exists | 0.05 | El archivo existe |
| has_frontmatter | 0.05 | Tiene frontmatter YAML válido |
| has_version | 0.05 | Tiene versionado semántico |
| has_project_agnostic | 0.10 | Es reutilizable en cualquier proyecto |
| has_principles_ref | 0.10 | Referencia principios universales |
| has_evolve_hooks | 0.10 | Tiene hooks de auto-mejora |
| has_fde_flow | 0.10 | Incorpora FDE principles |
| has_guardrails | 0.05 | Tiene validaciones de guardrails |
| has_variables | 0.05 | Usa variables {{}} para parametrización |
| has_mermaid | 0.05 | Incluye diagramas de flujo |
| has_checklist | 0.05 | Tiene checklist de verificación |
| has_domain_sections | 0.05 | Estructura clara con secciones |
| length_adequate | 0.05 | Tamaño adecuado (200-5000 chars) |
| fde_coverage | 0.10 | Cobertura de patrones FDE |
| evolve_coverage | 0.05 | Cobertura de patrones EVO |
