---
name: frontier-engineering
description: "Usar cuando el usuario pida ciclo frontera: cargar skills/agentes + tarea explícita, investigación web SOTA/papers, arquitecturas y algoritmos O(n²)→O(n), fórmulas, spec/SDD, TDD adversarial mutante y docs. Alcance: ciclo completo; para gates pre-merge ver agent-rigor. | UPG·NAM·FRS"
license: MIT
---

# Frontier Engineering (min)

Ciclo que dispara la petición explícita de frontera:

> "Carga skills, agentes, **<tarea explícita>**. Investigación web frontera,
> papers/artículos/técnicas, arquitecturas óptimas, algoritmos, complejidad
> O(n²)→O(n), fórmulas, spec (mejorar/reimplementar si aplica), SDD, TDD
> adversarial mutante, actualiza Docs."

Atajo: `/frontera <tarea explícita>`.

## Fases (no saltar gates)

1. **Load** — manifest de skills/agentes/specs/memoria; IDP: si existe, mejorar, no duplicar.
2. **Research** — `docs/research/frontier-<fecha>-<tema>.md`; URLs leídas o `[UNVERIFIED]`; ≥3 hipótesis comparadas.
3. **Design** — arquitectura + trade-offs + pseudocódigo con `O(·)` y fórmulas.
4. **Spec/SDD** — spec nueva o diff + rationale; ACs testeables.
5. **TDD adversarial** — rojo→verde, oráculo congelado, mutantes, gates verdes.
6. **Docs** — CHANGELOG + roadmap + MEJORAS + ADR; `publish.py`.

## Reglas duras

- RSF/FRS: sin fuente no hay claim.
- VER: el `O(n²)→O(n)` se mide (gate N/2N/4N) y se prueba contra el oráculo anterior.
- Si el test de equivalencia falla, auditar el oráculo **antes** que la implementación.
- Alcance honesto: técnica no aplicable se documenta con motivo.

## Checklist

- [ ] Tarea explícita acotada
- [ ] Research con URLs verificadas
- [ ] Complejidad antes→después medida
- [ ] Spec/SDD + tests adversariales
- [ ] Gates verdes + docs + `publish.py`
- [ ] Sin datos privados ni rutas personales
