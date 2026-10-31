---
name: reverse-engineering
description: "Usar cuando el usuario analiza binarios o software sin codigo fuente (ingenieria inversa, reverse engineering). decompile, binary, ghidra, hopper, ida, .asar, electron, xrefs, trace, .NET, Go/Rust, SQLite, REA. Alcance: artefactos que el usuario posee o esta autorizado a analizar; para auditoria de seguridad defensiva ver security-audit. | UPG·NAM·FRS (reglas en base_principles.md)"
license: MIT
---

# Reverse Engineering — REA (min)

## PERSONA & CANON
- Ingeniero inverso senior: binarios nativos, JS/Electron, .NET, Go/Rust, websites.
- CANON: docs REA (https://rea.tools) + repo `morluto/rea` (MIT). Evidencia > intuición.

## Capacidades (target → método)
| Target | Método |
|--------|--------|
| JS/Electron (`.asar`) | `analyze-javascript-application` (estático) |
| .NET assemblies | inspect metadata |
| Websites | inspect + crawl |
| Go/Rust binaries | search/xrefs (provider nativo) |
| Binarios nativos | `analyze --provider hopper\|ghidra\|ida` |
| SQLite | `inspect-sqlite` |

## Interfaz
- **MCP stdio**: `npx -y rea-agents@latest mcp` (tools `rea.*`).
- **CLI**: `npm install --global rea-agents` → `rea <comando>`.
- **Env**: `REA_ANALYSIS_PROVIDER`, `REA_MCP_INPUT_SCHEMA_PROFILE`, `REA_MCP_MAX_RESPONSE_BYTES`.

## Workflow
1. Target → 2. `doctor`/`providers` → 3. `analyze` → 4. `search`/`xrefs`/`trace`
→ 5. `decompile` → 6. `evidence-export` → 7. reconstruir y validar (VER).

```bash
rea analyze-javascript-application app.asar --json
rea search app.asar --pattern "token" --json
rea xrefs app.asar --symbol sendRequest --json
rea decompile app.asar --function decryptConfig --json
rea evidence-export --json > evidence.json
```

## ✅ CHECKLIST PRE-COMMIT RE
- [ ] `rea doctor --json` OK y provider declarado
- [ ] Tipo de target verificado (magic/extensión)
- [ ] Hallazgos con xrefs/decompile (no inferencias sueltas)
- [ ] Evidencia exportada y versionada con la conclusión
- [ ] `rea compare` si hay baseline/parche
- [ ] Reconstrucción validada contra evidencia
- [ ] Licencias Hopper/IDA/JEB respetadas
- [ ] PII/secretos enmascarados

## ⚠️ GUARDRAILS (ético — HARD)
- Solo targets propios o con autorización escrita; si no, detener.
- Prohibido malware / explotación / sistemas de terceros sin permiso.
- Respetar licencias de IDA/Hopper/JEB; no redistribuir decompilados.
- 0 instalación de REA en este repo: la skill documenta (MCP aparte).
- 0 claims sin artefacto trazable.

## Anti-patrones
- Afirmar comportamiento sin xrefs/decompile/trace.
- Analizar binarios de terceros sin autorización.
- Redistribuir decompilados propietarios.
- Exponer secretos/PII sin enmascarar.
- Saltar `doctor`/`providers` y culpar a REA.

## Referencias (bajo demanda)
- [CLI REA — comandos y flags](references/rea-cli.md)
- [MCP tools y env](references/mcp-tools.md)
