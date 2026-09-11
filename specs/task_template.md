---
# Spec-First Task Template — Patrón Proof-or-Stop (Huang 2026)
# Cada tarea DEBE tener este spec ANTES de ejecutar.
# El agente lee este archivo y verifica los exit criteria antes de marcar DONE.
# Fuente: AgentSPEX (Wang 2026) + Proof-or-Stop + Pondero CI-for-Agents
task_id: "{{TASK_ID}}"
version: "1.0.0"
created: "{{DATE}}"
author: "{{AGENT_NAME}}"
status: "draft"  # draft | in_progress | evidence | review | done | failed
---

# {{TASK_TITLE}}

## 1. SPECIFICATION (Specification First)

### Outcome deseado
<!-- ¿Qué debe existir AL FINAL de esta tarea? Sé específico y medible. -->
<!-- "Al finalizar, X debe ser capaz de Y con Z condiciones." -->

### Requisitos funcionales
- [ ] FR-1: {{requisito 1}}
- [ ] FR-2: {{requisito 2}}
- [ ] FR-3: {{requisito 3}}

### Requisitos no-funcionales
- [ ] NF-1: Performance — {{latencia/memoria esperada}}
- [ ] NF-2: Seguridad — {{restricciones de seguridad}}
- [ ] NF-3: Portabilidad — {{funciona en Linux/Mac/Windows}}

## 2. PLAN (Plan & Task Breakdown)

### Pasos de ejecución
| # | Paso | Dependencias | Evidencia esperada |
|---|------|-------------|-------------------|
| 1 | {{paso 1}} | — | {{evidencia 1}} |
| 2 | {{paso 2}} | 1 | {{evidencia 2}} |
| 3 | {{paso 3}} | 1,2 | {{evidencia 3}} |

### Recursos necesarios
- Archivos a modificar: {{lista}}
- Archivos a crear: {{lista}}
- Tests a escribir: {{lista}}
- Dependencias nuevas: {{lista}}

## 3. EVIDENCE (Verification Loops)

### Checks obligatorios (T1 — deterministic, <90s)
- [ ] `ruff check` → 0 errores
- [ ] `pytest harness/tests/test_{{modulo}}.py -q` → todos pasan
- [ ] `vulture harness/{{archivo}} --min-confidence 80` → 0 dead code
- [ ] Importa correctamente: `python -c "from harness.{{modulo}} import {{clase}}"`

### Checks profundos (T2 — LLM-judge, <10min)
- [ ] Coverage del módulo >= 80%
- [ ] Mutation score >= 70% (si aplica)
- [ ] Type hints completos en interfaz pública
- [ ] Docstrings ES en TODAS las funciones nuevas

### Checks de regresión (T3 — full suite)
- [ ] `pytest harness/tests/ -q` → 0 regressions
- [ ] No se rompen tests existentes del módulo relacionado

## 4. SANDBOX (Aislamiento de Fallos)

### Scope de esta tarea
- **Modifica**: {{archivos que se modifican}}
- **Crea**: {{archivos que se crean}}
- **NO toca**: {{archivos que NO se deben tocar}}

### Rollback plan
<!-- ¿Cómo se revierte si algo sale mal? -->
1. `git checkout -- {{archivos modificados}}`
2. `rm {{archivos nuevos}}`
3. Verificar: `pytest harness/tests/ -q`

## 5. EXIT CRITERIA (Gates)

### Para marcar IN_PROGRESS → EVIDENCE
- [ ] Todos los FR implementados
- [ ] Todos los NF verificados
- [ ] Tests escritos y pasando

### Para marcar EVIDENCE → REVIEW
- [ ] T1 checks pasan (lint + test + security)
- [ ] T2 checks pasan (coverage + mutation)
- [ ] Evidencia documentada en este archivo

### Para marcar REVIEW → DONE
- [ ] Review aprobado (humano o LLM-judge)
- [ ] Sin regressions en T3
- [ ] Changelog actualizado (si aplica SVE)

### Para marcar FAILED
- [ ] Causa raíz documentada (ERR: WHAT+WHY+WHERE)
- [ ] Failure registrado en `harness/db/failures.jsonl`
- [ ] Skill derivado identificado (si aplica)

## 6. FEEDBACK (Iteration Loop)

### Lecciones aprendidas
<!-- Se llena DESPUÉS de completar la tarea -->
- **Qué funcionó**: {{description}}
- **Qué no funcionó**: {{description}}
- **Skill derivado**: {{nombre del skill o "ninguno"}}
- **Tiempo real vs estimado**: {{real}} / {{estimado}}

### Métricas
- Lines added: {{n}}
- Lines removed: {{n}}
- Files modified: {{n}}
- Tests added: {{n}}
- Coverage delta: {{+/- porcentaje}}

## 7. APPROVAL

### Gate voting (orchestrator pattern)
- [ ] Builder: {{aprobado/rechazado}} — {{razón}}
- [ ] Guardian: {{aprobado/rechazado}} — {{razón}}
- [ ] Scientist: {{aprobado/rechazado}} — {{razón}}

### Final decision
- **Status**: {{DONE / FAILED / BLOCKED}}
- **Blocked by**: {{reason o "none"}}
- **Next action**: {{siguiente tarea o "none"}}
