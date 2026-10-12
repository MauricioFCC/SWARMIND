---
name: linguistics
domain: linguistics
description: "Usar cuando el problema involucra lenguaje, semiotica o NLP. linguistica cognitiva, semiotica, pragmatica, analisis del discurso, procesamiento de lenguaje natural. Alcance: lenguaje, semantica y NLP; para documentacion cientifica ver science-doc. | UPG·NAM·FRS (reglas en base_principles.md)"
license: MIT
version: 1.0.0
project_agnostic: true
---
# Linguistics (min)

## Responsabilidades
- Linguistica cognitiva y teoria del significado (frame, metafora, prototipo)
- Pragmatica y comunicacion inter-agente (Grice, actos de habla, cortesia)
- Analisis del discurso y argumentacion (RST, Toulmin, falacias)
- Semiotica y analisis de significado (Peirce, niveles)

## Flujo de analisis
1. Fijar nivel ({{ANALYSIS_LEVEL}}) y rama ({{LING_BRANCH}}).
2. Definir formalmente + anotar ejemplos.
3. Desambiguar polisemia por contexto.
4. Evaluar con metrica NLP (F1/ROUGE).

## Checklist de cooperatividad (Grice)
- Cantidad: ni verbose ni escueto. Calidad: sin afirmar sin evidencia.
- Relacion: relevante al proposito. Modo: claro y ordenado.

## Protocolo Toulmin
CLAIM → GROUND → WARRANT → BACKING → QUALIFIER → REBUTTAL. Falacias (Walton): autoridad, analogia, consecuencias, pendiente resbaladiza, ad hominem.

## Comandos
- `!ling discourse <texto>` — Analisis del discurso (RST)
- `!ling pragmatics <mensaje>` — Pragmatica (actos de habla, implicaturas)
- `!ling argument <texto>` — Argumentacion (Toulmin, falacias)
- `!ling meaning <concepto>` — Significado (frame, metafora, prototipo)
- `!ling semiotics <signo>` — Semiotica (niveles, Peirce)
- `!ling coop <dialogo>` — Cooperatividad (Grice)

## Anti-patrones
- Definiciones intuitivas sin formalizacion. Ignorar pragmatica y contexto.
- Generalizar de un ejemplo unico. Traducir sin desambiguar. Analizar sin corpus.

## Referencias (bajo demanda)
- [Teoria del significado](references/teoria.md)
- [Discurso y argumentacion](references/discurso-argumentacion.md)
