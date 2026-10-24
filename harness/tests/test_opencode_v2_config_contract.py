"""Contrato de config NATIVA OpenCode V2 del acople SWARMIND (spec 11.14).

WHAT: exige que los artefactos REALES de config de OpenCode estén en forma
nativa de V2 según la guía oficial (https://opencode.ai/v2/docs/migrate-v1/).
V2 acepta las claves V1 pero las normaliza en memoria y varias pasan a ser
ignoradas con warning (``compaction.prune``, ``reasoning`` de modelos,
``experimental.mcp_timeout`` deja de ser el canonical). Sin este contrato, la
config parece correcta al operador mientras el runtime ignora partes.

Criterios de aceptación (1 test = 1 criterio):

1. Template ``.opencode/opencode.json`` sin claves V1 deprecadas
   (``agent``, ``provider``, ``small_model``, ``experimental.mcp_timeout``,
   ``skills`` objeto, ``compaction.prune/reserved``).
2. Agentes de config con ``permissions`` (lista ordenada V2) y acciones V2
   (``shell``/``subagent``, nunca ``bash``/``task``).
3. ``mcp.timeout`` nativo (catalog+execution >= 90000) en disco.
4. Frontmatter de ``.opencode/agents/*.md`` sin ``permission:`` V1.
5. Plugin en el layout nativo ``.opencode/plugins/`` (el singular es legado).
6. Features de frontera V2 adoptadas: ``policies`` (sudo hard-deny),
   ``permissions`` globales (git read-only allow / push ask) y
   ``watcher.ignore`` (ruido de venv/caches/federated).

WHY: sin esto, cada render/sync puede reintroducir V1 sin que ninguna suite lo
note y el runtime degrada en silencio.

WHERE: ``.opencode/opencode.json`` + ``.opencode/agents/*.md`` +
``.opencode/plugins/compaction-context.js``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

_ROOT = Path(__file__).resolve().parents[2]
_CONFIG = _ROOT / ".opencode" / "opencode.json"
_AGENTS_DIR = _ROOT / ".opencode" / "agents"
_PLUGIN_V2 = _ROOT / ".opencode" / "plugins" / "compaction-context.js"
_PLUGIN_V1_DIR = _ROOT / ".opencode" / "plugin"

#: Claves de nivel superior V1 que V2 acepta pero normaliza/ignora.
_V1_TOP_KEYS = ("agent", "provider", "small_model", "command", "reference",
                "snapshot", "attachment", "plugin")

#: Acciones V1 prohibidas en forma nativa (bash->shell, task->subagent...).
_V1_ACTIONS = frozenset({"bash", "task", "write", "patch"})

#: Patron minimo de una regla V2 de permisos.
_RULE_FIELDS = frozenset({"action", "resource", "effect"})

#: Timeout minimo exigido a servers stdio en frio (npx/uvx).
_MIN_TIMEOUT_MS = 90_000


def _config() -> dict[str, Any]:
    """Template ``.opencode/opencode.json`` parseado (JSON con comentarios)."""
    raw = _CONFIG.read_text(encoding="utf-8")
    return json.loads("\n".join(ln for ln in raw.splitlines() if not ln.strip().startswith("//")))


def _frontmatter(path: Path) -> dict[str, Any]:
    """Frontmatter YAML de un archivo markdown (dict vacio si no tiene)."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    return yaml.safe_load(text.split("---", 2)[1]) or {}


def _base_agents() -> list[Path]:
    """Agentes base (excluye las variantes ocultas ``*.agent.min.md``)."""
    return sorted(p for p in _AGENTS_DIR.glob("*.md") if not p.name.endswith(".agent.min.md"))


class TestTemplateSinCamposV1:
    """El template versionado no conserva claves V1 deprecadas."""

    def test_sin_claves_v1_deprecadas_de_nivel_superior(self) -> None:
        doc = _config()
        found = sorted(k for k in _V1_TOP_KEYS if k in doc)
        assert found == [], (
            f"claves V1 en el template: {found}. V2 las normaliza en memoria y "
            "algunas se ignoran con warning; usa la forma nativa V2."
        )

    def test_experimental_sin_mcp_timeout_v1(self) -> None:
        doc = _config()
        experimental = doc.get("experimental") or {}
        assert "mcp_timeout" not in experimental, (
            "experimental.mcp_timeout es V1: el canonical V2 es "
            "mcp.timeout.{catalog,execution}"
        )

    def test_compaction_en_forma_v2(self) -> None:
        compaction = _config().get("compaction") or {}
        legacy = {"prune", "reserved", "preserve_recent_tokens", "tail_turns"} & set(compaction)
        assert not legacy, f"campos V1 de compaction: {sorted(legacy)}"
        assert isinstance((compaction.get("keep") or {}).get("tokens"), int), (
            "falta compaction.keep.tokens (V2 reteniene por presupuesto de tokens)"
        )
        buffer = compaction.get("buffer")
        if buffer is not None:
            assert isinstance(buffer, int) and buffer >= 0, (
                f"compaction.buffer invalido: {buffer!r} (entero no negativo)"
            )

    def test_buffer_no_fija_un_valor_absoluto(self) -> None:
        """El template NO fija ``buffer``: hereda el default proporcional (10%).

        Un valor absoluto no escala de modelos de 8K (locales) a 200K (cloud):
        ``buffer: 2000`` dejo solo 1% de holgura en sesiones de 200K y la
        compactacion automatica se disparaba tarde; el request desbordaba y el
        recovery de OpenCode volvia a desbordar -> error que obligaba a cambiar
        a un modelo de mayor contexto a mano. El default de V2 (10% del
        limite) es proporcional: 2K de holgura en 8K locales, 20K en 200K.
        """
        compaction = _config().get("compaction") or {}
        assert "buffer" not in compaction, (
            "buffer absoluto fijado en el template: usa el default proporcional "
            "de OpenCode (10% del limite) omitiendo la clave"
        )

    def test_skills_es_array_v2(self) -> None:
        skills = _config().get("skills")
        assert isinstance(skills, list), (
            f"skills debe ser el array V2 (paths/urls combinados), no {type(skills).__name__}"
        )

    def test_provider_bloque_nativo_v2(self) -> None:
        """``providers`` con ``package`` aisdk + ``settings``; sin npm/options."""
        doc = _config()
        assert "providers" in doc, "falta la seccion `providers` (V2)"
        legacy_provider = sorted(
            name for name, entry in (doc.get("providers") or {}).items()
            if "npm" in (entry or {}) or "options" in (entry or {})
        )
        assert legacy_provider == [], f"providers con campos V1: {legacy_provider}"
        llamacpp = (doc.get("providers") or {}).get("llamacpp") or {}
        assert str(llamacpp.get("package", "")).startswith("aisdk:"), (
            f"package V2 ausente: {llamacpp.get('package')!r} (V1 npm -> package aisdk:)"
        )
        assert "baseURL" in (llamacpp.get("settings") or {}), (
            "settings.baseURL ausente (V1 options.baseURL -> V2 settings)"
        )

    def test_modelos_en_forma_v2(self) -> None:
        """Ningun modelo en disco conserva ``reasoning``/``tools``/``options`` V1."""
        malos: list[str] = []
        for provider, entry in (_config().get("providers") or {}).items():
            for name, model in (entry.get("models") or {}).items():
                legacy = {"reasoning", "tools", "options"} & set(model or {})
                if legacy:
                    malos.append(f"{provider}/{name}: {sorted(legacy)}")
        assert malos == [], f"modelos con claves V1 (ignoradas con warning en V2): {malos}"


class TestAgentesEnFormaV2:
    """Entradas de config con ``permissions`` lista y acciones V2."""

    def test_agents_existe_sin_permission_v1(self) -> None:
        doc = _config()
        agents = doc.get("agents")
        assert isinstance(agents, dict) and agents, "falta la seccion `agents` (V2)"
        assert "agent" not in doc, "seccion `agent` singular es V1"
        legacy = sorted(n for n, e in agents.items() if "permission" in (e or {}))
        assert legacy == [], f"agentes con mapa `permission` V1: {legacy}"

    def test_reglas_permissions_con_forma_completa(self) -> None:
        agents = _config().get("agents") or {}
        malas: list[str] = []
        for name, entry in agents.items():
            for rule in (entry or {}).get("permissions") or []:
                if not isinstance(rule, dict) or set(rule) != _RULE_FIELDS:
                    malas.append(f"{name}: forma invalida {rule!r}")
                elif rule["action"] in _V1_ACTIONS:
                    malas.append(f"{name}: accion V1 `{rule['action']}`")
                elif rule["effect"] not in {"allow", "deny", "ask"}:
                    malas.append(f"{name}: effect invalido {rule['effect']!r}")
        assert malas == [], f"reglas V1/rotas: {malas}"

    def test_todo_agent_config_usa_permissions_lista(self) -> None:
        agents = _config().get("agents") or {}
        sin_reglas = [
            name for name, entry in agents.items()
            if "permissions" in (entry or {}) and not isinstance(entry["permissions"], list)
        ]
        assert sin_reglas == [], f"permissions debe ser lista ordenada V2: {sin_reglas}"


class TestMcpTimeoutNativoEnDisco:
    """``mcp.timeout`` nativo >= 90000 (los espejos leen este template)."""

    def test_timeout_catalog_y_execution_suficientes(self) -> None:
        timeout = ((_config().get("mcp") or {}).get("timeout")) or {}
        catalog = int(timeout.get("catalog") or 0)
        execution = int(timeout.get("execution") or 0)
        assert catalog >= _MIN_TIMEOUT_MS, f"mcp.timeout.catalog={catalog} < {_MIN_TIMEOUT_MS}"
        assert execution >= _MIN_TIMEOUT_MS, f"mcp.timeout.execution={execution} < {_MIN_TIMEOUT_MS}"


class TestFeaturesDeFronteraV2:
    """Features V2 adoptadas: policies, permissions globales y watcher."""

    def test_policies_hard_deny_sudo(self) -> None:
        policies = _config().get("policies")
        assert isinstance(policies, list) and policies, "falta `policies` (V2)"
        assert {"action": "tool.use", "resource": "shell:sudo *", "effect": "deny"} in policies, (
            "sin policy sudo hard-deny, un `Allow always` guardado podria"
            " autorizar sudo para siempre"
        )

    def test_permissions_globales_git(self) -> None:
        rules = _config().get("permissions")
        assert isinstance(rules, list) and rules, "falta `permissions` global (V2)"
        assert {"action": "shell", "resource": "git status *", "effect": "allow"} in rules, (
            "inspeccion git read-only debe ser allow (reduce prompts)"
        )
        assert {"action": "shell", "resource": "git push *", "effect": "ask"} in rules, (
            "push debe pedir confirmacion (acto deliberado, CMT/push consciente)"
        )
        assert {"action": "shell", "resource": "sudo *", "effect": "deny"} in rules

    def test_watcher_ignora_ruido_de_sistema(self) -> None:
        ignore = ((_config().get("watcher") or {}).get("ignore")) or []
        esperados = (".venv/**", "**/__pycache__/**", ".opencode/federated/**")
        faltan = [p for p in esperados if p not in ignore]
        assert faltan == [], (
            f"watcher.ignore sin {faltan}: recargas/buffers por ruido de "
            "venv/caches/federated en cada turno (TKN Cache-Shape)"
        )


class TestFrontmatterDeAgentesV2:
    """Los .md de agentes no declaran ``permission:`` V1 en el frontmatter."""

    def test_ningun_agente_base_usa_permission_v1(self) -> None:
        legacy = sorted(p.name for p in _base_agents() if "permission" in _frontmatter(p))
        assert legacy == [], (
            f"agentes con `permission:` V1: {legacy}. V2 usa `permissions:` "
            "(lista de reglas); V2 lo traduce, pero la fuente debe ser nativa."
        )

    def test_permissions_del_frontmatter_son_listas_v2(self) -> None:
        malos: list[str] = []
        for path in _AGENTS_DIR.glob("*.md"):
            perms = _frontmatter(path).get("permissions")
            if perms is None:
                continue
            if not isinstance(perms, list):
                malos.append(f"{path.name}: {type(perms).__name__}")
                continue
            for rule in perms:
                if not isinstance(rule, dict) or set(rule) != _RULE_FIELDS:
                    malos.append(f"{path.name}: regla invalida {rule!r}")
        assert malos == [], f"permissions no nativas: {malos}"


class TestPluginLayoutV2:
    """El plugin vive en el directorio nativo ``.opencode/plugins/``."""

    def test_plugin_en_directorio_plugins(self) -> None:
        assert _PLUGIN_V2.is_file(), (
            f"falta {_PLUGIN_V2.relative_to(_ROOT)} (layout V2 preferido: "
            "OpenCode descubre .opencode/plugins/)"
        )

    def test_directorio_singular_legado_retirado(self) -> None:
        assert not _PLUGIN_V1_DIR.exists(), (
            ".opencode/plugin/ (singular) sigue presente: con AMBOS directorios "
            "OpenCode cargaria el plugin dos veces y el hook de compactacion "
            "se registraria duplicado"
        )
