"""evolve_skills.py — Pase profundo del loop EVO sobre las skills (GEPA + gate).

WHAT: para cada skill genera variantes del CUERPO con `GEPAMutator` (GEPA),
las puntua con un scorer determinista (estructura, tamano, perdida de
contenido) y solo promueve la mejor si SUPERA el baseline y pasa el gate.
WHY: el pase determinista (frontmatter/descripcion/secciones) ya se hizo; la
mejora profunda del cuerpo exige un ciclo generate→evaluate→promote con gate
(Proof-or-Stop). Sin evidencia NO se promueve: `--dry-run` es el default.
WHERE: loop EVO/ASI-Evolve sobre `.opencode/skills/`; el gate final lo cierra
`scripts/validate_skills.py --strict` + `harness/tests/test_skill_pec.py`.

Uso:
    python scripts/evolve_skills.py                 # dry-run (propone, no escribe)
    python scripts/evolve_skills.py --limit 5
    python scripts/evolve_skills.py --apply         # promueve solo si mejora y pasa el gate

Exit codes: 0 = OK; 1 = fallo de lectura/escritura; 2 = gate de promocion fallido.
"""

from __future__ import annotations

import argparse
import logging
import sys
import zlib
from pathlib import Path

logger = logging.getLogger("swarmind.evolve_skills")

#: Raiz del repo (scripts/ -> repo).
ROOT = Path(__file__).resolve().parent.parent
#: Directorio de skills.
SKILLS_DIR = ROOT / ".opencode" / "skills"

#: Separador de frontmatter YAML.
_FRONTMATTER_DELIMITER = "---"
#: Lineas maximas recomendadas de un SKILL.md (progressive disclosure).
MAX_SKILL_LINES = 500
#: Variantes generadas por skill.
DEFAULT_MUTANTS = 3
#: Secciones que una variante NO puede perder (contrato de skill).
REQUIRED_SECTIONS: tuple[str, ...] = ("## Checklist", "## Anti-patrones")
#: Pesos del scorer determinista.
WEIGHT_SECTION = 0.3
WEIGHT_PERSONA = 0.2
WEIGHT_OVERFLOW = 0.5
WEIGHT_MISSING_SECTION = 0.4


def _split_frontmatter(text: str) -> tuple[str, str]:
    """Separa el frontmatter YAML del cuerpo de un SKILL.md.

    Args:
        text: Contenido completo del archivo.

    Returns:
        `(frontmatter, body)`; si no hay frontmatter, `("", text)`.
    """
    if not text.startswith(_FRONTMATTER_DELIMITER):
        return "", text
    parts = text.split(_FRONTMATTER_DELIMITER, 2)
    if len(parts) < 3:
        return "", text
    return f"{_FRONTMATTER_DELIMITER}{parts[1]}{_FRONTMATTER_DELIMITER}", parts[2]


def _count_lines(body: str) -> int:
    """Cuenta las lineas no vacias de un cuerpo.

    Args:
        body: Texto del cuerpo.

    Returns:
        Numero de lineas con contenido.
    """
    return sum(1 for line in body.splitlines() if line.strip())


def _has_checklist(body: str) -> bool:
    """Indica si el cuerpo trae items de checklist (`- [ ]`).

    Args:
        body: Texto del cuerpo.

    Returns:
        True si hay al menos un item de checklist.
    """
    return "- [ ]" in body


def score_skill(body: str) -> float:
    """Puntua un cuerpo de skill de forma determinista (mayor es mejor).

    Reglas: premia secciones requeridas y PERSONA; penaliza exceso de tamano.

    Args:
        body: Cuerpo de la skill (sin frontmatter).

    Returns:
        Score en puntos (float); 0.0 = cuerpo vacio.
    """
    if not body.strip():
        return 0.0
    score = 0.0
    for section in REQUIRED_SECTIONS:
        if section in body:
            score += WEIGHT_SECTION
    if _has_checklist(body):
        score += WEIGHT_SECTION
    if "PERSONA" in body:
        score += WEIGHT_PERSONA
    if _count_lines(body) > MAX_SKILL_LINES:
        score -= WEIGHT_OVERFLOW
    return round(score, 4)


def _missing_sections(original: str, candidate: str) -> tuple[str, ...]:
    """Secciones requeridas presentes en el original pero ausentes en la variante.

    Args:
        original: Cuerpo baseline.
        candidate: Cuerpo de la variante.

    Returns:
        Tupla de secciones perdidas (vacia si no se perdio ninguna).
    """
    return tuple(
        section for section in REQUIRED_SECTIONS
        if section in original and section not in candidate
    )


def evaluate_variant(original: str, candidate: str) -> float:
    """Puntua una variante penalizando la perdida de secciones del contrato.

    Args:
        original: Cuerpo baseline.
        candidate: Cuerpo mutado.

    Returns:
        Score de la variante (puede ser negativo si pierde contrato).
    """
    return round(
        score_skill(candidate)
        - WEIGHT_MISSING_SECTION * len(_missing_sections(original, candidate)),
        4,
    )


def _skill_paths(limit: int | None) -> list[Path]:
    """Lista las rutas de SKILL.md del repositorio (ordenadas).

    Args:
        limit: Maximo de skills a procesar (None = todas).

    Returns:
        Lista de rutas a `SKILL.md`.
    """
    paths = sorted(SKILLS_DIR.glob("*/SKILL.md"))
    return paths[:limit] if limit else paths


def _propose_variants(name: str, body: str, count: int) -> list[tuple[float, str, str]]:
    """Genera variantes GEPA del cuerpo y las puntua (determinista).

    Args:
        name: Nombre de la skill (source_agent del mutador).
        body: Cuerpo baseline.
        count: Numero de variantes.

    Returns:
        Lista `(score, estrategias, cuerpo_mutado)` ordenada por score desc.
    """
    from harness.evolve_loop.gepa_mutator import GEPAMutator

    mutator = GEPAMutator(seed=zlib.crc32(name.encode("utf-8")))
    mutants = mutator.create_mutants(name, body, num_mutants=count)
    scored = [
        (evaluate_variant(body, mutant.mutated_prompt),
         ", ".join(mutant.mutations_applied), mutant.mutated_prompt)
        for mutant in mutants
    ]
    return sorted(scored, key=lambda item: item[0], reverse=True)


def _process(path: Path, *, dry_run: bool, mutants: int) -> tuple[str, float, float]:
    """Procesa una skill: puntua baseline, propone y (si aplica) promueve.

    Args:
        path: Ruta al SKILL.md.
        dry_run: True para no escribir cambios.
        mutants: Numero de variantes a generar.

    Returns:
        `(nombre, score_baseline, score_mejor)`.
    """
    text = path.read_text(encoding="utf-8")
    front, body = _split_frontmatter(text)
    baseline = score_skill(body)
    proposals = _propose_variants(path.parent.name, body, mutants)
    best_score, strategies, best_body = proposals[0]
    logger.info(
        "  %-20s baseline=%.2f mejor=%.2f (%s)",
        path.parent.name, baseline, best_score, strategies,
    )
    if dry_run or best_score <= baseline or not front:
        return path.parent.name, baseline, best_score
    if _missing_sections(body, best_body):
        logger.warning("  %s: variante pierde secciones; NO se promueve", path.parent.name)
        return path.parent.name, baseline, best_score
    path.write_text(f"{front}\n{best_body}", encoding="utf-8")
    logger.info("  %s: PROMOVIDA (%.2f -> %.2f)", path.parent.name, baseline, best_score)
    return path.parent.name, baseline, best_score


def run(dry_run: bool, limit: int | None, mutants: int) -> int:
    """Ejecuta el pase profundo sobre las skills seleccionadas.

    Args:
        dry_run: True para solo proponer (no escribir).
        limit: Maximo de skills a procesar.
        mutants: Numero de variantes por skill.

    Returns:
        Exit code (0 OK; 1 fallo de IO).
    """
    paths = _skill_paths(limit)
    if not paths:
        logger.error("WHAT: no hay skills en %s. WHERE: evolve_skills.run", SKILLS_DIR)
        return 1
    logger.info("evolve_skills: %d skill(s) | dry_run=%s", len(paths), dry_run)
    promoted = 0
    try:
        for path in paths:
            _, baseline, best = _process(path, dry_run=dry_run, mutants=mutants)
            promoted += int(best > baseline)
    except OSError as exc:
        logger.error("WHAT: fallo de IO. WHY: %s. WHERE: evolve_skills.run", exc)
        return 1
    logger.info("evolve_skills: candidatas a promover=%d (dry_run=%s)", promoted, dry_run)
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Construye el parser de argumentos.

    Returns:
        Parser con `--apply`, `--limit`, `--mutants`.
    """
    parser = argparse.ArgumentParser(
        description="Pase profundo EVO (GEPA) sobre las skills, con gate determinista.",
    )
    parser.add_argument("--apply", action="store_true", help="promover variantes (default: dry-run)")
    parser.add_argument("--limit", type=int, default=None, help="maximo de skills a procesar")
    parser.add_argument("--mutants", type=int, default=DEFAULT_MUTANTS, help="variantes por skill")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada del runner.

    Args:
        argv: Argumentos opcionales (default: `sys.argv`).

    Returns:
        Exit code del contrato.
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = build_parser().parse_args(argv)
    return run(dry_run=not args.apply, limit=args.limit, mutants=args.mutants)


if __name__ == "__main__":
    sys.exit(main())
