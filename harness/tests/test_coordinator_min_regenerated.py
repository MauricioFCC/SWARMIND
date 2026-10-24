"""Tests de regeneracion del artefacto precompilado ``coordinator.agent.min.md``.

Verifican que el prompt minificado del coordinator sea coherente con la doctrina
vigente (ADR-0103, WS-B): frontmatter completo, referencia a
``coordinator_policy.yaml`` (SSOT de politica) y sin doctrina vieja pre-WS-B.

La suite es solo-lectura: ``test_minified_is_synced_with_source`` recompila en
memoria con :func:`minify_agent` (no escribe artefactos).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from harness.scripts.compile_agents import minify_agent

# ---------------------------------------------------------------------------
# Rutas y constantes (MAG)
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = ROOT / ".opencode" / "agents"
COORDINATOR_MD = AGENTS_DIR / "coordinator.md"
COORDINATOR_MIN = AGENTS_DIR / "coordinator.agent.min.md"

#: Nombre del YAML SSOT que el artefacto minificado debe referenciar.
POLICY_FILENAME = "coordinator_policy.yaml"

#: Fragmentos de doctrina pre-WS-B que NO deben sobrevivir en el .min.md.
STALE_DOCTRINE_MARKERS: tuple[str, ...] = (
    "LTS Shared Memory",
    "AgentBus",
    "Helium Workflow",
)


# ---------------------------------------------------------------------------
# Helpers (reutilizables por los asserts mutation-style)
# ---------------------------------------------------------------------------


def _read(path: Path) -> str:
    """Lee un archivo de texto en UTF-8.

    Args:
        path: Ruta del archivo.

    Returns:
        Contenido completo (nuevas lineas normalizadas por el SO).
    """
    return path.read_text(encoding="utf-8")


def _parse_frontmatter(text: str) -> dict[str, Any]:
    """Extrae el frontmatter YAML de un documento .md.

    Args:
        text: Contenido markdown que inicia con ``---``.

    Returns:
        Documento frontmatter parseado.

    Raises:
        AssertionError: Si el texto no tiene frontmatter delimitado.
    """
    assert text.startswith("---"), "el .min.md debe conservar el frontmatter"
    end = text.find("---", 3)
    assert end != -1, "frontmatter sin delimitador de cierre"
    return yaml.safe_load(text[3:end])


def _references_policy(text: str) -> bool:
    """Indica si un texto referencia el YAML SSOT de politica.

    Args:
        text: Contenido a inspeccionar.

    Returns:
        ``True`` si contiene el nombre del archivo de politica.
    """
    return POLICY_FILENAME in text


# ---------------------------------------------------------------------------
# Invariantes del artefacto regenerado
# ---------------------------------------------------------------------------


class TestCoordinatorMinRegenerated:
    """Invariantes del artefacto ``coordinator.agent.min.md`` regenerado."""

    def test_minified_is_synced_with_source(self) -> None:
        """El .min.md en disco coincide con recompilar el .md fuente (no stale)."""
        # Arrange
        source = _read(COORDINATOR_MD)
        on_disk = _read(COORDINATOR_MIN)

        # Act
        regenerated = minify_agent(source)

        # Assert
        assert regenerated == on_disk, (
            "coordinator.agent.min.md esta desincronizado: ejecutar "
            "`python harness/scripts/compile_agents.py --role coordinator`"
        )

    def test_min_references_policy_yaml(self) -> None:
        """(a) El .min.md referencia ``coordinator_policy.yaml`` (SSOT)."""
        # Arrange / Act / Assert
        assert _references_policy(_read(COORDINATOR_MIN)), (
            f"coordinator.agent.min.md debe referenciar '{POLICY_FILENAME}'"
        )

    def test_min_frontmatter_matches_source(self) -> None:
        """(b) El frontmatter del .min.md = el del .md fuente + `hidden: true`.

        El marcador `hidden` es exclusivo de OpenCode (oculta la variante
        minificada para que no aparezca como agente duplicado); el resto del
        frontmatter debe seguir coincidiendo con el .md fuente.
        """
        # Arrange
        source_fm = dict(_parse_frontmatter(_read(COORDINATOR_MD)))
        expected = {**source_fm, "hidden": True}

        # Act / Assert
        assert _parse_frontmatter(_read(COORDINATOR_MIN)) == expected, (
            "el frontmatter del .min.md debe ser el del .md fuente + "
            "`hidden: true` (marcador OpenCode-only; ver compile_agents.minify_agent)"
        )

    def test_min_has_no_stale_doctrine(self) -> None:
        """(b) El .min.md no conserva doctrina pre-WS-B (secciones obsoletas)."""
        # Arrange
        text = _read(COORDINATOR_MIN)

        # Act
        survivors = [marker for marker in STALE_DOCTRINE_MARKERS if marker in text]

        # Assert
        assert not survivors, f"doctrina vieja sobrevive en el .min.md: {survivors}"

    def test_mutation_removing_policy_reference_is_detected(self) -> None:
        """(c) mutation-style: borrar la referencia al YAML rompe el chequeo."""
        # Arrange
        original = _read(COORDINATOR_MIN)
        mutated = original.replace(POLICY_FILENAME, "POLICY_REMOVED")

        # Act / Assert
        assert POLICY_FILENAME in original, "sanity: el fixture debe referenciar el YAML"
        assert not _references_policy(mutated), (
            "el checker acepto un .min.md sin referencia al YAML (mutante vivo)"
        )
