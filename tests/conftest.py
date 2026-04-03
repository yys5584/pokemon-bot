"""공통 pytest fixture — DB/텔레그램 mock, 샘플 데이터."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── 1. 환경변수 패치 (.env 없이 import 가능하게) ──
@pytest.fixture(autouse=True)
def patch_env(monkeypatch):
    """config.py가 .env 없이도 로드되도록 환경변수 세팅."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/test")
    monkeypatch.setenv("BOT_TOKEN", "fake-token")
    monkeypatch.setenv("ADMIN_IDS", "12345")


# ── 1b. AI 서사 mock (DB/API 호출 방지) ──
@pytest.fixture(autouse=True)
def mock_ai_narrative(monkeypatch):
    """get_ai_narrative를 항상 None으로 — DB/Gemini 없이 테스트."""
    async def _noop(*args, **kwargs):
        return None
    monkeypatch.setattr("services.fortune_service.get_ai_narrative", _noop)


# ── 2. DB pool mock ──
@pytest.fixture
def mock_pool():
    """asyncpg.Pool mock — fetch/fetchrow/fetchval/execute 지원."""
    pool = AsyncMock()
    pool.fetch = AsyncMock(return_value=[])
    pool.fetchrow = AsyncMock(return_value=None)
    pool.fetchval = AsyncMock(return_value=None)
    pool.execute = AsyncMock()
    return pool


@pytest.fixture
def mock_db(mock_pool):
    """database.connection.get_db()를 mock pool로 교체."""
    with patch("database.connection.get_db", return_value=mock_pool):
        yield mock_pool


# ── 3. Telegram Update/Context mock ──
@pytest.fixture
def mock_update():
    """telegram.Update mock."""
    update = MagicMock()
    update.effective_user.id = 12345
    update.effective_user.first_name = "TestUser"
    update.effective_user.username = "testuser"
    update.effective_chat.id = -100123
    update.effective_chat.type = "supergroup"
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    update.message.reply_photo = AsyncMock()
    update.message.delete = AsyncMock()
    update.callback_query = None
    return update


@pytest.fixture
def mock_context():
    """telegram.ext.ContextTypes.DEFAULT_TYPE mock."""
    ctx = MagicMock()
    ctx.bot = MagicMock()
    ctx.bot.send_message = AsyncMock()
    ctx.bot.send_photo = AsyncMock()
    ctx.bot.edit_message_text = AsyncMock()
    ctx.user_data = {}
    ctx.chat_data = {}
    return ctx


# ── 4. 샘플 포켓몬 데이터 ──
@pytest.fixture
def sample_pokemon():
    """배틀/합성 테스트용 포켓몬 dict."""
    return {
        "id": 1001,
        "pokemon_id": 6,
        "pokemon_instance_id": 1001,
        "name_ko": "리자몽",
        "emoji": "🔥",
        "rarity": "epic",
        "stat_type": "offensive",
        "friendship": 3,
        "pokemon_type": "fire",
        "is_shiny": 0,
        "iv_hp": 20, "iv_atk": 25, "iv_def": 15,
        "iv_spa": 28, "iv_spdef": 18, "iv_spd": 22,
    }
