# AGENTS.md — Doctrina de trabajo para agentes en SWARMIND

> **Session-start hook** (patrón superpowers): este archivo se inyecta al inicio
> de cada sesión de agente para que la metodología esté siempre activa.

## ¿Qué es SWARMIND?

Harness Python de orquestación multi-agente (opencode, Claude Code, Codex)
con: orchestrator con fan-out paralelo + votación gobernada, model routing
small/frontier con fallback, memoria central portable (LanceDB + SQLite-vec),
token economics, validación PBT/mutation real, y aceleración GPU CUDA.

## Reglas universales (siempre activas)

```
RSF: Research First | investigar ANTES de ejecutar
IDP: Idempotencia | si ya esta implementado NO reimplementar
ERR: Errores legibles | WHAT+WHY+WHERE | sin except silencioso
ARQ: hexagonal + DI | KISS | DRY | type hints | pathlib
SEG: 0 secrets | validate input | mask logs | parametriza SQL
DOC: docstrings ES OBLIGATORIAS | 0 funciones sin docstring
TST: core >=80% | pre-commit gates | 0 except silenciosos
CMT: conventional commit type(scope): descripcion
TKN: Cache-Shape | Structured Compact | Failure-Spend
AGR: Guardrails | layers | type hints | tamano | imports prohibidos
UPG: Upgrade Continuo | ultimas versiones estables | investigar antes
FRS: Frontier Research | web research SIEMPRE antes de resolver
VER: Verificacion autonoma | SIEMPRE ejecuta el check y muestra evidencia
```

## Verificación autónoma obligatoria (VER)

Doctrina frontier 2026 (Anthropic, "Building Effective Agents"): **un agente
nunca afirma, verifica**. Al completar cualquier cambio:

1. **Da al agente un check que pueda ejecutar**: tests, build, lint, o exit
   code — no pedir "revísalo", pedir "ejecuta `pytest` y muéstrame el output".
2. **Exige evidencia, no afirmación**: cita el output real del check (pass
   rate, exit code, líneas de error) en la respuesta final.
3. **Itera hasta pasar**: si el check falla, corrige y re-ejecuta; no entregar
   con check rojo ni parchear el test para "pintar verde" (anti-patrón).
4. **Checks de skills**: tras editar `.opencode/skills/*`, ejecuta
   `python scripts/validate_skills.py --strict` y muestra el resultado.
5. **Checks de código**: tras tocar `harness/`, ejecuta los tests del módulo
   afectado (p. ej. `pytest harness/tests/test_<modulo>.py -q`) + ruff.

## Cómo trabajar aquí

1. **Investigar antes de ejecutar** (RSF/FRS): lee el código existente, revisa
   `git log`, verifica que no esté implementado (IDP).
2. **Skills**: los skills viven en `.opencode/skills/` (33 skills, formato spec
   Agent Skills de la Linux Foundation). Cada skill tiene `SKILL.md` +
   `SKILL.min.md` + frontmatter (name/domain/description/version/
   project_agnostic). Valida con `python scripts/validate_skills.py --strict`.
3. **ADRs**: las decisiones de arquitectura se documentan en
   `docs/src/es/adr/` (internos, NO se pushean al remoto).
4. **Docs oficiales**: README.md (inglés, público), docs/src/es/ (español,
   primario), CHANGELOG.md, docs/.MEJORAS_SWARMIND.md. Los ADR NO se mencionan
   en la documentación pública.
5. **Tests**: pytest en `harness/tests/` (4414 passing). TDD siempre-on.
   Ruff 0 errores, vulture 0 dead code, deuda AGR 0.
6. **Commits**: conventional commit en español (`feat(scope): mensaje`).
7. **Push**: los ADR (docs/src/es/adr/) se versionan localmente pero NO se
   pushean (`.githooks/pre-push` lo bloquea — permite solo borrados).

## Referencias rápidas

- Roadmap: `docs/src/es/roadmap/estado.md`
- Mejoras log: `docs/.MEJORAS_SWARMIND.md`
- Agentes: `.opencode/agents/` (22 agentes)
- Registry de skills: `.opencode/skills/skills_registry.yaml`
- Principios completos: `.opencode/core/base_principles.md`
