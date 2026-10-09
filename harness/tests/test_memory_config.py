"""
Tests para Memory Config — MemoryConfig, get_memory_config, set_memory_config.

Cubre:
  - Configuraciones por defecto (backend, rutas, dimensiones)
  - Configuraciones personalizadas (backend, rutas, flags)
  - Validacion de parametros (enums, tipos)
  - Serializacion (to_dict, from_dict)
  - Carga desde entorno (from_env)
  - Funciones globales (get/set/reset_memory_config)
  - Edge cases
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from harness.memory_rag.memory_config import (
    MemoryBackend,
    MemoryConfig,
    TelemetryLevel,
    get_memory_config,
    reset_memory_config,
    set_memory_config,
)

# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture(autouse=True)
def _reset_global_config():
    """Resetea la config global antes de cada test."""
    reset_memory_config()
    yield
    reset_memory_config()


# ===========================================================================
# Tests: Configuracion por defecto
# ===========================================================================


class TestMemoryConfigDefault:
    """Verifica los valores por defecto de MemoryConfig."""

    def test_backend_default_lancedb(self):
        """El backend por defecto es lancedb."""
        config = MemoryConfig()
        assert config.backend == MemoryBackend.LANCEDB

    def test_lancedb_path_default_se_resuelve(self):
        """lancedb_path se resuelve automaticamente si no se especifica."""
        config = MemoryConfig()
        assert config.lancedb_path != ""
        assert "db" in config.lancedb_path and "lancedb" in config.lancedb_path

    def test_embedding_dim_default(self):
        """embedding_dim por defecto es 384."""
        config = MemoryConfig()
        assert config.embedding_dim == 384

    def test_telemetry_level_default_basic(self):
        """telemetry_level por defecto es BASIC."""
        config = MemoryConfig()
        assert config.telemetry_level == TelemetryLevel.BASIC

    def test_allow_fallback_default_false(self):
        """allow_fallback por defecto es False."""
        config = MemoryConfig()
        assert config.allow_fallback is False

    def test_auto_create_collections_default_true(self):
        """auto_create_collections por defecto es True."""
        config = MemoryConfig()
        assert config.auto_create_collections is True

    def test_kpi_collections_default_contiene_agent_performance(self):
        """kpi_collections por defecto incluye agent_performance."""
        config = MemoryConfig()
        assert "agent_performance" in config.kpi_collections
        assert "skill_effectiveness" in config.kpi_collections


# ===========================================================================
# Tests: Configuracion personalizada
# ===========================================================================


class TestMemoryConfigCustom:
    """Verifica valores personalizados en MemoryConfig."""

    def test_backend_memory(self):
        """Se puede configurar backend='memory'."""
        config = MemoryConfig(backend=MemoryBackend.MEMORY)
        assert config.backend == MemoryBackend.MEMORY

    def test_lancedb_path_personalizado(self):
        """Se puede especificar lancedb_path personalizado."""
        config = MemoryConfig(lancedb_path="/tmp/test_lancedb")
        assert config.lancedb_path == "/tmp/test_lancedb"

    def test_embedding_dim_personalizado(self):
        """Se puede especificar embedding_dim personalizado."""
        config = MemoryConfig(embedding_dim=768)
        assert config.embedding_dim == 768

    def test_telemetry_level_off(self):
        """Se puede desactivar telemetria."""
        config = MemoryConfig(telemetry_level=TelemetryLevel.OFF)
        assert config.telemetry_level == TelemetryLevel.OFF

    def test_telemetry_level_full(self):
        """Se puede activar telemetria completa."""
        config = MemoryConfig(telemetry_level=TelemetryLevel.FULL)
        assert config.telemetry_level == TelemetryLevel.FULL

    def test_allow_fallback_true(self):
        """Se puede activar fallback."""
        config = MemoryConfig(allow_fallback=True)
        assert config.allow_fallback is True

    def test_kpi_collections_personalizado(self):
        """Se pueden especificar colecciones KPI personalizadas."""
        config = MemoryConfig(kpi_collections={"custom_kpi"})
        assert config.kpi_collections == {"custom_kpi"}


# ===========================================================================
# Tests: to_dict / from_dict
# ===========================================================================


class TestMemoryConfigSerialization:
    """Verifica serializacion y deserializacion."""

    def test_to_dict_incluye_campos_clave(self):
        """to_dict retorna dict con campos esenciales."""
        config = MemoryConfig()
        d = config.to_dict()
        assert d["backend"] == "lancedb"
        assert d["embedding_dim"] == 384
        assert d["telemetry_level"] == "basic"
        assert "lancedb_path" in d
        assert "kpi_collections" in d
        assert isinstance(d["kpi_collections"], list)

    def test_from_dict_restaura_config(self):
        """from_dict restaura un MemoryConfig desde un dict."""
        original = MemoryConfig(
            backend=MemoryBackend.MEMORY,
            embedding_dim=768,
            telemetry_level=TelemetryLevel.FULL,
            kpi_collections={"kpi1", "kpi2"},
        )
        d = original.to_dict()
        restored = MemoryConfig.from_dict(d)
        assert restored.backend == MemoryBackend.MEMORY
        assert restored.embedding_dim == 768
        assert restored.telemetry_level == TelemetryLevel.FULL
        assert restored.kpi_collections == {"kpi1", "kpi2"}

    def test_from_dict_maneja_strings(self):
        """from_dict acepta strings para backend y telemetry_level."""
        d: dict[str, Any] = {
            "backend": "memory",
            "telemetry_level": "full",
            "kpi_collections": ["kpi_a"],
        }
        config = MemoryConfig.from_dict(d)
        assert config.backend == MemoryBackend.MEMORY
        assert config.telemetry_level == TelemetryLevel.FULL
        assert config.kpi_collections == {"kpi_a"}

    def test_from_dict_con_dict_vacio(self):
        """from_dict con dict vacio retorna config por defecto."""
        config = MemoryConfig.from_dict({})
        assert config.backend == MemoryBackend.LANCEDB
        assert config.embedding_dim == 384


# ===========================================================================
# Tests: from_env
# ===========================================================================


class TestMemoryConfigFromEnv:
    """Verifica carga de configuracion desde variables de entorno."""

    @patch.dict(os.environ, {
        "MEMORY_BACKEND": "memory",
        "EMBEDDING_DIM": "512",
        "TELEMETRY_LEVEL": "off",
        "MEMORY_FALLBACK": "true",
    })
    def test_from_env_carga_vars(self):
        """from_env carga configuracion desde environment."""
        config = MemoryConfig.from_env()
        assert config.backend == MemoryBackend.MEMORY
        assert config.embedding_dim == 512
        assert config.telemetry_level == TelemetryLevel.OFF
        assert config.allow_fallback is True

    @patch.dict(os.environ, {
        "LANCEDB_PATH": "/custom/lancedb",
    })
    def test_from_env_rutas_personalizadas(self):
        """from_env carga rutas desde environment."""
        config = MemoryConfig.from_env()
        assert config.lancedb_path == "/custom/lancedb"

    @patch.dict(os.environ, {}, clear=True)
    @patch("harness.memory_rag.memory_config.Path.home")
    def test_from_env_sin_vars_usa_defaults(self, mock_home):
        """from_env sin variables de entorno usa valores por defecto.
        Se mockea Path.home porque el environment sin HOME puede fallar.
        MEMORY_BACKEND default es 'lancedb' directamente."""
        mock_home.return_value = Path("/tmp/fake_home")
        # from_env usa os.environ.get("MEMORY_BACKEND", "lancedb") → default
        config = MemoryConfig.from_env()
        assert config.backend == MemoryBackend.LANCEDB
        assert config.embedding_dim == 384
        assert config.telemetry_level == TelemetryLevel.BASIC
        assert config.allow_fallback is False


# ===========================================================================
# Tests: Funciones globales
# ===========================================================================


class TestGlobalConfigFunctions:
    """Verifica get/set/reset_memory_config."""

    def test_get_memory_config_retorna_instancia(self):
        """get_memory_config retorna una instancia de MemoryConfig."""
        config = get_memory_config()
        assert isinstance(config, MemoryConfig)

    def test_get_memory_config_cachea(self):
        """get_memory_config cachea el resultado (misma instancia)."""
        config1 = get_memory_config()
        config2 = get_memory_config()
        assert config1 is config2

    def test_set_memory_config(self):
        """set_memory_config establece la config global."""
        custom = MemoryConfig(backend=MemoryBackend.MEMORY)
        set_memory_config(custom)
        assert get_memory_config() is custom

    def test_reset_memory_config(self):
        """reset_memory_config reinicia la config global."""
        custom = MemoryConfig(backend=MemoryBackend.MEMORY)
        set_memory_config(custom)
        reset_memory_config()
        config = get_memory_config()
        assert config.backend == MemoryBackend.LANCEDB  # Default


# ===========================================================================
# Tests: Edge cases
# ===========================================================================


class TestMemoryConfigEdgeCases:
    """Verifica casos limite de MemoryConfig."""

    def test_lancedb_path_vacio_se_resuelve(self):
        """lancedb_path vacio se resuelve automaticamente."""
        config = MemoryConfig(lancedb_path="")
        assert config.lancedb_path != ""

    def test_embedding_dim_cero(self):
        """embedding_dim puede ser 0 aunque no tenga sentido practico."""
        config = MemoryConfig(embedding_dim=0)
        assert config.embedding_dim == 0

    def test_embedding_dim_grande(self):
        """embedding_dim puede ser un valor grande."""
        config = MemoryConfig(embedding_dim=4096)
        assert config.embedding_dim == 4096

    def test_kpi_collections_vacio(self):
        """kpi_collections puede ser un set vacio."""
        config = MemoryConfig(kpi_collections=set())
        assert config.kpi_collections == set()

    def test_kpi_collections_muchos(self):
        """kpi_collections puede tener multiples elementos."""
        kpis = {f"kpi_{i}" for i in range(100)}
        config = MemoryConfig(kpi_collections=kpis)
        assert config.kpi_collections == kpis

    def test_memory_backend_enum_values(self):
        """MemoryBackend enum tiene los valores esperados."""
        assert MemoryBackend.LANCEDB.value == "lancedb"
        assert MemoryBackend.MEMORY.value == "memory"

    def test_telemetry_level_enum_values(self):
        """TelemetryLevel enum tiene los valores esperados."""
        assert TelemetryLevel.OFF.value == "off"
        assert TelemetryLevel.BASIC.value == "basic"
        assert TelemetryLevel.FULL.value == "full"

    def test_to_dict_convierte_kpi_set_a_list(self):
        """to_dict convierte kpi_collections de set a list para JSON."""
        config = MemoryConfig(kpi_collections={"a", "b"})
        d = config.to_dict()
        assert isinstance(d["kpi_collections"], list)
        assert set(d["kpi_collections"]) == {"a", "b"}


# ===========================================================================
# Tests: Memoria central (Memory_Proyects / .swarmind_config.json)
# ===========================================================================


class TestMemoryRootResolution:
    """El default de lancedb_path resuelve a la memoria central cuando
    existe .swarmind_config.json (SSOT de backup_memory.py)."""

    def _write_swarmind_config(self, root: Path) -> None:
        """Crea .swarmind_config.json + data/lancedb en el root temporal."""
        import json
        (root / "data" / "lancedb").mkdir(parents=True, exist_ok=True)
        (root / ".swarmind_config.json").write_text(
            json.dumps({"memory_root": str(root)}),
            encoding="utf-8",
        )

    @patch.dict(os.environ, {"MEMORY_ROOT": ""}, clear=True)
    def test_default_apunta_memory_root_cuando_existe_config(self, tmp_path: Path):
        """Con MEMORY_ROOT + .swarmind_config.json, el default usa <root>/data/lancedb."""
        self._write_swarmind_config(tmp_path)
        with patch.dict(os.environ, {"MEMORY_ROOT": str(tmp_path)}):
            config = MemoryConfig()
        expected = str(tmp_path / "data" / "lancedb")
        assert config.lancedb_path == expected

    @patch.dict(os.environ, {"MEMORY_ROOT": ""}, clear=True)
    def test_default_legacy_sin_memory_root(self, tmp_path: Path):
        """Sin config -> legacy harness/db/lancedb (no usa Memory_Proyects)."""
        config = MemoryConfig()
        assert "db" in config.lancedb_path and "lancedb" in config.lancedb_path
        assert "Memory_Proyects" not in config.lancedb_path

    @patch.dict(os.environ, {"MEMORY_ROOT": ""}, clear=True)
    def test_env_lancedb_path_prioridad_sobre_memory_root(self, tmp_path: Path):
        """LANCEDB_PATH env tiene prioridad sobre .swarmind_config.json."""
        self._write_swarmind_config(tmp_path)
        with patch.dict(os.environ, {"MEMORY_ROOT": str(tmp_path), "LANCEDB_PATH": "/custom/lancedb"}):
            config = MemoryConfig.from_env()
        assert config.lancedb_path == "/custom/lancedb"

    @patch.dict(os.environ, {"MEMORY_ROOT": ""}, clear=True)
    def test_memory_root_sin_data_lancedb_usa_legacy(self, tmp_path: Path):
        """MEMORY_ROOT valido pero sin data/lancedb -> legacy (no rompe)."""
        import json
        (tmp_path / ".swarmind_config.json").write_text(
            json.dumps({"memory_root": str(tmp_path)}),
            encoding="utf-8",
        )
        with patch.dict(os.environ, {"MEMORY_ROOT": str(tmp_path)}):
            config = MemoryConfig()
        assert "db" in config.lancedb_path and "lancedb" in config.lancedb_path

    @patch.dict(os.environ, {}, clear=True)
    @patch("harness.memory_rag.memory_config._safe_home")
    def test_resiliente_sin_home_no_crashea(self, mock_home, tmp_path: Path):
        """Sin HOME y sin env vars, MemoryConfig no crashea (resiliencia CI).

        WHY: entornos headless/CI sin HOME/USERPROFILE; el harness degrada
        a la ruta legacy relativa sin lanzar RuntimeError.
        WHERE: memory_config.__post_init__
        """
        mock_home.return_value = None
        config = MemoryConfig()
        assert config.lancedb_path != ""
        assert "lancedb" in config.lancedb_path
