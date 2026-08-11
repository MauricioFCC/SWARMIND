# legal-doc — Analisis Juridico

Skill especializado en procesamiento y analisis de documentos legales colombianos.

## Capacidades

| Capacidad | Descripcion | Tecnica |
|-----------|-------------|---------|
| **NER juridico** | Extrae entidades: normas, cortes, cargos, fechas | SaulLM-7B + LexBERT |
| **Argument mining** | Extrae ratio decidendi y obiter dicta | Arg-LLaDA |
| **Clasificacion** | 6 tipos: sentencia, demanda, contrato, concepto, norma | Pattern + keyword |
| **Resumen** | Resumen por palabras clave juridicas | Sufficiency-aware |
| **Comparacion** | Compara documentos por entidades compartidas | Entity matching |

## Verificación de Vigencia y Citas Legales (frontier 2026)

Skill actualizado al estándar 2026 para validación de citas jurídicas y vigencia normativa:

### Precedente Corte Suprema Colombia (feb-2026)

- Detectar citas apócrifas o inventadas por modelos IA (fenomenon documentado feb-2026, sanción Corte Suprema por citas no verificables).
- **Criterios T-323-24**: toda cita normativa debe verificar contra el texto oficial en el repositorio del Centro de Información Judicial (CIJ).
- Patrón LegalGraphRAG (Researcher→Auditor→Adjudicator):
  1. **Researcher**: Recupera precedentes y normativas relacionadas via embedding semantic search.
  2. **Auditor**: Valida vigencia de cada cita contra SUIN (Sistema Único de Información Normativa) y relatorías oficiales.
  3. **Adjudicator**: Emite veredicto de vigencia por cada cita.

### Marcos de Veredicto de Vigencia

Cada cita debe recibir un veredicto oficial entre:

| Veredicto | Significado | Acción |
|-----------|-------------|--------|
| **VIGENTE** | Cita vigente y aplicable en la jurisdicción actual | Usar libremente en argumentos |
| **MODIFICADO** | Cita vigente pero con modificaciones parciales | Consultar versión actualizada |
| **DEROGADO** | Cita oficialmente derogada o sustituida | No usar; reemplazar por versión nueva |
| **INEXEQUIBLE** | Cita teóricamente existene pero inaplicable por inconstitucionalidad | Usar con advertencia cautelar |

### Marca `APÓCRIFA-REVISAR`

- Cuando no se pueda verificar la origen de una cita en fuentes oficiales, marcar explícitamente con tag `APÓCRIFA-REVISAR` en el margen del documento.
- El sistema debe sugerir fuentes alternativas de consulta (Banco de Leyes, WIPO, LexML, etc.).
- Este tag es **distinto** de `CITA-NO-VERIFICADA` (uso scientifico): `APÓCRIFA-REVISAR` es específicamente jurídico-legal.

### Checklists por Norma

Para cada tipo de documento legal, aplicar checklist de verificación:

**Para Sentencias:**
- [ ] Todas las citations tienen fuente oficial verificada (SUIN/CIJ)
- [ ] No hay citas `APÓCRIFA-REVISAR` sin alternativa
- [ ] Precedentes citados están en vigor (estado VIGENTE/MODIFICADO)
- [ ] No hay contradicciones entre partes dispositivas y considerandos

**Para Demandas:**
- [ ] Todas las normas citadas tienen vigencia confirmada
- [ ] Citas a tratados internacionales verificados (ratificación colombiana)
- [ ] No se usan citas apócrifas (revisar `APÓCRIFA-REVISAR`)
- [ ] Conformidad con línea de jurisprudencia T-323-24

**Para Contratos:**
- [ ] Todas las referencias normativas tienen fuente primaria
- [ ] No hay superposición de cánones derivados de fuentes no verificables
- [ ] Consistencia con jurisprudencia sobre clausulas abusivas

## Comandos

- `!legal analyze <doc>` — Analizar documento legal completo
- `!legal extract <doc>` — Extraer entidades juridicas
- `!legal compare <doc1> <doc2>` — Comparar documentos
- `!legal summarize <doc>` — Resumir documento
- `!legal verify <doc>` — Verificar vigencia de todas las citations (reporta VIGENTE/MODIFICADO/DEROGADO/INEXEQUIBLE y marca `APÓCRIFA-REVISAR` si corresponde)

## Ver Tambien

- [Registro de skills](registry.md)
- [Investigacion aplicada](../reference/investigacion-aplicada.md)
