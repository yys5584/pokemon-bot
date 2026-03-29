"""Tests for CS 문의 시스템."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


# ─── cs_queries 카테고리/상수 테스트 ───

class TestCSCategories:
    def test_category_labels_exist(self):
        from database.cs_queries import CATEGORIES
        assert "bug" in CATEGORIES
        assert "suggestion" in CATEGORIES
        assert "premium" in CATEGORIES
        assert "other" in CATEGORIES

    def test_category_labels_are_korean(self):
        from database.cs_queries import CATEGORIES
        for key, label in CATEGORIES.items():
            assert isinstance(label, str)
            assert len(label) > 0


# ─── api_cs 헬퍼 테스트 ───

class TestAPICSHelpers:
    def test_is_admin_true(self):
        from dashboard.api_cs import _is_admin
        import config
        if config.ADMIN_IDS:
            assert _is_admin(config.ADMIN_IDS[0]) is True

    def test_is_admin_false(self):
        from dashboard.api_cs import _is_admin
        assert _is_admin(9999999999) is False

    def test_time_ago_none(self):
        from dashboard.api_cs import _time_ago
        assert _time_ago(None) == ""

    def test_time_ago_recent(self):
        from dashboard.api_cs import _time_ago
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc)
        assert _time_ago(now) == "방금"

    def test_time_ago_minutes(self):
        from dashboard.api_cs import _time_ago
        import datetime
        dt = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=5)
        result = _time_ago(dt)
        assert "분 전" in result

    def test_time_ago_hours(self):
        from dashboard.api_cs import _time_ago
        import datetime
        dt = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=3)
        result = _time_ago(dt)
        assert "시간 전" in result

    def test_time_ago_days(self):
        from dashboard.api_cs import _time_ago
        import datetime
        dt = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=3)
        result = _time_ago(dt)
        assert "일 전" in result

    def test_time_ago_old(self):
        from dashboard.api_cs import _time_ago
        import datetime
        dt = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)
        result = _time_ago(dt)
        assert "/" in result  # MM/DD 형식

    def test_status_labels(self):
        from dashboard.api_cs import STATUS_LABELS
        assert STATUS_LABELS["open"] == "대기중"
        assert STATUS_LABELS["resolved"] == "완료"

    def test_category_labels(self):
        from dashboard.api_cs import CATEGORY_LABELS
        assert CATEGORY_LABELS["bug"] == "버그신고"
        assert CATEGORY_LABELS["premium"] == "프리미엄"


# ─── dm_cs 핸들러 로직 테스트 ───

class TestDMCSHandler:
    def test_categories_list(self):
        from handlers.dm_cs import CATEGORIES, CAT_LABELS
        assert len(CATEGORIES) == 4
        assert CAT_LABELS["bug"] == "🐛 버그신고"
        assert CAT_LABELS["suggestion"] == "💡 개선제안"

    @pytest.mark.asyncio
    async def test_cs_text_input_no_state(self):
        """cs_state 없으면 False 반환."""
        from handlers.dm_cs import cs_text_input
        update = MagicMock()
        context = MagicMock()
        context.user_data = {}
        result = await cs_text_input(update, context)
        assert result is False

    @pytest.mark.asyncio
    async def test_cs_text_input_cancel(self):
        """'취소' 입력 시 상태 정리."""
        from handlers.dm_cs import cs_text_input
        update = MagicMock()
        update.message.text = "취소"
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        context.user_data = {"cs_state": {"step": "title", "category": "bug"}}
        result = await cs_text_input(update, context)
        assert result is True
        assert "cs_state" not in context.user_data

    @pytest.mark.asyncio
    async def test_cs_text_input_title_too_long(self):
        """제목 100자 초과."""
        from handlers.dm_cs import cs_text_input
        update = MagicMock()
        update.message.text = "a" * 101
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        context.user_data = {"cs_state": {"step": "title", "category": "bug"}}
        result = await cs_text_input(update, context)
        assert result is True
        update.message.reply_text.assert_called_once()
        assert "100자" in update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_cs_text_input_title_too_short(self):
        """제목 1글자."""
        from handlers.dm_cs import cs_text_input
        update = MagicMock()
        update.message.text = "a"
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        context.user_data = {"cs_state": {"step": "title", "category": "bug"}}
        result = await cs_text_input(update, context)
        assert result is True
        assert "2글자" in update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_cs_text_input_title_success(self):
        """제목 정상 입력 → step=content로 전환."""
        from handlers.dm_cs import cs_text_input
        update = MagicMock()
        update.message.text = "버그 발생"
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        state = {"step": "title", "category": "bug"}
        context.user_data = {"cs_state": state}
        result = await cs_text_input(update, context)
        assert result is True
        assert state["step"] == "content"
        assert state["title"] == "버그 발생"

    @pytest.mark.asyncio
    async def test_cs_text_input_content_too_long(self):
        """내용 2000자 초과."""
        from handlers.dm_cs import cs_text_input
        update = MagicMock()
        update.message.text = "x" * 2001
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        context.user_data = {"cs_state": {"step": "content", "category": "bug", "title": "test"}}
        result = await cs_text_input(update, context)
        assert result is True
        assert "2000자" in update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_cs_text_input_content_success(self):
        """내용 정상 입력 → DB 저장 + 상태 정리."""
        from handlers.dm_cs import cs_text_input
        update = MagicMock()
        update.message.text = "이로치 전환 안 됩니다"
        update.message.reply_text = AsyncMock()
        update.effective_user.id = 12345
        update.effective_user.first_name = "TestUser"
        update.effective_user.username = "testuser"
        context = MagicMock()
        context.user_data = {"cs_state": {"step": "content", "category": "bug", "title": "버그"}}
        context.bot.send_message = AsyncMock()

        with patch("handlers.dm_cs.csq") as mock_csq:
            mock_csq.create_inquiry = AsyncMock(return_value=42)
            result = await cs_text_input(update, context)

        assert result is True
        assert "cs_state" not in context.user_data
        mock_csq.create_inquiry.assert_called_once_with(
            12345, "TestUser", "bug", "버그", "이로치 전환 안 됩니다"
        )
        # 유저에게 접수 완료 메시지
        reply_text = update.message.reply_text.call_args[0][0]
        assert "#42" in reply_text
        assert "접수 완료" in reply_text
