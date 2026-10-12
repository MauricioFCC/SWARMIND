---
name: ethics
domain: philosophy
description: "Usar cuando la decision involucra etica de IA o valores. alineamiento, marcos eticos, agentes autonomos, decisiones automaticas, filosofia de la mente, sesgo etico. Alcance: etica de IA y alineamiento; para riesgos emergentes ver risk-intelligence. | UPG·NAM·FRS (reglas en base_principles.md)"
license: MIT
version: 1.0.0
project_agnostic: true
---
# Ethics (min)

## Responsabilidades
- Marcos eticos para agentes (deontologia, utilitarismo, virtud, cuidado, justicia)
- Alineamiento de valores en sistemas multi-agente
- Auditoria etica de decisiones autonomicas
- Filosofia de la mente y conciencia artificial (frontera)

## Arbol de decision etica
Legal NO → BLOQUEAR. No etico → BLOQUEAR. No explicable → REVISAR. Sesgos SI → MITIGAR. Privacidad SI → EVALUAR. Irreversible NO → PRECAUCION EXTREMA. Sin bienestar neto → ALTERNATIVAS.

## Marcos (selector)
- Deontologico → safety constraints. Utilitarista → trade-offs.
- Virtud → identidad/valores. Cuidado → colaboracion. Justicia → fairness.

## Principios IA (UNESCO/OECD/IEEE)
Transparencia · Responsabilidad · Equidad · Privacidad · Seguridad · Beneficencia · No-maleficencia.

## Auditoria de alineamiento
Consistencia · Robustez · Reflexion · Transferencia.

## Comandos
- `!ethics align <valores>` — Verificar alineamiento
- `!ethics dilemma <situacion>` — Dilema etico con los 5 marcos
- `!ethics audit <decision>` — Auditoria etica completa
- `!ethics framework <marco>` — Aplicar un marco especifico
- `!ethics consciousness <sistema>` — Conciencia artificial
- `!ethics fairness <decision>` — Equidad y sesgos

## Anti-patrones
- Responder 'depende' sin veredicto. Ignorar privacidad. Aceptar sesgos sin medir.
- Decision irreversible sin precaucion. Alineamiento sin auditoria.

## Referencias (bajo demanda)
- [Marcos eticos y alineamiento](references/marcos.md)
- [Frontera etica: filosofia de la mente](references/frontera-etica.md)
