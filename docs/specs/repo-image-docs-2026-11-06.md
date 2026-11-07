# SPEC — Repo image y documentación mantenible (2026-11-06)

> Estado: **implementado** (v1.0.0). Fuente:
> `docs/research/frontier-2026-11-06-repo-image.md`.

## 1. Contexto

El README (441 líneas) y los índices de docs habían derivado de la realidad:
decían 42 skills/25 agentes/~7000 tests cuando hay 49/26/7745; el índice
`SUMMARY.md` listaba 20 agentes y 34 skills a mano; `docs/` no tenía índice y no
existía gate de enlaces. Un visitante recibía una imagen inexacta y el
mantenedor pagaba deuda en cada alta.

## 2. Objetivo medible

| AC | Criterio | Verificación |
|---|---|---|
| RI-1 | README ≤ 260 líneas, con qué/por qué/para quién, quickstart, Mermaid, mapa de docs y límites | `test_docs_image.py::TestReadme` |
| RI-2 | README declara 49 skills, 26 agentes y ≥7.7k tests; no repite conteos obsoletos | `TestReadme::test_conteos_reales` |
| RI-3 | `docs/README.md` existe y mapea Diátaxis (tutorial/how-to/reference/explanation) | `TestDocsIndex` |
| RI-4 | `docs/src/es/{agents,skills}/INDEX.md` se generan desde `.opencode` y registry; `--check` detecta drift | `test_docs_index_sync` |
| RI-5 | `scripts/check_docs_links.py` falla con enlaces relativos rotos y resuelve rutas mdbook `/assets/...` | `TestLinks` |
| RI-6 | `SUMMARY.md` no enumera catálogos a mano; apunta a los índices generados | `TestSummary` |
| RI-7 | Gates verdes (ruff, vulture, arquitectura+ratchet, complejidad, ratchet, preview, pep649, skills) y suite completa | cierre del ciclo |

## 3. Diseño

- **README**: hero + badges + one-liner; “Why” (3 bullets); at-a-glance
  (26 agentes, 49 skills, 7.7k tests, Python 3.12+); quickstart; arquitectura
  Mermaid; mapa del repo; mapa de documentación (Diátaxis); evidencia/calidad;
  seguridad y límites; contribución/licencia.
- **docs/README.md**: hub con cuatro cuadrantes Diátaxis y enlaces a ES/EN,
  roadmap, specs, research, operación y referencia.
- **Índices generados** (`gen_docs_index.py`): leen frontmatter de agentes y
  registry de skills; escriben tablas ordenadas con conteos; `--check` compara
  y sale 1 si hay drift. Complejidad O(A+S).
- **Link checker** (`check_docs_links.py`): parsea enlaces Markdown, ignora
  http/mailto/anclas, resuelve relativos y rutas mdbook `/x` contra
  `docs/src/<lang>/x`; sale 1 si falta el destino. Complejidad O(L).
- **SUMMARY**: secciones + hubs; se eliminan listas manuales de 20/34.

## 4. Decisiones y trade-offs

- **No reescribir las 263 páginas** de docs: se arregla la fachada (README,
  hubs, índices) y se añade gate; el resto queda como deuda incremental.
- **Índices generados** en vez de listas manuales: +1 script, −2 fuentes de
  deriva; `--check` en tests evita el drift.
- **Link checker local** en vez de `lychee`/`markdown-link-check`: cero
  dependencias, mismo gate para enlaces internos; los externos se validan con
  `canon_audit`/herramientas existentes (no se duplica red en CI).

## 5. Gaps declarados

| Gap | Motivo | Siguiente paso |
|---|---|---|
| Enlaces externos no se validan en el gate | red/CI flaky; ya hay `canon_audit` | Job semanal con `lychee` |
| mdbook sigue compilando `docs/src/en` | el sitio publicado es EN; ES es primario en repo | Evaluar build dual ES/EN |
| `docs/es/*.html` legacy | artefactos antiguos | Limpiar cuando el sitio use `docs/book` |
| Social preview PNG | GitHub exige subida manual | Subir `docs/src/en/assets/social-preview.svg` convertido a PNG |
| Benchmarks tipo Harness-Bench | Requiere sandbox/evaluadores | Roadmap de evals |

## Ejemplo

```bash
python scripts/gen_docs_index.py --write   # regenera agentes/skills INDEX
python scripts/gen_docs_index.py --check   # falla si hay drift
python scripts/check_docs_links.py         # falla si un link interno no existe
pytest harness/tests/test_docs_image.py -q
```
