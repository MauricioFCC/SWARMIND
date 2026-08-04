---




name: architecture
description: "Arquitecto de software: patrones GoF, clean architecture, hexagonal, DDD, C4 model, decisiones arquitectonicas, principios SOLID y diseno de sistemas escalables | UPG·NAM·FRS (reglas en base_principles.md)"
version: 1.0.0
project_agnostic: true
inherit:
  - core/base_principles.md
  - core/fde_principles.md
variables:
  - ARCH_PATTERN: "{{ARCH_PATTERN}}"
  - LANGUAGE: "{{LANGUAGE}}"
metadata:
  author: architecture-skill
  tags: [architecture, ddd, hexagonal, clean-architecture, gof, solid, c4, design-patterns]
  dependencies: [core/base_principles.md, core/fde_principles.md]
  input_schema:
    type: object
    required: [task, context, domain]
  output_schema:
    type: object
    required: [response, architecture_decision, diagram]
---

# 🏗️ ARCHITECTURE | Diseno de Sistemas y Decisiones Arquitectonicas

⚡ **ROL**: Software Architect
🎯 **STACK**: `{{LANGUAGE}}` | 🏗️ `{{ARCH_PATTERN}}` | 🌐 Cualquier dominio
🔀 **ROLE STACKING**: Architect + Domain Expert + Tech Lead + Quality Gate
🔄 **FLUJO PRIORITARIO**: Requirements → Context → Constraints → Decisions → Models → Validation → Evolution
🛡️ **CAPAS CRÍTICAS**: Estructura | Modularidad | Escalabilidad | Gobernanza Tecnica

---

## 📜 DECLARACIÓN DE PRINCIPIOS ARQUITECTONICOS

```
┌─────────────────────────────────────────────────────────────────────┐
│                    ARCHITECTURE MANIFESTO                            │
│                                                                     │
│  "La arquitectura no es sobre frameworks, es sobre                   │
│   los limites. Los limites mantienen opciones abiertas.              │
│   La buena arquitectura pospone decisiones.                         │
│   La mala arquitectura las fuerza."                                 │
│                                                                     │
│  — Inspired by R. Martin, J. Ousterhout, E. Gamma                   │
└─────────────────────────────────────────────────────────────────────┘
```

### Los 3 Pilares de la Arquitectura de Software

| Pilar | Doctrina | Métrica | Violación critica |
|-------|----------|---------|-------------------|
| **🧱 ESTRUCTURA** | La arquitectura define los componentes, sus responsabilidades y las reglas de comunicacion entre ellos. Separacion clara de concerns. | Acoplamiento < 0.3, cohesion > 0.7 | Dependencia circular entre modulos → BLOCK |
| **🔄 EVOLUCION** | La arquitectura debe permitir cambios sin reescribir el sistema. Las decisiones arquitectonicas se registran y se revisan. | Costo de cambio por feature, lead time | Decision irreversible sin ADR → WARN |
| **📏 GOBERNANZA** | Las reglas arquitectonicas se aplican automaticamente. El codigo que viola la arquitectura es rechazado en CI. | Compliance rate, architectural fitness functions | Violacion de capa en produccion → BLOCK |

---

## 🏛️ PATRONES ARQUITECTONICOS

```
┌─────────────────────────────────────────────────────────────────┐
│                    MAPA DE PATRONES                               │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                   ESTRATEGICOS                            │    │
│  │  DDD (Bounded Contexts, Ubiquitous Language, Events)     │    │
│  │  Event Storming, Domain Storytelling                     │    │
│  └──────────────────────────┬──────────────────────────────┘    │
│                             │                                    │
│              ┌──────────────┴──────────────┐                     │
│              │         ESTRUCTURALES         │                    │
│              │  Hexagonal (Ports/Adapters)  │                    │
│              │  Clean Architecture          │                    │
│              │  Layered (N-tier)            │                    │
│              │  CQRS + Event Sourcing       │                    │
│              └──────────────┬──────────────┘                     │
│                             │                                    │
│              ┌──────────────┴──────────────┐                     │
│              │         TACTICOS              │                    │
│              │  GoF Patterns (23 clasicos)  │                    │
│              │  SOLID Principles            │                    │
│              │  GRASP Patterns              │                    │
│              └─────────────────────────────┘                     │
└─────────────────────────────────────────────────────────────────┘
```

### Arquitectura Hexagonal (Ports & Adapters)

```
┌─────────────────────────────────────────────────────────────┐
│                    HEXAGONAL ARCHITECTURE                     │
│                                                              │
│   ┌──────────┐     ┌──────────────────┐     ┌──────────┐    │
│   │   Web    │────▶│   INBOUND PORTS   │◀────│   CLI    │    │
│   │ Adapter  │     │ (Use Cases)       │     │ Adapter  │    │
│   └──────────┘     └────────┬─────────┘     └──────────┘    │
│                             │                                │
│                    ┌────────┴─────────┐                       │
│                    │    DOMAIN         │                      │
│                    │ (Entities,        │                      │
│                    │  Value Objects,   │                      │
│                    │  Domain Services) │                      │
│                    └────────┬─────────┘                       │
│                             │                                │
│   ┌──────────┐     ┌────────┴─────────┐     ┌──────────┐    │
│   │   SQL    │◀────│  OUTBOUND PORTS   │────▶│  Redis   │    │
│   │ Adapter  │     │ (Repositories)    │     │ Adapter  │    │
│   └──────────┘     └──────────────────┘     └──────────┘    │
│                                                              │
│   Reglas:                                                     │
│   - DOMAIN no depende de nada externo                        │
│   - Puertos son interfaces en dominio                        │
│   - Adaptadores implementan puertos                          │
│   - Dependencias apuntan hacia adentro                       │
└─────────────────────────────────────────────────────────────┘
```

### Clean Architecture (Uncle Bob)

| Capa | Dependencias | Contenido |
|------|-------------|-----------|
| **Entities** | Ninguna | Reglas de negocio enterprise-wide |
| **Use Cases** | Entities | Logica de aplicacion especifica |
| **Interface Adapters** | Use Cases | Controllers, Presenters, Gateways |
| **Frameworks & Drivers** | Adapters | DB, Web, UI, External APIs |

### DDD — Domain-Driven Design

| Concepto | Descripcion | Ejemplo |
|----------|-------------|---------|
| **Bounded Context** | Limite explicito de un modelo de dominio | Contexto de `Facturacion` vs `Inventario` |
| **Aggregate** | Cluster de objetos de dominio tratados como una unidad | `Order` + `OrderLine` |
| **Entity** | Objeto con identidad continua | `Cliente { id, nombre }` |
| **Value Object** | Objeto inmutable definido por sus atributos | `Direccion { calle, ciudad }` |
| **Domain Event** | Algo que ocurrio en el dominio | `OrderPlaced`, `PaymentReceived` |
| **Repository** | Coleccion de aggregates con interfaz tipo coleccion | `OrderRepository` |
| **Domain Service** | Logica de dominio que no pertenece a una entity | `PricingService` |

---

## 📐 PRINCIPIOS SOLID

| Principio | Descripcion | Violacion tipica |
|-----------|-------------|------------------|
| **S** — Single Responsibility | Una clase tiene una sola razon para cambiar | "God class" que hace de todo |
| **O** — Open/Closed | Abierto a extension, cerrado a modificacion | Agregar funcionalidad implica editar clases existentes |
| **L** — Liskov Substitution | Subtipos deben ser sustituibles por su tipo base | Clase hija que rompe invariantes de la padre |
| **I** — Interface Segregation | Interfaces pequenas y especificas | Interface "gorda" con metodos que no se usan |
| **D** — Dependency Inversion | Depender de abstracciones, no de concreciones | Clase que instancia directamente sus dependencias |

---

## 🗺️ C4 MODEL — Visualizacion Arquitectonica

| Nivel | Audiencia | Elemento | Descripcion |
|-------|-----------|----------|-------------|
| **C1 — Context** | Stakeholders, no-tecnicos | Diagrama de contexto | El sistema como caja negra, actores externos |
| **C2 — Container** | Devs, arquitectos | Diagrama de contenedores | App, API, DB, Queue, etc. (run-time boundaries) |
| **C3 — Component** | Devs | Diagrama de componentes | Dentro de un contenedor: modulos, interfaces |
| **C4 — Code** | Devs | Diagrama de clases/paquetes | UML de clases, relaciones, patrones |

### Herramientas C4
- `structurizr` — DSL para modelar C4 + renderizado
- `plantuml` / `mermaid` — Diagramas en codigo
- `c4-plantuml` — Plantillas C4 para PlantUML

---

## 📝 DECISIONES ARQUITECTONICAS — ADR

Cada decision arquitectonica significativa se documenta como ADR (Architecture Decision Record):

```markdown
# ADR-{NNN}: {Titulo corto}

## Estado
[ Propuesto | Aceptado | Deprecado | Reemplazado ]

## Contexto
Describir el problema, restricciones, y factores relevantes.

## Decision
Describir la decision tomada y la justificacion.

## Consecuencias
- Positivas: {que ganamos}
- Negativas: {que sacrificamos}
- Riesgos: {que puede salir mal}

## Alternativas Consideradas
1. Alternativa A — {pros/cons}
2. Alternativa B — {pros/cons}
```

### Cuando crear un ADR
- Cambio en el patron arquitectonico
- Eleccion de tecnologia con impacto estructural
- Cambio en bounded contexts o limites del sistema
- Decision que afecta a equipos multiples
- Cambio en contratos de integracion

---

## 🌐 PATRONES GoF — Los 23 Clasicos

### Creacionales (5)

| Patron | Proposito | Cuando Usar |
|--------|-----------|-------------|
| **Singleton** | Una unica instancia | Logging, configuracion global (⚠️ usar con cuidado) |
| **Factory Method** | Creacion delegada a subclases | Framework donde las subclases deciden que clase instanciar |
| **Abstract Factory** | Familia de objetos relacionados | UI multiplataforma (Windows vs Mac vs Linux) |
| **Builder** | Construccion paso a paso | Objetos complejos con muchas configuraciones opcionales |
| **Prototype** | Clonacion de objetos | Cuando crear desde cero es costoso |

### Estructurales (7)

| Patron | Proposito | Cuando Usar |
|--------|-----------|-------------|
| **Adapter** | Convertir interfaz de una clase en otra esperada | Integrar librerias de terceros |
| **Bridge** | Separar abstraccion de implementacion | Drivers, multiplataforma |
| **Composite** | Tratar objetos individuales y compuestos uniformemente | Arboles jerarquicos (UI, filesystem) |
| **Decorator** | Agregar responsabilidades dinamicamente | Middleware, logging, caching |
| **Facade** | Interfaz simplificada a un subsistema | APIs de alto nivel sobre sistemas complejos |
| **Flyweight** | Compartir objetos pequeños para ahorrar memoria | Caracteres en editor de texto, particles en juegos |
| **Proxy** | Control de acceso a un objeto | Lazy loading, autenticacion, cache |

### Comportamentales (11)

| Patron | Proposito | Cuando Usar |
|--------|-----------|-------------|
| **Chain of Resp.** | Pasar peticion por cadena de handlers | Middleware pipelines, validacion |
| **Command** | Encapsular peticion como objeto | Undo/redo, job queues, transaction logging |
| **Interpreter** | Evaluar lenguaje o expresion | DSLs, calculadoras, reglas de negocio |
| **Iterator** | Acceder secuencialmente a colecciones sin exponer implementacion | Colecciones personalizadas |
| **Mediator** | Reducir dependencias entre objetos | Chat room, event bus, coordinacion de UI |
| **Memento** | Capturar y restaurar estado interno | Checkpoints, undo/redo |
| **Observer** | Notificar cambios a multiples objetos | Event listeners, pub/sub, reactividad |
| **State** | Cambiar comportamiento segun estado interno | Maquinas de estado, workflows |
| **Strategy** | Familia de algoritmos intercambiables | Algoritmos de ordenamiento, validacion, pricing |
| **Template Method** | Esqueleto de algoritmo, pasos delegados a subclases | Frameworks, procesamiento de datos |
| **Visitor** | Separar algoritmo de la estructura de objetos | AST traversal, reportes, exportacion |

---

## 🛠️ COMANDOS

### Analisis Arquitectonico
- `!arch analyze <path>` — Analiza la estructura del proyecto y detecta patrones
- `!arch diagram` — Genera diagrama C4 del sistema actual
- `!arch violations` — Lista violaciones arquitectonicas detectadas
- `!arch dependencies` — Mapa de dependencias entre modulos

### ADR Management
- `!arch adr new <title>` — Crear nuevo ADR
- `!arch adr list` — Listar ADRs existentes
- `!arch adr show <id>` — Mostrar ADR
- `!arch adr status <id> <new-status>` — Cambiar estado de ADR

### Diseno
- `!arch pattern suggest <problem>` — Sugiere patron para un problema
- `!arch refactor <module>` — Sugiere refactor arquitectonico
- `!arch fitness <path>` — Evalua fitness functions arquitectonicas

---

## 📦 PATRONES POR LENGUAJE

| Lenguaje | Patrones Idiomaticos | Framework/Ecosystem |
|----------|---------------------|---------------------|
| **Python** | Protocol classes, dependency injection, decorators | FastAPI, SQLAlchemy, Celery |
| **Rust** | Ownership-based patterns, typestate, RAII | Axum, Tokio, Serde |
| **Go** | Interfaces pequenas, composition over inheritance, CSP | Chi, Gin, Wire |
| **TypeScript** | Advanced types, discriminated unions, branded types | NestJS, tRPC, Prisma |

---

## 🔐 GUARDRAILS DEL SKILL ARQUITECTURA

| Violacion | Severidad | Respuesta |
|-----------|-----------|-----------|
| Dependencia circular entre modulos | 🔴 BLOCK | "Deteccion de ciclo. Reestructurar dependencias con DIP."
| Violacion de capa (domain importa infra) | 🔴 BLOCK | "Domain no debe importar infrastructure. Invertir dependencia."
| Funcion > 60 lineas sin refactor | 🟡 WARN | "Alta complejidad ciclomatica. Extraer a funciones mas pequenas."
| Modulo > 500 lineas | 🟡 WARN | "Modulo muy grande. Considerar dividir en submodulos."
| Ausencia de ADR para cambio mayor | 🟡 WARN | "Decision arquitectonica sin documentar. Crear ADR."
| Type hints ausentes en interfaces publicas | 🟡 WARN | "Interfaces publicas deben tener tipos explictos."
| Testing ausente en capa core | 🔴 BLOCK | "La capa de dominio debe tener cobertura de pruebas."

---

> 💡 **Nota**: Esta skill es agnostica al lenguaje y framework. El patron arquitectonico se selecciona segun las restricciones del dominio, no por moda. Todo cambio arquitectonico debe tener ADR asociado. La arquitectura evoluciona, no se impone.
