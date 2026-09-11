---
name: process-over-tools
domain: orchestration
version: 1.0.0
project_agnostic: true
description: "Usar cuando se evalúa adoptar herramienta, modelo o agente en el proyecto: aplica el principio 'la diferencia no es la herramienta, es el proceso' — antes de adoptar, define objetivo, responsable, datos, medición y escalado, y enrútalo al harness. | UPG·NAM·FRS (reglas en base_principles.md)"
license: MIT
---

# Process Over Tools (min)

5 preguntas antes de adoptar cualquier herramienta; nunca agentes sueltos:
fan-out + votacion (gate ≥ 70), memoria SSOT via !rag, oraculos
PBT/mutacion, KPIs; adoptar procesos, no herramientas (caso ORCA).

## Las 5 preguntas
1. **¿Problema?** — gap concreto que cierra (task_planner, adaptive_planner)
2. **¿Responsable?** — quien ejecuta/decide (multi_user_governance, mars_scheduler)
3. **¿Datos?** — memoria SSOT Memory_Proyects, no DBs paralelas (!rag, federated_search, LanceDB)
4. **¿Medicion?** — votacion gate≥70 (N=3), PBT, mutation, AgentKPITracker, token_budgets.yaml
5. **¿Escalar?** — evolve, MetaClaw, GPU/CUDA

## Reglas
- La diferencia no es el modelo: es el harness (caso ORCA 2026: se descarto la herramienta, se adopto su proceso)
- Sin gap demostrable no hay adopcion (IDP); sin medicion no existe
- Enrutar al harness: fan-out N=3 + votacion gobernada + memoria SSOT + oraculos
- Documentar mesa de trabajo + ADR (FRS)

## Checklist
- [ ] 5 preguntas respondidas
- [ ] Gap vs harness existente (IDP)
- [ ] Fan-out + votacion gate>=70
- [ ] Memoria SSOT, sin DBs paralelas
- [ ] Oraculos PBT/mutation + KPIs + budget
- [ ] ADR + docs actualizados
- [ ] Evidencia: tests + lint verdes (VER)
