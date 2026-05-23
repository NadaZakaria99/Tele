"""
Tests for rag_service/safety.py and chain.py

Tests the keyword fast-paths and state dict flow — no NIM calls required.
"""

import pytest
from rag_service.safety import SafetyRunnable, TopicRunnable, _OFF_TOPIC_KEYWORDS, _BANKING_KEYWORDS


class TestTopicRunnable:
    """Test the keyword fast-path layers — no NIM calls needed."""

    def test_banking_keyword_passes(self):
        for keyword in ["rtgs", "حساب", "kyc", "aml", "تسوية", "ائتمان"]:
            state = {"query": f"ما هو إجراء {keyword}", "blocked": False}
            result = TopicRunnable().invoke(state)
            assert not result.get("blocked"), f"Banking keyword '{keyword}' was incorrectly blocked"

    def test_off_topic_keyword_blocked(self):
        for keyword in _OFF_TOPIC_KEYWORDS[:3]:
            state = {"query": f"هل شاهدت {keyword} أمس", "blocked": False}
            result = TopicRunnable().invoke(state)
            assert result.get("blocked"), f"Off-topic keyword '{keyword}' was not blocked"

    def test_already_blocked_state_passes_through(self):
        """If blocked=True already set, topic runnable must not reset it."""
        state = {"query": "test", "blocked": True, "refusal": "blocked by safety"}
        result = TopicRunnable().invoke(state)
        assert result["blocked"] is True
        assert result["refusal"] == "blocked by safety"

    def test_state_dict_preserved(self):
        """Non-blocked state should preserve all existing keys."""
        state = {"query": "ما هو حساب التوفير", "blocked": False, "role": "teller"}
        result = TopicRunnable().invoke(state)
        assert "role" in result
        assert result["role"] == "teller"


class TestAnswerRunnable:
    """Test AnswerRunnable short-circuits on blocked state."""

    def test_blocked_state_returns_refusal(self):
        from rag_service.chain import AnswerRunnable
        state = {
            "query": "test",
            "blocked": True,
            "refusal": "محتوى غير مناسب",
            "role": "teller",
            "context_docs": [],
        }
        result = AnswerRunnable().invoke(state)
        assert result["answer"] == "محتوى غير مناسب"

    def test_empty_docs_returns_role_rejection(self):
        """Empty context_docs should return the role-specific rejection message."""
        from rag_service.chain import AnswerRunnable
        state = {
            "query": "test",
            "blocked": False,
            "role": "teller",
            "context_docs": [],
        }
        result = AnswerRunnable().invoke(state)
        # Should return a refusal / rejection, not an empty string
        assert len(result["answer"]) > 10
