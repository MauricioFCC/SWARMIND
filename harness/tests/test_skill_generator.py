"""Tests de SkillGenerator (auto-creación y lookup de skills procedurales)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import yaml

from harness.evolve_loop import skill_generator as sg
from harness.evolve_loop.skill_generator import (
    SkillGenerator,
    _resolve_skill_path,
)
from harness.memory_rag.lance_vector_store import COLLECTION_PROCEDURAL_SKILLS


@pytest.fixture(autouse=True)
def _paths_en_tmp(monkeypatch, tmp_path):
    """Los artefactos (auto/, registry) van al tmp, nunca al repo."""
    auto = tmp_path / "auto"
    auto.mkdir()
    registry = tmp_path / "skills_registry.yaml"
    monkeypatch.setattr(sg, "AUTO_SKILLS_DIR", auto)
    monkeypatch.setattr(sg, "REGISTRY_PATH", registry)
    return tmp_path


class TestGenerateSkill:
    """Heurística: >=5 llamadas de tool Y success, y con steps."""

    def test_requiere_cinco_llamadas(self, tmp_path):
        gen = SkillGenerator()
        assert gen.generate_skill("agente", "tarea", 4, True, ["paso 1"]) is None

    def test_cinco_llamadas_con_success_genera(self, tmp_path):
        gen = SkillGenerator()
        resultado = gen.generate_skill("agente", "tarea cinco", 5, True, ["paso 1"])
        assert isinstance(resultado, dict)
        assert resultado["name"]

    def test_sin_success_no_genera(self, tmp_path):
        gen = SkillGenerator()
        assert gen.generate_skill("agente", "tarea", 6, False, ["paso 1"]) is None

    def test_requiere_steps(self, tmp_path):
        gen = SkillGenerator()
        assert gen.generate_skill("agente", "tarea", 5, True, []) is None

    def test_genera_fichero_md_y_registro(self, tmp_path):
        gen = SkillGenerator()
        entrada = gen.generate_skill(
            "software-engineer",
            "deploy del servicio",
            5,
            True,
            ["crear el artefacto", "desplegar"],
        )
        assert entrada is not None

        ficheros = list((tmp_path / "auto").glob("*.md"))
        assert len(ficheros) == 1
        contenido = ficheros[0].read_text(encoding="utf-8")
        assert f"# skill: {entrada['name']}" in contenido
        assert "**Dominio**: full-stack-development" in contenido
        assert "**Generado por**: @software-engineer" in contenido
        assert "1. crear el artefacto" in contenido
        assert "2. desplegar" in contenido

        cargado = yaml.safe_load(
            (tmp_path / "skills_registry.yaml").read_text(encoding="utf-8")
        )
        nombres = [s["name"] for s in cargado["skills"]]
        assert nombres == [entrada["name"]]
        assert cargado["skills"][0]["domain"] == "full-stack-development"

    def test_trigger_limitado_a_200(self, tmp_path):
        gen = SkillGenerator()
        entrada = gen.generate_skill("agente", "tarea", 5, True, ["paso"])
        assert len(entrada["trigger"]) <= 200

    def test_registro_sin_duplicados(self, tmp_path):
        gen = SkillGenerator()
        with pytest.MonkeyPatch.context() as mp:
            # mismo slug => se reemplaza, no se duplica
            mp.setattr(sg.SkillGenerator, "_make_slug", staticmethod(lambda *_a: "fijo"))
            gen.generate_skill("agente", "tarea", 5, True, ["paso"])
            gen.generate_skill("agente", "tarea", 5, True, ["paso"])

        cargado = yaml.safe_load(
            (tmp_path / "skills_registry.yaml").read_text(encoding="utf-8")
        )
        assert len(cargado["skills"]) == 1

    def test_registro_yaml_corrompido_se_recupera(self, tmp_path):
        """Un registry ilegible no impide registrar (se reconstruye)."""
        (tmp_path / "skills_registry.yaml").write_text(
            "skills: [esto no es yaml {{", encoding="utf-8"
        )
        gen = SkillGenerator()
        entrada = gen.generate_skill("agente", "tarea", 5, True, ["paso"])
        assert entrada is not None
        cargado = yaml.safe_load(
            (tmp_path / "skills_registry.yaml").read_text(encoding="utf-8")
        )
        assert [s["name"] for s in cargado["skills"]] == [entrada["name"]]

    def test_indexa_en_lancedb_si_hay_store(self, tmp_path):
        store = MagicMock()
        gen = SkillGenerator(vector_store=store)
        gen.generate_skill("agente", "tarea", 5, True, ["paso"])

        assert store.insert.call_count == 1
        coleccion, vectores, metadatos = store.insert.call_args[0]
        assert coleccion == COLLECTION_PROCEDURAL_SKILLS
        assert vectores.shape == (1, 384)
        assert metadatos[0]["agent"] == "agente"
        assert metadatos[0]["steps_text"].startswith("1. paso")

    def test_sin_store_no_indexa(self, tmp_path):
        gen = SkillGenerator(vector_store=None)
        gen.generate_skill("agente", "tarea", 5, True, ["paso"])
        assert (tmp_path / "auto").glob("*.md")

    def test_fallo_del_store_no_propaga(self, tmp_path):
        store = MagicMock()
        store.insert.side_effect = RuntimeError("lancedb caido")
        gen = SkillGenerator(vector_store=store)
        assert gen.generate_skill("agente", "tarea", 5, True, ["paso"]) is not None


class TestInferDomain:
    """Mapa agente -> dominio (con fallback general)."""

    @pytest.mark.parametrize(
        ("agente", "dominio"),
        [
            ("software-engineer", "full-stack-development"),
            ("security-engineer", "security-compliance"),
            ("quant-developer", "quantitative-trading"),
            ("project-manager", "project-management"),
            ("evolve", "self-improvement"),
        ],
    )
    def test_dominio_conocido(self, agente: str, dominio: str) -> None:
        assert SkillGenerator._infer_domain(agente) == dominio

    def test_dominio_desconocido(self) -> None:
        assert SkillGenerator._infer_domain("agente-raro") == "general"


class TestMakeSlug:
    """Slug URL-safe con las primeras palabras significativas."""

    def test_usa_las_primeras_palabras(self) -> None:
        slug = SkillGenerator._make_slug("Deploy del Kafka Topic", "agente")
        # filtra solo palabras de <=2 caracteres; "del" (3) se queda
        assert slug.startswith("deploy_del_kafka_topic_")
        assert len(slug.rsplit("_", 1)[1]) == 6  # id corto de uuid4

    def test_filtra_palabras_cortas(self) -> None:
        slug = SkillGenerator._make_slug("de la a kafka", "agente")
        # "de", "la", "a" miden <= 2 -> se quedan fuera
        assert slug.startswith(("kafka_", "skill_"))

    def test_fallback_sin_palabras_significativas(self) -> None:
        slug = SkillGenerator._make_slug("ab", "mi-agente")
        assert slug.startswith("skill_mi_agente_")

    def test_slug_es_url_safe(self) -> None:
        slug = SkillGenerator._make_slug("Crea/una ruta? rara!", "agente")
        assert slug.replace("_", "").replace("-", "").isalnum()


class TestBuildMdContent:
    """El .md generado documenta slug, dominio, agente, trigger y pasos."""

    def test_contiene_los_campos(self) -> None:
        contenido = SkillGenerator._build_md_content(
            "mi_skill", "seguridad", "auditor", "revisar PR", ["paso uno"]
        )
        assert "# skill: mi_skill" in contenido
        assert "**Dominio**: seguridad" in contenido
        assert "**Generado por**: @auditor" in contenido
        assert "**Trigger**: revisar PR" in contenido
        assert "1. paso uno" in contenido
        assert "---" in contenido


class TestQueryTokensYScore:
    """Tokenización sin stopwords y puntuación ponderada por campo."""

    def test_query_vacia_o_solo_stopwords(self) -> None:
        assert SkillGenerator._query_tokens("") == ()
        assert SkillGenerator._query_tokens("de la que y") == ()
        assert SkillGenerator._query_tokens("skill skills") == ()

    def test_tokens_validos(self) -> None:
        tokens = SkillGenerator._query_tokens("deploy el kafka topic")
        assert all(len(t) >= 2 for t in tokens)
        assert "el" not in tokens
        assert "deploy" in tokens

    def test_score_por_nombre(self) -> None:
        skill = {"name": "security-audit", "domain": "otro", "description": "x"}
        assert SkillGenerator._score_skill(("security",), skill) == pytest.approx(3.0)

    def test_score_por_dominio(self) -> None:
        skill = {"name": "x", "domain": "infraestructura", "description": "y"}
        assert SkillGenerator._score_skill(("infraestructura",), skill) == pytest.approx(2.0)

    def test_score_sin_match_es_cero(self) -> None:
        assert SkillGenerator._score_skill(("zzz",), {"name": "x"}) == pytest.approx(0.0)


class TestFindInRegistry:
    """Búsqueda por tokens en el registry YAML."""

    def test_sin_registry(self) -> None:
        assert SkillGenerator.find_in_registry("seguridad") is None

    def test_registry_corrompido(self, tmp_path) -> None:
        (tmp_path / "skills_registry.yaml").write_text("{{ roto", encoding="utf-8")
        assert SkillGenerator.find_in_registry("seguridad") is None

    def test_sin_tokens_significativos(self, tmp_path) -> None:
        (tmp_path / "skills_registry.yaml").write_text(
            yaml.safe_dump({"skills": [{"name": "x"}]}), encoding="utf-8"
        )
        assert SkillGenerator.find_in_registry("de la que") is None

    def test_match_por_token_de_nombre(self, tmp_path) -> None:
        (tmp_path / "skills_registry.yaml").write_text(
            yaml.safe_dump(
                {"skills": [{"name": "security-audit", "description": "otra"}]}
            ),
            encoding="utf-8",
        )
        encontrado = SkillGenerator.find_in_registry("audit security")
        assert encontrado is not None
        assert encontrado["name"] == "security-audit"

    def test_resuelve_path_curado(self, tmp_path) -> None:
        carpeta = tmp_path / "security-audit"
        carpeta.mkdir()
        (carpeta / "SKILL.md").write_text("# security", encoding="utf-8")
        (tmp_path / "skills_registry.yaml").write_text(
            yaml.safe_dump({"skills": [{"name": "security-audit"}]}),
            encoding="utf-8",
        )
        encontrado = SkillGenerator.find_in_registry("security audit")
        assert encontrado["path"] == str(carpeta / "SKILL.md")

    def test_score_bajo_no_matchea(self, tmp_path) -> None:
        (tmp_path / "skills_registry.yaml").write_text(
            yaml.safe_dump({"skills": [{"name": "alpha"}]}), encoding="utf-8"
        )
        assert SkillGenerator.find_in_registry("zzz qqq") is None


class TestResolveSkillPath:
    """Resolución de la ruta de un skill curado."""

    def test_vacio_devuelve_vacio(self) -> None:
        assert _resolve_skill_path("") == ""

    def test_no_existe(self) -> None:
        assert _resolve_skill_path("no-existe") == ""

    def test_directo(self, tmp_path) -> None:
        carpeta = tmp_path / "directo"
        carpeta.mkdir()
        (carpeta / "SKILL.md").write_text("x", encoding="utf-8")
        assert _resolve_skill_path("directo") == str(carpeta / "SKILL.md")

    def test_por_glob_anidado(self, tmp_path) -> None:
        anidado = tmp_path / "dom" / "anidado"
        anidado.mkdir(parents=True)
        (anidado / "SKILL.md").write_text("x", encoding="utf-8")
        assert _resolve_skill_path("anidado") == str(anidado / "SKILL.md")


class TestPathDeRegistro:
    """_resolve_skill_path usa el padre del registry como raiz de skills."""

    def test_raiz_es_el_directorio_del_registry(self, tmp_path) -> None:
        assert sg.REGISTRY_PATH.parent == tmp_path
        assert _resolve_skill_path("") == ""
