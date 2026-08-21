"""agent_card — Identidad y descubrimiento de agentes por proyecto (ADR-0058).

Adopta el formato de Agent Card de A2A v1.0 (Linux Foundation, RFC 8615):
cada proyecto publica su card en la URI bien conocida
`.opencode/.well-known/agent-card.json` describiendo qué skills expone a
otros agentes. La card es un contrato: cambios en skills[].id o version son
breaking y exigen bump de versión.

Ejemplo::

    card = load_agent_card(Path("C:/DEV-SPACE/core-quant-engine"))
    print(card.name, [s.id for s in card.skills])
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

#: Nombre canónico del archivo de card (convención A2A/RFC 8615).
AGENT_CARD_FILENAME = "agent-card.json"

#: Directorio well-known dentro del mirror .opencode del proyecto.
WELL_KNOWN_DIR = ".opencode/.well-known"

#: Campos requeridos por el estándar A2A (fuente única de validación).
_REQUIRED_CARD_FIELDS: tuple[str, ...] = (
    "name",
    "description",
    "version",
    "capabilities",
    "default_input_modes",
    "default_output_modes",
)


@dataclass(frozen=True)
class AgentSkill:
    """Skill que un proyecto expone a otros agentes (formato A2A).

    Args:
        id: Identificador estable de la skill (contrato público).
        name: Nombre legible.
        description: Qué hace y cuándo delegarle trabajo.
        tags: Etiquetas de búsqueda/descubrimiento.
    """

    id: str
    name: str
    description: str
    tags: tuple[str, ...] = field(default=())


@dataclass(frozen=True)
class AgentCard:
    """Agent Card A2A de un proyecto del ecosistema.

    Args:
        name: Nombre único del proyecto/agente.
        description: Propósito del agente.
        version: Versión semántica de la card (contrato).
        project_root: Raíz absoluta del proyecto (transporte local).
        skills: Skills expuestas para delegación.
        capabilities: Capacidades declaradas (streaming, push, etc.).
        default_input_modes / default_output_modes: Modos MIME aceptados.
    """

    name: str
    description: str
    version: str
    project_root: Path
    skills: tuple[AgentSkill, ...] = field(default=())
    capabilities: tuple[str, ...] = field(default=())
    default_input_modes: tuple[str, ...] = field(default=("text/plain",))
    default_output_modes: tuple[str, ...] = field(
        default=("text/plain", "application/json")
    )

    def has_skill(self, skill_id: str) -> bool:
        """Indica si la card declara una skill concreta.

        Args:
            skill_id: Identificador de la skill buscada.

        Returns:
            True si la skill está declarada.
        """
        return any(s.id == skill_id for s in self.skills)

    def to_dict(self) -> dict[str, object]:
        """Serializa la card a dict compatible con agent-card.json.

        Returns:
            Dict con todos los campos del contrato.
        """
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "project_root": str(self.project_root),
            "skills": [
                {
                    "id": s.id,
                    "name": s.name,
                    "description": s.description,
                    "tags": list(s.tags),
                }
                for s in self.skills
            ],
            "capabilities": list(self.capabilities),
            "default_input_modes": list(self.default_input_modes),
            "default_output_modes": list(self.default_output_modes),
        }


def card_path(project_root: Path) -> Path:
    """Retorna la ruta canónica de la card de un proyecto.

    Args:
        project_root: Raíz del proyecto.

    Returns:
        Ruta a .opencode/.well-known/agent-card.json.
    """
    return Path(project_root) / WELL_KNOWN_DIR / AGENT_CARD_FILENAME


def _parse_card(data: dict[str, object], source: Path) -> AgentCard:
    """Valida y convierte un dict JSON en AgentCard (fail-fast).

    Args:
        data: Contenido JSON parseado.
        source: Ruta de origen (para mensajes de error).

    Returns:
        AgentCard válida.

    Raises:
        ValueError: si falta un campo requerido o los tipos no cuadran
            (WHAT falta / WHY contrato A2A / WHERE archivo+campo).
    """
    missing = [f for f in _REQUIRED_CARD_FIELDS if f not in data]
    if missing:
        raise ValueError(
            f"ValueError: agent-card en {source} carece de campos requeridos "
            f"{missing}. WHY: el contrato A2A exige esos campos para que "
            "otros agentes puedan descubrir y delegar. WHERE: "
            "agent_card.load_agent_card."
        )
    raw_skills = data.get("skills") or []
    if not isinstance(raw_skills, list):
        raise TypeError(
            f"TypeError: 'skills' en {source} no es una lista. WHY: el "
            "contrato A2A define skills como lista. WHERE: load_agent_card."
        )
    skills = tuple(
        AgentSkill(
            id=str(s.get("id", "")),
            name=str(s.get("name", "")),
            description=str(s.get("description", "")),
            tags=tuple(str(t) for t in s.get("tags", [])),
        )
        for s in raw_skills
        if isinstance(s, dict)
    )
    return AgentCard(
        name=str(data["name"]),
        description=str(data["description"]),
        version=str(data["version"]),
        project_root=Path(str(data.get("project_root", source.parent.parent.parent))),
        skills=skills,
        capabilities=tuple(str(c) for c in data.get("capabilities", [])),
        default_input_modes=tuple(
            str(m) for m in data["default_input_modes"]
        ),
        default_output_modes=tuple(
            str(m) for m in data["default_output_modes"]
        ),
    )


def load_agent_card(project_root: Path) -> AgentCard:
    """Carga y valida la Agent Card de un proyecto.

    Args:
        project_root: Raíz del proyecto.

    Returns:
        AgentCard validada.

    Raises:
        FileNotFoundError: si el proyecto no publica card
            (WHAT no existe / WHY sin card no hay descubrimiento /
            WHERE ruta well-known).
        ValueError: si la card viola el contrato (delegado a _parse_card)
            o el JSON es inválido.
    """
    path = card_path(project_root)
    if not path.is_file():
        raise FileNotFoundError(
            f"FileNotFoundError: no existe agent-card en {path}. WHY: un "
            "proyecto sin card no es descubrible por la federación. WHERE: "
            "agent_card.load_agent_card (ejecute write_agent_card primero)."
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"ValueError: JSON inválido en {path}: {exc}. WHY: la card debe "
            "ser JSON estricto. WHERE: agent_card.load_agent_card."
        ) from exc
    return _parse_card(data, path)


def write_agent_card(card: AgentCard, project_root: Path) -> Path:
    """Publica la card de un proyecto en su URI bien conocida.

    Args:
        card: Card a publicar.
        project_root: Raíz del proyecto destino.

    Returns:
        Ruta del archivo escrito.

    Raises:
        OSError: propagada si no se puede escribir (sin except silencioso).
    """
    path = card_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {**card.to_dict(), "project_root": str(project_root)}
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("agent_card: card publicada en %s", path)
    return path


def discover_cards(projects_root: Path) -> list[AgentCard]:
    """Descubre las cards de todos los proyectos hermanos que publiquen una.

    Args:
        projects_root: Directorio que contiene los proyectos (p. ej.
            DEV-SPACE). Los proyectos sin card se ignoran silenciosamente
            (no publican = no participan; decisión explícita, no error).

    Returns:
        Lista de cards ordenadas por nombre de proyecto.
    """
    root = Path(projects_root)
    cards: list[AgentCard] = []
    if not root.is_dir():
        logger.warning(
            "agent_card: projects_root inexistente %s (WHERE: discover_cards)",
            root,
        )
        return []
    for candidate in sorted(root.iterdir()):
        path = card_path(candidate)
        if path.is_file():
            try:
                cards.append(load_agent_card(candidate))
            except (ValueError, OSError) as exc:
                logger.warning(
                    "agent_card: card inválida en %s: %s (WHERE: discover_cards)",
                    candidate.name, exc,
                )
    return cards
