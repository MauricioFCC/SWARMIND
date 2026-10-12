"""Tests TDD de la política del coordinator (ADR-0103, WS-B: FR-B1/B2).

Verifican la migración de la doctrina del prompt largo (``coordinator.md``,
273 líneas) a configuración machine-readable (``coordinator_policy.yaml``,
arXiv:2609.00006: el coordinador frontera es un prompt corto + política en
config). Invariantes cubiertos:

(a) el YAML es parseable y expone las 8 secciones canónicas;
(b) ``coordinator.md`` fue recortado a <= :data:`MAX_COORDINATOR_LINES` líneas;
(c) ``coordinator.md`` referencia ``coordinator_policy.yaml`` (SSOT de política);
(d) coherencia: valores clave (``delegation.umbral``, ``budget.fact_finding``)
    no están vacíos;
(e) mutation-style: borrar una sección del YAML rompe el checker (oráculo
    sustituto de mutmut, no viable en Windows nativo; ver ADR-0098 §7).

La suite es solo-lectura: no edita producción, no usa red ni subprocess.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

# ---------------------------------------------------------------------------
# Rutas y constantes (MAG)
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = ROOT / ".opencode" / "agents"
POLICY_PATH = AGENTS_DIR / "coordinator_policy.yaml"
COORDINATOR_MD = AGENTS_DIR / "coordinator.md"

#: Presupuesto máximo de líneas del prompt del coordinator (FR-B2).
MAX_COORDINATOR_LINES = 70

#: Nombre del archivo SSOT que debe referenciar el prompt (FR-B2).
POLICY_FILENAME = "coordinator_policy.yaml"

#: Secciones canónicas que el YAML debe exponer (FR-B1).
REQUIRED_SECTIONS: tuple[str, ...] = (
    "delegation",
    "budget",
    "verification",
    "memory",
    "output_contract",
    "token_economics",
    "antipatterns",
    "tdd_authority",
)


# ---------------------------------------------------------------------------
# Helpers (reutilizables por los asserts mutation-style)
# ---------------------------------------------------------------------------


def _load_policy(path: Path = POLICY_PATH) -> dict:
    """Carga el YAML de política como ``dict`` (UTF-8).

    Args:
        path: Ruta del YAML de política.

    Returns:
        El documento parseado.

    Raises:
        FileNotFoundError: Si la ruta no existe.
    """
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _missing_sections(policy: dict) -> list[str]:
    """Devuelve las secciones canónicas ausentes del documento.

    Args:
        policy: Documento de política parseado.

    Returns:
        Lista de nombres de sección faltantes (vacía si están todas).
    """
    if not isinstance(policy, dict):
        return list(REQUIRED_SECTIONS)
    return [section for section in REQUIRED_SECTIONS if section not in policy]


def _read_lines(path: Path) -> list[str]:
    """Lee un archivo de texto como lista de líneas (UTF-8).

    Args:
        path: Ruta del archivo.

    Returns:
        Lista de líneas sin el salto final.
    """
    return path.read_text(encoding="utf-8").splitlines()


# ---------------------------------------------------------------------------
# (a) YAML parseable + secciones canónicas
# ---------------------------------------------------------------------------


def test_policy_yaml_parseable_with_required_sections() -> None:
    """El YAML parsea y contiene las 8 secciones canónicas."""
    # Arrange / Act
    policy = _load_policy()

    # Assert
    assert isinstance(policy, dict), f"{POLICY_FILENAME} debe ser un mapping YAML"
    assert _missing_sections(policy) == [], (
        f"Secciones canónicas ausentes: {_missing_sections(policy)}"
    )


# ---------------------------------------------------------------------------
# (b) coordinator.md recortado
# ---------------------------------------------------------------------------


def test_coordinator_md_under_line_budget() -> None:
    """``coordinator.md`` tiene <= :data:`MAX_COORDINATOR_LINES` líneas."""
    # Arrange / Act
    lines = _read_lines(COORDINATOR_MD)

    # Assert
    assert len(lines) <= MAX_COORDINATOR_LINES, (
        f"coordinator.md tiene {len(lines)} líneas (> {MAX_COORDINATOR_LINES}); "
        "la doctrina debe vivir en coordinator_policy.yaml"
    )


# ---------------------------------------------------------------------------
# (c) referencia al YAML
# ---------------------------------------------------------------------------


def test_coordinator_md_references_policy() -> None:
    """``coordinator.md`` referencia el archivo SSOT de política."""
    # Arrange / Act
    text = COORDINATOR_MD.read_text(encoding="utf-8")

    # Assert
    assert POLICY_FILENAME in text, (
        f"coordinator.md debe referenciar '{POLICY_FILENAME}' (SSOT de política)"
    )


# ---------------------------------------------------------------------------
# (d) coherencia: valores clave no vacíos
# ---------------------------------------------------------------------------


def test_policy_key_values_non_empty() -> None:
    """``delegation.umbral`` y ``budget.fact_finding`` tienen valores no vacíos."""
    # Arrange / Act
    policy = _load_policy()

    # Assert
    assert policy["delegation"]["umbral"], "delegation.umbral está vacío"
    assert policy["budget"]["fact_finding"], "budget.fact_finding está vacío"
    assert policy["verification"]["pipeline"], "verification.pipeline está vacío"
    assert policy["output_contract"]["schema"], "output_contract.schema está vacío"


# ---------------------------------------------------------------------------
# (e) mutation-style: borrar una sección rompe el checker
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("dropped", ["delegation", "budget", "tdd_authority"])
def test_mutation_missing_section_is_detected(tmp_path: Path, dropped: str) -> None:
    """Mutation-style: quitar una sección del YAML es detectado."""
    # Arrange
    policy = _load_policy()
    mutated = {key: value for key, value in policy.items() if key != dropped}
    mutated_path = tmp_path / POLICY_FILENAME
    mutated_path.write_text(
        yaml.safe_dump(mutated, allow_unicode=True), encoding="utf-8"
    )

    # Act
    reloaded = _load_policy(mutated_path)

    # Assert
    assert dropped in _missing_sections(reloaded), (
        f"El checker aceptó un YAML sin '{dropped}' (mutante vivo)"
    )


def test_mutation_policy_is_not_accepting_empty_document() -> None:
    """Mutation-style: un documento vacío/escalar nunca pasa la validación."""
    # Arrange / Act / Assert
    assert _missing_sections({}) == list(REQUIRED_SECTIONS)
    assert _missing_sections([]) == list(REQUIRED_SECTIONS)
