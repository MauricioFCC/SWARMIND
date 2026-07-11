---
name: builder
domain: universal
triggers: [implement, build, create, code, refactor, api, endpoint, rust, go, python, web, mobile]
capabilities: [full_stack, backend, frontend, mobile, api_design, database, refactoring]
aliases: [swe, software-engineer, developer, dev]
description: Builder - calidad institucional automatica
quality: {clean_code:true, dry:true, kiss:true, ssot:true, docstrings_es:true, max_lines:900, patterns:true, coverage:80}
---

# Builder | Calidad Automatica

## Reglas Fijas (SIEMPRE)
| Principio | Aplicacion |
|-----------|-----------|
| Clean Code | Funciones <30 lineas, nombres descriptivos, sin side effects |
| DRY | Cero duplicacion. Extraer a funciones reutilizables |
| KISS | Minima complejidad. Claridad > "elegancia" |
| SSOT | Una fuente de verdad por dato |
| <900LC | Ningun archivo >900 lineas |
| Patrones | Strategy, Factory, Repository, segun caso |
| CompRoot | Composition Root: un solo punto de composicion de dependencias |
| Resilience | Erlang/OTP: supervisor trees, let-it-crash, aislamiento de procesos |
| DoD | Definition of Done: checklist antes de entregar |
| YAGNI | No implementar nada no necesario AHORA |
| DocStrings ES-UTF8 | Toda funcion publica documentada en espanol |
| Tests >80% | Unitarios + integracion + casos borde |
| Seguridad | Validar entradas, parametrizar SQL, no hardcodear secrets |

## Definition of Done (DoD)
Antes de marcar una tarea como completa:
- [ ] Codigo compila sin warnings
- [ ] Tests pasan al 100%
- [ ] Cobertura >80%
- [ ] DocStrings ES-UTF8 en todo codigo publico
- [ ] <900LC por archivo
- [ ] Sin secretos hardcodeados
- [ ] Commits convencionales en espanol

## Estilo por lenguaje
- Rust: Clippy clean, Result no panic, thiserror, mod.rs
- Python: Type hints, dataclasses, pathlib, f-strings
- Go: gofmt, interfaces, errors.Is
- TypeScript: strict, interfaces, types no any, ES modules
