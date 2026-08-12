"""Agent Discovery keywords — mapas de dominios y capacidades.

Extraccion mecanica del modulo original
``harness/orchestrator/agent_discovery.py`` (sin cambios de logica
ni firmas): mapas usados por la inferencia desde contenido.
"""
from __future__ import annotations

# Mapa de dominios por keywords en el contenido del .md
_DOMAIN_KEYWORDS: list[tuple[list[str], str]] = [
    (["quantitative", "trading", "strategy", "broker", "order", "signal", "backtest"], "quantitative-analysis"),
    (["risk", "position sizing", "drawdown", "exposure", "kelly"], "risk-management"),
    (["trading", "monitoring", "alert", "live", "market", "operation"], "trading"),
    (["architecture", "system design", "c4", "adr", "enterprise", "roadmap"], "architecture"),
    (["machine learning", "model", "ai", "pipeline", "llm", "training", "inference"], "ai-ml"),
    (["api", "endpoint", "software", "full-stack", "microservice", "backend"], "software-engineering"),
    (["ui", "frontend", "dashboard", "component", "visualization"], "frontend"),
    (["data", "schema", "migration", "model", "database", "etl"], "data-engineering"),
    (["devops", "ci/cd", "docker", "kubernetes", "deploy", "infrastructure"], "devops"),
    (["security", "vulnerability", "compliance", "audit", "secret", "hardening"], "security"),
    (["test", "quality", "coverage", "qa", "gate", "regression"], "quality"),
    (["documentation", "docs", "manual", "technical writing", "readme"], "documentation"),
    (["mobile", "ios", "android", "app", "react native", "flutter"], "mobile"),
    (["requirements", "analysis", "feasibility", "proposal", "user story"], "requirements"),
    (["context", "prompt", "token", "rag", "budget"], "context-engineering"),
    (["tool", "mcp", "server", "json-rpc"], "tool-mcp"),
    (["evolve", "improvement", "cognition", "experiment", "evolution"], "evolve"),
    (["project manager", "planning", "delegate", "coordinate", "roadmap"], "project-management"),
]

# Mapa de capacidades por keywords en el contenido
_CAPABILITY_KEYWORDS: list[tuple[str, str]] = [
    # software-engineer
    (r"\bapi\b", "api_development"),
    (r"\bendpoint\b", "api_development"),
    (r"\bfull.?stack\b", "full_stack"),
    (r"\bmicroservice", "microservices"),
    (r"\bci/cd\b", "ci_cd"),
    (r"\btesting\b", "testing"),
    (r"\brefactor", "refactoring"),
    # security-engineer
    (r"\bsecurity\b", "security_audit"),
    (r"\bvulnerabilit", "vulnerability_scan"),
    (r"\bcompliance\b", "compliance_check"),
    (r"\bthreat\b", "threat_modeling"),
    (r"\bhardening\b", "hardening"),
    # data-architect
    (r"\bschema\b", "data_modeling"),
    (r"\bmigration", "migration_design"),
    (r"\betl\b", "etl_pipeline"),
    (r"\bdatabase\b", "schema_design"),
    # devops-sre
    (r"\bdocker\b", "docker_kubernetes"),
    (r"\bkubernetes\b", "docker_kubernetes"),
    (r"\bci/cd\b", "ci_cd_pipeline"),
    (r"\bmonitoring\b", "monitoring"),
    (r"\bobservability\b", "observability"),
    (r"\bterraform\b", "infrastructure_as_code"),
    # ai-engineer
    (r"\bmachine learning\b", "ml_pipeline"),
    (r"\bmodel\b", "model_training"),
    (r"\bllm\b", "llm_ops"),
    (r"\binference\b", "inference_optimization"),
    (r"\bfeature engineering\b", "feature_engineering"),
    # quant-developer
    (r"\bstrateg", "strategy_implementation"),
    (r"\border\b", "order_execution"),
    (r"\bbroker\b", "broker_integration"),
    (r"\bbacktest", "backtesting"),
    # frontend-engineer
    (r"\bui\b", "ui_development"),
    (r"\bdashboard\b", "dashboard"),
    (r"\bvisualization\b", "visualization"),
    (r"\bcomponent\b", "component_design"),
    # general
    (r"\bdocumentation\b", "documentation"),
    (r"\bquality\b", "quality_assurance"),
    (r"\bplan", "planning"),
    (r"\brisk\b", "risk_assessment"),
]
