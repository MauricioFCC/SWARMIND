# architecture — Advanced

> Detalle operativo y avanzado.

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

