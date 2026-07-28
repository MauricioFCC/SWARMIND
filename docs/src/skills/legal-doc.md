# legal-doc — Analisis Juridico

Skill especializado en procesamiento y analisis de documentos legales colombianos.

## Capacidades

| Capacidad | Descripcion | Tecnica |
|-----------|-------------|---------|
| **NER juridico** | Extrae entidades: normas, cortes, cargos, fechas | SaulLM-7B + LexBERT |
| **Argument mining** | Extrae ratio decidendi y obiter dicta | Arg-LLaDA |
| **Clasificacion** | 6 tipos: sentencia, demanda, contrato, concepto, norma | Pattern + keyword |
| **Resumen** | Resumen por palabras clave juridicas | Sufficiency-aware |
| **Comparacion** | Compara documentos por entidades compartidas | Entity matching |

## NLP Juridico 2026

- **SaulLM-7B**: LLM juridico entrenado con 570B tokens legales (EN/FR/DE/ES)
- **LexBERT**: NER juridico con taxonomia de 100+ entidades
- **MiningLegalBench**: Mineria de contratos, clausulas abusivas, compliance

## Comandos

- `!legal analyze <doc>` — Analizar documento legal completo
- `!legal extract <doc>` — Extraer entidades juridicas
- `!legal compare <doc1> <doc2>` — Comparar documentos
- `!legal summarize <doc>` — Resumir documento

## Ver tambien
- [Registro de skills](registry.md)
- [Investigacion aplicada](../reference/investigacion-aplicada.md)
