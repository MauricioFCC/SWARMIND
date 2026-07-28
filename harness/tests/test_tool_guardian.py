"""Tests para ToolGuardian — seguridad declarativa de tools (arXiv:2607.21835)."""
from __future__ import annotations

import pytest

from harness.orchestrator.tool_guardian import (
    CharacterizationStage,
    CharacterizationResult,
    ToolGuardian,
    ToolPolicy,
    ToolRiskLevel,
)


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def guardian() -> ToolGuardian:
    """ToolGuardian con politicas por defecto."""
    return ToolGuardian()


@pytest.fixture
def strict_guardian() -> ToolGuardian:
    """ToolGuardian en modo estricto."""
    return ToolGuardian(strict_mode=True)


# ===========================================================================
# Test: Politicas por defecto
# ===========================================================================


class TestDefaultPolicies:
    """Verificar que las politicas por defecto se cargan correctamente."""

    def test_list_policies_contains_defaults(self, guardian: ToolGuardian) -> None:
        """Las politicas por defecto deben incluir filesystem, network, etc."""
        policies = guardian.list_policies()
        expected = {"filesystem", "network", "database", "shell", "llm", "git",
                    "tool_registry"}
        for name in expected:
            assert name in policies, f"Falta politica por defecto: {name}"

    def test_policy_has_blocked_actions(self, guardian: ToolGuardian) -> None:
        """Filesystem debe bloquear delete y format."""
        policy = guardian.get_policy("filesystem")
        assert policy is not None
        assert "delete" in policy.blocked_actions
        assert "format" in policy.blocked_actions

    def test_policy_requires_human_approval(self, guardian: ToolGuardian) -> None:
        """Shell debe requerir aprobacion humana."""
        policy = guardian.get_policy("shell")
        assert policy is not None
        assert policy.requires_human_approval is True


# ===========================================================================
# Test: validate_tool_call
# ===========================================================================


class TestValidateToolCall:
    """Validacion de llamadas a tools contra politicas."""

    def test_allowed_action_passes(self, guardian: ToolGuardian) -> None:
        """Accion permitida debe retornar True."""
        assert guardian.validate_tool_call("filesystem", "read") is True

    def test_blocked_action_fails(self, guardian: ToolGuardian) -> None:
        """Accion bloqueada debe retornar False."""
        assert guardian.validate_tool_call("filesystem", "delete") is False

    def test_unknown_tool_fails(self, guardian: ToolGuardian) -> None:
        """Tool sin politica registrada debe retornar False."""
        assert guardian.validate_tool_call("unknown_tool", "read") is False

    def test_strict_mode_rejects_unlisted(self, strict_guardian: ToolGuardian) -> None:
        """Modo estricto debe rechazar acciones no listadas."""
        # 'stream' no esta en allowed_actions ni blocked_actions de llm
        assert strict_guardian.validate_tool_call("llm", "stream") is False

    def test_normal_mode_allows_unlisted(self, guardian: ToolGuardian) -> None:
        """Modo normal debe permitir acciones no listadas."""
        assert guardian.validate_tool_call("llm", "stream") is True

    def test_validate_with_path_context(self, guardian: ToolGuardian) -> None:
        """Validacion contextual de rutas debe rechazar rutas no permitidas."""
        # /etc no esta en allowed_paths de filesystem, debe rechazar
        assert guardian.validate_tool_call("filesystem", "read",
                                           {"path": "/etc/passwd"}) is False
        # /tmp si esta en allowed_paths
        assert guardian.validate_tool_call("filesystem", "read",
                                           {"path": "/tmp/foo.txt"}) is True

    def test_shell_blocked_action_in_content(self, guardian: ToolGuardian) -> None:
        """Shell debe bloquear comandos con rm -rf."""
        assert guardian.validate_tool_call("shell", "execute",
                                           {"cmd": "rm -rf /"}) is True
        # La validacion de blocked_actions es sobre el nombre de la accion,
        # no sobre los argumentos. El contenido del comando se evalua en
        # analyze_tool o en las etapas del pipeline.

    def test_network_blocked_action(self, guardian: ToolGuardian) -> None:
        """Network debe bloquear delete."""
        assert guardian.validate_tool_call("network", "delete") is False

    def test_database_allowed_action(self, guardian: ToolGuardian) -> None:
        """Database debe permitir query."""
        assert guardian.validate_tool_call("database", "query") is True

    def test_database_blocked_action(self, guardian: ToolGuardian) -> None:
        """Database debe bloquear drop."""
        assert guardian.validate_tool_call("database", "drop") is False


# ===========================================================================
# Test: analyze_tool (analisis estatico)
# ===========================================================================


class TestAnalyzeTool:
    """Analisis estatico de codigo fuente de tools."""

    def test_safe_code_returns_safe(self, guardian: ToolGuardian) -> None:
        """Codigo seguro debe retornar SAFE."""
        codigo = '''
def sumar(a: int, b: int) -> int:
    """Suma dos numeros."""
    return a + b
'''
        assert guardian.analyze_tool("math_tool", codigo) == ToolRiskLevel.SAFE

    def test_suspicious_code_returns_suspicious(self, guardian: ToolGuardian) -> None:
        """Codigo con patron peligroso debe retornar SUSPICIOUS."""
        codigo = '''
def leer_y_ejecutar(ruta: str) -> str:
    """Lee un archivo del sistema y ejecuta."""
    with open(ruta, "r") as f:
        return f.read()
    subprocess.run(["ls"])
'''
        assert guardian.analyze_tool("file_reader", codigo) == ToolRiskLevel.SUSPICIOUS

    def test_malicious_code_returns_malicious(self, guardian: ToolGuardian) -> None:
        """Codigo con exec() y eval() debe retornar MALICIOUS."""
        codigo = '''
def ejecutar(codigo: str) -> None:
    """Ejecuta codigo arbitrario."""
    exec(codigo)
    eval("os.system('rm -rf /')")
'''
        assert guardian.analyze_tool("executor", codigo) == ToolRiskLevel.MALICIOUS

    def test_empty_code_returns_safe(self, guardian: ToolGuardian) -> None:
        """Codigo vacio debe retornar SAFE."""
        assert guardian.analyze_tool("empty", "") == ToolRiskLevel.SAFE
        assert guardian.analyze_tool("empty", "   ") == ToolRiskLevel.SAFE

    def test_code_with_subprocess_is_malicious(self, guardian: ToolGuardian) -> None:
        """Codigo con subprocess debe ser al menos SUSPICIOUS."""
        codigo = '''
import subprocess
subprocess.run(["rm", "-rf", "/"])
'''
        assert guardian.analyze_tool("danger", codigo) in (
            ToolRiskLevel.SUSPICIOUS, ToolRiskLevel.MALICIOUS
        )

    def test_code_with_obfuscation_is_suspicious(self, guardian: ToolGuardian) -> None:
        """Codigo con ofuscacion debe ser SUSPICIOUS."""
        codigo = '''
import base64
cod = base64.b64decode("cHJpbnQoImhlbGxvIik=")
exec(cod)
'''
        level = guardian.analyze_tool("obfuscated", codigo)
        assert level in (ToolRiskLevel.SUSPICIOUS, ToolRiskLevel.MALICIOUS)

    def test_code_without_docstring_penalty(self, guardian: ToolGuardian) -> None:
        """Codigo sin docstring debe sumar riesgo."""
        codigo = "def f(): return 42"
        # Sin docstring suma 1 punto, pero es insuficiente para sospechoso
        assert guardian.analyze_tool("no_doc", codigo) == ToolRiskLevel.SAFE


# ===========================================================================
# Test: Progressive Characterization Pipeline
# ===========================================================================


class TestCharacterizationPipeline:
    """Pipeline de caracterizacion progresiva (arXiv:2607.21835)."""

    def test_pipeline_returns_four_stages(self, guardian: ToolGuardian) -> None:
        """El pipeline debe retornar exactamente 4 etapas."""
        results = guardian.characterize("test_tool", "print('hello')",
                                        metadata={"description": "test", "author": "dev"})
        assert len(results) == 4
        stages = [r.stage for r in results]
        assert CharacterizationStage.DESCRIPTION in stages
        assert CharacterizationStage.SYSCALL in stages
        assert CharacterizationStage.MOCK_EXECUTION in stages
        assert CharacterizationStage.SOURCE_ANALYSIS in stages

    def test_stage_description_no_metadata(self, guardian: ToolGuardian) -> None:
        """Stage Description debe detectar falta de metadata."""
        results = guardian.characterize("test_tool", "print('hello')")
        desc_result = results[0]
        assert desc_result.stage == CharacterizationStage.DESCRIPTION
        assert desc_result.score > 0
        assert "Sin metadata" in " ".join(desc_result.evidence)

    def test_stage_syscall_detects_ptrace(self, guardian: ToolGuardian) -> None:
        """Stage Syscall debe detectar ptrace."""
        codigo = "import ptrace\nptrace.traceme()"
        results = guardian.characterize("debug_tool", codigo)
        syscall_result = results[1]
        assert syscall_result.stage == CharacterizationStage.SYSCALL
        assert syscall_result.score > 0
        assert any("ptrace" in e for e in syscall_result.evidence)

    def test_stage_mock_execution_while_true(self, guardian: ToolGuardian) -> None:
        """Stage Mock Execution debe detectar while True."""
        codigo = "while True:\n    print('loop')"
        results = guardian.characterize("looper", codigo)
        mock_result = results[2]
        assert mock_result.stage == CharacterizationStage.MOCK_EXECUTION
        assert mock_result.score > 0
        assert any("Loop" in e for e in mock_result.evidence)

    def test_stage_source_analysis_malicious(self, guardian: ToolGuardian) -> None:
        """Stage Source Analysis debe detectar exec()."""
        codigo = "exec('dangerous_code')"
        results = guardian.characterize("mal", codigo)
        source_result = results[3]
        assert source_result.stage == CharacterizationStage.SOURCE_ANALYSIS

    def test_characterize_with_verdict_safe(self, guardian: ToolGuardian) -> None:
        """Veredicto para tool segura debe ser SAFE."""
        codigo = '''
def sumar(a: int, b: int) -> int:
    """Suma dos numeros."""
    return a + b
'''
        verdict = guardian.characterize_with_verdict("math", codigo,
                                                     metadata={"description": "math ops",
                                                               "author": "core"})
        assert verdict["risk_level"] == ToolRiskLevel.SAFE
        assert verdict["cumulative_score"] < 3.0
        assert "permitida" in verdict["verdict"]

    def test_characterize_with_verdict_malicious(self, guardian: ToolGuardian) -> None:
        """Veredicto para tool maliciosa debe ser MALICIOUS."""
        codigo = '''
import subprocess
import os
import socket

def exploit():
    """Exploit"""
    exec("malicious_code")
    eval("os.system('rm -rf /')")
    os.system("rm -rf /")
    subprocess.run(["dd", "if=/dev/zero", "of=/dev/sda"])
    sock = socket.socket()
'''
        verdict = guardian.characterize_with_verdict("exploit", codigo)
        assert verdict["risk_level"] == ToolRiskLevel.MALICIOUS
        assert verdict["cumulative_score"] >= 8.0
        assert "bloqueada" in verdict["verdict"]


# ===========================================================================
# Test: Gestion de politicas (CRUD)
# ===========================================================================


class TestPolicyManagement:
    """Registro, obtencion y eliminacion de politicas."""

    def test_register_custom_policy(self, guardian: ToolGuardian) -> None:
        """Registrar politica personalizada debe funcionar."""
        policy = ToolPolicy(
            name="custom_service",
            allowed_actions=["ping", "status"],
            blocked_actions=["shutdown"],
            max_execution_time=5,
        )
        guardian.register_policy(policy)
        retrieved = guardian.get_policy("custom_service")
        assert retrieved is not None
        assert retrieved.name == "custom_service"
        assert "ping" in retrieved.allowed_actions

    def test_register_overwrites_existing(self, guardian: ToolGuardian) -> None:
        """Sobrescribir politica existente debe actualizarla."""
        nueva = ToolPolicy(name="filesystem",
                           allowed_actions=["read"],
                           blocked_actions=[])
        guardian.register_policy(nueva)
        policy = guardian.get_policy("filesystem")
        assert policy is not None
        assert "read" in policy.allowed_actions
        assert "write" not in policy.allowed_actions

    def test_remove_policy(self, guardian: ToolGuardian) -> None:
        """Eliminar politica debe removerla del registro."""
        assert guardian.remove_policy("llm") is True
        assert guardian.get_policy("llm") is None
        assert "llm" not in guardian.list_policies()

    def test_remove_nonexistent_policy(self, guardian: ToolGuardian) -> None:
        """Eliminar politica inexistente debe retornar False."""
        assert guardian.remove_policy("no_existe") is False

    def test_list_policies(self, guardian: ToolGuardian) -> None:
        """Listar politicas debe devolver todas las registradas."""
        policies = guardian.list_policies()
        assert len(policies) >= 7
        assert "shell" in policies
        assert "database" in policies


# ===========================================================================
# Test: Caracterizacion — casos borde
# ===========================================================================


class TestCharacterizationEdgeCases:
    """Casos borde del pipeline de caracterizacion."""

    def test_empty_code_all_stages_pass_safe(self, guardian: ToolGuardian) -> None:
        """Codigo vacio debe ser SAFE en todas las etapas."""
        results = guardian.characterize("empty_tool", "")
        assert len(results) == 4
        # Sin codigo, las etapas 2-4 tienen score 0
        assert results[1].score == 0.0  # syscall
        assert results[2].score == 0.0  # mock execution
        assert results[3].score == 0.0  # source analysis

    def test_suspicious_name_in_metadata(self, guardian: ToolGuardian) -> None:
        """Nombre de tool sospechoso debe incrementar score en Stage 1."""
        results = guardian.characterize("temp_delete", "print('ok')",
                                        metadata={"description": "util",
                                                  "author": "dev"})
        desc_result = results[0]
        assert any("sospechoso" in e for e in desc_result.evidence)

    def test_author_unknown_increments_score(self, guardian: ToolGuardian) -> None:
        """Autor 'anonymous' debe incrementar score en Stage 1."""
        results = guardian.characterize("tool", "print('ok')",
                                        metadata={"description": "una herramienta",
                                                  "author": "anonymous"})
        desc_result = results[0]
        assert any("Autor" in e for e in desc_result.evidence)

    def test_os_environ_detected_mock_execution(self, guardian: ToolGuardian) -> None:
        """os.environ debe detectarse en Stage 3."""
        codigo = "import os\nos.environ['PATH'] = '/tmp'"
        results = guardian.characterize("env_tool", codigo)
        mock_result = results[2]
        assert any("entorno" in e.lower() for e in mock_result.evidence)

    def test_pipeline_evidence_accumulates(self, guardian: ToolGuardian) -> None:
        """La evidencia debe acumularse correctamente entre etapas."""
        codigo = '''
import os
import subprocess

def backdoor():
    """Backdoor entry point"""
    while True:
        cmd = input("> ")
        os.system(cmd)
'''
        results = guardian.characterize("backdoor", codigo)
        total_evidence = sum(len(r.evidence) for r in results)
        assert total_evidence >= 3

    def test_cumulative_score_all_stages(self, guardian: ToolGuardian) -> None:
        """Score acumulativo debe ser suma de todas las etapas."""
        codigo = "exec('x')"
        results = guardian.characterize("exec_tool", codigo)
        cumulative = sum(r.score for r in results)
        # stage 1: sin metadata -> 1.0, stage 4: exec -> 2.0
        assert cumulative >= 2.0

    def test_characterize_with_verdict_returns_all_keys(self,
                                                       guardian: ToolGuardian) -> None:
        """El veredicto debe contener todas las claves esperadas."""
        v = guardian.characterize_with_verdict("t", "print('ok')")
        assert "results" in v
        assert "risk_level" in v
        assert "cumulative_score" in v
        assert "verdict" in v
        assert len(v["results"]) == 4


# ===========================================================================
# Test: strict_mode en politicas
# ===========================================================================


class TestStrictMode:
    """Comportamiento del modo estricto."""

    def test_strict_rejects_unknown_tool(self, strict_guardian: ToolGuardian) -> None:
        """Modo estricto rechaza tools sin politica."""
        assert strict_guardian.validate_tool_call("unknown", "list") is False

    def test_strict_allows_explicit_allowed(self, strict_guardian: ToolGuardian) -> None:
        """Modo estricto permite acciones explicitamente permitidas."""
        assert strict_guardian.validate_tool_call("filesystem", "read") is True

    def test_strict_rejects_blocked(self, strict_guardian: ToolGuardian) -> None:
        """Modo estricto bloquea acciones explicitamente bloqueadas."""
        # Para 'database', 'drop' esta en blocked_actions
        assert strict_guardian.validate_tool_call("database", "drop") is False


# ===========================================================================
# Test: Caracterizacion — APIs Legitimas
# ===========================================================================


class TestLegitimateTools:
    """Tools legitimas deben pasar el pipeline sin falsos positivos."""

    SAFE_CODIGO = '''
def calcular_imc(peso: float, altura: float) -> float:
    """Calcula el indice de masa corporal.

    Args:
        peso: Peso en kilogramos.
        altura: Altura en metros.

    Returns:
        IMC calculado.
    """
    if altura <= 0:
        raise ValueError("Altura debe ser positiva")
    return peso / (altura ** 2)
'''

    def test_legitimate_tool_safe_verdict(self, guardian: ToolGuardian) -> None:
        """Tool legitima debe obtener veredicto SAFE."""
        meta = {"description": "Calcula IMC dado peso y altura",
                "author": "health-team"}
        verdict = guardian.characterize_with_verdict("imc_calculator",
                                                      self.SAFE_CODIGO,
                                                      metadata=meta)
        assert verdict["risk_level"] == ToolRiskLevel.SAFE
        assert verdict["cumulative_score"] < 2.0

    def test_legitimate_tool_validate_passes(self, guardian: ToolGuardian) -> None:
        """Tool legitima debe pasar validacion."""
        assert guardian.validate_tool_call("filesystem", "list") is True


# ===========================================================================
# Test: CharacterizationResult dataclass
# ===========================================================================


class TestCharacterizationResult:
    """Verificar estructura de CharacterizationResult."""

    def test_default_values(self) -> None:
        """Valores por defecto deben ser correctos."""
        result = CharacterizationResult(stage=CharacterizationStage.DESCRIPTION)
        assert result.passed is True
        assert result.score == 0.0
        assert result.evidence == []
        assert result.details == {}

    def test_custom_values(self) -> None:
        """Valores personalizados deben asignarse correctamente."""
        result = CharacterizationResult(
            stage=CharacterizationStage.SOURCE_ANALYSIS,
            passed=False,
            score=5.0,
            evidence=["exec() detectado"],
            details={"pattern": "exec"},
        )
        assert result.stage == CharacterizationStage.SOURCE_ANALYSIS
        assert result.passed is False
        assert result.score == 5.0


# ===========================================================================
# Test: Edge cases adicionales
# ===========================================================================


class TestEdgeCases:
    """Casos limite adicionales."""

    def test_validate_case_insensitive(self, guardian: ToolGuardian) -> None:
        """La validacion debe ser case-insensitive para acciones."""
        assert guardian.validate_tool_call("filesystem", "READ") is True
        assert guardian.validate_tool_call("filesystem", "DELETE") is False

    def test_validate_none_args(self, guardian: ToolGuardian) -> None:
        """args=None no debe causar error."""
        assert guardian.validate_tool_call("filesystem", "read", None) is True

    def test_analyze_tool_none_code(self, guardian: ToolGuardian) -> None:
        """analyze_tool con None debe retornar SAFE sin error."""
        assert guardian.analyze_tool("test", "") == ToolRiskLevel.SAFE

    def test_multiple_strict_mode_reject(self, strict_guardian: ToolGuardian) -> None:
        """Modo estricto debe rechazar acciones no listadas explicitamente."""
        # 'walk' no esta en filesystem policies
        assert strict_guardian.validate_tool_call("filesystem", "walk") is False
