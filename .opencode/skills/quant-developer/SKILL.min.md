---
name: quant-developer
description: Estrategias, broker adapters, ejecución órdenes, ONNX inference. Python cuantitativo.
---

# QUANT DEVELOPER | {{PROJECT_NAME}}

Solo cuando {{DOMAIN}} == "trading". Si {{DOMAIN}} != "trading", responder: SKIP (dominio no trading).

⚡ ROL: Desarrollador Cuantitativo • 🎯 STACK: Python/{{TRADING.platform}} • 🏗️ Hexagonal+Factory

## FLUJO: Contexto→Senal→Compliance→Orden→Broker→Log→Monitoreo

### Sub-flujo Estrategico: LEARN->DESIGN->EXPERIMENT->ANALYZE

## ✅ PRE-COMMIT CHECKLIST
- [ ] IBrokerAdapter: connect/get_ohlcv/submit_order/close_all
- [ ] Ordenes SIEMPRE con bracket OCO (stop loss + take profit)
- [ ] Multi-platform: BrokerRegistry.get(platform) via factory pattern
- [ ] ContextScore (market_context.overall_context_score) en cada Signal
- [ ] Reconexion con backoff exponencial + state recovery
- [ ] Logging: timestamp, precio, slippage, status, context_score, plataforma
- [ ] Precision decimal: MNQ=0.25, MGC=0.10 (desde {{TRADING.symbol_precision}})
- [ ] Timeout + circuit breaker en llamadas al broker
- [ ] MCP servers listos para integracion de herramientas externas
- [ ] Token/cost tracking habilitado si {{TRADING.cost_tracking_enabled}} == true

## 📐 DECISIONES TECNICAS (IF-THEN)
Si (mcp_habilitado) -> Conectar MCP servers desde {{TRADING.mcp_servers}} para datos en vivo
Si (cost_tracking_activo) -> Verificar token_budget={{TRADING.token_budget}} antes de inferencia LLM

## ⚠️ NUNCA

## 📦 STACK
Python 3.11+ | {{TRADING.brokers}} | onnxruntime | pandas | numpy | pydantic | websockets

## VARIABLES DE PROYECTO
- TRADING.platform: {{TRADING.platform}}
- TRADING.active_symbols: {{TRADING.active_symbols}}
- TRADING.confidence_metric: {{TRADING.confidence_metric}}
- TRADING.token_budget: {{TRADING.token_budget}}
- TRADING.cost_tracking_enabled: {{TRADING.cost_tracking_enabled}}
- TRADING.mcp_servers: {{TRADING.mcp_servers}}

## LEARNING ROADMAP REFERENCES

### 8 Core Domains

### 4 Personas del Ecosistema Quant

| Persona | Enfoque Principal |
|---|---|
| **Algorithmic Trader** | Operativa en vivo, gestion de riesgos, ejecucion de estrategias |
| **Quant Developer** (este skill) | Infraestructura, broker adapters, pipelines de datos, optimizacion de ejecucion |
| **Quant Researcher** | Modelos predictivos, backtesting, analisis estadistico, senales |
| **Quant Trader** | Trading cuantitativo en mesa, risk management, portfolio construction |

### Topicos Clave Referenciados

## MCP INTEGRATION

### MCP Servers para Trading

### Configuracion de MCP en el Skill

# Ejemplo de configuracion en opencode.jsonc
"mcpServers": {
  "trading-data": {

### Flujo de Trabajo con MCP

## PRODUCTION CONSIDERATIONS

### Cost Tracking y Guardrails

- **Token Budgets**: definir un maximo de tokens por sesion/estrategia via {{TRADING.token_budget}}

# Ejemplo de guard pattern para cost tracking
if COST_TRACKING_ENABLED:
    current_cost = cost_tracker.get_session_cost()

### Multi-Agent Orchestration

### Resilience Patterns

### Precision Decimal por Simbolo

| Simbolo | Tick Size | Precision |
|---|---|---|
| MNQ | 0.25 | 2 decimales fijos |
| MGC | 0.10 | 2 decimales fijos |
| {{TRADING.active_symbols}} | {{TRADING.symbol_precision}} | configurable |

### Variables de Entorno para Produccion
