# NLP Jurídico, Argument Mining y Framework Enterprise — detalle bajo demanda

> Migrado a `references/` por politica "focused beats comprehensive" (SkillsBench 2026).
> El workflow de 7 fases y las reglas de citas permanecen en `SKILL.md`; aqui vive
> la frontera de NLP legal 2026, la extraccion de argumentos y el framework enterprise.

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
