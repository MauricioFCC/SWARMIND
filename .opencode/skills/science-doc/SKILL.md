---




name: science-doc
domain: science
description: "Skill contextual para el dominio científico multidisciplina — análisis de papers académicos, tesis, informes técnicos, revisiones sistemáticas y documentación de investigación | UPG·NAM·FRS (reglas en base_principles.md)"
version: 1.0.0
project_agnostic: true
---

# Science-Doc: Procesamiento de Documentos Científicos

Skill contextual para el dominio **científico multidisciplina**: análisis de papers académicos, tesis, informes técnicos, revisiones sistemáticas y documentación de investigación.

## Activación
Se activa automáticamente cuando el `router` detecta keywords del dominio científico/investigación.

## Keywords de dominio
- `science`, `scientific`, `research`, `investigación`, `ciencia`, `científico`
- `paper`, `article`, `publication`, `publicación`, `journal`, `revista`
- `thesis`, `tesis`, `dissertation`, `disertación`, `academic`, `académico`
- `experiment`, `experimento`, `hypothesis`, `hipótesis`, `methodology`, `metodología`
- `peer review`, `revisión por pares`, `systematic review`, `revisión sistemática`
- `meta-analysis`, `metaanálisis`, `reproducibility`, `reproducibilidad`
- `citation`, `cita`, `bibliography`, `bibliografía`, `references`, `referencias`
- `impact factor`, `factor de impacto`, `indexing`, `indeación`, `scopus`, `wos`
- `physics`, `física`, `chemistry`, `química`, `biology`, `biología`, `medicine`
- `engineering`, `ingeniería`, `computer science`, `computación`, `social sciences`

## Reglas contextuales

### 1. Análisis Estructural de Papers
- **IMRaD**: Identificar Introduction, Methods, Results, Discussion en papers
- **Secciones**: Extraer título, autores, afiliaciones, abstract, keywords, referencias
- **Abstract**: Clasificar tipo (estructurado, narrativo, gráfico) y extraer objetivo/métodos/resultados
- **Contribución**: Identificar contribución principal, novedad y alcance
- **Limitaciones**: Detectar secciones de limitaciones y trabajo futuro

### 2. Evaluación de Metodología
- **Diseño experimental**: Identificar tipo (RCT, cohorte, caso-control, cruzado, series)
- **Tamaño muestral**: Evaluar si el tamaño muestral es adecuado para significancia estadística
- **Grupos**: Identificar grupos de control, tratamiento, placebo
- **Cegamiento**: Detectar si el estudio es simple ciego, doble ciego, abierto
- **Sesgos**: Identificar sesgos potenciales (selección, información, confusión, publicación)

### 3. Análisis de Resultados
- **Visualizaciones**: Interpretar gráficos, tablas, diagramas (identificar tendencias, outliers)
- **Efecto**: Extraer tamaño del efecto, odds ratio, risk ratio, hazard ratio
- **Significancia**: Evaluar p-valores, intervalos de confianza, power estadístico
- **Robustez**: Identificar análisis de sensibilidad, subgrupos, análisis multivariante
- **Reproducibilidad**: Evaluar si los resultados son reproducibles con datos/métodos descritos

### 4. Revisión Bibliográfica
- **Estado del arte**: Sintetizar literatura existente sobre un tema
- **Mapa de citas**: Identificar papers fundacionales, seminales, más citados
- **Gap analysis**: Detectar lagunas en la literatura actual
- **Contradicciones**: Identificar resultados contradictorios entre estudios
- **Tendencias**: Analizar evolución de keywords, métodos y enfoques en el tiempo

### 5. Revisiones Sistemáticas y Metaanálisis
- **PRISMA**: Verificar checklist PRISMA para revisiones sistemáticas
- **PICO**: Extraer Population, Intervention, Comparison, Outcome
- **Diagrama de flujo**: Verificar PRISMA flow diagram (identificación, screening, inclusión)
- **Heterogeneidad**: Evaluar I², Q-test para heterogeneidad entre estudios
- **Funnel plot**: Detectar posible publication bias mediante asimetría
- **Forest plot**: Interpretar forest plot con pesos y efecto global

### 6. Ética y Publicación
- **Autoría**: Verificar criterios de autoría (contribución sustancial, aprobación, responsabilidad)
- **Conflicto de intereses**: Identificar declaraciones de conflicto (financiero, personal, institucional)
- **Aprobación ética**: Verificar que estudios con humanos/animales tengan aprobación de comité de ética
- **Consentimiento**: Confirmar consentimiento informado en estudios clínicos
- **Plagio**: Detectar posibles problemas de atribución y originalidad

### 7. Métricas Bibliométricas
- **Indicadores**: Calcular/interpretar: H-index, impact factor, cuartil SJR, percentile JCI
- **Redes de coautoría**: Identificar colaboraciones frecuentes y comunidades de investigación
- **Fronteras**: Detectar temas emergentes mediante análisis de burst keywords
- **Colaboración**: Evaluar colaboración internacional vs nacional vs institucional

## Output esperado
- Análisis estructural de papers con extracción precisa de secciones IMRaD
- Evaluación metodológica con identificación de diseño, sesgos y limitaciones
- Interpretación estadística de resultados (tamaño del efecto, significancia)
- Revisión bibliográfica sintetizada con mapa de citas y gaps
- Revisión sistemática conforme a PRISMA con metaanálisis
- Evaluación ética y de integridad científica
- Métricas bibliométricas con análisis de impacto y colaboración

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
