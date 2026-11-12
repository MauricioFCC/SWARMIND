# Spec: Modo tutor socrático (aprendizaje opt-in)

> **Estado:** nueva · **Ciclo:** 11.95 · **Fecha:** 2026-11-12
> **Research:** `docs/research/frontier-2026-11-12-socratic-tutor.md`
> **Dueño:** `harness/tutor/` + `scripts/tutor.py` + skill `socratic-tutor`
> **Decisión:** H3 — preguntas guía + intento obligatorio + pistas escalonadas
> + autoexplicación + recuperación espaciada. **Opt-in**, no modo por defecto.

## 1. Problema

El agente resuelve y el humano copia: la práctica mejora (+48%) pero el examen
empeora (-17%) (Wharton/PNAS); la delegación total deja <40% de comprensión
frente a 65-86% cuando se pregunta (Anthropic). El harness necesita un modo que
**haga pensar** al usuario, sin imponer fricción a las tareas de entrega.

## 2. Objetivos

1. Estado de sesión persistente (tema, nivel de pista, intentos, revisión).
2. Escalera de ayuda que **nunca** revela la solución sin petición explícita.
3. Directiva compacta para que cualquier agente (OpenCode, Claude Code) sepa
   cómo responder en modo tutor.
4. Skill con contrato y anti-triggers (no activar en tareas de producción).
5. Medición mínima: intentos, pistas usadas, soluciones reveladas.

### No objetivos

- Sustituir la implementación normal cuando el usuario pide "hazlo".
- Evaluar automáticamente la calidad de la explicación con un LLM.
- Crawling de material didáctico.

## 3. Estados y transiciones

```
OFF ──start──▶ GUIDE/EXAM ──attempt──▶ (mismo nivel, intentos+1)
                     │
                     ├─hint──▶ nivel+1 (máx PARTIAL)
                     ├─solve --confirm──▶ SOLUTION (explícito)
                     └─off──▶ OFF
```

`HintLevel`: `QUESTION(0) < CONCEPT(1) < LOCAL(2) < PARTIAL(3) < SOLUTION(4)`.

Invariantes:

- `next_hint` sube **como máximo un nivel** y nunca llega a `SOLUTION`.
- `reveal_solution` exige `confirm=True`; sin confirmación lanza `ValueError`.
- Un intento nunca reduce el nivel; `repeat` lo reinicia a `QUESTION`.
- Las fechas de revisión son 1/7/16/35 días desde el intento correcto.

## 4. Persistencia

JSON atómico en `MEMORY_ROOT/data/tutor/sessions.json` (o
`TUTOR_STATE_PATH` para tests). Forma:

```json
{"version": 1, "sessions": {"<topic>": {...}}}
```

Sin código, sin secretos, sin rutas personales.

## 5. Interfaz

- `harness/tutor/__init__.py`: `TutorMode`, `HintLevel`, `TutorSession`,
  `TutorPolicy`, `TutorStore`, `default_state_path`.
- CLI `scripts/tutor.py`: `start|status|attempt|hint|solve|review|off`.
- `directive(session)`: bloque markdown que se inyecta en el prompt:
  "no des la solución; haz preguntas; pide un intento; nivel actual".

## 6. Criterios de aceptación (testeables)

- **AC1** `start` crea sesión en `QUESTION` con 0 intentos.
- **AC2** `attempt` incrementa intentos y no baja el nivel.
- **AC3** `hint` sube exactamente un nivel, tope `PARTIAL`; nunca `SOLUTION`.
- **AC4** `solve` sin `confirm` lanza `ValueError`; con `confirm` marca
  `solution_revealed=True`.
- **AC5** `directive` incluye el nivel, el tema y la prohibición de revelar.
- **AC6** `review_schedule` devuelve 4 fechas crecientes (1/7/16/35 días).
- **AC7** `TutorStore` hace round-trip atómico y `list`/`active` funcionan.
- **AC8** El CLI persiste entre invocaciones y respeta `TUTOR_STATE_PATH`.

## 7. Plan de tests

- Unitarios (AC1-AC8) + property-based: monotonía de nivel/intentos.
- Mutantes esperados: invertir comparación de nivel, permitir solución sin
  confirm, no persistir, devolver fechas desordenadas.
- Sin dependencia de red ni del DLL nativo (estado JSON puro).

## 8. Integración

- `AGENTS.md`: sección "Modo tutor (opt-in)" con disparadores y anti-triggers.
- Skill `socratic-tutor` en `.opencode/skills/` + registry.
- `xtask` ya valida skills (`validate_skills --strict`).
