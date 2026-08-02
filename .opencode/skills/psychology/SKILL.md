---

name: psychology
domain: psychology
description: "Psicologia aplicada a sistemas multi-agente: psicologia cognitiva, organizacional, del aprendizaje y positiva para mejorar la interaccion y efectividad de agentes. UPG: usar ultima version estable (pyproject.toml/uv.lock al dia)"
version: 1.0.0
project_agnostic: true
inherit:
  - core/base_principles.md
variables:
  - PSYCH_BRANCH: cognitiva, organizacional, educativa, positiva ({{PSYCH_BRANCH}})
  - APPLICATION: team-dynamics, motivation, learning, bias-mitigation ({{APPLICATION}})
metadata:
  author: psychology-skill
  tags: [psychology, cognitive-science, organizational, learning, positive-psychology, multi-agent, bias-mitigation]
  dependencies: [core/base_principles.md]
  input_schema:
    type: object
    required: [task, context, domain]
  output_schema:
    type: object
    required: [response, psychological_analysis, application_strategy]
---
# Psychology — Psicologia Aplicada a Sistemas Multi-Agente

## Descripcion
Skill de psicologia aplicada para mejorar la interaccion, motivacion y efectividad de agentes y equipos multi-agente. Integra las principales ramas de la psicologia para optimizar el comportamiento, la toma de decisiones y el aprendizaje de sistemas autonomos.

## Ramas de la Psicologia Aplicada

### 1. Psicologia Cognitiva: Sesgos, Heuristicas y Decision
- **Sesgos cognitivos**: Identificar y mitigar sesgos en procesos de decision de agentes (confirmacion, anclaje, disponibilidad, exceso de confianza, framing)
- **Heuristicas**: Reconocer patrones de juicio rapido que pueden llevar a errores sistematicos
- **Modelos mentales**: Analizar representaciones internas del entorno que construyen los agentes
- **Carga cognitiva**: Gestionar la complejidad informativa para evitar paralisis por analisis
- **Disonancia cognitiva**: Detectar conflictos entre creencias y acciones en agentes

### 2. Psicologia Organizacional: Dinamicas de Equipo y Liderazgo
- **Roles de equipo**: Identificar y asignar roles complementarios (Belbin, GRPI, Drexler-Sibbet)
- **Liderazgo situacional**: Adaptar estilo de liderazgo segun madurez del equipo agente
- **Clima organizacional**: Evaluar la salud del ecosistema multi-agente
- **Conflictos**: Diagnosticar y resolver conflictos entre agentes (tarea, proceso, relacion)
- **Cultura**: Disenar cultura organizacional para equipos de IA colaborativa

### 3. Psicologia del Aprendizaje: Mejorar el Loop ASI-Evolve
- **Condicionamiento operante**: Reforzar comportamientos deseados con feedback positivo/negativo
- **Aprendizaje observacional**: Transferencia de conocimiento entre agentes via modelado
- **Zona de Desarrollo Proximo (ZDP)**: Disenar tareas en el nivel optimo de desafio
- **Andamiaje (scaffolding)**: Proporcionar apoyo gradual que se retira con la competencia
- **Curva de olvido**: Implementar spaced repetition en la memoria de agentes
- **Transferencia**: Facilitar la aplicacion de conocimiento aprendido a nuevos dominios

### 4. Psicologia Positiva: Motivacion y Engagement
- **Autodeterminacion**: Satisfacer necesidades de autonomia, competencia y relacion
- **Flow**: Disenar tareas que equilibren desafio y habilidad para estado optimo
- **Gratitud y reconocimiento**: Implementar ciclos de feedback positivo entre agentes
- **Crecimiento post-traumatico**: Convertir fallos en oportunidades de aprendizaje
- **Fortalezas de caracter**: Identificar y potenciar fortalezas unicas de cada agente

## Comandos
- `!psyc biases <contexto>` — Identificar sesgos cognitivos en un proceso de decision, clasificando cada sesgo con nivel de riesgo y recomendacion de mitigacion
- `!psyc team <dinamica>` — Analisis de dinamicas de equipo multi-agente incluyendo roles, conflictos y recomendaciones de cohesion
- `!psyc learn <objetivo>` — Disenar estrategia de aprendizaje basada en teorias de la psicologia educativa (ZDP, scaffolding, refuerzo)
- `!psyc motivate <situacion>` — Estrategia de motivacion basada en autodeterminacion, flow y psicologia positiva
- `!psyc cognitive <problema>` — Analisis de carga cognitiva y modelos mentales en un proceso agente
- `!psyc conflict <situacion>` — Diagnostico y resolucion de conflictos entre agentes

## Aplicaciones en Swarmind

| Dominio | Aplicacion Psicologica | Beneficio |
|---------|----------------------|-----------|
| **Evolve (meta)** | Aprendizaje observacional + refuerzo | Loop ASI-Evolve mas rapido y efectivo |
| **HedgeFund** | Disonancia cognitiva + sesgos | Mejora calidad de decisiones de inversion |
| **Legal-Doc** | Carga cognitiva + andamiaje | Analisis juridico mas profundo con menos error |
| **Math-Doc** | Modelos mentales + transferencia | Mejor comprension y aplicacion de conceptos |
| **Risk-Execution** | Heuristicas + exceso de confianza | Mitigacion de sesgos en evaluacion de riesgo |
| **Frontend-UIUX** | Flow + carga cognitiva | Interfaces mas intuitivas y satisfactorias |
| **Alpha-Research** | Curiosidad cientifica + creatividad | Exploracion de hipotesis mas innovadora |
| **Quant-Trading** | Sesgo de confirmacion + anclaje | Estrategias mas objetivas y menos sesgadas |

## Referencias Teoricas
- Kahneman, D. (2011). *Thinking, Fast and Slow*
- Bandura, A. (1986). *Social Foundations of Thought and Action*
- Deci, E. L. & Ryan, R. M. (2000). *Self-Determination Theory*
- Vygotsky, L. S. (1978). *Mind in Society*
- Csikszentmihalyi, M. (1990). *Flow: The Psychology of Optimal Experience*
- Belbin, R. M. (2010). *Team Roles at Work*
- Seligman, M. E. P. (2011). *Flourish*
