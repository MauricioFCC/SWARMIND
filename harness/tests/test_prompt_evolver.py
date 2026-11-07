"""Tests de PromptEvolver (mutación/evaluación/promoción de perfiles)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from harness.evolve_loop import prompt_evolver as pe_module
from harness.evolve_loop.prompt_evolver import PromptEvolver
from harness.memory_rag.lance_vector_store import COLLECTION_PROMPT_EVOLUTION_LOG

PROFILE = """# software-engineer

## Responsabilidades
Implementa endpoints REST y escribe tests.

## Output
Respuesta en markdown con el diff aplicado.

## Notas
- por ejemplo: GET /api/v1/status
- nota: mantener cobertura >= 80%
"""


@pytest.fixture(autouse=True)
def _archivos_en_tmp(monkeypatch, tmp_path):
    """Los artefactos (archivos de agentes y mutantes) van al tmp."""
    archivo = tmp_path / "archive"
    agentes = tmp_path / "agents"
    archivo.mkdir()
    agentes.mkdir()
    monkeypatch.setattr(pe_module, "PROMPT_ARCHIVE_DIR", archivo)
    monkeypatch.setattr(pe_module, "AGENTS_DIR", agentes)
    return tmp_path


def _perfil(tmp_path: Path, nombre: str = "software-engineer.md") -> Path:
    path = tmp_path / nombre
    path.write_text(PROFILE, encoding="utf-8")
    return path


class TestMutatePrompt:
    """Paso 1: generar las tres variantes A/B/C."""

    def test_perfil_inexistente_lanza(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="Agent profile not found"):
            PromptEvolver().mutate_prompt(str(tmp_path / "no_existe.md"))

    def test_genera_tres_variantes_en_el_archive(self, tmp_path, _archivos_en_tmp):
        perfil = _perfil(tmp_path)
        rutas = PromptEvolver().mutate_prompt(str(perfil))
        assert len(rutas) == 3
        assert [Path(r).name for r in rutas] == [
            "software-engineer_mutant_A.md",
            "software-engineer_mutant_B.md",
            "software-engineer_mutant_C.md",
        ]
        assert all(Path(r).is_file() for r in rutas)

    def test_mutante_a_quita_lineas_de_ejemplo(self, tmp_path, _archivos_en_tmp):
        """Mientras quede presupuesto (70 %), caen las líneas de ejemplo/nota."""
        perfil = tmp_path / "agente-min.md"
        perfil.write_text(
            "# agente\n"
            "linea normal 1\n"
            "linea normal 2\n"
            "por ejemplo: uno\n"
            "por ejemplo: dos\n"
            "e.g. tres\n"
            "note: cuatro\n"
            "nota: cinco\n",
            encoding="utf-8",
        )
        rutas = PromptEvolver().mutate_prompt(str(perfil))
        contenido_a = Path(rutas[0]).read_text(encoding="utf-8").lower()
        assert "por ejemplo" not in contenido_a
        assert "e.g." not in contenido_a
        assert "linea normal 1" in contenido_a

    def test_mutante_b_mueve_output_al_principio(self, tmp_path, _archivos_en_tmp):
        """La sección de salida pasa por delante de las demás secciones."""
        perfil = _perfil(tmp_path)
        rutas = PromptEvolver().mutate_prompt(str(perfil))
        contenido_b = Path(rutas[1]).read_text(encoding="utf-8").lower()
        assert contenido_b.index("## output") < contenido_b.index(
            "## responsabilidades"
        )
        # La variante "Reorder" debe de verdad mutar (no devolver el original).
        assert contenido_b != perfil.read_text(encoding="utf-8").lower()

    def test_mutante_c_anade_caso_concreto(self, tmp_path, _archivos_en_tmp):
        rutas = PromptEvolver().mutate_prompt(str(_perfil(tmp_path)))
        contenido_c = Path(rutas[2]).read_text(encoding="utf-8")
        assert "## Caso concreto" in contenido_c
        assert "GET /api/v1/status" in contenido_c  # caso del dominio

    def test_mutante_c_usa_el_caso_por_defecto(self, tmp_path, _archivos_en_tmp):
        """Un agente sin caso propio usa el default (no escribe vacío)."""
        perfil = tmp_path / "agente-raro.md"
        perfil.write_text("# x\n", encoding="utf-8")
        rutas = PromptEvolver().mutate_prompt(str(perfil))
        contenido_c = Path(rutas[2]).read_text(encoding="utf-8")
        assert "quality-gate" in contenido_c


class TestEvaluateMutants:
    """Paso 2: puntuación determinista por heurística (sin LLM)."""

    def test_evalua_original_y_mutantes(self, tmp_path, _archivos_en_tmp):
        original = _perfil(tmp_path)
        rutas = PromptEvolver().mutate_prompt(str(original))
        scores = PromptEvolver().evaluate_mutants(
            str(original), rutas, "deploy status endpoint"
        )
        assert set(scores) == {"original"} | {Path(r).stem for r in rutas}
        for resultado in scores.values():
            assert {"tokens", "success", "time", "score"} <= set(resultado)
            assert isinstance(resultado["tokens"], int)

    def test_formula_de_score(self, tmp_path, _archivos_en_tmp):
        """score = 100*success - tokens/1000 - time/10."""
        original = _perfil(tmp_path)
        scores = PromptEvolver().evaluate_mutants(
            str(original), [], "deploy status endpoint"
        )
        resultado = scores["original"]
        bonus = 100.0 if resultado["success"] else 0.0
        esperado = bonus - resultado["tokens"] / 1000.0 - resultado["time"] / 10.0
        assert resultado["score"] == pytest.approx(esperado)

    def test_success_depende_de_las_keywords(self, tmp_path, _archivos_en_tmp):
        original = _perfil(tmp_path)
        original.write_text("deploy status endpoint deploy", encoding="utf-8")
        scores = PromptEvolver().evaluate_mutants(
            str(original), [], "deploy status endpoint"
        )
        assert scores["original"]["success"] is True

        original.write_text("zzz yyy", encoding="utf-8")
        scores = PromptEvolver().evaluate_mutants(
            str(original), [], "deploy status endpoint"
        )
        assert scores["original"]["success"] is False


class TestPromoteWinner:
    """Paso 3: promover el ganador, respaldar y registrar en LanceDB."""

    def _prepara(self, tmp_path: Path, contenido_ganador: str = "NUEVO CONTENIDO"):
        agentes = tmp_path / "agents"
        archivo = tmp_path / "archive"
        agentes.mkdir(exist_ok=True)
        archivo.mkdir(exist_ok=True)
        (agentes / "software-engineer.md").write_text("ORIGINAL", encoding="utf-8")
        ganador = archivo / "software-engineer_mutant_B.md"
        ganador.write_text(contenido_ganador, encoding="utf-8")
        return ganador, agentes, archivo

    def test_ganador_inexistente(self, tmp_path, _archivos_en_tmp):
        assert PromptEvolver().promote_winner(str(tmp_path /("no.md"))) is False

    def test_perfil_original_inexistente(self, tmp_path, _archivos_en_tmp):
        archivo = tmp_path / "archive"
        archivo.mkdir(exist_ok=True)
        suelto = archivo / "fantasma_mutant_A.md"
        suelto.write_text("x", encoding="utf-8")
        assert PromptEvolver().promote_winner(str(suelto)) is False

    def test_promociona_y_respaldando(self, tmp_path, _archivos_en_tmp):
        ganador, agentes, archivo = self._prepara(tmp_path)
        assert PromptEvolver().promote_winner(str(ganador)) is True
        original = agentes / "software-engineer.md"
        assert original.read_text(encoding="utf-8") == "NUEVO CONTENIDO"
        respaldos = list(archivo.glob("software-engineer_backup_*.md"))
        assert len(respaldos) == 1
        assert respaldos[0].read_text(encoding="utf-8") == "ORIGINAL"

    def test_sin_vector_store_no_intent_registrar(self, tmp_path, _archivos_en_tmp):
        ganador, _, _ = self._prepara(tmp_path)
        evolver = PromptEvolver(vector_store=None)
        assert evolver.promote_winner(str(ganador)) is True
        assert evolver._vector_store is None

    def test_registra_promocion_en_el_store(self, tmp_path, _archivos_en_tmp):
        ganador, _, _ = self._prepara(tmp_path, contenido_ganador="MAS CORTO Y RESUMIDO")
        store = MagicMock()
        evolver = PromptEvolver(vector_store=store)
        assert evolver.promote_winner(str(ganador)) is True

        assert store.insert.call_count == 1
        coleccion, vectores, metadatos = store.insert.call_args[0]
        assert coleccion == COLLECTION_PROMPT_EVOLUTION_LOG
        assert vectores.shape == (1, 384)
        meta = metadatos[0]
        assert meta["agent"] == "software-engineer"
        assert meta["mutation_type"] == "B"
        assert meta["promoted"] is True
        # antes = respaldo original ("ORIGINAL"), despues = ganador ya aplicado
        assert meta["tokens_before"] == int(len("ORIGINAL") * 0.75)
        assert meta["tokens_after"] == int(len("MAS CORTO Y RESUMIDO") * 0.75)
        assert meta["tokens_before"] != meta["tokens_after"]

    def test_fallo_del_store_no_propaga(self, tmp_path, _archivos_en_tmp):
        """Un error al registrar en LanceDB no revierte la promoción."""
        ganador, agentes, _ = self._prepara(tmp_path)
        store = MagicMock()
        store.insert.side_effect = RuntimeError("lancedb caido")
        evolver = PromptEvolver(vector_store=store)
        assert evolver.promote_winner(str(ganador)) is True
        assert (agentes / "software-engineer.md").read_text(encoding="utf-8") == (
            "NUEVO CONTENIDO"
        )
