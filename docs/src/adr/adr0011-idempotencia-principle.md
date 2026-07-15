# ADR-0011: Idempotencia — No Reimplementar si ya Existe

## Estado
**ACEPTADO** — Implementado en commit a7dcfee.

## Contexto
El sistema AGENTIC ejecuta cientos de tareas de implementacion, investigacion y testing.
En cada ejecucion existe el riesgo de reimplementar funcionalidad que ya existe, lo cual:

1. **Desperdicia tokens**: Cada reimplementacion cuesta tokens de entrada (contexto + codigo) y salida (codigo nuevo) sin valor agregado.
2. **Inconsistencia**: Dos implementaciones de la misma funcionalidad pueden divergir en comportamiento, rompiendo SSOT (Single Source of Truth).
3. **Ciclos redundantes**: El sistema puede entrar en loops de "mejorar" lo que ya funciona, consumiendo presupuesto sin delta real.
4. **Deuda cognitiva**: La cognition store se llena de variantes de la misma solucion, dificultando la recuperacion de la correcta.

Se requiere un principio formal que prevenga trabajo redundante sin impedir mejoras genuinas.

## Decision
Establecer **Idempotencia (IDP)** como principio universal trans-agentico: **si ya esta implementado, NO reimplementar; solo mejorar si hay delta demostrable.**

### Definicion Formal

```
IDP: Antes de implementar cualquier funcionalidad:
  1. VERIFICAR existencia con: git log, ADRs, cognition store, archivos existentes
  2. Si existe Y funciona → PASAR a la siguiente tarea
  3. Si existe pero hay MEJORA demostrable → implementar mejora y documentar delta
  4. Si NO existe → implementar normalmente

Delta = mejora cuantificable (ej: -X% tokens, +Y% speed, +Z% coverage, -W% latency)
Solo se procede si delta > 0. Sin delta demostrable, no hay implementacion.
```

### Niveles de Aplicacion

| Nivel | Alcance | Regla |
|-------|---------|-------|
| **Builder** | Codigo, APIs, refactors | Verificar `git log`, archivos existentes. Si la funcion/clase/api ya existe, no reescribir. |
| **Scientist** | Investigacion, papers, analisis | Verificar ADRs, cognition store, papers previos. No repetir investigacion ya hecha. |
| **Guardian** | Tests, auditorias, seguridad | Verificar test suite existente, coverage reports. Solo anadir tests que cubran caminos nuevos. |
| **Coordinator** | Orquestacion, delegacion | Verificar estado del sistema antes de delegar. No re-planificar lo que ya esta en ejecucion. |
| **Evolve** | Auto-mejora, skills, cognition | Verificar cognition store y git log. No proponer mejora de algo que ya se mejoro sin delta nuevo. |

### Check-list de Idempotencia

- [ ] `git log --oneline` revisado para commits similares
- [ ] ADRs revisados (docs/src/adr/)
- [ ] Archivos existentes revisados (grep por nombre/funcionalidad)
- [ ] Cognition store consultada
- [ ] Delta documentado (si aplica mejora)
- [ ] Justificacion de por que es mejora y no redundancia

## Codificacion en el Sistema

### base_principles.md (Nivel 1 — Esencial)
```
IDP: Idempotencia | si ya esta implementado NO reimplementar | solo mejorar
```

### base_principles.md (Nivel 2 — Estandar)
```
IDP: Idempotencia: si la funcionalidad ya existe, NO reimplementar.
Verificar con git log, cognition store, ADRs existentes.
Solo mejorar si hay delta demostrable.
```

### context_injector.py — UNIVERSAL_FIRMA
```
+Idempotencia
```

### context_injector.py — STANDARDS_ENCODED
Cada agente (builder, scientist, guardian, coordinator, evolve) incluye `+Idempotencia` en su cadena de estandares.

### SETUP.md
Nueva seccion completa como **Regla #2** despues de Research First.

## Archivos Modificados
- `.opencode/core/base_principles.md`: +IDP en Nivel 1 (linea 21) + Nivel 2 (linea 39)
- `.opencode/agents/builder.md`: +Idempotencia en tabla de Reglas Fijas
- `.opencode/agents/builder.agent.min.md`: +Idempotencia en REGLAS FIJAS
- `.opencode/agents/coordinator.md`: +Idempotencia en Reglas Fijas
- `.opencode/agents/coordinator.agent.min.md`: +Idempotencia en REGLAS FIJAS
- `.opencode/agents/evolve.md`: Nueva seccion Idempotencia
- `.opencode/agents/evolve.agent.min.md`: +Idempotencia en reglas
- `.opencode/agents/guardian.md`: Nueva seccion Idempotencia
- `.opencode/agents/guardian.agent.min.md`: +Idempotencia en reglas
- `.opencode/agents/scientist.md`: Nueva seccion Idempotencia
- `.opencode/agents/scientist.agent.min.md`: +Idempotencia en reglas
- `harness/memory_rag/context_injector.py`: UNIVERSAL_FIRMA + STANDARDS_ENCODED con Idempotencia
- `SETUP.md`: Nueva seccion Regla #2
- `docs/src/adr/README.md`: +ADR-0011

## Consecuencias
- **Positivas**: Elimina trabajo redundante, preserva tokens, mantiene SSOT, evita ciclos de mejora sin delta, alinea con Token Economics (Failure-Spend Governance).
- **Negativas**: Requiere verificacion previa (~5-10 segundos adicionales por tarea), puede omitir mejoras pequenas si el delta no se documenta correctamente.
- **Research First complementario**: IDP actua despues de Research First — primero se investiga el estado del arte, luego se verifica si ya esta implementado.

## Referencias
- **Idempotencia en sistemas distribuidos**: "Idempotence is not a single thing", Pat Helland, 2012
- **Principio DRY (Don't Repeat Yourself)**: The Pragmatic Programmer, Hunt & Thomas, 1999
- **SSOT (Single Source of Truth)**: Concepto de Data Warehousing, Dataversity
- **Token Economics AGENTIC**: ADR-0008 Token Economy & Speed Optimization v2026
- **Research First Principle**: ADR-0008, ADR-0009, ADR-0010, base_principles.md
