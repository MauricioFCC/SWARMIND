---
name: base-principles-min
domain: core
description: "N1 esencial para sesiones con modelos locales 9B (ctx 16K): principios sin N2/N3. | UPG·NAM·FRS (reglas en base_principles.md)"
license: MIT
version: 3.3.0
project_agnostic: true
---

# PRINCIPIOS UNIVERSALES (min) — solo N1

Para sesiones locales con modelos 9B (ctx limitado): inyectar ESTE archivo
en vez de `base_principles.md` completo (38KB). N2/N3 quedan bajo demanda
via `base_principles.md` y `base_principles_full.md`. Modelos cloud/frontier
usan el archivo completo.

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
ADV: Verificacion adversarial SIEMPRE | atacante (halla gaps) → steelman (defiende+propone) → juez (veredicto+disenso) | T siempre ultimo movimiento | 1/5 "resuelto" es incorrecto: fortalecer antes de confiar
```
