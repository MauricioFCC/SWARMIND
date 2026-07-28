"""Tests de validacion de archivos de agentes .md.

Verifica que todos los agentes en .opencode/agents/ tengan:
- Frontmatter YAML valido
- Campos obligatorios presentes
- Formato correcto
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest
import yaml

# Ruta base del proyecto
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
AGENTS_DIR = PROJECT_ROOT / ".opencode" / "agents"

# Campos obligatorios del frontmatter YAML de cada agente
REQUIRED_FIELDS = {"name", "domain", "triggers", "capabilities", "aliases", "description"}

# Agentes existentes con frontmatter simplificado (sin domain/capabilities/aliases)
SIMPLE_AGENTS = {"evolve-analyzer", "evolve-engineer", "evolve-researcher"}

# Dominios validos conocidos
VALID_DOMAINS = {
    "universal",
    "research",
    "quality",
    "architecture",
    "devops",
    "data",
    "security",
    "self-improvement",
}

# Agentes nuevos que deben existir
NEW_AGENTS = [
    "researcher",
    "reviewer",
    "architect",
    "devops",
    "data-engineer",
    "security-engineer",
]

# Agentes existentes que no deben eliminarse
EXISTING_AGENTS = [
    "builder",
    "coordinator",
    "guardian",
    "scientist",
    "evolve",
    "evolve-analyzer",
    "evolve-engineer",
    "evolve-researcher",
]


# ============================================================================
# Helpers
# ============================================================================


def _get_agent_files() -> List[Path]:
    """Retorna lista de archivos .md de agentes (excluye .min.md).

    Returns:
        Lista de Paths a archivos de agente.
    """
    files = []
    for f in AGENTS_DIR.glob("*.md"):
        # Excluir archivos .min.md y .gitkeep
        if f.name.endswith(".min.md") or f.name == ".gitkeep":
            continue
        files.append(f)
    return sorted(files)


def _parse_frontmatter(filepath: Path) -> Optional[Dict[str, Any]]:
    """Extrae y parsea el frontmatter YAML de un archivo de agente.

    Args:
        filepath: Ruta al archivo .md del agente.

    Returns:
        Dict con el frontmatter parseado, o None si no tiene frontmatter valido.

    Raises:
        yaml.YAMLError: Si el YAML del frontmatter es invalido.
    """
    content = filepath.read_text(encoding="utf-8")
    if not content.startswith("---"):
        return None

    # Encontrar el segundo ---
    second_delim = content.find("---", 3)
    if second_delim == -1:
        return None

    yaml_content = content[3:second_delim]
    return yaml.safe_load(yaml_content)


def _validate_agent_file(filepath: Path) -> Dict[str, Any]:
    """Valida un archivo de agente individual.

    Args:
        filepath: Ruta al archivo .md del agente.

    Returns:
        Dict con resultados: valido (bool), errores (list), advertencias (list).

    Raises:
        IOError: Si no se puede leer el archivo.
    """
    result = {
        "valido": True,
        "errores": [],
        "advertencias": [],
        "frontmatter": None,
    }

    try:
        frontmatter = _parse_frontmatter(filepath)
    except yaml.YAMLError as e:
        result["valido"] = False
        result["errores"].append(f"Error parseando YAML: {e}")
        return result

    if frontmatter is None:
        result["valido"] = False
        result["errores"].append("No tiene frontmatter YAML (debe empezar con ---)")
        return result

    result["frontmatter"] = frontmatter

    # Agentes con frontmatter simplificado (solo name + role + description + triggers)
    agent_name = frontmatter.get("name", "")
    is_simple = agent_name in SIMPLE_AGENTS

    # Verificar campos obligatorios
    required = REQUIRED_FIELDS if not is_simple else {"name"}
    for field in required:
        if field not in frontmatter:
            result["valido"] = False
            result["errores"].append(f"Campo obligatorio faltante: '{field}'")

    # Verificar que los campos no esten vacios
    for field in ["name", "domain"]:
        if field in frontmatter and not frontmatter[field]:
            result["valido"] = False
            result["errores"].append(f"Campo '{field}' esta vacio")

    # Verificar domain valido
    domain = frontmatter.get("domain", "")
    if domain and domain not in VALID_DOMAINS:
        result["advertencias"].append(
            f"Dominio '{domain}' no esta en dominios conocidos: {sorted(VALID_DOMAINS)}",
        )

    # Verificar triggers (debe ser lista no vacia)
    triggers = frontmatter.get("triggers", [])
    if not isinstance(triggers, list):
        result["valido"] = False
        result["errores"].append("'triggers' debe ser una lista")
    elif len(triggers) == 0:
        result["advertencias"].append("'triggers' esta vacio")

    # Verificar capabilities (debe ser lista no vacia)
    capabilities = frontmatter.get("capabilities", [])
    if not isinstance(capabilities, list):
        result["valido"] = False
        result["errores"].append("'capabilities' debe ser una lista")
    elif len(capabilities) == 0:
        result["advertencias"].append("'capabilities' esta vacio")

    # Verificar aliases (debe ser lista no vacia)
    aliases = frontmatter.get("aliases", [])
    if not isinstance(aliases, list):
        result["valido"] = False
        result["errores"].append("'aliases' debe ser una lista")
    elif len(aliases) == 0:
        result["advertencias"].append("'aliases' esta vacio")

    # Verificar description (debe ser string no vacio)
    description = frontmatter.get("description", "")
    if not description or not isinstance(description, str):
        result["valido"] = False
        result["errores"].append("'description' debe ser un string no vacio")

    return result


# ============================================================================
# Tests
# ============================================================================


class TestAgentFilesExist:
    """Verifica que los archivos de agente existen."""

    def test_agents_directory_exists(self) -> None:
        """El directorio de agentes debe existir.

        Returns:
            None. Asserts que el directorio existe.
        """
        assert AGENTS_DIR.exists(), f"Directorio de agentes no encontrado: {AGENTS_DIR}"
        assert AGENTS_DIR.is_dir()

    def test_new_agents_exist(self) -> None:
        """Verifica que los 6 nuevos agentes fueron creados.

        Returns:
            None. Asserts que cada archivo de agente existe.
        """
        missing = []
        for agent_name in NEW_AGENTS:
            agent_file = AGENTS_DIR / f"{agent_name}.md"
            if not agent_file.exists():
                missing.append(agent_name)
        assert not missing, f"Faltan archivos de agente: {missing}"

    def test_existing_agents_preserved(self) -> None:
        """Verifica que los agentes existentes no fueron eliminados.

        Returns:
            None. Asserts que los agentes originales existen.
        """
        missing = []
        for agent_name in EXISTING_AGENTS:
            agent_file = AGENTS_DIR / f"{agent_name}.md"
            if not agent_file.exists():
                missing.append(agent_name)
        assert not missing, f"Faltan archivos de agentes existentes: {missing}"

    def test_all_agents_count(self) -> None:
        """Verifica que hay al menos 14 agentes (8 existentes + 6 nuevos).

        Returns:
            None. Asserts que hay al menos 14 archivos de agente.
        """
        agent_files = _get_agent_files()
        assert (
            len(agent_files) >= 14
        ), f"Solo se encontraron {len(agent_files)} agentes, se esperaban al menos 14"


class TestAgentFrontmatter:
    """Verifica que todos los archivos de agente tienen frontmatter valido."""

    @pytest.mark.parametrize("agent_name", NEW_AGENTS)
    def test_new_agent_frontmatter(self, agent_name: str) -> None:
        """Verifica frontmatter de cada nuevo agente.

        Args:
            agent_name: Nombre del agente a verificar.

        Returns:
            None. Asserts que el frontmatter es valido.
        """
        agent_file = AGENTS_DIR / f"{agent_name}.md"
        assert agent_file.exists(), f"Archivo {agent_name}.md no encontrado"

        result = _validate_agent_file(agent_file)
        assert result["valido"], (
            f"Agente '{agent_name}' tiene errores de frontmatter:\n"
            + "\n".join(f"  - {e}" for e in result["errores"])
        )

    @pytest.mark.parametrize("agent_name", NEW_AGENTS)
    def test_new_agent_required_fields(self, agent_name: str) -> None:
        """Verifica campos obligatorios especificos de cada nuevo agente.

        Args:
            agent_name: Nombre del agente.

        Returns:
            None. Asserts que todos los campos requeridos existen.
        """
        agent_file = AGENTS_DIR / f"{agent_name}.md"
        frontmatter = _parse_frontmatter(agent_file)
        assert frontmatter is not None, f"No se pudo parsear frontmatter de {agent_name}"

        # Verificar name coincide con el nombre del agente
        assert frontmatter.get("name") == agent_name, (
            f"El campo 'name' debe ser '{agent_name}', "
            f"pero es '{frontmatter.get('name')}'"
        )

        # Verificar que triggers contiene al menos el nombre del agente
        triggers: list = frontmatter.get("triggers", [])
        assert isinstance(triggers, list), "'triggers' debe ser una lista"

        # Verificar que capabilities es una lista no vacia
        capabilities: list = frontmatter.get("capabilities", [])
        assert isinstance(capabilities, list)
        assert len(capabilities) > 0, f"'capabilities' vacio en {agent_name}"

        # Verificar que aliases contiene el nombre del agente
        aliases: list = frontmatter.get("aliases", [])
        assert isinstance(aliases, list)
        assert any(
            agent_name in alias for alias in aliases
        ), f"'aliases' debe contener '{agent_name}', tiene {aliases}"

    @pytest.mark.parametrize("agent_name", NEW_AGENTS + EXISTING_AGENTS)
    def test_agent_file_readable_utf8(self, agent_name: str) -> None:
        """Verifica que los archivos de agente son legibles en UTF-8.

        Args:
            agent_name: Nombre del agente.

        Returns:
            None. Asserts que el archivo se lee correctamente.
        """
        agent_file = AGENTS_DIR / f"{agent_name}.md"
        assert agent_file.exists()
        content = agent_file.read_text(encoding="utf-8")
        assert len(content) > 0, f"Archivo {agent_name}.md esta vacio"
        # Verificar que tiene contenido UTF-8 (caracteres no-ASCII, ej: acentos, e?es, em dash)
        has_utf8 = any(ord(c) > 127 for c in content)
        assert has_utf8, (
            f"Archivo {agent_name}.md no contiene caracteres UTF-8 (todo ASCII)"
        )


class TestAllAgentsValid:
    """Tests de validacion completa de todos los agentes."""

    def test_all_agents_frontmatter_valid(self) -> None:
        """Todos los archivos de agente deben tener frontmatter valido.

        Returns:
            None. Asserts que todos los agentes son validos.
        """
        errors = []
        for agent_file in _get_agent_files():
            result = _validate_agent_file(agent_file)
            if not result["valido"]:
                for error in result["errores"]:
                    errors.append(f"{agent_file.name}: {error}")

        assert not errors, (
            "Errores de frontmatter encontrados:\n" + "\n".join(f"  - {e}" for e in errors)
        )

    def test_all_agents_have_description(self) -> None:
        """Todos los agentes deben tener descripcion no vacia.

        Returns:
            None. Asserts que todos tienen description.
        """
        empty_desc = []
        for agent_file in _get_agent_files():
            frontmatter = _parse_frontmatter(agent_file)
            if frontmatter is None:
                empty_desc.append(f"{agent_file.name}: sin frontmatter")
            elif not frontmatter.get("description", ""):
                empty_desc.append(f"{agent_file.name}: description vacia")

        assert not empty_desc, (
            "Agentes con description vacia:\n" + "\n".join(f"  - {e}" for e in empty_desc)
        )

    def test_no_duplicate_names(self) -> None:
        """No debe haber dos agentes con el mismo nombre.

        Returns:
            None. Asserts que los nombres son unicos.
        """
        names = []
        duplicates = []
        for agent_file in _get_agent_files():
            frontmatter = _parse_frontmatter(agent_file)
            if frontmatter and "name" in frontmatter:
                name = frontmatter["name"]
                if name in names:
                    duplicates.append(name)
                names.append(name)

        assert not duplicates, f"Nombres de agente duplicados: {duplicates}"


# ============================================================================
# Test de agentes especificos (nuevos)
# ============================================================================


class TestResearcherAgent:
    """Tests especificos para el agente researcher."""

    def test_researcher_has_literature_review_capability(self) -> None:
        """researcher debe tener capacidad literature_review.

        Returns:
            None. Asserts que tiene la capacidad.
        """
        agent_file = AGENTS_DIR / "researcher.md"
        frontmatter = _parse_frontmatter(agent_file)
        assert frontmatter is not None
        caps: list = frontmatter.get("capabilities", [])
        assert "literature_review" in caps, "researcher debe tener literature_review"


class TestReviewerAgent:
    """Tests especificos para el agente reviewer."""

    def test_reviewer_has_code_review_capability(self) -> None:
        """reviewer debe tener capacidad code_review.

        Returns:
            None. Asserts que tiene la capacidad.
        """
        agent_file = AGENTS_DIR / "reviewer.md"
        frontmatter = _parse_frontmatter(agent_file)
        assert frontmatter is not None
        caps: list = frontmatter.get("capabilities", [])
        assert "code_review" in caps, "reviewer debe tener code_review"


class TestArchitectAgent:
    """Tests especificos para el agente architect."""

    def test_architect_has_c4_modeling_capability(self) -> None:
        """architect debe tener capacidad c4_modeling.

        Returns:
            None. Asserts que tiene la capacidad.
        """
        agent_file = AGENTS_DIR / "architect.md"
        frontmatter = _parse_frontmatter(agent_file)
        assert frontmatter is not None
        caps: list = frontmatter.get("capabilities", [])
        assert "c4_modeling" in caps, "architect debe tener c4_modeling"


class TestDevOpsAgent:
    """Tests especificos para el agente devops."""

    def test_devops_has_ci_cd_capability(self) -> None:
        """devops debe tener capacidad ci_cd.

        Returns:
            None. Asserts que tiene la capacidad.
        """
        agent_file = AGENTS_DIR / "devops.md"
        frontmatter = _parse_frontmatter(agent_file)
        assert frontmatter is not None
        caps: list = frontmatter.get("capabilities", [])
        assert "ci_cd" in caps, "devops debe tener ci_cd"


class TestDataEngineerAgent:
    """Tests especificos para el agente data-engineer."""

    def test_data_engineer_has_etl_capability(self) -> None:
        """data-engineer debe tener capacidad etl_elt o data_pipeline.

        Returns:
            None. Asserts que tiene la capacidad.
        """
        agent_file = AGENTS_DIR / "data-engineer.md"
        frontmatter = _parse_frontmatter(agent_file)
        assert frontmatter is not None
        caps: list = frontmatter.get("capabilities", [])
        has_etl = any("etl" in c for c in caps)
        assert has_etl, f"data-engineer debe tener capacidad ETL, tiene: {caps}"


class TestSecurityEngineerAgent:
    """Tests especificos para el agente security-engineer."""

    def test_security_engineer_has_security_audit_capability(self) -> None:
        """security-engineer debe tener capacidad security_audit.

        Returns:
            None. Asserts que tiene la capacidad.
        """
        agent_file = AGENTS_DIR / "security-engineer.md"
        frontmatter = _parse_frontmatter(agent_file)
        assert frontmatter is not None
        caps: list = frontmatter.get("capabilities", [])
        assert "security_audit" in caps, "security-engineer debe tener security_audit"
