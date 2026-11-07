"""Gate de enlaces internos de la documentación (README y hubs).

Resuelve enlaces Markdown relativos y rutas raíz de mdbook (`/assets/x` →
`docs/src/<lang>/assets/x`) y falla si el destino no existe. No valida URLs
externas (red/CI flaky): para eso están `canon_audit` y los jobs de enlaces.

Uso:
    python scripts/check_docs_links.py
    python scripts/check_docs_links.py README.md docs/README.md
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent
_LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)")
_SKIP_PREFIXES = ("http://", "https://", "mailto:", "tel:", "#")
DEFAULT_FILES = (
    "README.md",
    "docs/README.md",
    "docs/src/es/README.md",
    "docs/src/es/SUMMARY.md",
    "docs/src/en/README.md",
    "docs/src/en/SUMMARY.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
)


@dataclass(frozen=True)
class BrokenLink:
    """Enlace relativo cuyo destino no existe."""

    source: Path
    line: int
    target: str
    resolved: Path


def iter_links(path: Path) -> list[tuple[int, str]]:
    """Lista (línea, destino) de enlaces Markdown fuera de bloques de código."""
    links: list[tuple[int, str]] = []
    in_fence = False
    for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        links.extend((number, target) for target in _LINK.findall(line))
    return links


def _base_dir(path: Path) -> Path:
    """Directorio base para resolver rutas mdbook (``/x``) o relativas."""
    parts = path.resolve().parts
    if "docs" in parts and "src" in parts:
        index = parts.index("src")
        if index + 1 < len(parts):
            return Path(*parts[: index + 2])
    return path.parent


def resolve(path: Path, target: str) -> Path:
    """Resuelve un destino interno (relativo o raíz mdbook) a ruta absoluta."""
    clean = unquote(target.split("#", 1)[0].split("?", 1)[0])
    if clean.startswith("/"):
        return (_base_dir(path) / clean.lstrip("/")).resolve()
    return (path.parent / clean).resolve()


def check_files(paths: list[Path]) -> list[BrokenLink]:
    """Devuelve los enlaces internos rotos de ``paths`` existentes."""
    broken: list[BrokenLink] = []
    for path in paths:
        if not path.is_file():
            continue
        broken.extend(
            BrokenLink(path, line, target, resolve(path, target))
            for line, target in iter_links(path)
            if not target.startswith(_SKIP_PREFIXES)
            and not target.startswith(("{{", "<"))
            and not resolve(path, target).exists()
        )
    return broken


def default_paths() -> list[Path]:
    """Ficheros de fachada que el gate valida por defecto."""
    return [ROOT / name for name in DEFAULT_FILES]


def main(argv: list[str] | None = None) -> int:
    """CLI: exit 1 si hay enlaces internos rotos."""
    parser = argparse.ArgumentParser(description="Verifica enlaces internos de docs")
    parser.add_argument("paths", nargs="*", help="Markdown a revisar (default: fachada)")
    args = parser.parse_args(argv)
    paths = [Path(item) for item in args.paths] if args.paths else default_paths()
    broken = check_files(paths)
    for item in broken:
        try:
            shown = item.resolved.relative_to(ROOT)
        except ValueError:
            shown = item.resolved
        print(f"{item.source.relative_to(ROOT)}:{item.line}: {item.target} -> {shown}")
    print(f"enlaces rotos: {len(broken)} en {len(paths)} archivo(s)")
    return 1 if broken else 0


if __name__ == "__main__":
    raise SystemExit(main())
