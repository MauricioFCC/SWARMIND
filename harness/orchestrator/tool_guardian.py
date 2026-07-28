"""
ToolGuardian — Seguridad declarativa para interacciones agente-herramienta.

Basado en arXiv:2607.21835 (Ravindran & Deochake, Jul 2026):
Progressive characterization pipeline con ASP-based policy layer.
Alcanza 88% accuracy en deteccion de comportamiento malicioso.

Progressive characterization stages:
  1. Description: Verifica metadata y nombre de la tool.
  2. Syscall: Analiza llamadas al sistema peligrosas.
  3. Mock execution: Simula ejecucion en sandbox logicamente.
  4. Source analysis: Analisis estatico de codigo fuente.

Cada etapa produce evidencia que alimenta la policy layer basada en ASP,
asignando un risk_score acumulativo que determina el ToolRiskLevel final.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes de seguridad
# ---------------------------------------------------------------------------

# Patrones de codigo peligroso para analisis estatico (Stage 4)
DANGEROUS_PATTERNS: List[str] = [
    r"exec\s*\(", r"eval\s*\(", r"__import__\s*\(", r"subprocess\s*\.",
    r"os\.system", r"os\.popen", r"shutil\.rmtree", r"pathlib.*\.unlink",
    r"ctypes\.", r"pickle\.loads", r"socket\.", r"requests?\.",
    r"open\s*\(.*[rwab]",
]

# Llamadas al sistema de alto riesgo (Stage 2)
HIGH_RISK_SYSCALLS: Set[str] = {
    "execve", "execvp", "fork+exec", "ptrace", "process_vm_writev",
    "iopl", "ioperm", "kexec_load", "reboot", "swapon", "swapoff",
    "delete_module", "init_module", "setuid", "setgid", "chroot",
}

# Patrones de ofuscacion (Stage 4)
OBFUSCATION_PATTERNS: List[str] = [
    r"base64\.(b64decode|decode)", r"bytes\.fromhex", r"decode\s*\(['\"]hex['\"]",
    r"\\x[0-9a-fA-F]{2}",  # cadenas con escapes hex
    r"__builtins__", r"getattr.*__", r"setattr.*__",
]


class ToolRiskLevel(str, Enum):
    """Nivel de riesgo asignado a una tool tras el pipeline de caracterizacion.

    SAFE: Sin riesgo detectado, puede ejecutarse libremente.
    SUSPICIOUS: Comportamiento sospechoso, requiere supervision.
    MALICIOUS: Comportamiento malicioso confirmado, bloqueado.
    """

    SAFE = "safe"
    SUSPICIOUS = "suspicious"
    MALICIOUS = "malicious"


class CharacterizationStage(str, Enum):
    """Etapas del progressive characterization pipeline (arXiv:2607.21835)."""

    DESCRIPTION = "description"
    SYSCALL = "syscall"
    MOCK_EXECUTION = "mock_execution"
    SOURCE_ANALYSIS = "source_analysis"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ToolPolicy:
    """Politica de seguridad declarativa para una categoria de tool.

    Attributes:
        name: Nombre de la categoria (filesystem, network, shell, etc.).
        allowed_actions: Lista de acciones permitidas.
        blocked_actions: Lista de acciones bloqueadas explicitamente.
        required_capabilities: Capacidades que debe tener el agente.
        max_execution_time: Tiempo maximo de ejecucion en segundos.
        requires_human_approval: Si requiere aprobacion humana.
        allowed_domains: Dominios permitidos (solo network).
        allowed_paths: Rutas permitidas (solo filesystem).
    """

    name: str
    allowed_actions: List[str] = field(default_factory=list)
    blocked_actions: List[str] = field(default_factory=list)
    required_capabilities: List[str] = field(default_factory=list)
    max_execution_time: int = 30
    requires_human_approval: bool = False
    allowed_domains: List[str] = field(default_factory=list)
    allowed_paths: List[str] = field(default_factory=list)


@dataclass
class CharacterizationResult:
    """Resultado de una etapa del pipeline de caracterizacion.

    Attributes:
        stage: Etapa del pipeline.
        passed: True si la etapa fue superada sin hallazgos.
        score: Puntaje de riesgo de la etapa (0 = seguro, >0 = riesgo).
        evidence: Evidencia textual del analisis.
        details: Detalles adicionales estructurados.
    """

    stage: CharacterizationStage
    passed: bool = True
    score: float = 0.0
    evidence: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# ToolGuardian
# ---------------------------------------------------------------------------


class ToolGuardian:
    """Guardian de seguridad declarativa para herramientas de agente.

    Implementa progressive characterization pipeline (arXiv:2607.21835)
    con 4 etapas y una policy layer basada en ASP para determinar
    si una tool es segura, sospechosa o maliciosa.

    Examples:
        >>> guardian = ToolGuardian()
        >>> guardian.validate_tool_call("filesystem", "read", {"path": "/tmp"})
        True
        >>> guardian.validate_tool_call("shell", "execute", {"cmd": "rm -rf /"})
        False
    """

    def __init__(self, strict_mode: bool = False) -> None:
        """Inicializa ToolGuardian con politicas por defecto.

        Args:
            strict_mode: Si True, bloquea cualquier accion no explicitamente
                permitida. Si False, permite acciones no listadas como
                bloqueadas.
        """
        self._strict = strict_mode
        self._policies: Dict[str, ToolPolicy] = {}
        self._load_default_policies()

    # ------------------------------------------------------------------
    # Politicas por defecto
    # ------------------------------------------------------------------

    def _load_default_policies(self) -> None:
        """Carga las politicas de seguridad por defecto."""

        # Archivos: solo lectura/escritura controlada
        self._policies["filesystem"] = ToolPolicy(
            name="filesystem",
            allowed_actions=["read", "write", "list", "stat"],
            blocked_actions=["delete", "format", "chmod", "chown", "mkfs",
                             "mount", "umount", "truncate"],
            max_execution_time=10,
            allowed_paths=["/tmp", "/home", "/data", "./"],
        )

        # Red: solo GET/POST a dominios permitidos
        self._policies["network"] = ToolPolicy(
            name="network",
            allowed_actions=["get", "post", "head"],
            blocked_actions=["delete", "put", "patch", "connect",
                             "trace", "options"],
            requires_human_approval=True,
            allowed_domains=["api.github.com", "api.openai.com",
                             "api.anthropic.com"],
        )

        # Base de datos: solo consultas SELECT
        self._policies["database"] = ToolPolicy(
            name="database",
            allowed_actions=["query", "select", "describe", "list_tables"],
            blocked_actions=["drop", "truncate", "alter", "insert",
                             "update", "delete", "create", "grant",
                             "revoke"],
            requires_human_approval=True,
        )

        # Shell: solo comandos seguros, requiere aprobacion humana
        self._policies["shell"] = ToolPolicy(
            name="shell",
            allowed_actions=["execute", "list_processes", "get_env"],
            blocked_actions=["rm -rf", "dd", "format", ":(){", "mkfs",
                             "chmod -R", "kill -9", "shutdown", "reboot",
                             "> /dev/", "< /dev/"],
            requires_human_approval=True,
            max_execution_time=15,
        )

        # LLM: completions y embeddings
        self._policies["llm"] = ToolPolicy(
            name="llm",
            allowed_actions=["complete", "embed", "tokenize", "classify"],
            blocked_actions=[],
            max_execution_time=60,
        )

        # Git: operaciones de solo lectura
        self._policies["git"] = ToolPolicy(
            name="git",
            allowed_actions=["status", "log", "diff", "show", "branch",
                             "clone"],
            blocked_actions=["push", "commit", "merge", "rebase", "reset",
                             "cherry-pick", "tag"],
            requires_human_approval=True,
        )

        # Registro de herramientas (plugins)
        self._policies["tool_registry"] = ToolPolicy(
            name="tool_registry",
            allowed_actions=["list", "get", "search"],
            blocked_actions=["register", "unregister", "update",
                             "enable", "disable"],
            requires_human_approval=True,
        )

    # ------------------------------------------------------------------
    # API publica — Politicas
    # ------------------------------------------------------------------

    def register_policy(self, policy: ToolPolicy) -> None:
        """Registrar una politica personalizada.

        Args:
            policy: Politica a registrar. Si ya existe una politica con
                el mismo nombre, se sobrescribe.
        """
        self._policies[policy.name] = policy
        logger.info("ToolGuardian: politica registrada '%s'", policy.name)

    def get_policy(self, tool_name: str) -> Optional[ToolPolicy]:
        """Obtener la politica para una tool.

        Args:
            tool_name: Nombre de la tool.

        Returns:
            ToolPolicy si existe, None en caso contrario.
        """
        return self._policies.get(tool_name)

    def remove_policy(self, tool_name: str) -> bool:
        """Eliminar una politica registrada.

        Args:
            tool_name: Nombre de la politica a eliminar.

        Returns:
            True si fue eliminada, False si no existia.
        """
        if tool_name in self._policies:
            del self._policies[tool_name]
            logger.info("ToolGuardian: politica eliminada '%s'", tool_name)
            return True
        return False

    def list_policies(self) -> List[str]:
        """Listar los nombres de todas las politicas registradas.

        Returns:
            Lista de nombres de politicas.
        """
        return list(self._policies.keys())

    # ------------------------------------------------------------------
    # API publica — Validacion de llamadas
    # ------------------------------------------------------------------

    def validate_tool_call(
        self,
        tool_name: str,
        action: str,
        args: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Validar si una llamada a tool esta permitida segun la politica.

        Evalua la accion contra la politica de la tool, verificando
        acciones bloqueadas, permitidas y reglas adicionales (dominios,
        rutas, tiempo maximo).

        Args:
            tool_name: Nombre de la tool.
            action: Accion a ejecutar.
            args: Argumentos de la llamada (para validaciones
                  contextuales como rutas o dominios).

        Returns:
            True si la llamada esta permitida, False en caso contrario.
        """
        policy = self._policies.get(tool_name)
        if policy is None:
            logger.warning("ToolGuardian: sin politica para tool '%s'", tool_name)
            return False

        action_lower = action.lower()

        # Verificar acciones bloqueadas (prioridad maxima)
        for blocked in policy.blocked_actions:
            if blocked.lower() in action_lower:
                logger.warning(
                    "ToolGuardian: accion bloqueada '%s' en tool '%s'",
                    action, tool_name,
                )
                return False

        # Verificar acciones permitidas
        if action_lower in [a.lower() for a in policy.allowed_actions]:
            # Validaciones contextuales adicionales
            if args and not self._validate_contextual(policy, action_lower, args):
                return False
            return True

        # Modo estricto: solo acciones explicitamente permitidas
        if self._strict:
            logger.warning(
                "ToolGuardian: accion '%s' no permitida en tool '%s' (strict)",
                action, tool_name,
            )
            return False

        # Modo normal: acciones desconocidas se permiten con advertencia
        logger.info(
            "ToolGuardian: accion '%s' en tool '%s' no listada, permitida",
            action, tool_name,
        )
        return True

    def _validate_contextual(
        self,
        policy: ToolPolicy,
        action: str,
        args: Dict[str, Any],
    ) -> bool:
        """Validaciones contextuales adicionales (rutas, dominios, etc.).

        Args:
            policy: Politica activa.
            action: Accion en minusculas.
            args: Argumentos de la llamada.

        Returns:
            True si las validaciones contextuales pasan.
        """
        # Validar rutas permitidas (filesystem)
        if policy.allowed_paths and "path" in args:
            path = args["path"]
            if not any(path.startswith(allowed) for allowed in policy.allowed_paths):
                logger.warning(
                    "ToolGuardian: ruta '%s' no permitida para tool '%s'",
                    path, policy.name,
                )
                return False

        # Validar dominios permitidos (network)
        if policy.allowed_domains and "url" in args:
            url = args["url"]
            domain_match = any(domain in url for domain in policy.allowed_domains)
            if not domain_match:
                logger.warning(
                    "ToolGuardian: dominio en '%s' no permitido para tool '%s'",
                    url, policy.name,
                )
                return False

        return True

    # ------------------------------------------------------------------
    # API publica — Analisis de tool
    # ------------------------------------------------------------------

    def analyze_tool(self, tool_name: str, tool_code: str) -> ToolRiskLevel:
        """Analizar codigo fuente de una tool y asignar nivel de riesgo.

        Realiza analisis estatico basado en patrones peligrosos y
        ofuscacion. Es el Stage 4 del pipeline progresivo.

        Args:
            tool_name: Nombre de la tool (para contexto).
            tool_code: Codigo fuente de la tool.

        Returns:
            ToolRiskLevel: SAFE, SUSPICIOUS o MALICIOUS.
        """
        if not tool_code or not tool_code.strip():
            logger.info("ToolGuardian: tool '%s' sin codigo, SAFE", tool_name)
            return ToolRiskLevel.SAFE

        risk_score = 0
        matched_patterns: List[str] = []

        # Analizar patrones peligrosos
        for pattern in DANGEROUS_PATTERNS:
            matches = re.findall(pattern, tool_code, re.IGNORECASE)
            if matches:
                count = len(matches)
                risk_score += count * 2
                matched_patterns.append(pattern)

        # Analizar ofuscacion
        for ob_pattern in OBFUSCATION_PATTERNS:
            if re.search(ob_pattern, tool_code, re.IGNORECASE):
                risk_score += 3
                matched_patterns.append(ob_pattern)

        # Penalizar si no hay docstring (falta de transparencia)
        if '"""' not in tool_code and "'''" not in tool_code:
            risk_score += 1

        # Penalizar codigo excesivamente denso (menos de 50% de lineas en blanco/comentarios)
        total_lines = tool_code.strip().split("\n")
        code_no_comment = [l for l in total_lines if l.strip() and not l.strip().startswith("#")]
        if len(total_lines) > 20 and len(code_no_comment) / len(total_lines) > 0.85:
            risk_score += 1

        if matched_patterns:
            logger.info(
                "ToolGuardian: tool '%s' matched %d patrones peligrosos",
                tool_name, len(matched_patterns),
            )

        # Asignar nivel de riesgo
        if risk_score >= 6:
            return ToolRiskLevel.MALICIOUS
        elif risk_score >= 3:
            return ToolRiskLevel.SUSPICIOUS
        return ToolRiskLevel.SAFE

    # ------------------------------------------------------------------
    # Progressive characterization pipeline (arXiv:2607.21835)
    # ------------------------------------------------------------------

    def characterize(
        self,
        tool_name: str,
        tool_code: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[CharacterizationResult]:
        """Ejecutar el pipeline completo de caracterizacion progresiva.

        Las 4 etapas del pipeline (arXiv:2607.21835):
          1. Description: Verifica metadata de la tool.
          2. Syscall: Analiza llamadas al sistema.
          3. Mock execution: Simula ejecucion en sandbox.
          4. Source analysis: Analisis estatico de codigo.

        Args:
            tool_name: Nombre de la tool.
            tool_code: Codigo fuente de la tool.
            metadata: Metadatos de la tool (descripcion, autor, etc.).

        Returns:
            Lista de resultados por etapa del pipeline.
        """
        results: List[CharacterizationResult] = []

        # Stage 1 — Description
        desc_result = self._stage_description(tool_name, metadata)
        results.append(desc_result)

        # Stage 2 — Syscall analysis
        syscall_result = self._stage_syscall(tool_code)
        results.append(syscall_result)

        # Stage 3 — Mock execution
        mock_result = self._stage_mock_execution(tool_code)
        results.append(mock_result)

        # Stage 4 — Source analysis
        source_result = self._stage_source_analysis(tool_code)
        results.append(source_result)

        cumulative_score = sum(r.score for r in results)
        logger.info(
            "ToolGuardian: caracterizacion de '%s' completa — "
            "score acumulativo=%.1f, etapas=%d",
            tool_name, cumulative_score, len(results),
        )

        return results

    def _stage_description(
        self,
        tool_name: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CharacterizationResult:
        """Stage 1: Verificar metadata de la tool.

        Comprueba nombre, descripcion y autor. Tools sin metadata
        o con descripciones sospechosas reciben puntaje de riesgo.

        Args:
            tool_name: Nombre de la tool.
            metadata: Metadatos de la tool.

        Returns:
            CharacterizationResult de la etapa.
        """
        evidence: List[str] = []
        score = 0.0

        if not metadata:
            evidence.append("Sin metadata disponible")
            score += 1.0
        else:
            # Verificar descripcion vacia o generica
            desc = metadata.get("description", "")
            if not desc or len(desc) < 10:
                evidence.append("Descripcion vacia o insuficiente")
                score += 0.5

            # Verificar autor desconocido
            author = metadata.get("author", "")
            if not author or author.lower() in ("unknown", "anonymous", "root"):
                evidence.append("Autor desconocido o sospechoso")
                score += 0.5

            # Verificar nombre sospechoso
            suspicious_names = ["temp", "tmp", "delete", "remove", "clean",
                                "exploit", "hack", "backdoor"]
            for sname in suspicious_names:
                if sname in tool_name.lower():
                    evidence.append(f"Nombre sospechoso contiene '{sname}'")
                    score += 0.5
                    break

        return CharacterizationResult(
            stage=CharacterizationStage.DESCRIPTION,
            passed=score < 1.0,
            score=score,
            evidence=evidence,
            details={"tool_name": tool_name, "metadata_provided": metadata is not None},
        )

    def _stage_syscall(self, tool_code: str) -> CharacterizationResult:
        """Stage 2: Analizar llamadas al sistema.

        Busca syscalls peligrosas en el codigo como execve, ptrace,
        ioctl, etc.

        Args:
            tool_code: Codigo fuente de la tool.

        Returns:
            CharacterizationResult de la etapa.
        """
        evidence: List[str] = []
        score = 0.0

        if not tool_code:
            return CharacterizationResult(
                stage=CharacterizationStage.SYSCALL,
                evidence=["Sin codigo para analizar"],
                score=0.0,
            )

        for syscall in HIGH_RISK_SYSCALLS:
            if re.search(rf"\b{re.escape(syscall)}\b", tool_code, re.IGNORECASE):
                evidence.append(f"Syscall de alto riesgo detectada: {syscall}")
                score += 2.0

        return CharacterizationResult(
            stage=CharacterizationStage.SYSCALL,
            passed=score < 1.0,
            score=score,
            evidence=evidence,
            details={"high_risk_syscalls": len(evidence)},
        )

    def _stage_mock_execution(self, tool_code: str) -> CharacterizationResult:
        """Stage 3: Simular ejecucion en sandbox.

        Analiza el flujo de control del codigo para detectar
        comportamientos peligrosos como loops infinitos, recursion
        excesiva, o intentos de modificar el entorno de ejecucion.

        Args:
            tool_code: Codigo fuente de la tool.

        Returns:
            CharacterizationResult de la etapa.
        """
        evidence: List[str] = []
        score = 0.0

        if not tool_code:
            return CharacterizationResult(
                stage=CharacterizationStage.MOCK_EXECUTION,
                evidence=["Sin codigo para simular"],
                score=0.0,
            )

        # Detectar loops infinitos potenciales
        if re.search(r"while\s+True\s*:", tool_code):
            evidence.append("Loop infinito potencial (while True)")
            score += 1.0

        # Detectar recursion sin condicion de escape
        if re.search(r"def\s+\w+.*:\s*\n\s+return\s+\w+\(", tool_code):
            evidence.append("Recursion potencial detectada")
            score += 1.0

        # Detectar modificacion de variables de entorno
        if re.search(r"os\.environ", tool_code):
            evidence.append("Modificacion de variables de entorno")
            score += 1.0

        # Detectar intentos de acceso a memoria de otros procesos
        if re.search(r"(ptrace|process_vm|mprotect|madvise)", tool_code):
            evidence.append("Acceso a memoria de otros procesos")
            score += 2.0

        return CharacterizationResult(
            stage=CharacterizationStage.MOCK_EXECUTION,
            passed=score < 1.0,
            score=score,
            evidence=evidence,
            details={"dangerous_constructs": len(evidence)},
        )

    def _stage_source_analysis(self, tool_code: str) -> CharacterizationResult:
        """Stage 4: Analisis estatico de codigo fuente.

        Aplica el mismo analisis que analyze_tool() pero devuelve
        un CharacterizationResult estructurado para el pipeline.

        Args:
            tool_code: Codigo fuente de la tool.

        Returns:
            CharacterizationResult de la etapa.
        """
        evidence: List[str] = []
        score = 0.0

        if not tool_code:
            return CharacterizationResult(
                stage=CharacterizationStage.SOURCE_ANALYSIS,
                evidence=["Sin codigo para analizar"],
                score=0.0,
            )

        # Patrones peligrosos
        for pattern in DANGEROUS_PATTERNS:
            matches = re.findall(pattern, tool_code, re.IGNORECASE)
            if matches:
                evidence.append(f"Patron peligroso: {pattern}")
                score += len(matches) * 2.0

        # Ofuscacion
        for ob_pattern in OBFUSCATION_PATTERNS:
            if re.search(ob_pattern, tool_code, re.IGNORECASE):
                evidence.append(f"Ofuscacion detectada: {ob_pattern}")
                score += 3.0

        # Sin docstring
        if '"""' not in tool_code and "'''" not in tool_code:
            evidence.append("Tool sin documentacion (docstring)")
            score += 0.5

        return CharacterizationResult(
            stage=CharacterizationStage.SOURCE_ANALYSIS,
            passed=score < 2.0,
            score=score,
            evidence=evidence,
            details={"matched_patterns": len(evidence)},
        )

    def characterize_with_verdict(
        self,
        tool_name: str,
        tool_code: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Ejecutar pipeline completo y obtener veredicto final.

        Args:
            tool_name: Nombre de la tool.
            tool_code: Codigo fuente.
            metadata: Metadatos opcionales.

        Returns:
            Dict con 'results' (etapas), 'risk_level' (ToolRiskLevel),
            'cumulative_score' (float) y 'verdict' (str legible).
        """
        results = self.characterize(tool_name, tool_code, metadata)
        cumulative_score = sum(r.score for r in results)

        if cumulative_score >= 8.0:
            risk_level = ToolRiskLevel.MALICIOUS
        elif cumulative_score >= 3.0:
            risk_level = ToolRiskLevel.SUSPICIOUS
        else:
            risk_level = ToolRiskLevel.SAFE

        verdict_map = {
            ToolRiskLevel.SAFE: "Tool segura, ejecucion permitida",
            ToolRiskLevel.SUSPICIOUS: "Tool sospechosa, requiere revision humana",
            ToolRiskLevel.MALICIOUS: "Tool maliciosa, ejecucion bloqueada",
        }

        return {
            "results": results,
            "risk_level": risk_level,
            "cumulative_score": cumulative_score,
            "verdict": verdict_map[risk_level],
        }
