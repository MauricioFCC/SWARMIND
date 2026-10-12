"""Tests TDD de CognitionSeeder (siembra del cognition store desde documentos).

Contrato:
  (a) ``seed_from_roadmap`` parsea lineas ``- **ADR-XXXX titulo (ESTADO)** — ...``
      y crea 1 leccion por ADR (domain="architecture", tags=["adr", estado, num]).
  (b) ``seed_from_mejoras`` parsea secciones ``## N. Titulo`` y crea 1 leccion
      por seccion (domain="improvement", tags=["mejora", "seccion-N"]).
  (c) idempotencia: la 2da corrida sobre el mismo ``CognitionSync`` no crea nada.
  (d) best-effort: un archivo inexistente devuelve ``[]`` sin lanzar excepcion.
  (e) el contenido se recorta a ~500 caracteres.

Aislamiento: se inyecta un ``CognitionSync`` con ``MockVectorStore`` en memoria
(NUNCA se toca el ``asi_cognition_store`` real en disco).
"""

from __future__ import annotations

from pathlib import Path

from harness.evolve_loop.cognition_seeder import CognitionSeeder, SeedSource
from harness.evolve_loop.cognition_sync import CognitionSync
from harness.tests.mock_vector_store import MockVectorStore

_COLLECTION = "asi_cognition_store"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sync() -> CognitionSync:
    """Crea un CognitionSync aislado con store en memoria.

    Returns:
        CognitionSync apuntando a un MockVectorStore con la coleccion cognition.
    """
    store = MockVectorStore()
    store.create_collection(_COLLECTION)
    return CognitionSync(vector_store=store)


def _write(path: Path, texto: str) -> Path:
    """Escribe ``texto`` (UTF-8) en ``path`` y lo devuelve.

    Args:
        path: Ruta destino.
        texto: Contenido markdown.

    Returns:
        La misma ruta para encadenar.
    """
    path.write_text(texto, encoding="utf-8")
    return path


_ROADMAP_MD = """\
# Estado del roadmap

## ADRs aplicados

- **ADR-0092 Ratio local ≥60% (APLICADO)** — capability_profiles.py define umbrales por modelo.
- **ADR-0065 Segundo Cerebro (PROPUESTO)** — overlay graph_overlay.py sobre SurrealDB.

## Notas
- una linea que no es ADR y debe ignorarse.
"""

_MEJORAS_MD = """\
# Mejoras Aplicadas

## 1. Fix LanceDB check prematuro

**Problema:**
El import disparaba sys.exit en cualquier importacion.

**Solución:**
Mover el check a una funcion perezosa.

## 2. Directorios vacios con .gitkeep

**Problema:** faltaban .gitkeep en subdirectorios.
"""


# ===================================================================
# (a) seed_from_roadmap
# ===================================================================


class TestSeedFromRoadmap:
    """Parseo de ADRs desde estado.md."""

    def test_parsea_dos_adr(self, tmp_path: Path) -> None:
        """Dos lineas ADR validas → 2 lecciones de arquitectura."""
        path = _write(tmp_path / "estado.md", _ROADMAP_MD)
        seeder = CognitionSeeder(sync=_make_sync())

        lessons = seeder.seed_from_roadmap(path)

        assert len(lessons) == 2
        assert all(leccion.domain == "architecture" for leccion in lessons)

        primero, segundo = lessons
        assert primero.id == "adr-0092"
        assert primero.title == "ADR-0092: Ratio local ≥60%"
        assert primero.tags == ["adr", "aplicado", "0092"]
        assert "capability_profiles.py" in primero.content

        assert segundo.id == "adr-0065"
        assert segundo.tags == ["adr", "propuesto", "0065"]
        assert "graph_overlay.py" in segundo.content

    def test_content_recortado_500(self, tmp_path: Path) -> None:
        """Un content largo se recorta a ~500 caracteres."""
        relleno = "x" * 900
        md = (
            "# Estado\n\n"
            f"- **ADR-0100 Titulo largo (APLICADO)** — {relleno}\n"
        )
        path = _write(tmp_path / "estado.md", md)
        seeder = CognitionSeeder(sync=_make_sync())

        lessons = seeder.seed_from_roadmap(path)

        assert len(lessons) == 1
        assert len(lessons[0].content) <= 500


# ===================================================================
# (b) seed_from_mejoras
# ===================================================================


class TestSeedFromMejoras:
    """Parseo de secciones desde .MEJORAS_SWARMIND.md."""

    def test_parsea_dos_secciones(self, tmp_path: Path) -> None:
        """Dos secciones ``## N.`` → 2 lecciones de mejora."""
        path = _write(tmp_path / "mejoras.md", _MEJORAS_MD)
        seeder = CognitionSeeder(sync=_make_sync())

        lessons = seeder.seed_from_mejoras(path)

        assert len(lessons) == 2
        assert all(leccion.domain == "improvement" for leccion in lessons)

        primera, segunda = lessons
        assert primera.id == "mejora-1"
        assert primera.title == "Fix LanceDB check prematuro"
        assert primera.tags == ["mejora", "seccion-1"]
        assert "sys.exit" in primera.content

        assert segunda.id == "mejora-2"
        assert "gitkeep" in segunda.content


# ===================================================================
# (c) idempotencia
# ===================================================================


class TestIdempotencia:
    """Dedup por id determinista contra el mismo store."""

    def test_segunda_corrida_cero_nuevas(self, tmp_path: Path) -> None:
        """La 2da corrida de roadmap → 0 lecciones nuevas."""
        path = _write(tmp_path / "estado.md", _ROADMAP_MD)
        seeder = CognitionSeeder(sync=_make_sync())

        primera = seeder.seed_from_roadmap(path)
        segunda = seeder.seed_from_roadmap(path)

        assert len(primera) == 2
        assert segunda == []

    def test_mejoras_idempotente(self, tmp_path: Path) -> None:
        """La 2da corrida de mejoras → 0 lecciones nuevas."""
        path = _write(tmp_path / "mejoras.md", _MEJORAS_MD)
        seeder = CognitionSeeder(sync=_make_sync())

        primera = seeder.seed_from_mejoras(path)
        segunda = seeder.seed_from_mejoras(path)

        assert len(primera) == 2
        assert segunda == []


# ===================================================================
# (d) best-effort
# ===================================================================


class TestBestEffort:
    """Archivos ausentes no rompen la siembra."""

    def test_roadmap_inexistente(self, tmp_path: Path) -> None:
        """Archivo inexistente → [] sin excepcion."""
        seeder = CognitionSeeder(sync=_make_sync())
        assert seeder.seed_from_roadmap(tmp_path / "no_existe.md") == []

    def test_mejoras_inexistente(self, tmp_path: Path) -> None:
        """Archivo inexistente → [] sin excepcion."""
        seeder = CognitionSeeder(sync=_make_sync())
        assert seeder.seed_from_mejoras(tmp_path / "no_existe.md") == []


# ===================================================================
# (e) seed_all
# ===================================================================


class TestSeedAll:
    """seed_all compone ambas fuentes."""

    def test_seed_all_con_fuentes_custom(self, tmp_path: Path) -> None:
        """seed_all acepta fuentes inyectadas y suma ambas."""
        roadmap = _write(tmp_path / "estado.md", _ROADMAP_MD)
        mejoras = _write(tmp_path / "mejoras.md", _MEJORAS_MD)
        seeder = CognitionSeeder(sync=_make_sync())

        lessons = seeder.seed_all(
            sources=(
                SeedSource(path=roadmap, domain="architecture"),
                SeedSource(path=mejoras, domain="improvement"),
            )
        )

        assert len(lessons) == 4
        dominios = {leccion.domain for leccion in lessons}
        assert dominios == {"architecture", "improvement"}
