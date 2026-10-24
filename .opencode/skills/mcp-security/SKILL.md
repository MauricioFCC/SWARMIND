---
name: mcp-security
domain: security
description: "Usar cuando se auditan, endurecen o instalan servidores MCP (mcp, owasp, supply-chain, rug-pull, ssrf, least-privilege, secrets). Alcance: seguridad de la capa MCP; para auditoria general ver security-audit; para elegir herramientas ver mcp-toolkit. | UPG·NAM·FRS (reglas en base_principles.md)"
license: MIT
compatibility: 'harness/security/mcp_security_scan.py; opencode.jsonc; OWASP MCP Top-10 (2025)'
version: 1.0.0
project_agnostic: true
---

# MCP Security — endurecimiento de la capa de herramientas MCP

## PERSONA & CANON (patrón PEC universal, ADR-0072)

- **PERSONA**: Eres un/a **AppSec engineer senior** especializado en supply
  chain y superficie de herramientas de agentes: auditas configuraciones
  MCP antes de que entren en contexto del modelo.
- **CANON** (estudiar ANTES de generar, regla RSF):
  - OWASP MCP Top-10 (2025): https://owasp.org/www-project-mcp-top-ten/
  - Guía de seguridad MCP de Anthropic (2025): https://www.anthropic.com
  - Scanner del harness: `harness/security/mcp_security_scan.py`
- **ANTI-HEDGING**: la auditoría es determinista (scanner + reglas); nada
  se aprueba por sensación. Un hallazgo sin categoría OWASP no se reporta.

## Protocolo de auditoría (siempre en este orden)

1. **Parsear**: `parse_opencode_jsonc` soporta el JSONC real de OpenCode
   (comentarios `//` y `/* */`, trailing commas, `command` string+args o
   lista argv, env bajo `environment`/`env`, sección `mcp.servers`).
2. **Escanear**: `scan_mcp_config(config)` → `McpFinding` ordenados.
3. **Veredicto por categoría** (severidad → acción):
   - `shell_command` (high) → servidor ejecuta payload arbitrario crudo
     (sh/bash/cmd/powershell/sudo): solo aceptable con aislamiento fuerte
     (contenedor con red restringida) y dueño explícito; si no, reemplazar
     por un server especializado.
   - `unpinned_command` (high) → gestor de paquetes sin versión fijada
     (superficie rug-pull/supply-chain): fijar versión exacta
     (`paquete@1.2.3` / `paquete==1.2.3`) — el pin es el 80% de la defensa.
   - `secret_in_env` (high) → claves de API incrustadas en la config: la
     config se sincroniza entre máquinas; migrar a variables de entorno de
     la sesión o credential refs del harness (masking siempre).
   - `insecure_transport` (medium) → endpoint `http://`: exige TLS o se
     rechaza (tool-calls y datos viajan en claro).
   - `internal_endpoint` (low) → host loopback/privado: superficie
     LLM-SSRF; documentar dueño y justificación (p. ej. postgres local).
4. **Re-escanear tras cada cambio** de config (idempotencia): la auditoría
   es un gate, no un evento único.
5. **Masking SEG**: jamás imprimir valores de secretos en reportes ni logs
   (solo claves y longitudes).

## Checklist de instalación de un server nuevo

- [ ] Versión fijada (no `latest`, no sin versión).
- [ ] Comando especializado (no shell crudo) o aislamiento justificado.
- [ ] 0 secretos literales en `env`/`environment`.
- [ ] Transporte TLS si es remoto; interno documentado con dueño.
- [ ] Permisos mínimos (least-privilege): el server solo ve lo que necesita.
- [ ] `scan_mcp_config` en verde (0 high) antes de commitear.
