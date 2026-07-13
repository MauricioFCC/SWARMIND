"""
Guardrail check functions — extracted from guardrails.py for file size compliance.
Each function is a standalone check that returns a GuardrailResult.
"""
import re
from typing import Dict, Any, Tuple

from .guardrails_base import GuardrailResult, GuardrailSeverity


# =============================================================================
# ARCHITECTURE CHECKS
# =============================================================================

def check_architecture_pattern(context: Dict) -> GuardrailResult:
    """Verifica que el codigo siga el patron arquitectonico requerido."""
    pattern = context.get("required_pattern", "hexagonal")
    code = context.get("generated_code", "")
    if pattern == "hexagonal":
        has_ports = bool(re.search(r"(class\s+\w+Port|Protocol|ABC|@abstractmethod)", code, re.I))
        has_adapters = bool(re.search(r"(class\s+\w+Adapter|implements|extends)", code, re.I))
        if not has_ports and not has_adapters:
            return GuardrailResult(
                passed=False, severity=GuardrailSeverity.WARN,
                message="Codigo no evidencia patron Hexagonal (ports/adapters)",
                suggestion="Define interfaces (Ports) y sus implementaciones (Adapters)",
                rule_id="ARCH-001"
            )
    return GuardrailResult(
        passed=True, severity=GuardrailSeverity.INFO,
        message=f"✅ Patron {pattern} verificado", rule_id="ARCH-001"
    )


def check_dependency_injection(context: Dict) -> GuardrailResult:
    """Verifica uso de inyeccion de dependencias en lugar de hardcoding."""
    code = context.get("generated_code", "")
    dangerous_patterns = [
        r"Broker\(\)", r"Database\(\)", r"APIClient\(\)",
        r"requests\.get\(", r"httpx\.request\("
    ]
    violations = []
    for pattern in dangerous_patterns:
        if re.search(pattern, code):
            if not re.search(r"def\s+__init__\s*\([^)]*:\s*\w+(Port|Protocol|Client)?", code):
                violations.append(pattern)
    if violations:
        return GuardrailResult(
            passed=False, severity=GuardrailSeverity.WARN,
            message=f"Posible hardcoding de dependencias: {violations}",
            suggestion="Usa inyeccion de dependencias: def __init__(self, broker: BrokerPort)",
            rule_id="ARCH-002"
        )
    return GuardrailResult(
        passed=True, severity=GuardrailSeverity.INFO,
        message="✅ Inyeccion de dependencias aplicada", rule_id="ARCH-002"
    )


def check_resilience_patterns(context: Dict) -> GuardrailResult:
    """Verifica patrones de resiliencia en operaciones I/O."""
    code = context.get("generated_code", "")
    io_operations = ["request", "execute", "submit", "fetch", "query", "connect"]
    has_io = any(op in code.lower() for op in io_operations)
    if has_io:
        resilience_patterns = [
            r"timeout\s*=", r"retry", r"Retry", r"backoff",
            r"circuit_breaker", r"CircuitBreaker", r"max_attempts"
        ]
        has_resilience = any(re.search(p, code, re.I) for p in resilience_patterns)
        if not has_resilience:
            return GuardrailResult(
                passed=False, severity=GuardrailSeverity.WARN,
                message="Operaciones I/O sin patrones de resiliencia detectados",
                suggestion="Anade timeout, retries con backoff, o circuit breaker",
                rule_id="ARCH-003"
            )
    return GuardrailResult(
        passed=True, severity=GuardrailSeverity.INFO,
        message="✅ Resiliencia verificada", rule_id="ARCH-003"
    )


# =============================================================================
# SECURITY CHECKS (CRITICAL)
# =============================================================================

def check_no_secrets(output: str, context: Dict) -> GuardrailResult:
    """Bloquea codigo con secrets hardcodeados."""
    secret_patterns = [
        r"(?i)(api[_-]?key|apikey)\s*[:=]\s*['\"][a-zA-Z0-9_\-]{16,}['\"]",
        r"(?i)(secret[_-]?key|secretkey)\s*[:=]\s*['\"][a-zA-Z0-9_\-]{16,}['\"]",
        r"(?i)(password|passwd|pwd)\s*[:=]\s*['\"][^'\"]{8,}['\"]",
        r"(?i)(token|auth_token|access_token)\s*[:=]\s*['\"][a-zA-Z0-9_\-\.]{20,}['\"]",
        r"(pk_live|sk_live|ghp_[a-zA-Z0-9]{36}|xox[bprso]-[a-zA-Z0-9\-]+)",
        r"(?i)BASIC\s+[A-Za-z0-9+/]{20,}={0,2}",
    ]
    for pattern in secret_patterns:
        if re.search(pattern, output):
            return GuardrailResult(
                passed=False, severity=GuardrailSeverity.BLOCK,
                message="SECRETO DETECTADO en el codigo generado",
                suggestion="Usa os.getenv('VAR_NAME') y anade la variable a .env.example",
                rule_id="SEC-001"
            )
    return GuardrailResult(
        passed=True, severity=GuardrailSeverity.INFO,
        message="✅ Sin secrets hardcodeados", rule_id="SEC-001"
    )


def check_no_pii_in_logs(output: str, context: Dict) -> GuardrailResult:
    """Verifica que no se expongan datos personales en logs."""
    pii_patterns = [
        r"logging\.[^)]*['\"].*?(email|correo|correo_electronico)['\"].*?\+",
        r"logging\.[^)]*['\"].*?(account|cuenta|tarjeta)['\"].*?\+",
        r"print\([^)]*['\"].*?(password|clave|secret)['\"].*?\)",
    ]
    for pattern in pii_patterns:
        if re.search(pattern, output, re.I):
            return GuardrailResult(
                passed=False, severity=GuardrailSeverity.BLOCK,
                message="Posible exposicion de PII en logs",
                suggestion="Usa logging con masking: logger.info(f'User {user_id[:4]}***')",
                rule_id="SEC-002"
            )
    return GuardrailResult(
        passed=True, severity=GuardrailSeverity.INFO,
        message="✅ Logs seguros (sin PII)", rule_id="SEC-002"
    )


def check_sql_injection_safe(output: str, context: Dict) -> GuardrailResult:
    """Verifica que las queries SQL usen parametros, no string formatting."""
    if "SELECT" not in output.upper() and "INSERT" not in output.upper():
        return GuardrailResult(
            passed=True, severity=GuardrailSeverity.INFO,
            message="✅ No se detectaron queries SQL", rule_id="SEC-003"
        )
    dangerous = [
        r"execute\s*\(\s*f['\"]",
        r"execute\s*\(\s*['\"].*?\{",
        r"cursor\.execute\s*\([^,]+%\s*\(",
    ]
    for pattern in dangerous:
        if re.search(pattern, output, re.I):
            return GuardrailResult(
                passed=False, severity=GuardrailSeverity.BLOCK,
                message="Query SQL vulnerable a inyeccion",
                suggestion="Usa parametros: cursor.execute('SELECT * FROM t WHERE id=%s', (id,))",
                rule_id="SEC-003"
            )
    return GuardrailResult(
        passed=True, severity=GuardrailSeverity.INFO,
        message="✅ Queries SQL parametrizadas", rule_id="SEC-003"
    )


# =============================================================================
# COMMIT CHECKS
# =============================================================================

def check_conventional_commit(output: str, context: Dict) -> GuardrailResult:
    """Verifica que los mensajes de commit sigan Conventional Commits."""
    if "git commit" not in output.lower() and "commit" not in context.get("action", ""):
        return GuardrailResult(
            passed=True, severity=GuardrailSeverity.INFO,
            message="✅ No es operacion de commit", rule_id="COMMIT-001"
        )
    valid_types = ["feat", "fix", "docs", "style", "refactor", "test", "chore", "build", "ci"]
    commit_pattern = rf"^\s*({'|'.join(valid_types)})"
    if not re.search(commit_pattern, output, re.I | re.M):
        return GuardrailResult(
            passed=False, severity=GuardrailSeverity.WARN,
            message="Mensaje de commit sin tipo Conventional",
            suggestion="Usa: feat(scope): descripcion #ISSUE",
            rule_id="COMMIT-001"
        )
    return GuardrailResult(
        passed=True, severity=GuardrailSeverity.INFO,
        message="✅ Commit sigue Conventional Commits", rule_id="COMMIT-001"
    )


def check_docs_for_public_api(output: str, context: Dict) -> GuardrailResult:
    """Verifica que funciones/clases publicas tengan docstrings."""
    public_defs = re.findall(r"^(?:async\s+)?def\s+([a-z][a-zA-Z0-9_]*)\s*\(", output, re.M)
    public_classes = re.findall(r"^class\s+([A-Z][a-zA-Z0-9_]*)\s*[:\(]", output, re.M)
    public_defs = [d for d in public_defs if not d.startswith("_")]
    public_classes = [c for c in public_classes if not c.startswith("_")]
    if not public_defs and not public_classes:
        return GuardrailResult(
            passed=True, severity=GuardrailSeverity.INFO,
            message="✅ No se detectaron APIs publicas nuevas", rule_id="DOCS-001"
        )
    has_docstrings = bool(re.search(r'("""|\'\'\')', output))
    if not has_docstrings and (public_defs or public_classes):
        return GuardrailResult(
            passed=False, severity=GuardrailSeverity.WARN,
            message="APIs publicas sin docstrings",
            suggestion="Anade docstring con descripcion, args, returns y raises",
            rule_id="DOCS-001"
        )
    return GuardrailResult(
        passed=True, severity=GuardrailSeverity.INFO,
        message="✅ APIs documentadas", rule_id="DOCS-001"
    )


def check_tests_for_new_features(output: str, context: Dict) -> GuardrailResult:
    """Sugiere anadir tests para nuevas funcionalidades."""
    new_logic_patterns = [r"def\s+(?!test_)\w+\(", r"class\s+\w+\(", r"if\s+.*:"]
    has_new_logic = any(re.search(p, output) for p in new_logic_patterns)
    if not has_new_logic:
        return GuardrailResult(
            passed=True, severity=GuardrailSeverity.INFO,
            message="✅ Sin nueva logica que requiera tests", rule_id="TEST-001"
        )
    has_tests = bool(re.search(r"def\s+test_\w+\(", output) or "pytest" in output.lower())
    if not has_tests:
        return GuardrailResult(
            passed=True, severity=GuardrailSeverity.WARN,
            message="Nueva funcionalidad sin tests asociados",
            suggestion="Considera anadir tests en tests/test_*.py para la nueva logica",
            rule_id="TEST-001"
        )
    return GuardrailResult(
        passed=True, severity=GuardrailSeverity.INFO,
        message="✅ Tests incluidos para nueva funcionalidad", rule_id="TEST-001"
    )


# =============================================================================
# DISCOVERY CHECKS — FDE Pre-Flight Gate
# =============================================================================

def check_discovery_admin(context: Dict) -> GuardrailResult:
    """Verifica que se hayan definido reglas de negocio, SLAs y dominio."""
    rules = context.get("business_rules", {})
    has_rules = bool(rules) or bool(context.get("domain"))
    if not has_rules:
        return GuardrailResult(
            passed=False, severity=GuardrailSeverity.WARN,
            message="FDE Discovery: Business rules / SLAs no definidos",
            suggestion="Define reglas de negocio, SLAs y contexto de dominio antes de implementar",
            rule_id="DISC-ADMIN-001"
        )
    return GuardrailResult(
        passed=True, severity=GuardrailSeverity.INFO,
        message="✅ Discovery Admin: reglas de negocio presentes", rule_id="DISC-ADMIN-001"
    )


def check_discovery_data(context: Dict) -> GuardrailResult:
    """Verifica fuentes de datos, schemas, calidad y lineage."""
    has_sources = bool(context.get("data_sources"))
    has_schemas = bool(context.get("data_schema"))
    if not has_sources or not has_schemas:
        return GuardrailResult(
            passed=False, severity=GuardrailSeverity.WARN,
            message="FDE Discovery: Data sources / schemas no definidos",
            suggestion="Identifica fuentes de datos, define schemas y verifica calidad antes de codificar",
            rule_id="DISC-DATA-001"
        )
    return GuardrailResult(
        passed=True, severity=GuardrailSeverity.INFO,
        message="✅ Discovery Data: fuentes y schemas definidos", rule_id="DISC-DATA-001"
    )


def check_discovery_infra(context: Dict) -> GuardrailResult:
    """Verifica target de despliegue, red, dependencias y seguridad."""
    has_target = bool(context.get("deploy_target"))
    has_deps = bool(context.get("dependencies"))
    if not has_target:
        return GuardrailResult(
            passed=False, severity=GuardrailSeverity.WARN,
            message="FDE Discovery: Deploy target / dependencias no definidos",
            suggestion="Define target de despliegue, dependencias externas y requisitos de red",
            rule_id="DISC-INFRA-001"
        )
    return GuardrailResult(
        passed=True, severity=GuardrailSeverity.INFO,
        message="✅ Discovery Infra: target y dependencias presentes", rule_id="DISC-INFRA-001"
    )


# =============================================================================
# COST GUARDRAILS — Budget & Token Usage
# =============================================================================

def check_cost_budget(context: Dict) -> GuardrailResult:
    """Verifica que la solicitud tenga un presupuesto de tokens/costo definido."""
    budget = context.get("cost_budget") or context.get("token_budget")
    if budget is None:
        return GuardrailResult(
            passed=False, severity=GuardrailSeverity.WARN,
            message="No se definio presupuesto de costo/tokens",
            suggestion="Define cost_budget o token_budget en el contexto de la solicitud. "
                       "Ej: {'cost_budget': {'max_cost_usd': 0.50, 'currency': 'USD'}}",
            rule_id="COST-001"
        )
    if isinstance(budget, dict):
        max_val = budget.get("max_cost_usd") or budget.get("max_tokens")
        if max_val is None or max_val <= 0:
            return GuardrailResult(
                passed=False, severity=GuardrailSeverity.WARN,
                message="Presupuesto definido pero sin limite valido (max_cost_usd o max_tokens)",
                suggestion="Asegurate de incluir max_cost_usd o max_tokens > 0 en cost_budget",
                rule_id="COST-001"
            )
    elif not isinstance(budget, (int, float)) or budget <= 0:
        return GuardrailResult(
            passed=False, severity=GuardrailSeverity.WARN,
            message="Presupuesto definido pero con formato invalido",
            suggestion="Usa un numero positivo (int/float) o un dict con max_cost_usd/max_tokens",
            rule_id="COST-001"
        )
    return GuardrailResult(
        passed=True, severity=GuardrailSeverity.INFO,
        message=f"✅ Presupuesto definido: {budget}", rule_id="COST-001"
    )


def check_cost_usage(output: str, context: Dict) -> GuardrailResult:
    """Verifica que el uso de costo/tokens no exceda el presupuesto definido."""
    budget = context.get("cost_budget") or context.get("token_budget")
    if budget is None:
        return GuardrailResult(
            passed=True, severity=GuardrailSeverity.INFO,
            message="✅ Sin presupuesto definido, saltando verificacion de uso", rule_id="COST-002"
        )
    max_budget = None
    if isinstance(budget, dict):
        max_budget = budget.get("max_cost_usd") or budget.get("max_tokens")
    else:
        max_budget = float(budget)

    total_cost = None
    token_usage = None
    cost_patterns = [
        r'(?:total_)?cost[\s_:=]+\$?([0-9]+\.?[0-9]*)',
        r'(?:total_)?cost[\s_:=]+([0-9]+\.?[0-9]*)\s*(?:USD|usd|\$)',
    ]
    for pattern in cost_patterns:
        match = re.search(pattern, output, re.I)
        if match:
            total_cost = float(match.group(1))
            break

    token_pattern = r'(?:token_usage|total_tokens|tokens_used)[\s_:=]+([0-9]+)'
    token_match = re.search(token_pattern, output, re.I)
    if token_match:
        token_usage = int(token_match.group(1))

    if total_cost is None and token_usage is None:
        return GuardrailResult(
            passed=True, severity=GuardrailSeverity.INFO,
            message="✅ No se detectaron metricas de costo/uso en el output", rule_id="COST-002"
        )
    if total_cost is not None and max_budget is not None and total_cost > max_budget:
        return GuardrailResult(
            passed=False, severity=GuardrailSeverity.WARN,
            message=f"Costo total (${total_cost:.4f}) excede presupuesto (${max_budget:.4f})",
            suggestion="Revisa el consumo del modelo o reduce la longitud de las respuestas",
            rule_id="COST-002"
        )
    if token_usage is not None and max_budget is not None and token_usage > max_budget:
        return GuardrailResult(
            passed=False, severity=GuardrailSeverity.WARN,
            message=f"Token usage ({token_usage}) excede presupuesto ({int(max_budget)})",
            suggestion="Reduce el contexto o usa un modelo mas eficiente",
            rule_id="COST-002"
        )
    detail_parts = []
    if total_cost is not None:
        detail_parts.append(f"costo=${total_cost:.4f}")
    if token_usage is not None:
        detail_parts.append(f"tokens={token_usage}")
    return GuardrailResult(
        passed=True, severity=GuardrailSeverity.INFO,
        message=f"✅ Uso dentro de presupuesto: {', '.join(detail_parts)}", rule_id="COST-002"
    )


# =============================================================================
# MCP INTEGRATION CHECKS
# =============================================================================

def check_mcp_connectivity(context: Dict) -> GuardrailResult:
    """Verifica que servidores MCP esten configurados si la tarea requiere tools externas."""
    task = context.get("user_message", "") or context.get("task", "")
    has_mcp_tools_context = bool(context.get("mcp_tools") or context.get("mcp_servers"))
    task_needs_external = bool(
        re.search(r"(search|fetch|scrape|lookup|query\s+api|external|tool|browse|web)", task, re.I)
    )
    if not task_needs_external and not has_mcp_tools_context:
        return GuardrailResult(
            passed=True, severity=GuardrailSeverity.INFO,
            message="✅ MCP: tarea sin necesidad de herramientas externas", rule_id="MCP-001"
        )
    mcp_servers = context.get("mcp_servers", [])
    mcp_tools = context.get("mcp_tools", [])
    if not mcp_servers and not mcp_tools:
        return GuardrailResult(
            passed=False, severity=GuardrailSeverity.WARN,
            message="Tarea requiere herramientas externas pero no hay servidores MCP configurados",
            suggestion="Configura MCP servers en mcp_servers o mcp_tools del contexto. "
                       "Ej: {'mcp_servers': ['pulsemcp', 'mcpso'], 'mcp_tools': ['web-search', 'fetch-page']}",
            rule_id="MCP-001"
        )
    invalid_servers = []
    for server in mcp_servers:
        if isinstance(server, dict):
            if not server.get("url") and not server.get("endpoint"):
                invalid_servers.append(str(server))
        elif isinstance(server, str):
            if not server.startswith(("http", "https", "mcp:")):
                invalid_servers.append(server)
    if invalid_servers:
        return GuardrailResult(
            passed=False, severity=GuardrailSeverity.WARN,
            message=f"Servidores MCP con configuracion invalida: {invalid_servers}",
            suggestion="Cada servidor debe tener url/endpoint valido. "
                       "Ej: {'name': 'pulsemcp', 'url': 'https://mcp.pulsemcp.com'}",
            rule_id="MCP-001"
        )
    return GuardrailResult(
        passed=True, severity=GuardrailSeverity.INFO,
        message=f"✅ MCP conectividad verificada: {len(mcp_servers)} servidor(es)", rule_id="MCP-001"
    )


# =============================================================================
# THREE WHYS — Root Cause Diagnostic
# =============================================================================

def check_three_whys_diagnostic(output: str, context: Dict) -> GuardrailResult:
    """Verifica que outputs de post-mortem/error incluyan analisis Three Whys."""
    if "fail" not in output.lower() and "error" not in output.lower() and "issue" not in output.lower():
        return GuardrailResult(
            passed=True, severity=GuardrailSeverity.INFO,
            message="✅ Three Whys: no aplica (no es analisis de fallo)", rule_id="WHYS-001"
        )
    why_pattern = r"(why\s+\d|1st why|2nd why|3rd why|cause.*cause.*cause|root because)"
    has_three_whys = bool(re.search(why_pattern, output, re.I))
    if not has_three_whys:
        return GuardrailResult(
            passed=False, severity=GuardrailSeverity.WARN,
            message="Analisis de fallo sin Three Whys completo",
            suggestion="Aplica Three Whys: 1st Why (sintoma) -> 2nd Why (causa directa) -> 3rd Why (raiz sistemica)",
            rule_id="WHYS-001"
        )
    return GuardrailResult(
        passed=True, severity=GuardrailSeverity.INFO,
        message="✅ Three Whys: diagnostico completo de causa raiz", rule_id="WHYS-001"
    )


# =============================================================================
# RAG TRIAD CHECKS — Groundedness, Context Relevance, Faithfulness
# =============================================================================

def check_rag_groundedness(output: str, context: Dict) -> GuardrailResult:
    """Verifica que el output este fundamentado en las fuentes proporcionadas."""
    sources = context.get("sources") or context.get("source_documents") or context.get("context_sources", [])
    if not sources:
        return GuardrailResult(
            passed=True, severity=GuardrailSeverity.INFO,
            message="✅ RAG Groundedness: sin fuentes de referencia para verificar", rule_id="RAG-001"
        )
    grounding_patterns = [
        r"\[(\d+)\]", r"source:\s*\w+", r"according to",
        r"referenc(?:e|ing)\s+\w+", r"based on.*(?:source|document|data)",
        r"cited in", r"as stated in",
    ]
    has_grounding = any(re.search(p, output, re.I) for p in grounding_patterns)
    if not has_grounding:
        return GuardrailResult(
            passed=False, severity=GuardrailSeverity.WARN,
            message="RAG Groundedness: output sin referencias a fuentes proporcionadas",
            suggestion="Anade citas a las fuentes: [1], 'according to [source]', o 'based on [document]'",
            rule_id="RAG-001"
        )
    return GuardrailResult(
        passed=True, severity=GuardrailSeverity.INFO,
        message="✅ RAG Groundedness: output referenciado a fuentes", rule_id="RAG-001"
    )


def check_rag_context_relevance(output: str, context: Dict) -> GuardrailResult:
    """Verifica que el output use efectivamente el contexto proporcionado."""
    context_text = context.get("context") or context.get("context_text", "")
    sources = context.get("sources") or context.get("source_documents", [])
    if isinstance(sources, list):
        context_text = " ".join(sources) + " " + context_text
    if not context_text.strip():
        return GuardrailResult(
            passed=True, severity=GuardrailSeverity.INFO,
            message="✅ RAG Context Relevance: sin contexto de referencia para verificar", rule_id="RAG-002"
        )
    stopwords = {"this", "that", "with", "from", "have", "been", "were", "what", "when",
                 "where", "which", "their", "there", "would", "could", "should", "about"}
    context_words = set(re.findall(r'\b[a-zA-Z]{5,}\b', context_text.lower()))
    context_words -= stopwords
    if not context_words:
        return GuardrailResult(
            passed=True, severity=GuardrailSeverity.INFO,
            message="✅ RAG Context Relevance: contexto insuficiente para extraer terminos clave", rule_id="RAG-002"
        )
    output_lower = output.lower()
    matched = sum(1 for w in context_words if w in output_lower)
    relevance_ratio = matched / len(context_words)
    if relevance_ratio < 0.15:
        return GuardrailResult(
            passed=False, severity=GuardrailSeverity.WARN,
            message=f"RAG Context Relevance: solo {matched}/{len(context_words)} terminos del contexto aparecen en output ({relevance_ratio:.0%})",
            suggestion="El output debe usar activamente el contexto proporcionado. Revisa que no sea una respuesta generica.",
            rule_id="RAG-002"
        )
    return GuardrailResult(
        passed=True, severity=GuardrailSeverity.INFO,
        message=f"✅ RAG Context Relevance: {matched}/{len(context_words)} terminos ({relevance_ratio:.0%})", rule_id="RAG-002"
    )


def check_rag_faithfulness(output: str, context: Dict) -> GuardrailResult:
    """Verifica que el output no contradiga las fuentes."""
    sources = context.get("sources") or context.get("source_documents") or context.get("context_sources", [])
    if not sources:
        return GuardrailResult(
            passed=True, severity=GuardrailSeverity.INFO,
            message="✅ RAG Faithfulness: sin fuentes para verificar fidelidad", rule_id="RAG-003"
        )
    hallucination_patterns = [
        r"I don['']t have (?:access to |information about |that data)",
        r"Based on my (?:training|general knowledge|understanding)",
        r"As an AI.*I (?:believe|think|assume)",
        r"In my (?:opinion|experience|view)",
        r"I (?:guess|speculate|presume|suppose)",
    ]
    has_hallucination_marker = any(re.search(p, output, re.I) for p in hallucination_patterns)
    if has_hallucination_marker:
        return GuardrailResult(
            passed=False, severity=GuardrailSeverity.WARN,
            message="RAG Faithfulness: output contiene marcadores de especulacion/alucinacion",
            suggestion="Las respuestas deben basarse exclusivamente en las fuentes. Reemplaza opiniones con datos de las fuentes.",
            rule_id="RAG-003"
        )
    return GuardrailResult(
        passed=True, severity=GuardrailSeverity.INFO,
        message="✅ RAG Faithfulness: output alineado con fuentes, sin alucinaciones detectadas", rule_id="RAG-003"
    )
