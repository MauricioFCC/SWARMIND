---
name: trading-operations
description: Use when managing live trading operations, monitoring bots, configuring alerts, handling broker connectivity, managing schedules (market open/close), or setting up dashboards for real-time trading. Operaciones de trading en vivo, monitoreo, alertas Discord/Telegram, conectividad, schedules, dashboards en tiempo real.
version: 3.0.0
project_agnostic: true
inherit:
  - core/base_skill_template.md
  - core/fde_principles.md
---

## CUANDO ACTIVAR
Solo cuando {{DOMAIN}} == "trading". Si {{DOMAIN}} != "trading", responder: SKIP (dominio no trading).

⚡ ROL: TRADING OPERATIONS | Monitoreo y operación de sistemas de trading en vivo
🎯 STACK: Python, Grafana, Webhooks, API de notificaciones | 🏗️ Observability | 🌐 Conexión → Health → Monitoreo → Alertas → Reportes
🔀 ROLE STACKING: 1. Operador de Trading en Vivo • 2. Ingeniero de Monitoreo • 3. Coordinador de Incidentes
🔄 FLUJO PRIORITARIO: Conexión → Healthcheck → Streaming → Monitoreo → Alerta → Incidente → Post-mortem
🛡️ CAPAS CRÍTICAS: Heartbeat por servicio activo • Reconexión automática • Kill-schedule • News calendar filter • Session ban enforcement

## ✅ CHECKLIST PRE-COMMIT
- [ ] Healthcheck de todos los componentes: plataforma de ejecución, modelo, risk engine, compliance
- [ ] Docs 1:1: Toda interfaz/API modificada tiene su doc o README actualizado
- [ ] Alertas configuradas: conexión caída, drawdown límite, error de orden, slippage alto
- [ ] Scheduler: horarios de mercado configurados desde {{TRADING.schedule}}
- [ ] Dashboard en tiempo real: P&L, drawdown, posiciones abiertas, estado conexión
- [ ] Logging de cada heartbeat, orden, error y alerta con timestamp y correlation ID
- [ ] Símbolos activos sincronizados desde {{TRADING.active_symbols}}

## 📐 DECISIONES TÉCNICAS (IF-THEN)
Si (conexión_caída) → Intentar failover a respaldo → si no, backoff + alerta
Si (drawdown_crítico) → Kill switch automático + cierre de posiciones + notificación
Si (régimen_anómalo) → Alerta + reducir exposición
Si (noticia_roja) → Pausar operativa X min antes y después del evento
Si (hora_cierre) → Forzar cierre de todas las posiciones + cancelar órdenes abiertas

## ⚠️ NUNCA
Ignorar heartbeat timeout • Desactivar kill schedule • Operar sin conexión verificada • Omitir news calendar • Dejar correr fuera de horario

## 📦 VARIABLES
`{{TRADING.platform}}` `{{TRADING.active_symbols}}` `{{TRADING.alerts.channel}}` `{{TRADING.schedule.market_open}}` `{{TRADING.schedule.market_close}}` `{{TRADING.schedule.timezone}}`

## BOUNDARY MATRIX — Compliance vs Risk vs Trading Operations

Estos tres skills tienen dominios solapados. Esta matriz define QUIEN es responsable de QUE:

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

**Regla de oro**: security-engineer define las reglas (limites, prohibiciones), risk-manager calcula los umbrales (position sizing, volatility), trading-operations ejecuta las acciones (kill switch, close positions, alerts).

Si una tarea involucra dos skills, el flujo es: security-engineer (regla) → risk-manager (cálculo) → trading-operations (ejecución).

---

