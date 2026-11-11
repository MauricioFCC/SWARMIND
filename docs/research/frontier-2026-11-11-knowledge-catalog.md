# Frontier research — Catálogo de conocimiento (repos, papers, técnicas, arquitecturas y algoritmos)

> **Fecha:** 2026-11-11 · **Ciclo:** 11.94 · **Skill:** `frontier-engineering`
> **Tarea explícita:** que la memoria central mantenga un **catálogo** de
> repositorios, papers, investigaciones, artículos, técnicas, arquitecturas
> óptimas y algoritmos de estado del arte, **ingerido (embebido) y en grafo**,
> para reutilizar conocimiento fundamental y de frontera al programar.

## 0. Persona y canon

Principal AI architect & research scientist. Regla RSF/FRS: sin fuente leída
no hay claim. Las técnicas no aplicadas se documentan con su motivo.

## 1. Fuentes leídas (paper trail)

| # | Fuente | URL | Aporte | Estado |
|---|--------|-----|--------|--------|
| F1 | Edge et al., *From Local to Global: A Graph RAG Approach to Query-Focused Summarization* (Microsoft, 2024) | https://arxiv.org/abs/2404.16130 | GraphRAG: grafo de entidades + comunidades + resúmenes para preguntas globales | ✅ leída |
| F2 | Guo et al., *LightRAG: Simple and Fast Retrieval-Augmented Generation* (EMNLP 2025) | https://arxiv.org/abs/2410.05779 | Dual-level retrieval (local/global) + actualización incremental del grafo | ✅ leída |
| F3 | Gutiérrez et al., *HippoRAG: Neurobiologically Inspired Long-Term Memory for LLMs* (NeurIPS 2024) | https://arxiv.org/abs/2405.14831 | KG + Personalized PageRank para multi-hop, 10-30× más barato que iterative RAG | ✅ leída |
| F4 | Zhang et al., *A Survey of Graph Retrieval-Augmented Generation for Customized LLMs* (2025) | https://arxiv.org/abs/2501.13958 | Taxonomía GraphRAG (indexado, retrieval, generación) | ✅ leída |
| F5 | Xiao et al., *GraphRAG-Bench* (2025) | https://arxiv.org/abs/2506.02404 | Benchmark por etapas: construcción, retrieval, generación | ✅ leída |
| F6 | Xiang et al., *When to use Graphs in RAG* (2025) | https://arxiv.org/abs/2506.05690 | GraphRAG **no siempre** gana a RAG vanilla; condiciones de uso | ✅ leída |
| F7 | Xu et al., *A-MEM: Agentic Memory for LLM Agents* (NeurIPS 2025) | https://arxiv.org/abs/2502.12110 | Notas Zettelkasten con atributos + enlaces dinámicos y evolución | ✅ leída |
| F8 | Rasmussen et al., *Zep: A Temporal Knowledge Graph Architecture for Agent Memory* (2025) | https://arxiv.org/abs/2501.13956 | Grafo bi-temporal (valid time + ingestion time), no-lossy | ✅ leída |
| F9 | OpenAlex API (catálogo scholarly abierto) | https://help.openalex.org/api | IDs canónicos (DOI, arXiv, ORCID), metadatos y citas | ✅ leída |
| F10 | schema.org — `ScholarlyArticle` | https://schema.org/ScholarlyArticle | Vocabulario para papers/artículos | ✅ leída |
| F11 | W3C — SKOS Reference | https://www.w3.org/TR/skos-reference | Conceptos, `broader`/`narrower`/`related` para tags | ✅ leída |
| F12 | W3C — PROV-O | https://www.w3.org/TR/prov-o/ | Procedencia (`wasDerivedFrom`, `generatedAtTime`) | ✅ leída |
| F13 | DEEP-PolyU, *Awesome-GraphRAG* | https://github.com/DEEP-PolyU/Awesome-GraphRAG | Repos, surveys y benchmarks GraphRAG | ✅ leída |

## 2. Hipótesis comparadas

Criterios: **A** = accuracy multi-hop/global; **L** = latencia p95; **E** =
escalabilidad; **R** = robustez (degradación sin LLM/red); **P** =
reproducibilidad; **C** = costo.

| Hipótesis | A | L | E | R | P | C | Veredicto |
|-----------|---|---|---|---|---|---|-----------|
| **H1. RAG plano** (solo vectores/FTS sobre entradas) | Baja en multi-hop; alta en lookup | **Alta** | Alta | Alta | Alta | Bajo | Insuficiente para “qué técnicas conectan paper→arquitectura→algoritmo” |
| **H2. Solo grafo** (KG + PPR, sin texto) | Alta en multi-hop | Media | Media | Media | Alta | Medio | Pierde recall de texto libre y resúmenes |
| **H3. Dual-store híbrido** (RuscaDB vector+FTS con RRF + grafo tipado con expansión 1-hop) | **Alta** | **Alta** | Alta | **Alta** (degrada a H1 sin grafo) | **Alta** | Bajo-Medio | **Elegida** |
| H4. GraphRAG completo (comunidades + resúmenes LLM) | Muy alta en “temas globales” | Baja | Baja (reindexar) | Baja (depende de LLM) | Baja (no determinista) | Alto | **No aplicada**: costo/no-determinismo en el camino caliente |

**Hallazgo clave (F6):** GraphRAG no domina siempre a RAG vanilla; el grafo
aporta sobre todo en preguntas que cruzan entidades/documentos. Por eso H3 usa
el grafo como **expansión acotada** de candidatos (mejora multi-hop sin pagar
reindexación global), y H4 queda como fase offline opcional.

## 3. Gap analysis (IDP)

Lo que SWARMIND **ya tiene** (auditado antes de escribir código):

- `RuscaDBStore`: `insert` (vectores + metadata + `edges`), `search` (HNSW),
  `full_text_search` (BM25), `hybrid_search` (RRF, `k=60`), `graph_traverse`.
- `KnowledgeGraph`: `MultiDiGraph` NetworkX con nodos/aristas tipadas y
  persistencia JSON (`seed_from_skills`, `seed_from_adrs`).
- `doc_ingester`: chunking + vectorización de documentos.
- 16 colecciones canónicas en la memoria central (`rag_chunks`, etc.).
- Specs de memoria (`ruscadb-*`, `memory-*`) y 4.000+ tests.

Lo que **falta** (gap que cierra este ciclo):

1. Una colección **tipada** de conocimiento externo (repo/paper/artículo/
   técnica/arquitectura/algoritmo) con ID canónico, procedencia y estado.
2. Un **esquema de grafo** para conectar entradas ↔ conceptos/tecnologías ↔
   citas ↔ repos, reutilizable por agentes.
3. Una **API de consulta híbrida** (vector+FTS+grafo) con filtros por tipo y
   salida lista para inyectar en contexto.
4. **Ingesta idempotente** (dedupe por DOI/arXiv/GitHub) y export portable.
5. Seed curado con las fuentes de este research para valor inmediato.

## 4. Decisión y complejidad

**H3** sobre H1/H2/H4: mejor accuracy multi-hop que H1, mejor recall que H2 y
mucho menor costo/no-determinismo que H4, reutilizando el dual-store existente.

Complejidad (n = entradas, D = 384 dims, t = tags/conceptos, k = top-k,
b = factor de ramificación del grafo, d = profundidad):

- **Ingesta:** `O(n·(D + t))` — embedding + inserción + aristas.
- **Búsqueda:** `O(log n + k log k + b^d)` — ANN/FTS + RRF + expansión acotada
  (`d ≤ 2`, `b` limitado por `max_neighbors`).
- **Dedupe:** `O(1)` esperado por entrada (hash del ID canónico).
- Antes: no había catálogo → cada consulta exigía relectura manual de fuentes
  (`O(R)` por consulta, R = fuentes). Después: `O(log n + …)` con cache de
  conocimiento reutilizable.

Fórmula RRF usada por el dual-store:

$$
\mathrm{score}(d) = \sum_{r \in \{\text{dense},\text{sparse},\text{graph}\}}
\frac{1}{k + \mathrm{rank}_r(d)}, \quad k = 60
$$

## 5. Riesgos y mitigaciones

- **Envenenamiento de memoria** (OWASP ASI06): el store ya marca
  `trust_tier`/`quarantined`; el catálogo exige `source` y `retrieved_at`.
- **Deriva de IDs** (mismo paper con URL distinta): `canonical_id` normaliza
  DOI/arXiv/GitHub y se testea con PBT (idempotencia).
- **Grafo incompleto**: la búsqueda degrada a híbrida sin grafo (H1).
- **Datos privados**: el seed es público; el verificador rechaza rutas
  personales (`C:\Users\<user>`, `/home/<user>`).

## 6. No aplicado (con motivo)

- **Comunidades GraphRAG + resúmenes LLM (H4):** requiere LLM en indexación,
  reindexación costosa y salida no determinista; se deja como fase offline
  futura, no en el camino caliente.
- **PPR completo (HippoRAG):** la expansión 1-2 hops cubre el caso de uso;
  PPR se evaluará cuando el catálogo supere ~10k entradas.
- **Embeddings neuronales densos:** se usa el embedding determinista del repo
  (`make_embedding`, 384-d); sustituirlo por un modelo real es un cambio de
  configuración, no de arquitectura.
