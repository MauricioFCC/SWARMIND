# ADR 0075: Skills/Agentes Frontera — Composición, Competencia Beta y Gate Anti-Sobre-Descomposición

## Estado
Aplicado | `harness/context/skill_composition.py` + `harness/orchestrator/competence_model.py` + `harness/orchestrator/fanout_gate.py` | Propietario: @coordinator | Fecha: 2026-09-08

## Contexto
Research frontera (sep-2026) sobre skills y agentes, 2 tracks. Técnicas evaluadas con delta+alfa alto; IDP check contra el repo (progressive disclosure ADR-0048, PEC universal ADR-0072, tiers ADR-0053, adaptive_planner, failure_registry, session_affinity ADR-0073 ya cubren parte):

**Skills (8 destiladas):**
- SkillRouter retrieve-and-rerank (Hit@1=0.740 a 80K skills, body=señal decisiva 91.7% atención cross-encoder) → **SKIP**: en catálogos de miles; con 34 skills keyword+PEC basta (YAGNI de deps embeddings/FAISS).
- Composición skill-como-primitiva (Pocock v1.0): **−63% tokens**; skills compartidas delegadas.
- Taxonomía invocation (user|model|skill): composites no tasan la sesión raíz.
- Set-compatibility (Wang): un set debe ser ejecutable en conjunto, no solo relevante.
- SkillReranker adaptive-size, SAD compositional routing (51%→67.7%), curriculum por dificultad → diferidos (necesitan corpus grande o LLM de descomposición).

**Agentes (11 destiladas):**
- Sub-goals verificables GDE + RRM runtime + SIL policy-traces → **diferido a ADR futuro** (refactor del task_planner; grande).
- **Gate anti-sobre-descomposición** (Minitap arXiv:2602.07787 + EECS-2026-123): baseline single-agent ≥80% → fan-out amplifica errores hasta **17.2×**.
- **Competence modeling Beta** (SkillOrchestra): posterior por (agente×skill), evita routing collapse.
- imp@k (HyperAgents arXiv:2603.19461): métrica de mejora transferente por experimento.
- Confidence-aware gate (Nature s41598): switching instability −75% → ya cubierto por session_affinity (ADR-0073); métricas de churn quedan para el wiring.
- Post-validación vs estado real (Minitap 100% AndroidWorld), escalado mid-task (OI-MAS +7.68%), score 5-factor EFFGEN (τ=7.0±1) → diferidos (requieren verifier/probe infra).

## Decisión (3 módulos, TDD, 20 tests)
1. **`skill_composition.py`**: `parse_calls` (frontmatter `calls: [a,b]`), `parse_invocation` (tier user|model|skill, default model), `resolve_composition` (lazy DFS con dedup y **detección de ciclos** — a→b→a falla accionable), `prune_conflicts` (poda pares conflictivos conservando orden; matriz inyectable).
2. **`competence_model.py`**: posterior Beta(1,1) por (agente×skill); `update` con traces; `select` con **Thompson sampling** (o utilidad `sample − λ·costo`); mantiene exploración del agente débil (anti-collapse); `imp_at_k` = Δ métrica / k experimentos.
3. **`fanout_gate.py`**: `should_fanout(baseline_success, force)` — <80% → FANOUT; ≥80% → SINGLE (evita amplificación ×17.2); `force` como escape hatch.

## Consecuencias
### Positivas
- Skills componibles (calls) eliminan duplicación inline — camino directo al −63% de Pocock en el próximo pas de refinamiento de skills.
- Routing de agentes con evidencia (Beta+Thompson) en vez de keywords fijas; sin colapso.
- Fan-out solo cuando paga (baseline débil); ahorra el 17.2× de ruido en tareas simples.

### Negativas
- `calls:` aún no está declarado en las 34 skills (wiring pendiente; el parser está listo).
- Thompson sampling introduce variabilidad estocástica (rng inyectable para determinismo en tests).
- El gate anti-fanout requiere un probe de 1 pasada antes de decidir (costo pequeño pero real).

## Alternatives Considered
1. **SkillRouter con embeddings/FAISS**: pago a escala de miles de skills; con 34 es overhead (YAGNI).
2. **GDE sub-goals verificables ya**: refactor del planner entero; se difiere con spec a ADR-0076 potencial.
3. **Greedy en competencia (sin Thompson)**: colapso temprano al ganador inicial (SkillOrchestra lo documenta).

## Relacionado
- ADR-0052 (habilidades), ADR-0072 (PEC), ADR-0073 (session affinity), ADR-0074 (contexto)
- Pocock skills v1.0 (−63%), SkillRouter arXiv:2603.22455, SkillOrchestra (Wang 2026), Minitap arXiv:2602.07787, HyperAgents arXiv:2603.19461, EECS-2026-123
