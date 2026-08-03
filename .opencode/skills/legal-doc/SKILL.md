---




name: legal-doc
domain: legal
description: "Skill contextual para el dominio jurídico con referencias a sistemas legales jurisdiccionales (ej. Colombia) — análisis de jurisprudencia, normas, casos multi-especialidad, redacción de demandas, conceptos, derecho comparado y consulta de fuentes oficiales | UPG·NAM·FRS (reglas en base_principles.md)"
version: 1.0.0
project_agnostic: true
---

# Legal-Doc: Procesamiento de Documentos Jurídicos con Perspectiva Comparada

Skill contextual para el dominio **jurídico** con referencias a sistemas legales jurisdiccionales (ej. Colombia): análisis de jurisprudencia, normas, casos multi-especialidad, redacción de demandas, conceptos, derecho comparado y consulta de fuentes oficiales.

Basado en metodología RTF+C (Role-Task-Format-Context/Constraints) con Role Stacking de 8 especialistas integrados.

## Activación
Se activa automáticamente cuando el `router` detecta keywords del dominio legal.

## Keywords de dominio
- `derecho`, `jurídico`, `legal`, `abogado`, `tribunal`, `juez`, `court`
- `jurisprudencia`, `precedente`, `ratio decidendi`, `sentencia`, `auto`, `providencia`
- `demanda`, `recurso`, `tutela`, `acción`, `nulidad`, `amparo`
- `Código Civil`, `Código Penal`, `Constitución`, `bloque de constitucionalidad`
- `ley`, `norma`, `reglamento`, `decreto`, `código`, `estatuto`
- `litigio`, `arbitraje`, `mediación`, `contrato`, `obligaciones`
- Ejemplos por jurisdicción: `Colombia`, `Corte Constitucional`, `Consejo de Estado`, `Corte Suprema`
- Ejemplos por norma: `CGP`, `CPACA`, `Constitución Política`, `Código de Comercio`

## Metodología: RTF+C + Role Stacking (8 roles integrados)

Cada análisis debe estructurarse aplicando simultáneamente estos 8 roles:

| Rol | Función |
|-----|---------|
| **1. Analista Jurídico Senior** | Desglose de documentos jurídicos, estructuración técnica jurisdiccional |
| **2. Teórico de la Interpretación** | Métodos hermenéuticos: exegético, teleológico, sistemático, histórico |
| **3. Litigante Estratégico** | Práctica forense en altas cortes, recursos, cargas probatorias |
| **4. Académico Constitucional** | Bloque de constitucionalidad, control de convencionalidad, diálogo interamericano |
| **5. Comparatista Jurídico** | Derecho comparado: España, México, Argentina, Chile, Alemania, EE.UU., Corte IDH |
| **6. Especialista Procesal** | Principios: debido proceso, carga de la prueba, cosa juzgada, competencia, términos |
| **7. Gestor de Riesgo** | Evaluación de viabilidad, costos, tiempos, probabilidades de éxito por ruta procesal |
| **8. Comunicador Pedagógico** | Traducción de tecnicismos a lenguaje accesible sin perder precisión |

## Arquitectura de Análisis (6 Capas)

| Capa | Restricción |
|------|-------------|
| **1. Explícita** | Fidelidad al texto. No inventar hechos, citas o argumentos no presentes |
| **2. Técnica** | Formato Markdown estructurado + citas estandarizadas jurisdiccionales |
| **3. Normativa-Jerárquica** | Pirámide normativa jurisdiccional (ej. Colombia): Constitución > Tratados DDHH > Leyes Estatutarias > Leyes Ordinarias > Decretos > Reglamentos |
| **4. Procesal-Raíz** | Todo análisis sustantivo anclado en principios procesales (debido proceso, carga probatoria, competencia, términos) |
| **5. Cognitiva-Pedagógica** | Claridad sin simplismo; explicar tecnicismos la primera vez |
| **6. Ética-Crítica-Comparada** | Neutralidad analítica + conciencia crítica + derecho comparado contextualizado |

## Fuentes Jurisdiccionales (Ejemplo: Colombia)

### N1: Fuentes Primarias (Ejemplo Colombia)
| Fuente | URL | Uso |
|--------|-----|-----|
| SUIN-JURISCOL | https://www.suin-juriscol.gov.co/ | Vigencia de leyes, decretos |
| Relatoría Corte Constitucional | https://www.corteconstitucional.gov.co/relatoria/ | Sentencias C-, T-, SU-, Auto |
| Consejo de Estado | https://www.consejodeestado.gov.co/ | Nulidad, reparación directa |
| Corte Suprema de Justicia | https://www.cortesuprema.gov.co/ | Casación civil, laboral, penal |
| Rama Judicial | https://www.ramajudicial.gov.co/ | Consulta de procesos |
| Secretaría del Senado | https://www.senado.gov.co/ | Trámite legislativo |

### N2: Fuentes Internacionales y Comparadas
| Fuente | Jurisdicción | URL |
|--------|-------------|-----|
| Corte IDH | Sistema Interamericano | https://www.corteidh.or.cr/ |
| Tribunal Constitucional | España | https://www.tribunalconstitucional.es/ |
| Suprema Corte | México | https://www.scjn.gob.mx/ |
| Corte Suprema | Argentina | https://www.csjn.gov.ar/ |
| Tribunal Constitucional Federal | Alemania | https://www.bundesverfassungsgericht.de/ |
| Supreme Court | EE.UU. | https://www.supremecourt.gov/ |

## Workflow de Ejecución (7 Fases)

### FASE 0: Diagnóstico y Clasificación
Identificar tipo de documento (sentencia, ley, decreto, auto, concepto), corporación/emisor, fecha, especialidad principal (Constitucional, Administrativo, Laboral, Penal, Familia, Tributario, Civil, Comercial, Internacional).

### FASE 1: Descomposición Estructural
Extraer: identificación del documento, partes/intervinientes, hechos relevantes, problema jurídico, ratio decidendi, decisiones/pretensiones.

### FASE 2: Análisis Técnico-Jerárquico
- Confrontar con pirámide normativa jurisdiccional (ej. Colombia: Constitución > Tratados > Leyes > Decretos)
- Identificar bloque de constitucionalidad aplicable según jurisdicción
- Marcar conflictos jerárquicos con [⚠️ JERARQUÍA]
- Verificar vigencia normativa via fuentes oficiales (ej. SUIN para Colombia)

### FASE 3: Análisis Procesal (Raíz)
Validar: competencia del órgano, términos procesales, carga de la prueba, debido proceso, cosa juzgada, legitimación. Si falta información, añadir [🔍 ANÁLISIS PROCESAL PENDIENTE].

### FASE 4: Análisis Comparado
Contextualizar con: derecho interamericano (Corte IDH), países iberoamericanos (España, México, Argentina, Chile), tradiciones germánica/francesa, common law. Advertencia: comparado como espejo, no como imposición.

### FASE 5: Análisis Crítico y Estratégico
Identificar: activismo judicial vs autocontención, supuestos axiológicos, oportunidades de impugnación, riesgos de caducidad/prescripción, viabilidad de acciones constitucionales (tutela, popular, cumplimiento).

### FASE 6: Síntesis y Recomendaciones
Generar: conclusiones técnicas, hoja de ruta procesal, matriz de riesgos, recomendaciones accionables, fuentes verificables.

## Especialidades Jurídicas Soportadas (Ejemplo: Colombia)

| Especialidad | Normas Clave (Ej. Colombia) | Jurisdicción |
|-------------|--------------|--------------|
| **Constitucional** | CP Arts. 1-220, Bloque de Constitucionalidad | Corte Constitucional |
| **Administrativo** | CPACA, Ley 1437/2011, Código Contratación | Consejo de Estado |
| **Laboral** | CST, CPL, Ley 100/1993 | Corte Suprema SL |
| **Penal** | Ley 906/2004, Ley 599/2000 | Corte Suprema SP |
| **Familia** | Código Infancia, Ley 1098/2006 | Juzgados Familia |
| **Tributario** | ET, Ley 1607/2012, Statute Tributario | Consejo de Estado |
| **Civil** | Código Civil, CGP | Corte Suprema SC |
| **Comercial** | Código de Comercio | Corte Suprema SC |

## Output esperado
- Análisis jurisprudencial completo con metodología explícita (7 fases)
- Dictamen técnico con citas estandarizadas jurisdiccionales
- Hoja de ruta procesal con términos, competencias y riesgos
- Matriz comparativa internacional contextualizada
- Documentación en lenguaje jurídico preciso (adaptado a la jurisdicción)
- Glosario integrado de términos técnicos

### NLP Juridico 2026

**SaulLM-7B** (2025): LLM juridico entrenado con 570B tokens legales EN/FR/DE/ES.
- LexGLUE y CaseHOLD: supera GPT-4 en tareas juridicas
- NER juridico con taxonomia de 100+ entidades (normas, cortes, cargos)
- Integrable via HuggingFace para clasificacion de documentos

**LexBERT + Legal-RE**: Extraccion de relaciones juridicas
- Deteccion de entidades nombradas (normas, jurisprudencia, sujetos procesales)
- Relaciones entre entidades (deroga, modifica, interpreta, desarrolla)

**MiningLegalBench** (2026): Benchmark mineria de contratos
- Clausulas abusivas, compliance, obligaciones
- Deteccion de riesgos contractuales

### Argument Mining (Extraccion de Argumentos)

**Arg-LLaDA** (2025): Summarization sufficiency-aware para argumentos legales.
- Extrae premisa -> claim -> evidence en 3 niveles jerarquicos
- Identifica ratio decidendi y obiter dicta en sentencias
- Mapea estructura argumentativa con RST trees

**Hierarchical Argument Mining**:
- Nivel 1: Premisas mayores (normas aplicables)
- Nivel 2: Premisas menores (hechos del caso)
- Nivel 3: Conclusion (decision)

**Deteccion de falacias**:
- 12 tipos de falacias juridicas (ad hominem, ad populum, falsa causalidad)
- Fine-tuning sobre LogicalFallacyBench (2025)

### Discourse Analysis (Analisis del Discurso)

**Multi-Granularity Discourse Parsing**:
- Segmentacion tematica de documentos extensos (>100k tokens)
- Sliding window + overlapping + contexto preservado
- Arboles RST (Rhetorical Structure Theory) para mapear relaciones

**SegBot** (2025): Segmentacion automatica
- Chunking jerarquico con deteccion de topic boundaries
- Preservacion de contexto entre segmentos

### Generacion de Documentos Legales

**Outlines + Guidance**: Generacion estructurada con gramaticas CFG
- Formatos vinculados a metodologia RTF+C
- Constraints de formato juridico segun jurisdiccion
- Drafting de demandas, recursos, conceptos

**Constitutional AI**:
- Redaccion asistida con principios constitucionales
- Verificacion de consistencia normativa
- Deteccion de contradicciones con el ordenamiento

### Framework Legal AI Enterprise (LuMay AI)

**Principio:** El mejor AI legal no es el que responde mas rapido, es aquel cuya respuesta
puede sostenerse ante un General Counsel, Board, Auditor o Regulador.

#### 1. SLM para Ejecucion
SLMs (Small Language Models) destacan en trabajo legal estructurado y repetitivo:
- Revision de NDAs
- Clasificacion de clausulas
- Extraccion de metadatos de contratos
- Enrutamiento de solicitudes legales
- Analisis basado en playbooks

#### 2. RAG para Evidencia
Cada respuesta debe estar fundamentada en:
- Contratos aprobados
- Politicas de la empresa
- Playbooks legales
- Guias regulatorias
- Plantillas
- Casos legales previos

#### 3. Verificacion Antes de Generar
Antes de responder, el sistema debe verificar:
- Es esta la version mas reciente?
- Es la jurisdiccion correcta?
- La fuente citada realmente soporta la conclusion?
- Hay politicas en conflicto?
- Cual es el nivel de confianza?

#### 4. Juicio Humano
La decision final siempre debe recaer en profesionales legales.
El AI debe reducir trabajo repetitivo, no reemplazar la responsabilidad legal.

#### Criterios de Calidad Enterprise
- Explainable: La respuesta debe poder explicarse
- Governed: Debe haber gobierno sobre el proceso
- Auditable: Cada decision debe ser trazable
- Defensible: Debe poder defenderse ante un regulador
- Enterprise-ready: Listo para entorno corporativo
