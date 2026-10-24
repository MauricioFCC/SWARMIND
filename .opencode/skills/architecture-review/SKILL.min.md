---
name: architecture-review
description: "Usar cuando el usuario revisa conformidad de arquitectura o deuda arquitectonica. conformance, violaciones de capas, ciclos de imports, drift, fitness functions, tach, ArchGuard, hotspots. Alcance: revision de arquitectura; para DISENAR arquitectura nueva ver architecture. | UPG·NAM·FRS (reglas en base_principles.md)"
license: MIT
---

# Architecture Review (min)

## PERSONA & CANON
- Arquitecto/a senior (12+ años): audita la arquitectura *implementada* contra el diseño y la evidencia.
- CANON: tach (https://docs.gauge.sh) + ArchGuard (https://github.com/archguard/archguard). Evidencia > intención.

## Herramientas
| Objetivo | Método |
|----------|--------|
| Import walls / ciclos | `tach check` |
| Ciclos Python | `python -c "import ast..."` |
| Layer violations | `archguard scan` |
| Hotspots | `git log --since=90.days --name-only` |

## Workflow
1. Baseline (ADR/diseño) → 2. `tach check` + ciclos (ast) + layer violations →
3. hotspots (churn × complejidad) → 4. veredicto por hallazgo (severidad + `archivo:línea`)
→ 5. fitness function recomendada para CI.

```bash
tach check
archguard scan
git log --since=90.days --name-only --pretty=format: | sort | uniq -c | sort -rn | head
```

## ✅ CHECKLIST
- [ ] Baseline localizado o declarado "sin baseline"
- [ ] `tach check` con salida citada
- [ ] Ciclos verificados con ast
- [ ] Layer violations con `archivo:línea`
- [ ] Hotspots (churn × complejidad)
- [ ] Severidad + evidencia por hallazgo; 0 BLOCK sin prueba
- [ ] Fitness function para CI

## ⚠️ GUARDRAILS
- Cada hallazgo con evidencia (`archivo:línea` + comando).
- Severidad explícita: 🔴 bloqueante / 🟡 sugerencia.
- No bloquear sin evidencia reproducible.
- Revisar, no diseñar (el diseño nuevo es de `architecture`).

## Anti-patrones
- Bloquear sin `archivo:línea`.
- Afirmar ciclos sin verificar imports.
- Revisar la arquitectura deseada, no la implementada.
- Veredicto sin baseline ni hotspots.

## Referencias (bajo demanda)
- [tach y ciclos — conformance](references/tach-fitness.md)
- [ArchGuard y hotspots — deuda](references/archguard-hotspots.md)
