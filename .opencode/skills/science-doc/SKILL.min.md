---
name: science-doc
domain: science
description: "Usar cuando el usuario analiza papers o documentacion cientifica. papers academicos, tesis, informes tecnicos, revisiones sistematicas, investigacion. Alcance: analisis de papers y revisiones; para matematicas ver math-doc. | UPG·NAM·FRS (reglas en base_principles.md)"
license: MIT
version: 1.0.0
project_agnostic: true
---

# Science-Doc (min)

Analisis critico de papers/tesis/revisiones con trazabilidad de fuentes y verificacion de citas.

## Reglas esenciales
1. Estructura IMRaD + contribucion + limitaciones
2. Metodologia: diseno, tamano muestral, cegamiento, sesgos
3. Resultados: tamano del efecto, significancia, robustez, reproducibilidad
4. Revision: estado del arte, mapa de citas, gaps, contradicciones
5. Sistematicas: PRISMA, PICO, I², funnel/forest plot
6. Etica: autoria, COI, aprobacion, consentimiento, plagio
7. Bibliometria: H-index, IF, cuartil SJR, coautoria, burst keywords

## Verificacion 2026
Cada cita validada contra la fuente (DOI); marcar `CITA-NO-VERIFICADA`; veredicto `REPRODUCIBLE`/`PARCIAL`/`NO-REPRODUCIBLE`; contradicciones explicitas.

## Checklist
- [ ] IMRaD + metodologia · [ ] Sesgos · [ ] Citas con DOI
- [ ] Reproducibilidad · [ ] Contradicciones · [ ] PRISMA/PICO

## Referencias (bajo demanda)
- [Verificación de citas 2026](references/verificacion-2026.md) · [Keywords de dominio](references/keywords-dominio.md)
