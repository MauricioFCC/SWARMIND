"""
Token-Efficient Prompt Builder with compression, budgeting & relevance scoring.
Enterprise optimization for LLM context management.
"""
import re
import os
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass


@dataclass
class TokenBudget:
    """Configuración de presupuesto de tokens por sección."""
    total: int = 4096
    system_prompt: int = 512
    skill_content: int = 1536
    context: int = 1024
    user_message: int = 512
    response_format: int = 256
    buffer: int = 256  # Margen de seguridad
    
    @property
    def available_for_content(self) -> int:
        return self.total - self.buffer - sum([
            self.system_prompt, self.context, 
            self.user_message, self.response_format
        ])


# Técnicas de compresión configurables
COMPRESSION_CONFIG = {
    "remove_redundant_phrases": [
        (r"\b(es decir|en otras palabras|dicho de otro modo|vale la pena mencionar)\b", ""),
        (r"\bpor favor|por favor |please |kindly |I would like to \b", ""),
        (r"\bit is important to note that\b", ""),
        (r"\bgenerally speaking\b", ""),
    ],
    "abbreviate_terms": {
        # Términos cuantitativos
        "out-of-sample": "OOS",
        "walk-forward validation": "WFV",
        "deflated sharpe ratio": "DSR",
        "combinatorially symmetric cross-validation": "CSCV",
        "mixture of experts": "MoE",
        "long short-term memory": "LSTM",
        "gradient boosting": "GB",
        # Términos de trading
        "stop loss": "SL",
        "take profit": "TP",
        "risk-reward ratio": "RR",
        "position sizing": "pos_size",
        "buying power": "BP",
        "notional value": "notional",
        # Términos técnicos
        "application programming interface": "API",
        "continuous integration": "CI",
        "continuous deployment": "CD",
        "infrastructure as code": "IaC",
    },
    "collapse_structures": True,
    "remove_examples_if_tight": True,
}


def estimate_tokens(text: str, model: str = "gpt-4") -> int:
    """
    Estimación rápida de tokens (aproximada).
    
    Nota: Para producción, usar tiktoken library de OpenAI.
    """
    # Aproximación: 1 token ≈ 4 chars en inglés, ≈ 3 en español mezclado
    avg_chars_per_token = 3.5
    return max(1, len(text) // avg_chars_per_token)


def compress_text(text: str, techniques: Optional[List[str]] = None, 
                  aggressiveness: float = 0.5) -> str:
    """
    Aplica técnicas de compresión para reducir tokens.
    
    Args:
        text: Texto a comprimir
        techniques: Lista de técnicas a aplicar (None = todas)
        aggressiveness: 0.0 (conservador) a 1.0 (agresivo)
    
    Returns:
        Texto comprimido
    """
    if techniques is None:
        techniques = list(COMPRESSION_CONFIG.keys())
    
    result = text
    
    # 1. Eliminar frases redundantes
    if "remove_redundant_phrases" in techniques:
        for pattern, replacement in COMPRESSION_CONFIG["remove_redundant_phrases"]:
            result = re.sub(pattern, replacement, result, flags=re.I)
    
    # 2. Abreviar términos técnicos
    if "abbreviate_terms" in techniques:
        for full, abbr in COMPRESSION_CONFIG["abbreviate_terms"].items():
            # Solo reemplazar si hay espacio suficiente para la abreviación
            if len(full) - len(abbr) >= 3:
                result = re.sub(rf'\b{re.escape(full)}\b', abbr, result, flags=re.I)
    
    # 3. Colapsar estructuras (listas, secciones repetitivas)
    if "collapse_structures" in techniques and aggressiveness > 0.3:
        # Convertir listas markdown largas a formato compacto
        result = re.sub(r'\n-\s+([^\n]+)\n-\s+([^\n]+)', r'\n• \1; \2', result)
        result = re.sub(r'\n\*\s+([^\n]+)\n\*\s+([^\n]+)', r'\n• \1; \2', result)
        # Colapsar secciones de "ejemplos" si son muy largas
        if aggressiveness > 0.7:
            result = re.sub(r'(## Ejemplos?\s*\n)([\s\S]*?)(\n##|\Z)', 
                           r'\1[Ver docs para ejemplos]\3', result, flags=re.I)
    
    # 4. Remover whitespace excesivo
    result = re.sub(r'\n{3,}', '\n\n', result)
    result = re.sub(r' {2,}', ' ', result)
    
    return result.strip()


def score_relevance(content: str, query: str, context: Dict) -> float:
    """
    Calcula score de relevancia [0, 1] para priorizar contenido.
    
    Estrategia: keywords matching + semantic proximity (simplificada)
    """
    if not content or not query:
        return 0.0
    
    content_lower = content.lower()
    query_lower = query.lower()
    
    # 1. Matching de keywords de la query
    query_keywords = [w for w in re.findall(r'\b[a-z]{4,}\b', query_lower) 
                     if w not in {'the', 'and', 'for', 'with', 'that', 'this'}]
    
    keyword_score = sum(1 for kw in query_keywords if kw in content_lower) / max(1, len(query_keywords))
    
    # 2. Matching con contexto (símbolos, plataforma, etc.)
    context_score = 0.0
    if context:
        ctx_keywords = [str(v).lower() for v in context.values() if isinstance(v, (str, int, float))]
        matches = sum(1 for ck in ctx_keywords if ck in content_lower)
        context_score = matches / max(1, len(ctx_keywords))
    
    # 3. Peso combinado
    return 0.7 * keyword_score + 0.3 * context_score


def build_optimized_prompt(
    agent_role: str,
    user_message: str,
    context: Optional[Dict] = None,
    budget: Optional[TokenBudget] = None,
    include_universal_principles: bool = True,
    compression_level: float = 0.5
) -> str:
    """
    Construye prompt optimizado respetando presupuesto de tokens.
    
    Estrategia de priorización:
    1. Instrucciones críticas del rol (siempre)
    2. Mensaje del usuario (siempre)
    3. Contexto relevante (filtrado por score)
    4. Principios universales (si hay espacio)
    5. Ejemplos (solo si sobra espacio)
    
    Args:
        agent_role: Rol del agente (ej: "quant-developer")
        user_message: Mensaje del usuario
        context: Contexto adicional (símbolos, config, etc.)
        budget: Presupuesto de tokens (default: TokenBudget())
        include_universal_principles: Incluir principios de programación
        compression_level: 0.0-1.0 para compresión de contenido
    
    Returns:
        Prompt optimizado listo para enviar al LLM
    """
    budget = budget or TokenBudget()
    context = context or {}
    
    # 1. Header del rol (crítico, nunca comprimir)
    parts = [f"## ROL: {agent_role.upper().replace('-', ' ').title()}"]
    used_tokens = estimate_tokens(parts[0])
    
    # 2. Cargar y procesar skill content
    skill_content = _load_skill_content(agent_role)
    
    # Aplicar compresión si estamos tight en tokens
    skill_tokens = estimate_tokens(skill_content)
    if used_tokens + skill_tokens > budget.available_for_content * 0.9:
        skill_content = compress_text(skill_content, aggressiveness=compression_level)
        skill_tokens = estimate_tokens(skill_content)
    
    parts.append(skill_content)
    used_tokens += skill_tokens
    
    # 3. Incluir contexto filtrado por relevancia
    if context and used_tokens < budget.available_for_content * 0.7:
        relevant_context = _filter_context_by_relevance(context, user_message, 
                                                        max_tokens=budget.context)
        if relevant_context:
            ctx_section = f"\n## CONTEXTO OPERATIVO\n{relevant_context}"
            ctx_tokens = estimate_tokens(ctx_section)
            if used_tokens + ctx_tokens <= budget.available_for_content:
                parts.append(ctx_section)
                used_tokens += ctx_tokens
    
    # 4. Principios universales (solo si hay espacio y está habilitado)
    if include_universal_principles and used_tokens < budget.available_for_content * 0.85:
        principles = _get_relevant_principles(agent_role, user_message)
        if principles:
            princ_section = f"\n## PRINCIPIOS APLICABLES\n{principles}"
            princ_tokens = estimate_tokens(princ_section)
            if used_tokens + princ_tokens <= budget.available_for_content:
                parts.append(princ_section)
                used_tokens += princ_tokens
    
    # 5. Mensaje del usuario (siempre al final, antes del formato)
    user_section = f"\n## TU TAREA AHORA\n{user_message}"
    parts.append(user_section)
    used_tokens += estimate_tokens(user_section)
    
    # 6. Formato de respuesta (crítico para parsing)
    format_section = _get_response_format_instruction(agent_role)
    parts.append(f"\n## FORMATO DE RESPUESTA\n{format_section}")
    
    # 7. Verificación final y truncado de emergencia si es necesario
    final_prompt = "\n\n".join(parts)
    final_tokens = estimate_tokens(final_prompt)
    
    if final_tokens > budget.total - budget.buffer:
        # Truncado agresivo preservando estructura crítica
        final_prompt = _emergency_truncate(final_prompt, budget.total - budget.buffer)
    
    return final_prompt


def _load_skill_content(role: str) -> str:
    """Carga contenido del skill (simulado - en prod leería de archivo)."""
    # Placeholder: en producción, leer de .opencode/skills/{role}/SKILL.md
    # y aplicar inyección de variables {{VARIABLE}} desde config
    return f"""# {role.upper().replace('-', ' ')} SKILL

## RESPONSABILIDADES PRINCIPALES
• Implementar soluciones para {role.replace('-', ' ')}
• Seguir patrones: hexagonal, DI, resiliencia
• Validar con guardrails: arquitectura, seguridad, docs

## CHECKLIST PRE-COMMIT
[ ] Tests añadidos/actualizados
[ ] Docstrings en APIs públicas
[ ] Sin secrets hardcodeados
[ ] Commit message convencional

## GUARDRAILS OBLIGATORIOS
✅ Arquitectura: Ports/Adapters, inyección dependencias
✅ Seguridad: os.getenv() para secrets, logs sin PII
✅ Docs: Docstrings completos, README actualizado si aplica

## VARIABLES DISPONIBLES
{{PROJECT_NAME}}, {{ACTIVE_SYMBOLS}}, {{TRADING_PLATFORM}}, {{RISK_LIMITS}}

> Nota: Usa {{VARIABLES}} para parametrización. Valores en config/project_config.yaml
"""


def _filter_context_by_relevance(context: Dict, query: str, 
                                  max_tokens: int) -> Optional[str]:
    """Filtra contexto por relevancia y límite de tokens."""
    if not context:
        return None
    
    # Calcular scores de relevancia
    scored_items = []
    for key, value in context.items():
        if value in (None, '', [], {}):
            continue
        content = f"{key}: {value}" if not isinstance(value, dict) else str(value)
        score = score_relevance(content, query, context)
        scored_items.append((key, value, score))
    
    # Ordenar por relevancia descendente
    scored_items.sort(key=lambda x: -x[2])
    
    # Seleccionar items hasta llenar presupuesto
    selected = []
    used_tokens = 0
    
    for key, value, score in scored_items:
        if score < 0.3:  # Threshold mínimo de relevancia
            break
        
        item_text = f"- {key}: {value}" if not isinstance(value, dict) else f"- {key}: [objeto]"
        item_tokens = estimate_tokens(item_text)
        
        if used_tokens + item_tokens <= max_tokens:
            selected.append(item_text)
            used_tokens += item_tokens
    
    return "\n".join(selected) if selected else None


def _load_principles_from_file() -> Tuple[Dict[str, List[str]], Dict[str, List[str]], str]:
    """Carga principios desde base_principles.md. Fallback a hardcoded si no existe."""
    principles_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "core", "base_principles.md"
    )
    
    # Fallback hardcoded
    fallback_principles = {
        "ARQ": ["Hexagonal + DI. KISS <500 lineas. DRY. Type hints."],
        "SEG": ["0 secrets hardcode. Input validate. Logs mask. SQL parametrizada."],
        "DOC": ["Docstrings ES. Codigo EN. Docs 1:1 con API changes."],
        "TST": ["Core >=80%. Pre-commit gates. New feature = new test."],
        "OPS": ["Timeout >=30s. Retry 3x + backoff. Circuit breaker. Log JSON trace_id."],
        "CMT": ["Conventional commit type(scope): descripcion #ISSUE. <=72 chars."],
        "QLT": ["Respuesta <500 tokens. Codigo ejecutable. Sin hardcode."],
    }
    fallback_roles = {
        "quant-developer": ["ARQ", "SEG", "TST", "DOC", "OPS"],
        "quant-scientist": ["ARQ", "TST", "DOC"],
        "risk-manager": ["ARQ", "SEG", "TST", "OPS"],
        "software-engineer": ["ARQ", "SEG", "OPS", "CMT"],
        "frontend-engineer": ["ARQ", "DOC", "QLT"],
        "data-architect": ["ARQ", "TST", "SEG"],
        "devops-sre": ["OPS", "CMT", "SEG"],
        "security-engineer": ["SEG", "CMT", "ARQ", "DOC"],
        "trading-operations": ["OPS", "CMT"],
        "quality-gate": ["TST", "CMT", "QLT"],
        "documentation-specialist": ["DOC", "QLT"],
        "project-manager": ["CMT", "QLT"],
        "quality-gate": ["TST", "CMT", "SEG", "DOC", "QLT"],
    }
    
    try:
        with open(principles_path, "r", encoding="utf-8") as f:
            content = f.read()
    except (FileNotFoundError, IOError):
        return fallback_principles, fallback_roles, (
            "ARQ | Hexagonal + DI. KISS <500. DRY. Type hints.\n"
            "SEG | 0 secrets. Validate input. Mask logs.\n"
            "DOC | Docs ES. Codigo EN. Docs 1:1.\n"
            "TST | Core >=80%. Pre-commit gates.\n"
            "OPS | Timeout. Retry. Circuit breaker.\n"
            "CMT | Conventional commit.\n"
            "QLT | <500 tokens. Codigo listo."
        )
    
    # Parse NIVEL 2 table: | Cat | Reglas |
    principles: Dict[str, List[str]] = {}
    nivel2_match = re.search(
        r"\|\s*\*\*(\w+)\*\*\s*\|\s*(.+?)\s*\|",
        content
    )
    # Better: parse all rows in the Nivel 2 table
    nivel2_lines = re.findall(
        r"\|\s*\*\*(\w+)\*\*\s*\|\s*(.+?)\s*\|",
        content
    )
    for cat, rules in nivel2_lines:
        principles[cat] = [r.strip() for r in rules.split(".") if r.strip()[:3] != "Cat"]
    
    # Parse MAPA DE ROLES table: | Rol | Categorias |
    role_lines = re.findall(
        r"\|\s*(\w[\w-]*)\s*\|\s*([\w,\s]+)\s*\|",
        content
    )
    role_mapping: Dict[str, List[str]] = {}
    for role, cats in role_lines:
        if role.lower() in ("rol", "-----", "cat"):
            continue
        role_mapping[role] = [c.strip() for c in cats.split(",")]
    
    # Parse NIVEL 1 as single compact string
    nivel1_match = re.search(
        r"```\s*\n(ARQ:.*?CMT:.*?)\n```",
        content,
        re.DOTALL
    )
    nivel1 = nivel1_match.group(1).strip() if nivel1_match else fallback_principles
    
    if not principles:
        return fallback_principles, role_mapping or fallback_roles, nivel1
    
    return principles, role_mapping or fallback_roles, nivel1


# Cache para evitar re-lectura
_PRINCIPLES_CACHE: Optional[Tuple] = None

def _get_principles_cached():
    global _PRINCIPLES_CACHE
    if _PRINCIPLES_CACHE is None:
        _PRINCIPLES_CACHE = _load_principles_from_file()
    return _PRINCIPLES_CACHE


def _get_relevant_principles(role: str, query: str) -> str:
    """Obtiene principios universales relevantes para el rol y query.
    
    Nivel 1 (esencial): siempre incluido, ~45 tokens
    Nivel 2 (estandar): incluido si hay matching, ~120 tokens
    Max 5 principios por rol para ahorrar tokens.
    """
    all_principles, role_mapping, nivel1 = _get_principles_cached()
    
    categories = role_mapping.get(role, ["ARQ", "SEG", "DOC"])

    relevant = []

    # Siempre incluir nivel 1 (cada linea separada)
    for line in nivel1.strip().split("\n"):
        line = line.strip()
        if line:
            relevant.append(f"* {line}")

    # Nivel 2: filtrar por relevancia con la query
    query_lower = query.lower()
    query_words = set(re.findall(r"[a-z0-9]+", query_lower))
    for cat in categories:
        for principle in all_principles.get(cat, []):
            # Extraer keywords significativas del principio (>=4 chars, solo alfanumerico)
            principle_kw = {w.lower() for w in re.findall(r"[a-zA-Z0-9]{4,}", principle)}
            # Incluir si hay matching de keywords
            if principle_kw & query_words:
                relevant.append(f"* [{cat}] {principle}")

    return "\n".join(relevant[:10])  # 5 nivel1 + max 5 nivel2


def _get_response_format_instruction(role: str) -> str:
    """Instrucciones de formato de respuesta por rol."""
    base = "Responde en español. Sé conciso y accionable."
    
    role_formats = {
        "project-manager": "Usa listas con checkboxes [ ] para tareas. Incluye estimación de esfuerzo.",
        "quant-developer": "Incluye código con type hints. Añade docstrings. Menciona tests necesarios.",
        "quant-scientist": "Cita métricas estadísticas. Especifica metodología de validación.",
        "risk-manager": "Cuantifica riesgos numéricamente. Propone límites concretos.",
        "software-engineer": "Incluye snippets de config/deploy. Menciona variables de entorno requeridas.",
    }
    
    return f"{base} {role_formats.get(role, '')}".strip()


def _emergency_truncate(text: str, max_tokens: int) -> str:
    """Truncado de emergencia preservando estructura crítica."""
    # Mantener secciones críticas
    critical_markers = ["## ROL:", "## TU TAREA", "## FORMATO DE RESPUESTA"]
    
    sections = re.split(r'\n(?=## )', text)
    critical_sections = []
    optional_sections = []
    
    for section in sections:
        if any(marker in section for marker in critical_markers):
            critical_sections.append(section)
        else:
            optional_sections.append(section)
    
    # Reconstruir con críticos primero
    result = "\n".join(critical_sections)
    
    # Añadir opcionales si hay espacio
    for section in optional_sections:
        if estimate_tokens(result + "\n" + section) <= max_tokens:
            result += "\n" + section
    
    # Último recurso: truncar por caracteres
    if estimate_tokens(result) > max_tokens:
        result = result[:max_tokens * 3] + "\n\n[...contenido truncado por límite de tokens...]"
    
    return result


