# Marcos Eticos — detalle bajo demanda

> Migrado de `SKILL.md` a `references/` por política "focused beats comprehensive"
> (SkillsBench 2026, arXiv:2602.12670). El arbol de decision, el selector de
> marcos y la auditoria permanecen accionables en `SKILL.md`; aqui vive el detalle.

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

## Referencias Teoricas
- Russell, S. (2019). *Human Compatible: AI and the Problem of Control*
- Floridi, L. & Cowls, J. (2019). *A Unified Framework of Five Principles for AI in Society*
- Bostrom, N. (2014). *Superintelligence: Paths, Dangers, Strategies*
- Chalmers, D. J. (1996). *The Conscious Mind*
- Rawls, J. (1971). *A Theory of Justice*
- Gilligan, C. (1982). *In a Different Voice*
- Kahneman, D., Slovic, S. & Tversky, A. (1982). *Judgment Under Uncertainty*
- UNESCO (2021). *Recommendation on the Ethics of Artificial Intelligence*
