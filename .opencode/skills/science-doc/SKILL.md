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
