# Verificación de Vigencia y Citas Legales — detalle bajo demanda

> Migrado a `references/` por politica "focused beats comprehensive" (SkillsBench 2026).
> Las reglas duras (LegalGraphRAG, APÓCRIFA-REVISAR, vigencia, contador) permanecen
> en `SKILL.md`; aqui vive el contexto regulatorio y el detalle operativo completo.

## Verificación de Vigencia y Citas Legales (2026)

La verificación de citas en el dominio legal es un **DEBER sancionable, no una buena práctica
opcional**. Cualquier conclusión debe anclarse a fuentes verificadas y con estado de vigencia
conocido. Sin esto, el output no es legalmente defendible.

### Contexto regulatorio crítico (Colombia, feb 2026)
- La **Sala Civil de la Corte Suprema de Justicia de Colombia sancionó a un abogado por
  temeridad procesal** al citar textos legales y jurisprudencia apócrifos generados por IA.
  El incumplimiento de la verificación tiene consecuencias disciplinarias reales.
- La **Corte Constitucional (T-323 de 2024)** exhortó a funcionarios y empleados de la Rama
  Judicial sobre el uso de herramientas de IA generativa, y fija criterios exigibles:
  - **Transparencia**: declarar el uso de IA en la elaboración del documento.
  - **Responsabilidad**: el profesional responde por el contenido, no la herramienta.
  - **Verificación seria de fuentes**: toda cita debe cotejarse contra la fuente primaria.
  - **Control humano**: revisión final por profesional habilitado antes de presentar.
- Aplicar estos criterios también como estándar interno para cualquier análisis jurídico generado.

### Patrón LegalGraphRAG: Researcher → Auditor → Adjudicator
Pipeline de tres roles para garantizar que solo la evidencia verificada llegue al output:
```
1. RESEARCHER: recupera evidencia candidata (normas, sentencias, doctrina) desde el corpus
2. AUDITOR: VERIFICA la validez de cada candidata contra las fuentes primarias
   (existe la norma? la sentencia cita eso? la numeración es correcta? vigencia?)
3. ADJUDICATOR: sintetiza SOLO evidencia verificada, con citas trazables a la fuente
```
- Cada conclusión debe llevar citas **trazables**: norma/sentencia, órgano emisor, fecha y URL.
- Si el AUDITOR no puede verificar una fuente, esa evidencia NO entra a la síntesis
  (o entra marcada como no verificada, nunca como válida).

### Verificación de vigencia
- Para cada norma citada, reportar su **estado**: `VIGENTE` / `MODIFICADO` / `DEROGADO` /
  `INEXEQUIBLE`, **anclado a la fuente primaria** (con URL/fecha de consulta).
- Fuentes oficiales sugeridas (Colombia):
  - Relatoría de la Corte Constitucional (sentencias C-, T-, SU-, Autos).
  - **SUIN** (Sistema Único de Información Normativa) para vigencia de leyes y decretos.
  - Secretarías/relatorías de la Corte Suprema y Consejo de Estado, Rama Judicial.
  - **Kelsen MCP** (si está disponible): herramientas `buscar_normas`, `consultar_articulo`,
    `buscar_jurisprudencia`, `vigencia` para consulta estructurada de fuentes oficiales.
- La vigencia debe incluir fecha de la consulta: el estado puede cambiar entre consultas.

### Diagnostic Checklists por norma
Para cada norma analizada, aplicar un checklist diagnóstico:
- [ ] **Ámbito de aplicación**: a quién/situaciones aplica la norma.
- [ ] **Excepciones**: qué excluye expresamente la norma.
- [ ] **Jurisprudencia que la interpreta**: sentencias que la aplican o la desarrollan.
- [ ] **Vigencia**: estado actual anclado a fuente primaria + fecha de consulta.

### Marca explícita de citas no verificadas
- Cualquier cita NO verificada debe marcarse **`APÓCRIFA-REVISAR`** en la salida.
- **Nunca presentar como válida una cita no verificada**: es el anti-patrón que generó
  sanciones disciplinarias en Colombia.
- Al final del output, incluir un **contador de citas verificadas vs no verificadas**.

### Multi-jurisdicción
- Si el análisis cruza jurisdicciones, **verificar en la jurisdicción correcta** y
  **declararla explícitamente** en cada cita (ej. `[Colombia]`, `[España]`, `[México]`).
- No extrapolar vigencia o interpretación de una jurisdicción a otra sin señalarlo.
- Cuando aplique control de convencionalidad, anclar la verificación a la fuente de la
  jurisdicción pertinente (Corte IDH para el Sistema Interamericano).
