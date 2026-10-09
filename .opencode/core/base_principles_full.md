---
name: base-principles-full
description: Principios universales - SOLO N3 (detalle bajo demanda) con checklists extendidos, mapa de roles y abreviaciones. N1/N2 viven UNA vez en core/base_principles.md (SSOT).
version: 3.5.0
project_agnostic: true
inherit:
  - core/base_principles.md
  - core/fde_principles.md
---

# PRINCIPIOS UNIVERSALES | Nivel 3 (FULL — detalle bajo demanda)

> Este archivo contiene SOLO N3 (detalle completo: checklists, ejemplos,
> mapa de roles y abreviaciones). Consultar SOLO cuando se necesiten
> detalles de implementacion, tabla de roles o abreviaciones.

N1 (esencial) y N2 (estandar) viven UNA sola vez en
`core/base_principles.md` (SSOT). Aqui solo N3 (checklists/ejemplos
detallados). En runtime se inyecta `.opencode/core/base_principles.md`
(N1+N2); las sesiones locales 9B (ctx 16K) inyectan
`core/base_principles.min.md` (solo N1).

> **Cobertura**: los codigos con checklist extendido en este archivo son
> `FND`, `ARQ`, `SEG`, `DOC`, `TST`, `OPS`, `ERR`, `CMT`, `QLT`, `FDE`,
> `EVO`, `UPG`, `TYP`, `IMM`, `SOL`, `MAG`, `FSZ`, `NAM`, `FRS` y los del
> `ADR-0098` (`CLA`, `VAL`, `FST`, `AAA`, `ATM`). El resto
> (`RSF`, `IDP`, `POC`, `TKN`, `WFP`, `PBT`, `CEN`, `BTR`, `AGR`, `SVE`,
> `MCL`, `MKS`, `CMP`, `DEM`, `DOR`, `SPE`, `GATE`, `FAIL`, `SBX`, `RPA`,
> `CPD`, `ADV`) tiene su detalle N2 en `base_principles.md` (SSOT), sin
> checklist N3 extendido: consultarlo alli para no duplicar.

---

## NIVEL 3 -- COMPLETO (referencia detallada para expandir)

### FND - Foundation-First (Fase F0: entorno antes que producto)

Aplica al INICIO de un proyecto nuevo (greenfield) o al adoptar un modulo
grande. El primer commit NO es una feature: es el entorno + spec + test RED.
Cita: `FND` o `ADR-XXXX:FND`.

- [ ] **Scaffolding reproducible**: repo desde template; `.editorconfig`,
      `.gitignore`, `LICENSE`, `README.md`, `SECURITY.md`, `CHANGELOG.md`;
      lockfile congelado; `.devcontainer.json` (o entorno hermetic).
- [ ] **Contrato para agentes**: `AGENTS.md` CORTO (~100 lineas = mapa, no
      manual) + `constitution.md`/principios machine-readable del proyecto.
- [ ] **Gates T1 locales primero**: formatter + linter + type-checker +
      pre-commit; **CI <90s** como green-trunk gate (Google; DORA elite).
- [ ] **Seguridad en el andamiaje**: secret scanning + push protection,
      SAST/code scanning, SBOM, dependabot, branch protection; en Rust
      `#![forbid(unsafe_code)]` + `deny.toml` + `cargo-geiger`; en Python
      `bandit` + `pip-audit`. (NIST SSDF 800-218/218A, SLSA, OpenSSF Scorecard.)
- [ ] **ADR-first**: ADR-0001 "registrar decisiones" + ADRs de las <=3
      decisiones irreversibles. (Nygard ADR; fitness functions Ford/Parsons/Kua.)
- [ ] **Fitness functions**: cada caracteristica arquitectonica clave tiene una
      funcion objetiva automatizable que la protege (no una intencion).
- [ ] **Thinnest Viable Platform / golden path**: camino feliz (crear, testear,
      desplegar) documentado en wiki/script; NO construir un portal.
      (Team Topologies; en 2026 el consumidor tambien es un agente.)
- [ ] **Walking Skeleton / Tracer Bullet**: slice vertical end-to-end con tests
      que SE CONSERVA (no prototipo). (Cockburn; Pragmatic Programmer.)
- [ ] **Spec machine-readable ANTES de features**: `specs/<feature>.md`
      (outcome, FR/NF, exit criteria, sandbox, rollback) + primer test en RED
      (SPE + GATE). Sin spec = sin start.
- [ ] **Identidad el dia 1 SOLO si vas a publicar**: org/dominio/registry
      (crates.io/PyPI/npm; PEP 752 prefix). Si es privado: ruido, no bloquea.
- [ ] **Verificar**: primer commit = scaffold+spec+test; CI T1 verde; 0 secrets;
      ADR-0001 presente.
- [ ] **Skills que aplican**: architect, devops, builder, guardian, product-manager.

### ARQ - Arquitectura
- [ ] Hexagonal: puertos (interfaces) en domain/ -> adapters en infrastructure/
- [ ] DI: inyectar dependencias en __init__, nunca instanciar dentro
- [ ] KISS: cada modulo <500 lineas, una responsabilidad
- [ ] DRY: logica repetida -> utils o base class
- [ ] Type hints en toda interfaz publica
- `X class Service: self.db = Database()` -> `OK class Service: def __init__(self, db: DBInterface)`

### SEG - Seguridad
- [ ] Secrets: `os.getenv("VAR")`, NUNCA literales. `.env` en `.gitignore`
- [ ] Logs: mask PII/secrets. `logger.info(mask(email))`, no raw
- [ ] Input: sanear todo input externo (Pydantic schema)
- [ ] SQL: siempre parametrizada, jamas f-strings
- [ ] No `eval()/exec()` en produccion
- `X f"SELECT * FROM t WHERE id={uid}"` -> `OK session.execute(text("..."), {"id": uid})`

### DOC - Documentacion (OBLIGATORIO — sin docstring = FAIL)
- [ ] **TODA funcion/clase/metodo publico DEBE tener docstring en ESPANOL UTF-8**
- [ ] Formato: Args/Returns/Raises (NumPy style o Google style)
- [ ] Codigo EN: variables, funciones, clases, types, archivos
- [ ] Comentarios inline ES
- [ ] README, CHANGELOG, manuales ES
- [ ] Docs 1:1: si cambia API/interfaz -> docs obligatorio
- `X def calcular_media(precios)` -> `OK def calculate_mean(prices)`
- `X """Calculate the moving average."""` -> `OK """Calcula el promedio movil."""`
- Template obligatorio:
  ```python
  def mi_funcion(param1: str, param2: int) -> bool:
      """Descripcion breve en espanol.
      
      Args:
          param1: Descripcion del primer parametro.
          param2: Descripcion del segundo parametro.
      
      Returns:
          Descripcion del valor de retorno.
      
      Raises:
          ValueError: Si param2 es negativo.
      """
  ```
- ⚠️ CERO funciones sin docstring. Si el agente genera codigo sin docstring, se rechaza en revision.

### TST - Testing
- [ ] pytest framework. New feature -> test unitario + integracion
- [ ] Cobertura: core >=80%, global >=30% incremental
- [ ] Gates pre-commit: tests -> lint -> typecheck -> coverage -> security
- [ ] Lint + typecheck en CI. Secrets scan en pre-commit hook
- [ ] Mocks/stubs para I/O externo, no llamadas reales

### OPS - Operaciones y Resiliencia
- [ ] Timeout: `requests.get(url, timeout=30)`, nunca sin timeout
- [ ] Retry: 3 intentos max, exponential backoff + jitter
- [ ] Circuit breaker: en llamadas a API externas, half-open recovery
- [ ] Logging: JSON estructurado con `trace_id`, nivel segun contexto
- [ ] Fallback: siempre tener plan B si servicio externo falla
- `X response = requests.get(url)` -> `OK response = requests.get(url, timeout=30)`

### ERR - Error Handling & Readability (OBLIGATORIO)
- [ ] **TODO `except` debe registrar causa**: `logger.warning("Fallo X: %s", e)` — jamas `except: pass`
- [ ] **Formato de error accionable**: Mensaje que incluya:
  - `WHAT` = Que operacion fallo (ej: "Fallo al conectar a BD")
  - `WHY` = Causa raiz (ej: "Timeout de conexion: 30s")
  - `WHERE` = Archivo:linea:funcion (incluir en log)
  - `HOW` = Como resolver (ej: "Verificar que el servicio BD este corriendo")
- [ ] **Stack trace estructurado**: Usar `logging.exception()` o formatear con `traceback.format_exc()` — nunca `print(e)`
- [ ] **Errores en ES** para usuarios finales, **tecnicos en EN** con contexto completo
- [ ] **Error classification**: Distinguir entre:
  - `VALIDATION`: input invalido → mensaje claro al usuario
  - `OPERATIONAL`: red/DB/timeout → retry + alert
  - `BUG`: assertion/codigo → stack trace completo
- [ ] **Nunca exponer internals** en errores al usuario (sanitizar antes de mostrar)
- `X except: pass` -> `OK except TimeoutError as e: logger.warning("Timeout en %s: %s", op, e); raise`
- `X print(e)` -> `OK logger.exception("Fallo al procesar %s", request_id)`
- `X raise Exception("error")` -> `OK raise ConnectionError("No se pudo conectar a %s: %s", host, reason)`

### CMT - Commits Seguros
- [ ] Formato: `type(scope): descripcion #ISSUE`
- [ ] Types: feat/fix/docs/refactor/perf/test/build/ci/chore/security
- [ ] Asunto <=72 chars. Issue # obligatorio
- [ ] Pre-commit hook: secrets scan + file size check + lint + test
- [ ] Sin `--no-verify` excepto emergencia documentada
- [ ] 0 secrets en historial. Si hay leak: rotar + bfg filter-branch

### QLT - Metricas de Calidad (DEPRECATED v2.4.0)
- [ ] **DELETED v2.4.0**: las metricas de calidad ahora viven en NAM, TYP, IMM, SOL, MAG, FSZ, CMP, DEM.
- [ ] Esta seccion queda como referencia historica unicamente.

### FDE - Forward Deployment Engineering
- [ ] DELTA: Identificar gap entre producto ideal y realidad del cliente
- [ ] MISSION: Stakeholder definido + metrica de exito + Day 2 plan
- [ ] GLUE: Contratos API primero, implementacion despues
- [ ] VALUE: MVA en <30 dias. 80/20 scope. Quick win identificado
- [ ] DIPLOMACY: Champion + Blocker identificados. Plan de adopcion
- [ ] RESILIENCE: Timeouts + retry + circuit breaker + zero-trust

### EVO - ASI-Evolve Loop
- [ ] LEARN: Cognition store consultado antes de disenar
- [ ] DESIGN: Hipotesis formulada con parent nodes como base
- [ ] EXPERIMENT: Evaluador ejecutado con metricas estructuradas
- [ ] ANALYZE: Resultado analizado y leccion distillada a cognition
- [ ] REGISTER: Experimento guardado en DB con score y analysis
- [ ] SNAPSHOT: Best snapshot actualizado si mejora

### UPG - Upgrade Continuo (regla universal para TODO stack)
- [ ] **Aplicar a TODO cambio de stack** (no solo upgrades completos):
  - [ ] Lenguajes: Python, Rust, TypeScript, Go, etc. — ultima estable
  - [ ] Librerias/frameworks: Django, FastAPI, React, numpy, torch — ultima estable
  - [ ] Runtimes: uv, npm, cargo, pip — ultima estable
  - [ ] Build deps: setuptools, hatchling, maturin — ultima estable
  - [ ] Deps transitivas (incluidas via lockfile) — todas en latest
- [ ] **Protocolo obligatorio antes de cambiar versiones**:
  1. **Investigacion web exhaustiva** (PyPI, GitHub releases, endoflife.date, blogs oficiales)
  2. **Mesa de trabajo** con la siguiente estructura minima:
     - Inventario actual vs. ultima estable (tabla con todas las deps)
     - Analisis de incompatibilidades (breaking changes, EOL, deprecation)
     - Alternativas mas eficientes evaluadas (e.g., `lancedb` vs `duckdb-vss`)
     - **Consenso**: voto unanime, mayoria cualificada, o decision justificada del coordinator
  3. **Implementacion incremental**: lockfile regenerado, tests, lint, scanner
  4. **Validacion**: suite de tests + bandit + scanner + cross-platform (Win/Linux)
  5. **Propagacion local** (sync opencode + deploy_all) — NUNCA push automatico
  6. **PR al usuario** con mesa de trabajo adjunta para revision y aprobacion
- [ ] **Criterios de exclusion** (no upgrade automatico):
  - Paquete en EOL con deprecation > 6 meses y sin LTS
  - Alpha/beta/RC inestable en produccion
  - Breaking change sin ruta de migracion posible (deferred a ADR)
  - Incompatibilidad con hardware/OS objetivo (e.g., Python 3.13 en Win7)
- [ ] **Metricas de exito**:
  - Cobertura de tests no disminuye
  - Latencia P95 no aumenta > 10%
  - 0 vulnerabilidades nuevas de severidad HIGH/CRITICAL
  - Lockfile sin duplicados (un solo version por paquete)
- [ ] **Frecuencia sugerida**: investigacion trimestral + upgrade inmediato cuando hay EOL < 6 meses
- [ ] **Skills que aplican esta regla por defecto**: builder, scientist, guardian, evolve

### TYP - Type Hints (PEP 484/604/585)
- [ ] **TODAS las funciones publicas** deben tener type hints en signature + return type
- [ ] **PEP 604** (`X \| Y`) preferido sobre `Union[X, Y]` (Python 3.10+)
- [ ] **PEP 585** (`list[int]`, `dict[str, Any]`) preferido sobre `List`, `Dict` (Python 3.9+)
- [ ] **TypeVar** para generics: `T = TypeVar("T")`
- [ ] **Type aliases** con `type X = ...` o `TypeAlias`
- [ ] **NewType** para tipos distinctos: `UserId = NewType("UserId", int)`
- [ ] **Evitar `Any`** — preferir `object`, generics, o `Unknown`
- [ ] **mypy --strict** en CI (zero errors policy)
- [ ] **Return type** explicito:
  - `-> None` si no retorna
  - `-> T` o `-> T \| None` segun contrato
- [ ] **Dataclasses y NamedTuple**: tipos explicitos en fields
- [ ] **Funciones complejas**: `from __future__ import annotations` para PEP 604 en Python <3.10
- [ ] **Protocols** para interfaces estructurales: `class Renderable(Protocol): def render(self) -> str: ...`
- [ ] **Generics**: `class Repository(Generic[T]): def get(self, id: str) -> T | None: ...`
- [ ] **Validacion en CI**:
  - `mypy harness/ --strict --ignore-missing-imports`
  - `pyright harness/` como segunda opinion
  - 0 disallow_untyped_defs, 0 disallow_incomplete_defs
- [ ] **Ejemplos**:
  - `X def get(id): return db.query(id)` -> `OK def get(self, id: str) -> User | None: return self._db.query(id)`
  - `X items = []` -> `OK items: list[Item] = []`
  - `X def calc(x, y): return x + y` -> `OK def add(self, x: float, y: float) -> float: return x + y`

### IMM - Inmutabilidad por defecto
- [ ] **`frozen=True` en TODAS las dataclasses** que no muten
- [ ] **`NamedTuple` para records inmutables** simples (3-5 campos, sin metodos)
- [ ] **`tuple` en lugar de `list`** cuando la coleccion no se muta
- [ ] **`frozenset` para sets inmutables**
- [ ] **`MappingProxyType`** para views read-only de dicts
- [ ] **NO mutar parametros de entrada** (copiar si se necesita modificar)
- [ ] **`dataclasses.replace()`** para "mutar" inmutables (crea nueva instancia)
- [ ] **Inmutabilidad permite**:
  - Hashable (usable en set/dict keys)
  - Cache (hash estable)
  - Reasoning funcional (sin side effects)
  - Thread-safety (sin locks)
  - Eliminacion de bugs de aliasing
- [ ] **Excepciones justificadas** (mutabilidad necesaria):
  - Buffers de I/O (numpy arrays, file handles)
  - Builders/fluent APIs
  - State machines (donde mutar es el proposito)
- [ ] **Ejemplos**:
  - `X @dataclass class User: name: str` -> `OK @dataclass(frozen=True) class User: name: str`
  - `X result = (); result += (1,)` -> `OK result: tuple[int, ...] = (1,)`
  - `X def update(d, k, v): d[k] = v` -> `OK def with_value(d, k, v) -> dict: return {**d, k: v}`

### SOL - SOLID Principles
- [ ] **SRP** (Single Responsibility): cada clase/funcion hace UNA sola cosa
  - `X class UserManager: def create(): ...; def send_email(): ...; def generate_report(): ...` (3 razones para cambiar)
  - `OK class UserManager: ...; class EmailService: ...; class ReportGenerator: ...`
- [ ] **OCP** (Open-Closed): abierto a extension, cerrado a modificacion
  - Usar Protocols/ABC para permitir nuevas implementaciones sin modificar el cliente
  - Strategy pattern, plugin architecture
  - `X if shape == "circle": ... elif shape == "square": ...` (modificar para cada nuevo shape)
  - `OK shapes: list[Shape] = [Circle(...), Square(...)]; for s in shapes: s.area()` (extender con nuevas clases)
- [ ] **LSP** (Liskov Substitution): subtipos deben ser sustituibles por tipos base
  - Pre-condiciones no mas fuertes, post-condiciones no mas debiles
  - Invariantes del tipo base deben mantenerse en subtipos
  - `X class Square(Rectangle): def set_width(self, w): self._width = self._height = w` (rompe LSP)
  - `OK class Square(Rectangle): usa composicion o jerarquia separada`
- [ ] **ISP** (Interface Segregation): interfaces pequenas y especificas
  - `X interface Worker: def work(); def eat(); def sleep()` (cliente solo usa work)
  - `OK interface Workable: def work(); interface Feedable: def eat(); interface Sleepable: def sleep()`
- [ ] **DIP** (Dependency Inversion): depender de abstracciones
  - Inyectar dependencias via `__init__` (no instanciar dentro)
  - Usar Protocol/ABC para tipos
  - `X class UserService: def __init__(self): self.db = PostgresDB()` (acoplado a concrecion)
  - `OK class UserService: def __init__(self, db: DatabaseInterface): self._db = db` (depende de abstraccion)

### MAG - Magic Numbers / Constantes
- [ ] **Cero literales magicos** en codigo de produccion
- [ ] **Constantes a nivel de modulo** (no dentro de funciones, salvo que sean realmente locales)
- [ ] **Tablas de lookup** en lugar de if-elif-else chains
  - `X if status == 1: ... elif status == 2: ... elif status == 3: ...`
  - `OK STATUS_HANDLER = {1: handle_active, 2: handle_pending, 3: handle_done}; STATUS_HANDLER[status]()`
- [ ] **`Enum` para valores discretos** (no usar int/str magicos)
  - `X if role == "admin"` -> `OK if role == Role.ADMIN`
- [ ] **Constantes con unidades en el nombre**:
  - `X TIMEOUT = 30` -> `OK TIMEOUT_SECONDS = 30`
  - `X SIZE = 1024` -> `OK SIZE_BYTES = 1024`
- [ ] **Constantes agrupadas** en un modulo dedicado (`constants.py`, `config.py`)
- [ ] **Excepciones validas** (literales OK sin nombrar):
  - `0`, `1`, `-1`, `""`, `[]`, `{}` (obvios en contexto)
  - `math.pi`, `math.e` (constantes matematicas ya nombradas)
  - Indices: `arr[0]`, `arr[-1]`
- [ ] **Validacion en CI**: ruff `RUF` con reglas de magic numbers (custom rule)
- [ ] **Ejemplos**:
  - `X if user.age >= 18:` -> `OK LEGAL_AGE = 18; if user.age >= LEGAL_AGE:`
  - `X time.sleep(0.5)` -> `OK RETRY_BACKOFF_SECONDS = 0.5; time.sleep(RETRY_BACKOFF_SECONDS)`
  - `X return x * 1024 * 1024` -> `OK BYTES_PER_MB = 1024 * 1024; return x * BYTES_PER_MB`

### FSZ - Function Size
- [ ] **MAX 30 lineas por funcion** (excluyendo docstring)
- [ ] **Una funcion = una responsabilidad** (single level of abstraction)
- [ ] **Guard clauses tempranas** (return antes que if-else anidados)
  - `X if user: if user.active: if user.has_perm: do_thing()` (3 niveles)
  - `OK if not user: return; if not user.active: return; if not user.has_perm: return; do_thing()` (3 lineas planas)
- [ ] **Extraer helpers** cuando la funcion crece:
  - Helpers privados (`_helper_*` con prefijo `_`)
  - Funciones puras (mismo input = mismo output)
- [ ] **Parametros**: max 4-5. Si mas, usar dataclass de input:
  - `X def create_user(name, email, age, role, team, manager)` (6 params)
  - `OK @dataclass class UserInput: name: str; email: str; ...; def create_user(inp: UserInput)`
- [ ] **Cyclomatic complexity < 10** (medible con `radon` o `mccabe`)
- [ ] **Return temprano** (early return) sobre else anidados
- [ ] **Si el nombre tiene "and" u "or"**: dividir
  - `X def validate_and_save(data)` -> `OK def validate(data); def save(data)`
- [ ] **Validacion automatica**:
  - ruff: max 30 lineas por funcion (configurable)
  - radon: cyclomatic complexity < 10
  - Code review: si >30 lineas, refactorizar antes de merge
- [ ] **Excepciones validas** (funciones largas permitidas):
  - Switch statements con muchos casos (usar lookup table en su lugar)
  - Funciones main con CLI parsing (aceptable)
  - Funciones con tablas de datos hardcoded (raro, preferir data files)
- [ ] **Ejemplo de refactorizacion**:
  - `X def process(data): if data.valid: result = compute(data); if result > 0: save(result); log(result); return result; return None` (8 lineas, 4 responsabilidades)
  - `OK def process(data: Data) -> Result | None: if not data.valid: return None; result = _compute(data); _save(result); _log(result); return result`

---

### NAM - Naming Convention (Clean Code)
- [ ] **Codigo en INGLES** (variables, funciones, clases) + **documentacion en ESPANOL** (docstrings, comentarios, README)
- [ ] **Archivos Python**:
  - Modulos/scripts: `snake_case.py` (`user_manager.py`, `vector_store_adapter.py`)
  - Paquetes (directorios): `PascalCase/` (`memory_rag/`, `orchestrator/`)
  - Tests: `test_<modulo>.py` refleja archivo fuente (`test_user_manager.py`)
  - Documentacion: `kebab-case.md` (`api-design.md`, `getting-started.md`)
  - Config/data: `kebab-case.yaml` o `snake_case.json`
- [ ] **Funciones y metodos**: `snake_case` con verbo + accion:
  - `get_user_by_id()`, `set_cache_size()`, `compute_score()`, `validate_input()`
  - `is_empty()`, `has_children()`, `can_proceed()` (retornan bool)
  - `parse_query()`, `transform_result()`, `build_index()`
  - Prefijos utiles: `get_`, `set_`, `add_`, `remove_`, `update_`, `find_`, `parse_`, `format_`, `compute_`, `validate_`, `is_`, `has_`, `can_`, `should_`
- [ ] **Variables**: `snake_case` descriptivo:
  - `user_count`, `max_retries`, `default_timeout`, `api_key` (no `n`, `cnt`, `t`, `k`)
  - Booleanos: prefijo `is_`, `has_`, `can_`, `should_` (`is_active`, `has_errors`, `can_retry`)
  - Constantes: `UPPER_SNAKE_CASE` (`MAX_RETRIES = 3`, `DEFAULT_TIMEOUT = 30.0`)
  - **NO magic numbers**: si un valor es literal, nombrar constante con significado
  - **NO single letters** (excepto `i`, `j`, `k` para indices de loop; `e`, `ex` para exceptions; `T` para TypeVar; `f` para file handle; `df` para DataFrame)
- [ ] **Clases**: `PascalCase`, **sustantivos** (NO verbos):
  - `UserManager`, `VectorStoreAdapter`, `HedgeFund` (no `DoHedgeFund`)
  - Dataclasses: `UserProfile`, `TaskSpec`, `KnowledgeRecord`
  - Exceptions: `ValueError`, `UserNotFoundError` (terminan en `Error`/`Exception`)
  - Mixins/abstract: `Serializable` (sin sufijo `Base` o `Abstract` salvo necesario)
  - **Interfaces** (ABC): prefijo `I` es opcional; preferir nombre descriptivo (`Cache` sobre `ICache`)
- [ ] **Modulos/paquetes**: cortos, lowercase, sin separadores:
  - `user.py` (no `user_manager_module.py`)
  - Evitar prefijo `mod_` o sufijo `_module`
  - Un solo concepto por modulo
- [ ] **Tests**: `test_<funcionalidad>_<escenario>_<esperado>`:
  - `test_validate_email_with_invalid_format_returns_false`
  - `test_user_creation_with_duplicate_id_raises_conflict`
- [ ] **Privado (Python)**: prefijo `_`:
  - `_internal_cache`, `_compute_helper()`
  - **NO `__dunder__`** salvo metodos magicos reales (`__init__`, `__repr__`)
- [ ] **Constantes vs variables**:
  - Si cambia runtime, es variable (`max_retries` configurable)
  - Si nunca cambia, es constante (`DEFAULT_PORT = 8080`)
  - Magic numbers SIEMPRE con nombre: `if timeout > DEFAULT_TIMEOUT:` (no `if timeout > 30:`)
- [ ] **NO usar**:
  - Hungarian notation: `str_name`, `i_count`, `b_is_active` (obsoleto desde 1990s)
  - Single letters excepto casos canonicos
  - Abreviaciones no-standard: `mgr` (usar `manager`), `tmp` (usar `temp` o nombre completo)
  - Prefijos redundantes: `class CUser` (redundante)
  - Nombres con numero: `data1`, `data2` (usar nombre semantico)
- [ ] **Refactorizacion** (cuando el nombre necesita comentario):
  - `X user_data = ...  # parsed user` -> `OK parsed_user = ...`
  - `X process(data, flag=False)` -> `OK process(data, validate_schema=True)`
  - `X calc(x, y, mode)` -> `OK compute_distance(x, y, metric="euclidean")`
- [ ] **Bilinguismo** (proyecto SWARMIND):
  - Identificadores de codigo: INGLES (`compute_score`, `user_count`)
  - Mensajes de error para developers: INGLES (`logger.error("Failed to load user")`)
  - Mensajes para usuario final / docs: ESPANOL (`"No se pudo cargar el usuario"`)
  - Comments inline: ESPANOL (`# Incrementar contador de reintentos`)
  - Docstrings: ESPANOL con secciones Args/Returns/Raises
- [ ] **Validacion automatica** (post-generacion):
  - ruff reglas `N` (pep8-naming) activadas en CI
  - Linter rechaza: single letters fuera de loops, magic numbers en tests, Hungarian notation
  - Code review: si el nombre del modulo/funcion necesita explicacion, se rechaza

---
- [ ] **Skills que aplican esta regla por defecto**: builder, scientist, guardian, evolve

---

## MAPA DE ROLES -> CATEGORIAS

| Rol | Categorias |
|-----|-----------|
| quant-developer | ARQ, SEG, TST, DOC, OPS, FDE, EVO |
| quant-scientist | ARQ, TST, DOC, EVO, FDE |
| risk-manager | ARQ, SEG, TST, OPS, FDE |
| software-engineer | ARQ, SEG, OPS, CMT, TST, FDE |
| frontend-engineer | ARQ, DOC, NAM, TYP, FDE |
| data-architect | ARQ, TST, SEG, NAM, FDE |
| devops-sre | OPS, CMT, SEG, FDE |
| security-engineer | SEG, CMT, DOC, ARQ, FDE |
| trading-operations | OPS, CMT, FDE, EVO |
| documentation-specialist | DOC, NAM, FDE |
| project-manager | CMT, FDE, EVO |
| mobile-engineer | ARQ, SEG, NAM, FDE |
| quality-gate | TST, CMT, SEG, DOC, NAM, FDE, EVO |
| enterprise-architect | ARQ, FDE, CMT, DOC |
| ai-engineer | ARQ, TST, EVO, FDE, OPS |
| evolve | EVO, FDE, CMT, UPG, NAM, TYP, IMM, SOL, MAG, FSZ, CMP, DEM, FRS |

---

## ABREVIACIONES (para compresion automatica de tokens)

| Completo | Abrev. |
|----------|--------|
| out-of-sample | OOS |
| walk-forward validation | WFV |
| deflated sharpe ratio | DSR |
| combinatorially symmetric cross-validation | CSCV |
| mixture of experts | MoE |
| stop loss | SL |
| take profit | TP |
| risk-reward ratio | RR |
| position sizing | pos_size |
| dependency injection | DI |
| infrastructure as code | IaC |
| continuous integration / continuous deployment | CI/CD |
| application programming interface | API |
| static application security testing | SAST |
| software composition analysis | SCA |
| pull request | PR |
| Forward Deployment Engineering | FDE |
| ASI-Evolve | EVO |
| Minimum Viable Architecture | MVA |
| Statement of Work | SOW |
| User Acceptance Testing | UAT |
| cognition store | COG |
| experiment database | EXDB |
| Agent-to-Agent | A2A |
| cognition | COG |
| evolve loop | EVLP |
| MetaClaw continual meta-learning | MCL |
| Memento-Skills skill-as-memory | MKS |
| Metacognitive Agent Reflective Self-improvement | MARS |
| Hyperagents DGM-H | HYP |
| Experiential Reflective Learning | ERL |
| Native Self-Evolution | NSE |
| ShapleyFlow workflow attribution | SHF |
| AdaptOrch topology-aware orchestration | AOR |
| Neural Finite-State Machine | NFSM |
| Multi-Principal Agent Coordination | MPAC |
| Symphony-Coord bandit routing | SYM |
| LLM-as-Scheduler | LAS |
| StructAgent state-centered framework | SAG |
| Bandit Optimization for Agent Design | BOAD |
| MuTON language-agnostic mutation testing | MUT |
| Upgrade Continuo (regla universal) | UPG |
| Mesa de Trabajo (consenso para upgrades) | MT |
| Naming Convention (Clean Code) | NAM |
| Type Hints (PEP 484/604) | TYP |
| Immutability (frozen dataclasses) | IMM |
| SOLID Principles | SOL |
| Magic Numbers / Constantes | MAG |
| Function Size (max 30 lineas) | FSZ |
| Composition over Inheritance | CMP |
| Law of Demeter (Tell, Don't Ask) | DEM |
| Frontier Research & Solution (regla universal) | FRS |

---

### FRS - Frontier Research & Solution (regla universal obligatoria)

> **SE CUMPLE SIEMPRE**: para CUALQUIER requerimiento del usuario, sin excepcion.

- [ ] **1. Web research ANTES de resolver**: todo requerimiento inicia con
      busqueda web exhaustiva (papers arXiv, frameworks, tools, repos, blogs).
      Buscar: "<problema> 2026 best solution", "<problema> state of the art",
      "<problema> frontier".
- [ ] **2. Criterios de eleccion** (elegir la solucion que mejor cumpla):
  - **Frontera**: la mas avanzada disponible (2026+), no soluciones obsoletas
  - **Calidad**: adoptada, mantenida, documentada, con comunidad
  - **Eficiencia**: menor costo computacional, memoria, latencia, tokens
  - **Confiabilidad**: estable, testada, con fallback y recovery
- [ ] **3. NO resolver desde memoria o habito**: si la tarea ya se hizo antes,
      aun asi verificar que la solucion usada sigue siendo la frontier
      (RSF + UPG aplicados: la vanguardia se renueva sola).
- [ ] **4. Documentar la decision**: brevemente anotar en el commit/PR la fuente
      investigada y por que se eligio esa solucion sobre las alternativas.
- [ ] **5. AL FINALIZAR toda tarea**:
  - [ ] **Actualizar documentacion**: README/CHANGELOG/ADRs si la tarea cambio
        comportamiento, API, dependencias o arquitectura.
  - [ ] **Crear commit**: conventional commit `type(scope): descripcion #ISSUE`.
- [ ] **Ejemplos de busquedas obligatorias**:
  - `X "implementa un cache"` → `OK buscar "cache python 2026 best practice" → elegir
    ShapedCache/LRU+TTL frontier → implementar → docs + commit`
  - `X "arregla este error"` → `OK buscar el error exacto + "2026 fix" → entender
    causa raiz → aplicar fix frontier → docs + commit`
  - `X "agrega una API"` → `OK buscar "fastapi vs litestar 2026" → elegir el mas
    eficiente/confiable → implementar → docs + commit`
- [ ] **Excepciones validas** (NO requieren web research):
  - Cambios triviales de formato/typo sin impacto (aun asi, commit).
  - Operaciones urgentes de rollback/revert (despues se investiga).
  - La tarea es SOLO actualizar documentacion (la investigacion ya se hizo).

### ADR-0098 - Convenciones de codigo

Reglas de codigo institucionales (ADR-0098). Citar por ID: `CLA`, `VAL`,
`FST`, `AAA`, `ATM`. No duplican `ERR`/`TST`/`SEG`/`CMT`/`IMM`: los
referencian.

- [ ] **CLA - Direccion de dependencias (Clean Architecture)**: el codigo fluye
      estrictamente `Presentation -> Application -> Domain <- Infrastructure`.
      El dominio es puro (0 imports de frameworks, DBs o librerias externas);
      la infraestructura implementa los ports definidos por el dominio via DIP.
      Complementa `ARQ` (hexagonal ports/adapters).
  - `X domain/entity.ts -> import { PrismaClient } from '@prisma/client'`
  - `OK domain define IUserRepository; infrastructure/db la implementa y se inyecta`

- [ ] **VAL - Validacion de input**: TODO dato que entra desde HTTP/CLI se
      valida contra un schema ANTES de tocar el dominio (Zod en TS / Pydantic
      en Python / Joi). Complementa `SEG` (validate input).
  - `X def create_user(payload: dict): ...` (payload sin validar)
  - `OK def create_user(payload: CreateUserSchema): ...` (Pydantic valida en el borde)

- [ ] **FST - Fail-Fast tipado con `cause`**: errores tipados con `cause` +
      contexto; nunca swallow ni mensajes genericos (ver `ERR`). Ejemplos:

  ```typescript
  // X ANTI-PATTERN: swallow + mensaje generico
  try { await repo.save(user); } catch (e) { console.log("error"); }

  // OK BEST PRACTICE: error tipado con cause
  try {
    await repo.save(user);
  } catch (error) {
    if (error instanceof DuplicateKeyError) {
      throw new BusinessLogicError(`User ${user.email} already exists`, { cause: error });
    }
    throw new InfrastructureError("Database failure", { cause: error });
  }
  ```

  ```python
  # OK BEST PRACTICE: raise ... from causa (FST)
  try:
      repo.save(user)
  except DuplicateKeyError as error:
      raise ConflictError(f"User {user.email} already exists") from error
  ```

- [ ] **IMM - Inmutabilidad**: ya cubierta por `IMM` (frozen dataclasses,
      `NamedTuple`, `tuple` sobre `list`, copia en vez de mutar). No se
      duplica aqui; ver la seccion `IMM - Inmutabilidad por defecto`.

- [ ] **AAA - Tests AAA**: Arrange-Act-Assert; 1 test = 1 criterio; mocks en
      unit tests (0 DB/red real). Complementa `TST`.

  ```typescript
  it("should_create_user_when_data_is_valid", async () => {
    // Arrange
    const mockRepo = new MockUserRepository();
    const useCase = new CreateUserUseCase(mockRepo);
    // Act
    const result = await useCase.execute({ name: "Alice", email: "alice@test.com" });
    // Assert
    expect(result.id).toBeDefined();
    expect(mockRepo.wasCalled()).toBe(true);
  });
  ```

- [ ] **ATM - Atomic Changes**: 1 commit/PR = 1 preocupacion logica.
      Complementa `CMT` (conventional commit).

---

> Fuente unica N1/N2: `.opencode/core/base_principles.md` (SSOT) -
> Skills, gates, hooks y optimizer referencian ese archivo.
> Este archivo (`base_principles_full.md`) aporta SOLO N3 (detalle bajo
> demanda): checklists extendidos, mapa de roles y abreviaciones.
> Para extender: agregar categoria en el N1/N2 de `base_principles.md` y su
> checklist N3 aqui + MAPA DE ROLES + ABREVIACIONES si aplica.
>
> FDE + EVO integrados: `.opencode/core/fde_principles.md` para FDE completo, `.opencode/core/evolve_loop.py` para el loop autonomo.
