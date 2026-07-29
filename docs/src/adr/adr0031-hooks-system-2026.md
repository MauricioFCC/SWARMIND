# ADR-0031: Hook System — Automatizacion Determinista para AGENTIC

## Estado
**ACEPTADO** — Implementado en julio 2026.

## Contexto
El archivo AI agents.txt enfatiza: "Hooks = AUTOMATION. Pre-tool, post-tool, on-edit, on-notification. Deterministic — the LLM doesn't control them." AGENTIC carecia de un sistema de hooks deterministas, lo que limitaba la automatizacion de validaciones de seguridad, formato y auditoria.

## Decision
Implementar un sistema de hooks con 4 componentes:

1. **HookRegistry**: Singleton thread-safe que mantiene el registro maestro de hooks.
2. **HookManager**: Orquestador que ejecuta hooks en orden de prioridad.
3. **4 HookTypes**: PRE_TOOL, POST_TOOL, ON_EDIT, ON_NOTIFICATION.
4. **BuiltinHooks**: security_validator, permission_checker, audit_logger, metrics_collector.

### Prioridades de ejecucion
- CRITICAL: Validacion de seguridad (fail-fast, puede detener la operacion)
- HIGH: Validacion de integridad y permisos
- NORMAL: Logging, metricas, auditoria
- LOW: Notificaciones y cosmeticos

## Consecuencias
### Positivas
- Automatizacion determinista no controlable por el LLM
- Fail-fast en hooks CRITICAL de seguridad
- Auditoria completa de todas las operaciones
- Hooks extensibles via registro programatico

### Negativas
- Overhead de ejecucion (~1-5ms por hook)
- Complejidad adicional en el pipeline de herramientas

## Archivos creados
- `harness/hooks/hook_registry.py` (212 lines)
- `harness/hooks/hook_manager.py` (241 lines)
- `harness/hooks/builtin_hooks.py` (147 lines)
- `harness/hooks/__init__.py`
- `harness/tests/test_hooks.py` (21 tests)

## Referencias
- AI agents.txt — "Hooks = Automation"
