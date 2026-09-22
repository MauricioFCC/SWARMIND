# ADR 0098: Deep-Docs — Credentials, Tool Pipeline, Op-Sec, Attachments, Delegation

## Estado
Aplicado | `harness/security/{credential_ref,op_sec}.py` + `harness/orchestrator/{tool_pipeline,delegation_scope,attachment_gate}.py` | Propietario: @coordinator | Fecha: 2026-09-08

## Contexto
Barrido total de `01_search_frontier` + 2 especialistas (deepseek docs/packages restantes + PDFs vs repo): ideas no implementadas con ROI — credentialRef by-name, tool-execution-pipeline, defensive-patterns, attachments admit+verify, subagent catalog parent-owned. PDFs verificados: @skills IMPLEMENTADO, coherence IMPLEMENTADO, Agent Lightning PARCIAL (rescatar dedup+idempotencia; descartar RL sin cluster).

## Decisión (5 módulos, TDD, 16 passed + 1 skip platform)
1. **`credential_ref`**: secretos por nombre, resolve per-op sin caché (rotación next-request), describe UI-safe, records `<scope/id>`.
2. **`tool_pipeline`**: pre→guards monotónicos→approval→around→post→finalize inmutable; guard roto = bloquear, approval rota = denegar.
3. **`op_sec`**: `scrub_secrets` (KEY/SECRET en logs) + `secure_tmpdir` 0700 (POSIX; Windows por ACL).
4. **`attachment_gate`**: admit con digest + verify-on-read fail-closed ante swap.
5. **`delegation_scope`**: statement frozen parent-owned (skills+acciones); inmutable desde dentro.

TDD: 16 tests; ruff 0; mutante del pipeline muerto.

## Consecuencias
### Positivas
- Secretos rotables sin restart ni valores en contexto/logs.
- Tool-calls con política reordenable sin tocar el loop.
- Multimodal durable sin inyectar bytes (fail-closed).

### Negativas
- Vault real (keyring/KMS) y TTL quedan futuros (documentado).
- `attachment_gate` verifica archivos, no URLs remotas.

## Alternatives Considered
1. **Vault externo ya**: overkill sin threat model; by-name lo prepara.
2. **Subagentes continuables con sesión durable**: requiere runtime de sesiones (diferido).
3. **RL harnessed completo**: sin cluster de entreno (descartado, solo dedup+idempotencia rescatados).

## Relacionado
- ADR-0076 (boundary), SEG, HITL, misbehavior_guard, deepseek-harness-master/vendor (excluido: deps terceros)
