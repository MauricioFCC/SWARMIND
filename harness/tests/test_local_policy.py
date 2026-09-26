"""Tests para local_policy — politica local-first config-driven (ADR-0084).

Sin hardcode: target_local_ratio, confidence_margin y sample_rate salen
del YAML (`local_first:`) o de entorno (`SWARMIND_LOCAL_*`); defaults
seguros si falta el archivo.
"""

import pytest

from harness.model_router.local_policy import (
    DEFAULT_CONFIDENCE_MARGIN,
    DEFAULT_SAMPLE_RATE,
    DEFAULT_TARGET_RATIO,
    LocalPolicy,
    load_local_policy,
)


def test_defaults_when_no_file(tmp_path) -> None:
    """Sin YAML: defaults 99% local + oraculo 1% (0.99/0.50/0.01)."""
    policy = load_local_policy(tmp_path / "no-existe.yaml")
    assert policy.target_local_ratio == DEFAULT_TARGET_RATIO
    assert policy.confidence_margin == DEFAULT_CONFIDENCE_MARGIN
    assert policy.sample_rate == DEFAULT_SAMPLE_RATE
    assert DEFAULT_TARGET_RATIO == 0.99


def test_loads_yaml_section(tmp_path) -> None:
    """Lee la seccion local_first del YAML."""
    yaml_path = tmp_path / "ollama_models.yaml"
    yaml_path.write_text(
        "ollama:\n  base_url: x\nlocal_first:\n"
        "  target_local_ratio: 0.75\n  confidence_margin: 0.6\n  sample_rate: 0.2\n",
        encoding="utf-8",
    )
    policy = load_local_policy(yaml_path)
    assert policy.target_local_ratio == 0.75
    assert policy.confidence_margin == 0.6
    assert policy.sample_rate == 0.2


def test_env_overrides_yaml(tmp_path, monkeypatch) -> None:
    """SWARMIND_LOCAL_* vence al YAML (operacion sin editar archivos)."""
    yaml_path = tmp_path / "m.yaml"
    yaml_path.write_text("local_first:\n  sample_rate: 0.2\n", encoding="utf-8")
    monkeypatch.setenv("SWARMIND_LOCAL_SAMPLE_RATE", "0.35")
    policy = load_local_policy(yaml_path)
    assert policy.sample_rate == pytest.approx(0.35)


def test_invalid_values_raise() -> None:
    """Ratios fuera de [0,1] fallan accionable."""
    with pytest.raises(ValueError, match="WHAT"):
        LocalPolicy(target_local_ratio=1.5)
    with pytest.raises(ValueError, match="WHAT"):
        LocalPolicy(sample_rate=-0.1)


def test_policy_is_frozen() -> None:
    """LocalPolicy es inmutable."""
    policy = LocalPolicy()
    with pytest.raises(AttributeError):
        policy.sample_rate = 0.5  # type: ignore[misc]


def test_repo_yaml_loads() -> None:
    """El YAML real del repo carga con los valores documentados."""
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    policy = load_local_policy(repo / ".opencode" / "config" / "ollama_models.yaml")
    assert policy.target_local_ratio == 0.99
    assert policy.sample_rate == 0.01
