---
name: education
domain: education
description: "Ciencias de la educacion: diseno instruccional, pedagogia, andragogia, taxonomia de Bloom, microlearning, y evaluacion educativa."
version: 1.0.0
project_agnostic: true
inherit:
  - core/base_principles.md
variables:
  - LEARNER_TYPE: child, adolescent, adult, senior ({{LEARNER_TYPE}})
  - INSTRUCTIONAL_MODEL: ADDIE, SAM, Agile, Backward-Design ({{INSTRUCTIONAL_MODEL}})
metadata:
  author: education-skill
  tags: [education, instructional-design, pedagogy, andragogy, bloom-taxonomy, microlearning, assessment, curriculum]
  dependencies: [core/base_principles.md]
  input_schema:
    type: object
    required: [task, context, domain]
  output_schema:
    type: object
    required: [response, instructional_design, assessment_strategy]
---
# Education — Ciencias de la Educacion

## Descripcion
Skill de ciencias de la educacion para diseno instruccional, pedagogia y evaluacion. Proporciona marcos teoricos y metodologias para disenar experiencias de aprendizaje efectivas para humanos y sistemas multi-agente.

## Modelos de Diseno Instruccional

### 1. ADDIE — Modelo Clasico
| Fase | Descripcion | Output |
|------|-------------|--------|
| **Analisis** | Identificar necesidades, contexto, audiencia, recursos | Learner profile, gap analysis, requisitos |
| **Diseno** | Definir objetivos, secuencia, estrategias, medios | Storyboard, blueprint instruccional |
| **Desarrollo** | Crear contenidos, actividades, evaluaciones | Materiales, modulos, rúbricas |
| **Implementacion** | Entregar la instruccion en el entorno target | Sesion facilitada, plataforma activa |
| **Evaluacion** | Medir efectividad (reaccion, aprendizaje, transferencia, resultados) | Kirkpatrick levels, ROI, mejora continua |

### 2. SAM — Successive Approximation Model
- **Iterativo**: Prototipado rapido con ciclos de evaluacion continua
- **Savvy Start**: Sesion intensiva inicial para definir alcance y prototipo
- **Alpha/Beta/Gold**: Versiones progresivas con validacion en cada etapa
- **Aplicacion**: Proyectos con requisitos cambiantes o plazos ajustados

### 3. Agile Learning Design
- **Sprints de diseno**: Entregas incrementales de modulos de aprendizaje
- **Backlog pedagogico**: Priorizar objetivos de aprendizaje por valor
- **Retrospectivas**: Mejora continua del proceso instruccional
- **User stories de aprendizaje**: "Como [aprendiz], quiero [objetivo] para [motivo]"

### 4. Backward Design (Wiggins & McTighe)
```
1. Identificar resultados deseados → 2. Determinar evidencias aceptables → 3. Planificar experiencias
```
- **Etapa 1**: Objetivos duraderos, comprensiones esenciales, preguntas guia
- **Etapa 2**: Desempeno autentico, evaluacion formativa, rúbricas
- **Etapa 3**: Secuencia de aprendizaje, actividades, recursos

## Taxonomia de Bloom Revisada (Anderson & Krathwohl, 2001)

| Nivel | Proceso Cognitivo | Verbos Clave | Ejemplo de Objetivo |
|-------|------------------|--------------|---------------------|
| **Recordar** | Reconocer, recordar | Definir, listar, nombrar | "El agente recordara los 3 tipos de sesgos cognitivos" |
| **Comprender** | Interpretar, ejemplificar, clasificar | Explicar, resumir, comparar | "El agente explicara como funciona el sesgo de confirmacion" |
| **Aplicar** | Ejecutar, implementar | Usar, demostrar, resolver | "El agente aplicara tecnicas de mitigacion de sesgos en decisiones reales" |
| **Analizar** | Diferenciar, organizar, atribuir | Analizar, distinguir, examinar | "El agente analizara una decision previa e identificara sesgos presentes" |
| **Evaluar** | Verificar, criticar | Evaluar, justificar, argumentar | "El agente evaluara la efectividad de diferentes estrategias de mitigacion" |
| **Crear** | Generar, planificar, producir | Disenar, desarrollar, proponer | "El agente disenara un protocolo de decision libre de sesgos" |

## Andragogia — Principios de Aprendizaje Adulto (Knowles)

| Principio | Implicacion para Diseno |
|-----------|------------------------|
| **Autoconcepto** | Aprendices auto-dirigidos; disenar opciones y autonomia |
| **Experiencia** | Aprovechar experiencia previa como recurso de aprendizaje |
| **Disposicion** | Aprender cuando necesitan saber; justificar relevancia |
| **Orientacion** | Aprendizaje centrado en problemas, no en contenidos |
| **Motivacion** | Motivacion intrinseca > extrinseca; conectar con metas personales |

## Microlearning y Spaced Repetition

### Microlearning
- **Duracion**: 2-7 minutos por modulo
- **Formato**: Videos cortos, infografias, quizzes, flashcards
- **Enfoque**: Un solo objetivo de aprendizaje por modulo
- **Contexto**: Just-in-time, mobile-first, embedded en workflow

### Spaced Repetition (Ebbinghaus Curve)
```
Intervalos optimos: 1 dia → 7 dias → 16 dias → 35 dias
```
- **Leitner System**: Tarjetas en cajones segun nivel de dominio
- **SM-2 Algorithm**: Base del algoritmo de Anki para espaciado optimo
- **Aplicacion en agentes**: Cache de conocimiento con prioridad por frecuencia de uso y tasa de error

## Evaluacion Educativa

### Tipos de Evaluacion
| Tipo | Proposito | Ejemplos |
|------|-----------|----------|
| **Diagnostica** | Conocer estado inicial | Pre-test, encuesta de conocimientos previos |
| **Formativa** | Monitorear progreso durante el aprendizaje | Quices, tareas, discusiones, feedback continuo |
| **Sumativa** | Medir logro al finalizar | Examen final, proyecto integrador, portafolio |
| **Autentica** | Evaluar desempeno en contexto real | Simulaciones, estudios de caso, proyectos reales |

### Niveles de Kirkpatrick
1. **Reaccion**: Satisfaccion del aprendiz con la experiencia
2. **Aprendizaje**: Adquisicion de conocimientos, habilidades, actitudes
3. **Transferencia**: Aplicacion en el entorno real de trabajo
4. **Resultados**: Impacto organizacional (ROI, productividad, calidad)

## Comandos
- `!edu design <objetivo>` — Diseno instruccional completo con el modelo seleccionado (ADDIE por defecto)
- `!edu bloom <nivel>` — Generar objetivos de aprendizaje segun taxonomia de Bloom para un nivel especifico
- `!edu micro <tema>` — Disenar modulo de microlearning con estructura, duracion y actividades
- `!edu assess <contenido>` — Disenar evaluacion diagnostica, formativa y sumativa
- `!edu lesson <tema>` — Plan de clase/secuencia didactica completa
- `!edu andragogy <objetivo>` — Diseno andragogico para aprendizaje de adultos

## Aplicaciones en AGENTIC

| Contexto | Aplicacion Educativa | Beneficio |
|----------|---------------------|-----------|
| **Evolve** | Microlearning + spaced repetition | Mejora retencion de lecciones aprendidas |
| **Psicologia** | ZDP + scaffolding | Aprendizaje progresivo de competencias |
| **Alpha-Research** | Bloom analizar/crear | Investigacion mas profunda y generativa |
| **Legal-Doc** | Evaluacion formativa | Feedback continuo en calidad juridica |
| **HealthTech** | Andragogia para profesionales | Capacitacion medica efectiva |
| **Frontend-UIUX** | Diseno instruccional para UX | Onboarding de usuarios optimizado |

## Referencias Teoricas
- Anderson, L. W. & Krathwohl, D. R. (2001). *A Taxonomy for Learning, Teaching, and Assessing*
- Knowles, M. S. (1980). *The Modern Practice of Adult Education*
- Wiggins, G. & McTighe, J. (2005). *Understanding by Design*
- Kirkpatrick, D. L. & Kirkpatrick, J. D. (2006). *Evaluating Training Programs*
- Ebbinghaus, H. (1885). *Memory: A Contribution to Experimental Psychology*
- Allen, M. W. (2016). *Michael Allen's Guide to e-Learning*
