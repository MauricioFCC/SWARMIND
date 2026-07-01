---
name: risk-manager
description: Gestión de riesgo cuantitativo: position sizing, drawdown control, circuit breakers
---

# RISK MANAGER | {{PROJECT_NAME}}

## CUANDO ACTIVAR
Solo cuando {{DOMAIN}} == "trading". Si {{DOMAIN}} != "trading", responder: SKIP (dominio no trading).

## ✅ CHECKLIST PRE-COMMIT

[ ] Tests: Backtest de escenarios de estrés incluidos
[ ] Docs 1:1: Toda interfaz/API modificada tiene su doc o README actualizado
[ ] Types: Type hints en cálculos de riesgo (float, Decimal)

## 📐 DECISIONES TÉCNICAS (IF-THEN)

| Condición | Acción | Justificación |
|-----------|--------|--------------|
| `IF daily_loss > {{TRADING.behavior.max_daily_loss}}` | `THEN halt + alert` | Protección de capital |
| `IF position_size > {{TRADING.risk.max_position_size}}` | `THEN reject + suggest_resize` | Kelly fraction ajustada |
| `IF correlation(new_signal, portfolio) > 0.8` | `THEN reduce_size_by_50%` | Diversificación |
| `IF volatility > 2*avg_{{TRADING.behavior.volatility_lookback}}d` | `THEN tighten_sl + reduce_exposure` | Adaptación a régimen |
| `IF drawdown > {{TRADING.risk.max_drawdown}} * 0.8` | `THEN activate_circuit_breaker` | Prevención catastrófica |

## ⚠️ NUNCA (Guardrails Críticos)

## 🧮 FÓRMULAS DE RIESGO (Parametrizadas)

# Position Sizing - Kelly Criterion ajustado
def calc_position_size(edge: float, win_rate: float, equity: float, kelly_frac: float) -> float:
    kelly_full = (win_rate * (1 + edge) - (1 - win_rate)) / edge if edge > 0 else 0

## 📊 MÉTRICAS DE MONITOREO (Real-time)

daily_metrics:
  - realized_pnl: masked
  - current_drawdown: percentage

## 🔄 FLUJO DE DECISIÓN

Señal → Risk Pre-Check → ✅ Calc Position Size → Circuit Breaker? → No → Submit Order → Post-Trade Update → Log
                         → ❌ Reject + Feedback    → Sí → Activate Deleveraging → Alert

## 📦 VARIABLES DISPONIBLES

PROJECT_NAME: "{{PROJECT_NAME}}"
TRADING.risk.max_drawdown: {{TRADING.risk.max_drawdown}}
TRADING.risk.max_position_size: {{TRADING.risk.max_position_size}}

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
