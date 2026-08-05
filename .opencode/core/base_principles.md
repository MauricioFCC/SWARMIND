---
name: base-principles
description: Principios universales de programacion + ASI-Evolve + FDE - N1+N2 siempre, N3 bajo demanda (H7 ADR-0040)
version: 2.6.0
project_agnostic: true
inherit:
  - core/base_principles.md
  - core/fde_principles.md
---

# PRINCIPIOS UNIVERSALES | Multi-nivel

Fuente unica de verdad para todos los skills, gates y agentes.
N1+N2 siempre inyectados; N3 bajo demanda (ver seccion final).

---

## NIVEL 1 -- ESENCIAL (7 lineas, ~65 tokens, siempre inyectado)

```
RSF: Research First | investigar ANTES de ejecutar | vanguardia se renueva sola
IDP: Idempotencia | si ya esta implementado NO reimplementar | solo mejorar
ERR: Errores legibles y accionables | WHAT+WHY+WHERE | sin except silencioso
ARQ: hexagonal + DI | KISS <500 | DRY | type hints | pathlib
SEG: 0 secrets | validate input | mask logs | parametriza SQL | sys.path.insert(1)
DOC: docstrings ES OBLIGATORIAS | 0 funciones sin docstring | template Args/Returns/Raises
TST: core >=80% | pre-commit gates | 0 except silenciosos | logger.warning()
CMT: conventional commit type(scope): descripcion
FDE: bridge product↔reality | delta = gap to close | mission > persona
EVO: learn→design→experiment→analyze | cognition persists | loop repeats
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
```

---

## NIVEL 2 -- ESTANDAR (17 lineas, ~150 tokens, inyectado si budget >70%)

| Cat | Reglas |
|-----|--------|
| **RSF** | Research First: investigar estado del arte ANTES de ejecutar. Buscar papers/frameworks actuales. Elegir lo mas avanzado. Esto hace el sistema atemporal. |
| **IDP** | Idempotencia: si la funcionalidad ya existe, NO reimplementar. Solo mejorar si hay delta demostrable. Verificar con `git log`, `cognition store`, ADRs existentes. Si ya esta implementado y funciona, pasar a la siguiente tarea. |
| **ARQ** | Hexagonal ports/adapters + DI. **KISS** (Keep It Simple): preferir la solucion obvia. **DRY** (Don't Repeat Yourself): extraer logica repetida a utils. **YAGNI** (You Aren't Gonna Need It): no anadir configuracion para futuros casos hipoteticos. Type hints publicas. Pathlib siempre. |
| **SEG** | Secrets 0 hardcode: `os.getenv()`. Logs mask PII/data. Input sanitize. SQL parametrizada. No `eval()/exec()`. `sys.path.insert(1,)` nunca `insert(0,)`. Bandit + pip-audit en CI. |
| **DOC** | Docstrings ES: Args/Returns/Raises (NumPy style). README/CHANGELOG ES. Codigo EN. Docs 1:1 en API/interfaz changes. `Griffe` para autodoc moderno (reemplaza legacy sphinx.ext.autodoc). Validar docs AI-generated con `pytest-examples` o doctest. |
| **TST** | pytest framework. Core coverage >=80%. New feature = new test + integration. Pre-commit gates. 0 `except Exception: pass` sin logger. **Mutation testing** con `mutmut` o `cosmic-ray` (>=70% mutation score). **Property-based** (ver PBT). **Snapshot** con `syrupy` para outputs grandes. |
| **OPS** | Timeout >=30s I/O. Retry 3x exponential backoff + jitter. Circuit breaker. **OpenTelemetry** para tracing distribuido (OTLP exporter). Log JSON estructurado con `trace_id`, `span_id`, `request_id` (structlog). Fallback plan. Health checks: liveness vs readiness. **Prometheus metrics** para SLO. WAL obligatorio antes de tool-calls costosos. |
| **CMT** | Conventional commit `type(scope): msg #ISSUE`. <=72 chars. Pre-commit hook: secrets+size+lint+test. **Conventional Comments** para comentarios de PR. **Signed commits** (GPG/SSH) en ramas main. |
| **QLT** | **DEPRECATED v2.4.0**: cubierto por NAM, TYP, IMM, SOL, MAG, FSZ. Mantener solo como referencia historica. Codigo listo/sin hardcode. Conciso: 1 responsabilidad por funcion. Sin constantes magicas (siempre con nombre). |
| **ERR** | Errores accionables: WHAT (que fallo) + WHY (causa) + WHERE (linea/archivo/funcion). Sin except silencioso. Logger siempre con contexto. Stack trace estructurado. **Sentry** o similar para captura centralizada. **Error budgets** (SRE). |
| **TKN** | Cache-Shape Discipline (-38% tokens), Structured Compaction (-41% costo), Scoped Context (-44% tiempo), Failure-Spend Governance, Observation Masking, Phase-Scheduled MAS (-27.3% tokens). Effective-Input-Price = inp * miss_ratio * price + out * price. **2026**: usar modelos small para tareas simples (router por complejidad), cache de tool results, batching de invocaciones, prompt caching (Anthropic/OpenAI), speculative decoding para inferencia. |
| **WFP** | 4 patrones de flujo reutilizables: Evaluator-Optimizer (genera→evalua→loop), Voting (N variantes→ranking→mejor), Critique-Revise (genera→critica→revisa), Parallel-Transform (fan-out→transforma→fan-in merge). Retry cost -51%. **2026**: añadir MapReduce para tareas grandes (dividir → paralelo → reducir). |
| **PBT** | Property-Based Testing con templates de holes rellenables. 7 templates predefinidos (sorting, idempotent, pure, boundary, roundtrip, commutative, associative). Reduce alucinaciones -59%, costo -3.8x. **2026**: `hypothesis` 6.x con `@given` + `assume()`, profiles, health checks, deadlines. |
| **CEN** | Context Engineering: Least-Recent Context First (relevancia al inicio), Structured Chunking (metadatos por bloque), Progressive Disclosure (instruccion→ejemplos→datos). **2026**: usar `cache_control` breakpoints en prompts LLM, incluir timestamps en facts, versioning de system prompts. |
| **BTR** | Behavioral Tracing: cada decision registra action+chosen+rationale+confidence. Fingerprint de comportamiento por agente. Reportes de consistencia y auditoria. **2026**: OpenTelemetry spans + GenAI semantic conventions (`gen_ai.*` attrs). Langfuse/LangSmith para observability de agentes. |
| **AGR** | Architectural Guardrails: type hints obligatorios, max 60 lineas/funcion, prohibido except:pass, imports prohibidos (eval, exec, pickle). Validacion automatica post-generacion. **2026**: ruff reglas `A` (builtins shadowing), `C4` (comprehensions), `PIE` (misc), `RET` (returns), `SIM` (simplify), `TID` (tidy imports), `ARG` (unused args), `ERA` (commented-out code). Pre-commit enforcement. |
| **SVE** | Semantic Versioning MAJOR.MINOR.PATCH para skills y agent prompts. CHANGELOG automatico. Trazabilidad de regresiones por scaffolding. **2026**: usar `release-please` o `commitizen` para automatizar versionado. Conventional commits + automerge en CI. |
| **FDE** | Bridge product↔reality. Delta = gap a cerrar. Mission > persona. Glue 50% integracion. Speed-to-value primero. Diplomacia tecnica. Zero-trust. |
| **EVO** | Loop learn→design→experiment→analyze. Cognition store persiste lecciones. Experiment DB registra todo. Best snapshot automatico. SURS >= 90% en cada deploy. |
| **MCL** | MetaClaw continual meta-learning: skill-driven fast adaptation + RL process reward optimization. Skills como behavioral instructions que evolucionan. MARS reflection single-cycle. |
| **MKS** | Memento-Skills: skill-as-memory en cognition store. Router contrastivo recupera lecciones relevantes. ERL heuristics > raw trajectories para transferencia entre skills. |
| **UPG** | **Upgrade Continuo (regla universal)**: TODO stack tecnologico debe estar en la ultima version estable viable. Investigar ANTES de actuar (web research exhaustiva + mesa de trabajo). Lenguajes, librerias, frameworks, runtimes, dependencias build, deps transitivas: TODAS. Si una version mas reciente es incompatible con el codigo actual, se documenta el delta y se migra. Si existe alternativa mas eficiente (mismo problema, menor costo/memoria/latencia), se evalua via mesa de trabajo y se migra. Excluye: paquetes en EOL (deprecation > 6 meses) sin LTS, alphas/betas/RCs inestable, versiones que rompen contratos publicos sin migracion posible. |
| **NAM** | **Naming Convention (Clean Code)**: codigo en INGLES con semantic naming. Archivos Python: `snake_case.py` (modulos), `PascalCase/` (paquetes). Funciones y variables: `snake_case`. Clases: `PascalCase` (sustantivos, NO verbos). Constantes: `UPPER_SNAKE_CASE`. Booleanos: prefijo `is_`, `has_`, `can_`, `should_`. Funciones: verbo + accion (`get_`, `set_`, `compute_`, `validate_`, `parse_`, `is_`). Archivos de test: `test_<modulo>.py` refleja el archivo fuente. Sin magic numbers (usar constantes con nombre). Sin single letters (excepto `i`, `j`, `k` para loops, `e` para exceptions, `T` para TypeVar). Sin Hungarian notation. Sin abreviaciones no-standard. Si el nombre necesita comentario para entenderse, el nombre esta mal. |
| **TYP** | **Type Hints (PEP 484/604)**: TODA interfaz publica debe tener type hints. Usar `X \| Y` (PEP 604, Python 3.10+) en lugar de `Union[X, Y]`. `list[int]`, `dict[str, Any]` no `List`, `Dict` (Python 3.9+). TypeVar para generics. `type X = ...` para type aliases. `NewType` para tipos distinctos. Evitar `Any` (usar `object` o generics). mypy --strict en CI. Type hints en dataclasses, NamedTuple, signatures. Return type `-> None` explicito si no retorna. |
| **IMM** | **Inmutabilidad por defecto**: preferir estructuras inmutables para reducir bugs y habilitar reasoning concurrente. `frozen=True` en dataclasses. `NamedTuple` para records inmutables. `tuple` sobre `list` cuando no se muta. `MappingProxyType` para views de dicts. `frozenset` para sets inmutables. NO mutar parametros de entrada (copiar si es necesario). `dataclasses.replace()` para "mutar" inmutables. Inmutabilidad permite hashables, cache, reasoning funcional, y elimina bugs de aliasing. |
| **SOL** | **SOLID Principles**: (1) **SRP** Single Responsibility: cada clase/funcion hace UNA cosa. (2) **OCP** Open-Closed: abierto a extension, cerrado a modificacion (usar protocolos, ABC, dependency injection). (3) **LSP** Liskov Substitution: subtipos sustituibles por tipos base sin romper comportamiento. (4) **ISP** Interface Segregation: interfaces pequenas y especificas (no "fat interfaces"). (5) **DIP** Dependency Inversion: depender de abstracciones (Protocol, ABC), no de concreciones. Inyectar dependencias via __init__. |
| **MAG** | **Magic Numbers / Constantes**: NUNCA literales magicos en codigo. Si un valor tiene significado de negocio, nombrarlo. `MAX_RETRIES = 3`, `DEFAULT_TIMEOUT = 30.0`, `RETRY_BACKOFF = 0.5`. Tablas de lookup (`COLOR_MAP = {...}`) en lugar de if-elif-else chains. `Enum` para valores discretos (`class Status(Enum): ACTIVE = "active"; DELETED = "deleted"`). Constantes a nivel de modulo (no dentro de funciones). Excepciones: 0, 1, -1, "" (literales obvios), numeros matematicos pi=3.14 (usar `math.pi`). |
| **FSZ** | **Function Size**: funciones MAX 30 lineas (excluyendo docstring; Google style guide sugiere 40 como limite laxo, preferimos 30). Si excede: extraer helpers, aplicar guard clauses tempranas, dividir por responsabilidad. Una funcion = una tarea. Si el nombre necesita "and" o "or", dividir. Parametros: max 4-5 (si mas, usar un dataclass de input). Cyclomatic complexity < 10. Return temprano sobre if-else anidados. |
| **CMP** | **Composition over Inheritance** (GoF 1994): preferir COMPOSICION (HAS-A: "tiene un") sobre HERENCIA (IS-A: "es un"). Usar protocolos/ABC pequenos inyectados como componentes. Evitar jerarquias de herencia >2 niveles. Strategy pattern, State pattern, Decorator pattern son composicion. Herencia solo para tipos claramente relacionados (ej. Exception -> ValueError). Mixing composicion+herencia: subclase para especializar, composicion para variar comportamiento. |
| **DEM** | **Law of Demeter** (Principle of Least Knowledge, 1987): un objeto solo habla con sus "amigos directos" (sus propios metodos, sus atributos, los metodos de los objetos que recibe como parametro, los objetos que crea). NO chains: `customer.wallet.money.total()` (3 puntos = 2 violaciones). Max 1 punto por linea: `total = customer.total_money()` (delegar). Favorece Tell-Dont-Ask: en vez de pedirle datos a un objeto y decidir por el, pedirle que el mismo decida (command/query separation). Reduce acoplamiento y facilita testing. |
| **FRS** | **Frontier Research & Solution (regla universal obligatoria)**: TODO requerimiento del usuario — sea cual sea — debe iniciar con **busqueda web exhaustiva** para identificar la solucion MAS avanzada (frontera), de mejor calidad, mas eficiente y mas confiable disponible en el momento. NO resolver desde memoria o habitos: investigar primero. Criterios de eleccion: (1) frontier 2026 (papers, frameworks, tools), (2) calidad (adoptada, mantenida, documentada), (3) eficiencia (menor costo/memoria/latencia), (4) confiabilidad (estable, testada, comunidad). AL FINALIZAR toda tarea: **actualizar documentacion** (README/CHANGELOG/ADRs si aplica) y **crear commit** (conventional commit). |

---

## NIVEL 3 (bajo demanda)

> N3 completo (referencia detallada) movido a `.opencode/core/base_principles_full.md`
> (Progressive Disclosure / Scoped Context: N1+N2 siempre, N3 solo cuando se necesita).
> Contiene: checklists ARQ, SEG, DOC, TST, OPS, ERR, CMT, QLT, FDE, EVO, UPG, TYP,
> IMM, SOL, MAG, FSZ, NAM, CMP, DEM, FRS + MAPA DE ROLES->CATEGORIAS + ABREVIACIONES.
> Cargar SOLO si el agente necesita detalles de implementacion, tabla de roles o abreviaciones.

---

> Fuente unica: `.opencode/core/base_principles.md` (N1+N2) + `.opencode/core/base_principles_full.md` (N3 bajo demanda).
> FDE + EVO integrados: `.opencode/core/fde_principles.md` para FDE completo, `.opencode/core/evolve_loop.py` para el loop autonomo.
