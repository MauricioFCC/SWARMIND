"""Tests TDD del Skill Lift REAL — catalogo de tareas + runner determinista.

Cubre el ciclo RED->GREEN de la evaluacion pareada skill-on vs skill-off
(SkillsBench, arXiv:2602.12670) con verifiers DETERMINISTAS (0 LLM, 0 red, 0 DB):

    (a) el catalogo tiene >= 6 tareas, cada una con verifier callable y una skill
        que existe en el repo; la reference satisface su propio verifier.
    (b) el runner produce lift positivo donde se espera: con la skill (contexto
        real) el verifier pasa; con ``skill=None`` (naive) falla.
    (c) el runner respeta el ``skill_loader`` inyectado (spy: # llamadas/args).
    (d) integracion: ``SkillLiftEvaluator(runner=SkillLiftRunner(...))`` emite un
        ``LiftResult`` con verdict correcto.
    (e) mutacion: saltar el ``skill_loader`` (contexto vacio) rompe el lift
        (el verifier deja de pasar con skill).
    (f) determinismo: dos ejecuciones producen el mismo resultado.
"""

from __future__ import annotations

import pytest

from harness.evals.skill_lift import SkillLiftEvaluator
from harness.evals.skill_lift_runner import (
    SkillLiftRunner,
    default_skill_loader,
    skill_marker,
)
from harness.evals.skill_lift_tasks import (
    DEFAULT_TASKS,
    SKILLS_DIR,
    LiftTask,
    SkillLiftCatalog,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

#: Numero minimo de tareas exigido al catalogo por defecto.
_MIN_DEFAULT_TASKS = 6


def _synthetic_verifier(output: str) -> bool:
    """Verifier sintetico: exige dos tokens presentes en la reference."""
    return "alpha-open" in output and "alpha-close" in output


def _synthetic_catalog() -> SkillLiftCatalog:
    """Catalogo de una tarea con verifier puro para tests de DI."""
    task = LiftTask(
        id="syn-1",
        skill="demo-skill",
        prompt="demo prompt",
        verifier=_synthetic_verifier,
        reference="alpha-open alpha-close",
    )
    return SkillLiftCatalog(tasks=[task])


def _fake_loader(skill: str) -> str:
    """Loader sintetico: devuelve la marca de frontmatter de la skill pedida."""
    return f"---\n{skill_marker(skill)}\n---\nbody"


# ---------------------------------------------------------------------------
# (a) Catalogo
# ---------------------------------------------------------------------------


class TestCatalog:
    """Contrato del catalogo de tareas por defecto."""

    def test_a_default_tiene_al_menos_seis_tareas(self) -> None:
        """(a) el catalogo por defecto trae >= 6 tareas."""
        catalog = SkillLiftCatalog()
        assert len(catalog.all_tasks()) >= _MIN_DEFAULT_TASKS
        assert len(DEFAULT_TASKS) == len(catalog.all_tasks())

    def test_a_cada_verifier_es_callable(self) -> None:
        """(a) cada tarea expone un verifier callable."""
        for task in SkillLiftCatalog().all_tasks():
            assert callable(task.verifier)

    def test_a_cada_skill_existe_en_el_repo(self) -> None:
        """(a) cada tarea apunta a una skill real (SKILL.md presente)."""
        for task in SkillLiftCatalog().all_tasks():
            skill_md = SKILLS_DIR / task.skill / "SKILL.md"
            assert skill_md.is_file(), f"skill sin SKILL.md: {task.skill}"

    def test_a_reference_satisface_su_verifier(self) -> None:
        """(a) la reference (contrato) pasa su propio verifier determinista."""
        for task in SkillLiftCatalog().all_tasks():
            assert task.verifier(task.reference), f"reference no pasa verifier: {task.id}"

    def test_a_verifier_rechaza_salida_naive(self) -> None:
        """(a) los verifiers rechazan una salida sin las keywords del skill."""
        for task in SkillLiftCatalog().all_tasks():
            assert not task.verifier("No dispongo de las instrucciones necesarias.")

    def test_get_tarea_inexistente_lanza_keyerror(self) -> None:
        """get() de un id inexistente -> KeyError legible."""
        with pytest.raises(KeyError):
            SkillLiftCatalog().get("no-existe")

    def test_tasks_for_skill_filtra(self) -> None:
        """tasks_for_skill() devuelve solo las tareas de esa skill."""
        catalog = SkillLiftCatalog()
        tasks = catalog.tasks_for_skill("atdd-spec")
        assert tasks and all(task.skill == "atdd-spec" for task in tasks)
        assert catalog.tasks_for_skill("skill-inexistente") == []

    def test_ids_duplicados_falla(self) -> None:
        """Construir con ids duplicados -> ValueError."""
        task = LiftTask("dup", "atdd-spec", "p", _synthetic_verifier, "r")
        with pytest.raises(ValueError):
            SkillLiftCatalog(tasks=[task, task])

    def test_catalogo_vacio_falla(self) -> None:
        """Construir con lista vacia -> ValueError."""
        with pytest.raises(ValueError):
            SkillLiftCatalog(tasks=[])


# ---------------------------------------------------------------------------
# (b) Lift positivo / naive
# ---------------------------------------------------------------------------


class TestLiftSignal:
    """El runner produce PASS con skill y FAIL sin skill (ablacion)."""

    def test_b_con_skill_pasa_sin_skill_falla(self) -> None:
        """(b) con contexto real => True; con skill=None (naive) => False."""
        catalog = _synthetic_catalog()
        runner = SkillLiftRunner(catalog=catalog, skill_loader=_fake_loader)

        assert runner("syn-1", "demo-skill") is True
        assert runner("syn-1", None) is False

    def test_b_catalogo_real_lift_positivo(self) -> None:
        """(b) sobre el catalogo real: skill-on True, ablacion False en TODAS."""
        catalog = SkillLiftCatalog()
        runner = SkillLiftRunner(catalog=catalog)  # loader real por defecto

        for task in catalog.all_tasks():
            assert runner(task.id, task.skill) is True, task.id
            assert runner(task.id, None) is False, task.id

    def test_b_evaluador_delta_cien_useful(self) -> None:
        """(b) lift medido = +100pp para una skill que aporta su instruccion."""
        catalog = _synthetic_catalog()
        evaluator = SkillLiftEvaluator(
            runner=SkillLiftRunner(catalog=catalog, skill_loader=_fake_loader)
        )
        result = evaluator.evaluate("demo-skill", ["syn-1"], trials=2)

        assert result.pass_with == 1.0
        assert result.pass_without == 0.0
        assert result.verdict == "useful"


# ---------------------------------------------------------------------------
# (c) DI del skill_loader
# ---------------------------------------------------------------------------


class TestSkillLoaderDI:
    """El runner invoca el skill_loader inyectado con el nombre correcto."""

    def test_c_loader_recibe_la_skill(self) -> None:
        """(c) spy: el loader se llama una vez con el nombre de la skill."""
        calls: list[str] = []

        def spy_loader(skill: str) -> str:
            calls.append(skill)
            return _fake_loader(skill)

        runner = SkillLiftRunner(catalog=_synthetic_catalog(), skill_loader=spy_loader)
        assert runner("syn-1", "demo-skill") is True
        assert calls == ["demo-skill"]

    def test_c_ablacion_no_llama_al_loader(self) -> None:
        """(c) con skill=None el loader NO se invoca (ablacion pura)."""
        calls: list[str] = []

        def spy_loader(skill: str) -> str:
            calls.append(skill)
            return _fake_loader(skill)

        runner = SkillLiftRunner(catalog=_synthetic_catalog(), skill_loader=spy_loader)
        assert runner("syn-1", None) is False
        assert calls == []

    def test_c_solver_inyectado_tiene_prioridad(self) -> None:
        """(c) un solver inyectado reemplaza al baseline determinista."""
        seen: list[tuple[str, str | None]] = []

        def spy_solver(prompt: str, context: str | None) -> str:
            seen.append((prompt, context))
            return "alpha-open alpha-close"

        runner = SkillLiftRunner(catalog=_synthetic_catalog(), solver=spy_solver)
        assert runner("syn-1", None) is True  # el solver controla la salida
        assert seen == [("demo prompt", None)]


# ---------------------------------------------------------------------------
# (d) Integracion con SkillLiftEvaluator
# ---------------------------------------------------------------------------


class TestEvaluatorIntegration:
    """El runner es un SkillRunner valido para el evaluador pareado."""

    def test_d_produce_liftresult_verdict(self) -> None:
        """(d) SkillLiftEvaluator(runner=SkillLiftRunner(...)) -> LiftResult useful."""
        catalog = SkillLiftCatalog()
        evaluator = SkillLiftEvaluator(runner=SkillLiftRunner(catalog=catalog))
        result = evaluator.evaluate("atdd-spec", ["atdd-spec-cycle"], trials=3)

        assert result.delta_pp == pytest.approx(100.0)
        assert result.verdict == "useful"

    def test_d_evaluate_all_report(self) -> None:
        """(d) evaluate_all sobre las skills del catalogo produce un reporte."""
        catalog = SkillLiftCatalog()
        evaluator = SkillLiftEvaluator(runner=SkillLiftRunner(catalog=catalog))
        results = evaluator.evaluate_all(catalog.skills(), catalog.task_ids(), trials=1)

        assert len(results) == len(catalog.skills())
        summary = evaluator.report(results)
        assert summary["useful"] == len(results)


# ---------------------------------------------------------------------------
# (e) Mutation: saltar el skill_loader rompe el lift
# ---------------------------------------------------------------------------


class TestMutationSkippingLoader:
    """Si se omite el contexto, el lift desaparece (test que caza el mutante)."""

    def test_e_loader_vacio_rompe_el_pase(self) -> None:
        """(e) loader que no aporta contexto => verifier False con skill."""
        runner = SkillLiftRunner(catalog=_synthetic_catalog(), skill_loader=lambda _: "")
        assert runner("syn-1", "demo-skill") is False

    def test_e_contexto_sin_marca_no_ayuda(self) -> None:
        """(e) un contexto de OTRA skill no satisface el verifier."""
        runner = SkillLiftRunner(
            catalog=_synthetic_catalog(),
            skill_loader=lambda _: f"---\n{skill_marker('otra-skill')}\n---\n",
        )
        assert runner("syn-1", "demo-skill") is False

    def test_e_evaluador_queda_neutral_sin_contexto(self) -> None:
        """(e) sin contexto el lift deja de ser useful (cae a neutral)."""
        evaluator = SkillLiftEvaluator(
            runner=SkillLiftRunner(catalog=_synthetic_catalog(), skill_loader=lambda _: "")
        )
        result = evaluator.evaluate("demo-skill", ["syn-1"], trials=1)

        assert result.delta_pp == pytest.approx(0.0)
        assert result.verdict == "neutral"


# ---------------------------------------------------------------------------
# (f) Determinismo
# ---------------------------------------------------------------------------


class TestDeterminism:
    """El runner y su verifier son deterministas (reproducibles en CI)."""

    def test_f_dos_ejecuciones_iguales(self) -> None:
        """(f) dos corridas devuelven exactamente el mismo resultado."""
        catalog = SkillLiftCatalog()
        runner = SkillLiftRunner(catalog=catalog)

        first = [runner(task.id, task.skill) for task in catalog.all_tasks()]
        second = [runner(task.id, task.skill) for task in catalog.all_tasks()]
        assert first == second

    def test_f_default_skill_loader_lee_el_repo(self) -> None:
        """(f) el loader por defecto devuelve el SKILL.md real (idempotente)."""
        first = default_skill_loader("atdd-spec")
        second = default_skill_loader("atdd-spec")
        assert first == second
        assert skill_marker("atdd-spec") in first


# ---------------------------------------------------------------------------
# Guardrails
# ---------------------------------------------------------------------------


class TestRunnerGuardrails:
    """Validacion de dependencias (VAL)."""

    def test_catalog_invalido_falla(self) -> None:
        """catalog no SkillLiftCatalog -> TypeError."""
        with pytest.raises(TypeError):
            SkillLiftRunner(catalog="no-es-catalogo")  # type: ignore[arg-type]

    def test_skill_loader_invalido_falla(self) -> None:
        """skill_loader no callable -> TypeError."""
        with pytest.raises(TypeError):
            SkillLiftRunner(catalog=_synthetic_catalog(), skill_loader=42)  # type: ignore[arg-type]
