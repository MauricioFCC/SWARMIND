"""
Tests para success_correlation — Success-Correlation Engine (Headroom "learn").

Aprende del fallo seguido de exito (no cataloga fallos) y deriva lecciones
accionables inyectables en el contexto del agente (ADR-0033).

Cubre:
  - Lesson: campos, to_dict(), to_marker_block()
  - learn() deriva el texto segun la categoria
  - get_lessons() filtra por categoria
  - apply_to_context() es idempotente y preserva texto fuera de marcadores
  - from_session_trace() deriva path_correction de un trace sintetico
  - stats() cuenta por categoria
"""

from __future__ import annotations

from harness.orchestrator.success_correlation import (
    Lesson,
    SuccessCorrelationEngine,
)

# ===========================================================================
# Tests: Lesson
# ===========================================================================


class TestLesson:
    """Verifica la dataclass Lesson y sus serializaciones."""

    def test_to_dict_incluye_todos_los_campos(self):
        """to_dict expone category, lesson, failed_item, succeeded_item y source_session."""
        lesson = Lesson(
            category="path_correction",
            lesson="'A' no existe; usa 'B' en su lugar",
            failed_item="A",
            succeeded_item="B",
            source_session="s1",
        )
        d = lesson.to_dict()
        assert d["category"] == "path_correction"
        assert d["lesson"] == "'A' no existe; usa 'B' en su lugar"
        assert d["failed_item"] == "A"
        assert d["succeeded_item"] == "B"
        assert d["source_session"] == "s1"

    def test_source_session_default_vacia(self):
        """source_session por defecto es una cadena vacia."""
        lesson = Lesson(category="a", lesson="b", failed_item="c", succeeded_item="d")
        assert lesson.source_session == ""

    def test_to_marker_block_formato(self):
        """to_marker_block produce el bloque swarmind:learn con un bullet."""
        lesson = Lesson(
            category="path_correction",
            lesson="'A' no existe; usa 'B' en su lugar",
            failed_item="A",
            succeeded_item="B",
        )
        assert lesson.to_marker_block() == (
            "<!-- swarmind:learn:start -->\n"
            "- [path_correction] 'A' no existe; usa 'B' en su lugar\n"
            "<!-- swarmind:learn:end -->"
        )


# ===========================================================================
# Tests: learn()
# ===========================================================================


class TestLearn:
    """Verifica la derivacion del texto de la leccion por categoria."""

    def test_learn_path_correction(self):
        """path_correction: "'failed' no existe; usa 'succeeded' en su lugar"."""
        e = SuccessCorrelationEngine()
        lesson = e.learn("axion-formats", "axion-scala-common")
        assert lesson.category == "path_correction"
        assert lesson.lesson == "'axion-formats' no existe; usa 'axion-scala-common' en su lugar"
        assert lesson.failed_item == "axion-formats"
        assert lesson.succeeded_item == "axion-scala-common"

    def test_learn_search_scope(self):
        """search_scope: "Busca en 'succeeded' no en 'failed'"."""
        e = SuccessCorrelationEngine()
        lesson = e.learn("docs", "docs/src", category="search_scope")
        assert lesson.lesson == "Busca en 'docs/src' no en 'docs'"

    def test_learn_command_pattern(self):
        """command_pattern: "Usa 'succeeded' en vez de 'failed'"."""
        e = SuccessCorrelationEngine()
        lesson = e.learn("rm -rf", "trash-put", category="command_pattern")
        assert lesson.lesson == "Usa 'trash-put' en vez de 'rm -rf'"

    def test_learn_environment_fact(self):
        """environment_fact: "'succeeded' (disponible; 'failed' no)"."""
        e = SuccessCorrelationEngine()
        lesson = e.learn("tensorflow", "torch", category="environment_fact")
        assert lesson.lesson == "'torch' (disponible; 'tensorflow' no)"

    def test_learn_known_large_file(self):
        """known_large_file: "'succeeded' es un archivo grande, evita leerlo completo"."""
        e = SuccessCorrelationEngine()
        lesson = e.learn("data.bin", "data_sample.csv", category="known_large_file")
        assert lesson.lesson == "'data_sample.csv' es un archivo grande, evita leerlo completo"

    def test_learn_con_source_session(self):
        """learn registra la sesion de origen."""
        e = SuccessCorrelationEngine()
        lesson = e.learn("A", "B", source_session="sess-1")
        assert lesson.source_session == "sess-1"

    def test_learn_deduplica_pares_iguales(self):
        """Aprender el mismo par dos veces no duplica la leccion."""
        e = SuccessCorrelationEngine()
        e.learn("A", "B")
        e.learn("A", "B")
        assert len(e.get_lessons()) == 1

    def test_learn_retorna_la_lesson_creada(self):
        """learn retorna la Lesson creada (o existente)."""
        e = SuccessCorrelationEngine()
        l1 = e.learn("A", "B")
        l2 = e.learn("A", "B")
        assert isinstance(l1, Lesson)
        assert l2 is l1


# ===========================================================================
# Tests: get_lessons()
# ===========================================================================


class TestGetLessons:
    """Verifica el filtrado por categoria."""

    def test_filtra_por_categoria(self):
        """get_lessons(category) solo devuelve lecciones de esa categoria."""
        e = SuccessCorrelationEngine()
        e.learn("A", "B")
        e.learn("docs", "docs/src", category="search_scope")
        assert len(e.get_lessons("path_correction")) == 1
        assert len(e.get_lessons("search_scope")) == 1
        assert len(e.get_lessons()) == 2

    def test_categoria_sin_lecciones_retorna_vacia(self):
        """Una categoria sin lecciones retorna lista vacia."""
        e = SuccessCorrelationEngine()
        e.learn("A", "B")
        assert e.get_lessons("command_pattern") == []


# ===========================================================================
# Tests: apply_to_context()
# ===========================================================================


class TestApplyToContext:
    """Verifica la inyeccion idempotente de lecciones en el contexto."""

    def test_inyecta_bloque_en_texto_vacio(self):
        """apply_to_context('') genera el bloque marcado con las lecciones."""
        e = SuccessCorrelationEngine()
        e.learn("A", "B")
        resultado = e.apply_to_context("")
        assert resultado.startswith("<!-- swarmind:learn:start -->")
        assert "<!-- swarmind:learn:end -->" in resultado
        assert "- [path_correction] 'A' no existe; usa 'B' en su lugar" in resultado

    def test_idempotente_dos_llamadas_mismo_texto(self):
        """Dos llamadas seguidas producen el mismo texto (sin duplicados)."""
        e = SuccessCorrelationEngine()
        e.learn("A", "B")
        texto = "Contexto base del agente."
        primera = e.apply_to_context(texto)
        segunda = e.apply_to_context(primera)
        assert primera == segunda

    def test_idempotente_con_texto_con_bloque(self):
        """Si el texto ya trae un bloque, la segunda llamada no lo duplica."""
        e = SuccessCorrelationEngine()
        e.learn("A", "B")
        texto = "PRE\n<!-- swarmind:learn:start -->\n- [search_scope] vieja\n<!-- swarmind:learn:end -->\nPOST"
        primera = e.apply_to_context(texto)
        segunda = e.apply_to_context(primera)
        assert primera == segunda
        assert primera.count("<!-- swarmind:learn:start -->") == 1

    def test_preserva_texto_fuera_de_marcadores(self):
        """El texto previo al bloque se conserva intacto."""
        e = SuccessCorrelationEngine()
        e.learn("A", "B")
        texto = "Contexto base del agente."
        resultado = e.apply_to_context(texto)
        assert resultado.startswith("Contexto base del agente.")
        assert "Contexto base del agente." in resultado

    def test_reemplaza_contenido_entre_marcadores(self):
        """Con bloque existente, solo se reemplaza el contenido entre marcadores."""
        e = SuccessCorrelationEngine()
        e.learn("A", "B")
        texto = (
            "PRE\n"
            "<!-- swarmind:learn:start -->\n"
            "- [search_scope] leccion vieja\n"
            "<!-- swarmind:learn:end -->\n"
            "POST"
        )
        resultado = e.apply_to_context(texto)
        assert resultado.startswith("PRE")
        assert resultado.endswith("POST")
        assert "- [search_scope] leccion vieja" not in resultado
        assert "- [path_correction] 'A' no existe; usa 'B' en su lugar" in resultado

    def test_aplica_todas_las_lecciones(self):
        """El bloque incluye todas las lecciones aprendidas."""
        e = SuccessCorrelationEngine()
        e.learn("A", "B")
        e.learn("docs", "docs/src", category="search_scope")
        resultado = e.apply_to_context("")
        assert "- [path_correction] 'A' no existe; usa 'B' en su lugar" in resultado
        assert "- [search_scope] Busca en 'docs/src' no en 'docs'" in resultado


# ===========================================================================
# Tests: from_session_trace()
# ===========================================================================


class TestFromSessionTrace:
    """Verifica la correlacion fallo->exito a partir de un trace."""

    def test_deriva_path_correction(self):
        """Read X.java fallido + Read X.scala exitoso derivan path_correction."""
        e = SuccessCorrelationEngine()
        trace = [
            {"action": "Read", "item": "axion-formats/X.java", "status": "failed", "session": "s1"},
            {"action": "Read", "item": "axion-scala-common/X.scala", "status": "succeeded", "session": "s1"},
        ]
        lecciones = e.from_session_trace(trace)
        assert len(lecciones) == 1
        lesson = lecciones[0]
        assert lesson.category == "path_correction"
        assert lesson.failed_item == "axion-formats"
        assert lesson.succeeded_item == "axion-scala-common"
        assert lesson.lesson == "'axion-formats' no existe; usa 'axion-scala-common' en su lugar"

    def test_entradas_malformadas_se_omiten(self):
        """Entradas sin las claves requeridas se omiten sin romper el analisis."""
        e = SuccessCorrelationEngine()
        trace = [
            {"action": "Read", "status": "failed"},  # falta item
            {"action": "Read", "item": "mod-a/X.py", "status": "succeeded", "session": "s1"},
            {"action": "Read", "item": "mod-b/X.py", "status": "failed", "session": "s1"},
        ]
        lecciones = e.from_session_trace(trace)
        assert len(lecciones) == 1
        assert lecciones[0].failed_item == "mod-b"
        assert lecciones[0].succeeded_item == "mod-a"

    def test_sin_fallos_no_genera_lecciones(self):
        """Un trace sin acciones fallidas no genera lecciones."""
        e = SuccessCorrelationEngine()
        trace = [
            {"action": "Read", "item": "A", "status": "succeeded", "session": "s1"},
        ]
        assert e.from_session_trace(trace) == []

    def test_fallo_sin_exito_par_no_genera_leccion(self):
        """Una accion fallida sin correlato exitoso no genera leccion."""
        e = SuccessCorrelationEngine()
        trace = [
            {"action": "Read", "item": "X.java", "status": "failed", "session": "s1"},
        ]
        assert e.from_session_trace(trace) == []

    def test_lecciones_quedan_disponibles(self):
        """Las lecciones derivadas quedan almacenadas en el motor."""
        e = SuccessCorrelationEngine()
        trace = [
            {"action": "Read", "item": "axion-formats/X.java", "status": "failed", "session": "s1"},
            {"action": "Read", "item": "axion-scala-common/X.scala", "status": "succeeded", "session": "s1"},
        ]
        e.from_session_trace(trace)
        assert len(e.get_lessons("path_correction")) == 1


# ===========================================================================
# Tests: stats()
# ===========================================================================


class TestStats:
    """Verifica el conteo de lecciones por categoria."""

    def test_cuenta_por_categoria(self):
        """stats() agrupa el total de lecciones por categoria."""
        e = SuccessCorrelationEngine()
        e.learn("A", "B")
        e.learn("C", "D")
        e.learn("docs", "docs/src", category="search_scope")
        st = e.stats()
        assert st["path_correction"] == 2
        assert st["search_scope"] == 1
        assert st["total"] == 3

    def test_stats_motor_vacio(self):
        """Un motor sin lecciones reporta total 0."""
        e = SuccessCorrelationEngine()
        assert e.stats() == {"total": 0}
