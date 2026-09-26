"""Tests para draft_review + supervisor local-first con guia cloud (ADR-0084).

Frontera: RLM-Cascade (arXiv:2606.22840: draft local + verify cloud con
router de complejidad; 88.8% draft-use, -45.8% costo, 100% vs 95% calidad)
+ Local-Splitter (7 tacticas; T4 draft-review 51% en RAG-heavy; margen de
confianza contra falsos positivos) + UCCI (cascada calibrada -31%).
"""

import pytest

from harness.model_router.draft_review import (
    DRAFT_PATH,
    DraftReviewer,
    ReviewPath,
)
from harness.orchestrator.local_supervisor import (
    LocalSupervisor,
)


def _draft_fn(text: str):
    """Fabrica draft_fn local que retorna texto fijo."""

    def _fn(task: str) -> tuple[str, float]:
        return text, 0.9

    return _fn


def _review_fn(patch: str):
    """Fabrica review_fn cloud que retorna el patch."""

    def _fn(task: str, draft: str) -> tuple[str, bool]:
        return patch, True

    return _fn


def test_skipped_path_zero_cloud() -> None:
    """Tarea trivial: SKIPPED (solo local, 0 tokens cloud)."""
    rev = DraftReviewer(
        draft_fn=_draft_fn("borrador"),
        review_fn=_review_fn("x"),
        complexity_fn=lambda t: "trivial",
    )
    out = rev.run("resume esto")
    assert out.path is ReviewPath.SKIPPED
    assert out.cloud_tokens == 0
    assert out.output == "borrador"


def test_verify_path_accepts_good_draft() -> None:
    """Draft bueno + verify OK: se acepta sin regenerar (pocos tokens)."""
    rev = DraftReviewer(
        draft_fn=_draft_fn("draft correcto"),
        review_fn=lambda t, d: ("ok", True),
        complexity_fn=lambda t: "medium",
    )
    out = rev.run("explica el modulo")
    assert out.path is ReviewPath.VERIFY
    assert out.output == "draft correcto"
    assert out.cloud_tokens <= 200


def test_enhance_path_patches_draft() -> None:
    """Draft debil: ENHANCE aplica el patch del cloud."""
    rev = DraftReviewer(
        draft_fn=_draft_fn("draft flojo"),
        review_fn=lambda t, d: ("draft mejorado", False),
        complexity_fn=lambda t: "hard",
    )
    out = rev.run("disena el algoritmo")
    assert out.path is ReviewPath.ENHANCE
    assert out.output == "draft mejorado"


def test_low_confidence_escalates() -> None:
    """Confianza bajo el margen -> cloud directo (anti falso positivo)."""
    def _doubtful(task: str) -> tuple[str, float]:
        return "dudoso", 0.2

    rev = DraftReviewer(
        draft_fn=_doubtful,
        review_fn=lambda t, d: ("cloud responde", True),
        complexity_fn=lambda t: "trivial",
        confidence_margin=0.5,
    )
    out = rev.run("resume esto")
    assert out.path is ReviewPath.ENHANCE
    assert out.output == "cloud responde"


def test_paths_documented() -> None:
    """Los 3 paths existen (SKIPPED/VERIFY/ENHANCE)."""
    assert {p.value for p in ReviewPath} == {"skipped", "verify", "enhance"}
    assert DRAFT_PATH == "skipped"


def test_supervisor_samples_at_rate() -> None:
    """El supervisor audita ~sample_rate de salidas locales."""
    judged: list[bool] = []

    def judge_fn(task: str, output: str) -> bool:
        judged.append(True)
        return True

    sup = LocalSupervisor(judge_fn=judge_fn, sample_rate=1.0)
    sup.observe("t1", "agente-local", "salida uno")
    sup.observe("t2", "agente-local", "salida dos")
    assert len(judged) == 2
    assert sup.audited == 2


def test_supervisor_zero_rate_never_judges() -> None:
    """sample_rate=0: nunca audita (0 tokens cloud)."""
    judged: list[bool] = []

    def judge_fn(task: str, output: str) -> bool:
        judged.append(True)
        return True

    sup = LocalSupervisor(judge_fn=judge_fn, sample_rate=0.0)
    sup.observe("t1", "a", "o")
    assert judged == []
    assert sup.audited == 0


def test_supervisor_feeds_competence() -> None:
    """El veredicto alimenta el CompetenceModel (cierra el loop)."""
    from harness.orchestrator.competence_model import CompetenceModel

    model = CompetenceModel(agents=("local coder",), skills=("code",))

    def judge_fn(task: str, output: str) -> bool:
        return True

    sup = LocalSupervisor(judge_fn=judge_fn, sample_rate=1.0, competence=model)
    sup.observe("t1", "local coder", "codigo", skill="code")
    posterior = model.posterior("local coder", "code")
    assert posterior.successes >= 2  # prior + 1 veredicto


def test_supervisor_invalid_rate_raises() -> None:
    """sample_rate fuera de [0,1] falla accionable."""
    with pytest.raises(ValueError, match="WHAT"):
        LocalSupervisor(judge_fn=lambda t, o: True, sample_rate=1.5)
