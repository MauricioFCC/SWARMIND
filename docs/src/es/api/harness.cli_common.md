<!-- GENERADO POR scripts/gen_docs_api.py — NO editar a mano. Regenerar con `python scripts/gen_docs_api.py`. -->

# API — `harness.cli_common`

CLI Common — Funcionalidad compartida entre run.py y delegate.py.

### `setup\_logging(level: int = logging.INFO) -> logging.Logger`

Configura logging estructurado (JSON) para todos los entrypoints.

### `get\_harness\_root() -> Path`

Retorna la ruta absoluta a harness/.

### `get\_project\_root() -> Path`

Retorna la ruta absoluta a la raíz del proyecto.

### `parse\_message(task: str) -> tuple[str \| None, str]`

Parsea un mensaje extrayendo @rol: y !comandos.

### `format\_task\_with\_role(role: str, task: str) -> str`

Formatea tarea con @rol: prefix.

### `load\_vector\_store(db\_path: str \| None = None) -> Any`

Carga el vector store LanceDB, con manejo de errores claro.

### `check\_first\_run(harness\_root: Path) -> bool`

Detecta si es primera ejecución y guía al usuario en la configuración.

### `print\_banner(title: str, harness\_root: Path \| None = None) -> None`

Muestra banner del harness.
