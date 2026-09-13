# ADR 0079: Verify-Replan Gate + Trace Viewer + Permisos por Agente + Skill agent-rigor

## Estado
Aplicado | `harness/orchestrator/{verify_replan_gate,trace_viewer}.py` + `opencode.json:agent.*` + skill `agent-rigor` (PEC-35) | Propietario: @coordinator | Fecha: 2026-09-08

## Contexto
Research frontera (sep-2026): repos similares y tendencias 2026 —
- **VMAO** (ICLR26, Plan-Execute-Verify-Replan): stop si ≥80% completo o 75% confianza+50% completo; tokens Exec 61%/Verify 16%/Synthesis 10%.
- **Open Multi-Agent** (6.8k★): goal-not-graph, DAG runtime determinista, trace store inspeccionable + replay offline sin modelo, approval solo en acciones consequential.
- **opencode docs**: `agent.<nombre>.permission.task` con globs allow/deny/ask (Build full vs Plan restricted); subagentes General/Explore/Scout.
- **agent-rigor** (engineering discipline como skill): gates deterministas pre-merge.
- **Harness Effect** (arXiv 2607.06906): −41% coste/task con harness; medir $/task, no solo pass-rate.

IDP: HITL guard, behavioral tracer, fan-out+voting, DAG planner y auto-merge ya existen — se extienden, no se duplican.

## Decisión
1. **`VerifyReplanGate`**: `evaluate(completion, confidence)` con umbrales VMAO (STOP_COMPLETE=0.8, combo 0.75+0.5); fail-fast fuera de [0,1]; mutante de frontera muerto.
2. **`trace_viewer`**: `export_trace(decisiones) -> trace.jsonl` + `replay_trace(path, player)` determinista sin LLM (aísla regresiones de lógica vs varianza del modelo).
3. **Permisos granulares** en `opencode.json`: coordinator primary (task: `*`=ask, `builder-*`/`scientist-*`/`guardian-*`=allow); builder subagent (edit allow, bash ask); guardian (edit deny, bash allow); scientist (edit deny, bash ask, webfetch allow).
4. **Skill `agent-rigor`** (PEC-35): disciplina pre-merge (!rigor-premerge, !rigor-decorativos; coverage piso, MS≥70%, anti-pintar-verde) con PERSONA & CANON + registry + gate de 171→176 tests PEC.

TDD: 8 tests nuevos (gate 5 + viewer 3); ruff 0; suite PEC 176 verdes; `validate_skills --strict` ✅ (35 skills).

## Consecuencias
### Positivas
- El loop verify→replan tiene criterio de parada justificado (no itera sobre planes casi-listos).
- Trazas auditables y re-ejecutables sin costo de modelo.
- Least privilege por agente (defense in depth con el HITL existente).

### Negativas
- El gate VMAO aún no está enchufado en el DAG planner (siguiente wiring, como ADR-0075).
- agent-rigor añade standing tax solo si se instala (tier REFERENCE por defecto).

## Alternatives Considered
1. **SkillRouter con embeddings**: YAGNI a 35 skills (documentado en ADR-0075).
2. **Factory programada forgeo**: cron nocturno con commits directos a main — choca con branch protection; diferido.
3. **126 skills estilo godmode**: dilución de retrieval (SkillsBench); 35 PEC curadas > 126 planas.

## Relacionado
- ADR-0072 (PEC), ADR-0075 (wiring), ADR-0053 (tiers), VMAO ICLR26, OMA, Harness Effect arXiv:2607.06906
