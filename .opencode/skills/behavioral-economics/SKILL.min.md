---
name: behavioral-economics
domain: economics
description: "Usar cuando el problema involucra decisiones humanas bajo incertidumbre. teoria de juegos, sesgos cognitivos, heuristicas, incentivos, nudges. Alcance: decisiones economicas; para aprendizaje y equipo ver psychology. | UPG·NAM·FRS (reglas en base_principles.md)"
license: MIT
version: 1.0.0
project_agnostic: true
---
# Behavioral Economics (min)

## Responsabilidades
- Analisis de teoria de juegos en negociaciones multi-agente
- Identificacion y mitigacion de sesgos cognitivos
- Diseno de incentivos y mecanismos
- Toma de decisiones bajo incertidumbre

## Selector de juego
- Acuerdos vinculantes → cooperativo (Shapley). No vinculantes → Nash.
- Simultaneo → matriz de pagos. Secuencial → induccion hacia atras.
- Suma cero → conflicto puro. Suma no cero → win-win.

## Protocolo de sesgos
`DETECTAR → CUANTIFICAR → CORREGIR → VERIFICAR → REGISTRAR`. Alto impacto: anclaje, confirmacion, exceso de confianza, supervivencia, bandwagon.

## Mecanismos (Hurwicz-Myerson)
Compatibilidad de incentivos · racionalidad individual · eficiencia asignativa · presupuesto balanceado · veracidad.

## Decision bajo incertidumbre
Certeza → determinista. Riesgo → utilidad esperada. Ambigua → Maximin. Ignorancia → heuristicas + exploracion.

## Comandos
- `!behav game <situacion>` — Analisis de teoria de juegos
- `!behav biases <decision>` — Identificar y mitigar sesgos
- `!behav incentive <objetivo>` — Diseno de mecanismos
- `!behav decision <problema>` — Decision bajo incertidumbre
- `!behav nudge <comportamiento>` — Diseno de nudge transparente
- `!behav market <recurso>` — Diseno de mercado entre agentes

## Anti-patrones
- Asumir racionalidad perfecta. Premiar metrica proxy (Goodhart).
- Generalizar sin evidencia. Ignorar aversion al riesgo. Nudge manipulador.

## Referencias (bajo demanda)
- [Teoria: juegos, sesgos, incentivos, decision](references/teoria.md)
- [Aplicaciones en Swarmind](references/aplicaciones.md)
