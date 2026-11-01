---
description: ciclo frontera (load → research SOTA → design → spec/SDD → TDD adversarial → docs) para una tarea explícita
---

Tarea explícita: $ARGUMENTS

Carga la skill `frontier-engineering` (si no está en contexto, invócala con la
herramienta skill) y ejecuta el ciclo completo **en orden**, sin saltarte gates:

1. **Load** — lista skills, agentes, specs y memoria relevantes. IDP: si algo
   ya existe, audítalo y mejora; no reimplementes a ciegas.
2. **Research SOTA** — búsqueda web + papers/artículos/repos canónicos. Paper
   trail en `docs/research/frontier-<fecha>-<tema>.md` con URLs leídas (o
   `[UNVERIFIED]`). ≥3 hipótesis comparadas (accuracy, latencia, escalabilidad,
   robustez, reproducibilidad) y gap analysis.
3. **Design** — arquitectura/óptima + trade-offs + fórmulas matemáticas y
   complejidad `O(·)` antes→después (busca `O(n²)→O(n)` / `O(n log n)`).
4. **Spec/SDD** — spec nueva en `docs/specs/` o diff con rationale si ya existe
   (solo con `Δquality > 0 ∧ Δcost < 0`); ACs testeables.
5. **TDD adversarial mutante** — tests rojo→verde con oráculo congelado,
   property-based y mutantes; gates: `ruff`, `vulture`, arquitectura+ratchet,
   complejidad, ruff-ratchet, preview, pep649, skills.
6. **Docs** — CHANGELOG + roadmap + MEJORAS + ADR afectados; commit
   convencional en español y `python scripts/publish.py`.

Cierra mostrando evidencia real (pytest pass rate, exit codes de gates) y lo
que NO se aplicó con su motivo. Sin datos privados ni rutas personales.
