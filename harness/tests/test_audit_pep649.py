"""Tests de la auditoría PEP 649 (detección + baseline + gate)."""

from __future__ import annotations

import json

from scripts import audit_pep649 as audit

SAMPLE = '''
from typing import get_type_hints

class Outer:
    class Inner:
        def method(self):
            return self.__annotations__

def plain():
    return get_type_hints(Outer)

def sig(fn):
    import inspect
    return inspect.signature(fn)
'''


class TestScan:
    """Detección de los tres tipos de introspección."""

    def test_detects_all_kinds_with_qualnames(self, tmp_path):
        """get_type_hints/__annotations__/signature se clasifican y anidan."""
        source = tmp_path / "mod.py"
        source.write_text(SAMPLE, encoding="utf-8")
        hits = audit.scan_file(source, root=tmp_path)
        kinds = {(hit.qualname, hit.kind) for hit in hits}
        assert ("Outer.Inner.method", "raw-annotations") in kinds
        assert ("plain", "runtime-eval") in kinds
        assert ("sig", "signature") in kinds

    def test_ignores_syntax_errors(self, tmp_path):
        """Un archivo con sintaxis inválida no rompe el barrido."""
        source = tmp_path / "bad.py"
        source.write_text("def broken(:\n", encoding="utf-8")
        assert audit.scan_file(source, root=tmp_path) == []

    def test_scan_tree_excludes_tests(self, tmp_path):
        """Los tests quedan fuera del alcance (introspección deliberada)."""
        (tmp_path / "harness" / "tests").mkdir(parents=True)
        (tmp_path / "harness" / "core.py").write_text(
            "from typing import get_type_hints\nget_type_hints(int)\n",
            encoding="utf-8",
        )
        (tmp_path / "harness" / "tests" / "test_core.py").write_text(
            "from typing import get_type_hints\n", encoding="utf-8"
        )
        hits = audit.scan_tree(("harness",), root=tmp_path)
        assert [hit.path for hit in hits] == ["harness/core.py"]


class TestEvaluate:
    """Ratchet: nuevos usos fallan, usos registrados pasan."""

    def _hit(self, qualname: str = "f", kind: str = "signature") -> audit.Hit:
        return audit.Hit(path="harness/x.py", qualname=qualname, kind=kind, line=10)

    def test_new_usage_fails(self):
        """Un uso no registrado es un fallo accionable."""
        failures, warnings = audit.evaluate([self._hit()], {})
        assert failures == [
            "uso nuevo sin registrar: harness/x.py::f::signature (linea 10)"
        ]
        assert warnings == []

    def test_registered_with_rationale_passes(self):
        """Registrado y justificado no falla."""
        baseline = {self._hit().key: "solo lee firmas"}
        assert audit.evaluate([self._hit()], baseline) == ([], [])

    def test_registered_without_rationale_fails(self):
        """Registrar sin justificar no vale (deuda disfrazada)."""
        failures, _ = audit.evaluate([self._hit()], {self._hit().key: "  "})
        assert failures == ["uso sin justificar: harness/x.py::f::signature"]

    def test_stale_entry_is_warning_only(self):
        """Una entrada del baseline que ya no existe se avisa, no falla."""
        failures, warnings = audit.evaluate([], {"harness/x.py::f::signature": "ok"})
        assert failures == []
        assert warnings == ["harness/x.py::f::signature"]


class TestBaseline:
    """Persistencia del baseline."""

    def test_roundtrip_preserves_rationale(self, tmp_path, monkeypatch):
        """Al reescribir no se pierde la justificación existente."""
        target = tmp_path / "pep649_baseline.json"
        monkeypatch.setattr(audit, "BASELINE_PATH", target)
        hit = audit.Hit(path="harness/x.py", qualname="f", kind="signature", line=1)
        target.write_text(
            json.dumps({"version": 1, "entries": [{"key": hit.key, "rationale": "ok"}]}),
            encoding="utf-8",
        )
        audit.write_baseline([hit])
        assert audit.load_baseline()[hit.key] == "ok"

    def test_missing_baseline_is_empty(self, tmp_path, monkeypatch):
        """Baseline ausente equivale a cero usos registrados."""
        monkeypatch.setattr(audit, "BASELINE_PATH", tmp_path / "nope.json")
        assert audit.load_baseline() == {}

    def test_current_repo_is_registered(self):
        """El repo actual no tiene usos sin registrar (gate en verde)."""
        failures, _ = audit.evaluate(audit.scan_tree(), audit.load_baseline())
        assert failures == []
