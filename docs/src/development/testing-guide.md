# Guia de Testing — AGENTIC Harness

> **Ultima actualizacion:** Julio 2026  
> **Framework:** pytest 8+ con plugins oficiales  
> **Total:** 1522 tests · 287 suites · 47 modulos

---

## 1. Estructura de Tests

Todos los tests residen en `harness/tests/` y siguen la convencion `test_<modulo>.py`:

```
harness/tests/
├── __init__.py
├── conftest.py                  # Fixtures compartidas (session-scoped)
├── mock_vector_store.py         # Mock de LanceDB en memoria
├── test_agent_bus.py
├── test_agent_dispatcher.py
├── test_agent_kpi_tracker.py
├── test_agent_selector.py
├── test_architectural_guardrails.py
├── test_async_agent_bus.py
├── test_behavioral_tracer.py
├── test_cache.py
├── test_common.py
├── test_compressor.py
├── test_confidence.py
├── test_context_injector.py
├── test_context_window.py
├── test_context_window_manager.py
├── test_debate.py
├── test_difficulty_router.py
├── test_discovery.py
├── test_embeddings.py
├── test_federated_memory.py
├── test_hermes.py
├── test_hitl_guard.py
├── test_integration.py
├── test_lance_vector_store.py
├── test_lazy_loading.py
├── test_mcp_client.py
├── test_mcp_manager.py
├── test_memory.py
├── test_mock_vector_store.py
├── test_orchestrator.py
├── test_pbt_templates.py
├── test_reset_state.py
├── test_routing.py
├── test_run.py
├── test_run_commands.py
├── test_sandbox_loop.py
├── test_scheduler.py
├── test_scope_analyzer.py
├── test_semantic_cache_extended.py
├── test_session_context.py
├── test_skill_router.py
├── test_structured_log.py
├── test_task_manager.py
├── test_task_orchestrator.py
├── test_task_planner.py
├── test_telemetry.py
├── test_workflow_patterns.py
├── test_write_ahead_log.py
```

### Stack tecnologico

| Herramienta       | Version  | Proposito                          |
|-------------------|----------|------------------------------------|
| pytest            | >= 8.0   | Runner principal                   |
| pytest-cov        | >= 5     | Cobertura de codigo                |
| pytest-mock       | >= 3     | Mocking simplificado               |
| pytest-xdist      | >= 3     | Ejecucion paralela (experimental)  |
| pytest-asyncio    | >= 1.4   | Tests asincronos                   |
| unittest.mock     | stdlib   | MagicMock, patch                   |

### Convenciones

- **Nombre de archivo:** `test_<modulo>.py` (ej: `test_agent_bus.py`)
- **Nombre de clase:** `Test<NombreModulo>` o `Test<Funcionalidad>` (ej: `TestAgentBus`, `TestCreateCollection`)
- **Nombre de funcion:** `test_<descripcion>` con snake_case (ej: `test_post_message`, `test_cache_miss`)
- **Docstring:** Toda funcion de test DEBE tener docstring en ES-UTF8 describiendo el escenario y lo que verifica
- **Importaciones:** Usar `from __future__ import annotations` al inicio

---

## 2. Como Ejecutar Tests

### Todos los tests

```bash
pytest
```

### Con cobertura

```bash
pytest --cov=harness --cov-config=pyproject.toml
```

Reporte HTML local:

```bash
pytest --cov=harness --cov-report=html
# Abrir htmlcov/index.html en el navegador
```

### Tests rapidos (sin slow)

```bash
pytest -m "not slow"
```

Este es el comando que se ejecuta en cada commit — evita los tests de integracion que requieren LanceDB real.

### Tests paralelos (experimental)

```bash
pytest -n auto
```

Requiere `pytest-xdist`. **Importante:** La mayoria de los tests usan `MockVectorStore` en memoria, lo que permite paralelismo real sin locks de base de datos. Sin embargo, algunos tests con estado global pueden ser flaky en paralelo.

### Test especifico

```bash
# Por archivo
pytest harness/tests/test_run.py -v

# Por clase
pytest harness/tests/test_agent_bus.py::TestAgentBus -v

# Por test individual
pytest harness/tests/test_async_agent_bus.py::TestAsyncAgentBus::test_post_and_consume -v
```

### Por marcador

```bash
pytest -m "unit"          # Tests unitarios puros
pytest -m "integration"   # Tests con LanceDB real
pytest -m "slow"          # Tests lentos (>1s)
```

### Con salida verbosa y traceback corto

```bash
pytest -v --tb=short
```

### Sin cache de resultados

```bash
pytest -p no:cacheprovider
```

---

## 3. Categorias de Tests

| Marcador      | Descripcion                                        | Tiempo   |
|---------------|----------------------------------------------------|----------|
| `unit`        | Tests unitarios puros (default). Sin dependencias externas. | < 1s     |
| `slow`        | Tests lentos que requieren integracion real (LanceDB, red, etc.) | > 1s |
| `integration` | Tests con LanceDB real, MCP servers, u otros servicios externos | variable |
| `asyncio`     | Tests asincronos (requieren `pytest-asyncio`)       | < 1s     |
| `xfail`       | Tests esperados como fallidos por flakiness conocida | N/A      |

Los marcadores se definen en `pyproject.toml`:

```toml
[tool.pytest.ini_options]
markers = [
    "slow: tests lentos (>1s) que requieren integracion real",
    "integration: tests que dependen de LanceDB real u otros servicios externos",
    "unit: tests unitarios puros sin dependencias externas (default)",
]
```

**Nota:** `pytest.mark.asyncio` no esta registrado oficialmente en `pyproject.toml` — si aparece un warning, se puede agregar a la lista de marcadores.

---

## 4. Escribir Tests

### 4.1 Estructura basica

```python
"""Tests para MiModulo."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from harness.mi_modulo import MiClase


class TestMiClase:
    """Tests para MiClase."""

    def test_algo(self):
        """Descripcion del escenario y que verifica.  (linea X)"""
        obj = MiClase()
        assert obj.hacer_algo() == esperado
```

### 4.2 Uso de fixtures

El archivo `conftest.py` provee fixtures compartidas para toda la suite:

```python
# Fixture de sesion (se crea una vez para todos los tests)
@pytest.fixture(scope="session")
def mock_store():
    """MockVectorStore compartido por toda la sesion de tests."""
    return _mock_store_with_defaults()

# Fixture de funcion (nueva instancia por test)
@pytest.fixture
def vector_store():
    """VectorStore aislado por test usando MockVectorStore."""
    return _mock_store_with_defaults()

# Fixture compuesta (depende de otra fixture)
@pytest.fixture
def agent_bus(vector_store):
    """AgentBus conectado al vector store."""
    from harness.orchestrator.agent_bus import AgentBus
    return AgentBus(vector_store=vector_store)
```

Las fixtures disponibles globalmente incluyen:

| Fixture              | Scope    | Descripcion                                    |
|----------------------|----------|------------------------------------------------|
| `mock_store`         | session  | MockVectorStore con 15 colecciones por defecto |
| `vector_store`       | function | MockVectorStore fresco por test                |
| `agent_bus`          | function | AgentBus con vector_store                      |
| `delegation_engine`  | function | DelegationEngine                               |
| `context_assembler`  | function | ContextAssembler con vector_store              |
| `hermes_bridge`      | function | HermesBridge con vector_store                  |
| `cognition_sync`     | function | CognitionSync con vector_store                 |
| `semantic_cache`     | function | SemanticCache con MockVectorStore              |
| `agent_discovery`    | function | discover_agents_recursive()                    |
| `trajectory_compressor` | function | TrajectoryCompressor                        |
| `context_injector`   | function | ContextInjector                                |

### 4.3 Mocking de LanceDB con MockVectorStore

`MockVectorStore` es una implementacion falsa de `LanceVectorStore` que almacena datos en memoria (dicts + lists). No requiere LanceDB instalado y permite paralelismo real.

```python
from harness.tests.mock_vector_store import MockVectorStore


@pytest.fixture
def store():
    """MockVectorStore fresco para cada test."""
    return MockVectorStore()


def test_con_store(store):
    """Insercion y busqueda basica en MockVectorStore.  (linea 74)"""
    store.create_collection("test_col")
    store.add("test_col", [{"id": "1", "text": "hello"}])
    results = store.search("test_col", [0.1] * 384, top_k=5)
    assert len(results) == 1
    assert results[0]["id"] == "1"
```

**API compatible con LanceVectorStore:**

```python
# Insercion estilo LanceDB
ids = store.insert("collection", vectors_np, metadata_list)

# Busqueda hibrida
results = store.hybrid_search("col", query_vector, "keyword", top_k=5)

# Actualizar registros
count = store.update_records("col", {"domain": "test"}, {"status": "done"})

# Estadisticas
stats = store.get_collection_stats("col")
# => {"name": "...", "item_count": N, "schema": {}, "last_updated": "..."}

# Eliminar coleccion
store.delete_collection("col")
```

### 4.4 Tests asincronos

Usar `@pytest.mark.asyncio` para tests con `async/await`:

```python
import asyncio

import pytest

from harness.orchestrator.agent_bus import AsyncAgentBus


class TestAsyncAgentBus:
    """Suite de tests para AsyncAgentBus con canales asincronos."""

    @pytest.mark.asyncio
    async def test_post_and_consume(self):
        """
        Post de un mensaje seguido de consume en el mismo canal.

        Verifica que el mensaje publicado se recibe correctamente
        por el consumidor en el mismo canal.  (linea 16)
        """
        bus = AsyncAgentBus()
        expected = {"data": "hello_pacore"}

        await bus.post_message("test-channel", expected)
        result = await bus.consume("test-channel", timeout=5.0)

        assert result == expected

    @pytest.mark.asyncio
    async def test_consume_timeout(self):
        """
        Consume sin mensaje disponible lanza asyncio.TimeoutError.  (linea 32)
        """
        bus = AsyncAgentBus()

        with pytest.raises(asyncio.TimeoutError):
            await bus.consume("empty-channel", timeout=0.1)

    @pytest.mark.asyncio
    async def test_multiple_channels(self):
        """
        Canales independientes no interfieren entre si.  (linea 45)
        """
        bus = AsyncAgentBus()

        await bus.post_message("canal-a", "mensaje_A")
        await bus.post_message("canal-b", "mensaje_B")

        result_a = await bus.consume("canal-a", timeout=5.0)
        result_b = await bus.consume("canal-b", timeout=5.0)

        assert result_a == "mensaje_A"
        assert result_b == "mensaje_B"
```

### 4.5 Tests con marcadores

```python
import pytest


class TestConfidence:
    @pytest.mark.slow
    def test_full_pipeline_with_confidence(self):
        """Pipeline completo con scoring de confianza.  (linea 522)"""
        # ... test que toma >1s
        pass


class TestOrchestrator:
    @pytest.mark.slow
    def test_process_message_new_task(self):
        """Procesamiento de mensaje nuevo.  (linea 55)"""
        pass
```

### 4.6 Tests con xfail por flakiness

Cuando un test falla intermitentemente por polucion de estado entre tests:

```python
import pytest


class TestLoadServers:
    @pytest.mark.xfail(reason="Flaky por polucion entre tests (test_mcp_client corre primero)")
    def test_load_success(self, manager):
        """load_servers exitoso debe cargar servidores y conectar.  (linea 192)"""
        # ...
        pass
```

### 4.7 Ejemplo completo: tests unitarios de reset_state

```python
"""Tests para reset_state.py — limpieza de estado del harness."""
from __future__ import annotations

from pathlib import Path

from harness.reset_state import empty_dir_keep_gitkeep, rm_dir, rm_file


class TestRmDir:
    def test_elimina_directorio_existente(self, tmp_path: Path) -> None:
        """rm_dir elimina un directorio existente.  (linea 10)"""
        d = tmp_path / "testdir"
        d.mkdir()
        assert d.exists()
        rm_dir(d)
        assert not d.exists()

    def test_ignora_si_no_existe(self, tmp_path: Path) -> None:
        """rm_dir no falla si el directorio no existe.  (linea 17)"""
        d = tmp_path / "no_existe"
        assert not d.exists()
        rm_dir(d)  # no debe fallar


class TestRmFile:
    def test_elimina_archivo_existente(self, tmp_path: Path) -> None:
        """rm_file elimina un archivo existente.  (linea 24)"""
        f = tmp_path / "test.txt"
        f.write_text("data")
        assert f.exists()
        rm_file(f)
        assert not f.exists()


class TestEmptyDirKeepGitkeep:
    def test_vacia_directorio_conservando_gitkeep(self, tmp_path: Path) -> None:
        """empty_dir_keep_gitkeep vacia el directorio pero preserva .gitkeep.  (linea 37)"""
        d = tmp_path / "mydir"
        d.mkdir()
        gitkeep = d / ".gitkeep"
        gitkeep.write_text("")
        other = d / "data.txt"
        other.write_text("delete me")
        sub = d / "subdir"
        sub.mkdir()
        empty_dir_keep_gitkeep(d)
        assert gitkeep.exists()
        assert not other.exists()
        assert not sub.exists()
```

### 4.8 Ejemplo completo: AgentBus con fixtures

```python
"""Tests para AgentBus."""
from __future__ import annotations

import pytest


class TestAgentBus:
    def test_post_message(self, agent_bus):
        """post_message retorna un ID valido.  (linea 8)"""
        msg_id = agent_bus.post_message("#test", "@a", "@b", "hello", "notification")
        assert msg_id is not None
        assert isinstance(msg_id, str)
        assert len(msg_id) > 0

    def test_invalid_channel(self, agent_bus):
        """Canal invalido debe lanzar excepcion.  (linea 14)"""
        with pytest.raises(Exception):
            agent_bus.post_message("bad", "@a", "@b", "x", "notification")

    def test_poll_channel(self, agent_bus):
        """poll_channel recupera mensajes de un canal.  (linea 18)"""
        agent_bus.post_message("#ch", "@a", "@b", "msg1", "notification")
        agent_bus.post_message("#ch", "@a", "@b", "msg2", "notification")
        msgs = agent_bus.poll_channel("#ch", "@b")
        assert len(msgs) >= 1

    def test_circuit_breaker(self, agent_bus):
        """Circuit breaker se activa al superar max_iterations.  (linea 30)"""
        tid = "cb-001"
        for i in range(5):
            agent_bus.post_message("#t", "@a", "@b", f"e{i}", "error", task_id=tid)
        assert agent_bus.check_circuit_breaker(tid, max_iterations=5) is True
        assert agent_bus.check_circuit_breaker(tid, max_iterations=10) is False
```

### 4.9 Mocking avanzado con patch

Para tests que necesitan evitar imports de modulos pesados o simular comportamientos:

```python
from unittest.mock import MagicMock, patch


@pytest.fixture(autouse=True)
def patch_harness_imports():
    """Parchea importaciones de modulo top-level de run.py.  (linea 21)"""
    patches = [
        patch("harness.run.get_project_root", return_value=Path("/fake/project")),
        patch("harness.run.HAS_LANCEDB", True),
        patch("harness.run.run_full_pipeline", MagicMock()),
        patch("harness.run.logger"),
        patch("harness.run._safe_print"),
    ]
    for p in patches:
        p.start()
    yield
    for p in patches:
        p.stop()
```

Para mockear LanceDB dentro de `LanceVectorStore`:

```python
@pytest.fixture
def mem_store():
    """LanceVectorStore en modo fallback in-memory.  (linea 54)"""
    with patch.object(
        LanceVectorStore, "_try_import_lancedb", return_value=None
    ):
        store = LanceVectorStore(db_path="/tmp/test_mem", allow_fallback=True)
        yield store
```

### 4.10 Tests de integracion

Los tests de integracion real (con LanceDB) usan `@pytest.mark.slow` o `@pytest.mark.integration`:

```python
@pytest.fixture
def temp_data_dir():
    """Temp directory for test artifacts.  (linea 49)"""
    path = Path(tempfile.mkdtemp(prefix="harness_test_"))
    yield path
    shutil.rmtree(str(path), ignore_errors=True)


@pytest.mark.slow
def test_full_pipeline(orchestrator, temp_data_dir):
    """Pipeline completo: plan -> notificar -> ejecutar -> consolidar.  (linea 154)"""
    # ...
    pass
```

---

## 5. Cobertura

### Estado actual

| Metric               | Valor  |
|----------------------|--------|
| Cobertura total      | 59.69% |
| fail_under actual    | 59     |
| Objetivo             | 80%    |
| Ultima actualizacion | Jul 2026 |

La configuracion de cobertura esta en `pyproject.toml`:

```toml
[tool.coverage.run]
source = ["harness"]
omit = ["harness/tests/*", "harness/scripts/*"]

[tool.coverage.report]
fail_under = 59
# Proximo PR: fail_under = 65
# Siguiente:   fail_under = 70
# Objetivo:    fail_under = 80
```

### Ver cobertura local

```bash
# Reporte en terminal
pytest --cov=harness --cov-config=pyproject.toml

# Reporte HTML interactivo
pytest --cov=harness --cov-report=html
# Abrir htmlcov/index.html

# Reporte XML (para CI)
pytest --cov=harness --cov-report=xml
```

### Estrategia de mejora

1. **Priorizar modulos con menor cobertura** (ejecutar `coverage report -m` para listarlos)
2. **Escribir tests unitarios para ramas no cubiertas** (revisar reporte HTML)
3. **Incrementar fail_under gradualmente** (59 -> 65 -> 70 -> 80)
4. **No incluir tests ni scripts en la medicon** (ya estan omitidos)

---

## 6. CI Pipeline

### Flujo de integracion continua

```
Commit -> pre-commit hooks -> tests unitarios -> (opcional) tests lentos
```

| Paso                    | Comando                            | Frecuencia         |
|-------------------------|------------------------------------|--------------------|
| Pre-commit hooks        | `pre-commit run --all-files`       | cada commit        |
| Tests unitarios         | `pytest -m "not slow"`             | cada commit        |
| Tests con cobertura     | `pytest --cov=harness`             | cada commit        |
| Tests lentos            | `pytest -m "slow"`                 | schedule / pre-release |
| Tests paralelos         | `pytest -n auto -m "not slow"`     | experimental       |

### Pre-commit hooks

Definidos en `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: local
    hooks:
      - id: compile-check
        name: Python Compile Check
        entry: python -c "import sys, py_compile; ..."
        language: system
        types: [python]

      - id: secret-scan
        name: Secret Scanner
        entry: python -m harness.scripts.end_of_iteration.phase5_commit
        language: system
        pass_filenames: false

      - id: ruff-lint
        name: Ruff Lint
        entry: ruff check --select=E9,F --force-exclude
        language: system
        types: [python]
        pass_filenames: false
```

### Enforce de cobertura

El pipeline debe fallar si la cobertura baja del `fail_under` configurado en `pyproject.toml`:

```bash
pytest --cov=harness --cov-config=pyproject.toml
# Si coverage < fail_under -> exit code 2
```

---

## 7. Troubleshooting

### Tests flaky por polucion de estado

**Sintoma:** Un test falla intermitentemente solo cuando se ejecuta despues de otro test especifico.

**Solucion temporal:** Marcar como `xfail` con la razon documentada:

```python
@pytest.mark.xfail(reason="Flaky por polucion entre tests (test_mcp_client corre primero)")
def test_load_success(self, manager):
    """..."""
```

**Solucion permanente:** Identificar la fuente de polucion (estado global, variables de clase, modulos con efectos secundarios en importacion) y aislarla con `@pytest.fixture(autouse=True)` o `patch` en `conftest.py`.

### Errores de importacion

**Sintoma:** `ModuleNotFoundError: No module named 'harness'`

**Causa:** `sys.path` no incluye la raiz del proyecto.

**Solucion:** El `conftest.py` ya lo maneja:

```python
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(1, str(PROJECT_ROOT))
```

Si el error persiste, ejecutar los tests desde la raiz del proyecto:

```bash
cd C:\Users\USUARIO\Documents\DEV-SPACE\AGENTIC
pytest
```

### LanceDB no instalado

**Sintoma:** `ImportError: No module named 'lancedb'`

**Solucion:** Usar `MockVectorStore` como reemplazo (es el comportamiento por defecto en los tests). No es necesario tener LanceDB instalado para la mayoria de los tests.

Si se necesita probar con LanceDB real:

```bash
pip install lancedb
pytest -m "integration"
```

### Tests asincronos no se ejecutan

**Sintoma:** Los tests con `@pytest.mark.asyncio` se saltan o dan warning.

**Causa:** `pytest-asyncio` no esta instalado o configurado.

**Solucion:**

```bash
pip install pytest-asyncio
```

Verificar que esta en las dependencias:

```bash
pip install -e ".[dev]"
```

### Warning: Unknown pytest.mark.asyncio

**Sintoma:**
```
PytestUnknownMarkWarning: Unknown pytest.mark.asyncio - is this a typo?
```

**Solucion:** Agregar el marcador a `pyproject.toml`:

```toml
[tool.pytest.ini_options]
markers = [
    "asyncio: tests asincronos con pytest-asyncio",
    # ... otros marcadores
]
```

### Tests paralelos fallan intermitentemente

**Sintoma:** Tests que funcionan secuencialmente fallan con `pytest -n auto`.

**Causa:** Estado global compartido entre procesos (archivos temporales, variables de modulo, conexiones de red).

**Solucion:**
1. Usar `MockVectorStore` (thread-safe por usar estructuras en memoria locales)
2. Usar `tmp_path` de pytest para archivos temporales (aislado por test)
3. Marcar tests con estado global como `@pytest.mark.serial` (requiere `pytest-xdist` con `--dist loadscope`)
4. No compartir instancias entre tests sin `scope="session"`

### Cache de pytest causando falsos positivos

**Sintoma:** Un test pasa en isolation pero falla en suite completa.

**Solucion:** Descarta el cache de resultados:

```bash
pytest -p no:cacheprovider
```

O limpiar el cache manualmente:

```bash
rm -rf .pytest_cache
```

### Logging excesivo en tests

Para silenciar logs durante los tests:

```bash
pytest --log-cli-level=WARNING
```

O en `pyproject.toml`:

```toml
[tool.pytest.ini_options]
log_cli_level = "WARNING"
```

---

## Apendice A: MockVectorStore API Reference

`MockVectorStore` (definido en `harness/tests/mock_vector_store.py`) implementa la misma interfaz que `LanceVectorStore`:

### API nativa

| Metodo              | Descripcion                                    |
|---------------------|------------------------------------------------|
| `create_collection` | Crea una coleccion (idempotente)               |
| `add`               | Agrega items a una coleccion                   |
| `search`            | Busqueda con filtros opcionales                |
| `delete`            | Elimina un item por key                        |
| `list_tables`       | Lista todas las colecciones                    |
| `clear`             | Limpia todas las colecciones                   |

### Alias de compatibilidad con LanceVectorStore

| Metodo              | Delega en       |
|---------------------|-----------------|
| `insert`            | `add`           |
| `list_collections`  | `list_tables`   |
| `get_collection_stats` | interno     |
| `hybrid_search`     | `search` + reranking |
| `update_records`    | interno         |
| `delete_collection` | `clear` (una)   |

### Colecciones por defecto

```python
_MOCK_DEFAULT_COLLECTIONS = [
    "asi_cognition_store",
    "rag_chunks",
    "tasks_board",
    "agent_workspace_logs",
    "procedural_skills",
    "prompt_evolution_log",
    "scheduler_log",
    "hitl_approval_log",
    "semantic_cache",
    "iteration_reports",
    "agent_performance",
    "skill_effectiveness",
    "telemetry_events",
    "session_kpis",
    "agent_interactions",
]
```

Estas 15 colecciones se crean automaticamente en las fixtures `mock_store` (session) y `vector_store` (function).

---

## Apendice B: Comandos rapidos

```bash
# Todo
pytest

# Unitarios (rapido, cada commit)
pytest -m "not slow"

# Lentos (pre-release)
pytest -m "slow"

# Un archivo especifico
pytest harness/tests/test_agent_bus.py -v

# Con cobertura HTML
pytest --cov=harness --cov-report=html

# Test fallido con traceback completo
pytest --tb=long -v

# En paralelo (4 workers)
pytest -n 4 -m "not slow"

# Sin cache
pytest -p no:cacheprovider

# Listar tests sin ejecutar
pytest --collect-only --quiet
```
