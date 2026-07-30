"""Tests para HermesBridge y CognitionSync."""
from __future__ import annotations


class TestHermesBridge:
    def test_initialization(self, hermes_bridge):
        status = hermes_bridge.get_status()
        assert "available" in status

    def test_sync_to_hermes_no_root(self, hermes_bridge):
        result = hermes_bridge.sync_to_hermes([])
        assert isinstance(result, int)


class TestCognition:
    def test_add_lesson(self, cognition_sync):
        lesson = cognition_sync.add_lesson(
            title="test", content="test", domain="test", tags=["test"],
        )
        assert lesson is not None
        assert lesson.title == "test"

    def test_get_lessons_by_domain(self, cognition_sync):
        lessons = cognition_sync.get_lessons_by_domain(domain="test", top_k=5)
        assert isinstance(lessons, list)
