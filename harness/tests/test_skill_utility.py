"""Tests TDD de SkillUtilityTracker (SESA: utility assignment + retention).

Contrato (arXiv 2607.29468, "utility assignment" / "retention"):
  (a) mark_helpful/mark_hurt/mark_retrieval incrementan y persisten
      (un tracker nuevo desde el mismo path reconstruye los contadores).
  (b) retrievals=3, helpful=0, hurt=1 → evictable (net=-1).
  (c) retrievals=2, hurt=1 → NO evictable (bajo min_retrievals).
  (d) helpful=2, hurt=1 → NO evictable (net positivo).
  (e) prune() elimina el .md del skills_dir Y el registro del tracker.
  (f) reconstruccion de estado desde JSONL (2do tracker ve lo del 1ro).

Aislamiento: path y skills_dir se inyectan con tmp_path; NUNCA se toca el
JSONL real en ``harness/db`` ni ``.opencode/skills/auto``.
"""

from __future__ import annotations

from pathlib import Path

from harness.evolve_loop.skill_utility import SkillUtility, SkillUtilityTracker


def _make_tracker(tmp_path: Path) -> SkillUtilityTracker:
    """Crea un tracker aislado en disco.

    Args:
        tmp_path: Directorio temporal de pytest.

    Returns:
        Tracker apuntando a un JSONL y skills_dir temporales.
    """
    return SkillUtilityTracker(
        path=tmp_path / "skill_utility.jsonl",
        skills_dir=tmp_path / "auto_skills",
    )


class TestSkillUtilityDataclass:
    """Snapshot inmutable de utilidad observada."""

    def test_net_es_helpful_menos_hurt(self) -> None:
        """net = helpful - hurt; los ceros por defecto dan net=0."""
        assert SkillUtility(name="x").net == 0
        assert SkillUtility(name="x", helpful=2, hurt=5).net == -3

    def test_roundtrip_dict(self) -> None:
        """to_dict/from_dict preservan todos los contadores."""
        original = SkillUtility(name="avoid-a", helpful=2, hurt=1, retrievals=4)
        restored = SkillUtility.from_dict(original.to_dict())
        assert restored == original


class TestMarkAndPersist:
    """(a) marcado incrementa y persiste."""

    def test_contadores_incrementan(self, tmp_path: Path) -> None:
        """Cada llamada de marcado incrementa su contador correspondiente."""
        tracker = _make_tracker(tmp_path)

        tracker.mark_helpful("avoid-a")
        tracker.mark_helpful("avoid-a")
        tracker.mark_hurt("avoid-a")
        tracker.mark_retrieval("avoid-a")

        util = tracker.get("avoid-a")
        assert util.helpful == 2
        assert util.hurt == 1
        assert util.retrievals == 1

    def test_get_desconocido_devuelve_zeros(self, tmp_path: Path) -> None:
        """get() de un skill sin marcas devuelve contadores en cero."""
        assert _make_tracker(tmp_path).get("inexistente") == SkillUtility(
            name="inexistente"
        )


class TestEvictable:
    """(b)(c)(d) criterio de eviction SESA."""

    def test_utilidad_neta_negativa_es_evictable(self, tmp_path: Path) -> None:
        """retrievals=3, helpful=0, hurt=1 → net=-1 → evictable."""
        tracker = _make_tracker(tmp_path)
        for _ in range(3):
            tracker.mark_retrieval("danino")
        tracker.mark_hurt("danino")

        evictable = tracker.evictable()
        assert [u.name for u in evictable] == ["danino"]
        assert evictable[0].net == -1

    def test_bajo_min_retrievals_no_es_evictable(self, tmp_path: Path) -> None:
        """retrievals=2, hurt=1 → bajo el minimo → NO evictable."""
        tracker = _make_tracker(tmp_path)
        tracker.mark_retrieval("poco-uso")
        tracker.mark_retrieval("poco-uso")
        tracker.mark_hurt("poco-uso")

        assert tracker.evictable() == []

    def test_utilidad_positiva_no_es_evictable(self, tmp_path: Path) -> None:
        """helpful=2, hurt=1 → net=+1 → NO evictable (aunque retrievals>=3)."""
        tracker = _make_tracker(tmp_path)
        for _ in range(3):
            tracker.mark_retrieval("util")
        tracker.mark_helpful("util")
        tracker.mark_helpful("util")
        tracker.mark_hurt("util")

        assert tracker.evictable() == []

    def test_orden_por_net_ascendente(self, tmp_path: Path) -> None:
        """Los skills mas daninos (net mas bajo) van primero."""
        tracker = _make_tracker(tmp_path)
        for name, hurt in (("leve", 1), ("grave", 3)):
            for _ in range(3):
                tracker.mark_retrieval(name)
            for _ in range(hurt):
                tracker.mark_hurt(name)

        assert [u.name for u in tracker.evictable()] == ["grave", "leve"]


class TestPrune:
    """(e) eviction fisica del skill + registro."""

    def test_prune_elimina_archivo_y_registro(self, tmp_path: Path) -> None:
        """prune: elimina el .md y el registro, devuelve el name pruned."""
        tracker = _make_tracker(tmp_path)
        skills_dir = tmp_path / "auto_skills"
        skills_dir.mkdir(parents=True, exist_ok=True)
        skill_file = skills_dir / "danino.md"
        skill_file.write_text("# danino\n", encoding="utf-8")

        for _ in range(3):
            tracker.mark_retrieval("danino")
        tracker.mark_hurt("danino")

        pruned = tracker.prune()

        assert pruned == ["danino"]
        assert not skill_file.exists()
        assert tracker.get("danino").retrievals == 0  # registro removido

    def test_prune_sin_md_solo_quita_registro(self, tmp_path: Path) -> None:
        """Si el .md no existe, prune igual quita el registro del tracker."""
        tracker = _make_tracker(tmp_path)
        for _ in range(3):
            tracker.mark_retrieval("huerfano")
        tracker.mark_hurt("huerfano")

        assert tracker.prune() == ["huerfano"]
        assert tracker.get("huerfano").hurt == 0


class TestReconstruccion:
    """(f) carga idempotente desde JSONL."""

    def test_segundo_tracker_reconstruye_estado(self, tmp_path: Path) -> None:
        """Un tracker nuevo desde el mismo path ve lo que escribio el 1ro."""
        path = tmp_path / "skill_utility.jsonl"
        skills_dir = tmp_path / "auto_skills"

        first = SkillUtilityTracker(path=path, skills_dir=skills_dir)
        first.mark_helpful("avoid-x")
        first.mark_retrieval("avoid-x")
        first.mark_retrieval("avoid-x")
        first.mark_retrieval("avoid-x")
        first.mark_hurt("avoid-x")

        second = SkillUtilityTracker(path=path, skills_dir=skills_dir)
        util = second.get("avoid-x")
        assert util.helpful == 1
        assert util.hurt == 1
        assert util.retrievals == 3

    def test_prune_no_reaparece_al_recargar(self, tmp_path: Path) -> None:
        """Tras prune, un tracker nuevo NO ve el skill removido."""
        path = tmp_path / "skill_utility.jsonl"
        skills_dir = tmp_path / "auto_skills"

        first = SkillUtilityTracker(path=path, skills_dir=skills_dir)
        for _ in range(3):
            first.mark_retrieval("muerto")
        first.mark_hurt("muerto")
        first.prune()

        second = SkillUtilityTracker(path=path, skills_dir=skills_dir)
        assert second.get("muerto") == SkillUtility(name="muerto")
