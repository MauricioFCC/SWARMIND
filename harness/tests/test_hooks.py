"""Tests para el sistema de Hooks deterministas.

Cubre:
- HookRegistry: registro, baja, listado de hooks
- HookManager: ejecucion de hooks, prioridades, fail-fast
- BuiltinHooks: hooks incorporados del sistema
"""

from __future__ import annotations

from harness.hooks.builtin_hooks import register_builtin_hooks, security_validator_hook
from harness.hooks.hook_manager import (
    HookExecutionContext,
    HookManager,
    HookResult,
    HookResultStatus,
    HookType,
)
from harness.hooks.hook_registry import HookPriority, HookRegistry

# ============================================================================
# Tests: HookRegistry
# ============================================================================

class TestHookRegistry:
    """Tests para el registro central de hooks."""

    def setup_method(self) -> None:
        """Limpia el registro antes de cada test."""
        HookRegistry.get_instance().clear()

    def test_singleton(self) -> None:
        """HookRegistry debe ser singleton."""
        r1 = HookRegistry.get_instance()
        r2 = HookRegistry.get_instance()
        assert r1 is r2

    def test_register_and_count(self) -> None:
        """Registrar un hook debe incrementar el contador."""
        reg = HookRegistry.get_instance()
        reg.register("test_hook", HookType.PRE_TOOL, HookPriority.NORMAL, lambda ctx: True)
        assert reg.count() == 1

    def test_register_duplicate(self) -> None:
        """Registrar un hook con nombre duplicado debe fallar."""
        reg = HookRegistry.get_instance()
        reg.register("dup", HookType.PRE_TOOL, HookPriority.NORMAL, lambda ctx: True)
        result = reg.register("dup", HookType.POST_TOOL, HookPriority.HIGH, lambda ctx: True)
        assert result is False
        assert reg.count() == 1

    def test_unregister(self) -> None:
        """Eliminar un hook debe reducir el contador."""
        reg = HookRegistry.get_instance()
        reg.register("to_remove", HookType.PRE_TOOL, HookPriority.NORMAL, lambda ctx: True)
        assert reg.count() == 1
        reg.unregister("to_remove")
        assert reg.count() == 0

    def test_unregister_nonexistent(self) -> None:
        """Eliminar un hook inexistente debe retornar False."""
        reg = HookRegistry.get_instance()
        assert reg.unregister("no_existe") is False

    def test_get_hooks_by_type(self) -> None:
        """get_hooks debe retornar solo hooks del tipo solicitado."""
        reg = HookRegistry.get_instance()
        reg.register("pre1", HookType.PRE_TOOL, HookPriority.NORMAL, lambda ctx: True)
        reg.register("post1", HookType.POST_TOOL, HookPriority.NORMAL, lambda ctx: True)
        pre_hooks = reg.get_hooks(HookType.PRE_TOOL)
        assert len(pre_hooks) == 1
        assert pre_hooks[0].name == "pre1"

    def test_get_hooks_ordered_by_priority(self) -> None:
        """Los hooks deben retornarse ordenados por prioridad."""
        reg = HookRegistry.get_instance()
        reg.register("low", HookType.PRE_TOOL, HookPriority.LOW, lambda ctx: True)
        reg.register("critical", HookType.PRE_TOOL, HookPriority.CRITICAL, lambda ctx: True)
        hooks = reg.get_hooks(HookType.PRE_TOOL)
        assert hooks[0].priority == HookPriority.CRITICAL
        assert hooks[1].priority == HookPriority.LOW

    def test_enable_disable(self) -> None:
        """Habilitar/deshabilitar hooks debe funcionar."""
        reg = HookRegistry.get_instance()
        reg.register("toggle", HookType.PRE_TOOL, HookPriority.NORMAL, lambda ctx: True)
        assert reg.get_hook("toggle") is not None
        assert reg.get_hook("toggle").enabled is True

        reg.disable("toggle")
        assert reg.get_hook("toggle").enabled is False

        reg.enable("toggle")
        assert reg.get_hook("toggle").enabled is True

    def test_list_hooks(self) -> None:
        """list_hooks debe retornar todos los hooks."""
        reg = HookRegistry.get_instance()
        reg.register("a", HookType.PRE_TOOL, HookPriority.NORMAL, lambda ctx: True)
        reg.register("b", HookType.POST_TOOL, HookPriority.HIGH, lambda ctx: True)
        all_hooks = reg.list_hooks()
        assert len(all_hooks) == 2


# ============================================================================
# Tests: HookManager
# ============================================================================

class TestHookManager:
    """Tests para el orquestador de hooks."""

    def setup_method(self) -> None:
        """Limpia el registro antes de cada test."""
        reg = HookRegistry.get_instance()
        reg.clear()

    def test_execute_pre_tool_success(self) -> None:
        """Ejecutar hooks PRE_TOOL exitosos."""
        manager = HookManager()
        manager._registry.register("ok", HookType.PRE_TOOL, HookPriority.NORMAL, lambda ctx: True)
        results = manager.execute_pre_tool("test_tool", {"arg": 1})
        assert len(results) == 1
        assert results[0].status == HookResultStatus.SUCCESS

    def test_execute_pre_tool_blocked(self) -> None:
        """Hook que retorna False debe bloquear la operacion."""
        manager = HookManager()
        manager._registry.register("blocker", HookType.PRE_TOOL, HookPriority.CRITICAL, lambda ctx: False)
        results = manager.execute_pre_tool("test_tool")
        assert len(results) == 1
        assert results[0].status == HookResultStatus.BLOCKED

    def test_has_blocked(self) -> None:
        """has_blocked debe detectar hooks bloqueados."""
        manager = HookManager()
        results = [
            HookResult("hook1", HookResultStatus.SUCCESS),
            HookResult("hook2", HookResultStatus.BLOCKED),
        ]
        assert manager.has_blocked(results) is True

    def test_has_blocked_negative(self) -> None:
        """has_blocked debe retornar False si no hay bloqueos."""
        manager = HookManager()
        results = [
            HookResult("hook1", HookResultStatus.SUCCESS),
            HookResult("hook2", HookResultStatus.SUCCESS),
        ]
        assert manager.has_blocked(results) is False

    def test_has_errors(self) -> None:
        """has_errors debe detectar hooks con error."""
        manager = HookManager()
        results = [
            HookResult("hook1", HookResultStatus.ERROR),
        ]
        assert manager.has_errors(results) is True

    def test_skipped_hook(self) -> None:
        """Hook deshabilitado debe aparecer como SKIPPED."""
        manager = HookManager()
        reg = manager._registry
        reg.register("skipped", HookType.PRE_TOOL, HookPriority.NORMAL, lambda ctx: True)
        reg.disable("skipped")
        results = manager.execute_pre_tool("test")
        assert len(results) == 1
        assert results[0].status == HookResultStatus.SKIPPED

    def test_execute_post_tool(self) -> None:
        """Ejecutar hooks POST_TOOL."""
        manager = HookManager()
        manager._registry.register("post", HookType.POST_TOOL, HookPriority.NORMAL, lambda ctx: True)
        results = manager.execute_post_tool("test_tool", "resultado")
        assert len(results) == 1
        assert results[0].status == HookResultStatus.SUCCESS

    def test_execute_on_edit(self) -> None:
        """Ejecutar hooks ON_EDIT."""
        manager = HookManager()
        manager._registry.register("edit", HookType.ON_EDIT, HookPriority.NORMAL, lambda ctx: True)
        results = manager.execute_on_edit("/path/to/file.py")
        assert len(results) == 1

    def test_execute_on_notification(self) -> None:
        """Ejecutar hooks ON_NOTIFICATION."""
        manager = HookManager()
        manager._registry.register("notif", HookType.ON_NOTIFICATION, HookPriority.LOW, lambda ctx: True)
        results = manager.execute_on_notification("test_event", {"key": "value"})
        assert len(results) == 1


# ============================================================================
# Tests: Builtin Hooks
# ============================================================================

class TestBuiltinHooks:
    """Tests para los hooks incorporados del sistema."""

    def setup_method(self) -> None:
        """Limpia el registro antes de cada test."""
        reg = HookRegistry.get_instance()
        reg.clear()

    def test_register_builtin_hooks(self) -> None:
        """Registrar hooks incorporados debe funcionar."""
        count = register_builtin_hooks()
        assert count > 0
        # Verificar que se registraron los hooks esperados
        reg = HookRegistry.get_instance()
        assert reg.get_hook("security_validator") is not None
        assert reg.get_hook("permission_checker") is not None
        assert reg.get_hook("audit_logger") is not None

    def test_security_validator_safe(self) -> None:
        """security_validator debe aprobar comandos seguros."""
        ctx = HookExecutionContext(
            hook_type=HookType.PRE_TOOL,
            tool_name="bash",
            tool_args={"command": "ls -la"},
        )
        assert security_validator_hook(ctx) is True

    def test_security_validator_dangerous(self) -> None:
        """security_validator debe bloquear rm -rf /."""
        ctx = HookExecutionContext(
            hook_type=HookType.PRE_TOOL,
            tool_name="bash",
            tool_args={"command": "rm -rf /"},
        )
        assert security_validator_hook(ctx) is False

    def test_security_validator_safe_tool(self) -> None:
        """security_validator debe ignorar herramientas no-shell."""
        ctx = HookExecutionContext(
            hook_type=HookType.PRE_TOOL,
            tool_name="read",
            tool_args={"filePath": "test.py"},
        )
        assert security_validator_hook(ctx) is True

    def test_builtin_hooks_work_integration(self) -> None:
        """Los hooks incorporados deben ejecutarse correctamente en conjunto."""
        register_builtin_hooks()
        manager = HookManager()
        results = manager.execute_pre_tool("bash", {"command": "echo hello"})
        # Debe ejecutar security_validator + permission_checker
        assert len(results) >= 2
        # Todos deben ser SUCCESS (comando seguro)
        assert all(r.status == HookResultStatus.SUCCESS for r in results)
