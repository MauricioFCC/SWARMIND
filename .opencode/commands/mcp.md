---
description: Catalogo de herramientas MCP del harness SWARMIND (server recomendado por tarea)
---

Tarea: $ARGUMENTS

Reporta los servers MCP del harness adecuados para esa tarea. Evidencia, no suposiciones:

1. Usa la SSOT `harness/tools_sandbox/mcp_servers.yaml` y el catalogo
   `harness.tools_sandbox.mcp_catalog` (`servers_for_task`, `servers_for_skill`).
2. Cita por server su `name`, `tools` y si esta `disabled` en la config global
   (`~/.config/opencode/opencode.jsonc`): solo `fetch`, `time` y
   `sequentialthinking` estan activos por defecto; el resto se habilita bajo
   demanda.
3. Si recomiendas habilitar uno, da el comando exacto (incluye version fijada,
   p. ej. `npx -y <paquete>@<version>`) y recuerda que el arranque stdio en frio
   necesita `experimental.mcp_timeout` suficiente (el harness fija 90000 ms).
