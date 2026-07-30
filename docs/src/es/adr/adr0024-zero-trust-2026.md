# ADR-0024: Zero Trust Architecture

## Estado
**ACEPTADO** — Implementado en julio 2026.

## Contexto
AI agents.txt identifica Zero Trust Architecture y Token/Identity Security como gaps criticos. Swarmind necesitaba autenticacion mutua entre agentes, politicas de acceso granular y rotacion de credenciales para operar en entornos institucionales.

## Decision
Implementar Zero Trust siguiendo los principios de Google BeyondCorp y NIST SP 800-207:

1. **TokenManager**: Creacion y verificacion de tokens HMAC-SHA256 con expiracion y rotacion automatica.
2. **PolicyEngine**: Mini-OPA con politicas de acceso por recurso/accion, wildcards y herencia de roles.
3. **AgentIdentity**: Identidad unica por agente con public_key_hash y permisos.
4. **verify_agent_identity**: Verificacion multi-paso (token + identidad + permisos).

### Principios Zero Trust
- No confianza implicita: cada interaccion requiere autenticacion
- Minimo privilegio: denegar por defecto, permitir explicitamente
- Rotacion constante: tokens con TTL y clave secreta rotable
- Auditoria completa: cada operacion registrada

## Consecuencias
### Positivas
- Seguridad institucional para entornos regulados
- Autenticacion mutua entre agentes via AgentBus
- Politicas de acceso granular (mini-OPA)
- Rotacion de claves sin downtime

### Negativas
- Overhead de 2-5ms por verificacion de token
- Complejidad de configuracion inicial

## Archivos creados
- `harness/security/zero_trust.py` (393 lines)
- `harness/security/__init__.py`
- `harness/tests/test_zero_trust.py` (28 tests)

## Referencias
- AI agents.txt — Zero Trust Architecture
- NIST SP 800-207: Zero Trust Architecture
- Google BeyondCorp
