# Swiss Watch Pattern

El sistema funciona como un reloj suizo multi-agente: todos los especialistas
relevantes son notificados SIMULTANEAMENTE, trabajan en paralelo, y se sincronizan
via AgentBus.

## Flujo
1. RECIBIR: Mensaje del usuario
2. SWARM: Lanzar agentes en paralelo (nivel 0)
3. COMUNICAR: AgentBus transmite hallazgos parciales
4. CONSOLIDAR: Coordinator integra resultados
5. ENTREGAR: Respuesta unificada
