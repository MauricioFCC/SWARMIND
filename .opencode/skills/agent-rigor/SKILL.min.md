---
name: agent-rigor
domain: quality
description: "Usar cuando el usuario exige disciplina de ingeniería pre-merge. gates deterministas, anti-atajos, tests decorativos, verificación con evidencia, mutation score. Alcance: proceso de verificación; para mejora continua ver evolve. | UPG·NAM·FRS (reglas en base_principles.md)"
license: MIT
version: 1.0.0
project_agnostic: true
---

# Agent Rigor (min)

Disciplina de ingeniería pre-merge. Comandos: !rigor-premerge (lint+tests+ruff+vulture con evidencia), !rigor-decorativos (detecta tests sin oráculo). Reglas: 0 merges con check rojo; prohibido pintar verde; coverage piso (>=80% line+branch); MS>=70%; cada fix trae regresión.
