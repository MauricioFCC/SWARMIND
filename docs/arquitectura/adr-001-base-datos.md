# ADR-001: LanceDB como Almacenamiento Unificado

- **Estado:** Aceptado
- **Fecha:** 2025-11-15
- **Decisores:** Equipo de Arquitectura, Enterprise Architect
- **Última actualización:** 2026-06-11

---

## Contexto

El sistema multi-agente necesita un almacenamiento que cumpla con tres requisitos
fundamentales:

1. **Almacenamiento vectorial** para búsqueda semántica (RAG sobre memoria de agentes)
2. **Metadatos estructurados** para esquemas de tareas, estados de ejecución y grafo de transiciones
3. **Zero-configuration** para desarrollo local y despliegues ligeros

Inicialmente se consideró **SQLite** para los metadatos, combinado con un índice vectorial
separado (FAISS/Pinecone). Sin embargo, esta aproximación introducía complejidad operativa
(sincronización entre motores, manejo de transacciones distribuidas) y sobrecarga de
mantenimiento.

### Problemas identificados con SQLite + FAISS

| Problema | Impacto |
|----------|---------|
| Dos motores de almacenamiento | Mayor superficie de fallo |
| Sincronización manual | Riesgo de inconsistencia de datos |
| Sin búsqueda híbrida nativa | Consultas complejas requieren unión manual |
| FAISS en memoria | Consumo de RAM innecesario |

---

## Decisión

Se adopta **LanceDB** como almacenamiento unificado para todos los datos del sistema,
reemplazando tanto SQLite como FAISS.

### ¿Qué es LanceDB?

LanceDB es una base de datos vectorial **embebida** (sin servidor) construida sobre
el formato **Apache Lance**, que utiliza **Apache Arrow** para representación de datos
en memoria. No requiere infraestructura externa — se almacena como una carpeta local.

### Colecciones Implementadas

| Colección | Propósito | Schema |
|-----------|-----------|--------|
| `tasks_board` | Estado de tareas y requerimientos | Metadatos (estado, agente, prioridad) + embedding semántico |
| `rag_chunks` | Memoria del código base | Chunks de código/documentación + vectores |
| `asi_cognition_store` | Aprendizaje del sistema | Lecciones, errores, métricas UCB1 |

### Estructura en el Proyecto

```
harness/
└── db/
    └── lancedb_store/       ← Carpeta embebida de LanceDB
        ├── tasks_board.lance
        ├── rag_chunks.lance
        └── asi_cognition_store.lance
```

!!! tip "Apache Arrow Nativo"

    LanceDB permite cargar colecciones directamente como DataFrames de Pandas o Polars
    **sin copias en memoria**, gracias a Apache Arrow. Esto es crítico para el `quant-scientist`
    y `evolve-analyzer` que necesitan procesar grandes volúmenes de datos de cognición.

---

## Consecuencias

### Positivas

1.  **Zero-config**: No requiere servidor, demonio ni configuración de red. La carpeta
    `lancedb_store/` se autogestiona.
2.  **Apache Arrow nativo**: Las colecciones se pueden leer como DataFrames de Pandas/Polars
    sin serialización intermedia. Ideal para agentes que procesan datos cuantitativos.
3.  **Búsqueda híbrida**: LanceDB soporta filtrado por metadatos + búsqueda vectorial
    en una sola consulta. Permite consultas como *"tráeme chunks de documentación sobre
    facturación creados después de enero"*.
4.  **Embedded**: No hay latencia de red. Todo corre en el mismo proceso.
5.  **Versionado de datos**: El formato Lance soporta versionado nativo de tablas,
    permitiendo rollback de cambios en la base de conocimiento.

### Negativas

1.  **No es una base de datos relacional**: Las consultas JOIN y transacciones ACID
    complejas no son nativas. Para el `tasks_board` se usa una aproximación de
    documento embebido (similar a MongoDB).
2.  **Ecosistema más pequeño**: Comparado con SQLite o PostgreSQL, la comunidad y
    herramientas disponibles son más limitadas.
3.  **Lock-in de formato**: Migrar a otra base de datos vectorial requeriría exportar
    los embeddings.

### Neutrales

- El almacenamiento embebido significa que no hay separación cliente-servidor.
  Esto es adecuado para un sistema de agentes que corre en un solo proceso,
  pero podría requerir reconsideración si se escala a múltiples nodos.

---

## Alternativas Consideradas

### SQLite + FAISS (Descartada)

| Aspecto | Evaluación |
|---------|------------|
| Ventaja | Madurez y familiaridad de SQLite |
| Desventaja | Dos sistemas separados, sincronización manual, sin búsqueda híbrida |

### PostgreSQL + pgvector (Descartada)

| Aspecto | Evaluación |
|---------|------------|
| Ventaja | Soporte transaccional completo |
| Desventaja | Requiere servidor PostgreSQL + extensión pgvector. Sobrecarga operativa innecesaria |

### Pinecone / Weaviate (Descartada)

| Aspecto | Evaluación |
|---------|------------|
| Ventaja | Búsqueda vectorial gestionada |
| Desventaja | Costo recurrente, latencia de red, dependencia externa. Violación del principio de air-gap readiness (FDE-RESILIENCE) |

---

## Diagrama de Flujo de Datos

```
┌──────────────┐     ┌──────────────────────────────────────────────┐
│   Agente     │     │              Harness                          │
│ (Solicita    │     │                                              │
│  contexto)   │────▶│  ┌────────────────┐     ┌─────────────────┐  │
└──────────────┘     │  │ Context        │────▶│   LanceDB       │  │
                     │  │ Assembler      │     │                 │  │
┌──────────────┐     │  │ (memory_rag/)  │     │ ┌─────────────┐ │  │
│   Agente     │     │  └────────────────┘     │ │ rag_chunks  │ │  │
│ (Guarda      │     │                         │ │ tasks_board │ │  │
│  cognición)  │────▶│  ┌────────────────┐     │ │ cognition   │ │  │
└──────────────┘     │  │ Evolve Loop    │────▶│ │             │ │  │
                     │  │ (evolve_loop/) │     │ └─────────────┘ │  │
                     │  └────────────────┘     └─────────────────┘  │
                     └──────────────────────────────────────────────┘
```

---

## Referencias

- [LanceDB Documentation](https://lancedb.github.io/lancedb/)
- [Apache Arrow Format](https://arrow.apache.org/)
- [FDE Principles - RESILIENCE Pillar](https://github.com/onyx-project/onyx/blob/main/.opencode/core/fde_principles.md)
- [Arquitectura del Sistema](index.md)
