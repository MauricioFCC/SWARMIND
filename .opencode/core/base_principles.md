---
description: Principios universales v3.1.0 - N1+N2 siempre, N3 bajo demanda + taxonomia de adherencia (IFEval/DRFR) + RPA re-anclaje post-compaction + CPD fundamentos de competicion (ADR-0070) + TDD adversarial/mutante/PBT/pairwise/BVA/metamorphic/fuzz (ADR-0077)
inherit:
  - core/base_principles.md
  - core/fde_principles.md
name: base-principles
project_agnostic: true
version: 3.1.0
---

# PRINCIPIOS UNIVERSALES | Multi-nivel

Fuente unica de verdad para todos los skills, gates y agentes.
N1+N2 siempre inyectados; N3 bajo demanda (ver seccion final).

---

## NIVEL 1 -- ESENCIAL (7 lineas, ~65 tokens, siempre inyectado)

```md
RSF: Research First | investigar ANTES de ejecutar | vanguardia se renueva sola
IDP: Idempotencia | si ya esta implementado NO reimplementar | solo mejorar
ERR: Errores legibles y accionables | WHAT+WHY+WHERE | sin except silencioso
ARQ: hexagonal + DI | KISS <500 | DRY | type hints | pathlib
SEG: 0 secrets | validate input | mask logs | parametriza SQL | sys.path.insert(1)
DOC: docstrings ES OBLIGATORIAS | 0 funciones sin docstring | template Args/Returns/Raises
TST: core >=80% | TDD adversarial (test vs mutante) + mutantes + PBT + pairwise | coverage es piso no techo | pre-commit gates | 0 except silenciosos | logger.warning()
CMT: conventional commit type(scope): descripcion
FDE: bridge product↔reality | delta = gap to close | mission > persona
EVO: learn→design→experiment→analyze | cognition persists | loop repeats
POC: Proceso > herramienta | sin harness = departamento aislado | 5 preguntas antes de adoptar
TKN: Cache-Shape | Structured Compact | Failure-Spend | Observation Masking
WFP: Workflow Patterns | Evaluator-Optimizer | Voting | Critique-Revise | Parallel-Transform
PBT: Property-Based Testing Templates | holes rellenables | invariantes | -59% alucinaciones
CEN: Context Engineering | Least-Recent First | Progresivo | Chunking semantico
BTR: Behavioral Tracing | decisiones registradas | fingerprints | consistencia
AGR: Architectural Guardrails | layers | type hints | tamano | imports prohibidos
SVE: Semantic Versioning | MAJOR.MINOR.PATCH | changelog | skills y prompts
MCL: MetaClaw continual learning | skills evolucionan con RL | sin GPU local
MKS: Memento-Skills | cognition store como skill library | router contrastivo
UPG: Upgrade Continuo | siempre ultimas versiones estables | investigar antes | migrar si hay alternativa mas eficiente | mesa de trabajo para consenso
NAM: Naming Convention | snake_case archivos+vars+funcs | PascalCase clases | UPPER_SNAKE_CASE constants | booleans is_/has_/can_ | verbs en funciones | sin magic numbers | nombres comprensibles
TYP: Type Hints | type hints publicas | PEP 604 X|Y | generics TypeVar | type aliases | sin Any innecesario | mypy --strict
IMM: Immutability | frozen dataclasses | NamedTuple | tuple sobre list | MappingProxyType | copy sobre mutar
SOL: SOLID | SRP una responsabilidad | OCP abierto extension cerrado modificacion | LSP subtipos sustituibles | ISP interfaces segregadas | DIP depender de abstracciones
MAG: Magic Numbers | sin literales magicos | constantes con nombre semantico | tablas deLookup | enums para valores discretos
FSZ: Function Size | max 30 lineas | una responsabilidad | extraer helpers | guard clauses tempranas
CMP: Composition over Inheritance | preferir composicion sobre herencia | estrategia + interfaces | evitar jerarquias profundas | HAS-A sobre IS-A
DEM: Law of Demeter | solo hablar con amigos directos | no chains a.b.c.d | un punto por linea | tell dont ask
FRS: Frontier Research & Solution | SIEMPRE web research antes de resolver | elegir la solucion mas avanzada/frontera/eficiente/confiable | al finalizar: actualizar docs + commit
SPE: Spec-First (Proof-or-Stop) | spec ANTES de ejecutar | outcome medible | exit criteria definidos | sin spec = sin start
GATE: Evidence-Gated Lifecycle | claim→evidence→gate | 0 false-DONE | T1 deterministic + T2 LLM-judge + T3 regression
FAIL: Failure Registry | registrar fallos en JSONL | distillar en skills | Socratic-SWE traces→tasks | aprender de errores
SBX: Sandboxing | aislamiento de fallos | per-task environment | rollback plan | contenedor o timeout como minimo
RPA: Re-Pin After compaction | tras CADA compactacion recargar N1+rol+skills+agentes | 65% fallos = drift | bloque <<RE-ANCHOR>>
CPD: Fundamentos Competicion | checklist edges+invariants+BigO ANTES de codear | diagnose→repair→regenerate | dual verification
```

---

## TAXONOMIA DE ADHERENCIA (v3.1.0)

Cada codigo N1 pertenece a UNA categoria y un modo de cumplimiento. Los
CHECK son instrucciones verificables binarias (IFEval/DRFR: 1 regla = 1
criterio atomico); los GUIDE son orientativos (se citan por ID, nunca se
parafrasean — Ribeiro: el compliance es pattern matching fragil).

| Cat | Nombre | Codigos | Modo |
|-----|--------|---------|------|
| PRC | Proceso e investigacion | RSF, IDP, FRS, SPE, UPG, POC | CHECK |
| ARC | Arquitectura y codigo | ARQ, SOL, CMP, DEM, NAM, TYP, IMM, MAG, FSZ, AGR | CHECK |
| QLT | Calidad y testing | TST, PBT, GATE, CPD | CHECK |
| SEC | Seguridad y aislamiento | SEG, SBX | CHECK |
| DOC | Documentacion y commits | DOC, CMT, SVE | CHECK |
| CTX | Contexto y tokens | CEN, TKN | CHECK |
| GOV | Gobernanza y evidencia | ERR, FAIL, BTR, EVO, FDE | CHECK |
| SYS | Sistema y evolucion | WFP, MCL, MKS, RPA | GUIDE |

Reglas de uso (DRFR + SID + FollowBench):

1. **Una regla = un criterio atomico.** Si una linea tiene "X y Y", dividir.
2. **Citar por ID**: `CPD` o `ADR-0070:CPD`, nunca reescribir la regla.
3. **Densidad > detalle**: mas palabras por regla NO mejora adherencia
   (AAAI 2408.08781, 4 niveles probados).
4. **Self-restatement**: cada 10 respuestas restatear rol + 3 reglas mas
   criticas (IDs suficientes).
5. __Re-anclaje post-compaction (RPA)__: tras CADA compactacion recargar
   este N1 + agente activo + skills (bloque `<<RE-ANCHOR>>` via
   `harness/memory_rag/reanchor.py`). El summary retiene ~17% de las
   restricciones; el bloque las restaura (>90%).
6. **Jerarquia de conflicto**: formato > proceso > estilo (Wei: CoT verboso
   vs output conciso — resolver con orden explicito).

Fundamentos de competicion modernos (CPD, arXiv 2506.22954 + Wonda ICML 2026):

- **Checklist ANTES de codear**: edges + invariants + BigO + constraints I/O.
   El 44% de los fallos de LLMs en competicion es design (28.6%) + boundary
   (15.5%) — prevenibles con checklist.
- **Repair en 3 fases**: P1 diagnosticar contra taxonomia (design/boundary/
   condition/type/IO) → P2 reparar anclado a la categoria → P3 regenerar con
   info aumentada (5/80 → 46/80 AC con este framework).
- **Invariants con verificacion real**: citar invariante + comprobarla
   (Best-of-N filtering); invariante invalida se descarta, no se repara.
- **Dual verification**: solucion vs brute-force de referencia para
   confirmar complejidad sin OJ externo.

---

## NIVEL 2 -- ESTANDAR (17 lineas, ~150 tokens, inyectado si budget >70%)

| Cat | Reglas |
|-----|--------|
| __RSF__ | Research First: investigar estado del arte ANTES de ejecutar. Buscar papers/frameworks actuales. Elegir lo mas avanzado. Esto hace el sistema atemporal. |
| __IDP__ | Idempotencia: si la funcionalidad ya existe, NO reimplementar. Solo mejorar si hay delta demostrable. Verificar con `git log`, `cognition store`, ADRs existentes. Si ya esta implementado y funciona, pasar a la siguiente tarea. |
| __ARQ__ | Hexagonal ports/adapters + DI. __KISS__ (Keep It Simple): preferir la solucion obvia. __DRY__ (Don't Repeat Yourself): extraer logica repetida a utils. __YAGNI__ (You Aren't Gonna Need It): no anadir configuracion para futuros casos hipoteticos. Type hints publicas. Pathlib siempre. |
| __SEG__ | Secrets 0 hardcode: `os.getenv()`. Logs mask PII/data. Input sanitize. SQL parametrizada. No `eval()/exec()`. `sys.path.insert(1,)` nunca `insert(0,)`. Bandit + pip-audit en CI. |
| __DOC__ | Docstrings ES: Args/Returns/Raises (NumPy style). README/CHANGELOG ES. Codigo EN. Docs 1:1 en API/interfaz changes. `Griffe` para autodoc moderno (reemplaza legacy sphinx.ext.autodoc). Validar docs AI-generated con `pytest-examples` o doctest. |
| __TST__ | pytest framework. Core coverage >=80% (line+branch `--cov-branch`; 100% line con 60% branch = tests decorativos). New feature = new test + integration. Pre-commit gates. 0 `except Exception: pass` sin logger. __Adversarial TDD__ (AdverTest arXiv:2602.08146): loop test-vs-mutante co-evolutivo (M genera mutantes context-aware que hackean blind-spots de T; T los mata; +8.56% fault-detection, +63% vs EvoSuite); supervivientes = senal (no repetir mutantes en zonas ya cubiertas). __Mutation testing__ con `mutmut`/`cosmic-ray`: MS>=70% merge, objetivo >=85% nightly; suite manual dirigida donde mutmut da falsos negativos (imports de paquete). __Pairwise t=2__ (70-98% fallos son 1-2-way, NIST): covering array sobre variables discretizadas; subir a t=4-6 si hay supervivientes (fallos son <=6-way; 36626->1818, -95%). __BVA por variable__: min-1/min/min+1/max-1/max/max+1/0/""/None/NaN/overflow (~15% fallos boundary, 7x densidad). __Snapshot__ con `syrupy` para outputs grandes. |
| __OPS__ | Timeout >=30s I/O. Retry 3x exponential backoff + jitter. Circuit breaker. __OpenTelemetry__ para tracing distribuido (OTLP exporter). Log JSON estructurado con `trace_id`, `span_id`, `request_id` (structlog). Fallback plan. Health checks: liveness vs readiness. __Prometheus metrics__ para SLO. WAL obligatorio antes de tool-calls costosos. |
| __CMT__ | Conventional commit `type(scope): msg #ISSUE`. <=72 chars. Pre-commit hook: secrets+size+lint+test. __Conventional Comments__ para comentarios de PR. __Signed commits__ (GPG/SSH) en ramas main. |
| __QLT__ | __DEPRECATED v2.4.0__: cubierto por NAM, TYP, IMM, SOL, MAG, FSZ. Mantener solo como referencia historica. Codigo listo/sin hardcode. Conciso: 1 responsabilidad por funcion. Sin constantes magicas (siempre con nombre). |
| __ERR__ | Errores accionables: WHAT (que fallo) + WHY (causa) + WHERE (linea/archivo/funcion). Sin except silencioso. Logger siempre con contexto. Stack trace estructurado. __Sentry__ o similar para captura centralizada. __Error budgets__ (SRE). |
| __TKN__ | Cache-Shape Discipline (-38% tokens), Structured Compaction (-41% costo), Scoped Context (-44% tiempo), Failure-Spend Governance, Observation Masking, Phase-Scheduled MAS (-27.3% tokens). Effective-Input-Price = inp * miss_ratio * price + out * price. __2026__: usar modelos small para tareas simples (router por complejidad), cache de tool results, batching de invocaciones, prompt caching (Anthropic/OpenAI), speculative decoding para inferencia. |
| __WFP__ | 4 patrones de flujo reutilizables: Evaluator-Optimizer (genera→evalua→loop), Voting (N variantes→ranking→mejor), Critique-Revise (genera→critica→revisa), Parallel-Transform (fan-out→transforma→fan-in merge). Retry cost -51%. __2026__: añadir MapReduce para tareas grandes (dividir → paralelo → reducir). |
| __PBT__ | Property-Based Testing con templates de holes rellenables. 7 templates predefinidos (sorting, idempotent, pure, boundary, roundtrip, commutative, associative). Reduce alucinaciones -59%, costo -3.8x. __2026__: `hypothesis` 6.x con `@given` + `assume()`, profiles, health checks, deadlines. __Adversarial refinement__ (PROBE ACL'26): Validator genera contra-implementaciones que pasan la propiedad debil -> Generator la endurece (+9.79pp MS, 95% vs 65% correctness). __Metamorphic__ como PBT sin oraculo: MR reversibles (`reverse(reverse(x))==x`, `encode(decode(x))==x`, `f(x+k)==f(x)+k`). __Fuzzing dirigido__: parsers/fronteras (JSON/URLs/regex) con oraculo no-crash+roundtrip+timeout. |
| __CEN__ | Context Engineering: Least-Recent Context First (relevancia al inicio), Structured Chunking (metadatos por bloque), Progressive Disclosure (instruccion→ejemplos→datos). __2026__: usar `cache_control` breakpoints en prompts LLM, incluir timestamps en facts, versioning de system prompts. |
| __BTR__ | Behavioral Tracing: cada decision registra action+chosen+rationale+confidence. Fingerprint de comportamiento por agente. Reportes de consistencia y auditoria. __2026__: OpenTelemetry spans + GenAI semantic conventions (`gen_ai.*` attrs). Langfuse/LangSmith para observability de agentes. |
| __AGR__ | Architectural Guardrails: type hints obligatorios, max 60 lineas/funcion, prohibido except:pass, imports prohibidos (eval, exec, pickle). Validacion automatica post-generacion. __2026__: ruff reglas `A` (builtins shadowing), `C4` (comprehensions), `PIE` (misc), `RET` (returns), `SIM` (simplify), `TID` (tidy imports), `ARG` (unused args), `ERA` (commented-out code). Pre-commit enforcement. |
| __SVE__ | Semantic Versioning MAJOR.MINOR.PATCH para skills y agent prompts. CHANGELOG automatico. Trazabilidad de regresiones por scaffolding. __2026__: usar `release-please` o `commitizen` para automatizar versionado. Conventional commits + automerge en CI. |
| __FDE__ | Bridge product↔reality. Delta = gap a cerrar. Mission > persona. Glue 50% integracion. Speed-to-value primero. Diplomacia tecnica. Zero-trust. |
| __EVO__ | Loop learn→design→experiment→analyze. Cognition store persiste lecciones. Experiment DB registra todo. Best snapshot automatico. SURS >= 90% en cada deploy. |
| __POC__ | Proceso sobre herramienta: toda tool/modelo/agente nuevo se adopta como proceso orquestado (fan-out + votación gate≥70, memoria SSOT, oráculos PBT/mutation, KPIs) o se descarta. 5 preguntas: problema, responsable, datos, medición, escalado. Caso ORCA 2026. |
| __MCL__ | MetaClaw continual meta-learning: skill-driven fast adaptation + RL process reward optimization. Skills como behavioral instructions que evolucionan. MARS reflection single-cycle. |
| __MKS__ | Memento-Skills: skill-as-memory en cognition store. Router contrastivo recupera lecciones relevantes. ERL heuristics > raw trajectories para transferencia entre skills. |
| __UPG__ | __Upgrade Continuo (regla universal)__: TODO stack tecnologico debe estar en la ultima version estable viable. Investigar ANTES de actuar (web research exhaustiva + mesa de trabajo). Lenguajes, librerias, frameworks, runtimes, dependencias build, deps transitivas: TODAS. Si una version mas reciente es incompatible con el codigo actual, se documenta el delta y se migra. Si existe alternativa mas eficiente (mismo problema, menor costo/memoria/latencia), se evalua via mesa de trabajo y se migra. Excluye: paquetes en EOL (deprecation > 6 meses) sin LTS, alphas/betas/RCs inestable, versiones que rompen contratos publicos sin migracion posible. |
| __NAM__ | __Naming Convention (Clean Code)__: codigo en INGLES con semantic naming. Archivos Python: `snake_case.py` (modulos), `PascalCase/` (paquetes). Funciones y variables: `snake_case`. Clases: `PascalCase` (sustantivos, NO verbos). Constantes: `UPPER_SNAKE_CASE`. Booleanos: prefijo `is_`, `has_`, `can_`, `should_`. Funciones: verbo + accion (`get_`, `set_`, `compute_`, `validate_`, `parse_`, `is_`). Archivos de test: `test_<modulo>.py` refleja el archivo fuente. Sin magic numbers (usar constantes con nombre). Sin single letters (excepto `i`, `j`, `k` para loops, `e` para exceptions, `T` para TypeVar). Sin Hungarian notation. Sin abreviaciones no-standard. Si el nombre necesita comentario para entenderse, el nombre esta mal. |
| __TYP__ | __Type Hints (PEP 484/604)__: TODA interfaz publica debe tener type hints. Usar `X \| Y` (PEP 604, Python 3.10+) en lugar de `Union[X, Y]`. `list[int]`, `dict[str, Any]` no `List`, `Dict` (Python 3.9+). TypeVar para generics. `type X = ...` para type aliases. `NewType` para tipos distinctos. Evitar `Any` (usar `object` o generics). mypy --strict en CI. Type hints en dataclasses, NamedTuple, signatures. Return type `-> None` explicito si no retorna. |
| __IMM__ | __Inmutabilidad por defecto__: preferir estructuras inmutables para reducir bugs y habilitar reasoning concurrente. `frozen=True` en dataclasses. `NamedTuple` para records inmutables. `tuple` sobre `list` cuando no se muta. `MappingProxyType` para views de dicts. `frozenset` para sets inmutables. NO mutar parametros de entrada (copiar si es necesario). `dataclasses.replace()` para "mutar" inmutables. Inmutabilidad permite hashables, cache, reasoning funcional, y elimina bugs de aliasing. |
| __SOL__ | __SOLID Principles__: (1) __SRP__ Single Responsibility: cada clase/funcion hace UNA cosa. (2) __OCP__ Open-Closed: abierto a extension, cerrado a modificacion (usar protocolos, ABC, dependency injection). (3) __LSP__ Liskov Substitution: subtipos sustituibles por tipos base sin romper comportamiento. (4) __ISP__ Interface Segregation: interfaces pequenas y especificas (no "fat interfaces"). (5) __DIP__ Dependency Inversion: depender de abstracciones (Protocol, ABC), no de concreciones. Inyectar dependencias via __init__. |
| __MAG__ | __Magic Numbers / Constantes__: NUNCA literales magicos en codigo. Si un valor tiene significado de negocio, nombrarlo. `MAX_RETRIES = 3`, `DEFAULT_TIMEOUT = 30.0`, `RETRY_BACKOFF = 0.5`. Tablas de lookup (`COLOR_MAP = {...}`) en lugar de if-elif-else chains. `Enum` para valores discretos (`class Status(Enum): ACTIVE = "active"; DELETED = "deleted"`). Constantes a nivel de modulo (no dentro de funciones). Excepciones: 0, 1, -1, "" (literales obvios), numeros matematicos pi=3.14 (usar `math.pi`). |
| __FSZ__ | __Function Size__: funciones MAX 30 lineas (excluyendo docstring; Google style guide sugiere 40 como limite laxo, preferimos 30). Si excede: extraer helpers, aplicar guard clauses tempranas, dividir por responsabilidad. Una funcion = una tarea. Si el nombre necesita "and" o "or", dividir. Parametros: max 4-5 (si mas, usar un dataclass de input). Cyclomatic complexity < 10. Return temprano sobre if-else anidados. |
| __CMP__ | __Composition over Inheritance__ (GoF 1994): preferir COMPOSICION (HAS-A: "tiene un") sobre HERENCIA (IS-A: "es un"). Usar protocolos/ABC pequenos inyectados como componentes. Evitar jerarquias de herencia >2 niveles. Strategy pattern, State pattern, Decorator pattern son composicion. Herencia solo para tipos claramente relacionados (ej. Exception -> ValueError). Mixing composicion+herencia: subclase para especializar, composicion para variar comportamiento. |
| __DEM__ | __Law of Demeter__ (Principle of Least Knowledge, 1987): un objeto solo habla con sus "amigos directos" (sus propios metodos, sus atributos, los metodos de los objetos que recibe como parametro, los objetos que crea). NO chains: `customer.wallet.money.total()` (3 puntos = 2 violaciones). Max 1 punto por linea: `total = customer.total_money()` (delegar). Favorece Tell-Dont-Ask: en vez de pedirle datos a un objeto y decidir por el, pedirle que el mismo decida (command/query separation). Reduce acoplamiento y facilita testing. |
| __FRS__ | __Frontier Research & Solution (regla universal obligatoria)__: TODO requerimiento del usuario — sea cual sea — debe iniciar con __busqueda web exhaustiva__ para identificar la solucion MAS avanzada (frontera), de mejor calidad, mas eficiente y mas confiable disponible en el momento. NO resolver desde memoria o habitos: investigar primero. Criterios de eleccion: (1) frontier 2026 (papers, frameworks, tools), (2) calidad (adoptada, mantenida, documentada), (3) eficiencia (menor costo/memoria/latencia), (4) confiabilidad (estable, testada, comunidad). AL FINALIZAR toda tarea: __actualizar documentacion__ (README/CHANGELOG/ADRs si aplica) y __crear commit__ (conventional commit). |
| __SPE__ | __Spec-First (Proof-or-Stop, Huang 2026)__: TODO output de agente es un CLAIM, no estado. Lifecycle transitions solo avanzan cuando evidencia fresca satisface un gate predicate. Plantilla `specs/<task>.md` obligatoria ANTES de ejecutar: outcome medible, FR/NF, exit criteria, sandbox scope, rollback plan. Sin spec = sin start. Reduced false-DONE de 31/1800 a 2/1800 en ablation. |
| __GATE__ | __Evidence-Gated Lifecycle (Pondero CI-for-Agents 2026)__: 3-tier gates: __T1__ deterministic (<90s, blocks merge): schema validation, lint, test, security scan. __T2__ LLM-judge (<10min, blocks merge): behavioral spec, rubric scoring, majority voting repeat:3, judge temp=0. __T3__ regression (<60min, alert-only): nightly full suite, cross-model comparison. Spec y evals cambian juntos (SVE). Cost-arithmetic para judge models. |
| __FAIL__ | __Failure Registry (Socratic-SWE, Qu 2026)__: Cada fallo se registra en `harness/db/failures.jsonl` con: failure_type, error_msg, root_cause, resolution, skill_derived, severity. Evolve loop lee el registry → distilla en skills → genera tareas dirigidas que address capability gaps. Skills deduplicated por similaridad semántica. Solver-gradient alignment reward para task quality. +7.80 SWE-bench después de 3 iteraciones. |
| __SBX__ | __Sandboxing (Docker Sandboxes + Cloudflare Dynamic Workers 2026)__: Aislamiento de fallos: cada fan-out task puede correr en entorno aislado. Docker microVM para coding agents (Claude Code, Codex, OpenCode) con `--dangerously-skip-permissions`. Cloudflare V8 isolates: 100x más rápido que containers (ms startup, MB memory). Python-native: Pyodide/WASM para tool execution. Governance layer: network policies, filesystem controls. Rollback plan obligatorio antes de ejecutar. |

---

## NIVEL 3 (bajo demanda)

> N3 completo (referencia detallada) movido a `.opencode/core/base_principles_full.md`
> (Progressive Disclosure / Scoped Context: N1+N2 siempre, N3 solo cuando se necesita).
> Contiene: checklists ARQ, SEG, DOC, TST, OPS, ERR, CMT, QLT, FDE, EVO, UPG, TYP,
> IMM, SOL, MAG, FSZ, NAM, CMP, DEM, FRS + MAPA DE ROLES->CATEGORIAS + ABREVIACIONES.
> Cargar SOLO si el agente necesita detalles de implementacion, tabla de roles o abreviaciones.

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
   5. __Propagacion local__ (sync opencode + deploy_all) — NUNCA push automatico
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
- [ ] __Funciones complejas__: `from __future__ import annotations` para PEP 604 en Python <3.10
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

- [ ] **TOOLING - Scripts temporales y herramientas (ADR-0076)**:
   - Scripts temporales/one-off: **Python** (`uv run -- python -c "..."`) o **bash** (`.sh`) — NUNCA PowerShell: corrompe UTF-8 (mojibake en acentos ES `á→Ã¡`, emojis `🚀→?-*`), y su sintaxis de pipelines es no-portable.
   - Herramientas Linux-first: `rg` (ripgrep), `bash`, `awk`, `jq` — portables y deterministas; el texto ES/UTF-8 viaja intacto.
   - Si es inevitable leer/escribir texto con PowerShell: forzar `$OutputEncoding = [Console]::OutputEncoding = [Text.Encoding]::UTF8` y verificar el resultado (VER).
   - Wrappers de reduccion de output: `rtk` (Rust Token Killer, -60-90% output bash) y `tgrep` (Microsoft, trigram-indexed) cuando el binario este disponible (opt-in, passthrough si falta).

- [ ] __Funciones y metodos__: `snake_case` con verbo + accion:
   - `get_user_by_id()`, `set_cache_size()`, `compute_score()`, `validate_input()`
   - `is_empty()`, `has_children()`, `can_proceed()` (retornan bool)
   - `parse_query()`, `transform_result()`, `build_index()`
   - Prefijos utiles: `get_`, `set_`, `add_`, `remove_`, `update_`, `find_`, `parse_`, `format_`, `compute_`, `validate_`, `is_`, `has_`, `can_`, `should_`

- [ ] __Variables__: `snake_case` descriptivo:
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

- [ ] __Tests__: `test_<funcionalidad>_<escenario>_<esperado>`:
   - `test_validate_email_with_invalid_format_returns_false`
   - `test_user_creation_with_duplicate_id_raises_conflict`

- [ ] __Privado (Python)__: prefijo `_`:
   - `_internal_cache`, `_compute_helper()`
   - __NO `__dunder__`__ salvo metodos magicos reales (`__init__`, `__repr__`)

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

> Fuente unica: `.opencode/core/base_principles.md` (N1+N2) + `.opencode/core/base_principles_full.md` (N3 bajo demanda).
> FDE + EVO integrados: `.opencode/core/fde_principles.md` para FDE completo, `.opencode/core/evolve_loop.py` para el loop autonomo.
