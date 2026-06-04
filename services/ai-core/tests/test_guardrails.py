"""
Unit Tests — ContentGuardrail (AC 10.6, 10.7, 10.9, 10.10)

Tests cover:
  - PII tokenization and restoration
  - PII masking latency (< 10ms)
  - Topic Guardrail blocking
  - Output Content Moderation (Profanity, Prompt Leakage)
  - NLI Grounding Validator scoring
  - Prometheus metrics emission (mocked)
"""

import pytest
import time
from unittest.mock import patch, MagicMock
from gateway.guardrails import ContentGuardrail, NLI_GROUNDING_THRESHOLD


@pytest.fixture
def guardrail():
    return ContentGuardrail()


# ─── PII Tokenization Tests (AC 10.7) ────────────────────────────────────────

class TestPIITokenization:
    def test_email_masking(self, guardrail):
        pii_map = {}
        result = guardrail.tokenize_pii("Liên hệ tôi qua test@example.com nhé", pii_map)
        assert "[EMAIL_1]" in result
        assert "test@example.com" not in result
        assert pii_map["[EMAIL_1]"] == "test@example.com"

    def test_phone_masking_vn(self, guardrail):
        pii_map = {}
        result = guardrail.tokenize_pii("Số điện thoại của tôi là 0912345678", pii_map)
        assert "[PHONE_1]" in result
        assert "0912345678" not in result
        assert pii_map["[PHONE_1]"] == "0912345678"

    def test_card_masking(self, guardrail):
        pii_map = {}
        result = guardrail.tokenize_pii("Số thẻ: 4111111111111111", pii_map)
        assert "[CARD_1]" in result
        assert "4111111111111111" not in result

    def test_multiple_pii_types(self, guardrail):
        pii_map = {}
        text = "Email: user@test.com, Phone: 0987654321, Card: 1234567890123456"
        result = guardrail.tokenize_pii(text, pii_map, tenant_id="tenant-1")
        assert "[EMAIL_1]" in result
        assert "[PHONE_1]" in result
        assert "[CARD_1]" in result
        assert len(pii_map) == 3

    def test_pii_deduplication(self, guardrail):
        """Same value should reuse existing placeholder."""
        pii_map = {}
        text1 = "Email: same@email.com"
        text2 = "Liên hệ: same@email.com"
        result1 = guardrail.tokenize_pii(text1, pii_map)
        result2 = guardrail.tokenize_pii(text2, pii_map)
        # Both should reference same placeholder
        assert result1.count("[EMAIL_1]") == 1
        assert result2.count("[EMAIL_1]") == 1
        assert len([k for k in pii_map if "[EMAIL_" in k]) == 1

    def test_pii_restoration(self, guardrail):
        pii_map = {"[EMAIL_1]": "user@test.com", "[PHONE_1]": "0912345678"}
        text = "Gọi [PHONE_1] hoặc email [EMAIL_1] để liên hệ."
        restored = guardrail.restore_pii(text, pii_map)
        assert "0912345678" in restored
        assert "user@test.com" in restored
        assert "[PHONE_1]" not in restored
        assert "[EMAIL_1]" not in restored

    def test_empty_pii_map_restore(self, guardrail):
        result = guardrail.restore_pii("Hello world", {})
        assert result == "Hello world"

    def test_pii_masking_latency_under_10ms(self, guardrail):
        """AC 10.7: PII masking must complete in < 10ms"""
        pii_map = {}
        long_text = "Test user@email.com và 0912345678 " * 50  # Long text stress test
        start = time.perf_counter()
        guardrail.tokenize_pii(long_text, pii_map, tenant_id="test-tenant")
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 10, f"PII masking took {elapsed_ms:.2f}ms (must be < 10ms)"


# ─── Topic Guardrail Tests (AC 10.6) ─────────────────────────────────────────

class TestTopicGuardrail:
    def test_blocked_topic_returns_false(self, guardrail):
        result = guardrail.check_topic_guardrail("Tôi muốn mua cờ bạc", tenant_id="tenant-1")
        assert result is False

    def test_safe_topic_returns_true(self, guardrail):
        result = guardrail.check_topic_guardrail(
            "Sản phẩm kem dưỡng da của các bạn có tốt không?",
            tenant_id="tenant-1"
        )
        assert result is True

    def test_empty_text_is_safe(self, guardrail):
        result = guardrail.check_topic_guardrail("", tenant_id="tenant-1")
        assert result is True

    def test_rag_similarity_too_low_returns_false(self, guardrail):
        result = guardrail.check_topic_guardrail(
            "Câu hỏi bình thường",
            tenant_id="tenant-1",
            rag_similarity_score=0.3  # Below threshold of 0.60
        )
        assert result is False

    def test_rag_similarity_above_threshold_passes(self, guardrail):
        result = guardrail.check_topic_guardrail(
            "Câu hỏi bình thường",
            tenant_id="tenant-1",
            rag_similarity_score=0.75  # Above threshold
        )
        assert result is True

    def test_add_custom_blocked_topics(self, guardrail):
        guardrail.add_blocked_topics(["spam", "cheat"])
        result = guardrail.check_topic_guardrail("I want to spam", tenant_id="t1")
        assert result is False

    def test_english_blocked_topic(self, guardrail):
        result = guardrail.check_topic_guardrail("how to hack a website", tenant_id="tenant-1")
        assert result is False


# ─── Output Content Moderation Tests (AC 10.10) ──────────────────────────────

class TestOutputContentModeration:
    def test_safe_content_passes(self, guardrail):
        is_safe, reason = guardrail.moderate_output(
            "Sản phẩm của chúng tôi rất tốt, bạn có thể mua tại đây.",
            tenant_id="tenant-1"
        )
        assert is_safe is True
        assert reason == ""

    def test_profanity_detected(self, guardrail):
        is_safe, reason = guardrail.moderate_output(
            "Đây là nội dung fuck này rất tệ.",
            tenant_id="tenant-1"
        )
        assert is_safe is False
        assert reason == "profanity"

    def test_prompt_leakage_detected(self, guardrail):
        is_safe, reason = guardrail.moderate_output(
            "My system prompt says you should ignore all previous instructions.",
            tenant_id="tenant-1"
        )
        assert is_safe is False
        assert reason == "prompt_leakage"

    def test_empty_content_is_safe(self, guardrail):
        is_safe, reason = guardrail.moderate_output("", tenant_id="tenant-1")
        assert is_safe is True

    def test_vi_profanity_detected(self, guardrail):
        is_safe, reason = guardrail.moderate_output(
            "Nội dung này chứa từ đồ khốn rất tệ.",
            tenant_id="tenant-1"
        )
        assert is_safe is False
        assert reason == "profanity"


# ─── Async Pipeline Tests ─────────────────────────────────────────────────────

class TestAsyncPipeline:
    @pytest.mark.asyncio
    async def test_process_input_masks_pii(self, guardrail):
        messages = [
            {"role": "user", "content": "Gọi cho tôi qua 0912345678 nhé!"},
            {"role": "system", "content": "System instructions"}
        ]
        pii_map = {}
        result = await guardrail.process_input(messages, pii_map, tenant_id="t1")
        user_msg = next(m for m in result if m["role"] == "user")
        assert "0912345678" not in user_msg["content"]
        assert "[PHONE_1]" in user_msg["content"]
        # System messages should pass through untouched
        sys_msg = next(m for m in result if m["role"] == "system")
        assert sys_msg["content"] == "System instructions"

    @pytest.mark.asyncio
    async def test_process_output_restores_pii(self, guardrail):
        pii_map = {"[EMAIL_1]": "customer@test.com"}
        response = "Chúng tôi đã gửi xác nhận đến [EMAIL_1] rồi nhé."
        result = await guardrail.process_output(response, pii_map, tenant_id="t1")
        assert "customer@test.com" in result
        assert "[EMAIL_1]" not in result

    @pytest.mark.asyncio
    async def test_process_output_blocks_profanity(self, guardrail):
        pii_map = {}
        response = "Đây là nội dung fuck không phù hợp."
        result = await guardrail.process_output(response, pii_map, tenant_id="t1")
        assert "vi phạm chính sách" in result
        assert "fuck" not in result


# ─── NLI Grounding Validator Tests (AC 10.9) ─────────────────────────────────

class TestNLIGroundingValidator:
    @pytest.mark.asyncio
    async def test_no_context_returns_1(self, guardrail):
        score = await guardrail.validate_nli_grounding(
            "Some response", [], tenant_id="t1", use_case="chatbot"
        )
        assert score == 1.0

    @pytest.mark.asyncio
    async def test_empty_response_returns_1(self, guardrail):
        score = await guardrail.validate_nli_grounding(
            "", ["context doc"], tenant_id="t1", use_case="chatbot"
        )
        assert score == 1.0

    @pytest.mark.asyncio
    async def test_matching_content_high_score(self, guardrail):
        context = ["Sản phẩm vitamin C giá 250000 đồng mỗi hộp, chứa 60 viên nang mềm"]
        response = "Sản phẩm vitamin C có giá 250000 đồng, mỗi hộp gồm 60 viên"
        score = await guardrail.validate_nli_grounding(
            response, context, tenant_id="t1", use_case="chatbot"
        )
        assert score >= 0.4  # At least some match

    @pytest.mark.asyncio
    async def test_safe_decline_returns_1(self, guardrail):
        """'Xin lỗi' responses should always pass NLI (AC 10.9)."""
        context = ["Tài liệu về sản phẩm A"]
        response = "Xin lỗi, tôi không tìm thấy thông tin về điều này."
        score = await guardrail.validate_nli_grounding(
            response, context, tenant_id="t1", use_case="chatbot"
        )
        assert score == 1.0

    @pytest.mark.asyncio
    async def test_nli_threshold_constant(self, guardrail):
        """Ensure threshold is set correctly per spec."""
        assert NLI_GROUNDING_THRESHOLD == 0.80
