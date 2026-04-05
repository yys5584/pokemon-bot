"""시나리오 통합 테스트 헬퍼.

FakeUser: 가짜 텔레그램 유저 — 메시지 보내기, 버튼 누르기.
context.user_data가 같은 유저 인스턴스 안에서 유지되어 상태 전이 테스트 가능.
"""

from unittest.mock import AsyncMock, MagicMock


class FakeUser:
    """가짜 텔레그램 유저.

    Usage::

        admin = FakeUser(1832746512, "관리자", chat_id=-100999)
        user_a = FakeUser(111, "유저A", chat_id=-100999)

        update, ctx = admin.send("대회시작")
        await admin_handler(update, ctx)

        update, ctx = user_a.send("ㄷ")
        await tournament_join_handler(update, ctx)

        update, ctx = user_a.press("battle_accept_111")
        await battle_callback_handler(update, ctx)
    """

    _msg_id_counter = 1000

    def __init__(self, user_id: int, name: str, chat_id: int = -100999,
                 chat_type: str = "supergroup"):
        self.user_id = user_id
        self.name = name
        self.chat_id = chat_id
        self.chat_type = chat_type

        # 유저별 persistent context (핸들러 간 상태 유지)
        self._user_data: dict = {}
        self._chat_data: dict = {}

        # bot 호출 추적용 (send_message, edit_message_text 등)
        self.bot = MagicMock()
        self.bot.send_message = AsyncMock()
        self.bot.send_photo = AsyncMock()
        self.bot.edit_message_text = AsyncMock()
        self.bot.edit_message_reply_markup = AsyncMock()
        self.bot.delete_message = AsyncMock()
        self.bot.send_sticker = AsyncMock()
        self.bot.send_animation = AsyncMock()

        # sent_messages: bot.send_message 호출 시 텍스트 기록
        self._sent_texts: list[str] = []
        self.bot.send_message.side_effect = self._track_send_message

    async def _track_send_message(self, **kwargs):
        """bot.send_message 호출 추적."""
        text = kwargs.get("text", "")
        self._sent_texts.append(text)
        msg = MagicMock()
        msg.message_id = self._next_msg_id()
        return msg

    @classmethod
    def _next_msg_id(cls) -> int:
        cls._msg_id_counter += 1
        return cls._msg_id_counter

    @property
    def sent_texts(self) -> list[str]:
        """bot.send_message로 보내진 텍스트 목록."""
        return self._sent_texts

    def last_sent(self) -> str:
        """가장 최근 bot.send_message 텍스트."""
        return self._sent_texts[-1] if self._sent_texts else ""

    def clear_sent(self):
        """추적 기록 초기화."""
        self._sent_texts.clear()
        self.bot.send_message.reset_mock()
        self.bot.send_photo.reset_mock()
        self.bot.edit_message_text.reset_mock()

    def send(self, text: str) -> tuple[MagicMock, MagicMock]:
        """텍스트 메시지 전송 — message handler용 (update, context) 반환."""
        msg_id = self._next_msg_id()

        update = MagicMock()
        update.effective_user.id = self.user_id
        update.effective_user.first_name = self.name
        update.effective_user.username = self.name.lower().replace(" ", "")
        update.effective_chat.id = self.chat_id
        update.effective_chat.type = self.chat_type
        update.message = MagicMock()
        update.message.text = text
        update.message.message_id = msg_id
        update.message.from_user = update.effective_user
        update.message.chat = update.effective_chat
        update.message.reply_text = AsyncMock()
        update.message.reply_photo = AsyncMock()
        update.message.delete = AsyncMock()
        update.callback_query = None

        context = self._make_context()
        return update, context

    def press(self, callback_data: str, message_id: int | None = None) -> tuple[MagicMock, MagicMock]:
        """인라인 버튼 누르기 — callback handler용 (update, context) 반환."""
        msg_id = message_id or self._next_msg_id()

        update = MagicMock()
        update.effective_user.id = self.user_id
        update.effective_user.first_name = self.name
        update.effective_user.username = self.name.lower().replace(" ", "")
        update.effective_chat.id = self.chat_id
        update.effective_chat.type = self.chat_type
        update.message = None

        query = MagicMock()
        query.data = callback_data
        query.from_user = update.effective_user
        query.message = MagicMock()
        query.message.message_id = msg_id
        query.message.chat = update.effective_chat
        query.message.chat_id = self.chat_id
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        query.edit_message_reply_markup = AsyncMock()
        query.delete_message = AsyncMock()
        update.callback_query = query

        context = self._make_context()
        return update, context

    def _make_context(self) -> MagicMock:
        """persistent user_data/chat_data를 가진 context 생성."""
        ctx = MagicMock()
        ctx.bot = self.bot
        ctx.user_data = self._user_data
        ctx.chat_data = self._chat_data
        ctx.job = None
        ctx.job_queue = MagicMock()
        ctx.job_queue.run_once = MagicMock()
        return ctx


def make_job_context(bot: MagicMock, data: dict) -> MagicMock:
    """JobQueue 콜백용 context mock (resolve_spawn 등)."""
    ctx = MagicMock()
    ctx.bot = bot
    ctx.bot.send_message = bot.send_message
    ctx.bot.send_photo = bot.send_photo
    ctx.bot.edit_message_text = bot.edit_message_text
    ctx.job = MagicMock()
    ctx.job.data = data
    ctx.job.chat_id = data.get("chat_id")
    return ctx


def reset_all_service_state():
    """모든 서비스 글로벌 상태를 초기화. 시나리오 테스트 전에 호출."""
    # Tournament
    from services.tournament_service import _reset_state as reset_tournament
    reset_tournament()

    # Catch locks & event masterball count
    from handlers.group_catch import _catch_locks, _event_masterball_count
    _catch_locks.clear()
    _event_masterball_count.clear()

    # Duplicate callback/message guard
    try:
        from handlers._common import _last_callbacks, _last_messages
        _last_callbacks.clear()
        _last_messages.clear()
    except (ImportError, AttributeError):
        pass


def make_pokemon(pokemon_id: int = 25, name: str = "피카츄", emoji: str = "⚡",
                 rarity: str = "common", is_shiny: bool = False,
                 instance_id: int = 1001, **overrides) -> dict:
    """테스트용 포켓몬 dict 생성."""
    poke = {
        "id": instance_id,
        "instance_id": instance_id,
        "pokemon_instance_id": instance_id,
        "pokemon_id": pokemon_id,
        "name_ko": name,
        "emoji": emoji,
        "rarity": rarity,
        "is_shiny": 1 if is_shiny else 0,
        "stat_type": "offensive",
        "friendship": 3,
        "pokemon_type": "electric",
        "iv_hp": 20, "iv_atk": 25, "iv_def": 15,
        "iv_spa": 28, "iv_spdef": 18, "iv_spd": 22,
    }
    poke.update(overrides)
    return poke
