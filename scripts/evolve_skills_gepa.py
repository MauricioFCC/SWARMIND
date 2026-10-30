"""evolve_skills_gepa.py — oráculo determinista para el ciclo evolutivo GEPA de skills.

Implementa la fase EXPERIMENT del ciclo EVO/GEPA (arXiv:2507.19457) aplicada a
``SKILL.md``: evalúa candidatos (original, variantes mutantes) con heurísticas
deterministas **sin LLM**, produce *feedback textual* por gap y calcula el
**Pareto frontier** sobre dos objetivos ortogonales:

- **activabilidad** (¿la skill se dispara y se entiende rápido?): SDO
  (``Usar cuando``), anti-trigger explícito (``Cuándo NO usar``), apertura con
  acción, keywords de dominio y unicidad frente a otras skills (router).
- **ejecutabilidad** (¿el conocimiento se puede ejecutar?): brevedad
  (progressive disclosure), checklist/guardrails, ejemplo fenced, número de
  instrucciones imperativas y tabla de decisión accionable.

Un candidato domina a otro si no es peor en ningún objetivo y es mejor en al
menos uno (dominancia de Pareto). El ciclo promueve variantes Pareto-superiores
en vez del "mejor global" que estanca (lección GEPA).

Uso:
    python scripts/evolve_skills_gepa.py --baseline .opencode/skills/quant-trading/SKILL.md \
        --candidate A=variante-a.md --candidate B=variante-b.md
    python scripts/evolve_skills_gepa.py --baseline X --candidate A=Y --json

Exit codes: 0 = evaluación OK; 2 = error de entrada (I/O).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Rutas y constantes (MAG)
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parents[1]
_SKILLS_DIR = _ROOT / ".opencode" / "skills"

_MAX_LINES = 120
_ACCION_NORM = 18
_MIN_DOMAIN_KEYWORDS = 3

_FM_RE = re.compile(r"^---\r?\n(.*?)\r?\n---", re.DOTALL)
_SECTION_SPLIT_RE = re.compile(r"^##\s+", re.MULTILINE)
_CHECKLIST_RE = re.compile(r"^\s*-\s*\[\s*\]", re.MULTILINE)
_COMMAND_RE = re.compile(r"^\s*!", re.MULTILINE)
_FENCE_RE = re.compile(r"^```", re.MULTILINE)
_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$", re.MULTILINE)
_TABLE_SEP_RE = re.compile(r"^\s*\|[-\s:|]+\|\s*$", re.MULTILINE)
_ANTI_TRIGGER_RE = re.compile(r"cu[aá]ndo no usar|no usar cuando|no usar para", re.IGNORECASE)
_GUARDRAIL_RE = re.compile(r"guardrail|anti-?patr|prohibid", re.IGNORECASE)
_IMPERATIVE_RE = re.compile(
    r"^\s*(?:[-*+]\s+|\d+[.)]\s+)?"
    r"(aplica|usa|ejecuta|valida|define|mide|calcula|verifica|implementa|construye|revisa|"
    r"documenta|registra|comienza|inicia|abre|exige|formula|asigna|mapea|elige|fija|declara|"
    r"cierra|escala|responde|vigila|identifica|carga|ejecuta)\b",
    re.IGNORECASE | re.MULTILINE,
)

# Léxico de dominio financiero/cuantitativo para medir especificidad de la
# description (H7). Project-agnostic: términos del dominio, no del repo.
_DOMAIN_LEXICON = frozenset(
    {
        "trading", "quant", "cuantitativos", "latencia", "alpha", "backtesting",
        "market", "motores", "factores", "ejecucion", "riesgo", "reward", "mandato",
        "stop-loss", "capital", "institucional", "cro", "forum", "tecnologicos",
        "geopoliticos", "climaticos", "salud", "financieros", "solvencia", "liquidez",
    }
)

# Stopwords para el cálculo de unicidad de la description (H10).
_STOPWORDS = frozenset(
    {
        "usar", "cuando", "para", "ver", "alcance", "reglas", "base", "principles",
        "usuario", "proyecto", "esta", "este", "sobre", "como", "mas", "los", "las",
        "del", "que", "con", "por", "una", "unos", "unas", "fund", "ineficiente",
    }
)


@dataclass
class Metrics:
    """Puntaje por heurística + feedback textual de un candidato.

    Attributes:
        values: Mapa heurística -> valor normalizado en [0, 1].
        feedback: Frases accionables que explican cada gap detectado.
    """

    values: dict[str, float]
    feedback: list[str]


@dataclass
class Candidate:
    """Evaluación completa de un candidato (skill en un estado dado).

    Attributes:
        label: Etiqueta del candidato (original/A/B).
        path: Ruta del archivo evaluado.
        metrics: Métricas heurísticas.
        activability: Objetivo 1 (media de heurísticas de activabilidad).
        executability: Objetivo 2 (media de heurísticas de ejecutabilidad).
        composite: Score de resumen (media de los dos objetivos).
    """

    label: str
    path: Path
    metrics: Metrics
    activability: float
    executability: float
    composite: float

    def objective(self, name: str) -> float:
        """Retorna el valor de un objetivo por nombre.

        Args:
            name: "activability" o "executability".

        Returns:
            Valor del objetivo solicitado.
        """
        return self.activability if name == "activability" else self.executability


# ---------------------------------------------------------------------------
# Parseo
# ---------------------------------------------------------------------------
def _parse(text: str) -> tuple[dict[str, str], str]:
    """Extrae frontmatter (campos planos) y cuerpo de un SKILL.md.

    Args:
        text: Contenido completo del archivo.

    Returns:
        Tupla ``(campos, body)``; ``campos`` vacío si no hay frontmatter.
    """
    match = _FM_RE.match(text)
    if not match:
        return {}, text
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" in line and not line.startswith((" ", "-")):
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip().strip('"').strip("'")
    return fields, text[match.end():]


def _description_keywords(description: str) -> set[str]:
    """Extrae tokens de dominio de una description (para unicidad/H10).

    Args:
        description: Texto de la description.

    Returns:
        Conjunto de tokens normalizados, sin stopwords ni tokens cortos.
    """
    tokens = re.findall(r"[a-záéíóúñ0-9-]{4,}", description.lower())
    return {tok for tok in tokens if tok not in _STOPWORDS}


def _first_section(body: str) -> str:
    """Retorna el contenido de la primera sección H2 del cuerpo.

    Args:
        body: Cuerpo del SKILL.md (sin frontmatter).

    Returns:
        Texto de la primera sección (título + contenido), o el preámbulo si no
        hay secciones H2.
    """
    parts = _SECTION_SPLIT_RE.split(body)
    return parts[1] if len(parts) > 1 else parts[0]


def _has_table(body: str) -> bool:
    """Indica si el cuerpo contiene una tabla markdown con separador.

    Args:
        body: Cuerpo del SKILL.md.

    Returns:
        True si hay filas de tabla y una línea separadora ``|---|``.
    """
    return bool(_TABLE_ROW_RE.search(body)) and bool(_TABLE_SEP_RE.search(body))


def _count_actions(text: str) -> int:
    """Cuenta instrucciones imperativas/accionables en el texto.

    Args:
        text: Texto del cuerpo.

    Returns:
        Número de líneas accionables únicas (checklist + comandos + imperativas).
    """
    lines: set[int] = set()
    for regex in (_CHECKLIST_RE, _COMMAND_RE, _IMPERATIVE_RE):
        lines.update(text.count("\n", 0, match.start()) for match in regex.finditer(text))
    return len(lines)


# ---------------------------------------------------------------------------
# Evaluación heurística
# ---------------------------------------------------------------------------
def evaluate(text: str, all_descriptions: list[str] | None = None) -> Metrics:
    """Evalúa un SKILL.md con heurísticas deterministas y genera feedback.

    Args:
        text: Contenido completo del SKILL.md.
        all_descriptions: Descriptions de otras skills (corpus para H10). Si es
            None, H10 se calcula solo contra las demás del corpus vacío (1.0).

    Returns:
        Metrics con valores en [0, 1] por heurística y feedback textual.
    """
    fields, body = _parse(text)
    description = fields.get("description", "")
    desc_lower = description.lower()

    n_lines = len(text.splitlines())
    h1 = 1.0 if n_lines <= _MAX_LINES else max(0.0, 1.0 - (n_lines - _MAX_LINES) / 100.0)
    h2 = 1.0 if desc_lower.startswith("usar cuando") else 0.0
    h3 = 1.0 if _ANTI_TRIGGER_RE.search(description) else 0.0

    first = _first_section(body)
    actionable = (
        bool(_CHECKLIST_RE.search(first))
        or bool(_COMMAND_RE.search(first))
        or bool(_FENCE_RE.search(first))
        or bool(_IMPERATIVE_RE.search(first))
    )
    h4 = 1.0 if actionable else 0.0
    h5 = 1.0 if (_CHECKLIST_RE.search(body) or _GUARDRAIL_RE.search(body)) else 0.0
    h6 = 1.0 if (_FENCE_RE.search(body) or re.search(r"ejemplo trabajado", body, re.IGNORECASE)) else 0.0

    domain_hits = sum(1 for term in _DOMAIN_LEXICON if term in desc_lower)
    h7 = min(1.0, domain_hits / _MIN_DOMAIN_KEYWORDS)

    n_actions = _count_actions(body)
    h8 = min(1.0, n_actions / _ACCION_NORM)
    h9 = 1.0 if _has_table(body) else 0.0

    if all_descriptions:
        own = _description_keywords(description)
        max_jaccard = 0.0
        for other in all_descriptions:
            other_kw = _description_keywords(other)
            union = own | other_kw
            if union:
                max_jaccard = max(max_jaccard, len(own & other_kw) / len(union))
        h10 = 1.0 - max_jaccard
    else:
        h10 = 1.0

    values = {
        "H1_brevedad": h1,
        "H2_sdo": h2,
        "H3_anti_trigger": h3,
        "H4_apertura_accion": h4,
        "H5_checklist_guardrails": h5,
        "H6_ejemplo_fenced": h6,
        "H7_keywords_dominio": h7,
        "H8_accionabilidad": h8,
        "H9_tabla_decision": h9,
        "H10_unicidad_router": h10,
    }

    feedback = _build_feedback(values, n_lines, n_actions, domain_hits)
    return Metrics(values=values, feedback=feedback)


def _build_feedback(
    values: dict[str, float], n_lines: int, n_actions: int, domain_hits: int
) -> list[str]:
    """Genera feedback textual accionable a partir de los gaps detectados.

    Args:
        values: Valores por heurística.
        n_lines: Líneas del SKILL.md.
        n_actions: Instrucciones accionables contadas.
        domain_hits: Keywords de dominio en la description.

    Returns:
        Lista de frases de feedback (vacía si no hay gaps).
    """
    messages: list[str] = []
    if values["H1_brevedad"] < 1.0:
        messages.append(f"excede {_MAX_LINES} líneas ({n_lines}): mover detalle a references/.")
    if values["H2_sdo"] == 0.0:
        messages.append("la description no abre con 'Usar cuando': el router SDO no dispara.")
    if values["H3_anti_trigger"] == 0.0:
        messages.append(
            "description sin anti-trigger explícito ('Cuando NO usar: ...'): "
            "no puede descartar falsos positivos frente a skills solapadas."
        )
    if values["H4_apertura_accion"] == 0.0:
        messages.append(
            "el body abre con 'PERSONA & CANON', no con acción: añadir "
            "'## Activación inmediata' con pasos imperativos como primera sección."
        )
    if values["H7_keywords_dominio"] < 1.0:
        messages.append(f"solo {domain_hits} keywords de dominio en description (mínimo 3).")
    if values["H8_accionabilidad"] < 0.6:
        messages.append(
            f"pocas instrucciones imperativas ({n_actions}): convertir prosa/guardrails "
            "en pasos y checklist ejecutables."
        )
    if values["H9_tabla_decision"] == 0.0:
        messages.append("sin tabla de decisión accionable: el conocimiento no es ejecutable a primera vista.")
    if values["H10_unicidad_router"] < 0.5:
        messages.append(
            f"description solapada con otra skill (unicidad {values['H10_unicidad_router']:.2f}): "
            "especializar keywords para el router."
        )
    return messages


# ---------------------------------------------------------------------------
# Resultado y Pareto
# ---------------------------------------------------------------------------
def build_candidate(
    label: str, path: Path, all_descriptions: list[str] | None = None
) -> Candidate:
    """Construye un ``Candidate`` evaluado desde disco.

    Args:
        label: Etiqueta del candidato.
        path: Ruta del SKILL.md del candidato.
        all_descriptions: Corpus de descriptions para H10.

    Returns:
        Candidate evaluado.

    Raises:
        OSError: Si el archivo no puede leerse.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    metrics = evaluate(text, all_descriptions)
    v = metrics.values
    activability = (v["H2_sdo"] + v["H3_anti_trigger"] + v["H4_apertura_accion"]
                    + v["H7_keywords_dominio"] + v["H10_unicidad_router"]) / 5.0
    executability = (v["H1_brevedad"] + v["H5_checklist_guardrails"] + v["H8_accionabilidad"]
                     + v["H9_tabla_decision"]) / 4.0
    composite = (activability + executability) / 2.0
    return Candidate(
        label=label,
        path=path,
        metrics=metrics,
        activability=round(activability, 4),
        executability=round(executability, 4),
        composite=round(composite, 4),
    )


def dominates(a: Candidate, b: Candidate) -> bool:
    """Indica si el candidato ``a`` domina a ``b`` (Pareto).

    Args:
        a: Candidato candidato a dominante.
        b: Candidato potencialmente dominado.

    Returns:
        True si ``a`` no es peor en ningún objetivo y es estrictamente mejor en
        al menos uno.
    """
    no_worse = a.activability >= b.activability and a.executability >= b.executability
    strictly_better = a.activability > b.activability or a.executability > b.executability
    return no_worse and strictly_better


def pareto_frontier(candidates: list[Candidate]) -> list[str]:
    """Calcula las etiquetas del frente de Pareto.

    Args:
        candidates: Candidatos evaluados.

    Returns:
        Etiquetas de los candidatos no dominados por ningún otro.
    """
    frontier: list[str] = []
    for candidate in candidates:
        if not any(dominates(other, candidate) for other in candidates if other is not candidate):
            frontier.append(candidate.label)
    return frontier


def load_corpus_descriptions(exclude: Path | None = None) -> list[str]:
    """Carga las descriptions de todas las skills reales (corpus para H10).

    Args:
        exclude: Ruta de un SKILL.md a excluir del corpus (normalmente el propio
            baseline), para no autocontar la skill en evaluación.

    Returns:
        Lista de descriptions de las skills del repositorio.
    """
    descriptions: list[str] = []
    if not _SKILLS_DIR.is_dir():
        return descriptions
    for skill_md in sorted(_SKILLS_DIR.glob("*/SKILL.md")):
        if exclude is not None and skill_md.resolve() == exclude.resolve():
            continue
        fields, _ = _parse(skill_md.read_text(encoding="utf-8", errors="replace"))
        if fields.get("description"):
            descriptions.append(fields["description"])
    return descriptions


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------
def _render_table(candidates: list[Candidate], frontier: list[str]) -> None:
    """Imprime la tabla comparativa del ciclo y el frente de Pareto.

    Args:
        candidates: Candidatos evaluados.
        frontier: Etiquetas en el frente de Pareto.
    """
    header = f"{'CANDIDATO':<10} {'ACTIV':>7} {'EJEC':>7} {'COMP':>7} {'PARETO':>7}  FEEDBACK"
    print(header)
    print("-" * len(header))
    for cand in candidates:
        feedback = " | ".join(cand.metrics.feedback) or "sin gaps detectados"
        in_frontier = "SI" if cand.label in frontier else "no"
        print(
            f"{cand.label:<10} {cand.activability:>7.3f} {cand.executability:>7.3f} "
            f"{cand.composite:>7.3f} {in_frontier:>7}  {feedback}"
        )


def _render_json(candidates: list[Candidate], frontier: list[str]) -> None:
    """Imprime la evaluación en JSON (para CI / trazabilidad).

    Args:
        candidates: Candidatos evaluados.
        frontier: Etiquetas en el frente de Pareto.
    """
    payload = {
        "pareto_frontier": frontier,
        "candidates": [
            {
                "label": cand.label,
                "path": str(cand.path).replace("\\", "/"),
                "metrics": cand.metrics.values,
                "activability": cand.activability,
                "executability": cand.executability,
                "composite": cand.composite,
                "feedback": cand.metrics.feedback,
            }
            for cand in candidates
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> int:
    """Punto de entrada CLI: evalúa candidatos y reporta el Pareto frontier.

    Returns:
        0 si la evaluación completa; 2 si falla la lectura de un archivo.
    """
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Oráculo determinista GEPA para skills (sin LLM)")
    parser.add_argument("--baseline", required=True, help="SKILL.md de referencia")
    parser.add_argument(
        "--candidate",
        action="append",
        default=[],
        metavar="LABEL=PATH",
        help="Candidato variante (repetible)",
    )
    parser.add_argument("--json", action="store_true", help="Salida JSON")
    parser.add_argument("--no-corpus", action="store_true", help="No usar corpus de otras skills (H10=1.0)")
    args = parser.parse_args()

    baseline_path = Path(args.baseline)
    corpus = [] if args.no_corpus else load_corpus_descriptions(exclude=baseline_path)

    candidates: list[Candidate] = []
    try:
        candidates.append(build_candidate("original", baseline_path, corpus))
        for spec in args.candidate:
            label, _, raw_path = spec.partition("=")
            if not raw_path:
                print(
                    f"ERROR WHAT: --candidate mal formado ({spec!r}) "
                    "WHY: se espera LABEL=PATH WHERE: evolve_skills_gepa.py -> main()",
                    file=sys.stderr,
                )
                return 2
            candidates.append(build_candidate(label, Path(raw_path), corpus))
    except OSError as error:
        print(
            f"ERROR WHAT: no se pudo leer un candidato WHY: {error} "
            "WHERE: evolve_skills_gepa.py -> build_candidate()",
            file=sys.stderr,
        )
        return 2

    frontier = pareto_frontier(candidates)
    if args.json:
        _render_json(candidates, frontier)
    else:
        _render_table(candidates, frontier)
    return 0


if __name__ == "__main__":
    sys.exit(main())
