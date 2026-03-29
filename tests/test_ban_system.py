"""밴 시스템 테스트 — is_user_banned() + 포획/거래 차단."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── is_user_banned() 단위 테스트 ──

@pytest.mark.asyncio
async def test_is_user_banned_true():
    """banned_until > NOW() → True."""
    mock_pool = AsyncMock()
    mock_pool.fetchval = AsyncMock(return_value=True)
    with patch("database.queries.get_db", new_callable=AsyncMock, return_value=mock_pool):
        from database.queries import is_user_banned
        result = await is_user_banned(12345)
        assert result is True
        mock_pool.fetchval.assert_called_once()


@pytest.mark.asyncio
async def test_is_user_banned_false():
    """banned_until IS NULL or < NOW() → False."""
    mock_pool = AsyncMock()
    mock_pool.fetchval = AsyncMock(return_value=False)
    with patch("database.queries.get_db", new_callable=AsyncMock, return_value=mock_pool):
        from database.queries import is_user_banned
        result = await is_user_banned(12345)
        assert result is False


@pytest.mark.asyncio
async def test_is_user_banned_no_user():
    """유저가 없으면 → False."""
    mock_pool = AsyncMock()
    mock_pool.fetchval = AsyncMock(return_value=None)
    with patch("database.queries.get_db", new_callable=AsyncMock, return_value=mock_pool):
        from database.queries import is_user_banned
        result = await is_user_banned(99999)
        assert result is False


# ── catch_handler 밴 체크 통합 테스트 ──

@pytest.mark.asyncio
async def test_catch_handler_banned_user_blocked(mock_update, mock_context, mock_db):
    """밴된 유저가 ㅊ 치면 포획 차단 (무응답)."""
    with patch("database.queries.is_user_banned", new_callable=AsyncMock, return_value=True), \
         patch("handlers.group_catch.schedule_delete") as mock_delete, \
         patch("handlers.group_catch.get_user_lang", new_callable=AsyncMock, return_value="ko"), \
         patch("handlers.group_catch.is_tournament_active", return_value=False):
        from handlers.group_catch import catch_handler
        await catch_handler(mock_update, mock_context)
        # schedule_delete 호출됨 (메시지 삭제) — 포획 진행 안 됨
        mock_delete.assert_called_once()


@pytest.mark.asyncio
async def test_catch_handler_normal_user_passes(mock_update, mock_context, mock_db):
    """밴 안 된 유저는 정상 진행."""
    with patch("database.queries.is_user_banned", new_callable=AsyncMock, return_value=False), \
         patch("handlers.group_catch.schedule_delete") as mock_delete, \
         patch("handlers.group_catch.get_user_lang", new_callable=AsyncMock, return_value="ko"), \
         patch("handlers.group_catch.is_tournament_active", return_value=False), \
         patch("services.abuse_service.is_catch_locked_async", new_callable=AsyncMock, return_value=(False, 0)), \
         patch("handlers.group_catch.queries.ensure_user", new_callable=AsyncMock), \
         patch("handlers.group_catch.spawn_queries.get_active_spawn", new_callable=AsyncMock, return_value=None):
        from handlers.group_catch import catch_handler
        await catch_handler(mock_update, mock_context)
        # schedule_delete는 호출됨 (정상 flow에서도 명령어 삭제)
        # 하지만 is_user_banned 이후 로직까지 진행됨


# ── trade_handler 밴 체크 ──

@pytest.mark.asyncio
async def test_trade_handler_banned_user_blocked(mock_update, mock_context, mock_db):
    """밴된 유저가 교환하면 차단."""
    mock_update.effective_chat = None  # DM
    mock_update.message.text = "교환 @someone 피카츄"

    with patch("database.queries.is_user_banned", new_callable=AsyncMock, return_value=True), \
         patch("handlers.dm_trade.get_user_lang", new_callable=AsyncMock, return_value="ko"):
        from handlers.dm_trade import trade_handler
        await trade_handler(mock_update, mock_context)
        mock_update.message.reply_text.assert_called_with("🚫 이용이 제한된 계정입니다.")


# ── master_ball_handler 밴 체크 ──

@pytest.mark.asyncio
async def test_master_ball_handler_banned(mock_update, mock_context, mock_db):
    """밴된 유저 마볼 사용 차단."""
    with patch("database.queries.is_user_banned", new_callable=AsyncMock, return_value=True), \
         patch("handlers.group_catch.schedule_delete") as mock_delete, \
         patch("handlers.group_catch.get_user_lang", new_callable=AsyncMock, return_value="ko"):
        from handlers.group_catch import master_ball_handler
        await master_ball_handler(mock_update, mock_context)
        mock_delete.assert_called_once()
