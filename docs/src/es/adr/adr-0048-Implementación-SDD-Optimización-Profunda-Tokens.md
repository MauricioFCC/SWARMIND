# ADR-0048: Implementación de SDD y Optimización Profunda de Tokens (Slurp + Context Hygiene) en SWARMIND

**Estado**: Propuesto (2026-08-19)  
**Fecha**: 2026-08-19  
**Autor**: Ingeniero de Contexto y Python (Visión basada en investigación de frontera)  
**Proyecto**: [SWARMIND](https://github.com/MauricioFCC/SWARMIND)  

---

## Contexto
Tras la exitosa implementación de SDO (Skill Discovery Optimization) en ADR-0047, SWARMIND ha mejorado su precisión de activación y reducido falsos positivos. Sin embargo, la evolución de los sistemas multi-agente de frontera exige un salto metodológico para abordar dos desafíos críticos que limitan la escalabilidad:

1. **Fragilidad en la Composición de Agentes**: La falta de contratos formales entre skills genera comportamientos no deterministas cuando los agentes encadenan herramientas. Se requiere adoptar **SDD (Spec-Driven Development)** tanto a nivel de sistema como de código, donde la especificación (contrato, pre/post-condiciones) sea la fuente única de verdad y guíe la implementación y las pruebas.
2. **Colapso de la Ventana de Contexto (Context Bloat)**: El equipo de Claude Code redujo recientemente el skill `claude-api` de 200k tokens a 25k tokens [[47]]. Este es un ejemplo empírico contundente de que se debe revisar y mantener constantemente el stack de skills o contexto general de los agentes. Sin esta higiene, ciertas consultas pueden disparar la carga completa de ~200k tokens, consumiendo toda la ventana de contexto y degradando severamente el rendimiento y la coherencia del agente [[49]]. Además, se ha documentado que las descripciones de skills mal optimizadas en entornos MCP pueden desperdiciar aproximadamente 25,000 tokens por llamada a herramienta [[37]].

Para mitigar esto de manera científica, se investiga e integra la metodología de [`slurp`](https://github.com/CarlosVallejoRuiz/slurp), un sistema de navegación de grafos consciente del presupuesto de tokens que "sirve exactamente los fideos que tu LLM necesita" [[10]]. Esta metodología logra ahorros medios del 93.3% (hasta 97.1% en casos óptimos) al puntuar nodos de un grafo de conocimiento y seleccionar un subgrafo relevante que se ajuste estrictamente a un presupuesto de tokens definido, en lugar de inyectar archivos o documentación completa de manera indiscriminada [[10]].

---

## Decisión
Se aprueba la refactorización de la arquitectura de skills y el orchestrator de SWARMIND bajo los siguientes 4 pilares fundamentales:

### 1. Adopción de SDD (Spec-Driven Development) para Skills
Todo skill en SWARMIND debe evolucionar de ser un simple documento de instrucciones a un componente con contrato formal. Se exigirá la presencia de un archivo `SKILL.spec.json` (o `SPEC.md`) que defina:
- **`contract`**: Esquema JSON estricto de entrada (argumentos) y salida (formato de respuesta).
- **`preconditions` y `postconditions`**: Estado del sistema o del entorno que debe ser verdadero antes y después de la ejecución.
- **`failing_test`**: Un caso de prueba automatizado que falle inicialmente, alineado con la "Ley de Hierro" de ADR-0047 (*"NO SKILL WITHOUT A FAILING TEST FIRST"*). El agente debe usar el skill para hacer pasar esta prueba.
- El orchestrator validará este contrato antes de permitir la composición o ejecución del skill, rechazando invocaciones que no cumplan las precondiciones.

### 2. Integración del Motor de Navegación de Grafos (Metodología Slurp)
Se implementará un sistema de recuperación de contexto inspirado en `slurp` para el registro de skills de SWARMIND:
- **Grafo de Conocimiento de Skills**: Se generará un `swarmind-skills-graph.json` que mapee los skills como nodos, con aristas que representen relaciones explícitas: `REQUIRED_SUB_SKILL`, `CONFLICTS_WITH` y `ENHANCES`.
- **TokenBudgetRouter**: Ante una consulta del usuario, este router calculará la relevancia semántica (TF-IDF + PageRank estructural) de cada skill y seleccionará un subgrafo óptimo que no exceda un presupuesto estricto (ej. 4,000 tokens), logrando ahorros >90% en la inyección de contexto [[10]].
- **Divulgación Progresiva (Progressive Disclosure)**: El cuerpo completo del skill (código o especificación detallada) solo se inyecta (`--inject-spec`) si el nodo supera un umbral de puntuación de relevancia y el presupuesto de tokens lo permite.

### 3. Higiene de Contexto y Límites Estrictos (Lección Claude Code)
Para evitar el destino del skill `claude-api`, se establecen políticas de mantenimiento obligatorias:
- **Hard Caps**: Se establece un límite máximo de 5,000 tokens por skill individual y un techo global de 25,000 tokens para todo el stack de skills inyectados por sesión de agente [[55]].
- **Auditoría Continua**: Se crea `scripts/audit_context.py`, que se ejecuta en el pipeline de CI/CD para medir el peso exacto de cada skill (vía `tiktoken`), identificar "skills zombis" (baja activación, alto costo) y forzar la división de skills monolíticos en archivos `core.md` (esencial) y `advanced.md` (carga bajo demanda).

### 4. Validador Extendido (`scripts/validate_skills.py`)
El script de validación se actualiza para exigir:
- Presencia y validez de `SKILL.spec.json`.
- Que la estimación de tokens del skill no exceda los límites definidos (5,000 tokens).
- Mantenimiento de la regla SDO: la `description` en el registro debe comenzar con "Usar cuando..." y **nunca** resumir el workflow, para evitar que el agente se salte el cuerpo del skill [[47]].

---

## Consecuencias

### Positivas
- **Confiabilidad y Determinismo**: SDD garantiza que los agentes respeten contratos claros, reduciendo drásticamente las alucinaciones y los errores en cascada durante la composición de habilidades.
- **Eficiencia Extrema de Tokens**: La navegación tipo `slurp` reduce la carga de contexto en >90%, permitiendo ventanas de conversación más largas para el historial del usuario, menor latencia y reducción directa de costos de API [[10]].
- **Sostenibilidad a Largo Plazo**: Los límites estrictos y la auditoría continua previenen el "context bloat", asegurando que SWARMIND escale a cientos de skills sin colapsar la ventana de contexto, tal como lo demostró la optimización de Claude Code [[47]].

### Negativas
- **Curva de Aprendizaje**: Los desarrolladores y colaboradores deberán escribir especificaciones formales (`SKILL.spec.json`), lo que añade un paso inicial de rigor al desarrollo de nuevos skills.
- **Overhead de Indexación**: Mantener el grafo de skills actualizado requiere un proceso de indexación. Esto se mitigará implementando una re-indexación inteligente (`--smart`) que solo procese archivos modificados y sus dependencias, similar a la implementación original de `slurp` [[10]].

---

## Alternativas Consideradas
1. **Confiar únicamente en Prompt Caching de la API**: *RECHAZADO*. Aunque reduce costos de cómputo en la API, no resuelve el problema de ruido semántico ni el agotamiento de la ventana de contexto por sesión, que es el cuello de botella real en agentes complejos que pierden el hilo conductor [[45]].
2. **Mantener el enfoque actual de SDO sin SDD ni Grafos**: *RECHAZADO*. SDO optimiza el disparo inicial, pero no garantiza la corrección del comportamiento ni resuelve el problema catastrófico de cargar skills monolíticos que pueden consumir hasta 200k tokens [[49]].
3. **Adoptar el framework `slurp` completo como dependencia externa**: *RECHAZADO*. Se extraerán los patrones algorítmicos (scoring, presupuesto, grafo) para implementarlos de forma nativa y ligera en Python dentro de SWARMIND, evitando dependencias innecesarias y manteniendo el principio KISS.

---

## Plan de Implementación (Commit)
`FEAT` — Estructura SDD (`SKILL.spec.json`, contratos), integración de `TokenBudgetRouter` (metodología slurp adaptada), `scripts/audit_context.py` con límites estrictos (5k/skill, 25k total), y actualización del validador para exigir specs y métricas de tokens.

---
*Nota de visión*: La ingeniería de contexto no se trata de darle *más* información al LLM, sino de darle *la información exacta* en el momento preciso. Tratar el contexto como un recurso finito y caro, y los skills como microservicios con contratos SDD, es lo que separa a los prototipos de juguete de los sistemas de producción robustos como SWARMIND.