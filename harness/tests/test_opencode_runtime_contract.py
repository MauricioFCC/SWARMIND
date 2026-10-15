"""Contrato runtime de SWARMIND dentro de OpenCode (agregador de aislamiento).

WHAT: verifica los invariantes del acople 1:1 con OpenCode que NO se pueden
comprobar importando el harness, porque los decide el runtime de OpenCode:

1. **Agentes lanzables**: OpenCode V2 sin ``mode`` cae en ``primary`` y NO entra
   en el catalogo de subagentes; el fan-out del coordinator solo puede lanzar
   agentes ``subagent``/``all`` (verificado con ``opencode debug agents``: 55
   agentes, solo 7 subagent cuando 22 no declaraban ``mode``).
2. **Plugin V2**: OpenCode V2 exige ``export default { id, setup }``; la firma
   V1 (``export default async ({...}) => ({hooks})``) produce
   ``PluginModule.LoadError: Plugin must export a default definition ...`` y el
   hook de compactacion queda muerto en TODOS los proyectos.
3. **Comandos**: ``.opencode/commands/*.md`` es el directorio descubierto por
   OpenCode (el singular ``command/`` es legado).

WHY: sin estos tests el acople se rompe en silencio: los skills enrutan a
agentes que el modelo no puede lanzar y el plugin de compactacion no carga.

WHERE: ``.opencode/agents/*.md`` + ``.opencode/opencode.json`` +
``.opencode/plugin/compaction-context.js`` + ``.opencode/commands/``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

from harness.orchestrator.skill_bundler import SKILL_TO_AGENT

_ROOT = Path(__file__).resolve().parents[2]
_AGENTS_DIR = _ROOT / ".opencode" / "agents"
_CONFIG = _ROOT / ".opencode" / "opencode.json"
_PLUGIN = _ROOT / ".opencode" / "plugin" / "compaction-context.js"
_COMMANDS = _ROOT / ".opencode" / "commands"

#: Modos que OpenCode V2 pone en el catalogo de subagentes.
_LAUNCHABLE_MODES = frozenset({"subagent", "all"})


def _base_agents() -> list[Path]:
    """Agentes base (excluye las variantes ocultas ``*.agent.min.md``)."""
    return sorted(p for p in _AGENTS_DIR.glob("*.md") if not p.name.endswith(".agent.min.md"))


def _frontmatter(path: Path) -> dict:
    """Frontmatter YAML de un agente (dict vacio si no tiene)."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    return yaml.safe_load(text.split("---", 2)[1]) or {}


def _config_agents() -> dict:
    """Seccion ``agent`` de ``.opencode/opencode.json`` (JSON con comentarios)."""
    raw = _CONFIG.read_text(encoding="utf-8")
    stripped = "\n".join(ln for ln in raw.splitlines() if not ln.strip().startswith("//"))
    return json.loads(stripped).get("agent") or {}


def _effective_mode(agent: str) -> str:
    """Modo efectivo: el de la config (posterior) pisa el del archivo."""
    cfg_mode = (_config_agents().get(agent) or {}).get("mode")
    if cfg_mode:
        return str(cfg_mode)
    return str(_frontmatter(_AGENTS_DIR / f"{agent}.md").get("mode", "primary"))


class TestAgentesLanzables:
    """Todo agente del catalogo debe poder lanzarse como subagente."""

    def test_todo_agente_base_declara_mode(self) -> None:
        sin_mode = [p.stem for p in _base_agents() if "mode" not in _frontmatter(p)]
        assert sin_mode == [], (
            "agentes sin `mode:` (OpenCode los trataria como `primary` y el "
            f"fan-out no podria lanzarlos): {sin_mode}"
        )

    def test_todo_agente_base_es_lanzable(self) -> None:
        no_lanzables = [
            p.stem for p in _base_agents() if _effective_mode(p.stem) not in _LAUNCHABLE_MODES
        ]
        assert no_lanzables == [], f"agentes no lanzables como subagente: {no_lanzables}"

    def test_todo_destino_del_skill_router_es_lanzable(self) -> None:
        rotos = sorted(
            {agent for agent in set(SKILL_TO_AGENT.values()) if _effective_mode(agent) not in _LAUNCHABLE_MODES}
        )
        assert rotos == [], f"skills que enrutan a agentes inalcanzables: {rotos}"

    def test_coordinator_es_all(self) -> None:
        """El coordinator debe ser primario del sesion Y lanzable."""
        assert _effective_mode("coordinator") == "all"

    def test_config_no_degrada_un_agente_a_primary(self) -> None:
        degradados = sorted(
            name
            for name, entry in _config_agents().items()
            if (entry or {}).get("mode") == "primary"
        )
        assert degradados == [], (
            "la config declara `mode: primary` (fuera del catalogo de "
            f"subagentes): {degradados}"
        )


class TestPluginV2:
    """``compaction-context.js`` debe usar la API de plugins de OpenCode V2."""

    def test_export_default_es_objeto_con_id_y_setup(self) -> None:
        source = _PLUGIN.read_text(encoding="utf-8")
        assert re.search(r"export\s+default\s*\{", source), "falta default export objeto"
        assert re.search(r"^\s*id:\s*['\"]", source, flags=re.MULTILINE), "falta `id`"
        assert re.search(r"^\s*(async\s+)?setup\s*\(", source, flags=re.MULTILINE), (
            "falta `setup(ctx)`"
        )

    def test_no_usa_la_firma_v1(self) -> None:
        source = _PLUGIN.read_text(encoding="utf-8")
        # Ignora comentarios: documentan la migracion V1->V2, no son codigo.
        code = "\n".join(ln for ln in source.splitlines() if not ln.strip().startswith("//"))
        assert "experimental.session.compacting" not in code, (
            "hook V1: en V2 no se ejecuta (hay que usar session.hook('compaction'))"
        )
        assert not re.search(r"export\s+default\s+async\s*\(", code), (
            "firma V1: OpenCode V2 la rechaza con PluginModule.LoadError"
        )

    def test_registra_el_hook_de_compactacion(self) -> None:
        source = _PLUGIN.read_text(encoding="utf-8")
        assert 'session.hook("compaction"' in source

    def test_no_importa_dependencias_externas(self) -> None:
        """El repo no instala npm en los proyectos: un import romperia la carga."""
        source = _PLUGIN.read_text(encoding="utf-8")
        assert not re.search(r"^\s*import\s", source, flags=re.MULTILINE)


class TestComandosOpenCode:
    """``.opencode/commands/`` descubierto por OpenCode, con description."""

    def test_existe_y_no_esta_vacio(self) -> None:
        assert _COMMANDS.is_dir(), "falta .opencode/commands/"
        assert list(_COMMANDS.glob("*.md")), ".opencode/commands/ sin comandos"

    @pytest.mark.parametrize("name", ["mcp", "dispatch", "ver"])
    def test_comando_esperado_presente(self, name: str) -> None:
        assert (_COMMANDS / f"{name}.md").is_file(), f"falta /{name}"

    def test_todos_tienen_description(self) -> None:
        sin_desc = []
        for cmd in _COMMANDS.glob("*.md"):
            text = cmd.read_text(encoding="utf-8")
            if not text.startswith("---"):
                sin_desc.append(cmd.name)
                continue
            fm = yaml.safe_load(text.split("---", 2)[1]) or {}
            if not fm.get("description"):
                sin_desc.append(cmd.name)
        assert sin_desc == [], f"comandos sin description: {sin_desc}"
