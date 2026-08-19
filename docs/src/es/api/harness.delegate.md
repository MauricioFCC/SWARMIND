<!-- GENERADO POR scripts/gen_docs_api.py — NO editar a mano. Regenerar con `python scripts/gen_docs_api.py`. -->

# API — `harness.delegate`

logger = logging.getLogger(\_\_name\_\_)

### `resolve\_role(role\_alias: str) -> str \| None`

Resuelve un alias a su nombre canónico de agente.

### `delegate\_task(task\_text: str, extra\_args: list[str] \| None = None) -> int`

Parsea la tarea, detecta rol si es necesario, y delega a run.py.

### `main() -> int`

Delegate main entry point.
