# SPEC — Ciclo Frontera (frontier engineering)

> Estado: **implementado** (v1.0.0, 2026-11-01). Superficie operativa del
> meta-prompt de ciclo (Qwen XML 2026-11-01) traducido a activos del harness.

## 1. Contexto y problema

Los avances en Swarmind, RuscaDB, Micellium y CQE llegaron cuando el usuario
escribía **explícitamente** el ciclo completo:

> "Carga skills, agentes, **<tarea explícita>**. Investigación web frontera,
> papers/artículos/técnicas, arquitecturas óptimas, algoritmos, complejidad
> O(n²)→O(n), fórmulas, spec (mejorar/reimplementar si aplica), SDD, TDD
> adversarial mutante, actualiza Docs."

Ese meta-prompt vivía solo en la cabeza del usuario: había que reescribirlo en
cada sesión y el agente podía saltarse fases (research, oráculo, docs).

## 2. Objetivo (outcome medible)

Que cualquier petición explícita de frontera dispare el ciclo completo con
gates, sin reescribir el meta-prompt:

- **AC-FC1** — Existe la skill `frontier-engineering` (`SKILL.md` +
  `SKILL.min.md`) registrada en `skills_registry.yaml` con digest, y validada
  por `validate_skills.py --strict`.
- **AC-FC2** — Existe el comando `/frontera <tarea>` en `.opencode/commands/`
  que referencia la skill y enumera las 6 fases.
- **AC-FC3** — `AGENTS.md` (hook de sesión) contiene la sección "Ciclo
  Frontera" con la plantilla canónica, fases y cierre obligatorio, y la lista
  de skills declara 44.
- **AC-FC4** — `project_config.yaml` declara `SKILLS.total` y `skill_list`
  coherentes con los directorios reales (contrato `test_opencode_config_sync`).
- **AC-FC5** — Un test de contrato falla si cualquiera de las tres superficies
  (skill, comando, sección AGENTS) desaparece o pierde una fase.
- **AC-FC6** — El cierre exige evidencia real de gates y `publish.py`; la spec
  declara explícitamente qué exigencias del meta-prompt **no** se cumplen hoy.

## 3. Diseño (dónde se inserta y por qué)

| Superficie | Archivo | Por qué |
|---|---|---|
| Procedimiento | `.opencode/skills/frontier-engineering/SKILL.md` + `SKILL.min.md` | Reusable por cualquier agente; pasa `validate_skills` (M5/M6, digest) |
| Disparador | `.opencode/commands/frontera.md` | Atajo de una línea; sin pin de agente (la tarea decide el especialista) |
| Hook de sesión | `AGENTS.md` § "Ciclo Frontera" | Se inyecta al inicio de **cada** sesión (uso constante real) |
| Contrato | `harness/tests/test_frontier_cycle_contract.py` | Convierte la doctrina en gate ejecutable (VER) |

**No** se usa `base_principles.md` (se inyecta en todas las sesiones y pesa
demasiado para un ciclo por tarea) ni se crea un agente dedicado (exigiría
registrar flota en `coordinator_policy.yaml`, `opencode.json` y el contrato de
subagentes sin aportar a "uso constante").

## 4. Fases (contrato de ejecución)

1. **Load** — manifest de skills/agentes/specs/memoria; IDP.
2. **Research SOTA** — `docs/research/frontier-<fecha>-<tema>.md`; URLs leídas o
   `[UNVERIFIED]`; ≥3 hipótesis con criterios y gap analysis.
3. **Design** — arquitectura + trade-offs + fórmulas y `O(·)` antes→después.
4. **Spec/SDD** — spec nueva o diff con rationale (`Δquality > 0 ∧ Δcost < 0`).
5. **TDD adversarial mutante** — oráculo congelado, rojo→verde, PBT, mutantes;
   `O(n²)→O(n)` medido con gate N/2N/4N + equivalencia.
6. **Docs** — CHANGELOG + roadmap + MEJORAS + ADR; commit convencional y
   `python scripts/publish.py` (push + sync + verify).

## 5. Gaps declarados (honestidad de alcance)

| Exigencia del meta-prompt | Estado real en SWARMIND | Decisión |
|---|---|---|
| Coverage ≥95 % líneas / 90 % ramas | `fail_under = 62` (ratchet hacia 70/80) | Se reporta el valor real; no se finge el umbral |
| Mutantes ≥90 % | CI T2 70 %, nightly kernel 90 % | Umbral por paquete, no global |
| Spec formal TLA+/Alloy | Sin toolchain; contratos TOML (F8) + `cp_spec_gate` | No se promete TLA+ |
| Tree-of-Thought ≥3 hipótesis | No automatizado; lo cubre el research brief | Se exige en la fase 2 (documento), no como motor |
| STRIDE por defecto | `harness/security/` + agente security-engineer | Sin gate automático |
| `manifest.json` de activos | No existe productor automático | El manifest se lista en la respuesta |

## 6. Verificación

```bash
python scripts/validate_skills.py --strict
pytest harness/tests/test_frontier_cycle_contract.py -q
pytest harness/tests/test_opencode_config_sync.py -q
```

## Ejemplo

Petición real (ciclo 11.68): "Carga skills, agentes, **mejora la correlación
rolling del DSL de alpha** …". Resultado: research en
`docs/research/frontier-2026-11-01-ruscadb.md`, `_ts_corr` O(n·W)→O(n), 11
tests contra oráculo independiente, benchmark `alpha.ts_corr` ratio 1.94,
CHANGELOG 11.68 y `publish.py` OK.
