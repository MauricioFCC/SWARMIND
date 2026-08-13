# ADR-0019: Swarmind Governance & Business Context

## Estado
**ACEPTADO** — Implementado.

## Contexto
Analisis del documento "Hablamos de Orquestacion Swarmind CX" + referencias del sector (Google BigQuery conversational, Databricks governance, Snowflake semantic layer):

### Problemas identificados
1. **Shadow AI**: Agentes no auditados con acceso directo a internet (riesgo de prompt injection)
2. **Cost explosion**: Agentes mal disenados en loops infinitos consumiendo tokens
3. **Business context**: Agentes no entienden el contexto de negocio (ej: "cliente activo" significa diferente para cada empresa)
4. **Gobernanza**: Falta de marcos para decisiones autonomicas

## Decisiones e Implementacion

### 1. GovernanceAgent (ya implementado en ADR-0026)
`harness/orchestrator/governance_agent.py`:
- Registro de decisiones con contexto y justificacion
- Evaluacion de riesgo pre-deploy
- Aprobacion/rechazo de decisiones
- Trazabilidad completa

### 2. Agent Cost Controller
`harness/orchestrator/agent_cost_controller.py`:
- Monitoreo de consumo de tokens por agente
- Deteccion de loops infinitos (mismas llamadas repetidas)
- Limites de gasto por sesion
- Alertas de costos anomales

### 3. Business Context Layer
`harness/orchestrator/business_context.py`:
- Glosario de terminos de negocio
- Contexto especifico por industria/proyecto
- Resolucion de ambiguedades terminologicas
- Integracion con AgentBus para enriquecer prompts

### 4. Sandbox Mode
`harness/orchestrator/sandbox_mode.py`:
- Entorno controlado para experimentacion
- Limites de tokens, tiempo y alcance
- Auditoria completa de acciones
- Revisión pre-produccion obligatoria

## Referencias
- CX Swarmind Orchestration: Governance frameworks, shadow AI risks
- Google BigQuery conversational (Jul 2026): NLP analitico
- Databricks governance: Control de agentes, modelos y herramientas
- Snowflake semantic layer: Contexto compartido de negocio

## Consecuencias
- **Modulos nuevos:** 3 (cost controller, business context, sandbox)
- **Skills totales:** 31
- **ADRs totales:** 27
- **Riesgo reducido:** Shadow AI, cost explosion, ambiguedad terminologica
