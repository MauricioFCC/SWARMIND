# Verificación de Citas y Reproducibilidad (2026) — detalle bajo demanda

> Migrado de `SKILL.md` a `references/` por política "focused beats comprehensive"
> (SkillsBench 2026, arXiv:2602.12670). El checklist accionable y las reglas
> contextuales permanecen en `SKILL.md`; aquí vive el detalle del pipeline 2026.

## Verificación de Citas y Reproducibilidad (2026)

Las alucinaciones de citas son un problema medido y crítico en la literatura científica
asistida por IA: más de 50 citas falsas fueron detectadas en 300 submissions de ICLR 2026.
Toda síntesis debe implementar verificación de citas y reproducibilidad como parte del
pipeline, no como paso opcional.

### CiteGuard-style: Validación de cada cita contra la fuente
- Cada cita del paper/resumen debe validarse contra la fuente original mediante
  **retrieval-augmented validation** (búsqueda en la base + adjudicación con el texto recuperado).
- Mantener un **contador de citas no verificables**: cada cita que no pueda confirmarse
  contra una fuente real se contabiliza y se marca explícitamente como **`CITA-NO-VERIFICADA`**
  en el output. Nunca presentarla como válida.
- El retrieval debe incluir la acción de buscar el snippet textual (no solo el título),
  porque la evidencia textual recuperada es el mayor predictor de citas fieles
  (hallazgo central de CiteGuard, ACL 2026 — accuracy 68.1% en benchmark CiteME vs 69.2% humano).

### OpenScholar-style self-feedback
Pipeline de refinamiento iterativo para síntesis con citas trazables:
```
1. RECUPERAR evidencia: retrieval de papers relevantes desde la base (ID de paper + sección)
2. REDACTAR síntesis con citas in-text, cada afirmación anclada a una fuente
3. AUTO-REVISAR: verificar que cada claim tiene cita, que la cita soporta el claim, y que no hay claims sin soporte
4. REFINAR: reescribir las partes con citas débiles o faltantes
```
- El output debe permitir **trazar cada afirmación a la fuente**: ID del paper, sección,
  y fragmento textual recuperado (estilo Self-RAG / OpenScholar).
- Usar **LLM-as-a-Judge** para filtrar síntesis con citas débiles antes de emitirlas.

### Reproducibilidad (ARA-style)
Al analizar un paper, extraer explícitamente el paquete de reproducibilidad:
- **Datos de entrenamiento/experimentos**: datasets usados, splits, versiones, accesibilidad.
- **Hiperparámetros**: learning rate, batch size, épocas, seeds, config de modelos.
- **Métricas reportadas**: precisión/recall/F1, p-valores, IC, tamaño del efecto.
- Señalar si el paper permite **reproducibilidad document-level** (workflow graph: pasos,
  dependencias de datos, versiones) o si **faltan detalles** que impiden reproducir.
- Reportar un veredicto de reproducibilidad: `REPRODUCIBLE` / `PARCIAL` / `NO-REPRODUCIBLE`
  con la evidencia de qué falta.

### Detección de contradicciones
- Si el análisis encuentra **contradicciones entre papers o entre afirmaciones del mismo
  paper**, listarlas explícitamente con referencias (estilo PaperQA2), en formato:
  `Afirmación A [paper X, sección Y] ↔ Afirmación B [paper Z, sección W]`.
- No resolver la contradicción silenciosamente: marcarla como hallazgo y señalar el conflicto.

### Herramientas sugeridas
- **Semantic Scholar API**: retrieval por título/abstract/topics, embeddings científicos.
- **arXiv API**: acceso a preprints y versiones con DOI.
- **scholar-search-mcp** (si está disponible): búsqueda académica vía MCP.
- **DOI validation**: verificar que el DOI resuelve y apunta al documento correcto.
- **ai2 paper finder / retrieval pipelines**: alternativas de alta cobertura para el retrieval.
