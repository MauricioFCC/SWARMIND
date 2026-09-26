"""Tests para supply_chain_gate + slop_score (ADR-0097, mesa 2da).

Triple audit (GenTrust/Socket/Snyk): secret-scan (gitleaks-like) +
patrones inseguros (eval/exec/pickle) + SBOM check, conectable al
skill-auditor. Anti-slop: score de genericidad/hedging en outputs
(extension de vibe-gate) con umbral documentado.
"""


from harness.validation.supply_chain_gate import (
    SupplyReport,
    supply_chain_gate,
)
from harness.validation.vibe_review_gate import slop_score


def test_supply_clean_passes(tmp_path) -> None:
    """Archivo limpio pasa sin hallazgos."""
    f = tmp_path / "ok.py"
    f.write_text("x = 1\n", encoding="utf-8")
    report = supply_chain_gate([f])
    assert isinstance(report, SupplyReport)
    assert report.passed is True
    assert report.findings == ()


def test_supply_detects_secret(tmp_path) -> None:
    """API key hardcodeada se detecta con archivo:linea."""
    f = tmp_path / "bad.py"
    f.write_text('KEY = "sk-abcdefgh12345678"\n', encoding="utf-8")
    report = supply_chain_gate([f])
    assert report.passed is False
    assert any("bad.py:1" in finding for finding in report.findings)


def test_supply_detects_unsafe_pattern(tmp_path) -> None:
    """eval/exec/pickle se marcan (inseguros)."""
    f = tmp_path / "risky.py"
    f.write_text("result = eval(user_input)\n", encoding="utf-8")
    report = supply_chain_gate([f])
    assert report.passed is False
    assert any("eval" in finding for finding in report.findings)


def test_supply_missing_file_skipped(tmp_path) -> None:
    """Archivo inexistente se ignora (no crashea)."""
    report = supply_chain_gate([tmp_path / "no-existe.py"])
    assert report.passed is True


def test_supply_empty_list_passes() -> None:
    """Sin archivos: pass vacuo."""
    assert supply_chain_gate([]).passed is True


def test_slop_clean_technical() -> None:
    """Texto tecnico preciso tiene slop bajo."""
    text = (
        "The function returns None when the input list is empty. "
        "It raises ValueError for negative timeouts."
    )
    assert slop_score(text) < 0.3


def test_slop_hedging_high() -> None:
    """Hedging + cliches IA dan slop alto."""
    text = (
        "Delve into this tapestry: it might be worth considering that "
        "perhaps the landscape could potentially improve."
    )
    assert slop_score(text) > 0.5


def test_slop_empty_zero() -> None:
    """Vacio puntua 0."""
    assert slop_score("") == 0.0
    assert slop_score("   ") == 0.0
