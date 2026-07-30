"""Tests para el sistema Multi-Harness Adapter Layer.

Cubre:
- runtime_detector: deteccion automatica de runtime
- converter_base: clase base abstracta
- adapters: exportacion a cada runtime
- CLI: comandos principales
- ide_adapter: fachada de compatibilidad
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Generator, List

import pytest

from harness.orchestrator.ide_adapter import IDEAdapter, SUPPORTED_IDES
from harness.orchestrator.multi_harness import HarnessConverter, RuntimeInfo, detect_runtime
from harness.orchestrator.multi_harness.adapters import (
    ClaudeAdapter,
    CodexAdapter,
    CursorAdapter,
    GeminiAdapter,
    OpenCodeAdapter,
)
from harness.orchestrator.multi_harness.cli.multi_harness_cli import (
    cmd_detect,
    cmd_export,
    cmd_status,
    cmd_validate,
)
from harness.orchestrator.multi_harness.converter_base import ExportResult
from harness.orchestrator.multi_harness.runtime_detector import (
    RUNTIME_REGISTRY,
    get_detected_runtimes,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def temp_project() -> Generator[Path, None, None]:
    """Crea un proyecto temporal con estructura .opencode/."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        # Crear estructura minima de .opencode/
        (root / ".opencode" / "agents").mkdir(parents=True)
        (root / ".opencode" / "skills").mkdir(parents=True)
        (root / ".opencode" / "rag").mkdir(parents=True)

        # Agente de prueba
        agent_file = root / ".opencode" / "agents" / "test-agent.md"
        agent_file.write_text("# Test Agent\nUn agente de prueba.\n", encoding="utf-8")

        # Skill de prueba
        skill_file = root / ".opencode" / "skills" / "test-skill.md"
        skill_file.write_text("# Test Skill\nUn skill de prueba.\n", encoding="utf-8")

        # Config de prueba
        config_file = root / ".opencode" / "opencode.json"
        config_file.write_text('{"project": "test", "version": "1.0.0"}', encoding="utf-8")

        yield root


# ============================================================================
# Tests: Runtime Detector
# ============================================================================

class TestRuntimeDetector:
    """Tests para la deteccion automatica de runtime."""

    def test_detect_opencode_default(self, temp_project: Path) -> None:
        """Debe detectar OpenCode como runtime por defecto."""
        runtime = detect_runtime(temp_project)
        assert runtime.name == "opencode"
        assert runtime.detected is True

    def test_detect_explicit_override(self, temp_project: Path) -> None:
        """Debe respetar la variable Swarmind_RUNTIME explicita."""
        os.environ["Swarmind_RUNTIME"] = "claude"
        try:
            runtime = detect_runtime(temp_project)
            assert runtime.name == "claude"
            assert runtime.detected is True
        finally:
            del os.environ["Swarmind_RUNTIME"]

    def test_get_detected_runtimes_empty(self, temp_project: Path) -> None:
        """Sin directorios de runtime, solo detecta .opencode/."""
        detected = get_detected_runtimes(temp_project)
        names = [rt.name for rt in detected]
        assert "opencode" in names

    def test_runtime_registry_completeness(self) -> None:
        """El registro debe tener 5 runtimes definidos."""
        assert len(RUNTIME_REGISTRY) == 5
        names = [rt.name for rt in RUNTIME_REGISTRY]
        assert "opencode" in names
        assert "claude" in names
        assert "codex" in names
        assert "cursor" in names
        assert "gemini" in names

    def test_runtime_info_defaults(self) -> None:
        """RuntimeInfo debe tener valores por defecto correctos."""
        rt = RuntimeInfo(name="test", display_name="Test Runtime", config_dir=".test", env_var="TEST_ENV")
        assert rt.detected is False
        assert rt.config_path is None
        assert rt.version is None


# ============================================================================
# Tests: Converter Base
# ============================================================================

class TestHarnessConverter:
    """Tests para la clase base HarnessConverter."""

    def test_converter_abstract_cannot_instantiate(self) -> None:
        """No se debe poder instanciar HarnessConverter directamente."""
        with pytest.raises(TypeError):
            HarnessConverter()  # type: ignore

    def test_concrete_adapter_works(self, temp_project: Path) -> None:
        """OpenCodeAdapter debe funcionar como adaptador concreto."""
        adapter = OpenCodeAdapter(temp_project)
        assert adapter.runtime_name == "opencode"
        assert adapter.display_name == "OpenCode"
        assert adapter.target_config_dir == ".opencode"

    def test_validate_ok(self, temp_project: Path) -> None:
        """validate() debe retornar lista vacia si la estructura es correcta."""
        adapter = OpenCodeAdapter(temp_project)
        errors = adapter.validate()
        assert errors == []

    def test_validate_missing_opencode(self) -> None:
        """validate() debe detectar .opencode/ faltante."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            adapter = OpenCodeAdapter(root)
            errors = adapter.validate()
            assert len(errors) > 0
            assert any(".opencode/" in err for err in errors)


# ============================================================================
# Tests: Adapters
# ============================================================================

class TestOpenCodeAdapter:
    """Tests para el adaptador nativo de OpenCode."""

    def test_export_agents(self, temp_project: Path) -> None:
        """export_agents debe reportar los agentes encontrados."""
        adapter = OpenCodeAdapter(temp_project)
        result = adapter.export_agents()
        assert result.success is True
        assert result.files_exported == 1

    def test_export_skills(self, temp_project: Path) -> None:
        """export_skills debe reportar los skills encontrados."""
        adapter = OpenCodeAdapter(temp_project)
        result = adapter.export_skills()
        assert result.success is True
        assert result.files_exported == 1

    def test_export_dry_run(self, temp_project: Path) -> None:
        """dry_run no debe modificar archivos."""
        adapter = OpenCodeAdapter(temp_project)
        result = adapter.export_agents(dry_run=True)
        assert result.success is True

    def test_get_stats(self, temp_project: Path) -> None:
        """get_stats debe retornar estadisticas correctas."""
        adapter = OpenCodeAdapter(temp_project)
        stats = adapter.get_stats()
        assert stats["num_agents"] == 1
        assert stats["num_skills"] == 1


class TestClaudeAdapter:
    """Tests para el adaptador de Claude Code."""

    def test_adapter_properties(self) -> None:
        """Debe tener propiedades correctas."""
        adapter = ClaudeAdapter()
        assert adapter.runtime_name == "claude"
        assert adapter.display_name == "Claude Code"
        assert adapter.target_config_dir == ".claude"

    def test_export_agents_dry_run(self, temp_project: Path) -> None:
        """dry_run debe reportar agentes sin copiar."""
        adapter = ClaudeAdapter(temp_project)
        result = adapter.export_agents(dry_run=True)
        assert result.success is True
        assert result.files_exported > 0

    def test_export_skills_dry_run(self, temp_project: Path) -> None:
        """dry_run debe reportar skills sin copiar."""
        adapter = ClaudeAdapter(temp_project)
        result = adapter.export_skills(dry_run=True)
        assert result.success is True

    def test_export_config_dry_run(self, temp_project: Path) -> None:
        """dry_run debe reportar config sin escribir."""
        adapter = ClaudeAdapter(temp_project)
        result = adapter.export_config(dry_run=True)
        assert result.success is True

    def test_export_agents_real(self, temp_project: Path) -> None:
        """Exportacion real debe crear archivos en .claude/."""
        adapter = ClaudeAdapter(temp_project)
        result = adapter.export_agents()
        assert result.success is True
        assert result.files_exported == 1
        # Verificar que se creo AGENTS.md
        agents_md = temp_project / ".claude" / "AGENTS.md"
        assert agents_md.exists()
        content = agents_md.read_text(encoding="utf-8")
        assert "Test Agent" in content


class TestCodexAdapter:
    """Tests para el adaptador de Codex CLI."""

    def test_adapter_properties(self) -> None:
        adapter = CodexAdapter()
        assert adapter.runtime_name == "codex"

    def test_export_agents_real(self, temp_project: Path) -> None:
        adapter = CodexAdapter(temp_project)
        result = adapter.export_agents()
        assert result.success is True
        assert result.files_exported == 1
        prompts_dir = temp_project / ".codex" / "prompts"
        assert prompts_dir.is_dir()


class TestCursorAdapter:
    """Tests para el adaptador de Cursor."""

    def test_export_config_real(self, temp_project: Path) -> None:
        adapter = CursorAdapter(temp_project)
        result = adapter.export_config()
        assert result.success is True
        cursorrules = temp_project / ".cursorrules"
        assert cursorrules.exists()
        content = cursorrules.read_text(encoding="utf-8")
        assert "Swarmind" in content
        assert "Test Skill" in content


class TestGeminiAdapter:
    """Tests para el adaptador de Gemini CLI."""

    def test_export_config_real(self, temp_project: Path) -> None:
        adapter = GeminiAdapter(temp_project)
        result = adapter.export_config()
        assert result.success is True
        instructions = temp_project / ".gemini" / "instructions.md"
        assert instructions.exists()
        content = instructions.read_text(encoding="utf-8")
        assert "Swarmind" in content


# ============================================================================
# Tests: CLI
# ============================================================================

class TestCLI:
    """Tests para los comandos CLI del Multi-Harness."""

    def test_cmd_detect(self, temp_project: Path) -> None:
        """cmd_detect debe detectar el runtime correctamente."""
        runtime = cmd_detect(temp_project)
        assert runtime.name == "opencode"

    def test_cmd_status(self, temp_project: Path) -> None:
        """cmd_status debe retornar informacion del proyecto."""
        status = cmd_status(temp_project)
        assert "active_runtime" in status
        assert status["active_runtime"]["name"] == "opencode"

    def test_cmd_export_opencode(self, temp_project: Path) -> None:
        """cmd_export a opencode debe ser exitoso."""
        result = cmd_export("opencode", project_root=temp_project)
        assert result is True

    def test_cmd_export_claude_dry_run(self, temp_project: Path) -> None:
        """cmd_export a claude con dry-run debe ser exitoso."""
        result = cmd_export("claude", dry_run=True, project_root=temp_project)
        assert result is True

    def test_cmd_export_invalid_target(self, temp_project: Path) -> None:
        """cmd_export con target invalido debe fallar."""
        result = cmd_export("invalid_runtime", project_root=temp_project)
        assert result is False

    def test_cmd_validate(self, temp_project: Path) -> None:
        """cmd_validate debe validar la estructura del proyecto."""
        result = cmd_validate(temp_project)
        assert result is True


# ============================================================================
# Tests: IDEAdapter (fachada legacy)
# ============================================================================

class TestIDEAdapterFacade:
    """Tests para la fachada IDEAdapter (compatibilidad hacia atras)."""

    def test_detect_ides(self, temp_project: Path) -> None:
        """detect_ides debe funcionar como antes."""
        adapter = IDEAdapter(temp_project)
        ides = adapter.detect_ides()
        assert "OpenCode" in ides

    def test_get_supported_ides(self) -> None:
        """get_supported_ides debe retornar los 5 IDEs."""
        adapter = IDEAdapter()
        ides = adapter.get_supported_ides()
        assert len(ides) == 5

    def test_export_agents_claude(self, temp_project: Path) -> None:
        """export_agents debe funcionar via fachada."""
        adapter = IDEAdapter(temp_project)
        result = adapter.export_agents("Claude Code", dry_run=True)
        assert result is True

    def test_detect_runtime(self, temp_project: Path) -> None:
        """detect_runtime debe funcionar via fachada."""
        adapter = IDEAdapter(temp_project)
        runtime = adapter.detect_runtime()
        assert runtime.name == "opencode"

    def test_validate(self, temp_project: Path) -> None:
        """validate debe funcionar via fachada."""
        adapter = IDEAdapter(temp_project)
        result = adapter.validate()
        assert result is True
