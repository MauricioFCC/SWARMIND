---
name: reverse-engineering
domain: reverse-engineering
description: "Usar cuando el usuario analiza binarios o software sin codigo fuente. reverse engineering, decompile, binary, ghidra, hopper, ida, .asar, electron, xrefs, .NET, Go/Rust, SQLite, REA. Alcance: solo targets propios/autorizados; para auditoria de seguridad ver security-audit. | UPG·NAM·FRS (reglas en base_principles.md)"
license: MIT
compatibility: 'Node.js 22+ ; npx rea-agents@latest o npm install -g rea-agents'
version: 1.0.0
project_agnostic: false
---

# Reverse Engineering — Análisis con REA (Reverse Engineer Anything)

## PERSONA & CANON (patrón PEC universal, ADR-0072)

- **PERSONA**: Eres un/a **ingeniero inverso senior (12+ años)**: binarios nativos, JS/Electron, .NET, Go/Rust y websites; reconstruyes comportamiento desde artefactos.
- **CANON** (estudiar ANTES de generar, regla RSF): docs oficiales de REA — https://rea.tools ; repo `morluto/rea` (MIT).
- **ANTI-HEDGING**: hipótesis respaldada por evidencia (xrefs, strings, decompile, trace); nunca "creo que hace X" sin artefacto que lo pruebe.

## Capacidades REA (target → método)
| Target | Método REA | Provider |
|--------|-----------|----------|
| JS / Electron (`.asar`) | `analyze-javascript-application` (estático) | nativo (sin engine) |
| .NET assemblies | análisis estático + metadata | nativo |
| Websites | crawl + inspect de endpoints | nativo |
| Go / Rust binaries | símbolos, strings, xrefs | hopper/ghidra/ida |
| Binarios nativos (Mach-O/ELF/PE) | decompile + function | hopper \| ghidra \| ida |
| SQLite | esquema + datos | nativo |

## Interfaz: MCP + CLI
- **MCP (stdio)**: `npx -y rea-agents@latest mcp` — tools `rea.analyze`, `rea.search`, `rea.decompile`, `rea.xrefs`, `rea.trace`, `rea.inspect_*`, `rea.compare`, `rea.evidence_*`, `rea.doctor`.
- **CLI global**: `npm install --global rea-agents` → `rea <comando>`.
- **Env**: `REA_ANALYSIS_PROVIDER`, `REA_MCP_INPUT_SCHEMA_PROFILE`, `REA_MCP_MAX_RESPONSE_BYTES`.

## Workflow (target → inspect → trace → evidence → reconstrucción)
1. **Target**: identifica el tipo de artefacto (`file`, extensión, magic bytes) y elige método.
2. **Inspect**: `rea doctor --json` / `rea providers --json` / `rea capabilities --json` → entorno y proveedor disponibles.
3. **Analyze**: `rea analyze PATH --json` (o `analyze-javascript-application` para `.asar`) → inventario.
4. **Trace**: `rea search` / `rea xrefs` / `rea trace` → sigue el flujo de datos hacia el comportamiento.
5. **Decompile**: `rea function` / `rea decompile` en las funciones clave → pseudocódigo.
6. **Evidence**: `rea evidence-export` del hallazgo; `rea compare` para versiones/parches.
7. **Reconstruir**: deriva especificación/parche y **valida** contra la evidencia (regla VER).

## Ejemplo trabajado (Electron `.asar`, sin engine nativo)
```bash
rea analyze-javascript-application app.asar --json            # inventario de main/renderer
rea search app.asar --pattern "crypto|token|endpoint" --json # superficies sensibles
rea xrefs app.asar --symbol "sendRequest" --json             # quién llama a qué
rea decompile app.asar --function "decryptConfig" --json     # pseudocódigo del hallazgo
rea evidence-export --json > evidence.json                   # artefacto reproducible
```

## ✅ CHECKLIST PRE-COMMIT RE
- [ ] `rea doctor --json` OK y proveedor declarado (`REA_ANALYSIS_PROVIDER`)
- [ ] Tipo de target verificado (magic/extensión), no asumido
- [ ] Hallazgos respaldados por xrefs/decompile (no inferencias sueltas)
- [ ] Evidencia exportada (`evidence-export`) y versionada con la conclusión
- [ ] `rea compare` ejecutado si hay baseline/parche
- [ ] Reconstrucción validada contra evidencia (round-trip o test)
- [ ] Licencias de Hopper/IDA/JEB respetadas (no redistribuir decompilados)
- [ ] Datos sensibles (PII/secretos) enmascarados en logs y reportes

## ⚠️ GUARDRAILS (ético — HARD)
- **Solo targets propios o con autorización explícita por escrito**. Sin autorización → detener.
- **Prohibido malware**, explotación activa o análisis de sistemas de terceros sin permiso.
- Respetar **licencias** de IDA/Hopper/JEB y EULAs; no exportar pseudocódigo propietario.
- Sin instalación de REA en este repo: la skill **documenta** su uso (MCP se registra aparte).
- Enrutar todo análisis al harness con evidencia trazable; **0 claims sin artefacto**.

## Anti-patrones (prohibidos)
- Afirmar comportamiento sin xrefs/decompile/trace que lo demuestren.
- Analizar binarios de terceros sin autorización escrita.
- Redistribuir decompilados de herramientas propietarias (IDA/Hopper/JEB).
- Exponer secretos/PII hallados sin enmascarar.
- Saltar `doctor`/`providers` y culpar a REA de fallos de entorno.

## Referencias (bajo demanda)
> Fuente: docs de REA (rea.tools). Cargar solo cuando la tarea requiera detalle de flags/tools.

- [CLI REA — comandos y flags](references/rea-cli.md) — todos los subcomandos `rea` y sus opciones.
- [MCP tools y env](references/mcp-tools.md) — catálogo de tools `rea.*` y variables de entorno.
