# ADR-0037 — Reglas Universales de Código + Auto-Mejora Continua

- **Estado**: ACEPTADO
- **Fecha**: 2026-08-02
- **Decisores**: Coordinador Swiss Watch, Builder, Guardian, Evolve
- **Categoría**: Calidad / Gobernanza de Código

## Contexto

Los agentes de opencode (builder, scientist, guardian, evolve) escribían
código con convenciones inconsistentes: nombres de archivos/funciones difíciles
de comprender, versiones de librerías congeladas en el tiempo, type hints
ausentes, estructuras mutables cuando podían ser inmutables, jerarquías de
herencia profundas. La configuración YAML de `.opencode/config/` también se
desactualizaba (reflejaba 8 agentes/10 skills cuando el proyecto real tiene
20 agentes/31 skills).

No existía un mecanismo que:
1. Defina reglas universales obligatorias para TODO el código generado.
2. Valide automáticamente el cumplimiento (tests).
3. Actualice versiones de librerías automáticamente cuando hay mejores opciones.
4. Mantenga la configuración YAML sincronizada con la realidad del proyecto.

## Decisión

### 1. Reglas universales en `base_principles.md` (v2.4.0)

Se añadieron **10 reglas nuevas** a `.opencode/core/base_principles.md`
(fuente de verdad de los principios, inyectada en TODOS los agentes/skills):

| Regla | Nombre | Resumen |
|-------|--------|---------|
| **UPG** | Upgrade Continuo | Todo stack en última versión estable viable; investigar antes + mesa de trabajo |
| **NAM** | Naming Convention | snake_case archivos/vars/funcs, PascalCase clases, sin Hungarian, nombres comprensibles |
| **TYP** | Type Hints | PEP 604 (`X \| Y`), PEP 585 (`list[int]`), sin `Any` innecesario, mypy --strict |
| **IMM** | Immutability | frozen dataclasses, NamedTuple, tuple > list, MappingProxyType |
| **SOL** | SOLID | SRP, OCP, LSP, ISP, DIP (depender de abstracciones) |
| **MAG** | Magic Numbers | Sin literales mágicos; constantes con nombre semántico |
| **FSZ** | Function Size | Max 30 líneas (umbral gradual); guard clauses tempranas |
| **CMP** | Composition over Inheritance | Preferir HAS-A sobre IS-A; max 2 niveles de herencia |
| **DEM** | Law of Demeter | No chains `a.b.c.d`; Tell-Don't-Ask |
| **CFG** | Config Sync | Los YAML de config deben reflejar la realidad del proyecto |

Las 10 reglas se propagaron a las descripciones de los 20 agentes y 31 skills
(frontmatter YAML válido).

### 2. Tests de validación con auto-mejora

Se crearon 2 archivos de test con mecanismos de auto-mejora:

**`harness/tests/test_universal_rules.py`** (27 tests):
- Valida las 9 reglas de código (UPG, NAM, TYP, IMM, SOL, MAG, FSZ, CMP, DEM)
- CLI: `scan` (reporta violaciones), `evolve` (consulta PyPI, actualiza
  pyproject.toml + TARGET_VERSIONS + uv lock + verifica tests),
  `check-web` (compara con últimas versiones en PyPI)
- Estado persistente en `test_universal_rules_state.json`

**`harness/tests/test_opencode_config_sync.py`** (12 tests):
- Verifica que `.opencode/config/*.yaml` (project_config, routing_rules,
  token_budgets) reflejen la realidad (agent_count, skill_count, listas,
  agentes referenciados existen)
- CLI: `scan` (reporta drift), `evolve` (actualiza counts y listas a la realidad)
- Estado persistente en `test_opencode_config_sync_state.json`

### 3. Auto-actualización de versiones

El comando `evolve` de `test_universal_rules.py`:
1. Consulta PyPI JSON API para cada paquete en `TARGET_VERSIONS`.
2. Si hay versión más reciente, actualiza `pyproject.toml` y `TARGET_VERSIONS`.
3. Regenera `uv.lock`.
4. Re-ejecuta tests para verificar que siguen pasando.

TARGET_VERSIONS iniciales (auto-actualizadas 2026-08-02):
`python>=3.12`, `setuptools>=83.0.0`, `ruff>=0.16.1`, `mypy>=2.3.0`,
`hypothesis>=6.165.0`, `lancedb>=0.36.0`, `numpy>=2.5.1`, `torch>=2.13.0`,
`bandit>=1.9.4`, `safety>=3.8.1`.

### 4. Sincronía de config YAML

El comando `evolve` de `test_opencode_config_sync.py` reconstruye:
- `agent_count`, `skill_count`, `AGENTS.total`, `SKILLS.total`
- `AGENTS.agent_list`, `SKILLS.skill_list` completos (20 agentes, 31 skills)

## Consecuencias

### Positivas
- Código generado con convenciones consistentes y comprensibles.
- Versiones de librerías siempre actualizadas (auto-mejora).
- Config YAML siempre sincronizada con la realidad.
- Tests que se auto-actualizan y alertan sobre drift.

### Negativas
- Refactor progresivo necesario para reducir FSZ threshold (500→30).
- Los tests de validación deben mantenerse en CI.

### Riesgos y mitigaciones
- **Falsos positivos en regex**: mitigados con excepciones documentadas
  (acrónimos, module paths, tests/scripts).
- **Threshold FSZ 500**: el codebase tiene funciones legacy largas; el umbral
  se reduce gradualmente con cada refactor.
- **Auto-update rompe algo**: el `evolve` re-ejecuta tests; si fallan, no
  aplica (dry-run por defecto en CI).

## Alternativas consideradas

1. **Sin reglas explícitas** (solo depender del linter): rechazado — ruff
   no valida naming semántico, inmutabilidad ni config YAML sync.
2. **Solo documentación sin tests**: rechazado — no hay verificación
   automática, la desactualización vuelve.
3. **Actualización manual de versiones**: rechazado — el `evolve` con
   consulta PyPI es más fiable y no requiere recordar pasos.

## Verificación

```bash
# 1. Reglas universales + auto-mejora
uv run pytest harness/tests/test_universal_rules.py -q
# → 27 passed

# 2. Config YAML sync
uv run pytest harness/tests/test_opencode_config_sync.py -q
# → 12 passed

# 3. Auto-mejora de versiones
uv run python -m harness.tests.test_universal_rules evolve
# → "Sin updates necesarios (todo al dia)"

# 4. Config sync auto-mejora
uv run python -m harness.tests.test_opencode_config_sync evolve
# → "counts + lists actualizados (20 agentes, 31 skills)"

# 5. Scanner de seguridad
uv run python harness/qa/security_policy.py
# → 0 violaciones
```

## Referencias

- `.opencode/core/base_principles.md` (v2.4.0, 10 reglas nuevas)
- `harness/tests/test_universal_rules.py`
- `harness/tests/test_opencode_config_sync.py`
- ADR-0036 (Opción A: SSOT Global — base de la arquitectura)
- ADR-0033 (TDD-as-SSOT)
