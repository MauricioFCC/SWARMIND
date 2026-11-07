# SPEC — Contratos SDD de skills (ADR-0048) + routing body-aware

> Estado: **implementado** (v1.0.0, 2026-11-01). Cierra el gap "1 de 44 skills
> con contrato" y añade detección de drift cuerpo↔contrato.

## 1. Contexto

`harness/context/skill_contract.py` define el contrato formal de un skill
(`SKILL.spec.json`: schemas de I/O, precondiciones, postcondiciones,
invariantes y `failing_test`), pero solo `atdd-spec` lo tenía. Consecuencias:

- El orquestador no podía rechazar invocaciones fuera de precondiciones.
- Editar `SKILL.md` no dejaba rastro: el contrato (si existía) podía quedar
  obsoleto en silencio.
- El routing solo veía `description`; SkillRouter (2026) mide 37–44 puntos de
  caída de accuracy en ese régimen.

## 2. Objetivo medible

| AC | Criterio | Verificación |
|---|---|---|
| AC-SC1 | 44/44 skills tienen `SKILL.spec.json` válido y no vacío | `test_skill_contracts::test_every_skill_has_spec` |
| AC-SC2 | `preconditions`, `postconditions` (≥2), `invariants` (≥1) y `failing_test` resolubles | `test_contract_has_no_errors` |
| AC-SC3 | `source_sha256` == sha256 del `SKILL.md` vigente (sin drift) | `test_spec_matches_skill_md_digest` + `validate_skills --strict` |
| AC-SC4 | Regenerar produce byte-a-byte el mismo spec (determinista) | `test_specs_are_reproducible` |
| AC-SC5 | `routing.body_keywords`: ≥5, minúsculas, sin duplicados | `test_routing_keywords_are_distinctive` |
| AC-SC6 | `failing_test` repo-relativo (`harness/tests/...::nodo`) se resuelve contra la raíz | `test_validate_contract_repo_relative_failing_test` |
| AC-SC7 | `validate_skills --strict` falla si un spec queda desactualizado | `test_skill_con_spec_desactualizado_error` |

## 3. Diseño

```
SKILL.md ──(parse)──► frontmatter + body
   │                     │
   │                     ├─ ## Checklist        → postconditions
   │                     ├─ ## Reglas/Constraints→ invariants
   │                     └─ tf-idf vs corpus    → routing.body_keywords
   └─ sha256 ───────────────────────────────────► source_sha256
                                   │
                                   ▼
                        SKILL.spec.json (ADR-0048)
                                   │
              load_skill_contract + validate_contract
                                   │
                    validate_skills --strict (drift gate)
```

**Complejidad**: generación `O(Σ tokens)` (una pasada por corpus + top-8);
validación `O(bytes)` por skill. Antes: 0 contratos verificables; después:
44 contratos + 44 gates de drift.

**Decisiones**:
- El spec se **deriva** del cuerpo (checklist/reglas) y no se inventa: si el
  cuerpo no tiene checklist (2 skills), se añadió uno real al `SKILL.md`.
- `failing_test` apunta a `harness/tests/test_skill_contracts.py` (caso
  parametrizado por skill); el resolver acepta rutas repo-relativas sin romper
  los specs skill-relativos existentes (`atdd-spec`).
- Los `body_keywords` **no** se consumen aún por el router en runtime: son
  señal preparada (ver gaps).
- Los contratos **manuales curados** (hoy `atdd-spec`, sin `provenance.generator`)
  se preservan: el generador no los sobrescribe.
- El digest de origen normaliza CRLF→LF, así el mismo `source_sha256` vale en
  checkout Windows y Linux.

## 4. Gaps declarados

| Gap | Motivo | Siguiente paso |
|---|---|---|
| El router no usa `routing.body_keywords` todavía | Cambiarlo sin benchmark de routing sería un cambio a ciegas | Medir Hit@k con queries reales antes de cablearlo |
| `contract.input/output` es un esquema común | Los skills no declaran tipos específicos; derivarlos requeriría anotaciones en el body | Añadir bloque `## Contrato` opcional en skills de alto valor |
| Sin métrica de routing end-to-end | No hay corpus de consultas etiquetadas en el repo | Construir 50–100 queries → gold skill y medir |
| `cert-master`/`alpha-mining` sin checklist original | Se añadió checklist derivada de su flujo real | Revisar semántica con el dueño del dominio |

## 5. Herramientas

```bash
python scripts/generate_skill_specs.py --write   # genera/actualiza 44 specs
python scripts/generate_skill_specs.py --check   # falla si hay drift
python scripts/validate_skills.py --strict       # gate global de skills
pytest harness/tests/test_skill_contracts.py -q  # contrato + reproducibilidad
```

## Ejemplo

Añadir un criterio al `## Checklist` de `agent-rigor` y ejecutar:

```bash
python scripts/generate_skill_specs.py --check
# DRIFT: 1 spec(s) desactualizados; usa --write  (exit 1)
python scripts/generate_skill_specs.py --write
python scripts/hash_skills_registry.py --write
python scripts/validate_skills.py --strict
# ✅ Todos los skills validos
```
