"""Tests para la integracion ADR-0040 H6: TokenBudgetManager + token_budgets.yaml.

Cubre:
  - load_yaml: carga valida, archivo inexistente, YAML mal formado, no-mapping.
  - get_agent_budget: rol declarado, rol desconocido, fallback sin YAML.
  - get_role_budget: distinguir rol declarado de desconocido.
  - get_session_budget, get_compression_level, get_threshold, has_budget_config.
  - Integracion: BudgetManager.register_agent aplica budget por rol.
  - Backward compatibility: constantes historicas exportadas con el mismo nombre.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from harness.memory_rag import token_budget as tb
from harness.memory_rag.token_budget import (
    DEFAULT_AGENT_BUDGET,
    DEFAULT_SESSION_BUDGET,
    BudgetManager,
)
from harness.memory_rag.token_budget_manager import (
    DEFAULT_COMPRESSION_LEVEL,
    DEFAULT_COMPRESSION_THRESHOLD,
    TokenBudgetManager,
    load_yaml,
)

SAMPLE_YAML = """\
defaults:
  base_budget: 2048
  response_buffer: 256
  compression_threshold: 0.85
role_budgets:
  guardian:
    budget: 2048
    compression_level: high
  scientist:
    budget: 4096
    compression_level: low
session_budget: 24000
"""


@pytest.fixture
def budgets_yaml(tmp_path: Path) -> Path:
    """Crea un SSOT de budgets temporal."""
    path = tmp_path / "token_budgets.yaml"
    path.write_text(SAMPLE_YAML, encoding="utf-8")
    return path


def make_manager(yaml_path: Path | None) -> TokenBudgetManager:
    """Crea un manager con la config del SSOT indicado (sin sesiones)."""
    return TokenBudgetManager(default_budget=4000, max_sessions=100, yaml_path=yaml_path)


# ===========================================================================
# load_yaml
# ===========================================================================


class TestLoadYaml:
    """Tests para la funcion load_yaml."""

    def test_carga_yaml_valido(self, budgets_yaml: Path) -> None:
        """Un YAML valido se carga como dict."""
        data = load_yaml(budgets_yaml)
        assert data["defaults"]["base_budget"] == 2048
        assert data["role_budgets"]["guardian"]["budget"] == 2048

    def test_archivo_inexistente_raises(self, tmp_path: Path) -> None:
        """Archivo inexistente levanta FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_yaml(tmp_path / "no_existe.yaml")

    def test_yaml_malformado_raises_valueerror(self, tmp_path: Path) -> None:
        """YAML mal formado levanta ValueError (no falla silencioso)."""
        path = tmp_path / "broken.yaml"
        path.write_text("defaults: [unclosed", encoding="utf-8")
        with pytest.raises(ValueError):
            load_yaml(path)

    def test_no_mapping_raises_typeerror(self, tmp_path: Path) -> None:
        """Contenido que no es un mapping levanta TypeError."""
        path = tmp_path / "list.yaml"
        path.write_text("- a\n- b\n", encoding="utf-8")
        with pytest.raises(TypeError):
            load_yaml(path)


# ===========================================================================
# API: budgets por rol (SSOT)
# ===========================================================================


class TestAgentBudget:
    """Tests de get_agent_budget / get_role_budget."""

    def test_rol_declarado(self, budgets_yaml: Path) -> None:
        """Rol declarado en role_budgets usa su budget."""
        manager = make_manager(budgets_yaml)
        assert manager.get_agent_budget("guardian") == 2048
        assert manager.get_agent_budget("scientist") == 4096

    def test_rol_desconocido_usa_base_budget(self, budgets_yaml: Path) -> None:
        """Rol desconocido usa defaults.base_budget del SSOT."""
        manager = make_manager(budgets_yaml)
        assert manager.get_agent_budget("unknown") == 2048

    def test_sin_yaml_usa_constante_historica(self, tmp_path: Path) -> None:
        """Sin YAML, get_agent_budget cae a DEFAULT_AGENT_BUDGET (4000)."""
        manager = make_manager(tmp_path / "missing.yaml")
        assert manager.get_agent_budget("guardian") == DEFAULT_AGENT_BUDGET
        assert manager.get_agent_budget("unknown") == DEFAULT_AGENT_BUDGET

    def test_role_budget_declarado(self, budgets_yaml: Path) -> None:
        """get_role_budget retorna el budget del rol declarado."""
        manager = make_manager(budgets_yaml)
        assert manager.get_role_budget("guardian") == 2048

    def test_role_budget_desconocido_es_none(self, budgets_yaml: Path) -> None:
        """get_role_budget retorna None para roles no declarados."""
        manager = make_manager(budgets_yaml)
        assert manager.get_role_budget("unknown") is None


# ===========================================================================
# API: sesion, compresion y umbral
# ===========================================================================


class TestSessionAndCompression:
    """Tests de get_session_budget / get_compression_level / get_threshold."""

    def test_session_budget_declarado(self, budgets_yaml: Path) -> None:
        """session_budget del YAML se respeta."""
        manager = make_manager(budgets_yaml)
        assert manager.get_session_budget() == 24000

    def test_session_budget_sin_yaml_usa_default(self, tmp_path: Path) -> None:
        """Sin YAML, get_session_budget cae a DEFAULT_SESSION_BUDGET (16000)."""
        manager = make_manager(tmp_path / "missing.yaml")
        assert manager.get_session_budget() == DEFAULT_SESSION_BUDGET

    def test_compression_level_declarado(self, budgets_yaml: Path) -> None:
        """compression_level del rol declarado se respeta."""
        manager = make_manager(budgets_yaml)
        assert manager.get_compression_level("guardian") == "high"
        assert manager.get_compression_level("scientist") == "low"

    def test_compression_level_desconocido_es_none(self, budgets_yaml: Path) -> None:
        """Rol sin configuracion usa nivel neutro 'none'."""
        manager = make_manager(budgets_yaml)
        assert manager.get_compression_level("unknown") == DEFAULT_COMPRESSION_LEVEL

    def test_threshold_default(self, budgets_yaml: Path) -> None:
        """El umbral del YAML (0.85) se aplica."""
        manager = make_manager(budgets_yaml)
        assert manager.get_threshold() == pytest.approx(DEFAULT_COMPRESSION_THRESHOLD)

    def test_threshold_sin_yaml(self, tmp_path: Path) -> None:
        """Sin YAML, el umbral es DEFAULT_COMPRESSION_THRESHOLD."""
        manager = make_manager(tmp_path / "missing.yaml")
        assert manager.get_threshold() == pytest.approx(DEFAULT_COMPRESSION_THRESHOLD)

    def test_has_budget_config(self, budgets_yaml: Path, tmp_path: Path) -> None:
        """has_budget_config refleja si el SSOT fue cargado."""
        assert make_manager(budgets_yaml).has_budget_config() is True
        assert make_manager(tmp_path / "missing.yaml").has_budget_config() is False


# ===========================================================================
# Integracion con BudgetManager (token_budget.py)
# ===========================================================================


class TestBudgetManagerIntegration:
    """BudgetManager.register_agent aplica el budget por rol del SSOT."""

    def test_register_agent_aplica_budget_por_rol(self, budgets_yaml: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Roles declarados reciben su budget del YAML."""
        manager = make_manager(budgets_yaml)
        monkeypatch.setattr(tb, "get_token_budget_manager", lambda: manager)
        mgr = BudgetManager()
        assert mgr.register_agent("guardian").total_budget == 2048
        assert mgr.register_agent("scientist").total_budget == 4096

    def test_rol_desconocido_mantiene_default_historico(self, budgets_yaml: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Rol no declarado conserva el default historico (backward compat)."""
        manager = make_manager(budgets_yaml)
        monkeypatch.setattr(tb, "get_token_budget_manager", lambda: manager)
        mgr = BudgetManager()
        assert mgr.register_agent("custom_agent").total_budget == DEFAULT_AGENT_BUDGET

    def test_sin_yaml_mantiene_flat_default(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Sin YAML, todos los agentes reciben DEFAULT_AGENT_BUDGET (4000)."""
        manager = make_manager(tmp_path / "missing.yaml")
        monkeypatch.setattr(tb, "get_token_budget_manager", lambda: manager)
        mgr = BudgetManager()
        assert mgr.register_agent("guardian").total_budget == DEFAULT_AGENT_BUDGET

    def test_budget_explicito_tiene_prioridad(self, budgets_yaml: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Un budget explicito en register_agent tiene prioridad sobre el SSOT."""
        manager = make_manager(budgets_yaml)
        monkeypatch.setattr(tb, "get_token_budget_manager", lambda: manager)
        mgr = BudgetManager()
        assert mgr.register_agent("guardian", budget=8000).total_budget == 8000


# ===========================================================================
# Backward compatibility
# ===========================================================================


class TestBackwardCompatibility:
    """Las constantes historicas siguen exportadas con el mismo nombre."""

    def test_constantes_historica(self) -> None:
        """DEFAULT_AGENT_BUDGET / DEFAULT_SESSION_BUDGET no cambian de valor."""
        assert DEFAULT_AGENT_BUDGET == 4000
        assert DEFAULT_SESSION_BUDGET == 16000

    def test_token_budget_default_directo(self) -> None:
        """TokenBudget directo (sin BudgetManager) usa DEFAULT_AGENT_BUDGET."""
        assert tb.TokenBudget(agent_id="x").total_budget == DEFAULT_AGENT_BUDGET

    def test_tracking_de_sesiones_no_cambiado(self, tmp_path: Path) -> None:
        """El tracker de sesiones conserva su contrato con el SSOT activo."""
        manager = make_manager(tmp_path / "missing.yaml")
        result = manager.track_usage("s1", 1000)
        assert result["remaining"] == 3000  # default_budget=4000 explicito
        assert manager.get_remaining("s1") == 3000
