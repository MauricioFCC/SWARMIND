"""Tests para CacheGeometry — Cache Geometry Discipline (ADR-0034, Idea 2).

Cubre: clasificación static/dynamic, reorder preservando contenido, hash de
prefijo estable, detección de invalidación silenciosa.
"""


from harness.memory_rag.cache_geometry import CacheGeometry


class TestClassify:
    """Clasificación de bloques en estáticos y dinámicos."""

    def test_instruction_is_static(self):
        geo = CacheGeometry()
        assert geo.classify("Eres un agente experto en Rust.") == "static"

    def test_template_variable_is_dynamic(self):
        geo = CacheGeometry()
        assert geo.classify("Contexto: {{user_message}}") == "dynamic"

    def test_timestamp_is_dynamic(self):
        geo = CacheGeometry()
        assert geo.classify("Ejecutado: 2026-07-31T10:00:00Z") == "dynamic"

    def test_uuid_is_dynamic(self):
        geo = CacheGeometry()
        assert geo.classify("session: 123e4567-e89b-12d3-a456-426614174000") == "dynamic"

    def test_markdown_heading_is_static(self):
        geo = CacheGeometry()
        assert geo.classify("## Instrucciones de seguridad") == "static"


class TestReorder:
    """Reordenamiento estático-primero preservando contenido."""

    def test_reorder_puts_static_first(self):
        geo = CacheGeometry()
        blocks = [
            "Contexto: {{tarea}}",
            "## Instrucciones",
            "Reglas: no modificar src/",
            "Fecha: 2026-07-31",
        ]
        out = geo.reorder(blocks)
        assert out[0] == "## Instrucciones"
        assert out[1] == "Reglas: no modificar src/"
        assert out[-1] == "Fecha: 2026-07-31"

    def test_reorder_preserves_all_content(self):
        geo = CacheGeometry()
        blocks = ["A{{x}}", "B", "C{{y}}", "D"]
        out = geo.reorder(blocks)
        assert sorted(out) == sorted(blocks)

    def test_empty_blocks(self):
        geo = CacheGeometry()
        assert geo.reorder([]) == []

    def test_static_prefix_stable(self):
        geo = CacheGeometry()
        blocks1 = ["## Sys", "Regla", "{{dinamico}}"]
        blocks2 = ["## Sys", "Regla", "{{dinamico2}}"]
        h1 = geo.static_prefix_hash(blocks1)
        h2 = geo.static_prefix_hash(blocks2)
        assert h1 == h2

    def test_static_change_detects_invalidation(self):
        geo = CacheGeometry()
        blocks1 = ["## Sys", "Regla vieja", "{{dinamico}}"]
        blocks2 = ["## Sys", "Regla nueva", "{{dinamico}}"]
        h1 = geo.static_prefix_hash(blocks1)
        h2 = geo.static_prefix_hash(blocks2)
        assert h1 != h2


class TestReport:
    """Reporte de geometría de cache sobre requests."""

    def test_report_static_prefix_changed(self):
        geo = CacheGeometry()
        reqs = [
            {"blocks": ["## Sys", "Regla A", "{{x}}"]},
            {"blocks": ["## Sys", "Regla A", "{{y}}"]},
            {"blocks": ["## Sys", "Regla B", "{{z}}"]},
        ]
        report = geo.report(reqs)
        assert report["total_requests"] == 3
        assert report["static_prefix_changes"] == 1
        assert report["prefix_changed"] is True

    def test_report_no_change(self):
        geo = CacheGeometry()
        reqs = [
            {"blocks": ["## Sys", "Regla", "{{x}}"]},
            {"blocks": ["## Sys", "Regla", "{{y}}"]},
        ]
        report = geo.report(reqs)
        assert report["static_prefix_changes"] == 0
        assert report["prefix_changed"] is False

    def test_report_single_request(self):
        geo = CacheGeometry()
        report = geo.report([{"blocks": ["A", "{{b}}"]}])
        assert report["total_requests"] == 1
        assert report["prefix_changed"] is False
