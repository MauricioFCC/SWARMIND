"""
Tests para MultiUserGovernance — Permisos multi-principal con execution hooks.

arXiv:2606.21856: Verifica el sistema de gobernanza multi-usuario,
incluyendo roles, permisos con herencia, execution hooks, auditoria
y context manager de permisos temporales.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from harness.orchestrator.multi_user_governance import (
    ROLE_PERMISSIONS,
    ExecutionHooks,
    MultiUserGovernance,
    Role,
    _resolve_role_permissions,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def gov() -> MultiUserGovernance:
    """Fixture: MultiUserGovernance sin usuarios."""
    return MultiUserGovernance()


@pytest.fixture
def gov_with_users() -> MultiUserGovernance:
    """Fixture: MultiUserGovernance con un usuario por rol."""
    g = MultiUserGovernance()
    g.add_user("admin1", Role.ADMIN)
    g.add_user("editor1", Role.EDITOR)
    g.add_user("viewer1", Role.VIEWER)
    g.add_user("auditor1", Role.AUDITOR)
    return g


# ---------------------------------------------------------------------------
# Tests de resolucion de permisos (unidad)
# ---------------------------------------------------------------------------


class TestPermissionResolution:
    """Verifica la resolucion de permisos con herencia de roles."""

    def test_admin_inherits_all_permissions(self) -> None:
        """
        ADMIN debe heredar permisos de EDITOR y VIEWER.
        
        Verifica que _resolve_role_permissions para ADMIN incluya los
        permisos de todos los roles de los que depende en la jerarquia.
        """
        perms = _resolve_role_permissions(Role.ADMIN)
        assert "manage_users" in perms
        assert "delete_agent" in perms
        assert "create_agent" in perms
        assert "modify_agent" in perms
        assert "execute_agent" in perms
        assert "view_logs" in perms
        assert "audit_agent" in perms

    def test_editor_inherits_viewer_permissions(self) -> None:
        """
        EDITOR debe heredar permisos de VIEWER.
        
        Verifica que EDITOR tenga execute_agent y view_logs (de VIEWER)
        ademas de create_agent y modify_agent.
        """
        perms = _resolve_role_permissions(Role.EDITOR)
        assert "create_agent" in perms
        assert "modify_agent" in perms
        assert "execute_agent" in perms
        assert "view_logs" in perms
        assert "delete_agent" not in perms
        assert "manage_users" not in perms

    def test_viewer_has_limited_permissions(self) -> None:
        """
        VIEWER solo debe tener execute_agent y view_logs.
        
        Verifica que VIEWER no tenga permisos de administracion
        ni de modificacion de agentes.
        """
        perms = _resolve_role_permissions(Role.VIEWER)
        assert set(perms) == {"execute_agent", "view_logs"}

    def test_auditor_has_independent_permissions(self) -> None:
        """
        AUDITOR debe tener permisos de auditoria y logs.
        
        Verifica que AUDITOR tenga view_logs y audit_agent, pero no
        permisos de ejecucion ni modificacion.
        """
        perms = _resolve_role_permissions(Role.AUDITOR)
        assert "view_logs" in perms
        assert "audit_agent" in perms
        assert "execute_agent" not in perms
        assert "create_agent" not in perms

    def test_resolution_no_duplicates(self) -> None:
        """
        Los permisos resueltos no deben contener duplicados.
        
        ADMIN hereda de EDITOR y VIEWER; execute_agent y view_logs
        aparecen en multiples niveles y deben deduplicarse.
        """
        perms = _resolve_role_permissions(Role.ADMIN)
        assert len(perms) == len(set(perms)), (
            f"Permisos duplicados encontrados: {perms}"
        )


# ---------------------------------------------------------------------------
# Tests de gestion de usuarios
# ---------------------------------------------------------------------------


class TestUserManagement:
    """CRUD de usuarios: agregar, obtener, eliminar y actualizar."""

    def test_add_user_assigns_permissions(self, gov: MultiUserGovernance) -> None:
        """
        Agregar un usuario debe asignar permisos segun su rol.
        
        Verifica que add_user() cree el usuario con los permisos
        correctos segun el rol y su herencia.
        """
        user = gov.add_user("alice", Role.ADMIN)
        assert user.username == "alice"
        assert user.role == Role.ADMIN
        assert "delete_agent" in user.permissions
        assert "manage_users" in user.permissions
        assert user.enabled is True

    def test_add_duplicate_user_raises(self, gov: MultiUserGovernance) -> None:
        """
        Agregar un usuario con nombre duplicado debe lanzar ValueError.
        
        Verifica la unicidad de nombres de usuario en el sistema.
        """
        gov.add_user("alice", Role.VIEWER)
        with pytest.raises(ValueError, match="ya existe"):
            gov.add_user("alice", Role.ADMIN)

    def test_remove_user(self, gov: MultiUserGovernance) -> None:
        """
        Eliminar un usuario existente.
        
        Verifica que remove_user() elimine correctamente y que
        get_user() retorne None despues.
        """
        gov.add_user("bob", Role.EDITOR)
        gov.remove_user("bob")
        assert gov.get_user("bob") is None

    def test_remove_nonexistent_user_raises(self, gov: MultiUserGovernance) -> None:
        """
        Eliminar un usuario inexistente debe lanzar ValueError.
        """
        with pytest.raises(ValueError, match="no encontrado"):
            gov.remove_user("ghost")

    def test_update_user_role_recalculates_permissions(
        self, gov: MultiUserGovernance
    ) -> None:
        """
        Actualizar el rol debe recalcular los permisos.
        
        Verifica que al cambiar de VIEWER a ADMIN, el usuario obtenga
        todos los permisos de administrador.
        """
        user = gov.add_user("charlie", Role.VIEWER)
        assert "delete_agent" not in user.permissions

        gov.update_user_role("charlie", Role.ADMIN)
        user = gov.get_user("charlie")
        assert user is not None
        assert user.role == Role.ADMIN
        assert "delete_agent" in user.permissions
        assert "manage_users" in user.permissions

    def test_set_user_enabled_disabled(self, gov: MultiUserGovernance) -> None:
        """
        Deshabilitar un usuario debe impedir verificaciones de permiso.
        
        Verifica que un usuario deshabilitado no pueda obtener
        ningun permiso, incluso si tiene el rol adecuado.
        """
        gov.add_user("dave", Role.ADMIN)
        gov.set_user_enabled("dave", False)
        assert gov.check_permission("dave", "view_logs") is False


# ---------------------------------------------------------------------------
# Tests de verificacion de permisos
# ---------------------------------------------------------------------------


class TestPermissionCheck:
    """Verificacion de permisos con y sin execution hooks."""

    def test_admin_has_all_permissions(
        self, gov_with_users: MultiUserGovernance
    ) -> None:
        """
        ADMIN debe tener todos los permisos definidos.
        
        Verifica que un usuario ADMIN pueda ejecutar create_agent,
        delete_agent, modify_agent, execute_agent, view_logs,
        manage_users y audit_agent.
        """
        for perm in ROLE_PERMISSIONS[Role.ADMIN]:
            assert gov_with_users.check_permission("admin1", perm), (
                f"ADMIN deberia tener permiso '{perm}'"
            )

    def test_viewer_denied_admin_actions(
        self, gov_with_users: MultiUserGovernance
    ) -> None:
        """
        VIEWER no debe tener permisos de administrador.
        
        Verifica que un usuario VIEWER no pueda crear, eliminar ni
        modificar agentes, ni gestionar usuarios.
        """
        assert gov_with_users.check_permission("viewer1", "create_agent") is False
        assert gov_with_users.check_permission("viewer1", "delete_agent") is False
        assert gov_with_users.check_permission("viewer1", "manage_users") is False
        assert gov_with_users.check_permission("viewer1", "modify_agent") is False

    def test_nonexistent_user_denied(self, gov: MultiUserGovernance) -> None:
        """
        Usuario inexistente debe recibir denegacion.
        
        Verifica que check_permission retorne False para usuarios
        que no existen en el sistema.
        """
        assert gov.check_permission("ghost", "view_logs") is False

    def test_check_permission_with_context(
        self, gov: MultiUserGovernance
    ) -> None:
        """
        Verificar permiso con contexto debe funcionar correctamente.
        
        El contexto se pasa a los hooks pero no afecta la logica
        basica de verificacion de permisos.
        """
        gov.add_user("eve", Role.EDITOR)
        ctx = {"agent_id": "agent_42", "action": "modify"}
        assert gov.check_permission("eve", "modify_agent", context=ctx) is True
        assert gov.check_permission("eve", "delete_agent", context=ctx) is False


# ---------------------------------------------------------------------------
# Tests de execution hooks
# ---------------------------------------------------------------------------


class TestExecutionHooks:
    """Execution hooks: pre_exec, post_exec, on_deny."""

    def test_pre_exec_hook_denies_permission(self, gov: MultiUserGovernance) -> None:
        """
        pre_exec hook que retorna False debe denegar el permiso.
        
        Verifica que el hook pre_exec pueda interceptar y denegar
        una operacion antes de la verificacion de permisos.
        """
        def deny_hook(username: str, permission: str, context: dict) -> bool:
            return False  # Denegar siempre

        gov.set_hooks(ExecutionHooks(pre_exec=deny_hook))
        gov.add_user("frank", Role.ADMIN)
        assert gov.check_permission("frank", "view_logs") is False

    def test_pre_exec_hook_allows_permission(self, gov: MultiUserGovernance) -> None:
        """
        pre_exec hook que retorna True debe permitir la verificacion normal.
        
        Verifica que el hook no interfiera cuando retorna True.
        """
        def allow_hook(username: str, permission: str, context: dict) -> bool:
            return True  # Permitir verificacion normal

        gov.set_hooks(ExecutionHooks(pre_exec=allow_hook))
        gov.add_user("grace", Role.VIEWER)
        assert gov.check_permission("grace", "view_logs") is True
        assert gov.check_permission("grace", "delete_agent") is False

    def test_on_deny_hook_invoked_on_denial(
        self, gov: MultiUserGovernance
    ) -> None:
        """
        on_deny hook debe invocarse cuando se deniega un permiso.
        
        Verifica que el hook on_deny se ejecute con los argumentos
        correctos cuando un permiso es denegado.
        """
        denied_log: list = []

        def deny_logger(username: str, permission: str, context: dict,
                        reason: str | None) -> None:
            denied_log.append((username, permission, reason))

        gov.set_hooks(ExecutionHooks(on_deny=deny_logger))
        gov.add_user("heidi", Role.VIEWER)

        # Denegacion esperada
        gov.check_permission("heidi", "delete_agent")
        assert len(denied_log) == 1
        assert denied_log[0][0] == "heidi"
        assert denied_log[0][1] == "delete_agent"

        # Permiso concedido no debe invocar on_deny
        gov.check_permission("heidi", "view_logs")
        assert len(denied_log) == 1  # Sin incremento

    def test_post_exec_hook_invoked_always(
        self, gov: MultiUserGovernance
    ) -> None:
        """
        post_exec hook debe invocarse siempre, concedido o denegado.
        
        Verifica que el hook post_exec se ejecute tanto en
        verificaciones exitosas como denegadas.
        """
        post_log: list = []

        def post_logger(username: str, permission: str, context: dict,
                        granted: bool) -> None:
            post_log.append((username, permission, granted))

        gov.set_hooks(ExecutionHooks(post_exec=post_logger))
        gov.add_user("ivan", Role.EDITOR)

        # Verificacion exitosa
        gov.check_permission("ivan", "modify_agent")
        assert post_log[-1] == ("ivan", "modify_agent", True)

        # Verificacion denegada
        gov.check_permission("ivan", "delete_agent")
        assert post_log[-1] == ("ivan", "delete_agent", False)

        assert len(post_log) == 2

    def test_pre_exec_exception_denies_safely(
        self, gov: MultiUserGovernance
    ) -> None:
        """
        Si pre_exec lanza una excepcion, el permiso debe denegarse.
        
        Verifica que el sistema sea seguro ante fallos en los hooks:
        una excepcion en pre_exec resulta en denegacion del permiso.
        """
        def broken_hook(username: str, permission: str, context: dict) -> bool:
            raise RuntimeError("Fallo inesperado del hook")

        gov.set_hooks(ExecutionHooks(pre_exec=broken_hook))
        gov.add_user("jack", Role.ADMIN)
        assert gov.check_permission("jack", "manage_users") is False


# ---------------------------------------------------------------------------
# Tests del context manager with_permission
# ---------------------------------------------------------------------------


class TestWithPermission:
    """Context manager para permisos temporales."""

    def test_with_permission_granted_executes_block(self, gov: MultiUserGovernance) -> None:
        """
        El bloque con with_permission debe ejecutarse si hay permiso.
        
        Verifica que el context manager permita la ejecucion del
        bloque cuando el usuario tiene el permiso requerido.
        """
        gov.add_user("karen", Role.ADMIN)
        executed = False

        with gov.with_permission("karen", "delete_agent") as granted:
            if granted:
                executed = True

        assert executed is True

    def test_with_permission_denied_skips_block(
        self, gov: MultiUserGovernance
    ) -> None:
        """
        El bloque con with_permission no debe ejecutarse sin permiso.
        
        Verifica que el context manager deniegue la ejecucion del
        bloque cuando el usuario no tiene el permiso requerido.
        """
        gov.add_user("leo", Role.VIEWER)
        executed = False

        with gov.with_permission("leo", "delete_agent") as granted:
            if granted:
                executed = True

        assert executed is False


# ---------------------------------------------------------------------------
# Tests del registro de auditoria
# ---------------------------------------------------------------------------


class TestAuditLog:
    """Registro de auditoria de operaciones de gobernanza."""

    def test_audit_logs_permission_checks(
        self, gov_with_users: MultiUserGovernance
    ) -> None:
        """
        Las verificaciones de permiso deben quedar registradas.
        
        Verifica que check_permission genere entradas GRANTED y DENIED
        en el log de auditoria.
        """
        gov_with_users.check_permission("admin1", "manage_users")
        gov_with_users.check_permission("viewer1", "delete_agent")

        log = gov_with_users.get_audit_log()
        granted = [e for e in log if e.action == "GRANTED"]
        denied = [e for e in log if e.action == "DENIED"]

        assert len(granted) >= 1
        assert len(denied) >= 1

    def test_audit_log_includes_timestamp(
        self, gov: MultiUserGovernance
    ) -> None:
        """
        Cada entrada de auditoria debe tener timestamp UTC.
        
        Verifica que las entradas tengan timestamp con timezone UTC
        y que sean instancias de datetime.
        """
        gov.add_user("maria", Role.EDITOR)
        gov.check_permission("maria", "view_logs")

        entry = gov.get_audit_log()[0]
        assert isinstance(entry.timestamp, datetime)
        assert entry.timestamp.tzinfo is not None
        # Debe ser cercano al tiempo actual
        now = datetime.now(UTC)
        diff = abs((now - entry.timestamp).total_seconds())
        assert diff < 10  # Menos de 10 segundos de diferencia

    def test_audit_summary_groups_by_action(
        self, gov: MultiUserGovernance
    ) -> None:
        """
        get_audit_summary() debe agrupar entradas por tipo de accion.
        
        Verifica que el resumen contenga los tipos de eventos
        ocurridos con sus respectivos conteos.
        """
        gov.add_user("nancy", Role.VIEWER)
        gov.check_permission("nancy", "view_logs")
        gov.check_permission("nancy", "delete_agent")
        gov.check_permission("nancy", "view_logs")

        summary = gov.get_audit_summary()
        assert summary.get("ADD_USER", 0) == 1
        assert summary.get("GRANTED", 0) == 2  # view_logs x2
        assert summary.get("DENIED", 0) == 1   # delete_agent

    def test_audit_log_since_filter(
        self, gov: MultiUserGovernance
    ) -> None:
        """
        get_audit_log_since() debe filtrar por fecha.
        
        Verifica que solo se retornen entradas posteriores a la
        fecha especificada.
        """
        gov.add_user("oscar", Role.AUDITOR)
        before = datetime.now(UTC) - timedelta(hours=1)
        # Todas las entradas deben ser posteriores a 'before'
        entries = gov.get_audit_log_since(before)
        assert len(entries) >= 1

        # Filtrar por un futuro: debe retornar lista vacia
        future = datetime.now(UTC) + timedelta(hours=1)
        entries_future = gov.get_audit_log_since(future)
        assert len(entries_future) == 0

    def test_clear_audit_log(self, gov: MultiUserGovernance) -> None:
        """
        clear_audit_log() debe vaciar el registro de auditoria.
        """
        gov.add_user("paul", Role.EDITOR)
        assert gov.count_audit_entries() > 0
        gov.clear_audit_log()
        assert gov.count_audit_entries() == 0


# ---------------------------------------------------------------------------
# Tests de resumen del sistema
# ---------------------------------------------------------------------------


class TestGovernanceSummary:
    """Resumen del estado del sistema de gobernanza."""

    def test_get_summary_structure(self, gov_with_users: MultiUserGovernance) -> None:
        """
        get_summary() debe retornar un dict con las claves esperadas.
        """
        summary = gov_with_users.get_summary()
        assert "total_users" in summary
        assert "users_by_role" in summary
        assert "total_permissions" in summary
        assert "audit_entries" in summary
        assert "hooks_configured" in summary

    def test_get_summary_counts(self, gov: MultiUserGovernance) -> None:
        """
        Los conteos del resumen deben reflejar el estado real.
        """
        gov.add_user("admin1", Role.ADMIN)
        gov.add_user("editor1", Role.EDITOR)
        gov.add_user("viewer1", Role.VIEWER)

        summary = gov.get_summary()
        assert summary["total_users"] == 3
        assert summary["users_by_role"]["admin"] == 1
        assert summary["users_by_role"]["editor"] == 1
        assert summary["users_by_role"]["viewer"] == 1

    def test_hooks_configured_in_summary(self, gov: MultiUserGovernance) -> None:
        """
        El resumen debe reflejar si los hooks estan configurados.
        """
        summary = gov.get_summary()
        assert summary["hooks_configured"]["pre_exec"] is False
        assert summary["hooks_configured"]["post_exec"] is False
        assert summary["hooks_configured"]["on_deny"] is False

        gov.set_hooks(ExecutionHooks(
            pre_exec=lambda u, p, c: True,
        ))
        summary = gov.get_summary()
        assert summary["hooks_configured"]["pre_exec"] is True
        assert summary["hooks_configured"]["post_exec"] is False


# ---------------------------------------------------------------------------
# Tests de integracion y casos borde
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Casos borde del sistema de gobernanza multi-usuario."""

    def test_empty_governance_no_users(self, gov: MultiUserGovernance) -> None:
        """
        Sistema sin usuarios debe denegar todas las verificaciones.
        """
        assert gov.check_permission("anyone", "anything") is False
        assert gov.get_users() == {}
        assert gov.count_audit_entries() == 1  # La denegacion queda auditada
        assert gov.get_summary()["total_users"] == 0

    def test_get_users_returns_copy(self, gov: MultiUserGovernance) -> None:
        """
        get_users() debe retornar una copia, no el dict interno.
        """
        gov.add_user("protected", Role.ADMIN)
        users_copy = gov.get_users()
        # Mutar la copia no debe afectar el original
        users_copy.clear()
        assert len(gov.get_users()) == 1

    def test_add_user_with_metadata(self, gov: MultiUserGovernance) -> None:
        """
        Agregar usuario con metadatos debe conservarlos.
        """
        meta = {"email": "test@example.com", "department": "engineering"}
        user = gov.add_user("quinn", Role.EDITOR, metadata=meta)
        assert user.metadata["email"] == "test@example.com"
        assert user.metadata["department"] == "engineering"

    def test_get_user_permissions_for_nonexistent(
        self, gov: MultiUserGovernance
    ) -> None:
        """
        get_user_permissions() debe retornar lista vacia si no existe.
        """
        assert gov.get_user_permissions("ghost") == []

    def test_get_users_by_role_filter(self, gov_with_users: MultiUserGovernance) -> None:
        """
        get_users_by_role() debe filtrar correctamente por rol.
        """
        admins = gov_with_users.get_users_by_role(Role.ADMIN)
        assert len(admins) == 1
        assert admins[0].username == "admin1"

        editors = gov_with_users.get_users_by_role(Role.EDITOR)
        assert len(editors) == 1
        assert editors[0].username == "editor1"

        # Agregar otro admin
        gov_with_users.add_user("admin2", Role.ADMIN)
        admins = gov_with_users.get_users_by_role(Role.ADMIN)
        assert len(admins) == 2

    def test_role_enum_values(self) -> None:
        """
        Los valores del enum Role deben ser los esperados.
        """
        assert Role.ADMIN.value == "admin"
        assert Role.EDITOR.value == "editor"
        assert Role.VIEWER.value == "viewer"
        assert Role.AUDITOR.value == "auditor"
