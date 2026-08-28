# ADR-0061: Spec-First template (Proof-or-Stop + AgentSPEX)

**Fecha**: 2026-08-26
**Estado**: Aceptado
**Decisor**: Coordinator (SWARMIND)
**Categoría**: Proceso / Agentic Engineering

## Contexto

SWARMIND tiene la doctrina VER ("nunca afirma, verifica") pero no tiene un formato estandarizado para definir QUÉ se va a verificar antes de empezar. Los agentes empezaban a codificar sin spec formal, lo que causaba:

1. **Scope creep**: sin exit criteria claros, las tareas crecían indefinidamente
2. **False-DONE**: agentes marcaban tareas como completas sin evidencia
3. **Sin rollback plan**: cuando algo fallaba, no había plan de reversión
4. **Sin feedback loop**: las lecciones no se capturaban estructuradamente

Papers de frontera:
- **Proof-or-Stop** (Huang 2026): cada output es un claim, no estado. Lifecycle solo avanza con evidencia fresca. Redujo false-DONE de 31/1800 a 2/1800.
- **AgentSPEX** (Wang 2026): specs YAML declarativos con pre/post-conditions por step.

## Decisión

Crear `specs/task_template.md` como plantilla obligatoria para toda tarea:

### Estructura (7 secciones)
1. **Specification**: outcome deseado, FR/NF
2. **Plan**: pasos con dependencias y evidencia esperada
3. **Evidence**: T1/T2/T3 checks obligatorios
4. **Sandbox**: scope de archivos, rollback plan
5. **Exit Criteria**: gates para transiciones (IN_PROGRESS→EVIDENCE→REVIEW→DONE)
6. **Feedback**: lecciones aprendidas, métricas, skill derivado
7. **Approval**: gate voting (builder/guardian/scientist)

### Flujo
```
Draft → In Progress → Evidence → Review → Done
                     ↓ Failed (con failure registry)
```

## Consecuencias

### Positivas
- Cada tarea tiene outcome medible ANTES de ejecutar
- Exit criteria claros eliminan false-DONE
- Feedback loop captura lecciones para evolve
- Sandbox scope previene daño colateral
- Rollback plan siempre definido

### Negativas
- Overhead inicial: cada tarea requiere ~5 min de spec
- Template puede ser overkill para tareas triviales (< 30 min)

### Mitigación
- Tareas triviales pueden usar versión simplificada (solo secciones 1, 5, 6)
- El template es un ARCHIVO, no un proceso burocrático

## Referencias

- Huang et al. "Proof-or-Stop: Loop Engineering for Verifiable Evidence-Gated Lifecycle Control" (2026)
- Wang et al. "AgentSPEX: Agent Specification and Execution Language" (2026)
- Pondero "CI for Agents: Tiered Eval Gates" (2026)

## Archivos afectados

- `specs/task_template.md` (nuevo)
