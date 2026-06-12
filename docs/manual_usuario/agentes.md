# Guía de Agentes

!!! tip "Delegación Inteligente"

    Los agentes de Onyx se activan mediante la sintaxis `@rol: mensaje`.
    La delegación directa ahorra tokens al evitar que el sistema interprete
    la intención mediante NLP — usas el enrutamiento explícito del grafo.

---

## Sintaxis de Delegación

### Delegación Directa

La forma más eficiente de interactuar con los agentes:

```
@<nombre-del-agente>: <tu-instrucción>
```

**Ejemplos:**

```
@software-engineer: Implementa el endpoint POST /usuarios con validación Pydantic
@security-engineer: Revisa el módulo de autenticación por vulnerabilidades
@risk-manager: Calcula position sizing para una cartera de 100k con Kelly criterion
```

!!! tip "Ahorro de Tokens"

    Si ya sabes exactamente qué agente necesitas, **saltea al Project Manager**
    y delega directamente al especialista. Esto ahorra ~500 tokens por consulta
    que el PM gastaría en analizar y sub-delegar.

### Delegación Multi-Agente

Puedes encadenar agentes en una misma instrucción:

```
@project-manager: Planifica el módulo de pagos. Delega el schema a @data-architect,
la implementación a @software-engineer, y la seguridad a @security-engineer.
```

### Delegación con Contexto C.A.S.E.

Para obtener resultados más precisos, estructura tu instrucción siguiendo el
formato C.A.S.E. (Clarify → Architect → Solve → Evaluate):

```
@software-engineer:
C: Necesito un endpoint para crear usuarios con roles
A: Usar FastAPI + Pydantic + JWT. Sin dependencias externas.
S: Implementa solo el endpoint POST /usuarios y los tests unitarios
E: Verifica cobertura >=80% y que pase los security gates
```

---

## Lista Completa de Agentes con @rol

### Agentes de Evolución

| @rol | Descripción | Cuándo Usarlo |
|------|-------------|---------------|
| `@evolve-researcher` | Investiga oportunidades de mejora continua | Para analizar cognition store y proponer optimizaciones |
| `@evolve-engineer` | Ejecuta mejoras mediante evolución genética | Para aplicar mutaciones y generar nuevas versiones de skills |
| `@evolve-analyzer` | Evalúa resultados y destila lecciones | Para analizar experimentos y promover best snapshots |

### Agentes de Desarrollo

| @rol | Descripción | Cuándo Usarlo |
|------|-------------|---------------|
| `@software-engineer` | Desarrollo full-stack, APIs, servicios | Para implementar endpoints, refactorizar código, configurar CI/CD |
| `@frontend-engineer` | Dashboards, UI, visualizaciones | Para crear interfaces de usuario o paneles de monitoreo |
| `@mobile-engineer` | Apps iOS/Android, offline-first | Para desarrollar apps móviles o features específicas de mobile |
| `@data-architect` | Schemas, modelos, ETL, migraciones | Para diseñar bases de datos o pipelines de datos |
| `@devops-sre` | Infraestructura, Docker, K8s, CI/CD | Para configurar deploy, monitoreo, o infraestructura cloud |

### Agentes de Seguridad y Calidad

| @rol | Descripción | Cuándo Usarlo |
|------|-------------|---------------|
| `@security-engineer` | AppSec, hardening, compliance | Para auditorías de seguridad, revisión de vulnerabilidades |
| `@quality-gate` | Testing, cobertura, pre-commit gates | Para validar código antes de commit o diseñar test strategy |
| `@requirements-analyst` | Análisis de requerimientos | Para evaluar viabilidad de nuevas features o mejoras |

### Agentes Cuantitativos

| @rol | Descripción | Cuándo Usarlo |
|------|-------------|---------------|
| `@quant-developer` | Estrategias de trading, ejecución | Para implementar estrategias, conectar brokers, ejecutar señales |
| `@quant-scientist` | Validación estadística, experimentos | Para investigación cuantitativa, feature engineering, backtesting |
| `@risk-manager` | Gestión de riesgo, position sizing | Para calcular Kelly criterion, drawdown, o límites de exposición |

### Agentes Estratégicos

| @rol | Descripción | Cuándo Usarlo |
|------|-------------|---------------|
| `@project-manager` | Orquestación, planificación | Para planificar proyectos, delegar tareas, coordinar equipos |
| `@enterprise-architect` | Arquitectura, ADR, roadmaps | Para decisiones arquitectónicas o diseño de sistemas |
| `@documentation-specialist` | Documentación técnica | Para crear o actualizar manuales, API docs, white papers |

### Agentes de IA y Herramientas

| @rol | Descripción | Cuándo Usarlo |
|------|-------------|---------------|
| `@ai-engineer` | ML/AI, LLMOps, RAG | Para implementar modelos ML, optimizar inferencia, diseñar prompts |
| `@context-engineer` | Optimización de contexto | Para compactar prompts, diseñar memoria, optimizar tokens |
| `@tool-mcp-engineer` | Herramientas MCP | Para crear o mantener el ecosistema de tools de los agentes |

### Agente de Operaciones

| @rol | Descripción | Cuándo Usarlo |
|------|-------------|---------------|
| `@trading-operations` | Monitoreo en vivo, alertas | Para operaciones de trading en producción, schedules, conectividad |

---

## Tabla de Referencia Rápida

### Por Tarea Común

| Tarea | Agente Recomendado | Ejemplo |
|-------|-------------------|---------|
| Crear endpoint REST | `@software-engineer` | `@software-engineer: Crea POST /productos con validación` |
| Diseñar schema DB | `@data-architect` | `@data-architect: Diseña esquema para módulo de ventas` |
| Revisar seguridad | `@security-engineer` | `@security-engineer: Audita el módulo de pagos` |
| Calcular riesgo | `@risk-manager` | `@risk-manager: Calcula posición para MNQ con Kelly 0.25` |
| Validar estrategia | `@quant-scientist` | `@quant-scientist: Valida estrategia de momentum, OOS 30%` |
| Crear dashboard | `@frontend-engineer` | `@frontend-engineer: Crea dashboard de monitoreo en vivo` |
| Configurar CI/CD | `@devops-sre` | `@devops-sre: Configura pipeline de deploy automático` |
| Documentar API | `@documentation-specialist` | `@documentation-specialist: Documenta endpoints de autenticación` |
| Analizar feature | `@requirements-analyst` | `@requirements-analyst: Analiza viabilidad de módulo multi-moneda` |
| Planificar proyecto | `@project-manager` | `@project-manager: Planifica release v2.0` |
| Mejorar skill | `@evolve-researcher` | `@evolve-researcher: Encuentra mejoras para software-engineer` |

### Por Prioridad de Tokens

| Perfil de Uso | Estrategia | Ejemplo |
|---------------|------------|---------|
| **Budget ajustado** | Delegación directa al especialista | `@quant-developer: ...` (sin pasar por PM) |
| **Budget normal** | Delegación con contexto C.A.S.E. | `@software-engineer: C:... A:... S:... E:...` |
| **Budget amplio** | Flujo multi-agente con PM | `@project-manager: Planifica y delega...` |
| **Tarea simple** | Máxima compresión, agente directo | `@devops-sre: docker-compose up -d` |

---

## Mejores Prácticas

### 1. Sé Específico

!!! example "Comparación"

    **❌ Malo:** `@software-engineer: Hazme un backend`
    
    **✅ Bueno:** `@software-engineer: Implementa endpoint GET /productos/{id} con FastAPI,
    que devuelva JSON con nombre, precio y stock. Incluye validación de que id sea UUID.`

### 2. Incluye Restricciones

Las restricciones evitan que el agente tome decisiones subóptimas:

```
@software-engineer: Implementa el módulo de facturación.
REQUISITOS:
- Usar SOLO librerías estándar de Python
- Sin dependencias externas
- Output en JSON
- Timeout máximo 30s por request
```

### 3. Usa la Memoria del Sistema

No repitas contexto que el sistema ya conoce:

```
# En lugar de explicar todo el proyecto:
!evolve cognition search "facturación estructura"
# Luego:
@software-engineer: Basado en la cognition store, agrega validación fiscal al endpoint de facturas
```

### 4. Scaffolding Primero

Para tareas grandes, genera el esqueleto antes del código completo:

```
@software-engineer: Genera SOLO las interfaces y firmas de métodos para el
módulo de facturación. Sin implementación. Quiero validar la estructura primero.
```

### 5. Micro-Gestión para Budgets Ajustados

En entornos con presupuesto limitado (planes free/zen), delega directamente
al especialista sin pasar por el PM:

| Tú quieres... | En lugar de... | Haz esto directo |
|---------------|---------------|------------------|
| Un schema DB | `@project-manager: Diseña la DB` | `@data-architect: Crea el schema` |
| Un endpoint | `@project-manager: Implementa API` | `@software-engineer: Crea el endpoint` |
| Un test | `@project-manager: Valida calidad` | `@quality-gate: Diseña tests` |

---

## Referencias

- [Lista completa de agentes](../dominios_negocio/sistema-agentes.md)
- [Referencia CLI](cli.md)
- [Project Manager Agent](https://github.com/onyx-project/onyx/blob/main/.opencode/agents/project-manager.md)
