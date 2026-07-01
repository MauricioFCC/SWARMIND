---
name: trading-operations
description: Use when managing live trading operations, monitoring bots, configuring alerts, handling broker connectivity, managing schedules (market open/close), or setting up dashboards for real-time trading. Operaciones de trading en vivo, monitoreo, alertas Discord/Telegram, conectividad, schedules, dashboards en tiempo real.
---

## CUANDO ACTIVAR
Solo cuando {{DOMAIN}} == "trading". Si {{DOMAIN}} != "trading", responder: SKIP (dominio no trading).

## ✅ CHECKLIST PRE-COMMIT
- [ ] Healthcheck de todos los componentes: plataforma de ejecución, modelo, risk engine, compliance
- [ ] Docs 1:1: Toda interfaz/API modificada tiene su doc o README actualizado
- [ ] Alertas configuradas: conexión caída, drawdown límite, error de orden, slippage alto
- [ ] Scheduler: horarios de mercado configurados desde {{TRADING.schedule}}
- [ ] Dashboard en tiempo real: P&L, drawdown, posiciones abiertas, estado conexión
- [ ] Logging de cada heartbeat, orden, error y alerta con timestamp y correlation ID
- [ ] Símbolos activos sincronizados desde {{TRADING.active_symbols}}

## 📐 DECISIONES TÉCNICAS (IF-THEN)

## ⚠️ NUNCA

## 📦 VARIABLES
`{{TRADING.platform}}` `{{TRADING.active_symbols}}` `{{TRADING.alerts.channel}}` `{{TRADING.schedule.market_open}}` `{{TRADING.schedule.market_close}}` `{{TRADING.schedule.timezone}}`

## BOUNDARY MATRIX — Compliance vs Risk vs Trading Operations

| Concern | security-engineer | risk-manager | trading-operations |
|---------|:-:|:-:|:-:|
| Daily loss limit enforcement | **OWN** | Input | Execute kill |
| Max drawdown tracking | **OWN** | Calculate threshold | Monitor + kill |
| Position size limits | Validate | **OWN** | Execute |
| Kelly criterion / sizing | — | **OWN** | — |
| Volatility-based adjustments | — | **OWN** | — |
| Circuit breaker thresholds | — | **OWN** | — |
| Circuit breaker execution | — | — | **OWN** |
| News filter / calendar | **OWN** | — | Monitor + pause |
| Session / overnight bans | **OWN** | — | Execute close |
| Market hours schedules | — | — | **OWN** |
| Broker connectivity | — | — | **OWN** |
| Healthchecks / alerts | — | — | **OWN** |
| Profit target rules | **OWN** | Input | — |
| Prop firm rule versioning | **OWN** | — | — |
| Audit trail & reporting | **OWN** | Log risk events | Log ops events |
| Stress test / MC scenarios | — | **OWN** | — |
