"""
Swarmind BRIDGE SYNC
===================
Script de sincronización entre shared_memory y Swarmind Harness.

Uso:
    python scripts/Swarmind_bridge_sync.py          # Sync bidireccional completo
    python scripts/Swarmind_bridge_sync.py --status  # Solo estado
    python scripts/Swarmind_bridge_sync.py --to-hermes   # Swarmind → Hermes
    python scripts/Swarmind_bridge_sync.py --to-Swarmind  # Hermes → Swarmind
"""

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Rutas
HERMES_PATH = Path(__file__).resolve().parent.parent
Swarmind_PATH = Path(os.environ.get(
    "Swarmind_PATH",
    r"$HOME\Documents\DEV-SPACE\Swarmind",
))


def check_status() -> dict:
    """Verifica el estado de la sincronización."""
    status = {
        "timestamp": datetime.now().isoformat(),
        "hermes_path": str(HERMES_PATH),
        "hermes_exists": HERMES_PATH.exists(),
        "Swarmind_path": str(Swarmind_PATH),
        "Swarmind_exists": Swarmind_PATH.exists(),
        "hermes_brain": (HERMES_PATH / "99_Hermes_Brain").exists(),
        "Swarmind_harness": (Swarmind_PATH / "harness").exists(),
    }

    # Contar conocimiento
    knowledge_dir = HERMES_PATH / "knowledge" / "Swarmind_bridge"
    status["knowledge_files"] = len(list(knowledge_dir.glob("*.json"))) if knowledge_dir.exists() else 0

    # Contar skills
    skills_dir = HERMES_PATH / "skills" / "Swarmind_bridge"
    status["skill_dirs"] = len([d for d in skills_dir.iterdir() if d.is_dir()]) if skills_dir.exists() else 0

    return status


def sync_hermes_to_Swarmind() -> int:
    """Sincroniza Hermes → Swarmind: escribe conocimiento de Hermes en formato Swarmind.

    Returns:
        Cantidad de archivos sincronizados.
    """
    count = 0

    # 1. Conocimiento personal → Federated Memory de Swarmind
    hermes_knowledge = HERMES_PATH / "knowledge"
    Swarmind_federated = Swarmind_PATH / ".opencode" / "federated"

    if hermes_knowledge.exists() and Swarmind_federated.exists():
        target = Swarmind_federated / "hermes_knowledge"
        target.mkdir(parents=True, exist_ok=True)

        for fpath in hermes_knowledge.rglob("*.md"):
            if fpath.is_file():
                content = fpath.read_text(encoding="utf-8")
                record = {
                    "id": f"hermes:knowledge:{fpath.relative_to(hermes_knowledge)}",
                    "type": "knowledge",
                    "source_project": "shared_memory",
                    "source_agent": "hermes",
                    "key": str(fpath.relative_to(hermes_knowledge)),
                    "value": content[:2000],
                    "tags": ["hermes", "knowledge"],
                    "confidence": 0.8,
                    "created_at": datetime.now().isoformat(),
                }
                safe_name = str(fpath.relative_to(hermes_knowledge)).replace("\\", "_").replace("/", "_")
                out_path = target / f"{safe_name}.json"
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(record, f, indent=2, ensure_ascii=False)
                count += 1

    # 2. Skills de Hermes → Skills de Swarmind
    hermes_skills = HERMES_PATH / "skills"
    Swarmind_skills = Swarmind_PATH / ".opencode" / "skills"

    if hermes_skills.exists() and Swarmind_skills.exists():
        for skill_dir in hermes_skills.iterdir():
            if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
                target = Swarmind_skills / skill_dir.name
                target.mkdir(parents=True, exist_ok=True)
                content = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
                (target / "SKILL.md").write_text(content, encoding="utf-8")
                count += 1

    logger.info(f"Hermes → Swarmind: {count} archivos sincronizados")
    return count


def sync_Swarmind_to_hermes() -> int:
    """Sincroniza Swarmind → Hermes: lee conocimiento de Swarmind y lo almacena en Hermes.

    Returns:
        Cantidad de archivos sincronizados.
    """
    count = 0

    # 1. Federated Memory de Swarmind → conocimiento de Hermes
    Swarmind_federated = Swarmind_PATH / ".opencode" / "federated"
    hermes_bridge_knowledge = HERMES_PATH / "knowledge" / "Swarmind_bridge"

    if Swarmind_federated.exists():
        hermes_bridge_knowledge.mkdir(parents=True, exist_ok=True)

        for fpath in Swarmind_federated.rglob("*.json"):
            try:
                data = json.loads(fpath.read_text(encoding="utf-8"))
                records = data.get("records", [data] if isinstance(data, dict) else [])
                for record in records:
                    key = record.get("key", record.get("id", fpath.stem))
                    safe_name = key.replace(":", "_").replace("/", "_").replace(" ", "_")
                    out_path = hermes_bridge_knowledge / f"{safe_name}.json"
                    with open(out_path, "w", encoding="utf-8") as f:
                        json.dump(record, f, indent=2, ensure_ascii=False)
                    count += 1
            except (json.JSONDecodeError, OSError):
                continue

    # 2. Skills de Swarmind → Skills de Hermes
    Swarmind_skills = Swarmind_PATH / ".opencode" / "skills"
    hermes_skills_bridge = HERMES_PATH / "skills" / "Swarmind_bridge"

    if Swarmind_skills.exists():
        hermes_skills_bridge.mkdir(parents=True, exist_ok=True)
        for skill_dir in Swarmind_skills.iterdir():
            if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
                target = hermes_skills_bridge / skill_dir.name
                target.mkdir(parents=True, exist_ok=True)
                content = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
                (target / "SKILL.md").write_text(content, encoding="utf-8")
                count += 1

    logger.info(f"Swarmind → Hermes: {count} archivos sincronizados")
    return count


def sync_full() -> dict:
    """Sincronización bidireccional completa."""
    logger.info("=" * 60)
    logger.info("Swarmind BRIDGE — SINCRONIZACIÓN COMPLETA")
    logger.info("=" * 60)
    logger.info(f"Hermes: {HERMES_PATH}")
    logger.info(f"Swarmind: {Swarmind_PATH}")
    logger.info("")

    to_Swarmind = sync_hermes_to_Swarmind()
    to_hermes = sync_Swarmind_to_hermes()

    result = {
        "timestamp": datetime.now().isoformat(),
        "hermes_to_Swarmind": to_Swarmind,
        "Swarmind_to_hermes": to_hermes,
        "total": to_Swarmind + to_hermes,
    }

    logger.info("")
    logger.info(f"Total sincronizado: {result['total']} archivos")
    logger.info("=" * 60)

    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Swarmind Bridge Sync")
    parser.add_argument("--status", action="store_true", help="Mostrar estado")
    parser.add_argument("--to-hermes", action="store_true", help="Swarmind → Hermes")
    parser.add_argument("--to-Swarmind", action="store_true", help="Hermes → Swarmind")

    args = parser.parse_args()

    if args.status:
        s = check_status()
        print(json.dumps(s, indent=2))
    elif args.to_hermes:
        sync_Swarmind_to_hermes()
    elif args.to_Swarmind:
        sync_hermes_to_Swarmind()
    else:
        sync_full()
