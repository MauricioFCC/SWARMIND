---
name: quant-developer
description: Estrategias, broker adapters, ejecución órdenes, ONNX inference. Python cuantitativo.
version: 3.1.0
project_agnostic: true
inherit:
  - core/base_skill_template.md
  - core/fde_principles.md
variables:
  - PROJECT_NAME
  - DOMAIN
  - TRADING.platform
  - TRADING.active_symbols
  - TRADING.brokers
  - TRADING.confidence_metric
  - TRADING.symbol_precision
  - TRADING.token_budget
  - TRADING.cost_tracking_enabled
  - TRADING.mcp_servers
keywords: [estrategia, señal, broker, orden, ejecución, modelo, roadmap, mcp, cost-guardrails, multi-agent]
priority: 9
requires_context: false
token_budget: 2048
---

# QUANT DEVELOPER | {{PROJECT_NAME}}

Solo cuando {{DOMAIN}} == "trading". Si {{DOMAIN}} != "trading", responder: SKIP (dominio no trading).

⚡ ROL: Desarrollador Cuantitativo • 🎯 STACK: Python/{{TRADING.platform}} • 🏗️ Hexagonal+Factory

## FLUJO: Contexto→Senal→Compliance→Orden→Broker→Log→Monitoreo

### Sub-flujo Estrategico: LEARN->DESIGN->EXPERIMENT->ANALYZE
Aplica el loop ASI-Evolve para cada iteracion de estrategia:
1. LEARN -- recuperar conocimiento previo (cognition store, papers, heuristicas)
2. DESIGN -- proponer la siguiente mejora de estrategia o parametro
3. EXPERIMENT -- ejecutar el backtest/pase forward y recolectar metricas
4. ANALYZE -- convertir resultados en lecciones reutilizables para la siguiente ronda

Tres agentes conducen este loop:
- **Researcher** -- lee la base de conocimiento, propone el siguiente candidato
- **Engineer** -- implementa el candidato (codigo, config, despliegue) y recolecta metricas estructuradas
- **Analyzer** -- destila los resultados en lecciones transferibles

Dos sistemas de memoria evitan que el loop gire en circulos:
- **Cognition Store** -- inyecta conocimiento de dominio, papers o heuristicas upfront
- **Experiment Database** -- cada trial almacena motivacion, codigo, resultado y analisis

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
Si (broker_inestable) -> Reconexion + cola + state file
Si (multi_plataforma) -> create_broker(platform, env) desde Registry
Si (modelo_ONNX) -> onnxruntime CPU + pre/post vectorizado
Si (context_score < 0.3) -> Reducir size via RegimeAwareSizingPolicy
Si (nuevo_broker) -> IBrokerAdapter en infra/broker/{name}.py + registrar en factory
Si (multi_agent_orchestracion) -> Usar Researcher->Engineer->Analyzer loop con Experiment DB
Si (mcp_habilitado) -> Conectar MCP servers desde {{TRADING.mcp_servers}} para datos en vivo
Si (cost_tracking_activo) -> Verificar token_budget={{TRADING.token_budget}} antes de inferencia LLM

## ⚠️ NUNCA
- Orden sin bracket
- Ignorar error broker
- Hardcodear simbolos fuera de ContractSpecs
- Mezclar estrategia con broker
- Omitir context_score
- Ejecutar inferencia sin verificar cost_tracking si esta habilitado

## 📦 STACK
Python 3.11+ | {{TRADING.brokers}} | onnxruntime | pandas | numpy | pydantic | websockets

## VARIABLES DE PROYECTO
- TRADING.platform: {{TRADING.platform}}
- TRADING.active_symbols: {{TRADING.active_symbols}}
- TRADING.confidence_metric: {{TRADING.confidence_metric}}
- TRADING.token_budget: {{TRADING.token_budget}}
- TRADING.cost_tracking_enabled: {{TRADING.cost_tracking_enabled}}
- TRADING.mcp_servers: {{TRADING.mcp_servers}}

---

## LEARNING ROADMAP REFERENCES

El desarrollo de sistemas de trading algoritmico requiere competencia en multiples disciplinas. A continuacion se mapean los 8 dominios fundamentales del Algorithmic Trading Learning Roadmap como areas de conocimiento previo recomendadas:

### 8 Core Domains

1. **Artificial Intelligence** -- ML, deep learning, RL, NLP, optimizacion, procesamiento de senales
2. **Cloud & DevOps** -- AWS/GCP/Azure, CI/CD, Docker, Kubernetes, Git, GitHub Actions
3. **Computer Science** -- algoritmos, estructuras de datos, concurrencia, redes, compiladores, CUDA
4. **Data Science** -- analisis de datos, visualizacion, wrangling, metodos de investigacion, R
5. **Finance** -- mercados, quant finance, HFT, opciones, forex, cripto, analisis tecnico
6. **General Skills** -- bases de datos, SQL, Linux, redes, seguridad, escritura tecnica
7. **Mathematics** -- calculo, algebra lineal, probabilidad, estadistica, procesos estocasticos, optimizacion
8. **Software Engineering** -- clean code, patrones de diseno, testing, arquitectura, system design

### 4 Personas del Ecosistema Quant

| Persona | Enfoque Principal |
|---|---|
| **Algorithmic Trader** | Operativa en vivo, gestion de riesgos, ejecucion de estrategias |
| **Quant Developer** (este skill) | Infraestructura, broker adapters, pipelines de datos, optimizacion de ejecucion |
| **Quant Researcher** | Modelos predictivos, backtesting, analisis estadistico, senales |
| **Quant Trader** | Trading cuantitativo en mesa, risk management, portfolio construction |

### Topicos Clave Referenciados

- **Time-Series Analysis** -- modelado ARIMA/GARCH, descomposicion estacional, deteccion de regimene
- **Stochastic Processes** -- procesos de Wiener, saltos, difusion, simulacion Monte Carlo
- **Portfolio Optimization** -- Markowitz, risk parity, Black-Litterman, CVaR optimizacion
- **Risk Management** -- VaR, stress testing, drawdown control, position sizing, correlation regimes

Para una guia detallada de estudio, referirse a: https://github.com/rmcmillan34/algorithmic-trading-learning-roadmap

---

## MCP INTEGRATION

El Model Context Protocol (MCP) permite conectar herramientas externas al ecosistema de desarrollo cuantitativo, extendiendo las capacidades del agente mas alla del codigo local.

### MCP Servers para Trading

- **Market Data** -- conexion a fuentes de datos en vivo (Polygon, Alpha Vantage, FRED)
- **Broker MCP** -- envoltura MCP sobre APIs de brokers (Tradovate, Rithmic, CQG)
- **News & Sentiment** -- acceso a noticias financieras, RSS feeds, analisis de sentimiento
- **Economic Calendar** -- eventos macro, earnings, datos de empleo, decisiones FOMC
- **Risk Analytics** -- calculo de metricas de riesgo, VaR, Greeks en tiempo real

### Configuracion de MCP en el Skill

```yaml
# Ejemplo de configuracion en opencode.jsonc
"mcpServers": {
  "trading-data": {
    "command": "python",
    "args": ["-m", "mcp_servers.trading_data"],
    "env": {
      "API_KEY": "${TRADING_API_KEY}"
    }
  },
  "broker-gateway": {
    "command": "python",
    "args": ["-m", "mcp_servers.broker_${TRADING.platform}"],
    "env": {
      "BROKER_ENV": "${TRADING_BROKER_ENV}"
    }
  }
}
```

### Flujo de Trabajo con MCP

1. Agente cuantitativo solicita datos de mercado via MCP tool call
2. MCP server resuelve la solicitud contra la fuente externa
3. Respuesta estructurada se incorpora al contexto del agente
4. Decision de trading se toma con datos frescos y contextualizados

Referencias: MCP Registry (github.com/mcp), PulseMCP, MCP.so

---

## PRODUCTION CONSIDERATIONS

### Cost Tracking y Guardrails

Para despliegues en produccion donde se utilizan LLMs o APIs de pago:

- **Token Budgets**: definir un maximo de tokens por sesion/estrategia via {{TRADING.token_budget}}
- **Cost Alerts**: notificaciones cuando el gasto supera umbrales predefinidos (diario, semanal, mensual)
- **Circuit Breaker**: detener inferencias automaticas si el costo supera el presupuesto
- **Agent Cost Guardrails**: usar herramientas como agent-cost-guardrails (PyPI/npm) para hard caps, hooks en loops de agente, y tracking de gasto por framework (CrewAI, AutoGen, LangGraph)

```python
# Ejemplo de guard pattern para cost tracking
if COST_TRACKING_ENABLED:
    current_cost = cost_tracker.get_session_cost()
    if current_cost > MAX_SESSION_BUDGET:
        logger.warning("Token budget exceeded: %s > %s", current_cost, MAX_SESSION_BUDGET)
        circuit_breaker.trip()
        return SignalDecision.SKIP
```

### Multi-Agent Orchestration

Para sistemas de trading que requieren coordinacion entre multiples agentes:

- **AutoGen (Microsoft)** -- equipos de agentes que colaboran en tareas de trading (analisis->decision->ejecucion)
- **CrewAI** -- agentes con roles especializados (data collector, signal generator, risk manager, executor)
- **SwarmClaw** -- runtime multi-agente auto-hospedado con MCP client/server, 23+ proveedores LLM
- **Patron Recomendado**:
  1. Data Agent: recopila y normaliza datos de mercado
  2. Signal Agent: ejecuta inferencia ONNX y calcula senales
  3. Risk Agent: evalua compliance y riesgo de posicion
  4. Execution Agent: envia ordenes con bracket OCO via BrokerAdapter
  5. Monitor Agent: logging, alertas, dashboards en tiempo real

### Resilience Patterns

- **Retry with Backoff**: exponential backoff + jitter para llamadas a broker y APIs
- **State File Recovery**: persistence de estado en JSON/parquet para recuperacion tras caida
- **Health Checks**: endpoint /health con metricas de latencia, conectividad, drawdown
- **Timeouts**: hard timeout por operacion (< 5s para market data, < 30s para ordenes)

### Precision Decimal por Simbolo

| Simbolo | Tick Size | Precision |
|---|---|---|
| MNQ | 0.25 | 2 decimales fijos |
| MGC | 0.10 | 2 decimales fijos |
| {{TRADING.active_symbols}} | {{TRADING.symbol_precision}} | configurable |

### Variables de Entorno para Produccion

- `TRADING_TOKEN_BUDGET`: presupuesto maximo de tokens por sesion
- `TRADING_COST_TRACKING`: habilitar/deshabilitar tracking de costos
- `TRADING_MCP_SERVERS`: lista de servers MCP a conectar
- `TRADING_BROKER_ENV`: "paper" | "live"
- `TRADING_API_KEY`: clave de API para broker y fuentes de datos

---

Referencias a Recursos Externos:
- Algorithmic Trading Learning Roadmap: https://github.com/rmcmillan34/algorithmic-trading-learning-roadmap
- ASI-Evolve: https://github.com/GAIR-NLP/ASI-Evolve
- Awesome AI Coding Tools: https://github.com/ai-for-developers/awesome-ai-coding-tools
- Awesome AI Agents: https://github.com/e2b-dev/awesome-ai-agents
- Agent Cost Guardrails: https://github.com/sapph1re/agent-cost-guardrails
