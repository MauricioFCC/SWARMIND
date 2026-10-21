# Spec: ADR-0103 — Frontera Simple 2026 (roadmap SDD/TDD)

- **Estado:** propuesta + workstreams RED (2026-10-12)
- **Principio rector:** `SPE` (Spec-First / Proof-or-Stop) + `TST` (TDD adversarial/mutante) + `FRS` (Frontier Research)
- **ADR de origen:** ADR-0103 (`docs/adr/adr-0103-frontera-simple-2026.md`)
- **Alcance:** `harness/orchestrator/` (telemetría, triage, hidden-body, fan-out), `harness/model_router/` (cache-shape), `harness/memory_rag/` (masking default, token telemetry), `.opencode/agents/coordinator.md` + `coordinator_policy.yaml`, `.opencode/skills/skills_registry.yaml`, `.opencode/core/base_principles*.md`
- **Relación:** consume `TKN`, `GATE`, `SPE`, `FRS`, `ADV`; verificada por los tests listados en exit criteria

---

## 1. Problema (WHY)

El harness clasifica por heurística pura, asigna agentes por keywords, coordina
con un prompt de 273 líneas y optimiza tokens SIN medir. La frontera 2026
(evidencia en ADR-0103) muestra que: (a) el routing se aprende con clasificador
barato + evidencia (no preferencia); (b) el coordinador frontera es un prompt
corto con política en configuración; (c) el ahorro de tokens 30-60% exige
telemetría primero (cache-shape + masking); (d) el fan-out se satura; (e) las
skills son supply-chain y requieren digests.

**Hipótesis:** implementar las 8 acciones con TDD (cada una con test RED
discriminante) lleva el harness a estado del arte 2026 reduciendo complejidad.

---

## 2. Outcome medible (qué es "hecho")

1. `TokenTelemetry` registra `cached_tokens`, `input_tokens`, `tokens_por_rol`,
   `hit_rate` por sesión y expone `hit_rate()` y `gate_ok(threshold=0.80)`.
2. El prompt del coordinador se ensambla con orden cache-shape
   (`tools→system→estático→dinámico`) vía `build_cache_shaped_prompt()`.
3. `coordinator.md` ≤ ~70 líneas; la doctrina migra a `.opencode/agents/coordinator_policy.yaml`.
4. Observation masking activo por defecto (flag `SWARMIND_OBS_MASKING_DEFAULT=1`).
5. `TriageResult` (JSON `{intent, complexity}`) producido por SLM con cascada
   fallback a `DifficultyRouter` si el small_model falla.
6. `SkillRouter`/`AgentDispatcher` puntúan leyendo el cuerpo del SKILL.md/agent .md
   (hidden-body asymmetry), no solo metadata.
7. Fan-out cap: `DynamicScaling` limita a 5 agentes por defecto (configurable);
   debate vanilla reemplazado por votación + `MinoritySentinel` (opcional, votación ya existe).
8. `skills_registry.yaml` expone `sha256` por skill; `validate_skills.py --strict`
   verifica el digest si el archivo existe.

---

## 3. Requisitos funcionales (FR)

- **WS-A (token economics):**
  - FR-A1: módulo `harness/observability/token_telemetry.py` — `TokenTelemetry`
    thread-safe, `record_usage(role, cached, input, output)`, `hit_rate()`,
    `gate_ok(threshold)`, `report()` a `structured_log`.
  - FR-A2: `harness/orchestrator/context_scoped.py` (o nuevo `prompt_cache_shape.py`)
    — `build_cache_shaped_prompt(blocks: list[dict]) -> str` respeta el orden
    canónico y registra el breakpoint de caché.
  - FR-A3: `context_window_manager._apply_observation_masking` pasa a default ON
    vía `feature_flags`/env `SWARMIND_OBS_MASKING_DEFAULT`.
- **WS-B (coordinador):**
  - FR-B1: `.opencode/agents/coordinator_policy.yaml` — delegación, presupuesto,
    verificación, memoria (SSOT de política).
  - FR-B2: `coordinator.md` reducido a ~70 líneas que referencia el YAML.
- **WS-C (routing):**
  - FR-C1: `harness/orchestrator/triage_slm.py` — `TriageSLM.triage(text) ->
    TriageResult{intent, complexity}` con DI del small_model; `fallback()` a
    `DifficultyRouter` ante excepción/timeout.
  - FR-C2: `SkillRouter.route()` y `AgentDispatcher.find_skill_for_task()`
    puntúan con cuerpo (leer `.min.md`/`.md`) además de metadata.
  - FR-C3: `DynamicScaling` max 5 por defecto (constante `MAX_FANOUT_DEFAULT=5`,
    env `SWARMIND_MAX_FANOUT`).
- **WS-D (seguridad):**
  - FR-D1: `scripts/validate_skills.py` — verifica `sha256` en registry contra el
    archivo si el campo existe; `scripts/hash_skills_registry.py` rellena digests.

---

## 4. Requisitos no funcionales (NF)

- **NF-1 (atomicidad):** cada FR = 1 commit (ATM), 1 test = 1 criterio (AAA).
- **NF-2 (no-regresión):** suite de 6000+ tests pasa; ruff 0; bandit -ll 0.
- **NF-3 (determinismo):** triage SLM tiene fallback determinista; tests con
  mocks (0 LLM real en unit).
- **NF-4 (idempotencia):** telemetría y masking no mutan estado sin llamada.
- **NF-5 (tokens):** `build_cache_shaped_prompt` no reordena bloques inesperados;
  el orden es estable entre llamadas (cache-hit).
- **NF-6 (seguridad):** digests sha256 con `usedforsecurity=False` (dedup/verif,
  no criptográfico — evita B324).

---

## 5. Diseño (mapping canónico)

| Acción | Archivo(s) | Función principal | Verificación |
|:------:|-----------|-------------------|:------------:|
| 1 | `harness/observability/token_telemetry.py` (nuevo) | `TokenTelemetry.record_usage/hit_rate/gate_ok` | `test_token_telemetry.py` |
| 2 | `harness/orchestrator/prompt_cache_shape.py` (nuevo) | `build_cache_shaped_prompt` | `test_prompt_cache_shape.py` |
| 3 | `.opencode/agents/coordinator.md` + `coordinator_policy.yaml` | recorte + política | `test_coordinator_policy.py` |
| 4 | `harness/memory_rag/context_window_manager/manager.py` | masking default | `test_obs_masking_default.py` |
| 5 | `harness/orchestrator/triage_slm.py` (nuevo) | `TriageSLM.triage` + fallback | `test_triage_slm.py` |
| 6 | `harness/orchestrator/skill_bundler.py`, `agent_dispatcher.py` | puntuar con cuerpo | `test_hidden_body_router.py` |
| 7 | `harness/orchestrator/difficulty_router.py` (cap), `mars_scheduler` | `MAX_FANOUT_DEFAULT` | `test_fanout_cap.py` |
| 8 | `scripts/validate_skills.py`, `scripts/hash_skills_registry.py` | digests sha256 | `test_skills_digest.py` |

Workstreams paralelos (WS-A..E): WS-E = regla N1 `RSV` en base_principles +
min + full + `test_principles_integrity.py` extendido.

---

## 6. Exit criteria (Evidence-Gated, `GATE`)

- [ ] `uv run pytest harness/tests/test_token_telemetry.py harness/tests/test_prompt_cache_shape.py harness/tests/test_triage_slm.py harness/tests/test_hidden_body_router.py harness/tests/test_fanout_cap.py harness/tests/test_obs_masking_default.py harness/tests/test_skills_digest.py harness/tests/test_coordinator_policy.py -q` → GREEN (test RED antes del código).
- [ ] `uv run ruff check harness/ scripts/` → 0.
- [ ] `uv run bandit -r harness/ -x harness/tests -ll -q` → exit 0.
- [ ] `uv run python scripts/validate_skills.py --strict` → exit 0 (con digests).
- [ ] `coordinator.md` ≤ 70 líneas; `coordinator_policy.yaml` existe y es parseable.
- [ ] N1 incluye `RSV` en base_principles.md == min.md == full.md (anti-drift).
- [ ] Suite completa `pytest harness/tests/` sin regresiones (>6000).
- [ ] Mutation-style: al menos 1 assert por check que RECHAZA al mutante (borrar
      una regla/campo/orden rompe el test).

---

## 7. Sandbox y rollback

- **Sandbox (SBX):** por workstream: WS-A toca `harness/observability`,
  `harness/orchestrator`, `harness/memory_rag/context_window_manager`;
  WS-B toca `.opencode/agents/`; WS-C toca `harness/orchestrator`,
  `harness/model_router`; WS-D toca `scripts/`. Cada workstream aísla sus tests.
  Sin LLM real en unit (mocks); sin red.
- **Rollback:** cada FR = commit atómico (ATM). `git revert <commit>` restaura.
  La política YAML y el recorte de coordinator.md van en commits separados:
  primero YAML (aditivo), luego recorte (destructivo) — revert del recorte no
  pierde doctrina.

---

## 8. Tareas (tasks)

- [x] **T1** Investigación frontera 4 frentes + diagnóstico interno (2026-10-12).
- [x] **T2** ADR-0103 + este spec SDD (roadmap 8 acciones + WS paralelos).
- [ ] **T3** WS-E: regla N1 `RSV` en principios + tests de integridad.
- [ ] **T4** WS-A: telemetría (FR-A1) + cache-shape (FR-A2) + masking default (FR-A3).
- [ ] **T5** WS-B: coordinator_policy.yaml + recorte coordinator.md.
- [ ] **T6** WS-C: triage SLM (FR-C1) + hidden-body (FR-C2) + fan-out cap (FR-C3).
- [ ] **T7** WS-D: digests sha256 (FR-D1).
- [ ] **T8** Verificación integral (suite completa + ruff + bandit + validate_skills).
- [ ] **T9** Actualizar `docs/src/es/roadmap/estado.md` (hitos 2026-10-12).
- [ ] **T10** Propagación opcional (deploy_all + sync global) — respuesta del usuario.

---

## 9. Notas de verificación

- El orden de prioridad (EDV) es: 1→2→3→4→5→6→7→8 por ROI/riesgo.
- Referencias arXiv: 2609.00006 (harness), 2603.22455 (SkillRouter),
  2508.21433 (Complexity Trap/masking), 2607.15516 (CAPC), 2512.08296 (scaling),
  2603.13657 (MAST), 2608.12720 (ERSkill), ACL 2026 (debate vs majority-vote).
- Si mutmut no es viable (Windows), mutation-style asserts = oráculo sustituto
  (patrón ADR-0098 §7).