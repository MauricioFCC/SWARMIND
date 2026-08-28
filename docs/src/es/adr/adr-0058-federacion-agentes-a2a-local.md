# ADR 0058: Federación de Agentes Entre Proyectos (A2A Local)

## Estado
Aplicado | Implementado en `harness/federation/` (agent_card, task_protocol, federation_bus) | Propietario: @coordinator

## Contexto
Los proyectos del ecosistema DEV-SPACE necesitan que sus agentes se intercomuniquen y se activen
entre sí. Caso real: **CQE (core-quant-engine) es una librería que consume Onyx**, pero Onyx
requiere funciones de CQE que aún no existen y necesita delegar implementaciones en CQE para
poder avanzar. Hoy cada proyecto tiene su mirror `.opencode/` (35 skills) y el harness vive en
opencode global, pero **no existe un mecanismo de agente-a-agente entre proyectos**: solo hay
knowledge federado de memoria (`.opencode/federated/knowledge_*.json`, sin tareas).

Investigación frontera (ago 2026):
- **A2A (Agent2Agent)** — estándar Linux Foundation (donado por Google), alcanzó **v1.0 en marzo
  2026**. Descubrimiento vía Agent Card en URI bien conocido `/.well-known/agent-card.json`
  (RFC 8615); campos requeridos: name, description, version, supportedInterfaces, capabilities,
  defaultInputModes, defaultOutputModes, skills(id/name/description/tags). Ciclo de vida de
  tareas con estados terminales. Complementa MCP: *MCP expone tools a un agente; A2A expone un
  agente completo a otros agentes*.
- **ACP** (IBM BeeAI): mensajería REST minimalista sin lifecycle rico.
- **ANP**: descubrimiento descentralizado vía W3C DID — orientado a internet abierto, overkill
  para un ecosistema local de proyectos propios.

## Decisión
Adoptar los **conceptos de A2A v1.0** (Agent Card + task lifecycle) con **transporte local**
(sin servidores HTTP): el "endpoint" de un proyecto es su propio harness/opencode invocado en
su directorio raíz — patrón ya probado en `delegate.py`.

1. **`harness/federation/agent_card.py`** — identidad y descubrimiento:
   - `AgentCard` / `AgentSkill` inmutables con los campos requeridos del estándar.
   - Ubicación canónica: `.opencode/.well-known/agent-card.json` por proyecto.
   - `load_agent_card()` con validación fail-fast; `discover_cards()` escanea proyectos hermanos.
2. **`harness/federation/task_protocol.py`** — ciclo de vida A2A:
   - `TaskState`: submitted → working → completed | failed | input_required | canceled.
   - `FederatedTask` inmutable (task_id UUID, origen, destino, skill_id, prompt, artifacts).
   - `TaskStore` persistente en `.opencode/federated/tasks/*.json` con idempotencia por task_id.
3. **`harness/federation/federation_bus.py`** — activación gobernada:
   - Matriz de gobernanza allowlist `origen → {destinos}` **deny-by-default** (patrón
     MCPGovernor de ADR-0049) + audit trail con parámetros enmascarados.
   - `send_task()`: valida permiso → marca working → ejecuta el harness del proyecto destino
     (`subprocess.run(cwd=raíz destino)`) → registra artifact/estado terminal.

## Consecuencias
### Positivas
- Onyx puede pedir trabajo a CQE explícitamente: descubrimiento por card, tarea trazable,
  resultado como artifact — sin acoplamiento de código.
- Estándar abierto: si mañana los proyectos exponen HTTP real, la card y el lifecycle ya son
  compatibles con A2A v1.0.
- Gobernanza uniforme con el resto del harness (deny-by-default + auditoría).
- Cada proyecto mantiene autonomía total: la federación orquesta, no fusiona repos.

### Negativas
- Transporte local subprocess: sin streaming ni push notifications (A2A los define para HTTP).
- Las cards son archivos estáticos: pueden desincronizarse de las capacidades reales;
  mitigable validando skills al enviar la tarea.

## Alternatives Considered
1. **ACP REST puro**: requiere servidores vivos por proyecto; innecesario en máquina local.
2. **ANP/DID**: resolución descentralizada para internet abierto; YAGNI para ecosistema propio.
3. **Monorepo compartido**: resuelve el caso CQE↔Onyx acoplando todo el ecosistema; pierde
   autonomía y rompe el estándar v2.5 de mirrors.
4. **Solo memoria federada Hermes**: comparte conocimiento pero no ACTIVA agentes ni delega tareas.

## Relacionado
- ADR 0049: Model Context Protocol (gobernanza de tools — mismo patrón deny-by-default)
- ADR 0051: Gobernanza de Agente (4 preguntas aplican a agentes federados)
- A2A Protocol: https://github.com/a2aproject/A2A — https://a2a-protocol.org/latest/specification/
