# Frontier research — Modo tutor socrático para el harness y las skills

> **Fecha:** 2026-11-12 · **Ciclo:** 11.95 · **Skill:** `frontier-engineering`
> **Tarea explícita:** refactorizar el harness y las skills para que el agente
> **enseñe** en vez de resolver: preguntas guía, pistas escalonadas, práctica de
> recuperación y autoevaluación. Debe ser **opt-in** ("cuando aplique"), no el
> modo por defecto de una tarea de implementación.

## 0. Persona y canon

Instructional designer senior + AI architect. Regla anti-hedging: sin fuente
leída no hay claim; la pedagogía se elige por evidencia, no por preferencia.

## 1. Fuentes leídas (paper trail)

| # | Fuente | URL | Aporte | Estado |
|---|--------|-----|--------|--------|
| F1 | Kestin et al., *AI tutoring outperforms in-class active learning: an RCT* (Scientific Reports, 2025) | https://www.nature.com/articles/s41598-025-97652-6 | 194 estudiantes, diseño crossover: el tutor IA dio **>2× ganancia mediana** vs clase activa, en menos tiempo (49 vs 60 min) | ✅ leída |
| F2 | Harvard Gazette — *Professor tailored AI tutor to physics course* (2024) | https://news.harvard.edu/gazette/story/2024/09/professor-tailored-ai-tutor-to-physics-course-engagement-doubled | Contexto del RCT: feedback personalizado y autopaced | ✅ leída |
| F3 | Bastani et al., *Generative AI without guardrails can harm learning* (PNAS, 2025) | https://www.pnas.org/doi/10.1073/pnas.2422633122 | GPT Base: **+48% en práctica, -17% en examen**; GPT Tutor (pistas sin respuesta): **+127% práctica, examen ≈ control** | ✅ leída |
| F4 | Wharton — *Without Guardrails, Generative AI Can Harm Education* | https://knowledge.wharton.upenn.edu/article/without-guardrails-generative-ai-can-harm-education | Interpretación: la dependencia sin guardrails no construye el concepto | ✅ leída |
| F5 | Anthropic — *How AI assistance impacts the formation of coding skills* (2026) | https://www.anthropic.com/research/AI-assistance-coding-skills | 52 ingenieros junior: delegación **<40%** de comprensión; preguntas conceptuales **65%+**; generar→comprender **86%** | ✅ leída |
| F6 | InfoQ — *AI Coding Assistance Reduces Developer Skill Mastery by 17%* (2026) | https://www.infoq.com/news/2026/02/ai-coding-skill-formation | Resume el RCT de Anthropic y los patrones de uso | ✅ leída |
| F7 | Freeman et al., *Active learning increases student performance in science, engineering, and mathematics* (PNAS, 2014) | https://www.pnas.org/doi/10.1073/pnas.1319030111 | Meta-análisis de 225 estudios: la clase activa supera a la pasiva | ✅ leída |
| F8 | Karpicke & Blunt / Roediger & Karpicke — retrieval practice (Purdue PDF, 2012) | https://learninglab.psych.purdue.edu/downloads/2012/2012_Karpicke_CDPS.pdf | Recuperación activa > relectura; repetir recuperación mejora retención | ✅ leída |
| F9 | VanLehn, *The relative effectiveness of human tutoring, ITS and other tutoring systems* (2011) | https://www.tandfonline.com/doi/abs/10.1080/00461520.2011.611369 | Tutores con feedback cercano al humano superan a la instrucción grupal | [UNVERIFIED] |
| F10 | Kapur, *Productive failure* (2008) | https://www.tandfonline.com/doi/abs/10.1080/07370000802212669 | Intentar antes de recibir la solución mejora la transferencia | [UNVERIFIED] |
| F11 | Chi & Wylie, *ICAP framework* (2014) | https://www.tandfonline.com/doi/full/10.1080/00461520.2014.965823 | Interactivo > constructivo > activo > pasivo | [UNVERIFIED] |

**Lectura ejecutiva:** el patrón que gana no es "IA que responde", sino **IA que
hace preguntas y exige un intento antes de revelar**. La delegación total
funciona a corto plazo y falla en la transferencia.

## 2. Hipótesis comparadas

Criterios: **T** = retención/transferencia; **E** = engagement; **S** =
escalabilidad; **C** = costo; **R** = reproducibilidad.

| Hipótesis | T | E | S | C | R | Veredicto |
|-----------|---|---|---|---|---|-----------|
| **H1. Delegación** (la IA escribe/explica y el humano copia) | **Baja**: -17% en examen (F3), <40% comprensión (F5) | Alta a corto plazo | Alta | Bajo | Alta | Rechazada para aprendizaje |
| **H2. Tutor con pistas** (nunca da la respuesta) | Media-alta: +127% práctica, examen ≈ control (F3) | Alta | Alta | Bajo | Alta | Necesaria pero insuficiente |
| **H3. Socrático + recuperación + generar→comprender** (pregunta, intento, pista, autoexplicación, recall espaciado) | **Alta**: >2× (F1) y 86% (F5) en los patrones activos | Alta | Alta | Bajo-Medio | Alta | **Elegida** |
| H4. Clase humana activa | Alta (F7) pero < H3 en el RCT (F1) | Media | Baja | Alto | Media | Baseline, no implementable en el harness |

**Decisión:** H3 como **modo opt-in** (`guide`/`exam`), con H2 como fallback si
el usuario pide solo pistas. H1 sigue disponible para tareas de producción
donde el objetivo es entregar, no aprender.

## 3. Gap analysis (IDP)

Lo que SWARMIND ya tiene:

- Skills de dominio (`education`, `psychology`, `frontier-engineering`).
- `AGENTS.md` con doctrina RSF/VER/TST.
- Memoria central RuscaDB + catálogo de conocimiento.
- `harness/` con CLI, self-update y gates `xtask`.

Lo que falta:

1. Un **estado de sesión de tutoría** (nivel de pista, intentos, concepto,
   próxima revisión) que sobreviva entre turnos.
2. Una **política de revelación**: la solución solo se muestra con petición
   explícita; el nivel de pista sube de a uno.
3. Una **skill** que declare el contrato behavioral y los anti-triggers.
4. Un **CLI** (`tutor start|status|attempt|hint|solve|review`) y una directiva
   compacta para inyectar en el prompt.
5. **Medición**: registrar intentos/pistas para saber si el modo se usa y si
   el usuario acierta más con menos ayuda (Kirkpatrick nivel 2).

## 4. Diseño y complejidad

```
usuario pide aprender
   → tutor start <tema> --mode guide
   → diagnóstico (1-2 preguntas)
   → intento del usuario (obligatorio antes de pista)
   → escalera: P0 pregunta → P1 concepto → P2 pista local → P3 parcial
   → solución SOLO con `solve --confirm` (petición explícita)
   → autoexplicación + recall (1/7/16/35 días)
```

- Estado por sesión: `O(1)` (tema, nivel, intentos, próximas fechas).
- Transición de pista: `O(1)`; nunca baja sin `repeat`.
- Persistencia: JSON atómico en `Memory_Proyects/data/tutor/`; `O(1)` por turno.
- Sin LLM en la política: determinista y testeable.

## 5. Riesgos

- **Fricción**: el modo tutor no debe activarse en tareas de entrega; es
  opt-in y se desactiva con `tutor off` o `TUTOR_MODE=off`.
- **Falsa maestría**: el usuario puede pedir la solución; se registra como
  `solution_revealed` y se recomienda una revisión.
- **Privacidad**: el estado guarda tema/notas, no código ni secretos.
- **Sobreajuste a un estudio**: se combinan 4 fuentes (RCT Harvard, PNAS
  Wharton, Anthropic, meta-análisis Freeman) y se declara lo no verificado.

## 6. No aplicado (con motivo)

- **Tutor humano**: no escalable; el harness lo simula con preguntas.
- **LLM juez de autoexplicación**: no determinista y costoso; se usa una
  checklist de conceptos y el propio usuario evalúa.
- **Adaptación total por conocimiento previo**: requiere un modelo del alumno
  a largo plazo; se deja para una fase con datos de sesiones.
