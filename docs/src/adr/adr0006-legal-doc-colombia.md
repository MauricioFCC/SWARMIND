# ADR-0006: legal-doc Colombia — Skill Juridico Multi-Especialidad

## Estado
**ACEPTADO** — Implementado en commit 00ae958.

## Contexto
El skill legal-doc era generico (GDPR, common law). Se necesita analisis juridico colombiano con fuentes oficiales, derecho comparado y multi-especialidad.

## Decision
Reescribir legal-doc skill con:
- Metodologia RTF+C (Role-Task-Format-Context/Constraints)
- 8 roles integrados (Analista, Teorico, Litigante, Academico, Comparatista, Procesalista, Riesgo, Pedagogo)
- Fuentes colombianas: SUIN, Relatoria CC, Consejo Estado, Corte Suprema
- Derecho comparado: 7 jurisdicciones
- 8 especialidades: Const, Adm, Laboral, Penal, Familia, Trib, Civil, Comercial
- Workflow de 7 fases

## Skill en uso
- AGENTIC/.opencode/skills/legal-doc/SKILL.md
- JURIDICO project inicializado con AGENTIC completo
- 3 documentos de referencia en knowledge/legal-colombia/
