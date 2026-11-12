# Catálogo de conocimiento (memoria central)

> Memoria primaria: `$MEMORY_ROOT/data/` (`ruscadb.db`,
> `knowledge_catalog.index.json`, `knowledge_catalog_graph.json`).
> El repo solo versiona los **seeds públicos**; el estado vivo y el seed local
> viven en la memoria central (fuera del repositorio).

## Qué guarda

Entradas tipadas de conocimiento reutilizable al programar:

| `kind` | Ejemplo |
|---|---|
| `repo` | microsoft/graphrag, qdrant/qdrant |
| `paper` | GraphRAG (arXiv 2404.16130), LightRAG |
| `article` | OpenAlex API, SKOS, PROV-O |
| `technique` | RRF, mesa adversarial, PBT + mutación |
| `architecture` | hexagonal Rust+Python, dual-store |
| `algorithm` | ANN/HNSW, PPR (cuando se cataloguen) |

Cada entrada tiene ID canónico (arXiv/DOI/GitHub), procedencia
(`source`, `retrieved_at`), estado (`adopted|evaluated|unverified|rejected`),
tags/conceptos y, si aplica, complejidad antes/después.

## Doble representación

1. **Embebido**: colección RuscaDB `knowledge_catalog` (vector 384-d + BM25).
2. **Grafo**: `knowledge_catalog_graph.json` con aristas `about`,
   `instance_of`, `cites`, `implements`, `uses`, `evaluates`, `related_to`.

La búsqueda fusiona dense + sparse + expansión 1-hop con RRF (`k=60`) y
degrada a híbrida si el grafo no está disponible.

## Uso

```bash
# Ingesta (idempotente) de los seeds públicos
python scripts/knowledge_catalog.py ingest docs/knowledge/catalog.seed.json
python scripts/knowledge_catalog.py ingest docs/knowledge/catalog.repos.seed.json

# Consulta
python scripts/knowledge_catalog.py search "graph rag multi-hop" --top 5
python scripts/knowledge_catalog.py search "vector database" --kind repo --json
python scripts/knowledge_catalog.py stats
python scripts/knowledge_catalog.py graph paper:arxiv-2404.16130
```

## Ciclo de vida (obligatorio)

El catálogo **se consulta antes de investigar y se alimenta después de usar**;
sin feedback envejece y pierde efectividad.

```bash
# 1) Consultar antes de la tarea
python scripts/knowledge_catalog.py search "retrieval multi-hop" --top 5

# 2) Registrar el resultado (useful | stale | missing)
python scripts/knowledge_catalog.py feedback "retrieval multi-hop" \
  --ids paper:arxiv-2404.16130,paper:arxiv-2410.05779 \
  --outcome useful --note "aplicado al diseno"

# 3) Si faltó conocimiento, queda como gap y se alimenta
python scripts/knowledge_catalog.py feedback "queda corto en X" \
  --outcome missing --note "falta una fuente sobre X"
python scripts/knowledge_catalog.py gaps
```

Regla: una consulta sin `feedback` es conocimiento que se pierde. Los gaps
(`missing`) son la cola de trabajo para añadir entradas al seed local y
reingerir.

Desde código (para inyectar contexto en un agente):

```python
from harness.memory_rag.knowledge_catalog import KnowledgeCatalog
from harness.memory_rag.ruscadb_store import RuscaDBStore

catalog = KnowledgeCatalog(RuscaDBStore())
bloque = catalog.context_block("optimizar retrieval multi-hop", top_k=3)
```

## Seeds

- `docs/knowledge/catalog.seed.json` — papers, surveys, vocabularios y técnicas
  de ingeniería (17 fuentes verificadas, incluye Go simplicity).
- `docs/knowledge/catalog.repos.seed.json` — 20 repositorios públicos
  verificados con `git ls-remote`.
- `$MEMORY_ROOT/data/knowledge/local_sources.seed.json` — conocimiento
  extraído de la documentación local de `DEV-SPACE` (privado, no se versiona).
- `$MEMORY_ROOT/data/knowledge/frontier_research.seed.json` — 43 entradas de
  `FRONTIER_RESEARCH` (MESA/BUSEV, papers, PDFs, repos y modelos GGUF;
  privado).

## Reglas

- Sin secretos ni rutas personales (el verificador las rechaza).
- Sin LLM en indexación/búsqueda: determinista y reproducible.
- Los IDs son idempotentes: reingerir no duplica; un cambio de contenido
  reemplaza la fila y sube la versión.
- Spec: `docs/specs/knowledge-catalog.md`.
- Research: `docs/research/frontier-2026-11-11-knowledge-catalog.md`.
