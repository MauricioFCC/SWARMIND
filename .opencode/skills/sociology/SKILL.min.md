---
name: sociology
domain: sociology
description: "Usar cuando el problema involucra dinamicas sociales o de grupos. sociologia, antropologia, redes, cultura digital, grupos, sistemas multi-agente. Alcance: dinamicas sociales y redes; para psicologia individual ver psychology. | UPG·NAM·FRS (reglas en base_principles.md)"
license: MIT
version: 1.0.0
project_agnostic: true
---
# Sociology (min)

## Responsabilidades
- Dinamicas de grupos en equipos multi-agente (etapas Tuckman, roles Belbin, fenomenos grupales)
- Teoria de redes aplicada a topologias de comunicacion (metricas SNA)
- Sociologia del conocimiento y aprendizaje organizacional (SECI)
- Antropologia de la tecnologia y cultura digital (etnografia)

## Diagnostico de grupo (Tuckman)
- Forming → facilitar presentacion, definir reglas base.
- Storming → mediacion, clarificar objetivos y criterios.
- Norming → formalizar normas, celebrar acuerdos.
- Performing → monitorear, prevenir regresion a storming.
- Adjourning → documentar lecciones, cerrar ciclos.

## Protocolo SNA
1. MAPEAR nodos/edges → 2. MEDIR centralidad/densidad/clustering → 3. DIAGNOSTICAR cuellos de botella/aislamiento → 4. INTERVENIR puentes/roles → 5. MONITOREAR.

## Comandos
- `!socio group <dinamica>` — Analisis de dinamicas de grupo (Tuckman, Belbin, fenomenos)
- `!socio network <topologia>` — Analisis de red de agentes con metricas SNA
- `!socio culture <contexto>` — Analisis antropologico de cultura de agentes
- `!socio knowledge <problema>` — Transferencia de conocimiento (SECI)
- `!socio diversity <equipo>` — Diversidad cultural entre agentes
- `!socio ethnography <sistema>` — Diseno de estudio etnografico

## Anti-patrones
- Generalizar de una anecdota. Diagnostico sin datos ni marco teorico.
- Ignorar cultura y contexto de la red. Asumir homogeneidad del grupo.

## Referencias (bajo demanda)
- [Teoria social](references/teoria-social.md)
- [Redes y SNA](references/redes-sna.md)
- [Antropologia de la tecnologia](references/antropologia.md)
