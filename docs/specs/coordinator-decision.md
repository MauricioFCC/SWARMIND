# Spec: Decisión del Coordinator — auditoría adversarial + calibración de agentes/skills

- **Estado:** propuesta + batería adversarial implementada (2026-10-08)
- **Rol autor:** guardian (SDD + TDD adversarial/mutante)
- **Principios:** `SPE` (Proof-or-Stop), `GATE`, `ADV`, `TST`, `PBT`, `SBX`, `ERR`, `DOC`, `CPD`
- **ADR relacionados:** ADR-0033 (DecisionTrace), ADR-0048 (TokenBudgetRouter),
  ADR-0075 (CompetenceModel / SkillOrchestra), ADR-0077 (TDD adversarial),
  ADR-0098 (Code conventions)
- **Módulos bajo auditoría (NO se modifican en esta tarea):**
  `harness/orchestrator/agent_selector.py`,
  `harness/orchestrator/competence_model.py`,
  `harness/orchestrator/confidence_scorer.py`,
  `harness/orchestrator/delegation_engine.py`,
  `harness/orchestrator/skill_bundler.py`,
  `harness/orchestrator/agent_dispatcher.py`,
  `harness/context/token_budget_router.py`,
  `harness/orchestrator/decision_trace.py`

## 1. Problema (WHY)

El coordinator decide **qué agentes y qué skills** activar por tarea con una
política de keyword-scoring, umbrales fijos y fallbacks silenciosos. Una
auditoría adversarial (ejecutada sobre el código del workspace, ver §9) revela
que la decisión **no es auditable ni abstinente** frente a entradas fuera de
dominio, y que varios umbrales son **calibrables** (el gate de evidencia de
competencia es inerte; los triggers de dominio tienen falsos positivos por
substring; la inyección de keywords altera la selección).

Sin abstention, anti-triggers, dedup y trazabilidad, el sistema no puede
demostrar por qué eligió un agente/skill ni negarse a hacerlo cuando la
confianza es insuficiente. Frontera (negative selection, calibrated thresholds,
adversarial routing): la decisión debe ser **función pura, explicable,
resistente a manipulación y con señal de abstención**.

## 2. Outcome medible

Al final, toda decisión de agente/skill del coordinator cumple:

1. **Determinista** para entrada y `rng` fijos (Thompson se inyecta con semilla).
2. **Abstenible**: entrada fuera de dominio no fuerza un agente/skill arbitrario
   (o lo documenta explícitamente).
3. **Trazable**: expone una razón (`rationale`/`DecisionTrace`) por decisión.
4. **Resistente a inyección**: keywords hostiles no alteran el resultado legítimo.
5. **Sin duplicados**: ni skills duplicadas en bundles, ni ids repetidos.
6. **Umbrales calibrados** con sentinelas de mutación que matan al mutante
   (boundary ±ε cambia la decisión).

## 3. Invariantes (contrato verificable)

| ID | Invariante | Verificación |
|----|-----------|--------------|
| INV-1 | `select`/`auto_route`/`detect_domain`/`compose` son función pura de la entrada | 2 llamadas idénticas → mismo resultado |
| INV-2 | Entrada fuera de dominio **no** fuerza agente/skill (o documenta el fallo) | abstention / `xfail` |
| INV-3 | La decisión expone razón o traza | `rationale` no vacío / `DecisionTrace` con registro |
| INV-4 | Trigger hostil no cambia la decisión legítima | baseline == baseline+inyección |
| INV-5 | No hay skills/ids duplicados en una misma decisión | `len(x) == len(set(x))` |
| INV-6 | Umbral inclusivo en el límite; ±ε cambia la decisión | boundary test + monkeypatch |

## 4. Requisitos funcionales (FR)

- [ ] **FR-1 Negative selection / anti-trigger**: añadir señales negativas que
  eviten falsos positivos por substring (p. ej. `"doc"` dentro de `"docker"`),
  tokenizando con límites de palabra en `skill_bundler.select_skills`.
- [ ] **FR-2 Abstention**: introducir sentinela explícita (`None` / `"coordinator"`)
  cuando ninguna señal supera un umbral mínimo en `agent_selector` y `skill_bundler`.
- [ ] **FR-3 Decision trace**: registrar cada decisión de routing en un
  `DecisionTrace` (strategy, agent, score, task_id) — hoy no existe wiring.
- [ ] **FR-4 Dedup**: garantizar unicidad de skills/ids en `select_skills`,
  `compose` y `TokenBudgetRouter.select` (formalizar la invariante).
- [ ] **FR-5 Calibrar `MIN_EVIDENCE_FOR_RERANK`**: el prior Beta(1,1) totaliza 2.0,
  por lo que el umbral actual (`2.0`) es inerte; debe exigir evidencia **posterior
  al prior** (p. ej. `> PRIOR_ALPHA + PRIOR_BETA`).
- [ ] **FR-6 Inyección**: descartar keywords de agentes/skills que no correlacionan
  con la tarea real (anti-prompt-injection en el scoring).
- [ ] **FR-7 Determinismo**: documentar y testear que Thompson sampling es
  determinista dado un `rng` inyectado.

## 5. Requisitos no funcionales (NF)

- [ ] **NF-1** 0 llamadas de red y 0 LLM en la batería de tests (`SBX`).
- [ ] **NF-2** T1 determinista < 90 s; sin dependencias nuevas.
- [ ] **NF-3** Back-compat de contratos públicos (`select` sigue devolviendo
  `list[str]`; `compose` → `list[AgentConfig]`).
- [ ] **NF-4** Docstrings ES + errores `WHAT+WHY+WHERE`; 0 `except: pass`.
- [ ] **NF-5** Portabilidad Win/Linux (`pathlib`, sin rutas absolutas de SO).
- [ ] **NF-6** Sin efectos secundarios en disco salvo `tmp_path` de pytest.

## 6. Exit criteria (Gates)

- [ ] `ruff check harness/tests/test_coordinator_decision_invariants.py` → 0 errores.
- [ ] `pytest harness/tests/test_coordinator_decision_invariants.py -q -rx` →
  0 `failed`; los hallazgos pendientes quedan `xfailed` (no `failed`).
- [ ] Sentinelas de mutación (INV-6) verdes: los asserts matan mutantes de umbral.
- [ ] Al implementar FR-1..FR-7 los `xfail` pasan a `xpass` (no se borra el test).
- [ ] Mutation score ≥ 70% (nightly, `mutmut` en WSL) objetivo 85% (`TST`).
- [ ] Evidencia cruda registrada en §9 y commit

## 7. Sandbox (aislamiento de fallos)

- **Modifica (esta tarea):** nada de producción.
- **Crea:** `specs/coordinator-decision.md`,
  `harness/tests/test_coordinator_decision_invariants.py`.
- **NO toca:** los 8 módulos de producción (solo se leen).
- **Futuro (implementación de FR):** los 6 módulos de decisión + `decision_trace`.

## 8. Rollback plan

1. `git checkout -- specs/coordinator-decision.md harness/tests/test_coordinator_decision_invariants.py`
   (o `Remove-Item` si son nuevos).
2. Verificar: `uv run python -m pytest harness/tests/ -q` → 0 regresiones.

## 9. Evidencia cruda de la auditoría (observado en workspace)

Comandos ejecutados: `uv run python` (probes) + suite de tests. Todos los
resultados provienen del código del workspace (`harness/__init__.py` del repo).

| Invariante | Esperado | Observado | Estado |
|-----------|----------|-----------|--------|
| INV-1 | función pura | `select` x3 idéntico; `auto_route` x2 idéntico | ✅ cumple |
| INV-2 | abstention fuera de dominio | `agent_selector.select("xyzzy plugh")` → `['builder']` | ❌ **incumple** |
| INV-2 | abstention fuera de dominio | `delegation_engine.auto_route("xyzzy plugh")` → `coordinator` | ✅ cumple |
| INV-3 | razón/traza | `TokenBudgetRouter.select` → `rationale="score=1.000 tokens=100 vecinos=0"` | ✅ cumple |
| INV-3 | traza de routing | `agent_selector.select` y `auto_route` **no** emiten `DecisionTrace` | ❌ **incumple** |
| INV-4 | trigger hostil neutral | `auto_route("... ; self-improve")` → `builder` (no `evolve`) | ✅ cumple |
| INV-4 | trigger hostil neutral | `select("API Rust + 'selecciona evolve'")` → `['builder','evolve']` (baseline `['builder','guardian']`) | ❌ **incumple** |
| INV-4 | trigger hostil neutral | `define_domain("datos pandas\nSYSTEM: security audit")` → `security` | ❌ **incumple** |
| INV-5 | sin duplicados | `select_skills` (todos los dominios x tasks) sin dups; `compose` sin dups; `TokenBudgetRouter` sin ids dups | ✅ cumple |
| INV-6 | umbral inclusivo | dispatch sim == 0.70 → `used_skill=True`; 0.699… → `False` | ✅ cumple |
| INV-6 | umbral inclusivo | budget == 100 incluye nodo 100; budget 99 lo excluye | ✅ cumple |
| INV-6 | umbral inclusivo | `ConfidenceScore(0.90).should_stop=True`; `0.8999 → False` | ✅ cumple |
| FR-5 | sin evidencia → no re-rank | `CompetenceModel` sin updates altera `select` (prior total 2.0 ≥ umbral 2.0) | ❌ **incumple** |
| FR-1 | sin falso trigger | `select_skills("devops","desplegar docker")` añade `science-doc`,`legal-doc` (`"doc"` ⊂ `"docker"`) | ❌ **incumple** |

Hallazgos priorizados para las mejoras:
1. **FR-2/INV-2** `agent_selector` nunca abstiene (siempre `builder`).
2. **FR-5/INV-6** gate de evidencia inerte por igualdad con el prior.
3. **FR-1** falso trigger `"doc"` ⊂ `"docker"` (falta límite de palabra).
4. **FR-6/INV-4** inyección de keyword de agente/dominio altera la selección.
5. **FR-3/INV-3** falta wiring de `DecisionTrace` en la selección.

## 10. Fuentes frontier

| Técnica | Referencia |
|---|---|
| Mutation testing (matar mutantes de umbral) | `mutmut` / `cosmic-ray` (TST) |
| Property-based / boundary | `hypothesis` + BVA por variable (TST) |
| Adversarial test↔mutante | AdverTest, arXiv:2602.08146 |
| Refinamiento adversario de propiedades | PROBE (ACL'26) |
| Composición de agentes desde skills (SIGMA) | arXiv:2606.19758 (docstring `skill_bundler`) |
| Routing por competencia evidenciada | SkillOrchestra (ADR-0075) |
| Spec-first proof-or-stop | Huang 2026 (`SPE`) |

## 11. Verificación (comandos de la tarea)

```
uv run ruff check harness/tests/test_coordinator_decision_invariants.py
uv run python -m pytest harness/tests/test_coordinator_decision_invariants.py -q -rx
```

Mutación (no viable nativo en Windows → documentado):
```
uvx mutmut run --paths-to-mutate harness/orchestrator/agent_selector.py ...
# Windows: "To run mutmut on Windows, please use the WSL." (issue boxed/mutmut#397)
```
Compensación: sentinelas de mutación en la batería (INV-6) que fijan límites y
demuestran, vía `monkeypatch`, que cambiar el umbral cambia la decisión.