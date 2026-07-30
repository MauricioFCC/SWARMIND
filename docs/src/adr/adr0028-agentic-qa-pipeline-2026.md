# ADR-0028: Swarmind QA Pipeline 5-Capas

## Estado
**ACEPTADO** — Implementado y verificado con 15 tests.

## Contexto
Auditoria de 50 equipos de control de calidad (Julio 2026) revelo:
- **70% estancados en L3** (IA-generativa: ChatGPT para casos, Copilot para localizadores)
- **20% experimentando con L4** (agentes autonomos)
- **5% en L1** (datos/ML)
- **5% construyendo L5** (orquestacion agencial)

Swarmind necesitaba un pipeline QA completo que saltara directamente a L5:
orquestacion de calidad de extremo a extremo con ejecucion autonoma,
deteccion de alucinaciones y autorreparacion.

## Stack QA 5-Capas

```
L5 ─ QAOrchestrator ─ Orquestacion extremo a extremo
L4 ─ AutonomousTestAgent ─ Ejecucion autonoma con MCP
L3 ─ TestCaseGenerator ─ Generacion + guardrails anti-alucinacion
L2 ─ VisualAnomalyDetector ─ Deteccion de patrones anomalos
L1 ─ FailurePredictor ─ Prediccion de fallos antes de ejecutar
```

### L1 — FailurePredictor (AI/ML)
Predice probabilidad de fallo por target usando:
- Historial de ejecuciones previas (tasa de fallo historica)
- Complejidad ciclomatica normalizada [0, 1]
- Ratio de cambios recientes (churn) [0, 1]
- Cobertura de codigo actual [0, 1]
- Pesos: historial 40%, complejidad 25%, churn 20%, cobertura 15%

Returns: `RiskScore` con `probability` [0,1] y `nivel` (BAJO/MEDIO/ALTO)

### L2 — VisualAnomalyDetector (Redes Neuronales)
Detecta anomalias en datos de ejecucion usando:
- DURATION_SPIKE: Picos de duracion en tests
- APPROVAL_DROP: Caidas en tasa de aprobacion
- PATTERN_SHIFT: Cambios en patrones de fallo
- COVERAGE_DRIFT: Deriva de cobertura
- CORRELATED_FAILURE: Fallos correlacionados
- NOISE_FLOOR: Ruido de fondo elevado

Returns: `AnomalyReport` con lista de `AnomalyFinding`

### L3 — TestCaseGenerator (IA Generativa + Guardrails)
Genera casos de prueba con 3 guardrails anti-alucinacion:
1. **No invencion**: Rechaza selectores inventados (data-testid inexistentes)
2. **Palabras prohibidas**: Bloquea comandos destructivos
3. **Limite de longitud**: Rechaza casos excesivamente largos

Arquitectura: Generator → Guardrails → Validator (ToolGuardian pattern)

### L4 — AutonomousTestAgent (Agentes IA)
Ejecuta tests de forma autonoma:
- `run(test_files, parallel, max_workers)` — Ejecucion concurrente
- MCPCommand: Comandos estructurados para tools externas
- Retry con backoff exponencial en fallos
- Reporte consolidado con AgentResult (total, aprobados, fallidos)

### L5 — QAOrchestrator (IA Agencial)
Orquesta las 5 capas en secuencia con pesos:
- L1 15%, L2 20%, L3 15%, L4 50%
- Estados: SUCCESS (>0.8), DEGRADED (>0.5), COMPENSATED (>0), FAILED
- Propagacion de errores y compensacion automatica
- Trazabilidad completa via QAMetadata

## Archivos creados
- `harness/qa/__init__.py` — Entry point, enums, dataclasses base
- `harness/qa/l1_predictor/__init__.py` — FailurePredictor (230 lines)
- `harness/qa/l2_detector/__init__.py` — VisualAnomalyDetector (310 lines)
- `harness/qa/l3_generator/__init__.py` — TestCaseGenerator + Guardrails (374 lines)
- `harness/qa/l4_agent/__init__.py` — AutonomousTestAgent (349 lines)
- `harness/qa/l5_orchestrator/__init__.py` — QAOrchestrator (393 lines)
- `harness/tests/test_qa_pipeline.py` — 15 tests

## Referencias
- Auditoria de 50 equipos QA (Julio 2026): 70% L3, 20% L4, 5% L1, 5% L5
- arXiv:2607.21835 — ToolGuardian: Declarative Security
- arXiv:2607.25446 — IMACS: Organizational Science
- Playwright MCP: arbol de accesibilidad real vs selectores inventados
- ADR-0025: Frontier Coding Quality
