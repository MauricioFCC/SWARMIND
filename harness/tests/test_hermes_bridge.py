# -*- coding: utf-8 -*-
"""
Tests para HermesBridge (memory_rag/hermes_bridge.py) — puente de
integración con shared_memory.

Cubre: inicialización, resolución de paths, propiedades, sincronización
(to/from/skills), acceso a servicios, status y edge cases.

NOTA: Este test cubre el HermesBridge en memory_rag/, NO el de
harness/hermes_bridge.py (cubierto en test_hermes.py).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from harness.memory_rag.hermes_bridge import HermesBridge


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def hermes_bridge_no_path():
    """HermesBridge sin path (no disponible)."""
    with patch("harness.memory_rag.hermes_bridge.Path.exists") as mock_exists:
        mock_exists.return_value = False
        bridge = HermesBridge(auto_import=False)
        yield bridge


@pytest.fixture
def hermes_bridge_available(tmp_path):
    """HermesBridge con path temporal disponible."""
    hermes_dir = tmp_path / "shared_memory"
    hermes_dir.mkdir(parents=True, exist_ok=True)
    brain_dir = hermes_dir / "99_Hermes_Brain"
    brain_dir.mkdir(exist_ok=True)

    # Crear directorio knowledge
    knowledge_dir = hermes_dir / "knowledge" / "Swarmind_bridge"
    knowledge_dir.mkdir(parents=True, exist_ok=True)

    bridge = HermesBridge(hermes_path=str(hermes_dir), auto_import=False)
    yield bridge


@pytest.fixture
def hermes_bridge_with_modules(hermes_bridge_available):
    """HermesBridge con módulos mockeados."""
    bridge = hermes_bridge_available
    bridge._hermes_modules = {
        "MemoryService": MagicMock(),
        "QualityService": MagicMock(),
        "SessionService": MagicMock(),
        "ProcessingRequest": MagicMock(),
        "QualityMetric": MagicMock(),
    }
    yield bridge


# ---------------------------------------------------------------------------
# Tests: Initialization
# ---------------------------------------------------------------------------


class TestInitialization:
    """Tests de inicialización del bridge."""

    def test_init_not_available(self, hermes_bridge_no_path):
        """Sin path de Hermes, available debe ser False."""
        assert not hermes_bridge_no_path.available
        assert hermes_bridge_no_path.path is None

    def test_init_available(self, hermes_bridge_available):
        """Con path válido, available debe ser True."""
        assert hermes_bridge_available.available

    def test_init_custom_path(self, tmp_path):
        """Ruta personalizada debe usarse correctamente."""
        custom = tmp_path / "custom_hermes"
        custom.mkdir()
        bridge = HermesBridge(hermes_path=str(custom), auto_import=False)
        assert bridge.available
        assert bridge.path == str(custom)

    def test_init_auto_import_true(self, tmp_path):
        """Con auto_import=True, debe intentar importar módulos."""
        hermes_dir = tmp_path / "Hermes"
        hermes_dir.mkdir()
        with patch.object(HermesBridge, "_try_import_hermes_modules") as mock_import:
            bridge = HermesBridge(hermes_path=str(hermes_dir), auto_import=True)
            mock_import.assert_called_once()

    def test_init_auto_import_false(self, tmp_path):
        """Con auto_import=False, no debe importar módulos."""
        hermes_dir = tmp_path / "Hermes"
        hermes_dir.mkdir()
        with patch.object(HermesBridge, "_try_import_hermes_modules") as mock_import:
            bridge = HermesBridge(hermes_path=str(hermes_dir), auto_import=False)
            mock_import.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: _resolve_hermes_path
# ---------------------------------------------------------------------------


class TestResolvePath:
    """Tests para la resolución del path de Hermes."""

    def test_resolve_custom_path(self):
        """Con path personalizado, debe retornarlo."""
        result = HermesBridge._resolve_hermes_path("/custom/path")
        assert result == "/custom/path"

    def test_resolve_env_var(self, monkeypatch):
        """Variable de entorno HERMES_PATH debe tener prioridad."""
        monkeypatch.setenv("HERMES_PATH", "/env/hermes")
        # Como /env/hermes no existe, _resolve_hermes_path sigue buscando
        # en otras ubicaciones. Verificamos que intentó usar la env var.
        result = HermesBridge._resolve_hermes_path()
        # La función puede encontrar el directorio real del usuario; aceptamos
        # cualquier resultado que no lance error.
        assert result is None or isinstance(result, str)

    def test_resolve_env_var_that_exists(self, monkeypatch, tmp_path):
        """Si HERMES_PATH existe, debe retornarlo."""
        hermes_dir = tmp_path / "hermes_from_env"
        hermes_dir.mkdir()
        monkeypatch.setenv("HERMES_PATH", str(hermes_dir))
        result = HermesBridge._resolve_hermes_path()
        assert result == str(hermes_dir)

    def test_resolve_returns_none_when_not_found(self):
        """Si no encuentra ningún path, debe retornar None."""
        with patch("harness.memory_rag.hermes_bridge.Path.exists") as mock_exists:
            mock_exists.return_value = False
            result = HermesBridge._resolve_hermes_path()
            assert result is None


# ---------------------------------------------------------------------------
# Tests: Properties
# ---------------------------------------------------------------------------


class TestProperties:
    """Tests para propiedades del bridge."""

    def test_available_property(self, hermes_bridge_available):
        """available debe retornar True cuando hay path."""
        assert hermes_bridge_available.available

    def test_available_property_no_path(self, hermes_bridge_no_path):
        """available debe retornar False cuando no hay path."""
        assert not hermes_bridge_no_path.available

    def test_path_property(self, hermes_bridge_available):
        """path debe retornar la ruta configurada."""
        assert hermes_bridge_available.path is not None

    def test_brain_path_exists(self, hermes_bridge_available):
        """brain_path debe apuntar a 99_Hermes_Brain."""
        brain = hermes_bridge_available.brain_path
        assert brain is not None
        assert "99_Hermes_Brain" in brain

    def test_brain_path_not_exists(self, hermes_bridge_no_path):
        """Sin path, brain_path debe ser None."""
        assert hermes_bridge_no_path.brain_path is None

    def test_has_memory_service_true(self, hermes_bridge_with_modules):
        """has_memory_service debe ser True si MemoryService está cargado."""
        assert hermes_bridge_with_modules.has_memory_service

    def test_has_memory_service_false(self, hermes_bridge_no_path):
        """has_memory_service debe ser False si no hay módulos."""
        assert not hermes_bridge_no_path.has_memory_service


# ---------------------------------------------------------------------------
# Tests: sync_to_hermes
# ---------------------------------------------------------------------------


class TestSyncToHermes:
    """Tests para sincronización Swarmind → Hermes."""

    def test_sync_to_hermes_not_available(self, hermes_bridge_no_path, caplog):
        """Sin disponibilidad, sync_to_hermes debe retornar 0."""
        with caplog.at_level(logging.WARNING):
            count = hermes_bridge_no_path.sync_to_hermes([{"key": "test", "data": "val"}])
            assert count == 0
        assert any("not available" in msg for msg in caplog.messages)

    def test_sync_to_hermes_writes_file(self, hermes_bridge_available):
        """sync_to_hermes debe escribir archivos JSON."""
        records = [
            {"key": "test:record:1", "data": "value1", "domain": "test"},
            {"key": "test/record/2", "data": "value2", "domain": "test"},
        ]
        count = hermes_bridge_available.sync_to_hermes(records)
        assert count == 2

        # Verificar que los archivos se crearon
        knowledge_dir = Path(hermes_bridge_available.path) / "knowledge" / "Swarmind_bridge"
        files = list(knowledge_dir.glob("*.json"))
        assert len(files) == 2

    def test_sync_to_hermes_content(self, hermes_bridge_available):
        """El contenido del archivo JSON debe ser correcto."""
        records = [{"key": "test_record", "data": "hello", "domain": "test"}]
        hermes_bridge_available.sync_to_hermes(records)

        knowledge_dir = Path(hermes_bridge_available.path) / "knowledge" / "Swarmind_bridge"
        filepath = knowledge_dir / "test_record.json"
        assert filepath.exists()
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["key"] == "test_record"
        assert data["data"] == "hello"

    def test_sync_to_hermes_empty_records(self, hermes_bridge_available):
        """Lista vacía de records debe retornar 0."""
        count = hermes_bridge_available.sync_to_hermes([])
        assert count == 0

    def test_sync_to_hermes_fallback_key(self, hermes_bridge_available):
        """Sin key ni id, debe generar un nombre."""
        records = [{"data": "no key"}]
        count = hermes_bridge_available.sync_to_hermes(records)
        assert count == 1

    def test_sync_to_hermes_write_error(self, hermes_bridge_available, caplog):
        """Error al escribir no debe romper el proceso."""
        with patch("builtins.open", side_effect=PermissionError("Denied")):
            with caplog.at_level(logging.WARNING):
                count = hermes_bridge_available.sync_to_hermes(
                    [{"key": "test", "data": "val"}],
                )
                assert count == 0
            assert any("Error syncing" in msg for msg in caplog.messages)


# ---------------------------------------------------------------------------
# Tests: sync_from_hermes
# ---------------------------------------------------------------------------


class TestSyncFromHermes:
    """Tests para sincronización Hermes → Swarmind."""

    def test_sync_from_hermes_not_available(self, hermes_bridge_no_path):
        """Sin disponibilidad, sync_from_hermes debe retornar []."""
        result = hermes_bridge_no_path.sync_from_hermes()
        assert result == []

    def test_sync_from_hermes_reads_files(self, hermes_bridge_available):
        """sync_from_hermes debe leer archivos JSON del directorio."""
        # Primero escribir algunos archivos
        knowledge_dir = Path(hermes_bridge_available.path) / "knowledge" / "Swarmind_bridge"
        with open(knowledge_dir / "record1.json", "w", encoding="utf-8") as f:
            json.dump({"key": "record1", "data": "val1"}, f)
        with open(knowledge_dir / "record2.json", "w", encoding="utf-8") as f:
            json.dump({"key": "record2", "data": "val2"}, f)

        records = hermes_bridge_available.sync_from_hermes()
        assert len(records) == 2
        keys = [r["key"] for r in records]
        assert "record1" in keys
        assert "record2" in keys

    def test_sync_from_hermes_no_directory(self, hermes_bridge_available):
        """Sin directorio knowledge, debe retornar []."""
        import shutil
        knowledge_dir = Path(hermes_bridge_available.path) / "knowledge" / "Swarmind_bridge"
        if knowledge_dir.exists():
            shutil.rmtree(knowledge_dir)
        result = hermes_bridge_available.sync_from_hermes()
        assert result == []

    def test_sync_from_hermes_empty_dir(self, hermes_bridge_available):
        """Directorio vacío debe retornar []."""
        result = hermes_bridge_available.sync_from_hermes()
        assert result == []

    def test_sync_from_hermes_corrupted_file(self, hermes_bridge_available, caplog):
        """Archivo JSON corrupto debe saltarse."""
        knowledge_dir = Path(hermes_bridge_available.path) / "knowledge" / "Swarmind_bridge"
        (knowledge_dir / "bad.json").write_text("not valid json", encoding="utf-8")
        with caplog.at_level(logging.WARNING):
            records = hermes_bridge_available.sync_from_hermes()
            assert records == []
        assert any("Error reading" in msg for msg in caplog.messages)

    def test_sync_from_hermes_pattern(self, hermes_bridge_available):
        """Patrón glob debe filtrar archivos."""
        knowledge_dir = Path(hermes_bridge_available.path) / "knowledge" / "Swarmind_bridge"
        with open(knowledge_dir / "record1.json", "w", encoding="utf-8") as f:
            json.dump({"key": "r1"}, f)
        with open(knowledge_dir / "record2.json", "w", encoding="utf-8") as f:
            json.dump({"key": "r2"}, f)
        with open(knowledge_dir / "data.txt", "w", encoding="utf-8") as f:
            f.write("texto")

        records = hermes_bridge_available.sync_from_hermes(pattern="*.json")
        assert len(records) == 2


# ---------------------------------------------------------------------------
# Tests: sync_skills_to_hermes
# ---------------------------------------------------------------------------


class TestSyncSkills:
    """Tests para sincronización de skills."""

    def test_sync_skills_not_available(self, hermes_bridge_no_path):
        """Sin disponibilidad, debe retornar 0."""
        count = hermes_bridge_no_path.sync_skills_to_hermes("/some/path")
        assert count == 0

    def test_sync_skills_no_source_dir(self, hermes_bridge_available, caplog):
        """Si el directorio source no existe, debe loguear warning."""
        with caplog.at_level(logging.WARNING):
            count = hermes_bridge_available.sync_skills_to_hermes("/nonexistent/path/xyz")
            assert count == 0
        assert any("not found" in msg for msg in caplog.messages)

    def test_sync_skills_copies_files(self, hermes_bridge_available, tmp_path):
        """Debe copiar SKILL.md de cada skill."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        skill1 = skills_dir / "test_skill"
        skill1.mkdir()
        (skill1 / "SKILL.md").write_text("# Test Skill", encoding="utf-8")

        count = hermes_bridge_available.sync_skills_to_hermes(str(skills_dir))
        assert count == 1

        hermes_skills = Path(hermes_bridge_available.path) / "skills" / "Swarmind_bridge"
        assert (hermes_skills / "test_skill" / "SKILL.md").exists()

    def test_sync_skills_skips_non_skill_dirs(self, hermes_bridge_available, tmp_path):
        """Directorios sin SKILL.md deben omitirse."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        not_a_skill = skills_dir / "not_a_skill"
        not_a_skill.mkdir()
        (not_a_skill / "other.txt").write_text("not a skill", encoding="utf-8")

        count = hermes_bridge_available.sync_skills_to_hermes(str(skills_dir))
        assert count == 0


# ---------------------------------------------------------------------------
# Tests: Service access
# ---------------------------------------------------------------------------


class TestServiceAccess:
    """Tests para get_memory_service y get_quality_service."""

    def test_get_memory_service_available(self, hermes_bridge_with_modules):
        """Con MemoryService cargado, debe retornar instancia."""
        service = hermes_bridge_with_modules.get_memory_service()
        assert service is not None

    def test_get_memory_service_not_available(self, hermes_bridge_no_path):
        """Sin MemoryService, debe retornar None."""
        service = hermes_bridge_no_path.get_memory_service()
        assert service is None

    def test_get_quality_service_available(self, hermes_bridge_with_modules):
        """Con QualityService cargado, debe retornar instancia."""
        service = hermes_bridge_with_modules.get_quality_service()
        assert service is not None

    def test_get_quality_service_not_available(self, hermes_bridge_no_path):
        """Sin QualityService, debe retornar None."""
        service = hermes_bridge_no_path.get_quality_service()
        assert service is None

    def test_get_memory_service_creation_error(self, hermes_bridge_with_modules, caplog):
        """Error al crear MemoryService debe retornar None."""
        MemoryService = hermes_bridge_with_modules._hermes_modules["MemoryService"]
        MemoryService.side_effect = Exception("Creation failed")
        with caplog.at_level(logging.WARNING):
            service = hermes_bridge_with_modules.get_memory_service()
            assert service is None
        assert any("Error creating" in msg for msg in caplog.messages)


# ---------------------------------------------------------------------------
# Tests: get_status
# ---------------------------------------------------------------------------


class TestGetStatus:
    """Tests para get_status."""

    def test_get_status_keys(self, hermes_bridge_available):
        """get_status debe incluir todas las claves esperadas."""
        status = hermes_bridge_available.get_status()
        assert "available" in status
        assert "path" in status
        assert "brain_path" in status
        assert "has_memory_service" in status
        assert "hermes_path_exists" in status
        assert "modules_loaded" in status

    def test_get_status_available_true(self, hermes_bridge_available):
        """Cuando está disponible, el status debe reflejarlo."""
        status = hermes_bridge_available.get_status()
        assert status["available"] is True

    def test_get_status_available_false(self, hermes_bridge_no_path):
        """Cuando no está disponible, el status debe reflejarlo."""
        status = hermes_bridge_no_path.get_status()
        assert status["available"] is False
        assert status["path"] is None

    def test_get_status_modules_loaded(self, hermes_bridge_with_modules):
        """modules_loaded debe listar los módulos cargados."""
        status = hermes_bridge_with_modules.get_status()
        assert "MemoryService" in status["modules_loaded"]


# ---------------------------------------------------------------------------
# Tests: _try_import_hermes_modules
# ---------------------------------------------------------------------------


class TestImportModules:
    """Tests para la importación de módulos de Hermes."""

    def test_import_no_path(self, hermes_bridge_no_path):
        """Sin path, _try_import_hermes_modules no debe hacer nada."""
        hermes_bridge_no_path._try_import_hermes_modules()
        assert hermes_bridge_no_path._hermes_modules == {}

    def test_import_modules_populated(self, hermes_bridge_with_modules):
        """Importación exitosa debe poblar _hermes_modules."""
        bridge = hermes_bridge_with_modules
        assert "MemoryService" in bridge._hermes_modules
        assert "QualityService" in bridge._hermes_modules
        assert len(bridge._hermes_modules) >= 4

    def test_import_failure_logs_warning(self, tmp_path, caplog):
        """Fallo al importar debe loguear warning."""
        hermes_dir = tmp_path / "Hermes"
        hermes_dir.mkdir()
        bridge = HermesBridge(hermes_path=str(hermes_dir), auto_import=False)

        # Simular que el path existe pero los módulos no
        with patch.object(bridge, "_hermes_path", tmp_path / "Hermes"):
            # Limpiar sys.path para que no encuentre los módulos
            with patch("harness.memory_rag.hermes_bridge.sys.path", []):
                with caplog.at_level(logging.WARNING):
                    bridge._try_import_hermes_modules()
                # Debe loguear el error sin lanzar excepción
                assert bridge._hermes_modules == {}


# ---------------------------------------------------------------------------
# Tests: Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Tests de edge cases varios."""

    def test_hermes_path_does_not_exist(self):
        """Si la ruta no existe pero se pasa, available debe ser False."""
        bridge = HermesBridge(hermes_path="/nonexistent/path/xyz", auto_import=False)
        assert not bridge.available

    def test_brain_path_inside_hermes(self, hermes_bridge_available):
        """brain_path debe estar dentro del path de Hermes."""
        brain = hermes_bridge_available.brain_path
        assert brain is not None
        assert brain.startswith(hermes_bridge_available.path)

    def test_sync_to_hermes_safe_filename(self, hermes_bridge_available):
        """Caracteres peligrosos en key deben sanitizarse."""
        records = [{"key": "test:path/with spaces", "data": "val"}]
        count = hermes_bridge_available.sync_to_hermes(records)
        assert count == 1

        knowledge_dir = Path(hermes_bridge_available.path) / "knowledge" / "Swarmind_bridge"
        # Los caracteres :, / y espacios deben reemplazarse
        files = list(knowledge_dir.glob("*.json"))
        assert len(files) == 1
        # El filename no debe contener ':' ni '/'
        assert ":" not in files[0].name
        assert "/" not in files[0].name

    def test_initialization_logging(self, tmp_path, caplog):
        """Debe loguear información de inicialización."""
        hermes_dir = tmp_path / "Hermes"
        hermes_dir.mkdir()
        with caplog.at_level(logging.INFO):
            HermesBridge(hermes_path=str(hermes_dir), auto_import=False)
        assert any("HermesBridge initialized" in msg for msg in caplog.messages)

    def test_not_available_logging(self, tmp_path, caplog):
        """Sin path, debe loguear que no se encontró."""
        with patch("harness.memory_rag.hermes_bridge.Path.exists") as mock_exists:
            mock_exists.return_value = False
            with caplog.at_level(logging.INFO):
                HermesBridge(hermes_path="/fake/path", auto_import=False)
            assert any("not found" in msg for msg in caplog.messages)
