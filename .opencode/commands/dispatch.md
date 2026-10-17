---
description: Plan de dispatch del harness (agente + skills + herramientas) para una tarea
---

Tarea: $ARGUMENTS

Produce el plan de dispatch del harness SWARMIND para esa tarea, citando la evidencia real:

1. **Agente**: usa `harness.orchestrator.skill_bundler.SKILL_TO_AGENT` /
   `DOMAIN_SKILLS` y `harness.orchestrator.coordinator_dispatch.dispatch` para
   nombrar el agente y justificarlo con su `description`/`triggers`
   (`.opencode/agents/<agente>.md`).
2. **Skills**: lista las skills que se inyectarian (`skills_registry.yaml` +
   `.opencode/skills/`), no inventes nombres fuera del registry.
3. **Herramientas**: servers MCP recomendados (ver `/mcp`) y permisos del
   agente (todos los agentes SWARMIND son `subagent`/`all`; el `coordinator`
   puede lanzar la flota).
4. Cierra con el **check de verificacion** (VER) que deberia correr el agente
   al terminar, con el comando exacto.
