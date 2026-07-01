"""Tests para TrajectoryCompressor."""
from __future__ import annotations


class TestCompressor:
    def test_short_conversation_unchanged(self, trajectory_compressor):
        conv = [{"role": "user", "content": f"msg {i}"} for i in range(5)]
        result = trajectory_compressor.compress(conv)
        assert len(result) == len(conv)

    def test_long_conversation_compressed(self, trajectory_compressor):
        conv = []
        for i in range(25):
            txt = f"Turn {i}: " + "content " * 10
            conv.append({"role": "user" if i % 2 == 0 else "assistant", "content": txt})
        result = trajectory_compressor.compress(conv)
        assert len(result) < len(conv)
        assert any(m.get("compressed") for m in result)
