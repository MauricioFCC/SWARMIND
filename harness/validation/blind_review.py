"""blind_review.py — Paquete de revisión ciega (EGM) con gates deterministas.

WHAT: construye un paquete autocontenido (intención + diff redactado +
checklist de criterios de aceptación) para que el revisor juzgue **sin** la
conversación del autor, y aplica primero gates deterministas (sin modelo):
criterios presentes, cero secretos, cero rutas personales, diff acotado y
alcance de archivos.

WHY: EGM (Elephant Goldfish Model, Google): quien revisa con el contexto del
autor hereda sus mismos puntos ciegos. Binnacle: los checks deterministas
corren antes de que ningún modelo juzgue. Frontrera 2026 (FR-0010):
`docs/research/frontier-2026-11-19-harness-policies.md`.

WHERE: antes de pedir revisión a otro agente/modelo (`cross_review`,
`vibe_review_gate`); CLI `scripts/blind_review.py --spec <spec> --git-diff`.

Coste: O(|spec| + |diff|) en tiempo y memoria; sin red, sin modelo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from harness.validation.prompt_sanitizer import redact, redact_all

# ---------------------------------------------------------------------------
# Constantes (MAG)
# ---------------------------------------------------------------------------
#: Tope por defecto del diff incluido en el paquete (caracteres).
_DEFAULT_MAX_DIFF_CHARS = 20_000
#: Tope de archivos tocados (anti scope-creep).
_DEFAULT_MAX_FILES = 25
#: Máximo de criterios extraídos (evita paquetes gigantes).
_MAX_CRITERIA = 50
#: Marca explícita de truncado (nunca silencioso).
_TRUNCATION_MARK = "[TRUNCADO: {n} caracteres omitidos]"

#: Id de criterio de aceptación (AC-1, AC-BR2, AC_CG3...). Exige al menos un
#: dígito para no capturar palabras que empiezan por "AC" (ACE, ACTUAL).
_AC_ID_RE = re.compile(r"\bAC[-_ ]?[A-Za-z]*\d[A-Za-z0-9._-]*\b")
#: Encabezado de la sección de criterios (fallback sin ids).
_AC_SECTION_RE = re.compile(r"(?i)^#{1,6}\s*.*(criterios de aceptaci[oó]n|acceptance criteria).*$")
#: Prefijo de viñeta o numeración markdown.
_LIST_PREFIX_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")


@dataclass(frozen=True)
class CheckResult:
    """Resultado de un gate determinista del paquete.

    Attributes:
        name: Identificador estable del gate.
        passed: True si el gate no bloquea la revisión.
        detail: Evidencia legible (conteos, tipos, motivos).
    """

    name: str
    passed: bool
    detail: str = ""


@dataclass(frozen=True)
class BlindPacket:
    """Paquete reproducible para revisar sin el contexto del autor.

    Attributes:
        spec_title: Primer encabezado de la spec (intención).
        acceptance_criteria: Criterios extraídos en orden de aparición.
        diff: Diff redactado y eventualmente truncado.
        checks: Gates deterministas evaluados en orden estable.
        redactions: Resumen de redacciones aplicadas.
        files_touched: Archivos detectados en el diff.
        truncated: True si el diff se recortó por presupuesto.
    """

    spec_title: str
    acceptance_criteria: tuple[str, ...]
    diff: str
    checks: tuple[CheckResult, ...]
    redactions: tuple[str, ...] = ()
    files_touched: int = 0
    truncated: bool = False

    @property
    def approved_for_review(self) -> bool:
        """True si todos los gates deterministas pasaron."""
        return all(check.passed for check in self.checks)

    def failed_checks(self) -> tuple[str, ...]:
        """Nombres de los gates que bloquearon el paquete."""
        return tuple(check.name for check in self.checks if not check.passed)


def _spec_title(spec_md: str) -> str:
    """Extrae el primer encabezado de nivel 1 de la spec.

    Args:
        spec_md: Markdown de la especificación.

    Returns:
        Título o ``"Spec sin titulo"`` si no hay encabezado.
    """
    for line in spec_md.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip() or "Spec sin titulo"
    return "Spec sin titulo"


def _section_criteria(spec_md: str) -> tuple[str, ...]:
    """Fallback: viñetas bajo una sección de criterios de aceptación.

    Args:
        spec_md: Markdown de la especificación.

    Returns:
        Viñetas encontradas (máximo ``_MAX_CRITERIA``).
    """
    lines = spec_md.splitlines()
    for index, line in enumerate(lines):
        if _AC_SECTION_RE.match(line) is None:
            continue
        items: list[str] = []
        for candidate in lines[index + 1 :]:
            if candidate.startswith("#"):
                break
            if _LIST_PREFIX_RE.match(candidate):
                items.append(_LIST_PREFIX_RE.sub("", candidate.strip()))
                if len(items) >= _MAX_CRITERIA:
                    break
        return tuple(items)
    return ()


def _is_criterion_line(line: str) -> bool:
    """Indica si la línea es estructural (viñeta, fila de tabla o id al inicio).

    Args:
        line: Línea cruda del markdown.

    Returns:
        True si la línea puede declarar un criterio de aceptación.

    Notes:
        La prosa que menciona ids (``ver AC-1 y AC-2``) no declara criterios;
        contarla inflaría el paquete con referencias.
    """
    stripped = line.strip()
    return _LIST_PREFIX_RE.match(line) is not None or stripped.startswith("|") or _AC_ID_RE.match(stripped) is not None


def extract_acceptance_criteria(spec_md: str) -> tuple[str, ...]:
    """Extrae los criterios de aceptación de una spec.

    Args:
        spec_md: Markdown de la especificación.

    Returns:
        Criterios normalizados, sin duplicados por id y en orden de aparición.
    """
    found: dict[str, str] = {}
    for line in spec_md.splitlines():
        if not _is_criterion_line(line):
            continue
        ids = _AC_ID_RE.findall(line)
        if not ids:
            continue
        key = ids[0].rstrip(".:-").upper()
        text = _LIST_PREFIX_RE.sub("", line.strip()).lstrip("|").strip()
        found.setdefault(key, text)
        if len(found) >= _MAX_CRITERIA:
            break
    return tuple(found.values()) if found else _section_criteria(spec_md)


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    """Recorta el texto en un salto de línea y marca lo omitido.

    Args:
        text: Texto a recortar.
        limit: Tope de caracteres.

    Returns:
        ``(texto, truncado)`` con marca explícita si hubo recorte.
    """
    if len(text) <= limit:
        return text, False
    cut = text.rfind("\n", 0, limit)
    cut = cut if cut > 0 else limit
    omitted = len(text) - cut
    return f"{text[:cut]}\n{_TRUNCATION_MARK.format(n=omitted)}", True


def _count_files(diff: str) -> int:
    """Cuenta archivos tocados por cabeceras ``diff --git``.

    Args:
        diff: Diff en formato unificado.

    Returns:
        Número de cabeceras encontradas (0 si es un fragmento sin cabeceras).
    """
    return sum(1 for line in diff.splitlines() if line.startswith("diff --git "))


def _validate_inputs(spec_md: str, diff: str, max_diff_chars: int, max_files: int) -> None:
    """Valida entradas y topes del paquete (fail-fast tipado).

    Args:
        spec_md: Markdown de la especificación.
        diff: Diff a revisar.
        max_diff_chars: Tope de caracteres.
        max_files: Tope de archivos.

    Raises:
        ValueError: Si falta la spec/diff o los topes no son positivos.
    """
    if not spec_md.strip():
        raise ValueError("WHAT: spec vacia\nWHY: sin intencion no hay revision posible\nWHERE: build_blind_packet()")
    if not diff.strip():
        raise ValueError("WHAT: diff vacio\nWHY: no hay cambio que revisar\nWHERE: build_blind_packet()")
    if max_diff_chars <= 0 or max_files <= 0:
        raise ValueError(
            f"WHAT: topes invalidos ({max_diff_chars}, {max_files})\n"
            "WHY: deben ser enteros positivos\nWHERE: build_blind_packet()"
        )


def _build_checks(criteria: tuple[str, ...], view: DiffView, max_files: int) -> tuple[CheckResult, ...]:
    """Evalúa los cinco gates deterministas en orden estable."""
    return (
        CheckResult(
            "spec_has_acceptance_criteria",
            bool(criteria),
            f"{len(criteria)} criterios",
        ),
        CheckResult("no_secrets", not view.secret_kinds, ",".join(view.secret_kinds) or "sin secretos"),
        CheckResult("no_personal_paths", view.path_hits == 0, f"{view.path_hits} rutas personales"),
        CheckResult("diff_within_budget", not view.truncated, "truncado" if view.truncated else "completo"),
        CheckResult("scope_files", view.files <= max_files, f"{view.files} archivos (max {max_files})"),
    )


def _describe_redactions(secret_kinds: tuple[str, ...], path_hits: int, truncated: bool) -> tuple[str, ...]:
    """Resume de forma estable lo redactado o truncado."""
    parts = [f"secretos:{kind}" for kind in secret_kinds]
    if path_hits:
        parts.append(f"rutas_personales:{path_hits}")
    if truncated:
        parts.append("diff_truncado")
    return tuple(parts)


def _describe_packet(view: DiffView, spec_redacted: bool) -> tuple[str, ...]:
    """Resume lo redactado en el diff y, si aplica, en la spec."""
    descriptions = _describe_redactions(view.secret_kinds, view.path_hits, view.truncated)
    return (*descriptions, "spec_redactada") if spec_redacted else descriptions


@dataclass(frozen=True)
class DiffView:
    """Vista del diff ya redactada y acotada.

    Attributes:
        body: Diff redactado (y truncado si excede el presupuesto).
        secret_kinds: Tipos de secreto encontrados.
        path_hits: Rutas con nombre de usuario real.
        truncated: True si el diff se recortó.
        files: Archivos tocados según cabeceras ``diff --git``.
    """

    body: str
    secret_kinds: tuple[str, ...]
    path_hits: int
    truncated: bool
    files: int


def _prepare_diff(diff: str, max_diff_chars: int) -> DiffView:
    """Redacta el diff, lo acota y cuenta su alcance.

    Args:
        diff: Diff en formato unificado.
        max_diff_chars: Tope de caracteres del diff incluido.

    Returns:
        ``DiffView`` con el contenido listo para el paquete.
    """
    redacted, secret_kinds, path_hits = redact_all(diff)
    body, truncated = _truncate(redacted, max_diff_chars)
    return DiffView(body, secret_kinds, path_hits, truncated, _count_files(diff))


def _prepare_spec(spec_md: str) -> tuple[str, tuple[str, ...], bool]:
    """Extrae título y criterios de la spec, redactados antes de salir.

    Args:
        spec_md: Markdown de la especificación.

    Returns:
        ``(titulo, criterios, hubo_redaccion)``.
    """
    raw_criteria = extract_acceptance_criteria(spec_md)
    criteria = tuple(redact(item)[0] for item in raw_criteria)
    raw_title = _spec_title(spec_md)
    title = redact(raw_title)[0]
    return title, criteria, title != raw_title or criteria != raw_criteria


def _packet(
    title: str,
    criteria: tuple[str, ...],
    view: DiffView,
    max_files: int,
    spec_redacted: bool,
) -> BlindPacket:
    """Ensambla el paquete a partir de sus partes ya preparadas.

    Args:
        title: Título redactado de la spec.
        criteria: Criterios de aceptación redactados.
        view: Diff redactado y acotado.
        max_files: Tope de archivos tocados.
        spec_redacted: True si la spec se redactó.

    Returns:
        ``BlindPacket`` con los cinco gates evaluados.
    """
    return BlindPacket(
        spec_title=title,
        acceptance_criteria=criteria,
        diff=view.body,
        checks=_build_checks(criteria, view, max_files),
        redactions=_describe_packet(view, spec_redacted),
        files_touched=view.files,
        truncated=view.truncated,
    )


def build_blind_packet(
    spec_md: str,
    diff: str,
    *,
    max_diff_chars: int = _DEFAULT_MAX_DIFF_CHARS,
    max_files: int = _DEFAULT_MAX_FILES,
) -> BlindPacket:
    """Construye el paquete y ejecuta los gates deterministas.

    Args:
        spec_md: Spec con la intención del cambio.
        diff: Diff a revisar.
        max_diff_chars: Tope de caracteres del diff.
        max_files: Tope de archivos.

    Returns:
        ``BlindPacket`` con los gates evaluados.

    Raises:
        ValueError: Spec/diff vacíos o topes no positivos.
    """
    _validate_inputs(spec_md, diff, max_diff_chars, max_files)
    title, criteria, spec_redacted = _prepare_spec(spec_md)
    view = _prepare_diff(diff, max_diff_chars)
    return _packet(title, criteria, view, max_files, spec_redacted)


def _render_header(packet: BlindPacket) -> list[str]:
    """Cabecera del paquete con la instrucción de contexto cero."""
    return [
        f"# Revisión ciega — {packet.spec_title}",
        "",
        "Este paquete no incluye la conversación del autor: juzga **solo**",
        "contra la especificación y los criterios de aceptación.",
        "",
        "## Gates deterministas",
        "",
        "| Gate | Estado | Detalle |",
        "|---|---|---|",
    ]


def render_markdown(packet: BlindPacket) -> str:
    """Renderiza el paquete como prompt de revisión reproducible.

    Args:
        packet: Paquete generado por :func:`build_blind_packet`.

    Returns:
        Markdown determinista (sin fecha ni historial de conversación).
    """
    lines = _render_header(packet)
    for check in packet.checks:
        state = "PASS" if check.passed else "BLOCK"
        lines.append(f"| {check.name} | {state} | {check.detail} |")
    lines += ["", "## Criterios de aceptación", ""]
    lines += [f"- {item}" for item in packet.acceptance_criteria] or ["- (ninguno)"]
    if packet.redactions:
        lines += ["", "## Redacciones aplicadas", ""]
        lines += [f"- {item}" for item in packet.redactions]
    lines += ["", "## Diff", "", "```diff", packet.diff.rstrip(), "```", ""]
    return "\n".join(lines)


__all__ = [
    "BlindPacket",
    "CheckResult",
    "build_blind_packet",
    "extract_acceptance_criteria",
    "redact",
    "render_markdown",
]
