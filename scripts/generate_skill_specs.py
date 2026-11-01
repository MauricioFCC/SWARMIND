"""Genera ``SKILL.spec.json`` (contrato SDD, ADR-0048) desde cada SKILL.md.

El spec se **deriva** del contenido real del skill (no se inventa):

- ``preconditions``: disparador declarado en la ``description`` + contexto.
- ``postconditions``: items del ``## Checklist`` (fallback: pasos numerados).
- ``invariants``: items de secciones "Reglas"/"Constraints"/"Restricciones"/
  "Guardrails" (fallback: lineas con "nunca"/"siempre"/"prohibido").
- ``routing.body_keywords``: terminos distintivos del body (tf-idf vs corpus),
  senal body-aware que SkillRouter (2026) demuestra superior a description-only.
- ``source_sha256``: digest del SKILL.md que origino el spec (drift gate).

CLI:
    python scripts/generate_skill_specs.py --write   # escribe/actualiza specs
    python scripts/generate_skill_specs.py --check   # falla si hay drift
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / ".opencode" / "skills"
SPEC_NAME = "SKILL.spec.json"
GENERATOR = "scripts/generate_skill_specs.py"
GENERATOR_VERSION = "1.0.0"
FAILING_TEST = "harness/tests/test_skill_contracts.py"
MAX_DESCRIPTION = 256
MAX_INVARIANTS = 6
TOP_KEYWORDS = 8
MIN_KEYWORD_LEN = 4

_SECTION_RE = re.compile(r"^##\s+(.+)$", re.MULTILINE)
_CHECK_RE = re.compile(r"^\s*-\s*\[ \]\s*(.+)$", re.MULTILINE)
_ITEM_RE = re.compile(r"^\s*(?:[-*]|\d+\.)\s+(.+)$", re.MULTILINE)
_WORD_RE = re.compile(rf"[a-záéíóúñü]{{{MIN_KEYWORD_LEN},}}")
_INVARIANT_HEADINGS = ("regla", "constraint", "restriccion", "restricción", "guardrail")
_STOPWORDS_TEXT = """para como cuando donde desde entre sobre todos todas todo toda esta este
    estos estas skill skills usar usando debe deben puede pueden hacer hace
    hará sera será antes despues después cada otro otra solo sólo mas más
    menos muy sin con por que cual cuales quien quienes cuyo cuya del los las
    una unos unas sus tus mis nuestro nuestra ejemplo ejemplos regla reglas
    checklist documento proyecto sistema codigo código python test tests
    this that with your will have been they them what when which into also
    only more most other such each than then there these those their about
    above after again against being below between both does doing down during
    further here himself itself myself once same should some very were our out
    off over under until while who whom why how all any can did few for get
    got her his its let may new not now one own put see she too two use was
    way you name note topic notes"""
_STOPWORDS = frozenset(word for word in _STOPWORDS_TEXT.split())


def _load(skill_dir: Path) -> tuple[dict[str, object], str]:
    """Devuelve (frontmatter, body) del SKILL.md."""
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    front, body = text.split("---", 2)[1], text.split("---", 2)[2]
    return yaml.safe_load(front), body


def _sections(body: str) -> list[tuple[str, str]]:
    """Divide el body en (heading, contenido) por secciones ``##``."""
    matches = list(_SECTION_RE.finditer(body))
    chunks: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        chunks.append((match.group(1).strip(), body[match.end() : end]))
    return chunks


def _clean(item: str) -> str:
    """Normaliza un item de checklist/regla (sin markdown ni espacios extra)."""
    text = re.sub(r"\*\*|__|`", "", item).strip().rstrip(".;")
    return re.sub(r"\s+", " ", text)


def _postconditions(body: str) -> list[str]:
    """Items del checklist; fallback a los pasos numerados del flujo."""
    items = [_clean(item) for item in _CHECK_RE.findall(body)]
    if len(items) < 2:
        items = [_clean(item) for item in _ITEM_RE.findall(body)]
    return [item for item in items if 10 <= len(item) <= 220][:12]


def _invariants(body: str) -> list[str]:
    """Items de secciones de reglas/constraints (fallback: frases imperativas)."""
    items: list[str] = []
    for heading, chunk in _sections(body):
        lowered = heading.lower()
        if any(marker in lowered for marker in _INVARIANT_HEADINGS):
            items.extend(_clean(item) for item in _ITEM_RE.findall(chunk))
    if not items:
        for line in body.splitlines():
            lowered = line.lower()
            if any(word in lowered for word in ("nunca", "siempre", "prohibido")):
                items.append(_clean(line.lstrip("-* ")))
    unique = list(dict.fromkeys(item for item in items if len(item) >= 12))
    return unique[:MAX_INVARIANTS]


def _trigger(description: str) -> str:
    """Condicion de disparo (texto antes de ``Alcance:``, acotado)."""
    head = description.split("Alcance:")[0].strip().rstrip(".")
    return head[:220]


def _brief_description(description: str) -> str:
    """Description compacta: sin sufijo de reglas (``| UPG...``) y sin cortar palabras."""
    head = description.split("| UPG")[0].strip().rstrip(".")
    if len(head) <= MAX_DESCRIPTION:
        return head
    cut = head[:MAX_DESCRIPTION].rsplit(" ", 1)[0]
    return cut.rstrip(",;:.")


def _tokens(text: str) -> list[str]:
    """Tokens alfabeticos en minusculas (>= MIN_KEYWORD_LEN), sin stopwords."""
    return [word for word in _WORD_RE.findall(text.lower()) if word not in _STOPWORDS]


def _body_keywords(bodies: list[str], descriptions: list[str]) -> list[list[str]]:
    """Top terminos distintivos por skill (tf-idf contra el corpus de skills)."""
    corpus = [Counter(_tokens(body)) for body in bodies]
    doc_freq: Counter[str] = Counter()
    for tokens in corpus:
        doc_freq.update(set(tokens))
    total = len(corpus)
    result: list[list[str]] = []
    for tokens, description in zip(corpus, descriptions, strict=True):
        banned = set(_tokens(description))
        scores = {
            term: count * math.log((total + 1) / (doc_freq[term] + 1))
            for term, count in tokens.items()
            if term not in banned
        }
        ranked = sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))
        result.append([term for term, _ in ranked[:TOP_KEYWORDS]])
    return result


def _source_sha256(skill_dir: Path) -> str:
    """sha256 del SKILL.md con fin de linea normalizado a LF (portable CI)."""
    raw = (skill_dir / "SKILL.md").read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(raw).hexdigest()


def _build(
    skill_dir: Path,
    front: dict[str, object],
    body: str,
    keywords: list[str],
) -> dict[str, object]:
    """Construye el dict del spec para un skill."""
    name = skill_dir.name
    description = _brief_description(str(front.get("description", "")))
    return {
        "name": name,
        "version": str(front.get("version", "1.0.0")),
        "description": description,
        "contract": {
            "input": {
                "type": "object",
                "required": ["task"],
                "properties": {
                    "task": {"type": "string", "description": "Tarea explicita del usuario"},
                    "context": {
                        "type": "string",
                        "description": "Contexto del proyecto (codigo, tests, config)",
                    },
                },
            },
            "output": {
                "type": "object",
                "required": ["artifacts", "evidence"],
                "properties": {
                    "artifacts": {"type": "array", "items": {"type": "string"}},
                    "evidence": {
                        "type": "string",
                        "description": "Salida real de gates/tests (VER)",
                    },
                },
            },
        },
        "preconditions": [
            f"Peticion alineada con el disparador: {_trigger(description)}",
            "Contexto del proyecto disponible (codigo, tests, configuracion)",
        ],
        "postconditions": _postconditions(body),
        "invariants": _invariants(body),
        "failing_test": FAILING_TEST,
        "routing": {"triggers": [_trigger(description)], "body_keywords": keywords},
        "source_sha256": _source_sha256(skill_dir),
        "provenance": {
            "generator": GENERATOR,
            "generator_version": GENERATOR_VERSION,
            "source": "SKILL.md",
        },
    }


def _skill_dirs() -> list[Path]:
    """Directorios de skill con SKILL.md, ordenados."""
    return sorted(
        path
        for path in SKILLS_DIR.iterdir()
        if path.is_dir() and (path / "SKILL.md").is_file()
    )


def build_specs() -> dict[str, dict[str, object]]:
    """Construye todos los specs en memoria (clave = nombre de skill)."""
    loaded = [(path, *_load(path)) for path in _skill_dirs()]
    bodies = [body for _, _, body in loaded]
    descriptions = [str(front.get("description", "")) for _, front, _ in loaded]
    keywords = _body_keywords(bodies, descriptions)
    return {
        path.name: _build(path, front, body, words)
        for (path, front, body), words in zip(loaded, keywords, strict=True)
    }


def _serialize(spec: dict[str, object]) -> str:
    """JSON canonico del spec (indent 2, UTF-8, newline final)."""
    return json.dumps(spec, ensure_ascii=False, indent=2) + "\n"


def _is_generated(spec_path: Path) -> bool:
    """True si el spec lo genero este script (tiene ``provenance.generator``)."""
    try:
        data = json.loads(spec_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    provenance = data.get("provenance", {})
    return isinstance(provenance, dict) and provenance.get("generator") == GENERATOR


def _sync(specs: dict[str, dict[str, object]], write: bool) -> int:
    """Escribe (o solo cuenta) los specs que cambiaron. Devuelve nº de cambios."""
    changes = 0
    for name, spec in specs.items():
        target = SKILLS_DIR / name / SPEC_NAME
        if target.is_file() and not _is_generated(target):
            continue  # contrato manual curado: no se sobrescribe
        payload = _serialize(spec)
        if target.is_file() and target.read_text(encoding="utf-8") == payload:
            continue
        changes += 1
        if write:
            target.write_text(payload, encoding="utf-8")
    return changes


def main() -> int:
    """CLI: --write actualiza, --check falla si hay drift."""
    parser = argparse.ArgumentParser(description="Genera SKILL.spec.json (ADR-0048)")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="escribe los specs")
    mode.add_argument("--check", action="store_true", help="falla si hay drift")
    args = parser.parse_args()

    specs = build_specs()
    changes = _sync(specs, write=args.write)
    if args.check and changes:
        print(f"DRIFT: {changes} spec(s) desactualizados; usa --write")
        return 1
    action = "escritos" if args.write else "al dia"
    print(f"{len(specs)} specs | {changes} cambios | {action}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
