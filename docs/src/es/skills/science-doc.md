# Science Doc

> Skill contextual para el dominio científico multidisciplina — análisis de papers académicos, tesis, informes técnicos, revisiones sistemáticas y documentación de investigación.

## Categoria

Documentacion Cientifica

## Proposito

Skill contextual para el dominio científico multidisciplina — análisis de papers académicos, tesis, informes técnicos, revisiones sistemáticas y documentación de investigación.

## Agentes que lo usa

- Consultar [Registro de Skills](registry.md) para ver los agentes que utilizan este skill.

## Verificación de Citas y Reproducibilidad (frontier 2026)

Skill actualizado al estándar 2026 para validación de citas y reproducibilidad de investigación:

### CiteGuard-style — Validación de Citas

- **Retrieval-augmented validation**: cada afirmación factual en el paper debe ser rastreable a una fuente recuperada (via arXiv, PubMed, Google Scholar, bases de datos disciplinares).
- **Marca `CITA-NO-VERIFICADA`**: cuando no se pueda verificar una cita, se debe marcar explícitamente en el margen con el tag `CITA-NO-VERIFICADA` + razón (fuente no encontrada, contexto ambiguo, paper retractado).
- **OpenScholar-style self-feedback**: el agente debe generar un reporte de auto-feedback identificando:
  - Citas auto-referenciales (paper cita propio trabajo sin verificación externa)
  - Contradicciones entre secciones
  - Hallazgos que carecen de evidencia de soporte
- **Reproducibilidad ARA-style** (ARISE/ResearchAgent): cada experimento debe documentarse con:
  - Semilla aleatoria usada
  - División de train/valid/test
  - Métricas Reported vs Reproducidas
  - Bandera `REPRODUCIBLE / PARCIAL / NO` en metadatos

### Detección de Contradicciones (PaperQA2-style)

- **Contradicción de hechos**: búsqueda inversa de afirmaciones contradictorias en el mismo paper o conjunto de papers.
- **Marcado de conflicto**: si se detectan contradicciones, etiquetar con `CONTRADICCIÓN: <afirmación_1> vs <afirmación_2>` + fuente de cada una.
- **Prioridad de fuentes**: fuentes peer-reviewed > preprints > repositorios > web.

### Plantilla de Reporte de Reproducibilidad

```markdown
## Reproduccibilidad

- **Semilla**: `<valor>`
- **División de datos**: train/valid/test = `<razones>`
- **Métricas reportadas**: `<lista>`
- **Métricas reproducidas**: `<resultado al re-ejecutar>`
- **Estado**: REPRODUCIBLE / PARCIAL / NO
- **Comentarios**: `<breve explicación>`
```
