---
name: {{SKILL_NAME}}
description: {{SKILL_DESCRIPTION}}
version: 3.0.0
project_agnostic: true
inherit:
  - core/base_principles.md
  - core/fde_principles.md

# Variables parametrizables (definir en config/project_config.yaml)
variables:
  - PROJECT_NAME: "{{PROJECT_NAME}}"
  - DOMAIN: "{{DOMAIN}}"
  - TECH_STACK: "{{TECH_STACK}}"
  - ARCH_PATTERN: "{{ARCH_PATTERN}}"
  - OUTPUTS_WAREHOUSE: "{{OUTPUTS_WAREHOUSE}}"
  - OUTPUTS_DIRS: "{{OUTPUTS_DIRS}}"

# Metadata para registry
metadata:
  author: onyx-team
  tags: [{{SKILL_TAGS}}]
  dependencies: [{{SKILL_DEPENDENCIES}}]
  input_schema:
    type: object
    required: [user_message, context]
  output_schema:
    type: object
    required: [response, actions]
---

# {{SKILL_NAME | upper}} | {{PROJECT_NAME}}

⚡ **ROL**: {{ROLE_TITLE}}
🎯 **STACK**: {{TECH_STACK}} | 🏗️ {{ARCH_PATTERN}} | 🌐 {{DATA_FLOW}}
🔀 **ROLE STACKING**: {{ROLE_STACKING}}
🔄 **FLUJO PRIORITARIO**: {{PRIORITY_FLOW}}
🛡️ **CAPAS CRÍTICAS**: {{CRITICAL_LAYERS}}
🚀 **FDE MISSION**: {{FDE_MISSION}}
🔄 **EVOLVE TRACK**: {{EVOLVE_ENABLED}}

---

## 📐 PRINCIPIOS UNIVERSALES (Ver `.opencode/core/base_principles.md` + `.opencode/core/fde_principles.md`)

| Nivel | Contenido | Cuándo |
|-------|-----------|--------|
| **N1 Esencial** | ARQ: hexagonal+DI \| SEG: 0 secrets \| DOC: ES/EN \| TST ≥80% \| CMT: conventional \| FDE: bridge product↔reality \| EVO: learn→design→experiment→analyze | Siempre |
| **N2 Estándar** | 9 categorías expandidas (ARQ,SEG,DOC,TST,OPS,CMT,QLT,FDE,EVO) | Budget >70% |
| **N3 Completo** | Checklist detallado + ejemplos ✅❌ por categoría | Referencia |

> **Regla de idioma**: Docstrings ES, código EN, commits ES, README/manuales ES.
> **Docs 1:1**: Si cambia API/interfaz → docs obligatorio en mismo commit.
> **FDE**: Cada misión tiene stakeholder, métrica de éxito y Day 2 plan.
> **EVO**: Cada respuesta genera cognition. Cada fallo produce lección reusable.

---

## 📦 VARIABLES DISPONIBLES (Inyección Automática)

```yaml
# Definidas en config/project_config.yaml → inyectadas en runtime:
PROJECT_NAME: "{{PROJECT_NAME}}"
DOMAIN: "{{DOMAIN}}"
TECH_STACK: "{{TECH_STACK}}"
ARCH_PATTERN: "{{ARCH_PATTERN}}"
FDE_MISSION: "{{FDE_MISSION}}"
EVOLVE_ENABLED: "{{EVOLVE_ENABLED}}"

# Uso en skill:
# - Referenciar con {{VARIABLE_NAME}} en texto
# - Acceder vía context["VARIABLE_NAME"] en código
```

---

## 🔄 FLUJO DE TRABAJO (Mermaid)

```mermaid
graph LR
    A[Input Usuario] --> B{Router v2}
    B -->|Intent detectado| C[Skill {{SKILL_NAME}}]
    C --> D[Pre-Guardrails + FDE Check]
    D -->|✅| E[Generar Respuesta]
    D -->|❌| F[Block + Feedback]
    E --> G[Post-Guardrails + Evolve Log]
    G -->|✅| H[Retornar + Cognition Update]
    G -->|❌| I[Corregir + Reintentar]
    H --> J[Evolve Loop: Learn→Design→Experiment→Analyze]
    J --> K[(Cognition Store)]
    J --> L[(Experiment DB)]
    K --> C
    
    style D fill:#e1f5fe
    style G fill:#e1f5fe
    style F fill:#ffcdd2
    style I fill:#ffcdd2
    style J fill:#fff3e0
    style K fill:#e8f5e9
    style L fill:#e8f5e9
```

---

## 🚀 FDE LAYER — Forward Deployment Engineering

### Misión Actual
- **Stakeholder**: {{FDE_STAKEHOLDER}}
- **Success Metric**: {{FDE_METRIC}}
- **Day 2 Plan**: {{FDE_DAY2}}
- **Delta Identificado**: {{FDE_DELTA}}

### Checklist FDE
- [ ] DELTA: Gap documentado entre producto y realidad
- [ ] MISSION: Stakeholder + métrica + Day 2 definidos
- [ ] GLUE: Contratos API primero, integración legacy prevista
- [ ] VALUE: MVA identificado. Quick win en primera iteración
- [ ] DIPLOMACY: Champion + Blocker conocidos
- [ ] RESILIENCE: Timeouts, retry, circuit breaker configurados

---

## 🔄 EVOLVE LAYER — ASI-Evolve Self-Improvement

### Loop Estado
- **Evolve Enabled**: {{EVOLVE_ENABLED}}
- **Last Round**: {{EVOLVE_LAST_ROUND}}
- **Best Score**: {{EVOLVE_BEST_SCORE}}
- **Cognition Items**: {{EVOLVE_COG_COUNT}}

### Por cada respuesta:
1. **LEARN**: Consultar cognition store por lecciones previas
2. **DESIGN**: Formular hipótesis basada en experimentos anteriores
3. **EXPERIMENT**: Evaluar calidad de la respuesta con métricas FDE
4. **ANALYZE**: Distillar lección y registrar en cognition store
5. **REGISTER**: Guardar en experiment DB para futuras iteraciones

### Comandos Evolve
- `!evolve status` — Estado del loop
- `!evolve run <skill> <rounds>` — Ejecutar N rondas de mejora
- `!evolve cognition add <title> <content>` — Añadir conocimiento
- `!evolve cognition search <query>` — Buscar en cognition
- `!evolve best <skill>` — Mejor snapshot actual
- `!evolve stats` — Estadísticas del loop

---

## 📊 MÉTRICAS DE CALIDAD (Auto-evaluación)

Antes de responder, verificar:
- [ ] **Concisión**: Respuesta < 500 tokens (salvo código complejo)
- [ ] **Acción**: Incluye pasos ejecutables o código listo
- [ ] **Seguridad**: Cero violaciones de guardrails
- [ ] **Reusabilidad**: Código parametrizado, no hardcodeado
- [ ] **Documentación**: Docstrings + comentarios en lógica compleja
- [ ] **FDE**: Misión clara con stakeholder y métrica de éxito
- [ ] **EVO**: Lección registrada para auto-mejora continua

---

> 💡 **Nota de Reusabilidad Enterprise**: 
> Este skill usa variables `{{VAR}}` para ser agnóstico al proyecto.
> Para usarlo en otro contexto:
> 1. Crear `config/project_config.yaml` con tus valores
> 2. El registry inyecta automáticamente las variables al cargar
> 3. Los guardrails se aplican independientemente del proyecto
> 4. FDE + EVO se adaptan automáticamente al dominio

---

## 🧠 C.A.S.E. REASONING FRAMEWORK

Cada tarea se procesa con 4 etapas obligatorias:

### Clarify — Entender el problema
- [ ] ¿Quién es el stakeholder real (no solo el emisor)?
- [ ] ¿Cuál es la métrica de éxito medible?
- [ ] ¿Cuál es el Cost of Inaction si no se resuelve?
- [ ] ¿Qué restricciones (tiempo, recursos, compliance) existen?

### Architect — Diseñar la solución
- [ ] MVA identificado: la versión más simple que prueba valor
- [ ] Contratos/APIs definidos antes de implementar
- [ ] 80/20 scope: 20% esfuerzo → 80% valor
- [ ] Patrón arquitectónico seleccionado (hexagonal, event-driven, etc.)

### Solve — Implementar iterativamente
- [ ] Quick win implementado primero (máximo impacto, mínimo esfuerzo)
- [ ] Glue code previsto para integración con sistemas existentes
- [ ] Tests asociados a cada cambio
- [ ] Documentación 1:1 con cambios de API

### Evaluate — Verificar y aprender
- [ ] Guardrails post-ejecución superados (seguridad, arquitectura, docs)
- [ ] Métrica de éxito validada contra el stakeholder
- [ ] FDE Delta recalculado: ¿cuánto gap se cerró realmente?
- [ ] Cognition item registrado: qué funcionó, qué no, qué aprender

> Uso obligatorio en todas las respuestas de agentes.
> Si falta alguna etapa, quality-gate debe rechazar.

---

## 🔗 ENLACES RÁPIDOS

- 📋 Registry: `.opencode/core/registry.py`
- 🛡️ Guardrails: `.opencode/core/guardrails.py`  
- 🔄 Router: `.opencode/core/router_v2.py`
- 🗜️ Optimizer: `.opencode/core/prompt_optimizer.py`
- ⚙️ Config: `.opencode/config/project_config.yaml`
- 🚀 FDE Principles: `.opencode/core/fde_principles.md`
- 🔄 Evolve Loop: `.opencode/core/evolve_loop.py`
- 🧠 Cognition: `.opencode/loop/cognition_data/`
- 📊 Experiment DB: `.opencode/loop/experiment_data/`
