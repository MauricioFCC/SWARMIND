"""Contrato de export multi-harness (capa universal de SWARMIND).

WHAT: fija como los adaptadores (Claude Code, Codex CLI, Cursor, Gemini CLI,
OpenCode) deben leer la SSOT ``.opencode/`` y escribir en su runtime.

Tres invariantes que antes NO se cumplian (y que los tests previos no veian
porque el fixture era plano, distinto al layout real):

1. **Agentes**: se exportan SOLO los perfiles base. Las variantes
   ``*.agent.min.md`` son artefactos OCULTOS especificos de OpenCode
   (``hidden: true``, cargados por el propio harness como prompt pre-compilado);
   exportarlas duplicaba cada agente (48 en vez de 24) en los otros harnesses.
   Todos los consumidores internos ya las excluian
   (``agent_discovery.discovery``, ``routing_mutation``, ``compile_agents``,
   ``audit_skills_agents``); ``converter_base`` era la excepcion.
2. **Skills**: la SSOT real es ``<skill>/SKILL.md`` (no ``.md`` planos). El
   descubrimiento devolvia ``[]`` en un repo real y ``export_skills`` no
   exportaba NADA (o colisionaba todos los SKILL.md en un unico nombre).
   Layout exigido por el estandar Agent Skills de la Linux Foundation, que
   comparten OpenCode, Claude Code y Codex.
3. **Idempotencia**: el docstring de ``converter_base`` promete "ejecutar N
   veces produce el mismo resultado"; ``ClaudeAdapter.export_agents`` embebia
   una fecha/hora, asi que cada export regeneraba ``.claude/AGENTS.md``.

WHY: sin estos contratos el acople universal (export a otros harnesses) se
rompe en silencio: agentes duplicados y skills que nunca llegan.

WHERE: ``harness/orchestrator/multi_harness/converter_base.py`` +
``adapters/{claude,codex,cursor,gemini}_adapter.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.orchestrator.multi_harness.adapters import (
    ClaudeAdapter,
    CodexAdapter,
    CursorAdapter,
    GeminiAdapter,
    OpenCodeAdapter,
)

_ROOT = Path(__file__).resolve().parents[2]
_AGENTS_DIR = _ROOT / ".opencode" / "agents"
_SKILLS_DIR = _ROOT / ".opencode" / "skills"
_MIN_SUFFIX = ".agent.min.md"

#: (adaptador, directorio destino de skills relativo a la raiz del proyecto)
_SKILL_TARGETS: list[tuple[type, tuple[str, ...]]] = [
    (ClaudeAdapter, (".claude", "skills")),
    (CodexAdapter, (".codex", "prompts", "skills")),
    (CursorAdapter, (".cursor", "skills")),
    (GeminiAdapter, (".gemini", "skills")),
]

#: (adaptador, directorio destino de agentes relativo a la raiz del proyecto)
_AGENT_TARGETS: list[tuple[type, tuple[str, ...]]] = [
    (ClaudeAdapter, (".claude", "agents")),
    (CodexAdapter, (".codex", "prompts")),
    (CursorAdapter, (".cursor", "agents")),
    (GeminiAdapter, (".gemini", "agents")),
]


@pytest.fixture
def real_layout_project(tmp_path: Path) -> Path:
    """Proyecto temporal con el layout REAL de SWARMIND.

    Skills en carpetas (``<skill>/SKILL.md``) y agentes con su variante
    oculta ``*.agent.min.md``, como en el repo productivo.
    """
    agents = tmp_path / ".opencode" / "agents"
    agents.mkdir(parents=True)
    (agents / "base.md").write_text(
        "---\nname: base\nmode: subagent\n---\n# Base\nAgente base.\n", encoding="utf-8"
    )
    (agents / f"base{_MIN_SUFFIX}").write_text(
        "---\nhidden: true\nname: base\n---\n# Base min\n", encoding="utf-8"
    )
    for name in ("alpha", "beta"):
        skill_dir = tmp_path / ".opencode" / "skills" / name
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: Skill {name}.\n---\nCuerpo.\n",
            encoding="utf-8",
        )
    return tmp_path


class TestDescubrimientoSsot:
    """Lectura de la SSOT ``.opencode/`` por parte de los adaptadores."""

    def test_agentes_excluye_las_variantes_ocultas(self) -> None:
        adapter = ClaudeAdapter(_ROOT)
        exported = adapter._get_opencode_agents()

        assert exported, "sin agentes descubiertos"
        con_min = [p for p in exported if p.name.endswith(_MIN_SUFFIX)]
        assert con_min == [], f"variantes .agent.min exportadas: {[p.name for p in con_min]}"

    def test_agentes_cubre_exactamente_los_perfiles_base(self) -> None:
        adapter = ClaudeAdapter(_ROOT)
        all_md = sorted(_AGENTS_DIR.glob("*.md"))
        base = [p for p in all_md if not p.name.endswith(_MIN_SUFFIX)]
        mins = [p for p in all_md if p.name.endswith(_MIN_SUFFIX)]

        exported = adapter._get_opencode_agents()
        assert exported == base, "el descubrimiento no coincide con los perfiles base"
        assert mins, "el repo debe tener variantes .agent.min (si no, el test no prueba nada)"

    def test_skills_usa_el_manifest_skill_md_real(self) -> None:
        adapter = ClaudeAdapter(_ROOT)
        skills = adapter._get_opencode_skills()

        assert len(skills) >= 40, f"skills descubiertas: {len(skills)}"
        assert {s.name for s in skills} == {"SKILL.md"}, "manifesto incorrecto"
        assert all(s.parent.is_dir() for s in skills), "SKILL.md debe vivir en su carpeta"

    def test_stats_de_opencode_cuentan_agentes_reales(self) -> None:
        """``num_agents`` no debe inflarse con las variantes ocultas."""
        stats = OpenCodeAdapter(_ROOT).get_stats()
        base = [p for p in _AGENTS_DIR.glob("*.md") if not p.name.endswith(_MIN_SUFFIX)]

        assert stats["num_agents"] == len(base)


class TestExportSkillsLayout:
    """Las skills exportadas conservan el layout estandar ``<skill>/SKILL.md``."""

    @pytest.mark.parametrize(("adapter_cls", "target_parts"), _SKILL_TARGETS)
    def test_skills_exportadas_por_carpeta(
        self, real_layout_project: Path, adapter_cls: type, target_parts: tuple[str, ...]
    ) -> None:
        adapter = adapter_cls(real_layout_project)
        result = adapter.export_skills()

        assert result.success is True
        assert result.files_exported == 2, "debe exportar las 2 skills del fixture"
        target = real_layout_project.joinpath(*target_parts)
        assert (target / "alpha" / "SKILL.md").is_file()
        assert (target / "beta" / "SKILL.md").is_file()

    @pytest.mark.parametrize(("adapter_cls", "target_parts"), _SKILL_TARGETS)
    def test_sin_colision_de_manifestos(
        self, real_layout_project: Path, adapter_cls: type, target_parts: tuple[str, ...]
    ) -> None:
        """Ningun SKILL.md debe caer plano en el directorio destino."""
        adapter = adapter_cls(real_layout_project)
        adapter.export_skills()
        target = real_layout_project.joinpath(*target_parts)

        assert not list(target.glob("SKILL.md")), "SKILL.md plano = colision entre skills"


class TestExportAgents:
    """Los adaptadores exportan solo perfiles base y de forma idempotente."""

    @pytest.mark.parametrize(("adapter_cls", "target_parts"), _AGENT_TARGETS)
    def test_export_sin_variantes_ocultas(
        self, real_layout_project: Path, adapter_cls: type, target_parts: tuple[str, ...]
    ) -> None:
        adapter = adapter_cls(real_layout_project)
        result = adapter.export_agents()

        assert result.success is True
        assert result.files_exported == 1, "solo debe exportar el agente base"
        exported = list(real_layout_project.joinpath(*target_parts).glob("*.md"))
        assert not [p for p in exported if p.name.endswith(_MIN_SUFFIX)]

    def test_claude_indice_de_agentes_idempotente(
        self, real_layout_project: Path
    ) -> None:
        """Dos exports seguidos producen ``.claude/AGENTS.md`` identico."""
        adapter = ClaudeAdapter(real_layout_project)
        adapter.export_agents()
        first = (real_layout_project / ".claude" / "AGENTS.md").read_text(encoding="utf-8")

        adapter.export_agents()
        second = (real_layout_project / ".claude" / "AGENTS.md").read_text(encoding="utf-8")

        assert first == second, "el indice cambia entre exports (fecha/hora embebida)"

    def test_claude_indice_no_lista_variantes(
        self, real_layout_project: Path
    ) -> None:
        adapter = ClaudeAdapter(real_layout_project)
        adapter.export_agents()
        index = (real_layout_project / ".claude" / "AGENTS.md").read_text(encoding="utf-8")

        assert "Base" in index, "el agente base debe listarse"
        assert _MIN_SUFFIX not in index, "la variante oculta no debe listarse"
