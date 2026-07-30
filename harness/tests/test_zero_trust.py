"""Tests para Zero Trust Architecture.

Cubre:
- TokenManager: creacion, verificacion, rotacion, revocacion de tokens
- PolicyEngine: politicas de acceso, roles, wildcards
- verify_agent_identity: verificacion completa de identidad
- ZeroTrustConfig: configuracion del sistema
"""

from __future__ import annotations

import time

import pytest

from harness.security.zero_trust import (
    AgentIdentity,
    AgentRole,
    PolicyEngine,
    TokenManager,
    ZeroTrustConfig,
    verify_agent_identity,
)

# ============================================================================
# Tests: TokenManager
# ============================================================================

class TestTokenManager:
    """Tests para la gestion de tokens de agente."""

    def test_create_token(self) -> None:
        """Crear un token debe retornar un AgentToken valido."""
        manager = TokenManager()
        token = manager.create_token("agent_1")
        assert token.token_id.startswith("tok_")
        assert token.agent_id == "agent_1"
        assert token.signature != ""
        assert token.issued_at > 0
        assert token.expires_at > token.issued_at

    def test_create_token_with_scopes(self) -> None:
        """Crear token con scopes especificos."""
        manager = TokenManager()
        token = manager.create_token("agent_2", scopes=["read", "write"])
        assert "read" in token.scopes
        assert "write" in token.scopes

    def test_verify_valid_token(self) -> None:
        """Verificar un token valido debe retornar el token."""
        manager = TokenManager()
        token = manager.create_token("agent_3")
        verified = manager.verify_token(token.token_id)
        assert verified is not None
        assert verified.agent_id == "agent_3"

    def test_verify_invalid_token(self) -> None:
        """Verificar un token inexistente debe retornar None."""
        manager = TokenManager()
        assert manager.verify_token("tok_invalid") is None

    def test_revoke_token(self) -> None:
        """Revocar un token debe hacerlo invalido."""
        manager = TokenManager()
        token = manager.create_token("agent_4")
        assert manager.verify_token(token.token_id) is not None
        manager.revoke_token(token.token_id)
        assert manager.verify_token(token.token_id) is None

    def test_cleanup_expired(self) -> None:
        """cleanup_expired debe eliminar tokens expirados."""
        config = ZeroTrustConfig(token_ttl=1)  # 1 segundo
        manager = TokenManager(config)
        token = manager.create_token("agent_5")
        time.sleep(1.5)
        cleaned = manager.cleanup_expired()
        assert cleaned >= 1
        assert manager.verify_token(token.token_id) is None

    def test_max_agents(self) -> None:
        """Superar max_agents debe lanzar ValueError."""
        config = ZeroTrustConfig(max_agents=2)
        manager = TokenManager(config)
        manager.create_token("agent_a")
        manager.create_token("agent_b")
        with pytest.raises(ValueError, match="agentes alcanzado"):
            manager.create_token("agent_c")

    def test_active_count(self) -> None:
        """active_count debe reflejar el numero de tokens activos."""
        manager = TokenManager()
        assert manager.active_count() == 0
        manager.create_token("agent_6")
        assert manager.active_count() == 1

    def test_rotate_secret_key(self) -> None:
        """Rotar clave secreta debe invalidar todos los tokens."""
        manager = TokenManager()
        token = manager.create_token("agent_7")
        old_key = manager.rotate_secret_key()
        assert len(old_key) > 0
        # El token anterior debe ser invalido ahora
        assert manager.verify_token(token.token_id) is None

    def test_create_token_empty_id(self) -> None:
        """Crear token con ID vacio debe lanzar ValueError."""
        manager = TokenManager()
        with pytest.raises(ValueError, match="no puede estar vacio"):
            manager.create_token("")


# ============================================================================
# Tests: PolicyEngine
# ============================================================================

class TestPolicyEngine:
    """Tests para el motor de politicas de acceso."""

    def setup_method(self) -> None:
        self.engine = PolicyEngine()

    def test_add_policy(self) -> None:
        """Agregar politica debe funcionar."""
        self.engine.add_policy("docs/adr", "read", allowed=True)
        assert self.engine.check_access("docs/adr", "read") is True

    def test_deny_by_default(self) -> None:
        """Por defecto todo debe estar denegado."""
        assert self.engine.check_access("secret/data", "read") is False

    def test_wildcard_resource(self) -> None:
        """Wildcard por recurso debe funcionar."""
        self.engine.add_policy("harness/*", "write", allowed=True)
        assert self.engine.check_access("harness/orchestrator/task.py", "write") is True

    def test_global_wildcard(self) -> None:
        """Wildcard global debe funcionar."""
        self.engine.add_policy("*", "read", allowed=True)
        assert self.engine.check_access("anything/at/all", "read") is True

    def test_explicit_deny_overrides_wildcard(self) -> None:
        """Denegacion explicita debe sobreescribir wildcard."""
        self.engine.add_policy("*", "read", allowed=True)
        self.engine.add_policy("secrets/*", "read", allowed=False)
        assert self.engine.check_access("secrets/password", "read") is False

    def test_remove_policy(self) -> None:
        """Eliminar politica debe funcionar."""
        self.engine.add_policy("test", "read", allowed=True)
        assert self.engine.check_access("test", "read") is True
        self.engine.remove_policy("test", "read")
        assert self.engine.check_access("test", "read") is False

    def test_role_permissions(self) -> None:
        """Permisos por rol deben funcionar."""
        perms: set[str] = {"docs/adr:read", "harness/src:write"}
        self.engine.set_role_permissions(AgentRole.COORDINATOR, perms)
        assert self.engine.check_access("docs/adr", "read", role=AgentRole.COORDINATOR) is True
        assert self.engine.check_access("docs/adr", "write", role=AgentRole.COORDINATOR) is False

    def test_get_role_permissions(self) -> None:
        """get_role_permissions debe retornar los permisos."""
        perms: set[str] = {"resource:action"}
        self.engine.set_role_permissions(AgentRole.BUILDER, perms)
        assert self.engine.get_role_permissions(AgentRole.BUILDER) == perms

    def test_clear(self) -> None:
        """clear debe limpiar todas las politicas."""
        self.engine.add_policy("test", "read", allowed=True)
        self.engine.clear()
        assert self.engine.check_access("test", "read") is False


# ============================================================================
# Tests: verify_agent_identity
# ============================================================================

class TestVerifyAgentIdentity:
    """Tests para la verificacion completa de identidad."""

    def test_valid_identity(self) -> None:
        """Identidad valida debe pasar verificacion."""
        manager = TokenManager()
        token = manager.create_token("agent_valid", scopes=["execute"])
        result = verify_agent_identity("agent_valid", token.token_id, manager)
        assert result is True

    def test_invalid_agent_id(self) -> None:
        """Agent ID incorrecto debe fallar."""
        manager = TokenManager()
        token = manager.create_token("agent_real")
        result = verify_agent_identity("agent_impostor", token.token_id, manager)
        assert result is False

    def test_missing_permission(self) -> None:
        """Falta de permiso requerido debe fallar."""
        manager = TokenManager()
        token = manager.create_token("agent_limited", scopes=["read"])
        result = verify_agent_identity(
            "agent_limited", token.token_id, manager,
            required_permission="write",
        )
        assert result is False

    def test_revoked_token_fails(self) -> None:
        """Token revocado debe fallar verificacion."""
        manager = TokenManager()
        token = manager.create_token("agent_gone")
        manager.revoke_token(token.token_id)
        result = verify_agent_identity("agent_gone", token.token_id, manager)
        assert result is False


# ============================================================================
# Tests: AgentIdentity
# ============================================================================

class TestAgentIdentity:
    """Tests para la identidad de agente."""

    def test_is_expired(self) -> None:
        """is_expired sin expiracion debe retornar False."""
        identity = AgentIdentity(
            agent_id="test",
            role=AgentRole.SCIENTIST,
            public_key_hash="abc123",
        )
        assert identity.is_expired() is False

    def test_is_expired_with_date(self) -> None:
        """is_expired con fecha pasada debe retornar True."""
        identity = AgentIdentity(
            agent_id="test",
            role=AgentRole.BUILDER,
            public_key_hash="abc123",
            expires_at=time.time() - 1000,
        )
        assert identity.is_expired() is True

    def test_has_permission(self) -> None:
        """has_permission debe verificar permisos correctamente."""
        identity = AgentIdentity(
            agent_id="test",
            role=AgentRole.COORDINATOR,
            public_key_hash="abc123",
            permissions={"admin", "write"},
        )
        assert identity.has_permission("admin") is True
        assert identity.has_permission("delete") is False
