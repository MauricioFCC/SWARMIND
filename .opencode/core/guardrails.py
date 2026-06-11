"""
Guardrail Pipeline: Pre & Post execution checks for architecture, security, commits & docs.
Enterprise-grade validation for AI-generated code and decisions.
"""
import re
import json
from typing import Callable, Dict, Any, Tuple, List, Optional
from dataclasses import dataclass, field
from enum import Enum


class GuardrailSeverity(Enum):
    BLOCK = "block"      # Detener ejecución inmediatamente
    WARN = "warn"        # Advertir pero continuar
    INFO = "info"        # Solo registrar para observabilidad


@dataclass
class GuardrailResult:
    """Resultado de una verificación de guardrail."""
    passed: bool
    severity: GuardrailSeverity
    message: str
    suggestion: Optional[str] = None
    rule_id: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "severity": self.severity.value,
            "message": self.message,
            "suggestion": self.suggestion,
            "rule_id": self.rule_id
        }


class GuardrailPipeline:
    """Pipeline ejecutable de guardrails con soporte para pre/post checks."""
    
    def __init__(self):
        self._pre_checks: List[Tuple[str, Callable]] = []
        self._post_checks: List[Tuple[str, Callable]] = []
        self._results: List[GuardrailResult] = []
    
    def add_pre(self, rule_id: str, fn: Callable[[Dict], GuardrailResult]):
        """Añade un check pre-ejecución."""
        self._pre_checks.append((rule_id, fn))
    
    def add_post(self, rule_id: str, fn: Callable[[str, Dict], GuardrailResult]):
        """Añade un check post-ejecución."""
        self._post_checks.append((rule_id, fn))
    
    def run_pre(self, context: Dict[str, Any]) -> Tuple[bool, List[GuardrailResult]]:
        """Ejecuta todos los checks pre-ejecución."""
        self._results = []
        blocked = False
        
        for rule_id, check_fn in self._pre_checks:
            try:
                result = check_fn(context)
                result.rule_id = rule_id
                self._results.append(result)
                if result.severity == GuardrailSeverity.BLOCK and not result.passed:
                    blocked = True
            except Exception as e:
                self._results.append(GuardrailResult(
                    passed=False,
                    severity=GuardrailSeverity.WARN,
                    message=f"Error ejecutando {rule_id}: {str(e)}",
                    rule_id=rule_id
                ))
        
        return not blocked, self._results
    
    def run_post(self, output: str, context: Dict[str, Any]) -> Tuple[bool, List[GuardrailResult]]:
        """Ejecuta todos los checks post-ejecución."""
        results = []
        blocked = False
        
        for rule_id, check_fn in self._post_checks:
            try:
                result = check_fn(output, context)
                result.rule_id = rule_id
                results.append(result)
                if result.severity == GuardrailSeverity.BLOCK and not result.passed:
                    blocked = True
            except Exception as e:
                results.append(GuardrailResult(
                    passed=False,
                    severity=GuardrailSeverity.WARN,
                    message=f"Error ejecutando {rule_id}: {str(e)}",
                    rule_id=rule_id
                ))
        
        self._results.extend(results)
        return not blocked, results
    
    def get_summary(self) -> Dict[str, Any]:
        """Obtiene resumen de resultados para logging/observabilidad."""
        return {
            "total_checks": len(self._results),
            "passed": sum(1 for r in self._results if r.passed),
            "failed": sum(1 for r in self._results if not r.passed),
            "blocked": any(r.severity == GuardrailSeverity.BLOCK and not r.passed 
                          for r in self._results),
            "by_severity": {
                s.value: sum(1 for r in self._results if r.severity == s and not r.passed)
                for s in GuardrailSeverity
            },
            "failed_rules": [r.rule_id for r in self._results if not r.passed]
        }


# =============================================================================
# CHECKS DE ARQUITECTURA
# =============================================================================

def check_architecture_pattern(context: Dict) -> GuardrailResult:
    """Verifica que el código siga el patrón arquitectónico requerido."""
    pattern = context.get("required_pattern", "hexagonal")
    code = context.get("generated_code", "")
    
    if pattern == "hexagonal":
        # Verificar presencia de ports/adapters
        has_ports = bool(re.search(r"(class\s+\w+Port|Protocol|ABC|@abstractmethod)", code, re.I))
        has_adapters = bool(re.search(r"(class\s+\w+Adapter|implements|extends)", code, re.I))
        
        if not has_ports and not has_adapters:
            return GuardrailResult(
                passed=False,
                severity=GuardrailSeverity.WARN,
                message="Código no evidencia patrón Hexagonal (ports/adapters)",
                suggestion="Define interfaces (Ports) y sus implementaciones (Adapters)",
                rule_id="ARCH-001"
            )
    
    return GuardrailResult(
        passed=True,
        severity=GuardrailSeverity.INFO,
        message=f"✅ Patrón {pattern} verificado",
        rule_id="ARCH-001"
    )


def check_dependency_injection(context: Dict) -> GuardrailResult:
    """Verifica uso de inyección de dependencias en lugar de hardcoding."""
    code = context.get("generated_code", "")
    
    # Buscar instanciación directa de servicios críticos
    dangerous_patterns = [
        r"Broker\(\)", r"Database\(\)", r"APIClient\(\)",
        r"requests\.get\(", r"httpx\.request\("
    ]
    
    violations = []
    for pattern in dangerous_patterns:
        if re.search(pattern, code):
            # Verificar si está dentro de __init__ con parámetros (aceptable)
            if not re.search(r"def\s+__init__\s*\([^)]*:\s*\w+(Port|Protocol|Client)?", code):
                violations.append(pattern)
    
    if violations:
        return GuardrailResult(
            passed=False,
            severity=GuardrailSeverity.WARN,
            message=f"Posible hardcoding de dependencias: {violations}",
            suggestion="Usa inyección de dependencias: def __init__(self, broker: BrokerPort)",
            rule_id="ARCH-002"
        )
    
    return GuardrailResult(
        passed=True,
        severity=GuardrailSeverity.INFO,
        message="✅ Inyección de dependencias aplicada",
        rule_id="ARCH-002"
    )


def check_resilience_patterns(context: Dict) -> GuardrailResult:
    """Verifica patrones de resiliencia en operaciones I/O."""
    code = context.get("generated_code", "")
    
    # Operaciones que deberían tener resiliencia
    io_operations = ["request", "execute", "submit", "fetch", "query", "connect"]
    has_io = any(op in code.lower() for op in io_operations)
    
    if has_io:
        # Buscar patrones de resiliencia
        resilience_patterns = [
            r"timeout\s*=", r"retry", r"Retry", r"backoff",
            r"circuit_breaker", r"CircuitBreaker", r"max_attempts"
        ]
        has_resilience = any(re.search(p, code, re.I) for p in resilience_patterns)
        
        if not has_resilience:
            return GuardrailResult(
                passed=False,
                severity=GuardrailSeverity.WARN,
                message="Operaciones I/O sin patrones de resiliencia detectados",
                suggestion="Añade timeout, retries con backoff, o circuit breaker",
                rule_id="ARCH-003"
            )
    
    return GuardrailResult(
        passed=True,
        severity=GuardrailSeverity.INFO,
        message="✅ Resiliencia verificada",
        rule_id="ARCH-003"
    )


# =============================================================================
# CHECKS DE SEGURIDAD (CRÍTICOS)
# =============================================================================

def check_no_secrets(output: str, context: Dict) -> GuardrailResult:
    """🚫 Bloquea código con secrets hardcodeados."""
    # Patrones de secrets comunes
    secret_patterns = [
        r"(?i)(api[_-]?key|apikey)\s*[:=]\s*['\"][a-zA-Z0-9_\-]{16,}['\"]",
        r"(?i)(secret[_-]?key|secretkey)\s*[:=]\s*['\"][a-zA-Z0-9_\-]{16,}['\"]",
        r"(?i)(password|passwd|pwd)\s*[:=]\s*['\"][^'\"]{8,}['\"]",
        r"(?i)(token|auth_token|access_token)\s*[:=]\s*['\"][a-zA-Z0-9_\-\.]{20,}['\"]",
        r"(pk_live|sk_live|ghp_[a-zA-Z0-9]{36}|xox[bprso]-[a-zA-Z0-9\-]+)",
        r"(?i)BASIC\s+[A-Za-z0-9+/]{20,}={0,2}",  # Basic auth encoded
    ]
    
    for pattern in secret_patterns:
        if re.search(pattern, output):
            return GuardrailResult(
                passed=False,
                severity=GuardrailSeverity.BLOCK,
                message="🚫 SECRETO DETECTADO en el código generado",
                suggestion="Usa os.getenv('VAR_NAME') y añade la variable a .env.example",
                rule_id="SEC-001"
            )
    
    return GuardrailResult(
        passed=True,
        severity=GuardrailSeverity.INFO,
        message="✅ Sin secrets hardcodeados",
        rule_id="SEC-001"
    )


def check_no_pii_in_logs(output: str, context: Dict) -> GuardrailResult:
    """Verifica que no se expongan datos personales en logs."""
    # Patrones de PII que no deberían aparecer en logs
    pii_patterns = [
        r"logging\.[^)]*['\"].*?(email|correo|correo_electronico)['\"].*?\+",
        r"logging\.[^)]*['\"].*?(account|cuenta|tarjeta)['\"].*?\+",
        r"print\([^)]*['\"].*?(password|clave|secret)['\"].*?\)",
    ]
    
    for pattern in pii_patterns:
        if re.search(pattern, output, re.I):
            return GuardrailResult(
                passed=False,
                severity=GuardrailSeverity.BLOCK,
                message="🚫 Posible exposición de PII en logs",
                suggestion="Usa logging con masking: logger.info(f'User {user_id[:4]}***')",
                rule_id="SEC-002"
            )
    
    return GuardrailResult(
        passed=True,
        severity=GuardrailSeverity.INFO,
        message="✅ Logs seguros (sin PII)",
        rule_id="SEC-002"
    )


def check_sql_injection_safe(output: str, context: Dict) -> GuardrailResult:
    """Verifica que las queries SQL usen parámetros, no string formatting."""
    if "SELECT" not in output.upper() and "INSERT" not in output.upper():
        return GuardrailResult(
            passed=True,
            severity=GuardrailSeverity.INFO,
            message="✅ No se detectaron queries SQL",
            rule_id="SEC-003"
        )
    
    # Patrones peligrosos
    dangerous = [
        r"execute\s*\(\s*f['\"]",  # f-string en execute
        r"execute\s*\(\s*['\"].*?\{",  # .format() implícito
        r"cursor\.execute\s*\([^,]+%\s*\(",  # % formatting
    ]
    
    for pattern in dangerous:
        if re.search(pattern, output, re.I):
            return GuardrailResult(
                passed=False,
                severity=GuardrailSeverity.BLOCK,
                message="🚫 Query SQL vulnerable a inyección",
                suggestion="Usa parámetros: cursor.execute('SELECT * FROM t WHERE id=%s', (id,))",
                rule_id="SEC-003"
            )
    
    return GuardrailResult(
        passed=True,
        severity=GuardrailSeverity.INFO,
        message="✅ Queries SQL parametrizadas",
        rule_id="SEC-003"
    )


# =============================================================================
# CHECKS DE COMMIT SEGURO
# =============================================================================

def check_conventional_commit(output: str, context: Dict) -> GuardrailResult:
    """Verifica que los mensajes de commit sigan Conventional Commits."""
    if "git commit" not in output.lower() and "commit" not in context.get("action", ""):
        return GuardrailResult(
            passed=True,
            severity=GuardrailSeverity.INFO,
            message="✅ No es operación de commit",
            rule_id="COMMIT-001"
        )
    
    # Patrones de tipos válidos
    valid_types = ["feat", "fix", "docs", "style", "refactor", "test", "chore", "build", "ci"]
    commit_pattern = rf"^\s*({'|'.join(valid_types)})"
    
    if not re.search(commit_pattern, output, re.I | re.M):
        return GuardrailResult(
            passed=False,
            severity=GuardrailSeverity.WARN,
            message="📝 Mensaje de commit sin tipo Conventional",
            suggestion="Usa: feat(scope): descripción #ISSUE",
            rule_id="COMMIT-001"
        )
    
    return GuardrailResult(
        passed=True,
        severity=GuardrailSeverity.INFO,
        message="✅ Commit sigue Conventional Commits",
        rule_id="COMMIT-001"
    )


def check_docs_for_public_api(output: str, context: Dict) -> GuardrailResult:
    """Verifica que funciones/clases públicas tengan docstrings."""
    # Buscar definiciones públicas
    public_defs = re.findall(r"^(?:async\s+)?def\s+([a-z][a-zA-Z0-9_]*)\s*\(", output, re.M)
    public_classes = re.findall(r"^class\s+([A-Z][a-zA-Z0-9_]*)\s*[:\(]", output, re.M)
    
    # Filtrar privados
    public_defs = [d for d in public_defs if not d.startswith("_")]
    public_classes = [c for c in public_classes if not c.startswith("_")]
    
    if not public_defs and not public_classes:
        return GuardrailResult(
            passed=True,
            severity=GuardrailSeverity.INFO,
            message="✅ No se detectaron APIs públicas nuevas",
            rule_id="DOCS-001"
        )
    
    # Verificar docstrings
    has_docstrings = bool(re.search(r'("""|\'\'\')', output))
    
    if not has_docstrings and (public_defs or public_classes):
        return GuardrailResult(
            passed=False,
            severity=GuardrailSeverity.WARN,
            message="📖 APIs públicas sin docstrings",
            suggestion="Añade docstring con descripción, args, returns y raises",
            rule_id="DOCS-001"
        )
    
    return GuardrailResult(
        passed=True,
        severity=GuardrailSeverity.INFO,
        message="✅ APIs documentadas",
        rule_id="DOCS-001"
    )


def check_tests_for_new_features(output: str, context: Dict) -> GuardrailResult:
    """Sugiere añadir tests para nuevas funcionalidades."""
    # Detectar si se está añadiendo lógica nueva
    new_logic_patterns = [r"def\s+(?!test_)\w+\(", r"class\s+\w+\(", r"if\s+.*:"]
    has_new_logic = any(re.search(p, output) for p in new_logic_patterns)
    
    if not has_new_logic:
        return GuardrailResult(
            passed=True,
            severity=GuardrailSeverity.INFO,
            message="✅ Sin nueva lógica que requiera tests",
            rule_id="TEST-001"
        )
    
    # Verificar si hay tests asociados
    has_tests = bool(re.search(r"def\s+test_\w+\(", output) or "pytest" in output.lower())
    
    if not has_tests:
        return GuardrailResult(
            passed=True,  # No bloquear, solo advertir
            severity=GuardrailSeverity.WARN,
            message="⚠️ Nueva funcionalidad sin tests asociados",
            suggestion="Considera añadir tests en tests/test_*.py para la nueva lógica",
            rule_id="TEST-001"
        )
    
    return GuardrailResult(
        passed=True,
        severity=GuardrailSeverity.INFO,
        message="✅ Tests incluidos para nueva funcionalidad",
        rule_id="TEST-001"
    )


# =============================================================================
# DISCOVERY CHECKLIST — FDE Pre-Flight Gate (Admin, Data, Infra)
# =============================================================================

def check_discovery_admin(context: Dict) -> GuardrailResult:
    """Verifica que se hayan definido reglas de negocio, SLAs y dominio."""
    rules = context.get("business_rules", {})
    has_rules = bool(rules) or bool(context.get("domain"))
    if not has_rules:
        return GuardrailResult(
            passed=False,
            severity=GuardrailSeverity.WARN,
            message="FDE Discovery: Business rules / SLAs no definidos",
            suggestion="Define reglas de negocio, SLAs y contexto de dominio antes de implementar",
            rule_id="DISC-ADMIN-001"
        )
    return GuardrailResult(
        passed=True,
        severity=GuardrailSeverity.INFO,
        message="✅ Discovery Admin: reglas de negocio presentes",
        rule_id="DISC-ADMIN-001"
    )


def check_discovery_data(context: Dict) -> GuardrailResult:
    """Verifica fuentes de datos, schemas, calidad y lineage."""
    has_sources = bool(context.get("data_sources"))
    has_schemas = bool(context.get("data_schema"))
    if not has_sources or not has_schemas:
        return GuardrailResult(
            passed=False,
            severity=GuardrailSeverity.WARN,
            message="FDE Discovery: Data sources / schemas no definidos",
            suggestion="Identifica fuentes de datos, define schemas y verifica calidad antes de codificar",
            rule_id="DISC-DATA-001"
        )
    return GuardrailResult(
        passed=True,
        severity=GuardrailSeverity.INFO,
        message="✅ Discovery Data: fuentes y schemas definidos",
        rule_id="DISC-DATA-001"
    )


def check_discovery_infra(context: Dict) -> GuardrailResult:
    """Verifica target de despliegue, red, dependencias y seguridad."""
    has_target = bool(context.get("deploy_target"))
    has_deps = bool(context.get("dependencies"))
    if not has_target:
        return GuardrailResult(
            passed=False,
            severity=GuardrailSeverity.WARN,
            message="FDE Discovery: Deploy target / dependencias no definidos",
            suggestion="Define target de despliegue, dependencias externas y requisitos de red",
            rule_id="DISC-INFRA-001"
        )
    return GuardrailResult(
        passed=True,
        severity=GuardrailSeverity.INFO,
        message="✅ Discovery Infra: target y dependencias presentes",
        rule_id="DISC-INFRA-001"
    )


# =============================================================================
# COST GUARDRAILS — Budget & Token Usage Enforcement
# =============================================================================
# Inspired by Agent Cost Guardrails (github.com/sapph1re/agent-cost-guardrails)

def check_cost_budget(context: Dict) -> GuardrailResult:
    """Verifica que la solicitud tenga un presupuesto de tokens/costo definido."""
    budget = context.get("cost_budget") or context.get("token_budget")
    if budget is None:
        return GuardrailResult(
            passed=False,
            severity=GuardrailSeverity.WARN,
            message="No se definió presupuesto de costo/tokens",
            suggestion="Define cost_budget o token_budget en el contexto de la solicitud. "
                       "Ej: {'cost_budget': {'max_cost_usd': 0.50, 'currency': 'USD'}}",
            rule_id="COST-001"
        )
    # Validar estructura del budget
    if isinstance(budget, dict):
        max_val = budget.get("max_cost_usd") or budget.get("max_tokens")
        if max_val is None or max_val <= 0:
            return GuardrailResult(
                passed=False,
                severity=GuardrailSeverity.WARN,
                message="Presupuesto definido pero sin límite válido (max_cost_usd o max_tokens)",
                suggestion="Asegúrate de incluir max_cost_usd o max_tokens > 0 en cost_budget",
                rule_id="COST-001"
            )
    elif not isinstance(budget, (int, float)) or budget <= 0:
        return GuardrailResult(
            passed=False,
            severity=GuardrailSeverity.WARN,
            message="Presupuesto definido pero con formato inválido",
            suggestion="Usa un número positivo (int/float) o un dict con max_cost_usd/max_tokens",
            rule_id="COST-001"
        )
    return GuardrailResult(
        passed=True,
        severity=GuardrailSeverity.INFO,
        message=f"✅ Presupuesto definido: {budget}",
        rule_id="COST-001"
    )


def check_cost_usage(output: str, context: Dict) -> GuardrailResult:
    """Verifica que el uso de costo/tokens no exceda el presupuesto definido."""
    budget = context.get("cost_budget") or context.get("token_budget")
    if budget is None:
        return GuardrailResult(
            passed=True,
            severity=GuardrailSeverity.INFO,
            message="✅ Sin presupuesto definido, saltando verificación de uso",
            rule_id="COST-002"
        )
    # Intentar extraer costo total o uso de tokens del output
    max_budget = None
    if isinstance(budget, dict):
        max_budget = budget.get("max_cost_usd") or budget.get("max_tokens")
    else:
        max_budget = float(budget)

    # Buscar métricas de costo en el output
    # Patrones: "total_cost: 0.05", "token_usage: 1500", "cost": 0.03, etc.
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
            passed=True,
            severity=GuardrailSeverity.INFO,
            message="✅ No se detectaron métricas de costo/uso en el output",
            rule_id="COST-002"
        )

    # Verificar contra el presupuesto
    if total_cost is not None and max_budget is not None and total_cost > max_budget:
        return GuardrailResult(
            passed=False,
            severity=GuardrailSeverity.WARN,
            message=f"⚠️ Costo total (${total_cost:.4f}) excede presupuesto (${max_budget:.4f})",
            suggestion="Revisa el consumo del modelo o reduce la longitud de las respuestas",
            rule_id="COST-002"
        )
    if token_usage is not None and max_budget is not None and token_usage > max_budget:
        return GuardrailResult(
            passed=False,
            severity=GuardrailSeverity.WARN,
            message=f"⚠️ Token usage ({token_usage}) excede presupuesto ({int(max_budget)})",
            suggestion="Reduce el contexto o usa un modelo más eficiente",
            rule_id="COST-002"
        )

    detail_parts = []
    if total_cost is not None:
        detail_parts.append(f"costo=${total_cost:.4f}")
    if token_usage is not None:
        detail_parts.append(f"tokens={token_usage}")
    return GuardrailResult(
        passed=True,
        severity=GuardrailSeverity.INFO,
        message=f"✅ Uso dentro de presupuesto: {', '.join(detail_parts)}",
        rule_id="COST-002"
    )


# =============================================================================
# MCP INTEGRATION — External Tool Connectivity Checks
# =============================================================================

def check_mcp_connectivity(context: Dict) -> GuardrailResult:
    """Verifica que servidores MCP estén configurados si la tarea requiere tools externas."""
    task = context.get("user_message", "") or context.get("task", "")
    has_mcp_tools_context = bool(context.get("mcp_tools") or context.get("mcp_servers"))
    task_needs_external = bool(
        re.search(
            r"(search|fetch|scrape|lookup|query\s+api|external|tool|browse|web)",
            task,
            re.I,
        )
    )

    if not task_needs_external and not has_mcp_tools_context:
        return GuardrailResult(
            passed=True,
            severity=GuardrailSeverity.INFO,
            message="✅ MCP: tarea sin necesidad de herramientas externas",
            rule_id="MCP-001"
        )

    # Si la tarea necesita herramientas externas, verificar configuración MCP
    mcp_servers = context.get("mcp_servers", [])
    mcp_tools = context.get("mcp_tools", [])

    if not mcp_servers and not mcp_tools:
        return GuardrailResult(
            passed=False,
            severity=GuardrailSeverity.WARN,
            message="Tarea requiere herramientas externas pero no hay servidores MCP configurados",
            suggestion="Configura MCP servers en mcp_servers o mcp_tools del contexto. "
                       "Ej: {'mcp_servers': ['pulsemcp', 'mcpso'], 'mcp_tools': ['web-search', 'fetch-page']}",
            rule_id="MCP-001"
        )

    # Verificar que los servidores tengan endpoints válidos
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
            passed=False,
            severity=GuardrailSeverity.WARN,
            message=f"Servidores MCP con configuración inválida: {invalid_servers}",
            suggestion="Cada servidor debe tener url/endpoint válido. Ej: "
                       "{'name': 'pulsemcp', 'url': 'https://mcp.pulsemcp.com'}",
            rule_id="MCP-001"
        )
    return GuardrailResult(
        passed=True,
        severity=GuardrailSeverity.INFO,
        message=f"✅ MCP conectividad verificada: {len(mcp_servers)} servidor(es)",
        rule_id="MCP-001"
    )


# =============================================================================
# THREE WHYS — Root Cause Diagnostic (Post-Execution)
# =============================================================================

def check_three_whys_diagnostic(output: str, context: Dict) -> GuardrailResult:
    """Verifica que outputs de post-mortem/error incluyan análisis Three Whys."""
    if "fail" not in output.lower() and "error" not in output.lower() and "issue" not in output.lower():
        return GuardrailResult(
            passed=True,
            severity=GuardrailSeverity.INFO,
            message="✅ Three Whys: no aplica (no es análisis de fallo)",
            rule_id="WHYS-001"
        )
    # Buscar patrón de 3 whys
    why_pattern = r"(why\s+\d|1st why|2nd why|3rd why|cause.*cause.*cause|root because)"
    has_three_whys = bool(re.search(why_pattern, output, re.I))
    if not has_three_whys:
        return GuardrailResult(
            passed=False,
            severity=GuardrailSeverity.WARN,
            message="Análisis de fallo sin Three Whys completo",
            suggestion="Aplica Three Whys: 1st Why (síntoma) → 2nd Why (causa directa) → 3rd Why (raíz sistémica)",
            rule_id="WHYS-001"
        )
    return GuardrailResult(
        passed=True,
        severity=GuardrailSeverity.INFO,
        message="✅ Three Whys: diagnóstico completo de causa raíz",
        rule_id="WHYS-001"
    )


# =============================================================================
# RAG TRIAD — Groundedness, Context Relevance, Faithfulness
# =============================================================================
# The RAG Triad evaluates quality of Retrieval-Augmented Generation outputs.
# Reference: https://docs.arize.com/arize-llm-evaluation/metrics/rag-triadic-metrics

def check_rag_groundedness(output: str, context: Dict) -> GuardrailResult:
    """Verifica que el output esté fundamentado en las fuentes proporcionadas.

    Checks for citation patterns, source references, or explicit grounding
    markers in the generated output.
    """
    sources = context.get("sources") or context.get("source_documents") or context.get("context_sources", [])
    if not sources:
        return GuardrailResult(
            passed=True,
            severity=GuardrailSeverity.INFO,
            message="✅ RAG Groundedness: sin fuentes de referencia para verificar",
            rule_id="RAG-001"
        )
    # Check for grounding patterns: citations, source references, quotes
    grounding_patterns = [
        r"\[(\d+)\]",                      # [1], [2], etc.
        r"source:\s*\w+",                  # source: document_name
        r"according to",                    # "according to [source]"
        r"referenc(?:e|ing)\s+\w+",         # referencing / reference
        r"based on.*(?:source|document|data)",  # based on the source
        r"cited in",                       # cited in
        r"as stated in",                    # as stated in
    ]
    has_grounding = any(re.search(p, output, re.I) for p in grounding_patterns)
    if not has_grounding:
        return GuardrailResult(
            passed=False,
            severity=GuardrailSeverity.WARN,
            message="RAG Groundedness: output sin referencias a fuentes proporcionadas",
            suggestion="Añade citas a las fuentes: [1], 'according to [source]', o 'based on [document]'",
            rule_id="RAG-001"
        )
    return GuardrailResult(
        passed=True,
        severity=GuardrailSeverity.INFO,
        message="✅ RAG Groundedness: output referenciado a fuentes",
        rule_id="RAG-001"
    )


def check_rag_context_relevance(output: str, context: Dict) -> GuardrailResult:
    """Verifica que el output use efectivamente el contexto proporcionado.

    Checks that key terms from the context appear in the generated output,
    indicating the context was actually used.
    """
    context_text = context.get("context") or context.get("context_text", "")
    sources = context.get("sources") or context.get("source_documents", [])
    if isinstance(sources, list):
        context_text = " ".join(sources) + " " + context_text
    if not context_text.strip():
        return GuardrailResult(
            passed=True,
            severity=GuardrailSeverity.INFO,
            message="✅ RAG Context Relevance: sin contexto de referencia para verificar",
            rule_id="RAG-002"
        )
    # Extract key terms from context (words 5+ chars, excluding common words)
    stopwords = {"this", "that", "with", "from", "have", "been", "were", "what", "when",
                 "where", "which", "their", "there", "would", "could", "should", "about"}
    context_words = set(re.findall(r'\b[a-zA-Z]{5,}\b', context_text.lower()))
    context_words -= stopwords
    if not context_words:
        return GuardrailResult(
            passed=True,
            severity=GuardrailSeverity.INFO,
            message="✅ RAG Context Relevance: contexto insuficiente para extraer términos clave",
            rule_id="RAG-002"
        )
    output_lower = output.lower()
    matched = sum(1 for w in context_words if w in output_lower)
    relevance_ratio = matched / len(context_words)
    if relevance_ratio < 0.15:
        return GuardrailResult(
            passed=False,
            severity=GuardrailSeverity.WARN,
            message=f"RAG Context Relevance: solo {matched}/{len(context_words)} términos del contexto aparecen en output ({relevance_ratio:.0%})",
            suggestion="El output debe usar activamente el contexto proporcionado. Revisa que no sea una respuesta genérica.",
            rule_id="RAG-002"
        )
    return GuardrailResult(
        passed=True,
        severity=GuardrailSeverity.INFO,
        message=f"✅ RAG Context Relevance: {matched}/{len(context_words)} términos ({relevance_ratio:.0%})",
        rule_id="RAG-002"
    )


def check_rag_faithfulness(output: str, context: Dict) -> GuardrailResult:
    """Verifica que el output no contradiga las fuentes.

    Looks for contradiction markers: unsupported claims, hallucination
    patterns, or claims that go beyond what the sources state.
    """
    sources = context.get("sources") or context.get("source_documents") or context.get("context_sources", [])
    if not sources:
        return GuardrailResult(
            passed=True,
            severity=GuardrailSeverity.INFO,
            message="✅ RAG Faithfulness: sin fuentes para verificar fidelidad",
            rule_id="RAG-003"
        )
    # Check for hallucination patterns: claims that aren't in sources
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
            passed=False,
            severity=GuardrailSeverity.WARN,
            message="RAG Faithfulness: output contiene marcadores de especulación/alucinación",
            suggestion="Las respuestas deben basarse exclusivamente en las fuentes. Reemplaza opiniones con datos de las fuentes.",
            rule_id="RAG-003"
        )
    return GuardrailResult(
        passed=True,
        severity=GuardrailSeverity.INFO,
        message="✅ RAG Faithfulness: output alineado con fuentes, sin alucinaciones detectadas",
        rule_id="RAG-003"
    )


# =============================================================================
# PIPELINE INSTANCIA GLOBAL
# =============================================================================

guardrails = GuardrailPipeline()

# Registrar checks pre-ejecución (arquitectura + discovery + cost + mcp)
guardrails.add_pre("ARCH-001", check_architecture_pattern)
guardrails.add_pre("ARCH-002", check_dependency_injection)
guardrails.add_pre("ARCH-003", check_resilience_patterns)
guardrails.add_pre("DISC-ADMIN-001", check_discovery_admin)
guardrails.add_pre("DISC-DATA-001", check_discovery_data)
guardrails.add_pre("DISC-INFRA-001", check_discovery_infra)
guardrails.add_pre("COST-001", check_cost_budget)
guardrails.add_pre("MCP-001", check_mcp_connectivity)

# Registrar checks post-ejecución (seguridad, commits, docs, cost, whys, rag)
guardrails.add_post("SEC-001", check_no_secrets)
guardrails.add_post("SEC-002", check_no_pii_in_logs)
guardrails.add_post("SEC-003", check_sql_injection_safe)
guardrails.add_post("COMMIT-001", check_conventional_commit)
guardrails.add_post("DOCS-001", check_docs_for_public_api)
guardrails.add_post("TEST-001", check_tests_for_new_features)
guardrails.add_post("COST-002", check_cost_usage)
guardrails.add_post("WHYS-001", check_three_whys_diagnostic)
guardrails.add_post("RAG-001", check_rag_groundedness)
guardrails.add_post("RAG-002", check_rag_context_relevance)
guardrails.add_post("RAG-003", check_rag_faithfulness)


def run_full_pipeline(user_message: str, generated_code: str, context: Dict) -> Dict[str, Any]:
    """
    Ejecuta el pipeline completo de guardrails.
    
    Returns:
        Dict con: allowed, pre_results, post_results, summary
    """
    # Preparar contexto
    ctx = {**context, "generated_code": generated_code, "user_message": user_message}
    
    # Pre-checks
    pre_ok, pre_results = guardrails.run_pre(ctx)
    
    if not pre_ok:
        return {
            "allowed": False,
            "blocked_at": "pre",
            "results": [r.to_dict() for r in pre_results],
            "summary": guardrails.get_summary()
        }
    
    # Post-checks
    post_ok, post_results = guardrails.run_post(generated_code, ctx)
    
    return {
        "allowed": post_ok,
        "blocked_at": None if post_ok else "post",
        "pre_results": [r.to_dict() for r in pre_results],
        "post_results": [r.to_dict() for r in post_results],
        "summary": guardrails.get_summary()
    }
