# Cómo Modificar el Proyecto — Swarmind Harness

> **Última actualización:** Agosto 2026 · Python 3.12+ · 176 archivos test · 4722 tests · cobertura 75.70%

---

## 1. Estructura del Código

Todo el código fuente vive dentro de `harness/`, dividido en dominios:

| Dominio | Módulos | Propósito |
|---------|---------|-----------|
| `harness/orchestrator/` | **39** | Orquestación: agent_bus, task_planner, delegation_engine, scheduler, health, self_healing, debate, adaptive_planner, agent_discovery, agent_capsules, confidence_scorer, difficulty_router, federated_memory, hitl_guard, pbt_templates, behavioral_tracer, telemetry, scope_analyzer, governance_agent, agent_cost_controller, business_context, agent_benchmark, etc. |
| `harness/memory_rag/` | **27** | Memoria vectorial: lance_vector_store, vector_store_adapter, embeddings, semantic_cache, context_assembler, context_injector, trajectory_compressor, knowledge_graph, hermes_bridge, legal_analyzer, fts_search, agent_kpi_tracker, skill_router, compaction, etc. |
| `harness/tools_sandbox/` | **4** | MCP Client/Executor/Manager |
| `harness/evolve_loop/` | **9** | Auto-mejora: cognition_sync, evaluator, gepa_mutator, prompt_evolver, self_improver, skill_generator, agent_builder, nudge_system, procedural_memory |
| `harness/observability/` | **2** | OpenTelemetry: logging, opentelemetry_agent (trazas, métricas, exportación OTLP) |
| `harness/tests/` | **96** | Tests (92 test_*.py + conftest.py + mock_vector_store.py + __init__.py) |

**Nuevos módulos incorporados:**

| Módulo | Archivo | Propósito |
|--------|---------|-----------|
| GovernanceAgent | `orchestrator/governance_agent.py` | Políticas de gobernanza, compliance, auditoría de decisiones multi-agente |
| AgentCostController | `orchestrator/agent_cost_controller.py` | Detección de loops infinitos, control de costos de ejecución por agente |
| BusinessContext | `orchestrator/business_context.py` | Glosario de términos de negocio, contexto semántico compartido entre agentes |
| AgentBenchmark | `orchestrator/agent_benchmark.py` | Evaluación de agentes: accuracy, latencia, uso de tokens, tasa de éxito |
| OpenTelemetryAgent | `observability/opentelemetry_agent.py` | Trazabilidad distribuida, spans por operación, métricas, exportación OTLP |
| VectorStoreAdapter | `memory_rag/vector_store_adapter.py` | Abstracción multi-DB: LanceDB, Chroma, Qdrant con conmutación en caliente |

**Regla <900LC:** Ningún archivo supera 900 líneas. Si un módulo crece, se divide.

---

## 1b. Estructura `.opencode/` — CEREBRO SSOT (Opción A)

> **NUEVO (2026-08):** `.opencode/` es el cerebro del sistema (23 agents,
> 35 skills, core, registry). Se sincroniza automáticamente al global
> `~/.config/opencode/` en cada commit (pre-commit hook) y se propaga como
> mirror local a todos los proyectos de DEV-SPACE.

| Ruta | Contenido | Sync |
|------|-----------|------|
| `.opencode/agents/` | 23 perfiles (`*.md` + `*.agent.min.md`) + `auto/` | Global + mirrors |
| `.opencode/skills/` | 35 skills (`SKILL.md` + `SKILL.min.md`) + `skills_registry.yaml` | Global + mirrors |
| `.opencode/core/` | base_principles, registry, prompt_optimizer, base_skill_template | Global + mirrors |
| `.opencode/config/` | **Config propia del proyecto** (NO se sobrescribe en deploy) | Solo local |
| `.opencode/federated/` | Memoria federada entre proyectos | Solo local (preservada) |
| `.opencode/agents/auto/` | Agentes generados por evolve | Solo local (preservada) |

Scripts clave:

| Script | Función |
|--------|---------|
| `scripts/sync_opencode_global.py` | SWARMIND `.opencode/` → `~/.config/opencode/` (SSOT global) |
| `scripts/deploy_all.py` | SWARMIND → mirrors locales de DEV-SPACE (preserva config propia) |
| `harness/scripts/install_hooks.py` | Instala pre-commit (QA rápido + sync global automático) |

Guía completa: [docs/src/es/guide/opcion-a-ssot-global.md](../guide/opcion-a-ssot-global.md).

---

## 1c. Delegación local Ollama (4-tier, TKN)

Tareas simples/RAG/visión se delegan a **modelos locales** vía Ollama
(`harness/model_router/ollama_client.py` — cliente HTTP real + `ollama_tiers.py`
— router por capacidad): fast `qwen3:4b`, quality `deepseek-r1:8b`, coding
`qwen2.5-coder:7b`, embedding `qwen3-embedding:0.6b` (RAG, 1024 dims), vision
`qwen3-vl:4b`. Config sin hardcode en `.opencode/config/ollama_models.yaml`
(`keep_alive` "5m", `auto_pull` true, `warm_on_start`). Degrada a cloud
(ModelRouter/SlmRouter) si Ollama no está disponible.

## 1d. Integraciones: anydoc + patrones deepseek-harness

### Arquitecturas RAG frontier (2026-08-18): hibrido RRF + correctivo CRAG

Evaluacion de las 5 arquitecturas RAG 2026: **hibrido** y **correctivo**
implementados; **GraphRAG** y **agentic** cubiertos por modulos existentes;
**multimodal** parcial via anydoc (binarios → Markdown).

| Componente | Archivo | Rol |
|------------|---------|-----|
| `HybridRetriever` | `memory_rag/hybrid_retriever.py` | Fusion RRF (k=60) de vector denso (LanceDB) + BM25 disperso (FTS5); `HybridResult` frozen (doc_id, score, dense_rank, sparse_rank, metadata); DI sobre `FTSSearch.search(query, top_k, domain_filter)` + `LanceVectorStore.search(collection, query_vector, top_k, filters)` |
| `CorrectiveRetriever` | `memory_rag/corrective_retriever.py` | CRAG: evalua calidad de recuperacion pre-generacion (umbral 0.30, score medio + cobertura de terminos); si pobre → query rewrite (expansion de keywords) o fallback a fuente alternativa; expone `CorrectiveResult` (items, action, quality_score, corrected_query) |
| `RetrievalSource` (Protocol) | `memory_rag/corrective_retriever.py` | Contrato de fuente recuperable: `retrieve(query, top_k) -> list[dict]` |

Uso:

```python
from harness.memory_rag.hybrid_retriever import HybridRetriever
from harness.memory_rag.corrective_retriever import CorrectiveRetriever

hybrid = HybridRetriever(vector_store=vector, fts_search=fts, embed_fn=embed)
results = hybrid.retrieve("query", top_k=5)          # fusion RRF

crag = CorrectiveRetriever(primary=hybrid, fallback=fts)
out = crag.retrieve("query", top_k=5)                 # validacion + correccion
out.action          # "none" | "rewrite" | "fallback"
out.quality_score   # [0, 1]
```

Para cambiar el umbral de calidad o la funcion de reescritura, inyectar
`evaluator`/`rewrite_fn` en el constructor de `CorrectiveRetriever` (DI).

### anydoc — documentos binarios a Markdown en RAG

| Componente | Archivo | Rol |
|------------|---------|-----|
| `DocumentConverter` (Protocol) | `memory_rag/doc_converter.py` | Contrato de conversion binario → Markdown |
| `AnyDocConverter` | `memory_rag/doc_converter.py` | Implementacion lazy basada en `firecrawl-anydoc>=0.1.9` |
| `DocumentConversionError` | `memory_rag/doc_converter.py` | Error con `path` + `reason` (WHAT+WHY+WHERE) |
| `DOC_EXTENSIONS` | `memory_rag/doc_converter.py` | 21 extensiones soportadas |
| `DocumentChunker` | `memory_rag/doc_ingester.py` | Acepta `converter` inyectado (DI, default `AnyDocConverter`) |

Ingesta de binarios:

```bash
python harness/scripts/rag_ingest.py --dir <ruta> --include-docs   # CLI
!rag ingest --dir <ruta> --docs                                    # consola interactiva
```

### deepseek-harness — plugin lifecycle + session replay

- **Plugin lifecycle** (`plugins/registry.py`): `PluginBase` expone `on_load(ctx)`,
  `on_unload(ctx)` y `events` (defaults no-op). `ToolRegistry.__init__(event_bus=None)`
  inyecta el EventBus (DI) y suscribe automaticamente cada plugin a sus handlers
  `on_{event}`. `load_all()` / `unload_all()` son **idempotentes** (no re-cargan ni
  re-descargan plugins ya gestionados).
- **Session replay** (`observability/session_replay.py`): `SessionReplay` reproduce
  una sesion grabada y la exporta a Markdown o JSON; lanza `SessionNotFoundError`
  si el `session_id` no existe.

---

## 2. Ejecutar Tests

```bash
pytest                          # Todos
pytest -m "not slow"            # Rápidos (default en cada commit)
pytest --cov=harness            # Con cobertura
pytest harness/tests/test_agent_bus.py -v   # Archivo específico
pytest -n auto -m "not slow"    # Paralelo (experimental)
```

Marcadores: `unit` (default), `slow` (>1s), `integration` (LanceDB real).

Fixtures globales en `conftest.py`: mock_store (session), vector_store, agent_bus, delegation_engine, context_assembler, hermes_bridge, cognition_sync, semantic_cache, agent_discovery, trajectory_compressor, context_injector, governance_agent, agent_benchmark.

---

## 3. Estilo y Principios

```bash
ruff check .           # Linter completo
ruff format .          # Formateo automático
pre-commit run --all-files  # Hooks: compile-check, secret-scan, ruff-lint
```

| Principio | Exigencia |
|-----------|-----------|
| **DocStrings ES-UTF8** | Toda función/clase pública documentada con Args/Returns/Raises |
| **WHAT+WHY+WHERE** | Todo except loguea qué pasó, por qué y dónde. `except: pass` = FAIL |
| **Clean Code / DRY / KISS / SSOT / YAGNI** | Nombres claros, sin duplicación, simple, una fuente de verdad, lo mínimo necesario |
| **Resilience** | Circuit breakers, timeouts, retry con backoff |
| **Idempotencia** | Operaciones repetibles sin efectos secundarios |
| **CompRoot** | Composition Root único para inyección de dependencias |

---

## 4. Skills del Sistema (35)

`.opencode/skills/` contiene 35 skills en formato `SKILL.md` + `SKILL.min.md` (cobertura 100%):

**Core:** evolve, hedgefund, architecture, rust-lang  
**Cuantitativo:** quant-trading, alpha-research, risk-execution, risk-intelligence, math-doc  
**Datos/ML:** data-science, science-doc  
**Frontend/UX:** frontend-uiux, responsive-ui, creative-design  
**Negocio:** business-strategy, communication, project-management  
**Humanidades:** psychology, sociology, linguistics, ethics, behavioral-economics  
**Educación/Salud/Legal:** education, sustainability, healthtech, legal-doc  
**Infra/Seguridad:** devops-infra, security-audit  
**Retail/Física:** pos-retail, physical-sciences  
**Marketing:** ads-optimizer

---

## 5. Añadir un Nuevo Formato de Documento (anydoc)

Para que el RAG ingeste un formato adicional (p. ej. `doc`, `rtf` ya cubiertos, o
uno nuevo como `mdx`):

1. **Extender `DOC_EXTENSIONS`** en `harness/memory_rag/doc_converter.py`
   (frozenset de extensiones sin punto, en minusculas). `firecrawl-anydoc` debe
   soportar el formato; si no, implementa un converter propio del Protocol
   `DocumentConverter` e inyectalo en `DocumentChunker` (DIP).
2. **Ampliar el mapeo `_EXTENSION_TIPO`** en `harness/memory_rag/doc_ingester.py`
   para clasificar el documento en una categoria semantica:
   `documento` / `presentacion` / `hoja_calculo` / `datos_tabulares` (p. ej.
   `"docx": "documento"`, `"xlsx": "hoja_calculo"`, `"csv": "datos_tabulares"`).
3. **Verificar**: el chunker convierte el binario a Markdown antes de chunkear y
   propaga `DocumentConversionError(path, reason)` si falla — nunca lo traga.
4. **Tests**: anade un test en `harness/tests/` que ingeste un fixture del nuevo
   formato y que verifique el error para un archivo inexistente.

---

## 6. Plugin Lifecycle + Session Replay (deepseek-harness)

### Ciclo de vida de un plugin

```python
from harness.plugins.registry import PluginBase

class MiTool(PluginBase):
    """Tool demo con ciclo de vida completo."""

    def execute(self, **kwargs) -> Any:
        return "ok"

    def on_load(self, ctx: Any) -> None:
        # Hook al cargar: inicializar recursos, registrar en ctx
        ...

    def on_unload(self, ctx: Any) -> None:
        # Hook al descargar: liberar recursos, limpiar
        ...

    def events(self) -> tuple[str, ...]:
        # Eventos del EventBus a los que suscribirse (handlers on_{event})
        return ("tool_loaded",)
```

- `ToolRegistry(event_bus=bus)` inyecta el EventBus (DI); el registro suscribe
  automaticamente cada plugin a sus `on_{event}` y los desuscribe al descargar.
- `load_all(ctx)` / `unload_all(ctx)` son idempotentes: ejecutarlos dos veces no
  dispara doble carga/descarga.
- Demo de referencia: `harness/plugins/tools/example_tool.py` (`GreeterTool`).

### Session Replay

```python
from harness.observability.session_replay import SessionReplay, SessionNotFoundError

replay = SessionReplay()          # log_source por defecto: session log
try:
    md = replay.replay("sesion-123", format="markdown")   # o format="json"
except SessionNotFoundError as exc:
    print(f"Sesion no encontrada: {exc}")
```

- `export_markdown(session_id)` / `export_json(session_id)`: salida reproducible
  de una sesion grabada para auditoria o depuracion.
- `SessionNotFoundError(session_id)`: WHAT+WHY+WHERE — incluye el id de la sesion.
