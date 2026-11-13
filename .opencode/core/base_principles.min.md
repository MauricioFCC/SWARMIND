---
name: base-principles-min
domain: core
description: "N1 esencial para sesiones con modelos locales 9B (ctx 16K): principios sin N2/N3. | UPGÂ·NAMÂ·FRS (reglas en base_principles.md)"
license: MIT
version: 4.0.0
project_agnostic: true
---

# PRINCIPIOS UNIVERSALES (min) â€” solo N1

Para sesiones locales con modelos 9B (ctx limitado): inyectar ESTE archivo
en vez de `base_principles.md` completo. N2/N3 quedan bajo demanda
via `base_principles.md` y `base_principles_full.md`. Modelos cloud/frontier
usan el archivo completo.

```md
RSF: Research First | estado del arte ANTES de ejecutar | no resolver de memoria
IDP: Idempotencia | si ya existe NO reimplementar | solo mejorar con delta demostrable
ERR: Errores legibles | WHAT+WHY+WHERE | sin except silencioso
ARQ: hexagonal + DI | KISS + DRY + YAGNI | type hints | pathlib
SEG: 0 secrets | mask logs | SQL parametrizada | sin eval/exec
DOC: docstrings ES (Args/Returns/Raises) | 0 funciones sin docstring | docs 1:1 en API
TST: core >=80% | TDD adversarial + mutantes + PBT + pairwise | coverage es piso | 0 except silenciosos
CMT: conventional commit type(scope): descripcion | <=72 chars
FDE: bridge product<->reality | delta = gap a cerrar | mission > persona
EVO: learn->design->experiment->analyze | cognition persiste | loop se repite
POC: proceso > herramienta | sin harness = silo | 5 preguntas antes de adoptar
TKN: Cache-Shape | Structured Compact | Failure-Spend | Observation Masking
PBT: property-based | invariantes + templates | -59% alucinaciones
CEN: Context Engineering | relevancia primero | chunking + progressive disclosure
BTR: Behavioral Tracing | decision + rationale + confidence | fingerprints por agente
AGR: guardrails de arquitectura | layers | tamano | imports prohibidos
SVE: SemVer MAJOR.MINOR.PATCH | changelog | skills y prompts versionados
UPG: Upgrade Continuo | ultima version estable | investigar antes | migrar si hay alternativa mejor
NAM: snake_case archivos+vars+funcs | PascalCase clases | UPPER_SNAKE constantes | nombres que se explican solos
TYP: type hints publicas | PEP 604 X|Y | TypeVar/aliases | sin Any innecesario | mypy --strict
IMM: frozen dataclasses | NamedTuple | tuple sobre list | copy sobre mutar
SOL: SRP+OCP+LSP+ISP+DIP | una responsabilidad | depender de abstracciones
MAG: sin literales magicos | constantes con nombre | Enum para discretos
FSZ: max 30 lineas | una responsabilidad | guard clauses | complejidad <10
CMP: composicion sobre herencia | HAS-A sobre IS-A | jerarquias <=2
DEM: solo amigos directos | sin chains a.b.c.d | tell dont ask
EDV: evidencia medible, no preferencia | benchmark -> decidir -> heredar en SSOT -> iterar
FRS: Frontier Research | web research SIEMPRE | solucion mas avanzada/eficiente/confiable | docs + commit al final
RSV: Roadmap Sync | cada >=5 refactors leer roadmap + retrospectiva | features de frontera
FND: Foundation-First | entorno antes que producto | walking skeleton + CI <90s + seguridad ANTES de features
SPE: Spec-First | spec ANTES de ejecutar | outcome + exit criteria | sin spec = sin start
DOM: Mapa de dominio | docs/fdd/dominio.md vivo | entidades + lenguaje ubicuo | DDD si el dominio es complejo
FIC: Ficha por feature | accion + resultado + objeto | corte vertical + criterios demostrables | estado para retomar
FRC: Friccion proporcional | elegir -DD por requisito | irreversible = spec + ADR + rollback | puntual = fix + test
OWN: Propiedad de archivos | un solo coordinador por ola | cada archivo con dueno | paralelo sin archivos compartidos
GATE: Evidence-Gated | claim->evidence->gate | 0 false-DONE | T1 determinista + T2 judge + T3 regresion
HIT: Hitos FDD | disenado->implementado->verificado->integrado | integrado SOLO lo marca una persona | sin evidencia = no hecho
DEC: Decisiones cerradas | tema/decision/por que | invariantes con una sola puerta | el doc manda
FAIL: Failure Registry | fallos en JSONL | destilar en skills | aprender del error
SBX: Sandboxing | aislamiento por tarea | rollback plan | timeout/contenedor como minimo
CPD: Fundamentos Competicion | edges+invariants+BigO ANTES de codear | diagnose->repair->regenerate | doble verificacion
ADV: Verificacion adversarial | atacante->steelman->juez | T siempre ultimo | fortalecer antes de confiar
CLA: Clean Architecture | Presentation->Application->Domain<-Infrastructure | dominio puro | ports/adapters + DIP
VAL: Input Validation | todo input externo validado contra schema ANTES del dominio | Pydantic/Zod
FST: Fail-Fast tipado | error tipado con cause + contexto | nunca swallow
AAA: Test AAA | Arrange-Act-Assert | 1 test = 1 criterio | mocks en unit
ATM: Atomic Changes | 1 commit/PR = 1 preocupacion logica
```
