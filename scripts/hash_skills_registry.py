"""hash_skills_registry.py — Calcula y persiste digests sha256 de skills (FR-D1, ADR-0103).

Supply-chain hardening (SkillsMP / CVE-2025-59536): las skills pueden traer
scripts ejecutables sin revision; el registry debe declarar un digest de
integridad para detectar *content drift* (modificacion silenciosa de una skill).

El digest cubre, en orden canonico:
    SKILL.md  ->  SKILL.min.md  ->  scripts/** (ordenado por ruta relativa POSIX)

Se usa ``hashlib.sha256(usedforsecurity=False)`` (PEP 552): digest de integridad
de archivos, NO criptografico -> evita el hallazgo bandit B324.

La actualizacion del registry es aditiva y NO reordena entradas: solo agrega o
actualiza la linea ``sha256:`` dentro del bloque de cada skill. Idempotente.

CLI:
    python scripts/hash_skills_registry.py --dry-run   # muestra cambios, no escribe
    python scripts/hash_skills_registry.py --write     # escribe sha256 en el registry
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Rutas y constantes (MAG)
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parent.parent
_SKILLS_DIR = _ROOT / ".opencode" / "skills"
_REGISTRY = _SKILLS_DIR / "skills_registry.yaml"

# Orden canonico de archivos raiz de una skill (antes de scripts/).
_CANONICAL_FILES = ("SKILL.md", "SKILL.min.md")
_SCRIPTS_DIRNAME = "scripts"
_INDENT = "    "

# Entrada del registry: "  - name: <skill>"
_ENTRY_RE = re.compile(r"^  - name:\s*(\S+)\s*$")
# Linea de digest: "    sha256: <hex>"
_SHA_LINE_RE = re.compile(r"^(\s+)sha256:\s*(\S+)\s*$")


def compute_skill_digest(skill_dir: Path) -> str:
    """Calcula el sha256 canonico de una skill.

    Orden canonico: ``SKILL.md``, ``SKILL.min.md`` y, si existe ``scripts/``,
    todos sus archivos ordenados por ruta relativa POSIX. Cada archivo aporta
    su ruta relativa (separacion de dominio) + sus bytes.

    Args:
        skill_dir: Directorio raiz de la skill.

    Returns:
        Digest hexadecimal sha256 (64 caracteres). Si la skill no tiene
        archivos canonicos, retorna el digest del stream vacio.
    """
    files: list[Path] = []
    for fname in _CANONICAL_FILES:
        candidate = skill_dir / fname
        if candidate.is_file():
            files.append(candidate)
    scripts_dir = skill_dir / _SCRIPTS_DIRNAME
    if scripts_dir.is_dir():
        script_files = (p for p in scripts_dir.rglob("*") if p.is_file())
        files.extend(sorted(script_files, key=lambda p: p.relative_to(skill_dir).as_posix()))

    digest = hashlib.sha256(usedforsecurity=False)
    for file_path in files:
        rel = file_path.relative_to(skill_dir).as_posix()
        digest.update(rel.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(file_path.read_bytes())
        digest.update(b"\x00")
    return digest.hexdigest()


def _read_text_preserving(path: Path) -> str:
    """Lee un archivo preservando los finales de linea originales (CRLF/LF).

    Args:
        path: Ruta del archivo.

    Returns:
        Contenido textual sin normalizar newlines.
    """
    with open(path, "r", encoding="utf-8", newline="") as handle:
        return handle.read()


def _write_text_preserving(path: Path, text: str) -> None:
    """Escribe un archivo sin normalizar finales de linea.

    Args:
        path: Ruta del archivo.
        text: Contenido exacto a escribir.
    """
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def _registry_skill_names(text: str) -> list[str]:
    """Extrae los nombres de skill declarados en el registry (en orden).

    Args:
        text: Contenido del registry.

    Returns:
        Lista de nombres de skill.
    """
    return [match.group(1) for line in text.splitlines() if (match := _ENTRY_RE.match(line))]


def _entry_bounds(lines: list[str]) -> list[tuple[str, int, int]]:
    """Calcula los rangos [start, end) de cada bloque de skill en el registry.

    Args:
        lines: Lineas del registry (con finales de linea preservados).

    Returns:
        Lista de tuplas (name, start_index, end_index).
    """
    starts = [i for i, line in enumerate(lines) if _ENTRY_RE.match(line.rstrip("\r\n"))]
    bounds: list[tuple[str, int, int]] = []
    for idx, start in enumerate(starts):
        end = starts[idx + 1] if idx + 1 < len(starts) else len(lines)
        match = _ENTRY_RE.match(lines[start].rstrip("\r\n"))
        bounds.append((match.group(1), start, end))
    return bounds


def update_registry_text(text: str, digests: dict[str, str]) -> tuple[str, list[str]]:
    """Inserta/actualiza el campo ``sha256`` por skill sin reordenar entradas.

    Args:
        text: Contenido original del registry.
        digests: Mapa {skill: sha256} a persistir.

    Returns:
        Tupla (nuevo_texto, lista_de_skills_modificados).
    """
    lines = text.splitlines(keepends=True)
    newline = "\r\n" if "\r\n" in text else "\n"
    changed: list[str] = []
    # De abajo hacia arriba para no invalidar los indices al insertar lineas.
    for name, start, end in reversed(_entry_bounds(lines)):
        digest = digests.get(name)
        if digest is None:
            continue
        sha_idx = next(
            (i for i in range(start, end) if _SHA_LINE_RE.match(lines[i].rstrip("\r\n"))),
            None,
        )
        if sha_idx is not None:
            indent = _SHA_LINE_RE.match(lines[sha_idx].rstrip("\r\n")).group(1)
            new_line = f"{indent}sha256: {digest}{newline}"
            if lines[sha_idx] != new_line:
                changed.append(name)
            lines[sha_idx] = new_line
        else:
            insert_at = end
            while insert_at - 1 > start and lines[insert_at - 1].strip() == "":
                insert_at -= 1
            lines.insert(insert_at, f"{_INDENT}sha256: {digest}{newline}")
            changed.append(name)
    return "".join(lines), changed


def _build_digests(names: list[str]) -> tuple[dict[str, str], list[str]]:
    """Calcula digests para los skills declarados que existen en disco.

    Args:
        names: Nombres de skill declarados en el registry.

    Returns:
        Tupla (mapa_skill_digest, skills_sin_SKILL_md).
    """
    digests: dict[str, str] = {}
    missing: list[str] = []
    for name in names:
        skill_dir = _SKILLS_DIR / name
        if not (skill_dir / "SKILL.md").exists():
            missing.append(name)
            continue
        digests[name] = compute_skill_digest(skill_dir)
    return digests, missing


def main() -> None:
    """CLI principal: calcula digests y opcionalmente los persiste."""
    # Hardening Windows: consolas cp1252 no codifican emojis.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Digests sha256 de skills en el registry (FR-D1)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", help="Muestra cambios sin escribir (default)")
    group.add_argument("--write", action="store_true", help="Escribe los sha256 en el registry")
    args = parser.parse_args()

    if not _REGISTRY.exists():
        print(f"❌ registry faltante: {_REGISTRY}")
        return

    text = _read_text_preserving(_REGISTRY)
    names = _registry_skill_names(text)
    digests, missing = _build_digests(names)

    for name in names:
        if name in digests:
            print(f"  {name}: {digests[name]}")
    if missing:
        print(f"  ⚠  en registry sin SKILL.md: {', '.join(missing)}")

    new_text, changed = update_registry_text(text, digests)
    if args.write:
        _write_text_preserving(_REGISTRY, new_text)
        print(f"\n✅ {len(digests)} digests escritos ({len(changed)} actualizados)")
    else:
        print(
            f"\n🔎 dry-run: {len(digests)} digests calculados, "
            f"{len(changed)} cambios pendientes (no escrito)"
        )


if __name__ == "__main__":
    main()
