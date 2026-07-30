"""
context_injector.py — Inyeccion automatica de contexto en subtareas.

Resuelve el problema de que el LLM "olvida" los estandares durante
sesiones largas de refactorizacion. La clave: inyectar un recordatorio
ultra-compacto en CADA subtarea, no solo al inicio de la sesion.

Formato: 1 linea, ~100 chars, <25 tokens.
No reemplaza los agent prompts, los REFUERZA en cada interaccion.

Uso:
    injector = ContextInjector()
    descripcion = injector.inject("implementar modulo X")
    # → "[FIJOS] CleanCode+DRY+KISS+SSOT+<900LC | implementar modulo X"

    record = injector.get_reminder("builder")
    # → "FIJOS: CleanCode+DRY+KISS+SSOT+<900LC+Patrones+DocStringsES+tests>80+Seg"
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Codificacion ultra-compacta de estandares (<100 chars cada uno)
# ---------------------------------------------------------------------------
# Formato: siglas sin espacios, + como separador
# Cada entry: [nombre_corto] = [significado]

# !DOC_ES_OBLIG! y !ERR_ACTION! van PRIMERO en cada entry.
# Principios inyectados por rol (ver ADR-0001 para documentacion completa)
STANDARDS_ENCODED: dict[str, str] = {
    "builder": "!DOC_ES_OBLIG!+!ERR_ACTION!+!WFP!+!PBT!+!CEN!+!AGR!+!TH!+!HEX!+CleanCode+DRY+KISS+SSOT+<900LC+fn<60ln+YAGNI+Patrones+CompRoot+Copyright+Resiliencia+Hardening+ToastGlobal+Helpers+PathLib+DoD+tests>80+Seg+Rust+CP_Opt+AlgoEficiente+MemoriaO1+Complejidad+BigO+TDAD+TDFlow+PaCoRe+PROBE+AdverTest+FuzzAgent+PropBase+TokenEcon+CacheShape+FailSpend+StructCompact+obsMask+scopedCtx+parMax+HarnessEffect+ResearchFirst+Idempotencia",
    "scientist": "!DOC_ES_OBLIG!+!ERR_ACTION!+!WFP!+!PBT!+!CEN!+!BTR!+!TH!+!HEX!+MetodoCientifico+Fuentes+Analisis+Conclusiones+DocumentarES+DoD+PathLib+LecturaCritica+SQ3R+ComprensionProfunda+MapaMental+Resumir+Sintetizar+PaCoRe+LTS+Helium+Agentix+SwarmX+fn<60ln+obsMask+scopedCtx+parMax+HarnessEffect+TokenMaxing+38Metrics+AOSE+CDBench+ReproReas+ABCBench+ResearchFirst+Idempotencia",
    "guardian": "!DOC_ES_OBLIG!+!ERR_ACTION!+!WFP!+!PBT!+!AGR!+!BTR!+!TH!+!HEX!+Tests>80+OWASP+Hardening+CommitsConvencionales+SinVulns+DoD+Resiliencia+PathLib+PROBE+SpecOps+AdverTest+SMART+FuzzAgent+MuTON+TDADMut+CDBench+PBT+AdvLoop+MutScore85+fn<60ln+parMax+ResearchFirst+Idempotencia",
    "coordinator": "!DOC_ES_OBLIG!+!ERR_ACTION!+!WFP!+!CEN!+!BTR!+!TH!+!HEX!+SwissWatch+Paralelo+MaxSpeed+CalidadAutomatica+ParaleloMax+Consolidar+CompRoot+DoD+PathLib+CP_Strategies+DivideAndConquer+TwoPointers+SlidingWindow+Optimizacion+HarnessMec+TokenBudget+CircuitBrk+StructuredOut+obsMask+scopedCtx+parMax+PaCoRe+LTS+Helium+ScaleDecide+FailClass+PLAS+ATLAS+ResearchFirst+Idempotencia",
    "evolve": "!DOC_ES_OBLIG!+!ERR_ACTION!+!WFP!+!PBT!+!CEN!+!BTR!+!SVE!+!TH!+!HEX!+Cognition+MejoraContinua+Skills+Optimizacion+CompRoot+Resiliencia+DoD+TokenEcon+HarnessOpt+SwarmindRL+SpecEvo+RoleAOSE+FDE+Autobuilder+KATCoder+PaCoReTrain+LTSControl+TreeTrain+MCLA+AgentScale+fn<60ln+parMax+ResearchFirst+Idempotencia",
}

# Firma universal: aplica a TODOS los agentes, siempre, sin excepcion.
# Cubre: arquitectura, calidad, seguridad, documentacion, entrega, errores accionables.
UNIVERSAL_FIRMA = "!DOC_ES_OBLIG!+!ERR_ACTION!+!WFP!+!PBT!+!CEN!+!BTR!+!AGR!+!SVE!+!TH!+!HEX!+CleanCode+DRY+KISS+SSOT+<900LC+fn<60ln+YAGNI+Patrones+CompRoot+Copyright+Resiliencia+Hardening+Helpers+PathLib+DoD+tests>80+Seg+TokenEcon+CacheShape+StructuredOut+obsMask+scopedCtx+parMax+CircuitBrk+FailGovern+ResearchFirst+Idempotencia"

# Tamaño en chars de la firma (para calculo de tokens)
FIRMA_LENGTH = len(UNIVERSAL_FIRMA)

# Maximo de caracteres para la inyeccion (limitar impacto tokens)
MAX_INJECTION_CHARS = 120

# ---------------------------------------------------------------------------
# Research First — Principio Atemporal de Vanguardia
# ---------------------------------------------------------------------------
# ResearchFirst: ANTES de ejecutar cualquier tarea, investigar el estado del
# arte actual via web search. Esto garantiza que el agente use las tecnicas
# mas avanzadas disponibles en el momento de ejecucion, no las que conocia
# en su entrenamiento. El sistema es atemporal: la vanguardia se mantiene
# simple: "investiga primero, ejecuta despues".
#
# El agente DEBE:
#   1. Buscar papers, frameworks y herramientas actuales sobre el tema
#   2. Identificar la tecnica mas avanzada y adecuada
#   3. Documentar brevemente la fuente y por que la eligio
#   4. Ejecutar la tarea con esa tecnica
#
# Esto aplica a TODOS los agentes, sin excepcion. Es la unica forma de
# garantizar que el sistema se mantenga en la frontera technologica
# independientemente de cuando se ejecute.


class ContextInjector:
    """
    Inyecta recordatorio de estandares en descripciones de subtareas.

    El recordatorio es UNA SOLA LINEA ultra-compacta que se antepone
    a la descripcion real. Esto asegura que el LLM vea los estandares
    en CADA interaccion, no solo al inicio de la sesion.
    """

    def __init__(self, always_inject: bool = True):
        """
        Args:
            always_inject: Si True, siempre inyecta (incluso en tareas simples).
                          Si False, solo inyecta en tareas complejas.
        """
        self._always_inject = always_inject

    def inject(self, description: str, agent_role: str = "builder") -> str:
        """
        Inyecta estandares en una descripcion de subtarea.

        Args:
            description: Descripcion original de la subtarea.
            agent_role: Rol del agente (builder, scientist, guardian, etc).

        Returns:
            Descripcion con recordatorio de estandares antepuesto.
        """
        if not description:
            return description

        reminder = self.get_reminder(agent_role)
        # Solo inyectar si la descripcion no lo contiene ya
        if reminder in description:
            return description

        # Formato: recordatorio + " | " + descripcion original
        # Mantener la descripcion original legible
        if self._always_inject:
            return f"{reminder} | {description}"
        else:
            return description

    def get_reminder(self, agent_role: str = "builder") -> str:
        """
        Obtiene recordatorio de estandares para un rol.
        SIEMPRE incluye la firma universal + los estandares especificos del rol.

        Args:
            agent_role: Rol del agente.

        Returns:
            String con estandares codificados (universal + especifico).
        """
        universal = UNIVERSAL_FIRMA
        specific = STANDARDS_ENCODED.get(agent_role, "")
        if specific:
            # Unir universal + especifico, evitar duplicados
            universal_parts = set(universal.split("+"))
            specific_parts = [p for p in specific.split("+") if p not in universal_parts]
            combined = universal + "+" + "+".join(specific_parts)
        else:
            combined = universal
        return f"[F]{combined}"

    def estimate_tokens(self, agent_role: str = "builder") -> int:
        """Estima tokens adicionales por inyeccion."""
        reminder = self.get_reminder(agent_role)
        return len(reminder) // 4  # ~1 token cada 4 chars

    def batch_inject(
        self, descriptions: list[str], agent_role: str = "builder"
    ) -> list[str]:
        """Inyecta estandares en multiples descripciones."""
        return [self.inject(d, agent_role) for d in descriptions]

    @property
    def universal_firma(self) -> str:
        """Retorna la firma universal."""
        return UNIVERSAL_FIRMA

    @staticmethod
    def validate_docstrings(code: str, file_path: str = "<string>") -> list[str]:
        """Valida que todo codigo tenga docstring ES-UTF8 completo.

        Escanea el codigo con AST y reporta funciones/clases sin docstring
        o con docstring incompleto (sin Args/Returns/Raises).
        Puede llamarse despues de generar codigo para validacion automatica.

        Args:
            code: Codigo fuente a validar.
            file_path: Nombre del archivo (para reporte).

        Returns:
            Lista de strings con funciones/clases que faltan docstring.
            Vacia si todo cumple.
        """
        import ast
        missing: list[str] = []
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    # Saltar métodos privados (_foo) y dunder (__foo__)
                    if node.name.startswith("_"):
                        continue
                    doc = ast.get_docstring(node)
                    if not doc:
                        missing.append(f"[SIN DOCSTRING] {node.name} en {file_path}")
                    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        # Solo verificar Args/Returns en funciones, no en clases
                        doc_lower = doc.lower()
                        has_args = "args:" in doc_lower
                        has_returns = "returns:" in doc_lower
                        if not has_args and not has_returns:
                            missing.append(f"[DOCSTRING INCOMPLETO] {node.name} en {file_path} - falta Args/Returns")
            return missing
        except SyntaxError:
            return [f"  [SyntaxError] No se pudo parsear {file_path}"]

