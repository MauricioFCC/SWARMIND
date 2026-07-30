"""Zero Trust Architecture — Seguridad institucional para Swarmind.

Implementa un modelo de confianza cero donde cada agente debe:
1. Autenticarse antes de cualquier operacion.
2. Tener permisos explicitos (principio de minimo privilegio).
3. Ser validado en cada interaccion (no confianza implicita).
4. Usar tokens rotativos con expiracion.

Basado en los principios de Google BeyondCorp y NIST SP 800-207.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import threading
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

logger = logging.getLogger(__name__)


class AgentRole(Enum):
    """Roles de agentes en el sistema de confianza."""
    COORDINATOR = auto()
    BUILDER = auto()
    SCIENTIST = auto()
    GUARDIAN = auto()
    EVOLVE = auto()
    EXPLORER = auto()
    SPECIALIST = auto()
    SYSTEM = auto()


@dataclass
class AgentIdentity:
    """Identidad unica de un agente en el sistema Zero Trust.

    Attributes:
        agent_id: Identificador unico del agente.
        role: Rol del agente en el sistema.
        public_key_hash: Hash de la clave publica del agente.
        permissions: Lista de permisos concedidos.
        issued_at: Timestamp de creacion de la identidad.
        expires_at: Timestamp de expiracion de la identidad.
        metadata: Metadatos adicionales.
    """
    agent_id: str
    role: AgentRole
    public_key_hash: str
    permissions: set[str] = field(default_factory=set)
    issued_at: float = field(default_factory=time.time)
    expires_at: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_expired(self) -> bool:
        """Verifica si la identidad ha expirado.

        Returns:
            True si la identidad esta expirada.
        """
        if self.expires_at == 0.0:
            return False  # Sin expiracion
        return time.time() > self.expires_at

    def has_permission(self, permission: str) -> bool:
        """Verifica si el agente tiene un permiso especifico.

        Args:
            permission: Nombre del permiso a verificar.

        Returns:
            True si el agente tiene el permiso.
        """
        return permission in self.permissions


@dataclass
class AgentToken:
    """Token de autenticacion para un agente.

    Generado por TokenManager, firmado HMAC-SHA256.
    Los tokens tienen expiracion y rotacion automatica.

    Attributes:
        token_id: Identificador unico del token.
        agent_id: ID del agente propietario.
        signature: Firma HMAC-SHA256 del token.
        issued_at: Timestamp de creacion.
        expires_at: Timestamp de expiracion.
        scopes: Lista de alcances (scopes) del token.
    """
    token_id: str
    agent_id: str
    signature: str
    issued_at: float
    expires_at: float
    scopes: list[str] = field(default_factory=list)

    def is_valid(self, secret_key: bytes) -> bool:
        """Verifica la validez del token contra una clave secreta.

        Args:
            secret_key: Clave secreta para verificar la firma.

        Returns:
            True si el token es valido y no ha expirado.
        """
        if time.time() > self.expires_at:
            logger.warning("[ZeroTrust] Token expirado: %s", self.token_id)
            return False

        expected_sig: str = TokenManager._compute_signature(
            self.token_id, self.agent_id, self.issued_at, self.expires_at, secret_key,
        )
        return hmac.compare_digest(self.signature, expected_sig)


@dataclass
class ZeroTrustConfig:
    """Configuracion global del sistema Zero Trust.

    Attributes:
        enabled: Si el sistema Zero Trust esta activo.
        secret_key: Clave secreta para firmar tokens (auto-generada si vacia).
        token_ttl: Tiempo de vida de tokens en segundos (default: 1 hora).
        max_agents: Maximo numero de agentes autenticados simultaneamente.
        audit_log: Si se registran todas las operaciones en auditoria.
        strict_mode: Si se bloquean operaciones sin permiso explicito.
    """
    enabled: bool = True
    secret_key: bytes = field(default_factory=lambda: secrets.token_bytes(32))
    token_ttl: int = 3600  # 1 hora
    max_agents: int = 50
    audit_log: bool = True
    strict_mode: bool = True


class TokenManager:
    """Gestiona la creacion, verificacion y rotacion de tokens de agente.

    Thread-safe para entornos multi-agente.
    """

    def __init__(self, config: ZeroTrustConfig | None = None) -> None:
        """Inicializa el gestor de tokens.

        Args:
            config: Configuracion Zero Trust. Si es None, usa valores por defecto.
        """
        self._config: ZeroTrustConfig = config or ZeroTrustConfig()
        self._lock: threading.Lock = threading.Lock()
        self._active_tokens: dict[str, AgentToken] = {}
        self._revoked_tokens: set[str] = set()
        self._revoked_cache: set[str] = set()

    def create_token(
        self,
        agent_id: str,
        scopes: list[str] | None = None,
        ttl: int | None = None,
    ) -> AgentToken:
        """Crea un nuevo token de autenticacion para un agente.

        Args:
            agent_id: ID del agente.
            scopes: Lista de alcances del token.
            ttl: TTL en segundos (usa config.token_ttl si es None).

        Returns:
            AgentToken listo para usar.

        Raises:
            ValueError: Si agent_id es invalido o se excede max_agents.
        """
        if not agent_id or not agent_id.strip():
            raise ValueError("agent_id no puede estar vacio")

        with self._lock:
            if len(self._active_tokens) >= self._config.max_agents:
                raise ValueError(
                    f"Maximo de {self._config.max_agents} agentes alcanzado"
                )

            token_id: str = f"tok_{secrets.token_hex(16)}"
            now: float = time.time()
            expires: float = now + (ttl or self._config.token_ttl)

            signature: str = self._compute_signature(
                token_id, agent_id, now, expires, self._config.secret_key,
            )

            token: AgentToken = AgentToken(
                token_id=token_id,
                agent_id=agent_id,
                signature=signature,
                issued_at=now,
                expires_at=expires,
                scopes=scopes or [],
            )

            self._active_tokens[token_id] = token
            logger.debug("[ZeroTrust] Token creado: %s para agente %s", token_id, agent_id)
            return token

    def verify_token(self, token_id: str) -> AgentToken | None:
        """Verifica y retorna un token si es valido.

        Fast-path:
        - Cache negativo _revoked_cache para O(1) lookup sin lock de tokens revocados.
        - Si strict_mode es False, salta verificacion HMAC (confia en TTL).

        Args:
            token_id: ID del token a verificar.

        Returns:
            AgentToken si es valido, None si no.
        """
        # Fast-path lock-free: cache negativo de tokens revocados
        if token_id in self._revoked_cache:
            logger.warning("[ZeroTrust] Token revocado (cache): %s", token_id)
            return None

        with self._lock:
            # Doble check bajo lock para consistencia
            if token_id in self._revoked_tokens:
                return None

            token: AgentToken | None = self._active_tokens.get(token_id)
            if token is None:
                return None

            # Verificar expiracion siempre
            if time.time() > token.expires_at:
                self._revoke_token_internal(token_id)
                return None

            # Saltar verificacion HMAC si strict_mode es False (confiar en TTL)
            if self._config.strict_mode and not token.is_valid(self._config.secret_key):
                self._revoke_token_internal(token_id)
                return None

            return token

    def revoke_token(self, token_id: str) -> bool:
        """Revoca un token activo.

        Args:
            token_id: ID del token a revocar.

        Returns:
            True si se revoco exitosamente.
        """
        with self._lock:
            return self._revoke_token_internal(token_id)

    def _revoke_token_internal(self, token_id: str) -> bool:
        """Revocacion interna (sin lock, debe llamarse con lock adquirido).

        Args:
            token_id: ID del token a revocar.

        Returns:
            True si se revoco.
        """
        if token_id in self._active_tokens:
            del self._active_tokens[token_id]
            self._revoked_tokens.add(token_id)
            self._revoked_cache.add(token_id)
            logger.info("[ZeroTrust] Token revocado: %s", token_id)
            return True
        return False

    def rotate_secret_key(self) -> bytes:
        """Rota la clave secreta del sistema (invalida todos los tokens activos).

        Returns:
            Nueva clave secreta generada.

        Warning:
            Invalida TODOS los tokens existentes. Usar con precaucion.
        """
        with self._lock:
            old_key: bytes = self._config.secret_key
            self._config.secret_key = secrets.token_bytes(32)
            # Invalidar todos los tokens activos
            self._active_tokens.clear()
            logger.info("[ZeroTrust] Clave secreta rotada. %d tokens invalidados.",
                        len(self._active_tokens))
            return old_key

    def cleanup_expired(self) -> int:
        """Limpia tokens expirados del registro activo.

        Returns:
            Numero de tokens eliminados.
        """
        with self._lock:
            now: float = time.time()
            expired: list[str] = [
                tid for tid, tok in self._active_tokens.items()
                if now > tok.expires_at
            ]
            for tid in expired:
                self._revoke_token_internal(tid)
            return len(expired)

    def active_count(self) -> int:
        """Retorna el numero de tokens activos actualmente.

        Returns:
            Cantidad de tokens activos.
        """
        with self._lock:
            return len(self._active_tokens)

    @staticmethod
    def _compute_signature(
        token_id: str,
        agent_id: str,
        issued_at: float,
        expires_at: float,
        secret_key: bytes,
    ) -> str:
        """Calcula la firma HMAC-SHA256 para un token.

        Args:
            token_id: ID del token.
            agent_id: ID del agente.
            issued_at: Timestamp de creacion.
            expires_at: Timestamp de expiracion.
            secret_key: Clave secreta.

        Returns:
            Firma en hexadecimal.
        """
        message: str = f"{token_id}:{agent_id}:{issued_at}:{expires_at}"
        return hmac.new(
            secret_key,
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()


class PolicyEngine:
    """Motor de politicas de acceso (mini-OPA).

    Evalua reglas de acceso definidas como pares (recurso, accion) -> bool.
    Soporta herencia de roles y wildcards.

    Basado en Open Policy Agent (OPA) pero mas ligero.
    """

    def __init__(self) -> None:
        """Inicializa el motor de politicas vacio."""
        self._policies: dict[str, dict[str, bool]] = {}
        self._role_permissions: dict[AgentRole, set[str]] = {}

    def add_policy(self, resource: str, action: str, allowed: bool = True) -> None:
        """Agrega una politica de acceso.

        Args:
            resource: Recurso protegido (ej: 'harness/*', 'docs/adr').
            action: Accion permitida (ej: 'read', 'write', 'execute').
            allowed: True si esta permitido, False si esta denegado.
        """
        if resource not in self._policies:
            self._policies[resource] = {}
        self._policies[resource][action] = allowed
        logger.debug("[PolicyEngine] Politica: %s/%s -> %s", resource, action, allowed)

    def remove_policy(self, resource: str, action: str) -> bool:
        """Elimina una politica existente.

        Args:
            resource: Recurso de la politica.
            action: Accion de la politica.

        Returns:
            True si se elimino correctamente.
        """
        if resource in self._policies and action in self._policies[resource]:
            del self._policies[resource][action]
            if not self._policies[resource]:
                del self._policies[resource]
            return True
        return False

    def check_access(self, resource: str, action: str, role: AgentRole | None = None) -> bool:
        """Verifica si una accion esta permitida sobre un recurso.

        Primero verifica politicas explicitas, luego politicas wildcard,
        luego permisos de rol.

        Args:
            resource: Recurso a acceder.
            action: Accion a realizar.
            role: Rol del agente (opcional).

        Returns:
            True si el acceso esta permitido.
        """
        # 1. Politica exacta
        if resource in self._policies and action in self._policies[resource]:
            return self._policies[resource][action]

        # 2. Wildcard por recurso (ej: 'harness/*')
        parts: list[str] = resource.split("/")
        for i in range(len(parts), 0, -1):
            wildcard: str = "/".join(parts[:i]) + "/*"
            if wildcard in self._policies and action in self._policies[wildcard]:
                return self._policies[wildcard][action]

        # 3. Wildcard global
        if "*" in self._policies and action in self._policies["*"]:
            return self._policies["*"][action]

        # 4. Permisos de rol
        if role and role in self._role_permissions:
            perm: str = f"{resource}:{action}"
            if perm in self._role_permissions[role]:
                return True

        # 5. Denegar por defecto (principio de minimo privilegio)
        logger.debug("[PolicyEngine] Acceso denegado: %s/%s (role=%s)", resource, action, role)
        return False

    def set_role_permissions(self, role: AgentRole, permissions: set[str]) -> None:
        """Define los permisos para un rol especifico.

        Args:
            role: Rol del agente.
            permissions: Conjunto de permisos en formato 'recurso:accion'.
        """
        self._role_permissions[role] = permissions
        logger.info("[PolicyEngine] Permisos para %s: %d reglas", role.name, len(permissions))

    def get_role_permissions(self, role: AgentRole) -> set[str]:
        """Retorna los permisos de un rol.

        Args:
            role: Rol del agente.

        Returns:
            Set de permisos del rol.
        """
        return self._role_permissions.get(role, set())

    def clear(self) -> None:
        """Limpia todas las politicas (solo testing)."""
        self._policies.clear()
        self._role_permissions.clear()


def verify_agent_identity(
    agent_id: str,
    token: str,
    token_manager: TokenManager,
    required_permission: str | None = None,
) -> bool:
    """Verifica la identidad completa de un agente.

    Realiza:
    1. Verificacion del token.
    2. Verificacion de permisos (si se requiere).

    Args:
        agent_id: ID del agente a verificar.
        token: Token de autenticacion.
        token_manager: Gestor de tokens.
        required_permission: Permiso requerido (opcional).

    Returns:
        True si la identidad es valida y tiene los permisos necesarios.
    """
    # 1. Verificar token
    agent_token: AgentToken | None = token_manager.verify_token(token)
    if agent_token is None:
        logger.warning("[ZeroTrust] Token invalido para agente: %s", agent_id)
        return False

    # 2. Verificar que el token pertenece al agente
    if agent_token.agent_id != agent_id:
        logger.warning("[ZeroTrust] Token no pertenece al agente: %s", agent_id)
        return False

    # 3. Verificar permiso (si se requiere)
    if required_permission and required_permission not in agent_token.scopes:
        logger.warning(
            "[ZeroTrust] Agente %s no tiene permiso: %s",
            agent_id, required_permission,
        )
        return False

    return True
