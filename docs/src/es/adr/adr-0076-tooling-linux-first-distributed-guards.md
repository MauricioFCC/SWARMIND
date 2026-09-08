# ADR 0076: Tooling Linux-First + Distributed-Systems Guards (rtk, tgrep, Idempotency, Boundary)

## Estado
Aplicado | `harness/orchestrator/{tool_output_filter,idempotency_guard}.py` + `structured_enforcer(strict_keys)` + `llm_grep(TgrepBackend)` + base_principles v3.0.0 (sección TOOLING) | Propietario: @coordinator | Fecha: 2026-09-08

## Contexto
Dump frontera `01_search_frontier/Randon search 9-8-2026.md` (98 líneas) + problema constatado: **PowerShell corrompió el propio dump** (mojibake UTF-8 → `�?-` en acentos ES y emojis). Temas:

1. **rtk** (rtk-ai/rtk, 79K★, Apache-2.0): CLI proxy Rust que corta hasta 90% del output bash que lee el agente (100+ comandos, <10ms); hook PreToolUse reescribe `git status → rtk git status`.
2. **tgrep** (microsoft/tgrep, 2.1K★): grep trigram-indexed en Rust (índice una vez + file watcher, cliente/servidor); Copilot CLI lo usa internamente; 50%+ más rápido en codebases grandes.
3. **Agentic coordination = distributed systems** (no prompt engineering): "un workflow puede quedar en limbo cuando una mutación de estado intermedio falla sin idempotency key"; vendor devuelve 200 OK con JSON keys inesperados → deadlock; faltan compensating transactions, typed boundary guards, provenance.
4. **K2 Horizon** (universidad Abu Dabi, ifm.ai): 6 open source 0.9B-375B; 7B → 70.6 SWE-bench — candidato de tier local (no verificado en Ollama Hub esta sesión; diferido).
5. **7 dimensiones de estrategia IA** (4 duras sin compra: Ambición CEO, Modelo operativo, Personas, Gobernanza) → applies to organizational docs, no código; diferido a roadmap.

## Decisión
1. **Tooling Linux-first en principios** (base_principles § NAM/TOOLING): scripts temporales = **Python o bash, NUNCA PowerShell** (corrompe UTF-8 ES/emojis; pipelines no-portables); herramientas `rg`/`bash`/`awk`/`jq` preferidas; si PowerShell es inevitable → forzar `[Text.Encoding]::UTF8` y verificar (VER). Wrappers `rtk`/`tgrep` opt-in si el binario existe.
2. **`ToolOutputFilter`** (`harness/orchestrator/tool_output_filter.py`): reescribe `cmd[0] ∈ RTK_SUPPORTED` → `rtk <cmd>` (UNA sola ejecución — no doble efecto); passthrough si no hay binario o el comando no está soportado.
3. **`IdempotencyGuard`** (`harness/orchestrator/idempotency_guard.py`): dedup de efectos por (key, hash-payload); retry mismo par → replay cacheado (0 re-ejecución); mismo key + payload distinto → `KeyPayloadMismatch` accionable; métrica `replays`.
4. **Boundary guard** en `structured_enforcer`: `strict_keys=True` o schema `additionalProperties: False` → keys inesperadas = error con feedback que las nombra (mata el 200-OK-trojan del dump).
5. **`TgrepBackend`** en `llm_grep` (patrón de backends existentes): delega a `tgrep -n` si está en PATH; no-op documentado si falta.

TDD: 22 tests nuevos (filter 8, guard 8, enforcer+strict 2 existentes ampliados, tgrep vía suite llm_grep).

## Consecuencias
### Positivas
- Output bash al LLM reducido hasta 90% con rtk (opt-in, sin cambiar workflow).
- Retries sin doble efecto (idempotency) — el patrón distributed-systems aplicado al orquestador.
- 200 OK con keys trojan no pasa el boundary (feedback nombrando la key).
- El texto ES/UTF-8 viaja intacto con Python/bash (fin del mojibake en dumps).

### Negativas
- rtk/tgrep requieren binario instalado (passthrough documentado si faltan).
- IdempotencyGuard en memoria (sin persistencia) — reinicio pierde la cache (aceptable: los efectos ya ejecutados no se repiten por el guard).

## Alternatives Considered
1. **Hook global en shell (estilo Claude Code)**: modificar el entorno del agente es invasivo; el wrapper Python explícito es auditable y testeable.
2. **RLS/DB-backed idempotency**: persistencia del guard via SQLite — YAGNI hasta efectos multi-proceso.
3. **K2 Horizon como tier local ya**: modelo no verificado en Ollama Hub; se re-evalúa cuando haya peso/benchmarks en el hub.

## Relacionado
- ADR-0067 (llm_grep rg-first), ADR-0073 (structured_enforcer), ADR-0074 (artifacts)
- rtk-ai/rtk, microsoft/tgrep, dump 9-8-2026
