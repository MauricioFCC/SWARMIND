"""Genera los índices de agentes y skills desde la SSOT (anti-drift de docs).

Los catálogos de `docs/src/es/agents/INDEX.md` y `docs/src/es/skills/INDEX.md`
se derivan de `.opencode/agents/*.md` y `.opencode/skills/skills_registry.yaml`.
Así el visitante ve conteos reales y el mantenedor no actualiza listas a mano.

Uso:
    python scripts/gen_docs_index.py --write   # regenera los índices
    python scripts/gen_docs_index.py --check   # falla si hay drift
"""

from __future__ import annotations

import argparse
import operator
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = ROOT / ".opencode" / "agents"
REGISTRY = ROOT / ".opencode" / "skills" / "skills_registry.yaml"
OUT_AGENTS = ROOT / "docs" / "src" / "es" / "agents" / "INDEX.md"
OUT_SKILLS = ROOT / "docs" / "src" / "es" / "skills" / "INDEX.md"
REPO_URL = "https://github.com/MauricioFCC/SWARMIND/blob/main"
MAX_ROLE = 120
_MARKER = "<!-- generado por scripts/gen_docs_index.py -->"


def _frontmatter(path: Path) -> dict[str, object]:
    """Frontmatter YAML de un Markdown (vacío si no tiene)."""
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    data = yaml.safe_load(parts[1])
    return data if isinstance(data, dict) else {}


def _short(text: object, limit: int = MAX_ROLE) -> str:
    """Primera frase de una descripción, acotada a ``limit`` caracteres."""
    value = str(text or "").strip().split(" | ")[0]
    value = value.split("Alcance:")[0].strip().rstrip(".")
    if len(value) <= limit:
        return value
    return value[: limit - 1].rsplit(" ", 1)[0] + "…"


def _agents() -> list[dict[str, str]]:
    """Agentes reales (sin `.min.md`) con nombre, dominio y rol."""
    rows: list[dict[str, str]] = []
    for path in sorted(AGENTS_DIR.glob("*.md")):
        if path.name.endswith(".min.md"):
            continue
        meta = _frontmatter(path)
        rows.append(
            {
                "name": str(meta.get("name") or path.stem),
                "domain": str(meta.get("domain") or "general"),
                "role": _short(meta.get("description")),
                "source": f"{REPO_URL}/.opencode/agents/{path.name}",
            }
        )
    return rows


def _skills() -> list[dict[str, str]]:
    """Skills del registry con dominio, disparador y fuente."""
    data = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    rows: list[dict[str, str]] = []
    for item in data.get("skills", []):
        name = str(item.get("name", ""))
        if not name:
            continue
        rows.append(
            {
                "name": name,
                "domain": str(item.get("domain") or "general"),
                "role": _short(item.get("description")),
                "source": f"{REPO_URL}/.opencode/skills/{name}/SKILL.md",
            }
        )
    return sorted(rows, key=operator.itemgetter("domain", "name"))


def render_agents(rows: list[dict[str, str]]) -> str:
    """Markdown del índice de agentes."""
    lines = [
        "# Agentes",
        "",
        _MARKER,
        "",
        f"**{len(rows)} agentes** definidos en `.opencode/agents/`. El contenido es",
        "la SSOT; este índice solo lista nombre, dominio y rol.",
        "",
        "| Agente | Dominio | Rol | Fuente |",
        "|---|---|---|---|",
    ]
    lines.extend(
        f"| `{row['name']}` | {row['domain']} | {row['role']} | "
        f"[agent]({row['source']}) |"
        for row in rows
    )
    lines += ["", "Regenerar: `python scripts/gen_docs_index.py --write`.", ""]
    return "\n".join(lines)


def render_skills(rows: list[dict[str, str]]) -> str:
    """Markdown del índice de skills."""
    lines = [
        "# Skills",
        "",
        _MARKER,
        "",
        f"**{len(rows)} skills** registradas en `.opencode/skills/skills_registry.yaml`.",
        "Cada una tiene `SKILL.md` (procedimiento) y `SKILL.min.md` (N1).",
        "",
        "| Skill | Dominio | Cuándo usarla | Fuente |",
        "|---|---|---|---|",
    ]
    lines.extend(
        f"| `{row['name']}` | {row['domain']} | {row['role']} | "
        f"[skill]({row['source']}) |"
        for row in rows
    )
    lines += ["", "Regenerar: `python scripts/gen_docs_index.py --write`.", ""]
    return "\n".join(lines)


def build_indexes() -> dict[Path, str]:
    """Contenido esperado de ambos índices (sin escribir)."""
    return {
        OUT_AGENTS: render_agents(_agents()),
        OUT_SKILLS: render_skills(_skills()),
    }


def _sync(write: bool) -> int:
    """Escribe o compara los índices; devuelve nº de archivos desactualizados."""
    stale = 0
    for path, content in build_indexes().items():
        current = path.read_text(encoding="utf-8") if path.is_file() else ""
        if current == content:
            continue
        stale += 1
        if write:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
    return stale


def main(argv: list[str] | None = None) -> int:
    """CLI: `--write` regenera; `--check` falla si hay drift."""
    parser = argparse.ArgumentParser(description="Genera índices de agentes/skills")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    stale = _sync(write=args.write)
    if args.check and stale:
        print(f"DRIFT: {stale} índice(s) desactualizados; usa --write", file=sys.stderr)
        return 1
    print(f"{len(build_indexes())} índices | {stale} cambios")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
