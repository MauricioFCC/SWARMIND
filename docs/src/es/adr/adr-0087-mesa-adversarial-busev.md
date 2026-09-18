# ADR 0087: Mesa Adversarial + BUSEV Ejecutables (Search MESA R3)

## Estado
Aplicado | `harness/orchestrator/{adversarial_table,evidence_search,sprt_governor}.py` + `harness/validation/antivenom_filter.py` + WIP-2/TTL en postmortem | Propietario: @coordinator | Fecha: 2026-09-08

## Contexto
Carpeta `01_search_frontier/mesa adversarial y busqueda metodos` (4 docs): metodología MESA adversarial (roles rotativos, R0 silencioso, R1-R2 con parada adaptativa, juez-fitness, escriba Habermas, veredicto escalonado 66%, WIP-2, actas→cognition), BUSEV (4 estrategias ciegas, matriz converge/condiciona, SIFT-1, filtro antiveneno 4 cortes, claim-trace), corpus-trampa (drill 4/4 newcomer) + frontera (debate Du/MAD/ReConcile/ChatEval/FREE-MAD/Habermas/SPRT/AgentAuditor/consenso/MADC/debate-training).

## Decisión (4 módulos, TDD, 20 tests)
1. **`adversarial_table`**: `triage()` easy→checklist/hard→table; R0 (3+ voces, confianza) → acuerdo ≥66% sin rondas; si no, R1-R2 con rotación; fallback `stake_weighted_vote`; acta con mayoría+minoría + métricas (rounds, agreement_round). Mutante del gate muerto.
2. **`evidence_search`**: 1+1 ciegas por defecto (investiga+refuta), escala a 4 con `escalate=True`; matriz `EvidenceMatrix` con IDs trazables.
3. **`antivenom_filter`**: 4 cortes (V1 spam, V2 >18m, V3 vendor sin método, V4 sin venue); solo PASS entra al veredicto (drill 4/4 del corpus).
4. **`sprt_governor`**: umbral (0,1) + cap; frontera exacta `>=` testada (mutante muerto).
5. **Postmortem §7**: WIP-2 + TTL + tripwire + dueño (0 sin dueño a 30d).

## Consecuencias
### Positivas
- Decisiones irreversibles con proceso adversarial auditable (no intuición).
- Evidencia con procedencia y vigencia (antiveneno antes del veredicto).
- Parada calibrada (no rondas fijas que derivan a fallo colectivo).

### Negativas
- La mesa cuesta 3+ llamadas por decisión (solo para irreversibles/costo alto; fanout_gate decide).
- Roles/personas de la metodología (Atacante/Steelman/Juez/Escriba) son prompts, no agentes nuevos (YAGNI: las voces se parametrizan).

## Alternatives Considered
1. **4 agentes fijos con roles hardcodeados**: rígido; voces parametrizadas reutilizan el pool existente.
2. **Debate sin cap**: martingala documentada (deriva a fallo colectivo); cap R2 + SPRT lo impiden.
3. **Voto sin juez previo**: Kaesberg: consenso 66% primario, voto fallback (ya implementado así).

## Relacionado
- ADR-0075 (fanout/stakes/competence), ADR-0073 (batch_vote), ADR-0079 (trace viewer: las actas son replayables)
- Du/ReConcile/ChatEval/MAD/Habermas/SPRT/AgentAuditor/MADC
