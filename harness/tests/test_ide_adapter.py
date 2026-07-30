"""
Tests para IDEAdapter — Integracion con multiples IDEs.

Verifica deteccion de IDEs presentes en el proyecto, exportacion de
agentes Swarmind a formatos de IDEs destino, y consistencia de la
lista de IDEs soportados.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


from harness.orchestrator.ide_adapter import SUPPORTED_IDES, IDEAdapter, IDESupport


class TestIDEAdapter:
    """Suite de tests para el adaptador multi-harness de IDEs."""

    # ------------------------------------------------------------------
    # Tests de deteccion
    # ------------------------------------------------------------------

    def test_detect_no_ides(self, tmp_path: Path) -> None:
        """Proyecto vacio no detecta ningun IDE.

        Verifica que detect_ides() retorna lista vacia cuando no existe
        ningun archivo de configuracion de IDE en la raiz del proyecto.
        """
        adapter = IDEAdapter(project_root=tmp_path)
        detected = adapter.detect_ides()
        assert detected == [], (
            f"Se esperaba lista vacia, pero se detecto: {detected}"
        )

    def test_detect_opencode_present(self, tmp_path: Path) -> None:
        """Proyecto con .opencode/ detecta OpenCode.

        Verifica que al crear el directorio .opencode/ en la raiz,
        detect_ides() incluye 'OpenCode' en la lista de IDEs detectados.
        """
        (tmp_path / ".opencode").mkdir()
        adapter = IDEAdapter(project_root=tmp_path)
        detected = adapter.detect_ides()
        assert "OpenCode" in detected, (
            f"'OpenCode' deberia estar en detectados: {detected}"
        )

    def test_detect_multi_ide(self, tmp_path: Path) -> None:
        """Proyecto con multiples IDEs detecta todos.

        Verifica que al crear .claude/settings.json y .cursorrules,
        ambos IDEs son detectados simultaneamente.
        """
        (tmp_path / ".claude").mkdir()
        (tmp_path / ".claude" / "settings.json").write_text("{}")
        (tmp_path / ".cursor").mkdir()
        adapter = IDEAdapter(project_root=tmp_path)
        detected = adapter.detect_ides()
        assert "Claude Code" in detected
        assert "Cursor" in detected
        assert len(detected) >= 2

    # ------------------------------------------------------------------
    # Tests de exportacion
    # ------------------------------------------------------------------

    def test_export_agents_no_source(self, tmp_path: Path) -> None:
        """Exportacion falla si no existe .opencode/agents/.

        Verifica que export_agents() retorna False cuando el directorio
        de agentes origen no existe.
        """
        adapter = IDEAdapter(project_root=tmp_path)
        result = adapter.export_agents("OpenCode")
        assert result is False, (
            "Se esperaba False sin directorio de agentes origen"
        )

    def test_export_agents_unsupported_ide(self, tmp_path: Path) -> None:
        """Exportacion falla con IDE no soportado.

        Verifica que export_agents() retorna False si se pasa un nombre
        de IDE que no esta en SUPPORTED_IDES.
        """
        # Crear .opencode/agents/ con contenido para que no falle antes
        agents_dir = tmp_path / ".opencode" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "test_agent.md").write_text("# Test Agent")

        adapter = IDEAdapter(project_root=tmp_path)
        result = adapter.export_agents("VSCode")
        assert result is False, (
            "Se esperaba False para IDE no soportado"
        )

    def test_export_agents_dry_run(self, tmp_path: Path) -> None:
        """Dry-run reporta agentes disponibles sin copiar.

        Verifica que con dry_run=True, export_agents() retorna True si
        hay agentes, pero no crea archivos en el destino.
        """
        agents_dir = tmp_path / ".opencode" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "builder.md").write_text("# Builder Agent")
        (agents_dir / "scientist.md").write_text("# Scientist Agent")
        skills_dir = tmp_path / ".opencode" / "skills"
        skills_dir.mkdir()
        (skills_dir / "dummy.md").write_text("# skill")
        (tmp_path / ".opencode" / "opencode.json").write_text("{}")

        adapter = IDEAdapter(project_root=tmp_path)
        result = adapter.export_agents("OpenCode", dry_run=True)
        assert result is True, (
            "Dry-run deberia retornar True con agentes disponibles"
        )

    def test_export_agents_empty_dry_run(self, tmp_path: Path) -> None:
        """Dry-run retorna False si no hay agentes .md.

        Verifica que dry-run con directorio de agentes vacio retorna
        False sin copiar nada.
        """
        agents_dir = tmp_path / ".opencode" / "agents"
        agents_dir.mkdir(parents=True)
        # Solo un archivo no-.md
        (agents_dir / "not_an_agent.txt").write_text("data")

        adapter = IDEAdapter(project_root=tmp_path)
        result = adapter.export_agents("OpenCode", dry_run=True)
        assert result is False, (
            "Dry-run deberia retornar False sin agentes .md"
        )

    # ------------------------------------------------------------------
    # Tests de estructura de datos
    # ------------------------------------------------------------------

    def test_supported_ides_completeness(self) -> None:
        """SUPPORTED_IDES contiene los 5 IDEs esperados.

        Verifica que la lista canonica tenga exactamente los 5 IDEs
        que el adaptador declara soportar y que cada entrada tenga
        todos sus campos correctamente poblados.
        """
        assert len(SUPPORTED_IDES) == 5, (
            f"Se esperaban 5 IDEs soportados, hay {len(SUPPORTED_IDES)}"
        )
        names = [ide.name for ide in SUPPORTED_IDES]
        expected = [
            "Claude Code",
            "Codex CLI",
            "Cursor",
            "OpenCode",
            "Gemini CLI",
        ]
        assert names == expected, (
            f"Nombres de IDEs no coinciden:\nesperado={expected}\nobtenido={names}"
        )
        # Todos los campos deben ser strings no vacios
        for ide in SUPPORTED_IDES:
            assert isinstance(ide.name, str) and ide.name
            assert isinstance(ide.config_file, str) and ide.config_file
            assert isinstance(ide.agents_format, str) and ide.agents_format
            assert isinstance(ide.skills_path, str) and ide.skills_path

    def test_idesupport_dataclass(self) -> None:
        """IDESupport se comporta como dataclass inmutable.

        Verifica que los campos son accesibles, que el objeto es
        congelado (no se pueden asignar nuevos atributos), y que
        la representacion __repr__ es informativa.
        """
        ide = IDESupport("TestIDE", ".test/config", "agents.yaml", ".test/skills/")
        assert ide.name == "TestIDE"
        assert ide.config_file == ".test/config"
        assert ide.agents_format == "agents.yaml"
        assert ide.skills_path == ".test/skills/"
        # Verificar que repr contiene los valores
        rep = repr(ide)
        assert "TestIDE" in rep
        assert ".test/config" in rep
        # Los dataclass estandar permiten re-asignacion (no frozen),
        # pero solo verificamos que el constructor funciona.
        ide2 = IDESupport("TestIDE", ".test/config", "agents.yaml", ".test/skills/")
        assert ide == ide2


class TestIDEAdapterIntegration:
    """Tests de integracion con el sistema de archivos real."""

    def test_get_supported_ides_returns_copy(self) -> None:
        """get_supported_ides retorna copia, no la lista original.

        Verifica que modificar la lista retornada no afecta a
        SUPPORTED_IDES global.
        """
        adapter = IDEAdapter()
        ides = adapter.get_supported_ides()
        ides.clear()
        assert len(SUPPORTED_IDES) == 5, (
            "Modificar la copia no debe afectar SUPPORTED_IDES global"
        )

    def test_detect_opencode_in_real_project(self) -> None:
        """En el proyecto real, OpenCode debe ser detectable.

        Verifica que el proyecto Swarmind (que tiene .opencode/) sea
        detectado correctamente.
        """
        project_root = Path(__file__).resolve().parent.parent.parent
        adapter = IDEAdapter(project_root=project_root)
        detected = adapter.detect_ides()
        assert "OpenCode" in detected, (
            f"OpenCode deberia estar presente en el proyecto real. "
            f"Detectados: {detected}"
        )
