"""
AGENTIC BRIDGE SYNC
===================
Script de sincronización entre Hermes_Memory_Proyects y Agentic Harness.

Uso:
    python scripts/agentic_bridge_sync.py          # Sync bidireccional completo
    python scripts/agentic_bridge_sync.py --status  # Solo estado
    python scripts/agentic_bridge_sync.py --to-hermes   # Agentic → Hermes
    python scripts/agentic_bridge_sync.py --to-agentic  # Hermes → Agentic
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
AGENTIC_PATH = Path(os.environ.get(
    "AGENTIC_PATH",
    r"C:\Users\USUARIO\Documents\DEV-SPACE\AGENTIC",
))


def check_status() -> dict:
    """Verifica el estado de la sincronización."""
    status = {
        "timestamp": datetime.now().isoformat(),
        "hermes_path": str(HERMES_PATH),
        "hermes_exists": HERMES_PATH.exists(),
        "agentic_path": str(AGENTIC_PATH),
        "agentic_exists": AGENTIC_PATH.exists(),
        "hermes_brain": (HERMES_PATH / "99_Hermes_Brain").exists(),
        "agentic_harness": (AGENTIC_PATH / "harness").exists(),
    }

    # Contar conocimiento
    knowledge_dir = HERMES_PATH / "knowledge" / "agentic_bridge"
    status["knowledge_files"] = len(list(knowledge_dir.glob("*.json"))) if knowledge_dir.exists() else 0

    # Contar skills
    skills_dir = HERMES_PATH / "skills" / "agentic_bridge"
    status["skill_dirs"] = len([d for d in skills_dir.iterdir() if d.is_dir()]) if skills_dir.exists() else 0

    return status


def sync_hermes_to_agentic() -> int:
    """Sincroniza Hermes → Agentic: escribe conocimiento de Hermes en formato Agentic.

    Returns:
        Cantidad de archivos sincronizados.
    """
    count = 0

    # 1. Conocimiento personal → Federated Memory de Agentic
    hermes_knowledge = HERMES_PATH / "knowledge"
    agentic_federated = AGENTIC_PATH / ".opencode" / "federated"

    if hermes_knowledge.exists() and agentic_federated.exists():
        target = agentic_federated / "hermes_knowledge"
        target.mkdir(parents=True, exist_ok=True)

        for fpath in hermes_knowledge.rglob("*.md"):
            if fpath.is_file():
                content = fpath.read_text(encoding="utf-8")
                record = {
                    "id": f"hermes:knowledge:{fpath.relative_to(hermes_knowledge)}",
                    "type": "knowledge",
                    "source_project": "Hermes_Memory_Proyects",
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

    # 2. Skills de Hermes → Skills de Agentic
    hermes_skills = HERMES_PATH / "skills"
    agentic_skills = AGENTIC_PATH / ".opencode" / "skills"

    if hermes_skills.exists() and agentic_skills.exists():
        for skill_dir in hermes_skills.iterdir():
            if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
                target = agentic_skills / skill_dir.name
                target.mkdir(parents=True, exist_ok=True)
                content = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
                (target / "SKILL.md").write_text(content, encoding="utf-8")
                count += 1

    logger.info(f"Hermes → Agentic: {count} archivos sincronizados")
    return count


def sync_agentic_to_hermes() -> int:
    """Sincroniza Agentic → Hermes: lee conocimiento de Agentic y lo almacena en Hermes.

    Returns:
        Cantidad de archivos sincronizados.
    """
    count = 0

    # 1. Federated Memory de Agentic → conocimiento de Hermes
    agentic_federated = AGENTIC_PATH / ".opencode" / "federated"
    hermes_bridge_knowledge = HERMES_PATH / "knowledge" / "agentic_bridge"

    if agentic_federated.exists():
        hermes_bridge_knowledge.mkdir(parents=True, exist_ok=True)

        for fpath in agentic_federated.rglob("*.json"):
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

    # 2. Skills de Agentic → Skills de Hermes
    agentic_skills = AGENTIC_PATH / ".opencode" / "skills"
    hermes_skills_bridge = HERMES_PATH / "skills" / "agentic_bridge"

    if agentic_skills.exists():
        hermes_skills_bridge.mkdir(parents=True, exist_ok=True)
        for skill_dir in agentic_skills.iterdir():
            if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
                target = hermes_skills_bridge / skill_dir.name
                target.mkdir(parents=True, exist_ok=True)
                content = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
                (target / "SKILL.md").write_text(content, encoding="utf-8")
                count += 1

    logger.info(f"Agentic → Hermes: {count} archivos sincronizados")
    return count


def sync_full() -> dict:
    """Sincronización bidireccional completa."""
    logger.info("=" * 60)
    logger.info("AGENTIC BRIDGE — SINCRONIZACIÓN COMPLETA")
    logger.info("=" * 60)
    logger.info(f"Hermes: {HERMES_PATH}")
    logger.info(f"Agentic: {AGENTIC_PATH}")
    logger.info("")

    to_agentic = sync_hermes_to_agentic()
    to_hermes = sync_agentic_to_hermes()

    result = {
        "timestamp": datetime.now().isoformat(),
        "hermes_to_agentic": to_agentic,
        "agentic_to_hermes": to_hermes,
        "total": to_agentic + to_hermes,
    }

    logger.info("")
    logger.info(f"Total sincronizado: {result['total']} archivos")
    logger.info("=" * 60)

    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Agentic Bridge Sync")
    parser.add_argument("--status", action="store_true", help="Mostrar estado")
    parser.add_argument("--to-hermes", action="store_true", help="Agentic → Hermes")
    parser.add_argument("--to-agentic", action="store_true", help="Hermes → Agentic")

    args = parser.parse_args()

    if args.status:
        s = check_status()
        print(json.dumps(s, indent=2))
    elif args.to_hermes:
        sync_agentic_to_hermes()
    elif args.to_agentic:
        sync_hermes_to_agentic()
    else:
        sync_full()
