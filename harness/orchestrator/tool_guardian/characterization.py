"""ToolGuardian characterization — mixin del pipeline progresivo.

Extraccion mecanica del modulo original
``harness/orchestrator/tool_guardian.py`` (sin cambios de logica
ni firmas): pipeline de caracterizacion progresiva con sus 4 etapas
y el veredicto final (arXiv:2607.21835).
"""

from __future__ import annotations

import logging
import re
from typing import Any

from .constants import DANGEROUS_PATTERNS, HIGH_RISK_SYSCALLS, OBFUSCATION_PATTERNS
from .models import (
    CharacterizationResult,
    CharacterizationStage,
    ToolPolicy,
    ToolRiskLevel,
)

logger = logging.getLogger(__name__)


class _CharacterizationMixin:
    """Mixin con el pipeline de caracterizacion progresiva."""

    # ------------------------------------------------------------------
    # Progressive characterization pipeline (arXiv:2607.21835)
    # ------------------------------------------------------------------

    def characterize(
        self,
        tool_name: str,
        tool_code: str,
        metadata: dict[str, Any] | None = None,
    ) -> list[CharacterizationResult]:
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
        results: list[CharacterizationResult] = []

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
        metadata: dict[str, Any] | None = None,
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
        evidence: list[str] = []
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
        evidence: list[str] = []
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
        evidence: list[str] = []
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
        evidence: list[str] = []
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
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
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

    def _load_default_policies(self) -> None:
        """Carga las politicas de seguridad por defecto (por herramienta)."""
        # Archivos: solo lectura/escritura controlada
        self._policies["filesystem"] = ToolPolicy(
            name="filesystem",
            allowed_actions=["read", "write", "list", "stat"],
            blocked_actions=["delete", "format", "chmod", "chown", "mkfs",
                             "mount", "umount", "truncate"],
            max_execution_time=10,
            # sandbox: lista de rutas permitidas por diseno (no se escribe ahi)
            allowed_paths=["/tmp", "/home", "/data", "./"],  # nosec B108
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

    def get_policy(self, tool_name: str) -> ToolPolicy | None:
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

    def list_policies(self) -> list[str]:
        """Listar los nombres de todas las politicas registradas.

        Returns:
            Lista de nombres de politicas.
        """
        return list(self._policies.keys())
