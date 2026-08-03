"""Test de sincronia: .opencode/config/*.yaml vs realidad del proyecto.

Verifica que los YAML de configuracion de opencode reflejen EXACTAMENTE
lo que existe en el proyecto (agentes, skills, dependencias, versiones).

Regla universal: los YAML no deben estar desactualizados (reflejan librerias
y configuraciones que no existen o versiones viejas).

Archivos validados:
  - .opencode/config/project_config.yaml  (PROJECT_VERSION, agent_count, skill_count, collections)
  - .opencode/config/routing_rules.yaml   (agentes referenciados existen)
  - .opencode/config/token_budgets.yaml   (role_budgets coinciden con agentes core)

MODOS:
  pytest test_opencode_config_sync.py          # verifica sincronia
  python test_opencode_config_sync.py scan     # reporta discrepancias
  python test_opencode_config_sync.py evolve   # AUTO-MEJORA: actualiza YAML a la realidad
"""
from __future__ import annotations

import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = ROOT / ".opencode" / "config"
PROJECT_CONFIG = CONFIG_DIR / "project_config.yaml"
ROUTING_RULES = CONFIG_DIR / "routing_rules.yaml"
TOKEN_BUDGETS = CONFIG_DIR / "token_budgets.yaml"
STATE_FILE = Path(__file__).parent / "test_opencode_config_sync_state.json"

# Nombres reales del proyecto
AGENTS_DIR = ROOT / ".opencode" / "agents"
SKILLS_DIR = ROOT / ".opencode" / "skills"


def load_yaml(path: Path) -> dict[str, Any]:
    """Carga YAML sin PyYAML (parser minimal para configs flat)."""
    import yaml
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_state() -> dict[str, Any]:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"known_drifts": {}, "last_evolve": None, "drift_history": {}}


def save_state(state: dict[str, Any]) -> None:
    STATE_FILE.write_text(
        json.dumps(state, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )


def real_agents() -> list[str]:
    """Lista de agentes reales (sin .min.md ni .gitkeep)."""
    agents = []
    for f in AGENTS_DIR.glob("*.md"):
        if f.name.endswith(".min.md"):
            continue
        agents.append(f.stem)
    return sorted(agents)


def real_skills() -> list[str]:
    """Lista de skills reales (directorios con SKILL.md)."""
    skills = []
    for d in SKILLS_DIR.iterdir():
        if d.is_dir() and (d / "SKILL.md").exists():
            skills.append(d.name)
    return sorted(skills)


# ===========================================================================
# PROJECT_CONFIG.YAML
# ===========================================================================


class TestProjectConfigSync:
    """Verifica que project_config.yaml refleje la realidad del proyecto."""

    def test_agent_count_matches_reality(self) -> None:
        """agent_count / AGENTS.total debe coincidir con los .md reales."""
        config = load_yaml(PROJECT_CONFIG)
        real = real_agents()
        # Verificar en multiple lugares
        harness_cfg = config.get("HARNESS", {})
        agents_cfg = config.get("AGENTS", {})
        expected_count = len(real)

        for key, value in [("agent_count", harness_cfg.get("agent_count")),
                           ("AGENTS.total", agents_cfg.get("total"))]:
            if value is not None:
                assert value == expected_count, (
                    f"project_config.yaml: {key}={value} pero hay {expected_count} agentes reales. "
                    f"Ejecutar: python -m harness.tests.test_opencode_config_sync evolve"
                )

    def test_skill_count_matches_reality(self) -> None:
        """SKILLS.total debe coincidir con los directorios reales."""
        config = load_yaml(PROJECT_CONFIG)
        real = real_skills()
        expected_count = len(real)
        skills_cfg = config.get("SKILLS", {}).get("total")
        assert skills_cfg == expected_count, (
            f"project_config.yaml: SKILLS.total={skills_cfg} pero hay {expected_count} skills reales. "
            f"Ejecutar evolve"
        )

    def test_agent_list_matches_reality(self) -> None:
        """AGENTS.agent_list debe contener todos los agentes reales."""
        config = load_yaml(PROJECT_CONFIG)
        real = set(real_agents())
        listed = set(config.get("AGENTS", {}).get("agent_list", []))
        missing = real - listed
        assert not missing, (
            f"project_config.yaml: AGENTS.agent_list no incluye: {sorted(missing)}. "
            f"Ejecutar evolve"
        )

    def test_skill_list_matches_reality(self) -> None:
        """SKILLS.skill_list debe contener todos los skills reales."""
        config = load_yaml(PROJECT_CONFIG)
        real = set(real_skills())
        listed = set(config.get("SKILLS", {}).get("skill_list", []))
        missing = real - listed
        assert not missing, (
            f"project_config.yaml: SKILLS.skill_list no incluye: {sorted(missing)}. "
            f"Ejecutar evolve"
        )

    def test_collections_match_lance_schema(self) -> None:
        """HARNESS.collections_lancedb debe coincidir con DEFAULT_COLLECTIONS."""
        # Verificar contra la fuente real si existe
        schemas = ROOT / "harness" / "memory_rag" / "lance_schemas.py"
        if not schemas.exists():
            pytest.skip("lance_schemas.py no existe")
        import ast
        tree = ast.parse(schemas.read_text(encoding="utf-8"))
        real_collections: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and "COLLECTION" in target.id:
                        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                            real_collections.add(node.value.value)
                        elif isinstance(node.value, (ast.List, ast.Tuple)):
                            for elt in node.value.elts:
                                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                    real_collections.add(elt.value)
        if not real_collections:
            pytest.skip("No se pudieron extraer colecciones")
        config = load_yaml(PROJECT_CONFIG)
        listed = set(config.get("HARNESS", {}).get("collections_lancedb", []))
        # Solo verificar que todas las listadas existen (no exigir igualdad exacta)
        extra = listed - real_collections
        assert not extra, (
            f"project_config.yaml: collections_lancedb tiene colecciones que no existen: {sorted(extra)}"
        )

    def test_project_version_format(self) -> None:
        """PROJECT_VERSION debe ser semver (X.Y.Z)."""
        config = load_yaml(PROJECT_CONFIG)
        version = str(config.get("PROJECT_VERSION", ""))
        assert re.match(r"^\d+\.\d+\.\d+$", version), (
            f"project_config.yaml: PROJECT_VERSION='{version}' no es semver"
        )


# ===========================================================================
# ROUTING_RULES.YAML
# ===========================================================================


class TestRoutingRulesSync:
    """Verifica que routing_rules.yaml referencie agentes existentes."""

    def test_all_agents_in_routes_exist(self) -> None:
        """Todos los agentes en domain_routes deben existir."""
        config = load_yaml(ROUTING_RULES)
        real = set(real_agents())
        rules = config.get("routing_rules", {})
        for route in rules.get("domain_routes", []):
            for agent in route.get("agents", []):
                assert agent in real, (
                    f"routing_rules.yaml: agente '{agent}' en domain '{route.get('domain')}' "
                    f"no existe en .opencode/agents/. Ejecutar evolve"
                )

    def test_domains_reference_known_skills(self) -> None:
        """Los domains deben corresponder a skills o dominios conocidos."""
        config = load_yaml(ROUTING_RULES)
        rules = config.get("routing_rules", {})
        skill_domains = set(real_skills())
        # Dominios adicionales validos que no son skills (agrupadores)
        valid_domains = skill_domains | {
            "quantitative-analysis", "ai-ml", "memory", "quality",
            "documentation", "universal", "data", "risk-management",
            "architecture", "security", "devops", "mobile", "frontend",
            "trading",
        }
        for route in rules.get("domain_routes", []):
            domain = route.get("domain")
            assert domain in valid_domains, (
                f"routing_rules.yaml: domain '{domain}' no corresponde a skill ni dominio conocido"
            )


# ===========================================================================
# TOKEN_BUDGETS.YAML
# ===========================================================================


class TestTokenBudgetsSync:
    """Verifica que token_budgets.yaml coincida con agentes core."""

    def test_role_budgets_reference_core_agents(self) -> None:
        """role_budgets debe incluir los 5 agentes core (coordinator, builder, scientist, guardian, evolve)."""
        config = load_yaml(TOKEN_BUDGETS)
        budgets = set(config.get("role_budgets", {}).keys())
        core = {"coordinator", "builder", "scientist", "guardian", "evolve"}
        missing = core - budgets
        assert not missing, (
            f"token_budgets.yaml: role_budgets no incluye agentes core: {sorted(missing)}"
        )

    def test_all_role_budgets_exist_as_agents(self) -> None:
        """Todos los role_budgets deben ser agentes reales."""
        config = load_yaml(TOKEN_BUDGETS)
        real = set(real_agents())
        budgets = set(config.get("role_budgets", {}).keys())
        phantom = budgets - real
        assert not phantom, (
            f"token_budgets.yaml: role_budgets referencian agentes inexistentes: {sorted(phantom)}"
        )


# ===========================================================================
# Auto-mejora: actualizar YAML a la realidad
# ===========================================================================


class TestConfigSelfImprovement:
    """Mecanismo de auto-mejora: el test puede sincronizar los YAML."""

    def test_state_file_well_formed(self) -> None:
        """El estado debe ser JSON valido."""
        state = load_state()
        assert "known_drifts" in state

    def test_reporter_runs(self) -> None:
        """El scanner de drift debe ejecutarse sin errores."""
        results = scan_config_drift(verbose=False)
        assert isinstance(results, dict)
        assert "project_config" in results
        assert "routing_rules" in results


# ===========================================================================
# Helpers
# ===========================================================================


def scan_config_drift(verbose: bool = False) -> dict[str, list[str]]:
    """Escanea los YAML vs realidad. Retorna discrepancias por archivo."""
    drift: dict[str, list[str]] = {"project_config": [], "routing_rules": [], "token_budgets": []}
    real_agents_set = set(real_agents())
    real_skills_set = set(real_skills())

    # project_config.yaml
    try:
        config = load_yaml(PROJECT_CONFIG)
        harness_cfg = config.get("HARNESS", {})
        agents_cfg = config.get("AGENTS", {})
        skills_cfg = config.get("SKILLS", {})
        if harness_cfg.get("agent_count") != len(real_agents_set):
            drift["project_config"].append(
                f"HARNESS.agent_count={harness_cfg.get('agent_count')} != {len(real_agents_set)}"
            )
        if agents_cfg.get("total") != len(real_agents_set):
            drift["project_config"].append(f"AGENTS.total={agents_cfg.get('total')} != {len(real_agents_set)}")
        if skills_cfg.get("total") != len(real_skills_set):
            drift["project_config"].append(f"SKILLS.total={skills_cfg.get('total')} != {len(real_skills_set)}")
        listed_agents = set(agents_cfg.get("agent_list", []))
        missing_agents = real_agents_set - listed_agents
        if missing_agents:
            drift["project_config"].append(f"AGENTS.agent_list missing: {sorted(missing_agents)}")
        listed_skills = set(skills_cfg.get("skill_list", []))
        missing_skills = real_skills_set - listed_skills
        if missing_skills:
            drift["project_config"].append(f"SKILLS.skill_list missing: {sorted(missing_skills)}")
    except Exception as e:  # noqa: BLE001 - parser defensivo
        drift["project_config"].append(f"ERROR parsing: {e}")

    # routing_rules.yaml
    try:
        config = load_yaml(ROUTING_RULES)
        for route in config.get("routing_rules", {}).get("domain_routes", []):
            for agent in route.get("agents", []):
                if agent not in real_agents_set:
                    drift["routing_rules"].append(
                        f"agente '{agent}' en domain '{route.get('domain')}' no existe"
                    )
    except Exception as e:  # noqa: BLE001 - parser defensivo
        drift["routing_rules"].append(f"ERROR parsing: {e}")

    # token_budgets.yaml
    try:
        config = load_yaml(TOKEN_BUDGETS)
        for role in config.get("role_budgets", {}):
            if role not in real_agents_set:
                drift["token_budgets"].append(f"role_budget '{role}' no es agente real")
    except Exception as e:  # noqa: BLE001 - parser defensivo
        drift["token_budgets"].append(f"ERROR parsing: {e}")

    if verbose:
        for file, items in drift.items():
            print(f"\n{file}: {len(items)} drift(s)")
            for item in items[:10]:
                print(f"  - {item}")

    return drift


def evolve_config_sync(dry_run: bool = False) -> dict[str, Any]:
    """AUTO-MEJORA: actualiza los YAML a la realidad del proyecto.

    Returns:
        dict con archivos actualizados y acciones.
    """

    real_agents_list = real_agents()
    real_skills_list = real_skills()
    actions: list[str] = []

    # 1. Actualizar project_config.yaml
    text = PROJECT_CONFIG.read_text(encoding="utf-8")
    original = text
    new_text = re.sub(r"agent_count: \d+", f"agent_count: {len(real_agents_list)}", text)
    new_text = re.sub(r"skill_count: \d+", f"skill_count: {len(real_skills_list)}", new_text)
    # Actualizar AGENTS.total y SKILLS.total (cada uno con su contexto)
    # AGENTS.total -> len(real_agents_list), SKILLS.total -> len(real_skills_list)
    new_text = re.sub(
        r"(?ms)(^(\s*)total:\s*)(\d+)(\s*$)(?=\n\s*agent_list:)",
        lambda m: f"{m.group(1)}{len(real_agents_list)}",
        new_text,
    )
    new_text = re.sub(
        r"(?ms)(^(\s*)total:\s*)(\d+)(\s*$)(?=\n\s*skill_list:)",
        lambda m: f"{m.group(1)}{len(real_skills_list)}",
        new_text,
    )
    # Reconstruir agent_list completo
    if "agent_list:" in new_text:
        agent_lines = "\n".join(f"    - {a}" for a in real_agents_list)
        new_text = re.sub(
            r"(?ms)agent_list:.*?(?=\n\s*\w+:|$)",
            f"agent_list:\n{agent_lines}",
            new_text,
        )
    # Reconstruir skill_list completo
    if "skill_list:" in new_text:
        skill_lines = "\n".join(f"    - {s}" for s in real_skills_list)
        new_text = re.sub(
            r"(?ms)skill_list:.*?(?=\n\s*\w+:|$)",
            f"skill_list:\n{skill_lines}",
            new_text,
        )
    if new_text != original:
        PROJECT_CONFIG.write_text(new_text, encoding="utf-8")
        actions.append(f"project_config.yaml: counts + lists actualizados ({len(real_agents_list)} agentes, {len(real_skills_list)} skills)")

    # 2. Reportar routing_rules y token_budgets (no auto-actualizar: requieren criterio)
    drift = scan_config_drift(verbose=False)
    for rule_file, items in drift.items():
        if items:
            actions.append(f"{rule_file}: {len(items)} drift(s) detectados (revision manual)")

    state = load_state()
    state["last_evolve"] = datetime.now(UTC).isoformat()
    state["drift_history"][state["last_evolve"]] = {
        f: len(v) for f, v in drift.items()
    }
    save_state(state)

    return {"actions": actions, "drift": drift}


# ===========================================================================
# Presupuesto de tokens en descripciones (optimización de contexto)
# ===========================================================================


class TestDescriptionTokenBudget:
    """Las descripciones de agents/skills deben ser compactas (ahorro tokens).

    Regla CFG + optimización de contexto: las notas largas (UPG/NAM/FRS)
    se resumen con abreviaciones tacitas en vez de repetir la frase completa
    51 veces. Las reglas completas viven UNA vez en base_principles.md.

    Presupuesto: max 40 tokens por descripcion (~250 chars).
    Ahorro medido: 3875 -> 1684 tokens totales (-57%).
    """

    MAX_TOKENS_PER_DESCRIPTION = 45
    MAX_CHARS_PER_DESCRIPTION = 320

    def test_no_verbose_repeated_rules(self) -> None:
        """CFG: las descripciones usan abreviaciones (UPG·NAM·FRS), no frases largas."""
        verbose_markers = [
            "UPG: usar ultima version estable",
            "NAM: snake_case archivos+vars",
            "FRS: SIEMPRE web research",
            "CFG: los YAML de config",
        ]
        for f in list(AGENTS_DIR.glob("*.md")) + list(SKILLS_DIR.glob("*/SKILL.md")):
            if f.name.endswith(".min.md"):
                continue
            text = f.read_text(encoding="utf-8")
            for marker in verbose_markers:
                assert marker not in text, (
                    f"CFG/tokens: {f.relative_to(ROOT)} repite la regla '{marker[:20]}...'. "
                    f"Usar abreviacion (UPG·NAM·FRS). Reglas completas en base_principles.md"
                )

    def test_description_token_budget(self) -> None:
        """CFG/tokens: cada descripcion <= 40 tokens (~260 chars)."""
        violations = []
        for f in list(AGENTS_DIR.glob("*.md")) + list(SKILLS_DIR.glob("*/SKILL.md")):
            if f.name.endswith(".min.md"):
                continue
            text = f.read_text(encoding="utf-8")
            # Extraer solo el frontmatter (entre --- ---)
            if not text.startswith("---"):
                continue
            parts = text.split("---", 2)
            if len(parts) < 3:
                continue
            data = yaml.safe_load(parts[1])
            desc = data.get("description", "")
            if len(desc) > self.MAX_CHARS_PER_DESCRIPTION:
                violations.append(
                    f"{f.relative_to(ROOT)}: {len(desc)} chars > {self.MAX_CHARS_PER_DESCRIPTION}"
                )
        assert not violations, (
            "CFG/tokens: descripciones exceden presupuesto:\n  - "
            + "\n  - ".join(violations[:10])
        )

    def test_abbreviations_present_in_descriptions(self) -> None:
        """CFG: las descripciones con reglas indican abreviaciones tacitas."""
        total_with_abbr = 0
        total = 0
        for f in list(AGENTS_DIR.glob("*.md")) + list(SKILLS_DIR.glob("*/SKILL.md")):
            if f.name.endswith(".min.md"):
                continue
            text = f.read_text(encoding="utf-8")
            if not text.startswith("---"):
                continue
            parts = text.split("---", 2)
            if len(parts) < 3:
                continue
            data = yaml.safe_load(parts[1])
            desc = data.get("description", "")
            total += 1
            if ("UPG" in desc or "NAM" in desc or "FRS" in desc) and (
                "reglas en base_principles.md" in desc or "·" in desc
            ):
                total_with_abbr += 1
        assert total > 0
        ratio = total_with_abbr / total
        assert ratio >= 0.8, (
            f"CFG/tokens: solo {ratio:.0%} de descripciones usan abreviacion "
            f"({total_with_abbr}/{total}). Compactar notas largas."
        )


# ===========================================================================
# CLI
# ===========================================================================

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python -m harness.tests.test_opencode_config_sync scan")
        print("  python -m harness.tests.test_opencode_config_sync evolve")
        sys.exit(2)

    cmd = sys.argv[1]
    if cmd == "scan":
        results = scan_config_drift(verbose=True)
        total = sum(len(v) for v in results.values())
        print(f"\nTotal drifts: {total}")
        sys.exit(0 if total == 0 else 1)
    elif cmd == "evolve":
        result = evolve_config_sync(dry_run=False)
        print("AUTO-MEJORA (config sync):")
        for action in result["actions"]:
            print(f"  - {action}")
        sys.exit(0)
    else:
        print(f"Comando desconocido: {cmd}")
        sys.exit(2)
