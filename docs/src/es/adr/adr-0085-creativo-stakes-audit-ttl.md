# ADR 0085: Creativo Frontera — Voto con Stakes, Trajectory Audit y TTL en Cognition

## Estado
Aplicado | `stake_weighted_vote` + `trajectory_audit.py` + TTL en `cue_ledger` | Propietario: @coordinator | Fecha: 2026-09-08

## Contexto
Research frontera super-creativo (sep-2026): Ouroboros (self-developing harness, trajectory audits, Terminal-Bench 86.74% auditado), wagering mechanisms (arXiv:2607.04389), KalshiBench (deliberative consensus DEGRADA a 76% por sycophancy), CL-Bench (metadata temporal + TTL: 0.2301 vs 0.1855), agent credentials (completion records verificados).

## Decisión
1. **`stake_weighted_vote`** (en `batch_vote.py`): ponderación por stakes de confianza (equilibrio = ventaja esperada); empate exacto → None; validación [0,1]. Sin rondas de debate (KalshiBench: sycophancy).
2. **`trajectory_audit`**: flags por acceso a tests/verifier/oracle/solutions (9 reglas) → auto-zero; traza limpia → 1.0.
3. **TTL en `CueEntry`** (`ttl_s`, default None = compat): `_live_entries()` poda expirados con métrica `pruned_expired`; anti-stale CL-Bench.

TDD: 8 tests; ruff 0; mutante del audit muerto.

## Consecuencias
### Positivas
- Votos calibrados por confianza (pocos fuertes > muchos dudosos).
- Métricas a prueba de reward-hacking (auditoría de trayectoria).
- Memoria sin lessons stale (TTL + staleness + reset).

### Negativas
- Stakes auto-reportados pueden miscalibrarse (mitigado: supervisor + competence los recalibra).
- TTL requiere elegir duración por dominio (default: sin expiración).

## Alternatives Considered
1. **Debate multi-ronda**: KalshiBench lo desaconseja (76% < baselines).
2. **ZK-proofs on-chain (Veriagent)**: overkill para harness local; el ledger + hash basta.
3. **Borrar cues stale manualmente**: el TTL lo automatiza.

## Relacionado
- ADR-0073 (batch vote), ADR-0074 (cue-ledger), competence_model, Ouroboros/wagering/CL-Bench
