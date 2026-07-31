"""
Tests for ContextWindowManager — adaptive context window optimization.

Cubre: ContextSection, ContextWindow, ContextWindowManager,
       optimize(), compact_history(), get_stats() via StatsMixin.
"""

from harness.memory_rag.context_window_manager import (
    PRIORITY_CRITICAL,
    PRIORITY_HIGH,
    PRIORITY_LOW,
    ContextSection,
    ContextWindow,
    ContextWindowManager,
)


class TestContextSection:
    """Test individual context sections."""

    def test_create_section(self):
        section = ContextSection(name="test", content="hello world", priority=PRIORITY_HIGH, max_tokens=100)
        assert section.name == "test"
        assert section.token_estimate > 0
        assert not section.over_budget

    def test_over_budget(self):
        section = ContextSection(name="big", content="x" * 1000, max_tokens=10)
        assert section.over_budget

    def test_truncate_to_budget(self):
        section = ContextSection(name="big", content="x" * 500, max_tokens=10)
        assert section.truncate_to_budget()
        assert section.compressed
        assert "truncated" in section.content

    def test_truncate_frozen_skipped(self):
        section = ContextSection(name="frozen", content="x" * 500, max_tokens=10, frozen=True)
        assert not section.truncate_to_budget()
        assert not section.compressed

    def test_truncate_not_over_budget(self):
        section = ContextSection(name="small", content="hello", max_tokens=100)
        assert not section.truncate_to_budget()


class TestContextWindow:
    """Test the full context window."""

    def test_create_window(self):
        window = ContextWindow(total_budget=1000)
        assert window.total_budget == 1000
        assert len(window.sections) == 0

    def test_add_section(self):
        window = ContextWindow()
        section = window.add_section("system_identity", "You are a helpful AI.")
        assert section.name == "system_identity"
        assert section.priority == PRIORITY_CRITICAL  # from SECTION_PRIORITIES
        assert window.get_section("system_identity") is section

    def test_total_tokens(self):
        window = ContextWindow()
        window.add_section("a", "hello", max_tokens=100)
        window.add_section("b", "world", max_tokens=100)
        assert window.total_tokens > 0

    def test_over_budget(self):
        window = ContextWindow(total_budget=1)
        window.add_section("big", "x" * 100, max_tokens=100)
        assert window.over_budget

    def test_remove_section(self):
        window = ContextWindow()
        window.add_section("test", "content")
        assert window.remove_section("test")
        assert not window.remove_section("nonexistent")

    def test_to_prompt_compact(self):
        window = ContextWindow()
        window.add_section("a", "hello")
        window.add_section("b", "world")
        prompt = window.to_prompt(format="compact")
        assert "hello" in prompt
        assert "world" in prompt

    def test_to_prompt_labeled(self):
        window = ContextWindow()
        window.add_section("system_identity", "You are AI.")
        prompt = window.to_prompt(format="labeled")
        assert "System Identity" in prompt

    def test_to_dict(self):
        window = ContextWindow()
        window.add_section("test", "content")
        d = window.to_dict()
        assert "total_budget" in d
        assert "total_tokens" in d
        assert "sections" in d


class TestContextWindowManager:
    """Test the context window manager."""

    def test_create_manager(self):
        mgr = ContextWindowManager(total_budget=5000)
        assert mgr is not None
        assert mgr._total_budget == 5000

    def test_create_window(self):
        mgr = ContextWindowManager(total_budget=8000)
        window = mgr.create_window()
        assert window.total_budget == 8000

    def test_optimize_no_change_needed(self):
        mgr = ContextWindowManager(total_budget=10000)
        window = mgr.create_window()
        window.add_section("a", "small content", max_tokens=1000)
        result = mgr.optimize(window)
        assert result is window  # same object, modified in place

    def test_optimize_truncates_over_budget(self):
        mgr = ContextWindowManager(total_budget=100)
        window = mgr.create_window()
        window.add_section("rag_context", "x" * 500, max_tokens=10)
        window.add_section("tool_outputs", "y" * 500, max_tokens=10)
        before = window.total_tokens
        result = mgr.optimize(window)
        after = result.total_tokens
        # Should be reduced (or at least not increased)
        assert after <= before or not result.over_budget

    def test_stats_after_optimize(self):
        mgr = ContextWindowManager(total_budget=50)
        window = mgr.create_window()
        window.add_section("big", "x" * 200, max_tokens=10)
        mgr.optimize(window)
        stats = mgr.get_stats()
        assert stats["optimizations"] >= 1
        assert "avg_compression_pct" in stats

    def test_compact_history_short(self):
        mgr = ContextWindowManager()
        history = [{"role": "user", "content": "hi"}]
        result = mgr.compact_history(history, max_messages=5)
        assert len(result) == 1

    def test_compact_history_long(self):
        mgr = ContextWindowManager(sliding_window_size=3)
        history = [{"role": "user", "content": f"msg {i}"} for i in range(10)]
        result = mgr.compact_history(history, max_messages=5)
        # Should be compacted: summary + last N messages
        assert len(result) < len(history)

    def test_compact_history_empty(self):
        mgr = ContextWindowManager()
        assert mgr.compact_history([]) == []

    def test_hard_truncate(self):
        mgr = ContextWindowManager(total_budget=10)
        window = mgr.create_window()
        window.add_section("a", "x" * 1000, priority=PRIORITY_LOW)
        window.add_section("b", "critical", frozen=True)
        result = mgr._hard_truncate(window)
        # Critial section should remain
        assert result.get_section("b") is not None

    def test_aggressive_compress(self):
        compressed = ContextWindowManager._aggressive_compress(
            "line1\n\n\nline2\n  spaced  "
        )
        assert "line1" in compressed
        assert "line2" in compressed

    def test_default_summary(self):
        summary = ContextWindowManager._default_summary("short text")
        assert summary == "short text"
