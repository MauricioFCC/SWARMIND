# ADR 0048: Implementación SDD Optimización Profunda de Tokens (Contexto)

## Estado
Aplicado | Implementado en `harness/tools_sandbox/mcp_governance.py` (sobre el cliente MCP existente) | Propietario: @coordinator

## Contexto
El proyecto SWARMIND requiere una estandarización de la capa de conexión entre agentes de IA y herramientas/ datos empresariales. La investigación frontier (01_search_frontier) muestra que MCP (Model Context Protocol) se ha convertido en el estándar de facto (97M+ descargas mensuales, 81K GitHub stars, supportado por Anthropic, OpenAI, Google, Microsoft, AWS) desde su open-sourcing en noviembre 2024.

## Decisión
Implementar MCP como la capa de conectividad estándar en SWARMIND, siguiendo la arquitectura:
```
Agente → →Gobernanza  Humano → IA MCP → Herramientas y Datos Empresariales
```
Donde:
- **MCP conecta agentes de IA con la empresa** (estándar USB-C del mundo AI)
- **La gobernanza se convierte en la capa de control** (define qué herramientas puede acceder cada agente)
- **La verdadera oportunidad** no es simplemente conectar agentes a más sistemas, sino construir una infraestructura donde los agentes operen de forma segura, transparente y a escala empresarial

## Consecuencias
### Positivas
- Estándar de facto con amplio adoption (97M+ monthly downloads)
- Soporte de todos los proveedores LLM (Anthropic, OpenAI, Google, Microsoft, AWS)
- Estándar JSON-RPC 2.0 con primitivas clean: Tools, Resources, Prompts
- Discovery via MCP Server Cards (.well-known)
- OAuth 2.1 + PKCE authentication
- Governance through Agentic AI Foundation (Linux Foundation)

### Negativas
- Capa adicional de complejidad para casos de uso simples
- Necesidad de operar MCP Servers en producción
- Curva de aprendizaje para equipos que migran de integraciones custom

## Alternatives Considered
1. **Integraciones custom por agente**: Cada agente con sus propias conexiones - alto costo de mantenimiento, sin gobernanza central
2. **A2A (Agent-to-Agent) solo**: Bueno para colaboración agente-agente, pero no para agente-herramienta
3. **Sin protocolo estandarizado**: Mayor riesgo de seguridad, bloqueos de proveedores, gobernanza inconsistente

## Relacionado
- ADR 0048: Implementación SDD Optimización Profunda de Tokens
- MCP Official Specification: https://modelcontextprotocol.io/docs
- Agentic AI Foundation (Linux Foundation): https://www.anthropic.com/blog/mcp-a2a-foundation

<discussion>
MCP define las primitivas (Tools, Resources, Prompts) y la gobernanza mediante el Agentic AI Foundation. La decisión de implementar MCP toma el modelo de gobernanza existente de SWARMIND y lo eleva a un protocolo estandarizado, haciendo que la gobernanza sea explícita y verificable en lugar de implícita.
</discussion>