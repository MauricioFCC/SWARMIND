"""Tests de concurrencia de ``EvalSuite.run`` (pool de hilos, orden estable)."""

from __future__ import annotations

import threading
import time

from harness.evals import EvalResult, EvalSuite


def _result(metric: str, value: float = 0.9) -> EvalResult:
    """EvalResult mínimo para los tests."""
    return EvalResult(layer="llm", metric=metric, value=value, threshold=0.5)


class TestConcurrency:
    """``run(concurrency>1)`` ejecuta callables en paralelo sin romper orden."""

    def test_preserves_declaration_order(self):
        """Los resultados mantienen el orden de la suite, no el de finalización."""
        suite = EvalSuite(name="orden")
        suite.add_eval(lambda: [_result("a")])
        suite.add_eval(lambda: [_result("b")])
        suite.add_eval(lambda: [_result("c")])

        report = suite.run(concurrency=3)

        assert [result.metric for result in report.results] == ["a", "b", "c"]

    def test_mixed_direct_and_callable(self):
        """EvalResult directos y callables se intercalan en orden."""
        suite = EvalSuite(name="mixto")
        suite.add_eval(_result("directo-1"))
        suite.add_eval(lambda: [_result("callable")])
        suite.add_eval(_result("directo-2"))

        report = suite.run(concurrency=2)

        assert [result.metric for result in report.results] == [
            "directo-1",
            "callable",
            "directo-2",
        ]

    def test_callables_run_in_parallel(self):
        """Con 3 callables y concurrencia 3, los tres hilos se solapan."""
        suite = EvalSuite(name="paralelo")
        barrier = threading.Barrier(3, timeout=2.0)

        def _sync(metric: str):
            def _fn() -> list[EvalResult]:
                barrier.wait()  # si fueran secuenciales, timeout
                return [_result(metric)]

            return _fn

        for metric in ("a", "b", "c"):
            suite.add_eval(_sync(metric))

        started = time.monotonic()
        report = suite.run(concurrency=3)

        assert report.total == 3
        assert time.monotonic() - started < 2.0

    def test_failure_of_one_callable_does_not_abort(self):
        """Una excepción se registra y el resto de evaluaciones corre."""
        suite = EvalSuite(name="fallo")
        suite.add_eval(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        suite.add_eval(lambda: [_result("ok")])

        report = suite.run(concurrency=2)

        assert [result.metric for result in report.results] == ["ok"]

    def test_invalid_return_type_is_ignored(self):
        """Un callable que no devuelve lista no aporta resultados."""
        suite = EvalSuite(name="invalido")
        suite.add_eval(lambda: "no-es-lista")
        suite.add_eval(lambda: [_result("ok")])

        report = suite.run(concurrency=2)

        assert [result.metric for result in report.results] == ["ok"]

    def test_sequential_equivalent_to_concurrency_one(self):
        """Concurrency 1 produce el mismo reporte que el modo secuencial."""
        suite = EvalSuite(name="equivalente")
        suite.add_eval(lambda: [_result("a")])
        suite.add_eval(_result("b"))

        sequential = suite.run()
        parallel = suite.run(concurrency=1)

        assert [r.metric for r in sequential.results] == [
            r.metric for r in parallel.results
        ]
