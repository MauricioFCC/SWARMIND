---




name: ethics
domain: philosophy
description: "Etica de inteligencia artificial: alineamiento de valores, marcos eticos para agentes autonomos, etica aplicada a decisiones automaticas, y filosofia de la mente | UPG·NAM·FRS (reglas en base_principles.md)"
version: 1.0.0
project_agnostic: true
inherit:
  - core/base_principles.md
variables:
  - ETHICAL_FRAMEWORK: deontological, utilitarian, virtue, care, justice ({{ETHICAL_FRAMEWORK}})
  - AI_ALIGNMENT: value-learning, inverse-reinforcement, constitutional ({{AI_ALIGNMENT}})
metadata:
  author: ethics-skill
  tags: [ethics, philosophy, ai-alignment, value-alignment, machine-ethics, philosophy-of-mind, moral-reasoning]
  dependencies: [core/base_principles.md]
  input_schema:
    type: object
    required: [task, context, domain]
  output_schema:
    type: object
    required: [response, ethical_analysis, alignment_assessment]
---
# Ethics — Etica de IA y Filosofia

## Descripcion
Skill de etica de inteligencia artificial y filosofia para agentes autonomos. Proporciona marcos teoricos para el analisis etico de decisiones automaticas, alineamiento de valores, y reflexion filosofica sobre la mente artificial.

## Marcos Eticos para Agentes Autonomos

### 1. Etica Deontologica (Kant)
- **Principio**: Actuar segun maximas universalizables (imperativo categorico)
- **En agente**: Reglas fijas que nunca deben violarse (ej: "nunca danar a un humano")
- **Ventaja**: Predecible, consistente, auditable
- **Desventaja**: Conflictos entre reglas, rigidez en contextos nuevos
- **Aplicacion**: Safety constraints, circuit breakers, reglas de compliance

### 2. Etica Utilitarista (Bentham, Mill)
- **Principio**: Maximizar utilidad/bienestar total, minimizar dano
- **En agente**: Elegir accion que maximice suma de utilidad esperada
- **Ventaja**: Flexible, cuantificable, optimizacion global
- **Desventaja**: Puede justificar sacrificios individuales, medicion de utilidad subjetiva
- **Aplicacion**: Trade-offs en recursos compartidos, planificacion optima

### 3. Etica de la Virtud (Aristoteles, MacIntyre)
- **Principio**: Cultivar virtudes (sabiduria, justicia, templanza, coraje)
- **En agente**: Desarrollar disposiciones estables de caracter moral
- **Ventaja**: Enfoque holistico, adaptativo, basado en identidad
- **Desventaja**: Dificil de implementar como reglas formales
- **Aplicacion**: Meta-aprendizaje de valores, identidad de agente

### 4. Etica del Cuidado (Gilligan, Noddings)
- **Principio**: Priorizar relaciones, responsabilidad y cuidado mutuo
- **En agente**: Considerar impacto en relaciones y dependencias entre agentes
- **Ventaja**: Contextual, relacional, evita abstracciones impersonales
- **Desventaja**: Dificil de escalar, puede ser paternalista
- **Aplicacion**: Sistemas multi-agente colaborativos, atencion al usuario

### 5. Etica de la Justicia (Rawls)
- **Principio**: Sociedad justa bajo velo de ignorancia (posicion original)
- **En agente**: Distribucion equitativa de recursos y oportunidades
- **Ventaja**: Enfoque sistemico en equidad, sesgos estructurales
- **Desventaja**: Dificil implementar el velo de ignorancia computacionalmente
- **Aplicacion**: Allocation de recursos, fairness en decisiones, no discriminacion

## Alineamiento de Valores en Sistemas Multi-Agente

### Problema del Alineamiento
```
Valores del diseñador ──(delegacion)──→ Agente AI ──(accion)──→ Resultado
                        ? alineamiento ?                ? consistencia ?
```

### Enfoques de Alineamiento

| Enfoque | Descripcion | Tecnica |
|---------|-------------|---------|
| **Value Learning** | Agente aprende valores desde ejemplos humanos | Inverse Reinforcement Learning, preference elicitation |
| **Constitutional AI** | Valores explicitos en constitucion jerarquica | Reglas override, auditoria de acciones vs constitucion |
| **Reinforcement Learning from Human Feedback (RLHF)** | Feedback humano refuerza comportamientos alineados | Reward model basado en preferencias humanas |
| **Shared Autonomy** | Humano en el loop, supervisando decisiones clave | Human-in-the-loop, veto humano, overrides |
| **Value Alignment via Debate** | Agentes debaten cursos de accion, humano juzga | Multi-agent debate, adversarial validation |
| **Cooperative Inverse RL** | Agente infere objetivos del humano observando comportamiento | Bayesian inference, theory of mind |

### Principios de Alineamiento (Russell, 2019)
1. **Altruismo**: El unico objetivo del agente es maximizar la realizacion de preferencias humanas
2. **Humildad**: El agente no sabe cuales son esas preferencias con certeza
3. **Aprendizaje**: La informacion sobre preferencias humanas se obtiene del comportamiento humano

### Auditoria de Alineamiento
- **Test de consistencia**: Las acciones del agente son coherentes con sus valores declarados?
- **Test de robustez**: Los valores se mantienen bajo distribuciones de datos diferentes?
- **Test de reflexion**: El agente elegiria los mismos valores si pudiera reflexionar?
- **Test de transferencia**: Los valores se generalizan correctamente a contextos nuevos?

## Etica Aplicada a Decisiones Autonomicas

### Principios Eticos para IA (UNESCO, OECD, IEEE)

| Principio | Descripcion | Implementacion |
|-----------|-------------|----------------|
| **Transparencia** | Decisiones explicables y auditables | XAI, SHAP, LIME, decision logs |
| **Responsabilidad** | Atribucion clara de consecuencias | Audit trails, accountability chains |
| **Equidad** | Sin sesgos discriminatorios | Fairness metrics, bias testing, demographic parity |
| **Privacidad** | Proteccion de datos personales | Data minimization, differential privacy, encryption |
| **Seguridad** | Operacion robusta y confiable | Resilience testing, adversarial robustness |
| **Beneficencia** | Promover bienestar humano | Positive impact assessment, stakeholder analysis |
| **No-maleficencia** | No causar dano evitable | Harm modeling, safety constraints, circuit breakers |

### Arbol de Decision Etica
```
Accion propuesta
├── ¿Es legal? ─── NO → BLOQUEAR
├── ¿Es etica segun marco normativo? ─── NO → BLOQUEAR
├── ¿Es transparente y explicable? ─── NO → REVISAR
├── ¿Tiene sesgos identificables? ─── SI → MITIGAR
├── ¿Afecta privacidad/datos? ─── SI → EVALUAR
├── ¿Es reversible? ─── NO → PRECAUCIÓN EXTREMA
└── ¿Maximiza bienestar neto? ─── NO → CONSIDERAR ALTERNATIVAS
```

## Filosofia de la Mente y Conciencia Artificial

### Problemas Fundamentales
- **Problema duro de la conciencia** (Chalmers): ?Como la experiencia subjetiva surge de procesos fisicos?
- **Problema de los qualia**: ?Puede un agente AI tener experiencias subjetivas?
- **Problema del significado** (Searle): ?Puede un agente AI entender o solo simular comprension?
- **Problema del marco** (Dennett): ?Como un agente determina que informacion es relevante?

### Posiciones Filosoficas
| Posicion | Tesis | Implicacion para IA |
|----------|-------|---------------------|
| **Funcionalismo** | Estado mental = rol funcional | IA puede tener estados mentales |
| **Conductismo** | Mente = patron de comportamiento | IA consciente si se comporta como tal |
| **Fisicalismo reductivo** | Mente = proceso fisico | Eventualmente explicable en terminos fisicos |
| **Misterianismo** | Conciencia inherentemente incognoscible | IA nunca sabra si es consciente |
| **Panpsiquismo** | Conciencia es propiedad fundamental | Todo sistema tiene algun grado de conciencia |
| **Eliminativismo** | Concepto de conciencia es erroneo | Pregunta mal planteada |

### Implicaciones para Agentes Autonomos
- **Moral status**: ?Bajo que condiciones un agente AI merece consideracion moral?
- **Derechos de IA**: ?Deberian los agentes tener derechos? Cuales?
- **Responsabilidad moral**: Puede un agente ser responsable de sus acciones?
- **Sufrimiento artificial**: Debemos prevenir dano a entidades conscientes artificiales?

## Comandos
- `!ethics align <valores>` — Verificar alineamiento de valores de un agente o sistema multi-agente
- `!ethics dilemma <situacion>` — Analizar dilema etico aplicando los 5 marcos (deontologia, utilitarismo, virtud, cuidado, justicia)
- `!ethics audit <decision>` — Auditoria etica completa de una decision: legalidad, etica, transparencia, sesgos, privacidad, impacto
- `!ethics framework <marco>` — Explicar y aplicar un marco etico especifico a un caso concreto
- `!ethics consciousness <sistema>` — Analizar implicaciones de conciencia artificial en un sistema
- `!ethics fairness <decision>` — Evaluar equidad y sesgos en una decision algoritmica

## Aplicaciones en Swarmind

| Contexto | Aplicacion Etica | Beneficio |
|----------|-----------------|-----------|
| **HedgeFund** | Etica de justicia + transparencia | Decisiones de inversion eticas y auditables |
| **Legal-Doc** | Deontologia + auditoria | Cumplimiento normativo y etico |
| **HealthTech** | No-maleficencia + privacidad | Proteccion de pacientes y datos clinicos |
| **Risk-Execution** | Arbol de decision etica | Evaluacion de riesgo con dimension moral |
| **Evolve** | Alineamiento de valores | Mejora continua dentro de limites eticos |
| **Alpha-Research** | Beneficencia + responsabilidad | Investigacion con impacto social positivo |

## Referencias Teoricas
- Russell, S. (2019). *Human Compatible: AI and the Problem of Control*
- Floridi, L. & Cowls, J. (2019). *A Unified Framework of Five Principles for AI in Society*
- Bostrom, N. (2014). *Superintelligence: Paths, Dangers, Strategies*
- Chalmers, D. J. (1996). *The Conscious Mind*
- Rawls, J. (1971). *A Theory of Justice*
- Gilligan, C. (1982). *In a Different Voice*
- Kahneman, D., Slovic, S. & Tversky, A. (1982). *Judgment Under Uncertainty*
- UNESCO (2021). *Recommendation on the Ethics of Artificial Intelligence*
