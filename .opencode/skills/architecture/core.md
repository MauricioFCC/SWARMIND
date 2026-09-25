# architecture — Core

> Fundamentos. Detalle en `advanced.md`.

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

