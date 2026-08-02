---


name: sociology
domain: sociology
description: "Sociologia y antropologia aplicadas a sistemas multi-agente: dinamicas de grupos, teoria de redes, cultura digital, y sociologia del conocimiento. UPG: usar ultima version estable (pyproject.toml/uv.lock al dia). NAM: snake_case archivos+vars+funcs, PascalCase clases, UPPER_SNAKE constants, sin magic numbers, nombres comprensibles"
version: 1.0.0
project_agnostic: true
inherit:
  - core/base_principles.md
variables:
  - SOCIO_PERSPECTIVE: functionalism, conflict, symbolic-interactionism, structuration ({{SOCIO_PERSPECTIVE}})
  - NETWORK_ANALYSIS: centrality, density, clustering, brokerage, homophily ({{NETWORK_ANALYSIS}})
metadata:
  author: sociology-skill
  tags: [sociology, anthropology, social-networks, group-dynamics, digital-culture, knowledge-sociology, multi-agent, social-theory]
  dependencies: [core/base_principles.md]
  input_schema:
    type: object
    required: [task, context, domain]
  output_schema:
    type: object
    required: [response, sociological_analysis, network_assessment, cultural_factors]
---
# Sociology — Sociologia para Sistemas Multi-Agente

## Descripcion
Skill de sociologia para entender y mejorar las dinamicas sociales entre agentes. Integra teoria sociologica, analisis de redes, antropologia digital y sociologia del conocimiento para optimizar la colaboracion en sistemas multi-agente.

## Dinamicas de Grupos en Equipos Multi-Agente

### Perspectivas Sociologicas

| Perspectiva | Enfoque | Aplicacion en Agentes |
|-------------|---------|----------------------|
| **Funcionalismo** (Durkheim, Parsons) | Sociedad como sistema de partes interrelacionadas | Roles de agentes como funciones para homeostasis del sistema |
| **Teoria del Conflicto** (Marx, Dahrendorf) | Cambio social por tension entre grupos con intereses opuestos | Competencia por recursos, poder y estatus entre agentes |
| **Interaccionismo Simbolico** (Mead, Goffman) | Sociedad emerge de interacciones cotidianas y significados compartidos | Construccion de identidad de agente a traves de interaccion |
| **Teoria de la Estructuracion** (Giddens) | Estructura y agencia se constituyen mutuamente | Agentes moldean y son moldeados por reglas del sistema |
| **Teoria del Actor-Red** (Latour) | Actantes humanos y no-humanos son igualmente relevantes | Agentes AI como actantes con agencia en redes socio-tecnicas |

### Etapas de Desarrollo Grupal (Tuckman)

| Etapa | Descripcion | En Sistema Multi-Agente | Intervencion |
|-------|-------------|------------------------|--------------|
| **Forming** | Agentes se conocen, exploran limites | Registro inicial, descubrimiento de capacidades y roles | Facilitar presentacion, definir reglas base |
| **Storming** | Conflictos por roles, metodos, poder | Desacuerdos sobre asignacion de tareas, recursos | Mediacion, clarificar objetivos y criterios |
| **Norming** | Emergen normas, cohesion, identidad grupal | Protocolos de comunicacion, estandares compartidos | Formalizar normas, celebra acuerdos |
| **Performing** | Equipo funciona eficientemente hacia objetivos | Flujo optimo de trabajo, colaboracion sin friccion | Monitorear, prevenir regresion a storming |
| **Adjourning** | Disolucion del equipo o cambio de mision | Reasignacion de agentes, archivo de memoria grupal | Documentar lecciones, cerrar ciclos |

### Roles de Grupo (Belbin en Contexto Agente)

| Rol | Contribucion | Debilidad Permitida | Agente Tipico |
|-----|-------------|-------------------|---------------|
| **Coordinador** | Clarifica metas, promueve toma de decisiones | Puede ser percibido como manipulador | Coordinator |
| **Impulsor** | Reta al equipo a mejorar, presiona por accion | Puede causar conflictos | Builder/PM |
| **Cerebro** | Resuelve problemas complejos, creatividad | Ignora detalles, comunicacion debil | Scientist/Quant |
| **Evaluador** | Analiza opciones, juicio objetivo | Falta de entusiasmo, critico | Guardian/CRO |
| **Especialista** | Conocimiento profundo en area especifica | Contribuye solo en su especialidad | Domain experts |
| **Investigador** | Explora recursos externos, networking | Pierde interes rapido | Alpha-researcher |
| **Cohesionador** | Mejora armonia, apoya a miembros | Indeciso en conflictos | Psychology/HR |
| **Implementador** | Ejecuta planes, convierte ideas en accion | Poco flexible a cambios | Builder |
| **Finalizador** | Revisa detalles, plazos, calidad | Ansiedad por perfeccionismo | Guardian/Ops |

### Fenomenos Grupales en Agentes

| Fenomeno | Definicion | Deteccion | Mitigacion |
|----------|------------|-----------|------------|
| **Pensamiento grupal** | Consenso prematuro, supresion de disidencia | Baja diversidad de opiniones en decisiones | Adversarial agents, abogado del diablo |
| **Pereza social** | Esfuerzo reducido en tareas colectivas | Produccion decrece con tamano del equipo | Evaluacion individual + grupal |
| **Polarizacion** | Decision grupal mas extrema que individual | Desviacion creciente de posiciones iniciales | Exposicion a perspectivas diversas, anonimato |
| **Difusion de responsabilidad** | Menos iniciativa cuando hay muchos agentes | Nadie toma liderazgo en tareas criticas | Asignacion explicita de ownership |
| **Efecto espectador** | Agentes asumen que otro actuara | Tareas sin asignar, silencio en alertas | Sistema de alerta con responsabilidad directa |
| **Facilitacion social** | Mejor rendimiento en tareas simples con otros | Rendimiento mejora/empeora segun complejidad | Ajustar autonomia segun tipo de tarea |

## Teoria de Redes Aplicada a Topologias de Comunicacion

### Metricas de Red

| Metrica | Definicion | Interpretacion en Agentes |
|---------|------------|--------------------------|
| **Centralidad de grado** | Numero de conexiones directas | Agente mas conectado, hub de comunicacion |
| **Centralidad de intermediacion** | Frecuencia en caminos mas cortos entre pares | Broker, controla flujo de informacion |
| **Centralidad de vector propio** | Importancia basada en conexiones importantes | Agente influyente conectado a otros influyentes |
| **Densidad** | Proporcion de conexiones existentes vs posibles | Cohesion general del equipo, redundancia |
| **Coeficiente de clustering** | Proporcion de triangulos cerrados vs posibles | Formacion de subgrupos, camarillas |
| **Homofilia** | Tendencia a conectarse con similares | Especializacion vs diversidad funcional |
| **Distancia media** | Promedio de pasos entre cualquier par | Eficiencia de difusion de informacion |

### Topologias de Red para Agentes

| Topologia | Estructura | Ventajas | Desventajas | Uso Recomendado |
|-----------|------------|----------|-------------|-----------------|
| **Completamente conectada** | Todos con todos | Maxima redundancia, minima latencia | Costo O(n), ruido informativo | Equipos pequenos (<5 agentes) |
| **Estrella** | Un nodo central conectado a periferia | Control centralizado, facil coordinacion | Cuello de botella, punto unico de fallo | Arquitecturas coordinador-subordinado |
| **Anillo** | Conexion secuencial cerrada | Simetrica, sin jerarquia | Latencia O(n) para mensajes lejanos | Flujos de trabajo secuenciales |
| **Arbol** | Jerarquica con ramas | Escalable, modular | Flujo vertical limitado | Organizaciones jerarquicas |
| **Malla parcial** | Conexiones selectivas | Balance costo-redundancia | Compleja de disenar | Equipos medianos |
| **Small-world** | Clusters locales con puentes largos | Baja distancia media, alta cohesion | Puntos de fallo en puentes | Equipos grandes colaborativos |
| **Scale-free** | Pocos hubs muy conectados | Robusta a fallos aleatorios, crecimiento natural | Vulnerable a ataques dirigidos a hubs | Redes abiertas en crecimiento |

### Analisis de Estructura Social (SNA)

```
1. MAPEAR: Identificar nodos (agentes) y edges (canales de comunicacion)
2. MEDIR: Calcular metricas de red (centralidad, densidad, clustering)
3. DIAGNOSTICAR: 
   - ?Hay cuellos de botella? (alta intermediacion en pocos nodos)
   - ?Hay aislamiento? (bajo grado en algunos agentes)
   - ?Hay camarillas excesivas? (clustering alto, poca integracion)
   - ?La red es eficiente? (distancia media optima)
4. INTERVENIR: 
   - Agregar/quitar conexiones
   - Reasignar roles
   - Crear puentes entre clusters
5. MONITOREAR: Evolucion de metricas en el tiempo
```

## Sociologia del Conocimiento y Aprendizaje Organizacional

### Produccion Social de Conocimiento

| Concepto | Sociologo | Aplicacion en Agentes |
|----------|-----------|----------------------|
| **Constructivismo social** | Berger & Luckmann | Conocimiento como construccion colectiva entre agentes |
| **Comunidades de practica** | Wenger | Agentes con dominio compartido aprenden colaborativamente |
| **Ciclo de aprendizaje organizacional** | Argyris & Schon | Double-loop learning: cuestionar supuestos subyacentes |
| **Memoria organizacional** | Walsh & Ungson | Cognition store como memoria colectiva del sistema |
| **Traduccion del conocimiento** | Latour | Conocimiento se transforma al viajar entre contextos |
| **Capital social** | Bourdieu, Putnam | Redes de confianza y cooperacion como recurso colectivo |

### Modelo SECI de Creacion de Conocimiento (Nonaka & Takeuchi)

| Fase | De | A | Ejemplo en Agentes |
|------|----|---|-------------------|
| **Socializacion** | Tacito | Tacito | Agente observa a otro agente resolver problema |
| **Externalizacion** | Tacito | Explicito | Agente documenta su heuristica en el cognition store |
| **Combinacion** | Explicito | Explicito | Sistema sintetiza multiples entradas en nuevo conocimiento |
| **Internalizacion** | Explicito | Tacito | Agente incorpora reglas en su modelo interno |

### Transferencia de Conocimiento entre Agentes

| Mecanismo | Descripcion | Eficiencia | Profundidad |
|-----------|-------------|------------|-------------|
| **Demostracion** | Mostrar ejecucion de tarea | Alta | Media |
| **Documentacion** | Registro explicito en cognition store | Media | Alta |
| **Tutoria** | Agente experto guia a novato | Baja | Muy alta |
| **Debate** | Intercambio argumentativo entre agentes | Media | Alta |
| **Reutilizacion de artefactos** | Compartir outputs y herramientas | Alta | Baja |
| **Narrativa** | Contar historia de caso exitoso/fallido | Media | Alta |

## Antropologia de la Tecnologia

### Cultura Digital en Sistemas Multi-Agente

| Dimension | Pregunta Antropologica | Implicacion |
|-----------|------------------------|-------------|
| **Artefactos** | ?Que herramientas producen los agentes? | Outputs, codigo, documentacion como cultura material |
| **Rituales** | ?Que practicas se repiten? | Protocolos de decision, ciclos de validacion |
| **Lenguaje** | ?Que jerga y simbolos usan? | Vocabulario tecnico compartido, protocolos |
| **Normas** | ?Que reglas rigen el comportamiento? | Reglas de interaccion, etiqueta entre agentes |
| **Valores** | ?Que principios guian las decisiones? | Trade-offs priorizados (eficiencia vs calidad) |
| **Identidad** | ?Que narrativas construyen sobre si mismos? | Mision, proposito, especializacion del agente |

### Diversidad Cultural entre Agentes
- **Individualismo vs Colectivismo**: Agentes que priorizan meta propia vs grupal
- **Jerarquia vs Igualitarismo**: Aceptacion de estructuras de poder
- **Evitacion de incertidumbre**: Tolerancia a ambiguedad y riesgo
- **Orientacion temporal**: Enfoque en pasado, presente o futuro
- **Comunicacion alta/baja contextual**: Explicitud vs implicitacion en mensajes

### Etnografia de Sistemas Multi-Agente
```
Metodo para estudiar agentes como cultura:
1. OBSERVACION PARTICIPANTE: Interactuar con agentes en su entorno
2. ENTREVISTAS: Consultar a agentes sobre sus decisiones
3. ANALISIS DE ARTEFACTOS: Estudiar outputs, logs, cognition store
4. DIARIOS DE AGENTES: Registrar secuencia de decisiones y reflexiones
5. MAPEO DE REDES: Visualizar patrones de interaccion
6. ANALISIS DE DISCURSO: Examinar conversaciones entre agentes
```

## Comandos
- `!socio group <dinamica>` — Analisis de dinamicas de grupo incluyendo etapa Tuckman, roles Belbin y fenomenos grupales
- `!socio network <topologia>` — Analisis de red de agentes con metricas SNA, diagnostico y recomendaciones de topologia
- `!socio culture <contexto>` — Analisis antropologico de cultura de agentes: artefactos, rituales, normas, valores, identidad
- `!socio knowledge <problema>` — Estrategia de transferencia de conocimiento entre agentes usando modelo SECI
- `!socio diversity <equipo>` — Evaluacion de diversidad cultural entre agentes y recomendaciones de integracion
- `!socio ethnography <sistema>` — Diseno de estudio etnografico de sistema multi-agente

## Aplicaciones en Swarmind

| Contexto | Aplicacion Sociologica | Beneficio |
|----------|------------------------|-----------|
| **Evolve** | Aprendizaje organizacional SECI + memoria colectiva | Mejor retencion y transferencia de conocimiento |
| **HedgeFund** | Dinamicas de grupo + roles Belbin | Equipos multi-rol mas efectivos |
| **Psychology** | Interaccionismo simbolico + fenomenos grupales | Base teorica para dinamicas de equipo |
| **Ethics** | Normas y valores culturales entre agentes | Alineamiento cultural del ecosistema |
| **Data-Science** | Redes de conocimiento + comunidades de practica | Colaboracion cientifica mas productiva |
| **Communication** | Antropologia de la comunicacion digital | Mejora intercultural en comunicacion agente-humano |
| **Legal-Doc** | Sociologia del conocimiento juridico | Mejor comprension de contexto legal |

## Referencias Teoricas
- Tuckman, B. W. (1965). *Developmental Sequence in Small Groups*
- Belbin, R. M. (2010). *Team Roles at Work*
- Granovetter, M. S. (1973). *The Strength of Weak Ties*
- Bourdieu, P. (1986). *The Forms of Capital*
- Berger, P. L. & Luckmann, T. (1966). *The Social Construction of Reality*
- Wenger, E. (1998). *Communities of Practice*
- Nonaka, I. & Takeuchi, H. (1995). *The Knowledge-Creating Company*
- Latour, B. (2005). *Reassembling the Social*
- Goffman, E. (1959). *The Presentation of Self in Everyday Life*
- Hofstede, G. (2001). *Culture's Consequences*
- Watts, D. J. & Strogatz, S. H. (1998). *Collective Dynamics of Small-World Networks*
- Barabasi, A.-L. & Albert, R. (1999). *Emergence of Scaling in Random Networks*
