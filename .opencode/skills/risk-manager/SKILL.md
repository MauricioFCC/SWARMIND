---
name: risk-manager
description: Gestión de riesgo cuantitativo: position sizing, drawdown control, circuit breakers
version: 3.0.0
project_agnostic: true
inherit:
  - core/base_skill_template.md
  - core/fde_principles.md

variables:
  - PROJECT_NAME
  - DOMAIN
  - TRADING.risk.max_drawdown
  - TRADING.risk.max_position_size
  - TRADING.behavior.max_daily_loss
  - TRADING.behavior.kelly_fraction
  - TRADING.behavior.volatility_lookback
metadata:
  author: onyx-team
  tags: [risk, quant, analysis]
  dependencies: [project-manager]
---

# RISK MANAGER | {{PROJECT_NAME}}

## CUANDO ACTIVAR
Solo cuando {{DOMAIN}} == "trading". Si {{DOMAIN}} != "trading", responder: SKIP (dominio no trading).

⚡ **ROL**: Gestor de Riesgo Cuantitativo
🎯 **STACK**: Python, NumPy, Pandas | 🏗️ Hexagonal | 🌐 Event-driven
🔀 **STACKING**: Research → Risk → Execution gates
🔄 **FLUJO**: Señal → Risk Check → Size → Execute → Monitor
🛡️ **CAPAS**: Pre-trade validation, Real-time monitoring, Post-trade analysis

---

## ✅ CHECKLIST PRE-COMMIT

```
[ ] Tests: Backtest de escenarios de estrés incluidos
[ ] Docs 1:1: Toda interfaz/API modificada tiene su doc o README actualizado
[ ] Types: Type hints en cálculos de riesgo (float, Decimal)
[ ] Docs: Docstrings con fórmulas y referencias académicas
[ ] Security: 🚫 NO exponer valores reales en logs → usar masking
[ ] Logs: JSON con trace_id para auditoría de decisiones
[ ] Architecture: RiskEngine como Port, implementaciones como Adapters
[ ] Resilience: Circuit breaker si datos de mercado fallan
```

---

## 📐 DECISIONES TÉCNICAS (IF-THEN)

| Condición | Acción | Justificación |
|-----------|--------|--------------|
| `IF daily_loss > {{TRADING.behavior.max_daily_loss}}` | `THEN halt + alert` | Protección de capital |
| `IF position_size > {{TRADING.risk.max_position_size}}` | `THEN reject + suggest_resize` | Kelly fraction ajustada |
| `IF correlation(new_signal, portfolio) > 0.8` | `THEN reduce_size_by_50%` | Diversificación |
| `IF volatility > 2*avg_{{TRADING.behavior.volatility_lookback}}d` | `THEN tighten_sl + reduce_exposure` | Adaptación a régimen |
| `IF drawdown > {{TRADING.risk.max_drawdown}} * 0.8` | `THEN activate_circuit_breaker` | Prevención catastrófica |

---

## ⚠️ NUNCA (Guardrails Críticos)

- position_size = fijo sin cálculo • stop_loss fijo sin volatilidad • panic_close en drawdown
- Exponer valores reales en logs • Reportar posiciones individuales sin agregación
- check_risk_once_per_day() → risk_monitor continuo + event-driven

---

## 🧮 FÓRMULAS DE RIESGO (Parametrizadas)

```python
# Position Sizing - Kelly Criterion ajustado
def calc_position_size(edge: float, win_rate: float, equity: float, kelly_frac: float) -> float:
    kelly_full = (win_rate * (1 + edge) - (1 - win_rate)) / edge if edge > 0 else 0
    return min(equity * kelly_full * kelly_frac, equity * max_position_frac)

# Stop Loss dinámico por volatilidad
def calc_dynamic_sl(entry: float, atr: float, multiplier: float = 2.0) -> float:
    return entry - (atr * multiplier) if entry > 0 else entry + (atr * multiplier)

# Circuit Breaker por drawdown
def check_circuit_breaker(current_dd: float, max_dd: float) -> bool:
    return current_dd > (max_dd * 0.8)
```

---

## 📊 MÉTRICAS DE MONITOREO (Real-time)

```
daily_metrics:
  - realized_pnl: masked
  - current_drawdown: percentage
  - exposure: aggregated
  - correlation: if >2 positions

alert_thresholds:
  - warning: dd at 60% of limit
  - critical: dd at 80% of limit
  - halt: dd at 100% of limit
```

---

## 🔄 FLUJO DE DECISIÓN

```
Señal → Risk Pre-Check → ✅ Calc Position Size → Circuit Breaker? → No → Submit Order → Post-Trade Update → Log
                         → ❌ Reject + Feedback    → Sí → Activate Deleveraging → Alert
```

---

## 📦 VARIABLES DISPONIBLES

```yaml
PROJECT_NAME: "{{PROJECT_NAME}}"
TRADING.risk.max_drawdown: {{TRADING.risk.max_drawdown}}
TRADING.risk.max_position_size: {{TRADING.risk.max_position_size}}
TRADING.behavior.max_daily_loss: {{TRADING.behavior.max_daily_loss}}
TRADING.behavior.kelly_fraction: {{TRADING.behavior.kelly_fraction}}
TRADING.behavior.volatility_lookback: {{TRADING.behavior.volatility_lookback}}
```

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

