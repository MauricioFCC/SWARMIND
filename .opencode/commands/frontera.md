---
description: ciclo frontera (load → research SOTA → design → spec/SDD → TDD adversarial → docs) para una tarea explícita
---

Tarea explícita: $ARGUMENTS

Invoca la skill `frontier-engineering` (SSOT del procedimiento) y ejecútala
completa, en orden, sin saltar gates:

| Fase | Entregable / gate |
|---|---|
| **Load** | skills, agentes, specs y memoria; IDP: auditar antes de reimplementar |
| **Research** | `docs/research/frontier-<fecha>-<tema>.md`; ≥3 hipótesis, URLs leídas o `[UNVERIFIED]`, gap analysis |
| **Design** | arquitectura, trade-offs, fórmulas y `O(·)` antes→después |
| **Spec** | `docs/specs/` nueva o diff; solo si `Δquality > 0 ∧ Δcost < 0`; ACs testeables |
| **TDD** | rojo→verde, PBT + mutantes; gates: ruff, vulture, arquitectura+ratchet, complejidad, ruff-ratchet, preview, pep649, skills |
| **Docs** | CHANGELOG + roadmap + MEJORAS + ADR; commit `type(scope): ...` y `python scripts/publish.py` |

Cierra con evidencia real (pytest pass rate, exit codes) y lo no aplicado con
su motivo. Sin datos privados ni rutas personales.
