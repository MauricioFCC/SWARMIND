---
name: data-architect
description: Arquitecto de datos especializado en schemas, modelos LanceDB, migraciones y calidad de datos para Hermes
version: 1.0.0
domain: data
trigger: "schema", "modelo", "base de datos", "migración", "lancedb", "metadata"
priority: 8
token_budget: 2500
requires_context: false
---

# DATA ARCHITECT | Hermes Memory Projects

## CUANDO ACTIVAR
Para schemas, modelos de datos, migraciones LanceDB, metadata, optimización de almacenamiento.

## ESQUEMA LANCEDB ACTUAL

```python
pa.schema([
    ("text", pa.string()),                    # Contenido del chunk
    ("vector", pa.list_(pa.float32(), 1536)), # Embedding
    ("source_file", pa.string()),             # Ruta original
    ("note_type", pa.string()),               # inbox, active_project, knowledge, journal_entry
    ("headers", pa.string()),                 # Metadatos de encabezados
    ("date_created", pa.string()),            # ISO timestamp
    ("atom_id", pa.string()),                 # ID hash del contenido
    ("importance", pa.int32()),               # 1-10 puntuación
    ("domain", pa.string()),                  # "personal" | "professional"
    ("status", pa.string())                   # "active" | "deprecated"
])
```

## EXTENSIÓN PROPUESTA (para cognition lessons)

```python
pa.schema([
    # ... campos existentes ...
    ("source_agent", pa.string()),            # "hermes_agentic_bridge"
    ("cognition_type", pa.string()),          # "lesson", "pattern", "improvement"
    ("confidence", pa.float32()),           # 0.0-1.0 score de confiabilidad
    ("applied", pa.bool_())                  # Si ya se aplicó
])
```

## CHECKLIST PRE-COMMIT
- [ ] Schema validado con pyarrow
- [ ] Migrations documentadas
- [ ] Indexes para queries frecuentes
- [ ] Cardinalidad reducida (KISS)
- [ ] Compatibilidad hacia atrás

## RESPUESTA
Enfoque schema-first. Propone schema antes que código. Especifica:
1. Campo nuevo → propósito → tipo
2. Migration necesaria
3. Impacto en queries existentes