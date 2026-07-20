# Glosario de Terminos y Abreviaturas

> Referencia rapida de abreviaturas, terminos y frameworks del proyecto AGENTIC Harness.
> Version del sistema: 2026-07-20

---

## Abreviaturas del Sistema

| Abreviatura | Significado | Descripcion |
|-------------|-------------|-------------|
| ADR | Architecture Decision Record | Decision arquitectonica documentada con contexto, decision y consecuencias |
| WAL | Write-Ahead Log | Log de operaciones con soporte de retry y cancelacion para tolerancia a fallos |
| MCP | Model Context Protocol | Protocolo estandarizado de contexto para interaccion con LLMs (spec v2025-11-25) |
| HITL | Human In The Loop | Supervision humana obligatoria para acciones criticas o de alto riesgo |
| DAG | Directed Acyclic Graph | Grafo aciclico dirigido utilizado por TaskPlanner para representar subtareas |
| KPI | Key Performance Indicator | Metricas de rendimiento de agentes: exito, duracion, uso de tokens |
| RAG | Retrieval Augmented Generation | Generacion aumentada por recuperacion de conocimiento externo |
| TTL | Time To Live | Tiempo de vida maximo de entradas en cache antes de su evacuacion |
| LRU | Least Recently Used | Politica de evacuacion de cache basada en accesos menos recientes |
| PBT | Property-Based Testing | Testing basado en propiedades en lugar de ejemplos concretos |
| WFP | Workflow Pattern | Patron de flujo de trabajo reutilizable para orquestacion de tareas |
| SSOT | Single Source of Truth | Principio de una unica fuente de verdad para cada dato del sistema |
| CB | Circuit Breaker | Interruptor de circuito que previene llamadas repetidas a componentes fallidos |
| FDE | Forward Deployment Engineering | Ingenieria que prioriza despliegues incrementales con validacion continua |
| CQE | Core Quant Engine | Motor cuantitativo central implementado en Rust para computacion de alta perfomance |
| TCA | Transaction Cost Analysis | Analisis de costos de transaccion para optimizacion de ejecuciones |
| FSM | Finite State Machine | Maquina de estados finitos para modelar ciclos de vida de tareas y agentes |
| LC | Line Count | Conteo de lineas por archivo, con limite riguroso de <900 |
| DoD | Definition of Done | Criterios que una tarea debe cumplir para considerarse completada |
| YAGNI | You Ain't Gonna Need It | Principio de no anadir funcionalidad hasta que sea estrictamente necesaria |
| DRY | Don't Repeat Yourself | Principio de evitar duplicacion de logica y datos |
| KISS | Keep It Simple, Stupid | Principio de diseno que prioriza la simplicidad sobre la complejidad innecesaria |
| TDAD | Test-Driven AI Agent Definition | Definicion de agentes de IA guiada por tests desde el diseno inicial |
| TDFlow | Test-Driven Flow | Flujo iterativo SWE donde los tests guian la correccion y evolucion |
| PaCoRe | Parallel Coordination + RL | Patron de coordinacion paralela con refuerzo por paso de mensajes |
| PROBE | Probing Robustness Evaluation | Evaluacion de robustez mediante sondeos adversariales estructurados |
| SMART | Structured Mutation & Resilience Test | Mutacion inteligente para verificar tolerancia a fallos |
| CEN | Critical Error Neutralization | Neutralizacion de errores criticos mediante fallos controlados |
| BTR | Behavioral Trace Recorder | Registro de trazas de comportamiento para depuracion y auditoria |
| AGR | Architectural Guardrails | Barandillas arquitectonicas que previenen violaciones de diseno |
| SVE | Structured Validation Engine | Motor de validacion estructurada de invariantes del sistema |

---

## Terminos del Sistema

| Termino | Definicion |
|---------|------------|
| Agente | Entidad autonoma con un rol especifico (coordinator, builder, scientist, guardian, evolve) que ejecuta tareas dentro del harness |
| Harness | Motor de ejecucion multi-agente que orquesta, monitoriza y gestiona el ciclo de vida de agentes y tareas |
| Skill | Conocimiento especializado cargable por un agente, definido en YAML y registrado en el SkillRouter |
| Session | Contexto de ejecucion de una tarea que mantiene estado, historial y resultados parciales |
| Plan | DAG de subtasks generado por TaskPlanner a partir de una tarea compleja |
| Debate | Discusion multi-agente estructurada (consenso, critica, deliberacion) para mejorar calidad de respuestas |
| Self-Healing | Recuperacion automatica ante fallos mediante reintentos, circuit breakers y failover |
| Federated Memory | Memoria compartida entre proyectos/agentes mediante LanceDB con incrustaciones semanticas |
| Token Economics | Gestion de presupuesto de tokens LLM con caching, compresion y priorizacion |
| Dynamic Scaling | Ajuste automatico del numero de agentes segun complejidad de la tarea y carga del sistema |
| Context Window | Ventana de contexto que gestiona el historial de mensajes con limites de tokens y antiguedad |
| ShapedCache | Cache con politicas configurables (TTL, LRU, umbrales de similitud) optimizada por forma de acceso |
| Structured Compaction | Tecnica de compresion estructurada de contexto que reduce uso de tokens hasta 41% |
| Agent Bus | Bus de mensajes interno para comunicacion entre agentes con canales, suscripciones y circuit breaker |
| Write-Ahead Log | Registro de operaciones pendientes con capacidad de retry y cancelacion para garantizar consistencia |
| TaskOrchestrator | Orquestador central que coordina planificacion, despacho, ejecucion y consolidacion de tareas |
| Skill Router | Enrutador de skills que selecciona el skill adecuado segun similitud semantica y disponibilidad |
| Lazy Loading | Carga diferida de modulos (PEP 562) que reduce cold start de 2800ms a 39ms (72x mas rapido) |
| Circuit Breaker | Mecanismo de tolerancia a fallos que abre el circuito tras N fallos consecutivos |
| Confidence Score | Puntuacion de confianza (0.0-1.0) que cada agente asigna a sus respuestas |
| KPI Tracker | Sistema de metricas que registra rendimiento de agentes, sesiones y skills en LanceDB |
| Federated Learning | Aprendizaje federado opcional para mejorar modelos sin centralizar datos |
| MCP Client | Cliente del Model Context Protocol para interaccion estandarizada con LLMs externos |
| Semantic Cache | Cache semantica que permite recuperar entradas similares aunque no identicas |
| Behavioral Trace | Traza de comportamiento que registra acciones, decisiones y resultados de agentes |
| Architectural Guardrail | Barandilla arquitectonica que valida invariantes estructurales del sistema |
| Workflow Pattern | Patron de flujo de trabajo reutilizable (lineal, paralelo, condicional, bucle, etc.) |
| Property-Based Test | Test que verifica propiedades invariantes del sistema con entradas generadas aleatoriamente |
| Harness Effect | Efecto de retroalimentacion positiva donde el harness mejora la calidad de los agentes que lo usan |
| Failure-Spend Governance | Gobernanza que limita el gasto de recursos en fallos mediante presupuestos por error |
| Cache-Shape Discipline | Disciplina que adapta la configuracion de cache a los patrones de acceso observados |

---

## Papers y Frameworks 2026 Referenciados

| Nombre | Tipo | Referencia |
|--------|------|------------|
| PaCoRe | Patron de coordinacion | Parallel Coordination + RL message-passing para concurrencia multi-agente |
| Agent Capsules | Arquitectura | arXiv:2605.00410 — Reduccion de tokens en 51% mediante capsulas de agente |
| Meta-Agent | Framework | arXiv:2605.25233 — Verificacion DAG y orquestacion con meta-agentes |
| ShapedCache | Tecnica de cache | Mojentum 2026 — Reduccion de tokens en 38% con cache por forma de acceso |
| Structured Compaction | Tecnica de compresion | Struct47, LAS51 — Reduccion de tokens en 41% mediante compresion estructurada |
| Legal2LogicICL | Framework NLP | arXiv:2604.11699 — Procesamiento de lenguaje juridico con in-context learning |
| Visual-SDPO | Tecnica de generacion UI | arXiv:2606.10334 — Generacion de interfaces de usuario por preferencias difusas |
| MCP Protocol | Estandar de contexto | spec v2025-11-25 — Model Context Protocol para interaccion LLM estandarizada |
| TDAD | Metodologia de desarrollo | Test-Driven AI Agent Definition — Definicion de agentes guiada por tests |
| TDFlow | Metodologia de desarrollo | Test-Driven Flow — Flujo iterativo SWE con tests como guia |
| PROBE | Tecnica de testing | Probing Robustness Evaluation — Evaluacion adversarial estructurada |
| AdverTest | Tecnica de testing | Adversarial Test Loop — Bucle adversarial para descubrir vulnerabilidades |
| SMART Mutation | Tecnica de testing | Structured Mutation & Resilience Test — Mutacion inteligente de codigo |
| FuzzAgent | Tecnica de testing | Agente fuzzing para generacion de entradas limite y esquina |
| AlphaCFG | Tecnica de analisis | Alpha Control Flow Graph — Analisis estatico de flujo de control con RL |
| PIKAN | Tecnica numerica | Physics-Informed Kolmogorov-Arnold Networks — Redes neuronales con conocimiento fisico |
| MeanFieldControl | Teoria de control | Control de campo medio para optimizacion de sistemas multi-agente |
| MuTON | Arquitectura RL | Multi-Task Offline Network — Red fuera de linea para multiples tareas |
| SWE-Master | Framework SWE | Software Engineering Master — Automatizacion integral de ingenieria de software |
| ShapleyFlow | Tecnica de atribucion | Atribucion de contribucion basada en valores Shapley para flujos de trabajo |
| MetaClaw | Arquitectura agente | Agente metamorfico con capacidades de auto-reconfiguracion |
| AdaptOrch | Framework orquestacion | Orquestador adaptativo con planificacion dinamica de recursos |

---

## Convenciones de Nomenclatura

| Prefijo | Significado | Ejemplo |
|---------|-------------|---------|
| `test_` | Archivo/funcion de test | `test_agent_bus.py` |
| `mock_` | Objeto simulador para tests | `mock_vector_store.py` |
| `ADR-` | Architecture Decision Record | `ADR-0018-token-economics-cache-shape.md` |
| `ERR_` | Codigo de error estructurado | `ERR_AGENT_NOT_FOUND` |
| `DOC_` | Directiva de documentacion | `DOC_ES_UTF8` |

---

> **Nota:** Este glosario se actualiza conforme evoluciona el proyecto. Las referencias a papers 2026 incluyen contribuciones del estado del arte integradas en el sistema.
