"""
Tests para Memory Config — MemoryConfig, get_memory_config, set_memory_config.

Cubre:
  - Configuraciones por defecto (backend, rutas, dimensiones)
  - Configuraciones personalizadas (backend, rutas, flags)
  - Validacion de parametros (enums, tipos)
  - Propiedades derivadas (hermes_brain_path, is_hermes_available)
  - Serializacion (to_dict, from_dict)
  - Carga desde entorno (from_env)
  - Funciones globales (get/set/reset_memory_config)
  - Edge cases
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict
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

    def test_enable_hermes_bridge_default_false(self):
        """enable_hermes_bridge por defecto es False."""
        config = MemoryConfig()
        assert config.enable_hermes_bridge is False

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

    def test_backend_hermes(self):
        """Se puede configurar backend='hermes'."""
        config = MemoryConfig(backend=MemoryBackend.HERMES)
        assert config.backend == MemoryBackend.HERMES

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

    def test_enable_hermes_bridge_true(self):
        """Se puede activar Hermes bridge."""
        config = MemoryConfig(enable_hermes_bridge=True)
        assert config.enable_hermes_bridge is True

    def test_kpi_collections_personalizado(self):
        """Se pueden especificar colecciones KPI personalizadas."""
        config = MemoryConfig(kpi_collections={"custom_kpi"})
        assert config.kpi_collections == {"custom_kpi"}


# ===========================================================================
# Tests: Propiedades derivadas
# ===========================================================================


class TestMemoryConfigProperties:
    """Verifica propiedades derivadas de MemoryConfig."""

    def test_hermes_brain_path_con_hermes_path(self):
        """hermes_brain_path se construye desde hermes_path."""
        config = MemoryConfig(
            hermes_path="/base/hermes",
        )
        expected = str(Path("/base/hermes") / "99_Hermes_Brain" / "lancedb_data")
        assert config.hermes_brain_path == expected

    def test_hermes_brain_path_vacio_sin_hermes_path(self):
        """hermes_brain_path es '' si no hay hermes_path.
        Se usa object.__setattr__ para forzar hermes_path vacio porque
        __post_init__ puede resolverlo automaticamente."""
        config = MemoryConfig()
        object.__setattr__(config, "hermes_path", "")
        assert config.hermes_brain_path == ""

    def test_hermes_brain_path_con_path_no_existente(self):
        """hermes_brain_path se construye aunque el path no exista."""
        config = MemoryConfig(hermes_path="/base/hermes")
        expected = str(Path("/base/hermes") / "99_Hermes_Brain" / "lancedb_data")
        assert config.hermes_brain_path == expected

    def test_hermes_config_path_con_hermes_path(self):
        """hermes_config_path se construye desde hermes_path."""
        config = MemoryConfig(hermes_path="/base/hermes")
        expected = str(Path("/base/hermes") / "99_Hermes_Brain" / "configs")
        assert config.hermes_config_path == expected

    def test_is_hermes_available_false_sin_path(self):
        """is_hermes_available es False si no hay hermes_path."""
        config = MemoryConfig(hermes_path="", enable_hermes_bridge=True)
        # El __post_init__ puede resolver hermes_path si el path default existe.
        # Forzamos un path vacio real seteando despues de init.
        object.__setattr__(config, "hermes_path", "")
        assert config.is_hermes_available is False

    def test_is_hermes_available_false_sin_bridge(self):
        """is_hermes_available es False si enable_hermes_bridge es False."""
        config = MemoryConfig(hermes_path="/tmp", enable_hermes_bridge=False)
        assert config.is_hermes_available is False

    def test_is_hermes_available_con_path_inexistente(self):
        """is_hermes_available es False si el path no existe."""
        config = MemoryConfig(
            hermes_path="/ruta/inexistente/hermes",
            enable_hermes_bridge=True,
        )
        assert config.is_hermes_available is False

    def test_is_hermes_available_true(self, tmp_path: Path):
        """is_hermes_available es True si el path existe y bridge activo."""
        hermes_dir = tmp_path / "shared_memory"
        hermes_dir.mkdir(parents=True)
        config = MemoryConfig(
            hermes_path=str(hermes_dir),
            enable_hermes_bridge=True,
        )
        assert config.is_hermes_available is True


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
        assert "is_hermes_available" in d
        assert "lancedb_path" in d
        assert "kpi_collections" in d
        assert isinstance(d["kpi_collections"], list)

    def test_from_dict_restaura_config(self):
        """from_dict restaura un MemoryConfig desde un dict.
        Nota: is_hermes_available es propiedad computada, no parametro de init.
        """
        original = MemoryConfig(
            backend=MemoryBackend.MEMORY,
            embedding_dim=768,
            telemetry_level=TelemetryLevel.FULL,
            kpi_collections={"kpi1", "kpi2"},
        )
        d = original.to_dict()
        # Eliminar campos que no son parametros de __init__
        d.pop("is_hermes_available", None)
        restored = MemoryConfig.from_dict(d)
        assert restored.backend == MemoryBackend.MEMORY
        assert restored.embedding_dim == 768
        assert restored.telemetry_level == TelemetryLevel.FULL
        assert restored.kpi_collections == {"kpi1", "kpi2"}

    def test_from_dict_maneja_strings(self):
        """from_dict acepta strings para backend y telemetry_level."""
        d: Dict[str, Any] = {
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
        "HERMES_BRIDGE": "true",
    })
    def test_from_env_carga_vars(self):
        """from_env carga configuracion desde environment."""
        config = MemoryConfig.from_env()
        assert config.backend == MemoryBackend.MEMORY
        assert config.embedding_dim == 512
        assert config.telemetry_level == TelemetryLevel.OFF
        assert config.allow_fallback is True
        assert config.enable_hermes_bridge is True

    @patch.dict(os.environ, {
        "LANCEDB_PATH": "/custom/lancedb",
        "HERMES_PATH": "/custom/hermes",
    })
    def test_from_env_rutas_personalizadas(self):
        """from_env carga rutas desde environment."""
        config = MemoryConfig.from_env()
        assert config.lancedb_path == "/custom/lancedb"
        assert config.hermes_path == "/custom/hermes"

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
        assert MemoryBackend.HERMES.value == "hermes"

    def test_telemetry_level_enum_values(self):
        """TelemetryLevel enum tiene los valores esperados."""
        assert TelemetryLevel.OFF.value == "off"
        assert TelemetryLevel.BASIC.value == "basic"
        assert TelemetryLevel.FULL.value == "full"

    def test_hermes_path_con_env_var(self):
        """HERMES_PATH env var se usa si no se especifica hermes_path."""
        with patch.dict(os.environ, {"HERMES_PATH": "/from/env/hermes"}, clear=True):
            config = MemoryConfig(hermes_path="")
            # Si el path existe, se usa; si no, se ignora
            assert config.hermes_path == ""  # No existe /from/env/hermes

    def test_to_dict_convierte_kpi_set_a_list(self):
        """to_dict convierte kpi_collections de set a list para JSON."""
        config = MemoryConfig(kpi_collections={"a", "b"})
        d = config.to_dict()
        assert isinstance(d["kpi_collections"], list)
        assert set(d["kpi_collections"]) == {"a", "b"}
