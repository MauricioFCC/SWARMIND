# Spec: Solapamiento semántico de skills (ronda evolutiva 2 — efectividad del routing)

- **Estado:** análisis + test GREEN (2026-10-12). Sin cambios en skills (solo lectura).
- **Principios:** `RSF`/`FRS` (investigar antes), `EDV` (evidencia medible), `GATE`/`VER` (gate determinista), `DRY`/`KISS`, `TST` (mutación).
- **Relación:** `.opencode/skills/skills_registry.yaml` (36 skills), `harness/tests/test_skill_overlap.py`,
  `harness/orchestrator/skill_bundler.py` (carga registry), `harness/context/skill_composition.py`
  (ADR-0075 `calls:`/`invocation:`), `harness/orchestrator/skill_collision_probe.py` (ADR-0090),
  `harness/common.py::fallback_embedding`.

## 1. Problema (WHY)

Si dos skills responden al mismo trigger (misma intención de usuario con
descriptions "Usar cuando" parecidas), el router no sabe cuál elegir y degrada
(`SkillRouter`, arXiv:2603.22455: el router debe leer el CUERPO para
desambiguar; la mejor solución es **no duplicar**: composición declarada). Ronda 2
mide este riesgo en las 36 skills y lo convierte en un **gate de CI** verificable.

## 2. Método (reproducible)

- **Trigger head:** se aísla el texto previo a `Alcance:` (el `Alcance:` declara
  anti-triggers "para X ver Y" y NO debe contar como solape de trigger).
- **Tokens clave:** `hidden_body.tokenize` + stopwords (funcionales ES + plantilla
  común del registry).
- **Score que decide:** Jaccard de tokens clave del trigger (KISS/word-overlap).
- **Coseno fallback:** `fallback_embedding` (frecuencia de caracteres) — **saturado
  (~0.84–0.99) y no discriminativo** porque todas las descriptions comparten
  plantilla; se conserva solo como diagnóstico. `assert min(cosines) >= 0.75`.
- **Recomendación:** `duplica` (Jaccard ≥ 0.6) | `conflicta` (ambas pushy y
  solape > 0.4) | `especializa` (subconjunto) | `ok` (tolerable).
- **Umbrales:** pico `0.8` (guardia dura), banda de atención `0.10` (knee real).

## 3. Resultado real (36 skills, 630 pares)

`max score = 0.176` (< 0.8 → sin zona de peligro). `PEAKS >= 0.8 sin acción = 0`.

| # | Par | Score | Tokens compartidos | Reco | Anti-trigger |
|---|---|---|---|---|---|
| 1 | psychology ~ sociology | 0.176 | agente, multi, sistemas | ok | sí (sociology→psychology) |
| 2 | alpha-research ~ data-science | 0.143 | engineering, feature, ml | ok | sí (data-science→alpha-research) |
| 3 | hedgefund ~ risk-execution | 0.118 | institucional, riesgo | ok | sí (mutuo) |
| 4 | **healthtech ~ sociology** | **0.111** | digital, sistemas | **ok** | **NO ← GAP** |
| 5 | alpha-research ~ quant-trading | 0.100 | alpha, backtesting | ok | sí (mutuo) |
| 6 | frontend-uiux ~ creative-design | 0.100 | design, ux | ok | sí (creative→frontend-uiux) |
| 7 | data-science ~ physical-sciences | 0.083 | analisis, datos | ok | sí (physical→data-science) |
| 8 | devops-infra ~ swarm-release-ops | 0.080 | cd, ci | ok | sí (mutuo) |
| 9 | atdd-spec ~ agent-rigor | 0.071 | tests, verificacion | ok | sí (atdd→agent-rigor) |
| 10 | evolve ~ skill-engineering | 0.071 | mejorar, skills | ok | sí (skill-engineering→evolve) |

**Hallazgo:** el autor del registry ya usa anti-triggers cruzados ("para X ver Y")
=> las colisiones reales están desambiguadas en la propia `description`.

## 4. Gaps (pares en banda de atención sin decisión)

- `healthtech ~ sociology` (0.111): comparten "sistemas/digital", ninguno cita al
  otro. **Requiere decisión de producto** → test `xfail(strict=True, no bloqueante)`.
  Opciones: (a) añadir a `healthtech` "para dinámicas sociales/digitales ver
  sociology" y a `sociology` "para sistemas de salud ver healthtech"; o (b)
  aceptar el solape (dominios distintos). **No se aplica en esta ronda.**

## 5. Propuesta de composición declarada (NO aplicada)

Alinear con ADR-0075 (`calls:`) y la convención de anti-trigger ya existente:

1. **Anti-trigger en `description`** (barato, cero código): para pares `conflicta`
   de banda alta, cerrar la `description` con "para <X> ver <skill-Y>". Es lo que
   ya hacen 9/10 de los top pares.
2. **Metadata en el registry** (explícita, machine-readable): agregar por skill
   ```yaml
   relation:
     conflicta: [healthtech]      # triggers cercanos → desambiguar
     especializa: [risk-execution] # soy el caso general de X
     depende: [base-principles]    # (ya cubierto por inherit:)
   ```
   Consumible por el router para `prune_conflicts` (skill_composition) y por el
   `skill_collision_probe` (shadow test con queries discriminantes).
3. **Regla de gate:** todo par con `score >= ATTENTION_BAND` debe tener
   anti-trigger cruzado **o** una `relation` declarada. Es el invariante del test.

## 6. Verificación (VER)

- `uv run python -m pytest harness/tests/test_skill_overlap.py -q` → **8 passed, 1 xfailed** (strict).
- `uv run ruff check harness/tests/test_skill_overlap.py` → **All checks passed**.
- Cobertura: (a) scorer ordenado sobre registry real; (b) guardia `>=0.8` sin
  acción = 0 + detección de duplicado sintético; (c) mutación: `threshold=0.0`
  invierte el gate y anular `_recommend_pair` (todo `ok`) deja el duplicado sin
  acción → el gate falla.

## 7. Fuentes frontier

| Técnica | Fuente |
|---|---|
| SkillRouter (leer el cuerpo para desambiguar) | arXiv:2603.22455 `[no verificado]` |
| SkillReducer (colisiones por wording vs scope) | arXiv:2603.29919 `[no verificado]` |
| Composición de skills (ADR-0075 interno) | `harness/context/skill_composition.py` |
| Shadow test anti-colisión (ADR-0090 interno) | `harness/orchestrator/skill_collision_probe.py` |
