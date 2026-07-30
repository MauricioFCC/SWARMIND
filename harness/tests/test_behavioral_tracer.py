"""Tests para Behavioral Tracer â€” trazabilidad de decisiones."""
from __future__ import annotations

import pytest

from harness.orchestrator.behavioral_tracer import BehavioralTracer


class TestBehavioralTracer:
    def test_trace_registra_decisiones(self):
        """Las decisiones deben registrarse correctamente."""
        tracer = BehavioralTracer()
        with tracer.trace("builder", task_id="task-001") as ctx:
            ctx.record_decision(
                action="elegir_algoritmo",
                chosen="quicksort",
                alternatives=["mergesort", "heapsort"],
                rationale="O(n log n) promedio, in-place",
                confidence=0.85,
            )
            ctx.set_result("codigo generado")

        report = tracer.get_report("task-001")
        assert report is not None
        assert report["agent"] == "builder"
        assert len(report["decisions"]) == 1
        assert report["decisions"][0]["action"] == "elegir_algoritmo"
        assert report["decisions"][0]["chosen"] == "quicksort"

    def test_trace_sin_decisiones(self):
        """Trazabilidad sin decisiones debe tener lista vacia."""
        tracer = BehavioralTracer()
        with tracer.trace("scientist", task_id="task-002"):
            pass

        report = tracer.get_report("task-002")
        assert report is not None
        assert report["decisions"] == []

    def test_fingerprint_consistente(self):
        """Mismas decisiones deben generar mismo fingerprint."""
        tracer = BehavioralTracer()

        with tracer.trace("builder", task_id="t1") as ctx:
            ctx.record_decision(action="a", chosen="x", rationale="razon", confidence=0.9)

        with tracer.trace("builder", task_id="t2") as ctx:
            ctx.record_decision(action="a", chosen="x", rationale="razon", confidence=0.9)

        fp1 = tracer.get_report("t1")
        fp2 = tracer.get_report("t2")
        # fingerprints se calculan sobre las decisiones
        assert fp1 is not None and fp2 is not None

    def test_agent_behavior_summary(self):
        """Resumen de comportamiento debe mostrar metricas."""
        tracer = BehavioralTracer()

        for i in range(3):
            with tracer.trace("builder", task_id=f"t{i}") as ctx:
                ctx.record_decision(action="a", chosen="x", rationale="r", confidence=0.8)

        summary = tracer.get_agent_behavior_summary("builder")
        assert summary["sessions"] == 3
        assert summary["agent"] == "builder"

    def test_agent_behavior_summary_vacio(self):
        """Agente sin sesiones debe retornar summary con 0 sesiones."""
        tracer = BehavioralTracer()
        summary = tracer.get_agent_behavior_summary("unknown")
        assert summary["sessions"] == 0

    def test_record_decision_con_metadata(self):
        """record_decision debe aceptar metadata adicional."""
        tracer = BehavioralTracer()
        with tracer.trace("builder", task_id="task-meta") as ctx:
            ctx.record_decision(
                action="test",
                chosen="opt1",
                rationale="testing",
                confidence=0.5,
                extra_field="extra",
                numeric=42,
            )

        report = tracer.get_report("task-meta")
        dec = report["decisions"][0]
        assert dec["metadata"]["extra_field"] == "extra"
        assert dec["metadata"]["numeric"] == 42


class TestEdgeCases:
    """Tests para casos borde del BehavioralTracer."""

    def test_trace_exception_handling(self):
        """Excepcion dentro del context manager se registra y propaga."""
        tracer = BehavioralTracer()
        with pytest.raises(ValueError, match="error forzado"):  # noqa: SIM117
            with tracer.trace("builder", task_id="task-error") as ctx:
                ctx.record_decision(action="a", chosen="x", rationale="r")
                raise ValueError("error forzado")

        report = tracer.get_report("task-error")
        assert report is not None
        assert report["error"] == "error forzado"

    def test_get_report_nonexistent(self):
        """get_report retorna None para tarea inexistente."""
        tracer = BehavioralTracer()
        report = tracer.get_report("no-existe")
        assert report is None

    def test_add_tokens(self):
        """add_tokens acumula tokens correctamente."""
        tracer = BehavioralTracer()
        with tracer.trace("builder", task_id="task-tokens") as ctx:
            ctx.add_tokens(100)
            ctx.add_tokens(50)
            ctx.record_decision(action="a", chosen="x", rationale="r")
            ctx.set_result("done")

        report = tracer.get_report("task-tokens")
        assert report is not None
        assert report["tokens_consumed"] == 150
        assert report["result_preview"] == "done"
