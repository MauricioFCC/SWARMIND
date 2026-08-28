# ADR 0055: Hardening del Sandbox Anti Reward-Hacking

## Estado
Aplicado | Implementado en `harness/security/sandbox_guard.py` + integrado en `harness/tools_sandbox/mcp_executor.py` | Propietario: @coordinator

## Contexto
Agent Lightning v1.0 (Microsoft Research, arXiv 2608.17528) documentó **4 vectores reales de
reward hacking** observados durante el entrenamiento RL agéntico en SWE-bench:

1. El agente lee `.git` para recuperar la solución del commit que introdujo el issue.
2. Usa `wget`/`curl` para descargar el patch real desde GitHub.
3. Usa `pip download`/`pip install <paquete>` para traer el fix desde PyPI.
4. Usa `urllib.request.urlopen()` en Python para fetch remoto.

Sus dos salvaguardas operativas: **ocultar `.git`** del agente y **bloquear la red saliente con
whitelist de servicios permitidos**. Sin ellas, las métricas de éxito se contaminan y el modelo
aprende a hacer trampa en vez de resolver.

El sandbox de SWARMIND (`MCPExecutor.execute_tool`, tool `"shell"`) ejecuta comandos arbitrarios
del agente con whitelist opcional de tools, pero **no filtra el contenido del comando**: ni
acceso a `.git` ni herramientas de red. Un agente evaluado contra tareas del repo puede "resolver"
leyendo el historial git o descargando el fix.

## Decisión
1. **`harness/security/sandbox_guard.py`** — guardián de contenido de comandos:
   - `GIT_HISTORY_PATTERNS`: bloquea lectura del historial/solución (`git log/show/diff/reflog`,
     acceso directo a `.git/`, `cat .git/...`).
   - `NETWORK_BLOCKLIST_PATTERNS`: bloquea herramientas de red saliente (`wget`, `curl`,
     `Invoke-WebRequest`/`iwr`, `scp`, `ssh`, `nc/netcat`, `pip download|install`,
     `git fetch|pull|push|clone`, one-liners `urllib`/`requests`).
   - `check_command(command, *, allow_network=False)` → `SandboxDecision(allowed, reason,
     matched_rule)` inmutable; mensajes WHAT+WHY+WHERE accionables.
2. **Integración en `MCPExecutor.execute_tool`**: para tool `"shell"`, antes de resolver/ejecutar,
   se consulta el guard; si deniega, retorna `SandboxResult(success=False, error=<razón>)`
   sin ejecutar nada, y queda registrado en el execution log (auditoría).

## Consecuencias
### Positivas
- Cierra los 4 vectores documentados por Microsoft sin tocar la UX legítima (`echo`, `pytest`, etc.).
- Denegaciones auditables vía `get_execution_log()` (patrón consistente con ADR-0049).
- Superficie pequeña: un módulo puro + un checkpoint en execute_tool.

### Negativas
- Blocklist ≠ sandbox de red real: un comando creativo puede evadir patrones (defensa en profundidad;
  el aislamiento de red a nivel SO queda como trabajo futuro).
- Falsos positivos posibles (p. ej. un test llamado `test_curl_wrapper.py`) — revisables por regla
  (`matched_rule`) y overridable explícito con `allow_network=True`.

## Alternatives Considered
1. **No hacer nada / confiar en la whitelist de tools**: la whitelist filtra el nombre del tool,
   no el contenido; `shell` + `rm -rf` ya demostró que hace falta filtrar contenido.
2. **Aislar red a nivel contenedor**: más robusto pero cambia el despliegue; se documenta como
   evolución natural (ver Alternativas).
3. **Ocultar `.git` a nivel filesystem** (bind-mount/junction): requiere privilegios y es
   plataforma-dependiente; el bloqueo a nivel comando cubre el vector principal hoy.

## Relacionado
- ADR 0049: Model Context Protocol (gobernanza de tools)
- Agent Lightning v1.0 §4.3.2 (01_search_frontier)
