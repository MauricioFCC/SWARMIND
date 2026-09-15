# ADR 0083: Roles y Procesos de Empresa Élite — DORA, Shape Up, Trunk, RFC, Postmortem + Limpieza de Legados

## Estado
Aplicado | agente `platform-engineer` + `FeatureFlags` + `specs/task_template.md` (appetite/bet) + `specs/postmortem_template.md` + principios v3.2.0 (DOR/SPE/FAIL/OPS) + eliminación de 7 monolitos sombreados | Propietario: @coordinator | Fecha: 2026-09-08

## Contexto
Research frontera (sep-2026): roles y procesos de empresas profesionales de vanguardia —
- **DORA 2024** (N≈39K): elite = deploy on-demand (182x), lead <1h (127x), CFR <5% (8x), MTTR <1h (2293x); solo 19% elite; low crece 17%→25%.
- **Platform engineering**: Gartner 80% orgs grandes con platform team en 2026 (vs 45% 2022); Team Topologies (4 tipos: stream-aligned, enabling, complicated-subsystem, platform); thinnest viable platform.
- **Shape Up** (Basecamp): bets de tiempo fijo/scope variable, betting table, cooldown, shaping sin BDUF.
- **RFC vs ADR** (Uber/Glovo): RFC = propuesta debatible pre-trabajo; ADR = decisión tomada; comment = trivial.
- **Trunk-based** (DORA elite): integrate-daily, ramas <1 día, flags, merge ≠ release.
- **Beyond-DORA**: review burden +91% con IA (frenar si supera throughput), AI-attribution, lifecycle depth.

## Decisión
1. **Agente `platform-engineer`** (23º): thinnest viable platform como producto interno, self-service, golden paths, DORA como SLO; Team Topologies: builder=stream-aligned, scientist/guardian=enabling, CUDA=subsystem, platform=self-service.
2. **`FeatureFlags`** (`SWARMIND_FF_*=1`, default off, snapshot frozen): merge ≠ release (dark ship); sin flags no hay trunk real.
3. **Spec como pitch**: `specs/task_template.md` con `appetite` + `boundaries` + `¿RFC previo?` + destino en cooldown; fan-out vota (gate ≥70%).
4. **Postmortem blameless** (`specs/postmortem_template.md`): 1 por SEV≥2; timeline + 5 whys + action items con dueño+fecha.
5. **Principios v3.2.0**: `DOR` (DORA como SLO con cifras), `OPS` += trunk-based, `SPE` += Shape Up + RFC-vs-ADR, `FAIL` += postmortem; taxonomía GOV += DOR.
6. **Limpieza de monolitos sombreados**: 7 archivos `.py` legados (eval_factory 536L, federated_search, lance_vector_store 672L, sqlite_vec_adapter 725L, vector_store_adapter 599L, adaptive_planner 708L, agent_bus 600L) eran **código muerto**: los paquetes homónimos ganan el import (verificado) y solo quedaban referencias en comentarios. Eliminados (~4500 líneas); 433+68 tests de dominio verdes. Resta 1: `agent_kpi_tracker.py` (713L, genuino, pendiente de split).

## Consecuencias
### Positivas
- Roles completos: plataforma con dueño (antes tierra de nadie entre devops y coordinator).
- Trunk real: ramas cortas + flags + green-trunk gate.
- Postmortems convierten SEVs en skills (cierra el loop FAIL→EVO).
- −4500 líneas muertas; deuda AGR real: 1 archivo (era 8).

### Negativas
- 23 agentes = +1 slot de retrieval (mitigado: tiers ADR-0053).
- RFC puede burocratizarse: la regla lo limita a >1 dependencia/riesgo o contrato público.

## Alternatives Considered
1. **platform-engineer como alias de devops**: responsabilidades distintas (producto vs operación); el alias existía y no bastaba.
2. **Scrum clásico**: ceremonias sin valor para agentes (sin dailies que atender); Shape Up encaja mejor.
3. **Postmortem solo en docs**: sin plantilla ejecutable no se hace; el template + FAIL lo exigen.
4. **Conservar los .py legados "por si acaso"**: el import los ignora siempre; conservarlos es riesgo de shadowing por filesystem, no seguridad.

## Relacionado
- ADR-0050 (semántica), FAIL/EVO, DORA 2024, Team Topologies, Shape Up
