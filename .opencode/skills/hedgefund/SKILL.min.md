---
name: hedgefund
domain: financial
description: "Usar cuando se opera el proyecto como fondo institucional. riesgo/reward, mandato, stop-loss, asignacion de capital, riesgo institucional. Alcance: doctrina y estrategia; para motores ver quant-trading, para ejecucion ver risk-execution. Cuando NO usar: ver Alcance. | UPG-NAM-FRS (reglas en base_principles.md)"
license: MIT
version: 1.0.0
project_agnostic: true
---

# Hedgefund (min)

Doctrina fundacional: el proyecto se opera como un fondo institucional. 3 pilares
universales: DATA SCIENCE (sin datos no hay decision), RISK INSTITUCIONAL (el
riesgo se mide, asigna y limita antes de buscar retorno) y OPS EFFICIENCY (cada
token tiene costo de oportunidad).

## Roles (agente <-> fondo)
- `coordinator` = CIO (asignacion, go/no-go) | `builder` = PM (P&L por iniciativa)
- `scientist` = Quant Researcher | `guardian` = CRO (risk limits, veto)
- `evolve` = COO (eficiencia, auto-mejora, cognition)

## Reglas
- Tesis con tesis, anti-tesis, catalyst y sizing; un mandato por documento.
- Hipotesis falseable (H0/H1) antes de invertir recursos; validacion OOS.
- Stop-loss / limite de drawdown por posicion; sin datos -> BLOCK.
- Cada skill opera DENTRO de este marco; el CIO es el guardian de la doctrina.

## Checklist
- [ ] Tesis con anti-tesis, catalyst y sizing
- [ ] Mandato unico con limites de riesgo explicitos
- [ ] Hipotesis falseable + validacion OOS
- [ ] Stop-loss / limite de drawdown definido
- [ ] Evidencia de datos que respalde la decision
