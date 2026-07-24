# Commits Convencionales — AGENTIC Harness

> **Estandar:** Conventional Commits v1.0 · **Idioma:** Espanol · **Branch:** main (commits directos)

---

## 1. Formato

```
type(scope): descripcion en espanol

[Cuerpo opcional — explicar el QUE y el POR QUE]
```

- **type**: Obligatorio. Ver lista abajo.
- **scope**: Opcional. Ambito del cambio (tests, skills, docs, mcp, rag, evolve, deploy).
- **descripcion**: Imperativo, minusculas, < 72 chars, sin punto final.

## 2. Types Permitidos

| Type | Uso | Ejemplo real |
|------|-----|-------------|
| `feat` | Nueva funcionalidad | `feat: Knowledge Graph local-first (NetworkX+JSON, 16 tests)` |
| `fix` | Correccion de bug | `fix: routing_rules.yaml no se restaura con agentes obsoletos` |
| `docs` | Documentacion | `docs: ADR-0022 Frontier Optimization 2026 - investigacion + implementacion` |
| `refactor` | Cambio interno | `refactor: auditoria COD+TST+TKN con especialistas paralelos` |
| `test` | Tests | `feat(tests): +245 tests para archivos 0% (delegate, adaptive, fts, embedding)` |
| `chore` | Mantenimiento | `chore: commit final sesion - limpieza, docs, fixes menores` |
| `style` | Formateo | `style: ruff format aplicado a todo el codigo` |
| `config` | Configuracion | `config: actualizacion pyproject.toml con marcadores pytest` |

## 3. Ejemplos Reales

```text
feat: export_all_projects.py + push local completo (6 proyectos)
feat(tests): +245 tests para archivos 0%
feat(skills): 13 SKILL.min.md creados - cobertura 100% (29/29)
feat(legal-nlp): LegalAnalyzer con SaulLM/Arg-LLaDA + 13 tests
feat: Agent Capsules -51% tokens + ADR-0021 frontier gaps
fix: safety check on export for non-AGENTIC files
fix: dynamic cache threshold type-safe para tests con mock
docs(mdbook): configuracion actualizada con src=docs/src
docs(full): documentacion 1:1 de agentes y skills completa
chore: commit final sesion - limpieza, docs, fixes menores
```

## 4. Buenas Practicas

1. **Espanol siempre** — consistencia con el proyecto
2. **Imperativo presente** — "anade", "corrige", no "anadido"
3. **Un cambio por commit** — no mezclar feat + fix + docs
4. **Cuerpo explica el POR QUE**, no el COMO
5. **< 72 chars** en primera linea

## 5. Pre-commit Hooks (se ejecutan en cada commit)

```yaml
compile-check     # Errores de sintaxis Python
secret-scan       # Secretos hardcodeados
ruff-lint         # Linter rapido (E9, F)
trailing-whitespace / end-of-file-fixer / check-yaml / check-added-large-files
```

Si un hook falla: corregir y `git commit` de nuevo.

## 6. Flujo

```bash
git add <archivos>
pre-commit run --all-files     # Verificar hooks
pytest -m "not slow"           # Verificar tests
git commit -m "feat(scope): mensaje descriptivo"
git push origin main
```
