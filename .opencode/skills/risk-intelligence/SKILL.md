---




name: risk-intelligence
domain: risk
description: "Usar cuando el usuario analiza riesgos emergentes. CRO Forum, riesgos tecnologicos, geopoliticos, climaticos, salud, financieros. | UPG·NAM·FRS (reglas en base_principles.md)"
license: MIT
compatibility: 'Python 3.12+'
version: 1.0.0
project_agnostic: true
inherit:
  - core/base_principles.md
variables:
  - RISK_FRAMEWORK: emerging-radar, cro-forum-2026, concentration-mapping
  - RISK_DOMAIN: technology, geopolitics, climate, health, finance
---

# Risk Intelligence — Identificacion de Riesgos Emergentes

## Descripcion
Skill especializado en identificar, analizar y priorizar riesgos emergentes
utilizando el framework CRO Forum 2026: Major Trends and Emerging Risk Radar.

## Capacidades
1. Analisis de riesgos tecnologicos (AI concentration, cyber, autonomy)
2. Analisis de riesgos geopoliticos (war, sanctions, supply chains)
3. Analisis de riesgos climaticos (damage, transition volatility, litigation)
4. Analisis de riesgos de salud (pollution, ageing, public care)
5. Analisis de riesgos financieros (debt, liquidity, solvency)

## Comandos
- `!risk radar` — Reporte completo de riesgos emergentes
- `!risk tech` — Riesgos tecnologicos (AI concentration, cyber)
- `!risk geo` — Riesgos geopoliticos (supply chains, sanctions)
- `!risk climate` — Riesgos climaticos y ambientales
- `!risk health` — Riesgos de salud publica
- `!risk finance` — Riesgos financieros (debt, liquidity)

## Referencias
- CRO Forum 2026: Emerging Risks Initiative
- Major Trends and Emerging Risk Radar 2026
