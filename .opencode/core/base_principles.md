---
name: base-principles
description: Principios universales de programacion + ASI-Evolve + FDE - multi-nivel
version: 2.0.0
project_agnostic: true
inherit:
  - core/base_principles.md
  - core/fde_principles.md
---

# PRINCIPIOS UNIVERSALES | Multi-nivel

Fuente unica de verdad para todos los skills, gates y agentes.

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
```

---

## NIVEL 2 -- ESTANDAR (17 lineas, ~150 tokens, inyectado si budget >70%)

| Cat | Reglas |
|-----|--------|
| **RSF** | Research First: investigar estado del arte ANTES de ejecutar. Buscar papers/frameworks actuales. Elegir lo mas avanzado. Esto hace el sistema atemporal. |
| **IDP** | Idempotencia: si la funcionalidad ya existe, NO reimplementar. Solo mejorar si hay delta demostrable. Verificar con `git log`, `cognition store`, ADRs existentes. Si ya esta implementado y funciona, pasar a la siguiente tarea. |
| **ARQ** | Hexagonal ports/adapters + DI. KISS <500 lines/file. DRY utils. Type hints publicas. Pathlib siempre. |
| **SEG** | Secrets 0 hardcode: `os.getenv()`. Logs mask PII/data. Input sanitize. SQL parametrizada. No `eval()/exec()`. `sys.path.insert(1,)` nunca `insert(0,)`. |
| **DOC** | Docstrings ES: Args/Returns/Raises. README/CHANGELOG ES. Codigo EN. Docs 1:1 en API/interfaz changes. |
| **TST** | pytest framework. Core coverage >=80%. New feature = new test + integration. Pre-commit gates. 0 `except Exception: pass` sin logger. |
| **OPS** | Timeout >=30s I/O. Retry 3x backoff. Circuit breaker externo. Log JSON trace_id. Fallback plan. WAL obligatorio antes de tool-calls costosos. |
| **CMT** | Conventional commit `type(scope): msg #ISSUE`. <=72 chars. Pre-commit hook: secrets+size+lint+test. |
| **QLT** | Respuestas <500 tokens. Codigo listo/sin hardcode. Conciso: 1 responsabilidad por funcion. Sin constantes magicas (siempre con nombre). |
| **ERR** | Errores accionables: WHAT (que fallo) + WHY (causa) + WHERE (linea/archivo/funcion). Sin except silencioso. Logger siempre con contexto. Stack trace estructurado. |
| **TKN** | Cache-Shape Discipline (-38% tokens), Structured Compaction (-41% costo), Scoped Context (-44% tiempo), Failure-Spend Governance, Observation Masking, Phase-Scheduled MAS (-27.3% tokens). Effective-Input-Price = inp * miss_ratio * price + out * price. |
| **FDE** | Bridge product↔reality. Delta = gap a cerrar. Mission > persona. Glue 50% integracion. Speed-to-value primero. Diplomacia tecnica. Zero-trust. |
| **EVO** | Loop learn→design→experiment→analyze. Cognition store persiste lecciones. Experiment DB registra todo. Best snapshot automatico. SURS >= 90% en cada deploy. |

---

## NIVEL 3 -- COMPLETO (referencia detallada para expandir)

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

### QLT - Metricas de Calidad
- [ ] Respuesta agente <500 tokens (salvo codigo complejo)
- [ ] Codigo parametrizado, sin valores hardcodeados
- [ ] Concision: una responsabilidad por funcion/clase
- [ ] Documentacion: si hay logica compleja -> comentario explicativo
- [ ] Sin warnings de linter/typechecker sin justificar

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

---

## MAPA DE ROLES -> CATEGORIAS

| Rol | Categorias |
|-----|-----------|
| quant-developer | ARQ, SEG, TST, DOC, OPS, FDE, EVO |
| quant-scientist | ARQ, TST, DOC, EVO, FDE |
| risk-manager | ARQ, SEG, TST, OPS, FDE |
| software-engineer | ARQ, SEG, OPS, CMT, TST, FDE |
| frontend-engineer | ARQ, DOC, QLT, FDE |
| data-architect | ARQ, TST, SEG, FDE |
| devops-sre | OPS, CMT, SEG, FDE |
| security-engineer | SEG, CMT, DOC, ARQ, FDE |
| trading-operations | OPS, CMT, FDE, EVO |
| documentation-specialist | DOC, QLT, FDE |
| project-manager | CMT, QLT, FDE, EVO |
| mobile-engineer | ARQ, SEG, QLT, FDE |
| quality-gate | TST, CMT, SEG, DOC, QLT, FDE, EVO |
| enterprise-architect | ARQ, FDE, CMT, DOC |
| ai-engineer | ARQ, TST, EVO, FDE, OPS |
| evolve | EVO, FDE, CMT, QLT |

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

---

> Fuente unica: `.opencode/core/base_principles.md` - Skills, gates, hooks y optimizer referencian este archivo.
> Para extender: agregar categoria en los 3 niveles + MAPA DE ROLES + ABREVIACIONES si aplica.
>
> FDE + EVO integrados: `.opencode/core/fde_principles.md` para FDE completo, `.opencode/core/evolve_loop.py` para el loop autonomo.
