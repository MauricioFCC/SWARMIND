"""Tests para cue_ledger — memoria cue-anchored con dedup (ADR-0074).

Frontera (arXiv 2607.20972): ledger por sesion que inyecta solo el indice
compacto (cue + procedencia), dedup de inyecciones repetidas, staleness
check por hash del source y reset en compaction. Medido: -42% tokens,
grep/find -54%, costo -30%.
"""


from harness.memory_rag.cue_ledger import (
    CueLedger,
)


def test_register_and_render_index() -> None:
    """El indice compacto muestra cue + procedencia, sin contenido completo."""
    ledger = CueLedger()
    ledger.register("regla TST 80%", source="harness/rules.md")
    index = ledger.render_index()
    assert "regla TST 80%" in index
    assert "harness/rules.md" in index
    assert len(index) < 400  # cue-anchored: compacto


def test_inject_dedups_repeated_entries() -> None:
    """Inyectar 2 veces el mismo cue: la 2a retorna vacio (no re-inyecta)."""
    ledger = CueLedger()
    ledger.register("modelo MLA reduce KV", source="adr.md")
    first = ledger.inject("s1")
    second = ledger.inject("s1")
    assert "MLA" in first
    assert second == ""
    assert ledger.dedup_hits == 1


def test_staleness_detects_changed_source(tmp_path) -> None:
    """Si el source cambia (mtime), el cue queda stale y se re-lee."""
    f = tmp_path / "facts.md"
    f.write_text("v1: regla original", encoding="utf-8")
    ledger = CueLedger(clock=lambda: 1000.0)
    ledger.register("regla v1", source=str(f))
    f.write_text("v2: regla nueva", encoding="utf-8")
    stale = ledger.stale_cues()
    assert any(c.cue == "regla v1" for c in stale)


def test_reset_on_compaction_clears_injections() -> None:
    """reset() (tras compaction) limpia el dedup para re-inyectar lo vivo."""
    ledger = CueLedger()
    ledger.register("hecho clave", source="x.md")
    ledger.inject("s1")
    ledger.reset()
    assert ledger.dedup_hits == 0
    again = ledger.inject("s1")
    assert "hecho clave" in again


def test_savings_metric() -> None:
    """tokens_saved estima el ahorro por dedup (cue vs contenido completo)."""
    ledger = CueLedger()
    ledger.register("fact", source="s.md")
    ledger.inject("s1")
    ledger.inject("s1")
    assert ledger.tokens_saved > 0


def test_empty_ledger_renders_empty() -> None:
    """Ledger vacio renderiza indice vacio sin error."""
    assert CueLedger().render_index() == ""
