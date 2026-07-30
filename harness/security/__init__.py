"""Modulo de Seguridad para Swarmind — Zero Trust Architecture.

Implementa los principios de Zero Trust para comunicacion entre agentes:

1. Autenticacion mutua (mTLS) entre agentes via AgentBus.
2. Politicas de acceso granular (mini-OPA).
3. JWT rotation automatico para identidades de agentes.
4. Cifrado en transito para IPC/subprocess.
5. Verificacion de integridad de supply chain.

Basado en: AI agents.txt — Zero Trust Architecture + Token/Identity Security.
"""

from harness.security.zero_trust import (
    AgentIdentity,
    AgentToken,
    PolicyEngine,
    TokenManager,
    ZeroTrustConfig,
    verify_agent_identity,
)

__all__ = [
    "AgentIdentity",
    "AgentToken",
    "PolicyEngine",
    "TokenManager",
    "ZeroTrustConfig",
    "verify_agent_identity",
]
