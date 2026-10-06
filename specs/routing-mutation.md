# Spec: Routing Mutation (Quality-Diversity + Novelty) — variantes sanas del coordinador

- **Estado:** propuesta + prototipo (2026-10-05)
- **Principios:** `EVO`, `MCL`, `MKS`, `POC`, `ADV`, `GATE`, `SBX`
- **Relación:** consume `harness/orchestrator/agent_selector.py`,
  `competence_model.py`, `capability_profiles.py`, `skill_bundler.py`,
  `harness/evolve_loop/gepa_mutator.py`

## 1. Problema (WHY)

El coordinador decide **skills y agentes** con una política fija (routing
estático + competencia). Frontera 2026: los sistemas multi-agente sufren
**Diversity Collapse** (ACL Findings 2026) y **Representational Collapse** —
votar agentes como si fueran independientes amplifica errores. Mutar el routing
para explorar vecinos puede descubrir variantes mejores y más creativas, **pero
sin control degrada calidad/seguridad** (Heuresis 2026: reward hacking, 40
fabricaciones; Self-MoA 2025: la diversidad no siempre ayuda).

**Hipótesis:** un archivo Quality-Diversity de genomas de routing, con bonus de
novedad y gate de seguridad, produce variantes **sanas, nuevas y creativas** sin
caer por debajo del baseline.

## 2. Genoma de routing (mutables)

```
RoutingGenome(
  skills: tuple[str, ...],   # skill por paso
  agents: tuple[str, ...],   # agente por paso
  temperature: float,        # creatividad
  persona: str,              # anclaje anti-hivemind
  topology: str,             # sequential | fanout | debate
  budget_tokens: int,
)
```
El **baseline actual** es el *champion*.

## 3. Descriptor de comportamiento (ejes del nicho)

2-4 ejes discretizados y estables (indexan las celdas del archivo):

| Eje | Buckets |
|---|---|
| coste_tokens | low / mid / high |
| profundidad_razonamiento | shallow / deep |
| familia_skill | dominio de la skill dominante |
| topologia | sequential / fanout / debate |

## 4. Archivo QD (MAP-Elites / CVT)

`archive: dict[nicho, ScoredGenome]` — conserva **la mejor variante por nicho**;
nunca colapsa a una única élite (Mouret & Clune 2015; CVT-MAP-Elites 2016).

## 5. Fitness y novedad

```
fitness = calidad(gates T1/T2) − λ·coste − μ·latencia + ν·novelty
novelty = distancia semántica media (Jaccard/embeddings) al resto del archivo
```
Novelty Search (Lehman & Stanley 2011): premiar la variante **distinta** aunque
no supere al champion hoy.

## 6. Mutación sana

- Mutar **1-2 genes** por generación (rate 0.1-0.3).
- Sustituir un skill/agente por su **vecino semántico** (similitud de
  descripciones / `capability_profiles`).
- Jitter de temperatura, reordenamiento, crossover de genomas vecinos.
- **Criterio "sana"** (analogía mutation testing): la variante debe (a) mejorar
  un caso, (b) cubrir un nicho nuevo, o (c) **exponer un fallo del baseline**.
  Variantes equivalentes (no aportan) se **descartan**; los supervivientes son
  señal de blind spot.

## 7. Seguridad y promoción

- **Gate pre-ejecución**: allowlist de skills/agentes/permisos; no tocar secretos
  ni acciones irreversibles; sandbox + timeout (`SBX`).
- **Gate de votación** ≥70 para promover (`ADV`/`WFP`).
- **Canary/shadow**: la variante corre primero en shadow, luego canary 5%→25%→100%
  con **rollback por etapa**; comparación estadística (KS) vs champion.
- **Circuit breaker** (3 fallos → causa-aware steering → half-open).

## 8. Anti-patrones (prohibidos)

- Mutar sin medir (novelty por novelty).
- Votar variantes como si fueran independientes cuando comparten el mismo modelo
  (Diversity Collapse).
- Promover una variante sin canary ni rollback.
- Mutar hacia acciones no reversibles o que tocan secretos.
- Ignorar el coste (explorar siempre lo más caro).

## 9. Fuentes frontier

| Técnica | Fuente |
|---|---|
| MAP-Elites / Illumination | https://arxiv.org/abs/1504.04909 |
| CVT-MAP-Elites | https://arxiv.org/abs/1610.05729 |
| Novelty Search | https://dl.acm.org/doi/abs/10.1162/evco_a_00025 |
| DIAYN "Diversity is All You Need" | https://arxiv.org/abs/1802.06070 |
| Mixture-of-Agents | https://arxiv.org/abs/2406.04692 |
| Self-MoA (diversidad no siempre ayuda) | https://arxiv.org/abs/2502.00674 |
| Self-Consistency | https://arxiv.org/abs/2203.11171 |
| Multiagent Debate | https://arxiv.org/abs/2305.14325 |
| Diversity Collapse en MAS | https://aclanthology.org/2026.findings-acl.13/ |
| Minority Sentinel (romper el consenso) | https://arxiv.org/abs/2606.29270 `[no verificado]` |
| Heuresis (reward hacking en QD) | https://arxiv.org/abs/2606.25198 `[no verificado]` |
| GEPA (evolución reflexiva de prompts) | https://arxiv.org/abs/2507.19457 |
| AdverTest (mutación tipo mutation-testing) | https://arxiv.org/abs/2602.08146 `[no verificado]` |

## 10. Verificación

- [ ] El archivo conserva ≥1 variante por nicho (no colapsa).
- [ ] Toda variante pasa el gate de seguridad (allowlist + reversible).
- [ ] La promoción exige votación ≥70 + canary + rollback.
- [ ] `novelty` y `fitness` se calculan y se registran por variante.
- [ ] Variantes equivalentes se descartan (no inflan el archivo).
- [ ] Test: una mutación insegura (acción irreversible/secret) es RECHAZADA.
- [ ] Test: una mutación que expone un fallo del baseline se archiva como señal.
