# ADR 0088: Search 9-17 — QUAD, Bitemporal, Restrictor, Shunt, Misbehavior, Dream-Replay

## Estado
Aplicado | `harness/validation/task_quad.py` + bitemporal en `cue_ledger` + `harness/orchestrator/{content_restrictor,read_guard}.py` + `harness/security/misbehavior_guard.py` + `harness/evolve_loop/dream_replay.py` | Propietario: @coordinator | Fecha: 2026-09-08

## Contexto
Dump `01_search_frontier/Search 9-17-2026.md` (36 posts LinkedIn, 80 URLs): VoiceStudio local, Command Code (plan+skills+Playwright+prefs), QUAD (anti-vaguedad + 1 dueño), Claude skills lazy-load, memoria bitemporal (valid+tx time), stack IA local $0, skills audit triple, vibe-coding gates, MoE routing, skill-auditor 6 fases, Strands loop, SerpApi markdown (-74%), LLM fundamentals, AI-First rieles, anti-slop, Spotify shunt (90% tokens era mover contexto), GitNexus graph, trigramas 50x (ya: tgrep), agente=4 sistemas, OpenAI 6 conductas, Dream-RSI replay offline, GNN (no escalar naive).

## Decisión (6 deltas, TDD, 19 tests)
1. **`task_quad`**: gate Que/Hasta-cuándo/Estándar/Impacto + 1 solo dueño (lista/dict/set = nadie).
2. **Bitemporal en cues**: `valid_from/valid_to` ISO + `valid_at(fecha)`; TTL ya existía (ADR-0085).
3. **`content_restrictor`**: JSON buscador → solo orgánico (ads/pagination/related fuera); markdown pasa limpio.
4. **`read_guard`**: tope 8K chars; exceso → ArtifactStore (preview+handle); retrieve con offset.
5. **`misbehavior_guard`**: pre-tool-call (creds expuestas, uploads externos, destructivos) → BLOQUEO + approval.
6. **`dream_replay`**: replay offline de trazas ok/fail (improved/unchanged; regressed requiere oráculo).

TDD: 19 tests; ruff 0; 2 mutantes muertos (preview-truncate ya, quad-owner); roundtrip artifact byte-exacto.

## Consecuencias
### Positivas
- Asignaciones sin vaguedad (QUAD) + memoria con vigencia (bitemporal).
- -74% en resultados web; lecturas grandes no mueven contexto (shunt).
- 6 conductas OpenAI bloqueadas por diseño, no por suerte.

### Negativas
- Misbehavior con regex (heurístico; FPs posibles en strings raros — threshold documentado).
- Dream-replay sin oráculo no detecta regresiones (honesto: regressed=0).

## Alternatives Considered
1. **VoiceStudio local TTS/ASR**: capacidad nueva sin caso de uso en el harness (YAGNI).
2. **Headroom compressor externo**: nuestro stack (compaction+artifacts+restrictor) ya cubre.
3. **GNN naive**: barren plateau documentado; no escalar (del propio dump).

## Relacionado
- ADR-0074 (artifacts), ADR-0076 (boundary), ADR-0085 (TTL), Search 9-17-2026.md
