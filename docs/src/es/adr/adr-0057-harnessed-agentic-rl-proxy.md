# ADR 0057: Harnessed Agentic RL vía Proxy de Endpoint (Futuro)

## Estado
Propuesto | No implementado (requiere GPUs + pipeline de training) | Propietario: @coordinator

## Contexto
Agent Lightning v1.0 (Microsoft Research, arXiv 2608.17528) introduce el paradigma **harnessed
agentic RL**: desacopla el entrenamiento RL de la ejecución del agente interponiendo un
**proxy de endpoint LLM** (LightningAPIServer) entre el harness y el proveedor. Cualquier harness
existente — sin modificar una línea — puede ser entrenado: las llamadas al LLM se capturan como
rollouts, se calculan ventajas a nivel rollout (+3.2 pts vs token-level: 38.2% vs 35.0% en
SWE-bench Verified) y se normaliza la pérdida por rollout para estabilidad.

SWARMIND calza exactamente en ese paradigma: es un harness Python con orquestación multi-agente,
memoria central y observabilidad estructurada. Conectado como cliente del proxy, sus sesiones
(orchestrator → agentes → tools) se convierten en datos de entrenamiento RL con **cero cambios
de código** en el harness.

Requisitos que hoy no tenemos: GPUs para training, pipeline de filtrado de datos por dificultad
(model-based difficulty filter, 4 rollouts/tarea, ~6K tareas train), monitoreo de rollouts con
agentes AI detectores de reward hacking, e infraestructura de checkpointing.

## Decisión
**Documentar la viabilidad y posponer la implementación** hasta que existan los recursos. El
camino de integración cuando se active:

1. Apuntar el model routing de SWARMIND (`harness/model_router/`) al endpoint del proxy
   LightningAPIServer en vez del proveedor directo (cambio de configuración, no de código).
2. Reutilizar el sandbox endurecido (ADR-0055) como entorno de rollouts seguro.
3. Reutilizar `session_replay` + dedup keep-last (ADR-0056) como fuente de rollouts limpios.
4. Adoptar el filtro de dificultad basado en modelo antes de inyectar tareas al pipeline.
5. Monitoreo continuo de reward hacking con agentes AI sobre los rollouts (extensión de
   `harness/observability/`).

## Consecuencias
### Positivas
- Ruta clara y de bajo costo de migración cuando haya GPUs (config-only en el paso 1).
- El trabajo previo (ADR-0055/0056) ya deja el harness "RL-ready".
- Referencia empírica: +14.6% absoluto en SWE-bench Verified con ~6K ejemplos de entrenamiento.

### Negativas
- Costo de infraestructura (GPUs multi-nodo) fuera del alcance actual.
- Riesgo de dependencia de un framework en movimiento rápido; mitigable porque la integración
  es por endpoint HTTP estándar (OpenAI-compatible).

## Alternatives Considered
1. **Implementar ahora sin GPUs**: inviable; el training no corre sin hardware.
2. **RL propio ad-hoc**: reinventar lo que Agent Lightning ya resolvió (credit assignment a nivel
   rollout, time-sharing colocado de GPUs); viola UPG/FRS.
3. **Solo fine-tuning SFT tradicional**: no aprende del feedback del entorno agéntico; techo
   demostrado inferior al RL agéntico.

## Relacionado
- ADR 0055: Hardening del Sandbox Anti Reward-Hacking
- ADR 0056: Deduplicación Keep-Last-Per-Prompt
- Agent Lightning v1.0 (01_search_frontier)
