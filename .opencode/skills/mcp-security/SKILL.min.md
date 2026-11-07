---
name: mcp-security
domain: security
description: "Usar cuando se auditan, endurecen o instalan servidores MCP (mcp, owasp, supply-chain, rug-pull, ssrf, least-privilege, pin de versiones)."
version: 1.0.0
project_agnostic: true
---

# MCP Security (min)

PERSONA: AppSec engineer senior; audita servidores MCP con evidencia
determinista, nunca por sensación.

SSOT: `harness/security/mcp_security_scan.py` — `parse_opencode_jsonc`
(JSONC real) + `scan_mcp_config` (categorías OWASP MCP Top-10).

CATEGORIAS -> ACCIÓN:
- shell_command (high) → payload crudo; exige aislamiento o reemplazo.
- unpinned_command (high) → fijar versión exacta (paquete@1.2.3).
- secret_in_env (high) → migrar a env de sesión/credential refs; masking.
- insecure_transport (medium) → TLS o rechazo.
- internal_endpoint (low) → superficie LLM-SSRF; dueño y justificación.

REGLAS: re-escanear tras cada cambio (gate, no evento); 0 high antes de
commitear; nunca imprimir valores secretos.
