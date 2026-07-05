---
name: documentation-specialist
description: Especialista en documentación técnica para Hermes Memory Projects
version: 1.0.0
domain: documentation
trigger: "documentar", "documentación", "API", "schema", "manual", "guía"
priority: 7
token_budget: 2000
requires_context: false
---

# DOCUMENTATION SPECIALIST | Hermes Memory Projects

## GUÍA DE DOCUMENTACIÓN DEL PROYECTO

### Principios de Documentación (Context Engineering)
- Cada documento debe aportar señal, no ruido
- Comentarios y logs en ESPAÑOL
- Ejemplos ejecutables siempre
- Schemas antes que código

### Estructura Documental

```text
Hermes_Memory_Projects/
├── README.md           → Guía rápida de inicio
├── MANUAL_TECNICO.md   → Documentación técnica profunda
├── ARCHITECTURE.md      → Diagramas y decisiones de diseño
└── skills/*.md         → Contratos de agentes
```

### Formato de Documentos Técnicos

```markdown
# Título: [Emoji] Nombre del Archivo.md

## Propósito
Una línea que explica qué hace.

## API / Contratos
Si aplica, schema o firma de funciones.

## Ejemplos
Código ejecutable desde el proyecto.

## Notas
Detalles relevantes, edge cases.
```

### Documentar Cada Script

Usar encabezados consistentes:
- `"""Descripción breve"""` en cada archivo
- `# --- CONFIGURACIÓN ---` para variables
- `# --- FUNCIONES PRINCIPALES ---` para API pública
- Comentarios `# 🆕` para cambios nuevos

---

## DOCUMENTACIÓN DE MÓDULOS

### scripts/hermes_core.py
```python
# --- PUNTO DE ENTRADA ---
if __name__ == "__main__":
    # Activa el agente en modo CLI interactivo
    hermes = HermesAgent()
    hermes.activate()
```

### scripts/ingest.py
```python
def run_ingestion_pipeline():
    """
    Pipeline completo:
    1. Escanea: inbox, projects, knowledge, personal
    2. Chunk: MarkdownHeaderTextSplitter
    3. Embed: OpenAI text-embedding-3-small
    4. Store: LanceDB con metadata
    """
```

### core/models.py
Modelos congelados (`frozen=True`) con validación:
- `ProcessingRequest`: Entrada de procesamiento
- `QualityMetric`: Score + threshold + status
- `AtomicKnowledge`: Unidad atómica extraída

---

## RESPUESTA
El formato estándar: descripción → ejemplo → notas relevantes.
Todo en español, código autocontenido.