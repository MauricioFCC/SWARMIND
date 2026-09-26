<!-- GENERADO POR scripts/gen_docs_api.py — NO editar a mano. Regenerar con `python scripts/gen_docs_api.py`. -->

# API — `harness.memory_rag.knowledge_graph`

Knowledge Graph â€” Grafo de conocimiento local-first para Swarmind.

## `KnowledgeGraph`

Grafo de conocimiento local-first para Swarmind.

### `add\_node(node\_id: str, node\_type: str = 'concept', metadata: dict[str, Any] \| None = None) -> None`

Agregar un nodo al grafo.

### `connect(source: str, target: str, relation: str, weight: float = 1.0, metadata: dict[str, Any] \| None = None) -> None`

Conectar dos nodos con una relacion.

### `query(node: str, relation: str \| None = None, node\_type: str \| None = None, max\_depth: int = 1, reverse: bool = False) -> list[dict[str, Any]]`

Consultar el grafo desde un nodo.

### `find\_path(source: str, target: str, max\_length: int = 5) -> list[list[dict[str, Any]]]`

Encontrar caminos entre dos nodos.

### `get\_stats() -> dict[str, Any]`

Obtener estadisticas del grafo.

### `search\_by\_metadata(key: str, value: Any, node\_type: str \| None = None) -> list[str]`

Buscar nodos por metadatos.

### `save(path: Path \| None = None) -> None`

Guardar el grafo a JSON.

### `load(path: Path \| None = None) -> bool`

Cargar el grafo desde JSON.

### `seed\_from\_skills(skills\_dir: Path) -> int`

Poblar el grafo desde los skills en .opencode/skills/.

### `seed\_from\_adrs(adrs\_dir: Path) -> int`

Poblar el grafo desde los ADRs en docs/src/adr/.
