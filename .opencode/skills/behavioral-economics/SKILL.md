---
name: behavioral-economics
domain: economics
description: "Economia del comportamiento: teoria de juegos, sesgos cognitivos, heurísticas, toma de decisiones bajo incertidumbre, y diseno de incentivos."
version: 1.0.0
project_agnostic: true
inherit:
  - core/base_principles.md
variables:
  - GAME_TYPE: cooperative, non-cooperative, sequential, simultaneous, zero-sum ({{GAME_TYPE}})
  - INCENTIVE_DESIGN: intrinsic, extrinsic, gamification, mechanism ({{INCENTIVE_DESIGN}})
metadata:
  author: behavioral-economics-skill
  tags: [behavioral-economics, game-theory, cognitive-biases, heuristics, incentives, decision-theory, nudge, bounded-rationality]
  dependencies: [core/base_principles.md]
  input_schema:
    type: object
    required: [task, context, domain]
  output_schema:
    type: object
    required: [response, game_analysis, bias_assessment, incentive_plan]
---
# Behavioral Economics — Economia del Comportamiento

## Descripcion
Skill de economia del comportamiento para mejorar la toma de decisiones de agentes. Integra teoria de juegos, psicologia cognitiva y diseno de incentivos para optimizar decisiones estrategicas en sistemas multi-agente.

## Teoria de Juegos para Negociaciones entre Agentes

### Conceptos Fundamentales

| Concepto | Definicion | Aplicacion en Agentes |
|----------|-----------|----------------------|
| **Jugador** | Agente que toma decisiones estrategicas | Cada agente en el sistema multi-agente |
| **Estrategia** | Plan completo de accion en toda contingencia | Politica de decision del agente |
| **Payoff** | Utilidad resultante de un perfil de estrategias | Funcion de recompensa del agente |
| **Equilibrio** | Estado donde ningun jugador quiere desviarse unilateralmente | Punto de estabilidad en interacciones |
| **Informacion** | Conocimiento que tiene cada jugador sobre el juego | Shared context, observabilidad parcial |

### Tipos de Juegos

#### 1. Juegos Cooperativos vs No-Cooperativos
| Aspecto | Cooperativo | No-Cooperativo |
|---------|------------|----------------|
| **Acuerdos** | Vinculantes y exigibles | No vinculantes |
| **Enfoque** | Como distribuir ganancias de la cooperacion | Como actuar en conflicto de intereses |
| **Solucion** | Valor de Shapley, nucleolo, kernel | Equilibrio de Nash, estrategias mixtas |
| **Ejemplo** | Agentes compartiendo recursos computacionales | Agentes compitiendo por presupuesto |

#### 2. Juegos Secuenciales vs Simultaneos
- **Secuencial**: Arbol de decision, induccion hacia atras, equilibrio perfecto en subjuegos
- **Simultaneo**: Matriz de pagos, estrategias mixtas, equilibrio de Nash

#### 3. Juegos de Suma Cero vs Suma No Cero
- **Suma cero**: Conflicto puro, ganancia de uno = perdida del otro
- **Suma no cero**: Posibilidad de ganancias mutuas (win-win), trade-offs

### Soluciones Clave para Agentes

| Concepto | Formula/Uso | Aplicacion |
|----------|-------------|------------|
| **Equilibrio de Nash** | Ningun agente puede mejorar unilateralmente | Prediccion de comportamiento en mercados |
| **Estrategia Dominante** | Mejor eleccion independiente de lo que hagan otros | Protocolos de consenso optimos |
| **Dilema del Prisionero** | Cooperacion vs defecto en interaccion unica | Comparticion de informacion entre agentes |
| **Juego del Gallina** | Quien cede primero en escalada de riesgo | Asignacion de recursos criticos |
| **Juego del Bien Publico** | Contribucion individual a beneficio colectivo | Mantenimiento de conocimiento compartido |
| **Ultimatum** | Proponer dividir recurso, el otro acepta/rechaza | Negociacion de recursos entre agentes |
| **Coordinacion** | Beneficio mutuo de elegir la misma accion | Estandares, protocolos, sincronizacion |

## Identificacion y Mitigacion de Sesgos Cognitivos

### Catalogacion de Sesgos Clave

| Sesgo | Descripcion | Impacto en Decisiones Agente | Mitigacion |
|-------|-------------|------------------------------|------------|
| **Anclaje** | Dependencia excesiva del primer dato recibido | Sesgo en estimaciones iniciales | Multiple-point initialization, averaging |
| **Confirmacion** | Buscar evidencia que confirme creencias previas | Overfitting a hipotesis inicial | Adversarial testing, falsificacion activa |
| **Disponibilidad** | Juzgar probabilidad por facilidad de recordar ejemplos | Sobreestimar eventos recientes/salientes | Base rate correction, estratificacion temporal |
| **Exceso de confianza** | Sobreestimar precision de propias predicciones | Riesgo subestimado, margenes estrechos | Calibration scoring, intervalos de confianza probabilisticos |
| **Sesgo de supervivencia** | Enfocarse en exitos ignorando fallos | Metricas infladas, lecciones no aprendidas | Failure case analysis, registro completo |
| **Framing** | Decision afectada por como se presenta la informacion | Respuesta inconsistente a datos equivalentes | Reformulacion multiple, perspective-taking |
| **Sesgo de status quo** | Preferencia por estado actual sobre cambio | Resistencia a innovacion, inercia | Cost-benefit explicito, experimentos A/B |
| **Sesgo de atribucion** | Explicar comportamiento por personalidad vs situacion | Diagnostico erroneo de fallos de agentes | Analisis sistemico, multiple hypotheses |
| **Disonancia cognitiva** | Rechazar informacion que contradice creencias | Resistencia a correccion, circulo vicioso | Belief updating algorithms, Bayesian revision |
| **Efecto arrastre (bandwagon)** | Adoptar creencias populares sin evaluacion critica | Homogeneidad en exploracion, falta de diversidad | Exploracion forzada, adversarial agents |

### Protocolo de Mitigacion Sistematica
```
1. DETECTAR: Identificar sesgos que afectan la decision actual
2. CUANTIFICAR: Estimar magnitud y direccion del sesgo
3. CORREGIR: Aplicar tecnica de mitigacion especifica
4. VERIFICAR: Evaluar si la correccion fue efectiva
5. REGISTRAR: Documentar sesgo para aprendizaje futuro
```

## Diseno de Incentivos y Mecanismos

### Tipos de Incentivos

| Tipo | Descripcion | Ejemplo en Agentes |
|------|-------------|-------------------|
| **Intrinsecos** | Motivacion interna por la tarea misma | Curiosidad, mastery, proposito |
| **Extrinsecos** | Recompensas externas a la tarea | Tokens, reputacion, acceso preferencial |
| **Monetarios** | Valor cuantificable intercambiable | Creditos de computo, budget allocation |
| **Sociales** | Reconocimiento y estatus en el grupo | Leaderboards, badges, reputacion |
| **No-monetarios** | Beneficios no cuantificables | Acceso a informacion, prioridad, autonomia |

### Principios de Diseno de Mecanismos (Hurwicz, Myerson)
1. **Compatibilidad de incentivos**: Agentes maximizan su utilidad siendo honestos
2. **Racionalidad individual**: Participar es mejor que no participar
3. **Eficiencia asignativa**: Recursos llegan a quienes mas los valoran
4. **Presupuesto balanceado**: Sistema no requiere subsidio externo
5. **Veracidad**: Reportar informacion verdadera es estrategia optima

### Mecanismos Clave

| Mecanismo | Como Funciona | Aplicacion |
|-----------|--------------|------------|
| **Subasta Vickrey** | Paga el segundo precio mas alto | Asignacion eficiente de tareas |
| **Votacion Quadratica** | Costo de votos crece al cuadrado | Decisiones colectivas con intensidad de preferencia |
| **Mercado de Prediccion** | Apostar por resultados futuros | Forecasting colectivo entre agentes |
| **Shapley Value** | Contribucion marginal promedio | Distribucion justa de recompensas grupales |
| **Taxa Pigouviana** | Impuesto sobre externalidades negativas | Internalizar costos de uso de recursos compartidos |
| **Doble Subasta** | Compradores y vendedores pujan simultaneamente | Mercado de recursos entre agentes |

### Gamification para Agentes
- **PBL Triada**: Points, Badges, Leaderboards
- **Progresion**: Niveles que reflejan experiencia y confiabilidad
- **Misiones**: Desafios con recompensas por logros especificos
- **Personalizacion**: Adaptar incentivos a preferencias del agente
- **Feedback**: Ciclos de retroalimentacion inmediata y significativa

## Toma de Decisiones Bajo Incertidumbre

### Modelos de Decision

| Modelo | Descripcion | Cuando Usar |
|--------|-------------|-------------|
| **Utilidad Esperada (EUT)** | Maximizar sumatoria de utilidades ponderadas por probabilidad | Riesgo conocido, distribuciones cuantificables |
| **Prospect Theory (Kahneman-Tversky)** | Valoracion asimetrica de ganancias/perdidas, aversion a perdidas | Incertidumbre psicologica, framing effects |
| **Maximin (Wald)** | Maximizar el peor resultado posible | Alta aversion al riesgo, decisiones criticas |
| **Maximax** | Maximizar el mejor resultado posible | Alta tolerancia al riesgo, exploracion |
| **Minimax Regret (Savage)** | Minimizar arrepentimiento maximo posible | Decisiones con accountability externa |
| **Reglas Heuristicas** | Atajos cognitivos para decisiones rapidas | Baja informacion, presion de tiempo |

### Arbol de Decision Bajo Incertidumbre
```
? Certeza (100% conocido) → Optimizacion determinista
? Riesgo (probabilidades conocidas) → Utilidad esperada, Monte Carlo
? Incertidumbre Ambiguas (probabilidades desconocidas) → Maximin, robustez
? Ignorancia Total → Heuristicas, exploracion, aprendizaje activo
```

## Comandos
- `!behav game <situacion>` — Analisis completo de teoria de juegos incluyendo tipo de juego, jugadores, estrategias, equilibrio y recomendacion
- `!behav biases <decision>` — Identificar y mitigar sesgos cognitivos en una decision con protocolo DETECTAR-CUANTIFICAR-CORREGIR-VERIFICAR-REGISTRAR
- `!behav incentive <objetivo>` — Diseno de mecanismo de incentivos con analisis de compatibilidad, racionalidad y eficiencia
- `!behav decision <problema>` — Analisis de decision bajo incertidumbre con modelo optimo segun contexto
- `!behav nudge <comportamiento>` — Diseno de nudge (empujon) para modificar comportamiento sin restringir opciones
- `!behav market <recurso>` — Diseno de mercado o mecanismo de asignacion entre agentes

## Aplicaciones en AGENTIC

| Contexto | Aplicacion Economia Comportamental | Beneficio |
|----------|-------------------------------------|-----------|
| **HedgeFund** | Teoria de juegos + sesgos + incentivos | Mejores decisiones de portfolio, menos sesgos |
| **Risk-Execution** | Prospect theory + aversion a perdidas | Evaluacion de riesgo mas realista |
| **Evolve** | Incentivos intrinsecos + gamification | Mayor motivacion en loop de mejora |
| **Quant-Trading** | Teoria de juegos en mercados | Estrategias de trading mas sofisticadas |
| **Legal-Doc** | Minimax regret en decisiones juridicas | Documentos legales mas robustos |
| **Alpha-Research** | Sesgo de confirmacion + exploracion | Investigacion mas objetiva y diversa |
| **Psychology** | Sesgos cognitivos + Prospect Theory | Base teorica compartida y complementaria |

## Referencias Teoricas
- Kahneman, D. & Tversky, A. (1979). *Prospect Theory: An Analysis of Decision under Risk*
- Thaler, R. H. & Sunstein, C. R. (2008). *Nudge: Improving Decisions About Health, Wealth, and Happiness*
- Camerer, C. F. (2003). *Behavioral Game Theory*
- Shapley, L. S. (1953). *A Value for n-Person Games*
- Hurwicz, L. & Reiter, S. (2006). *Designing Economic Mechanisms*
- Ariely, D. (2008). *Predictably Irrational*
- Kahneman, D. (2011). *Thinking, Fast and Slow*
- Von Neumann, J. & Morgenstern, O. (1944). *Theory of Games and Economic Behavior*
