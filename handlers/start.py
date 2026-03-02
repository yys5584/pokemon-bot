"""Start and help handlers."""

import random

from telegram import Update
from telegram.ext import ContextTypes

from database import queries


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    if not update.effective_user:
        return

    user_id = update.effective_user.id
    display_name = update.effective_user.first_name or "트레이너"
    username = update.effective_user.username

    await queries.ensure_user(user_id, display_name, username)

    # Check if group or DM
    if update.effective_chat.type == "private":
        await update.message.reply_text(
            f"🎮 안녕하세요, {display_name} 트레이너님!\n"
            "포켓몬 봇에 오신 걸 환영합니다!\n"
            "━━━━━━━━━━━━━━━\n\n"
            "🌿 【포켓몬 수집】\n"
            "그룹 채팅방에서 야생 포켓몬이 출현하면\n"
            "ㅊ 입력으로 잡을 수 있어요!\n"
            "ㅁ 입력으로 마스터볼을 사용하면 100% 포획!\n\n"
            "🍚 【육성】\n"
            "잡은 포켓몬에게 밥/놀기로 친밀도를 올리고\n"
            "친밀도 MAX가 되면 진화할 수 있어요!\n\n"
            "⚔️ 【배틀】\n"
            "파트너를 지정하고 팀을 구성해서\n"
            "그룹 채팅방에서 다른 트레이너와 대전!\n"
            "승리 시 BP를 얻고 칭호를 해금하세요.\n\n"
            "🔄 【교환】\n"
            "다른 트레이너와 포켓몬을 교환할 수 있어요.\n"
            "일부 포켓몬은 교환으로만 진화해요!\n\n"
            "📖 【도감 & 칭호】\n"
            "251종 포켓몬을 모아 도감을 완성하고\n"
            "다양한 칭호를 해금해보세요!\n\n"
            "━━━━━━━━━━━━━━━\n"
            "💡 도움말 — 전체 명령어 보기"
        )
    else:
        # In group chat, register the chat room
        chat_id = update.effective_chat.id
        title = update.effective_chat.title
        try:
            count = await context.bot.get_chat_member_count(chat_id)
        except Exception:
            count = 0

        await queries.ensure_chat_room(chat_id, title, count)

        # Schedule spawns for this chat
        from services.spawn_service import schedule_spawns_for_chat, execute_spawn
        await schedule_spawns_for_chat(context.application, chat_id, count)

        # Schedule a welcome spawn within 1 hour (10~60 min, force=True to skip activity check)
        welcome_delay = random.randint(600, 3600)
        context.application.job_queue.run_once(
            execute_spawn,
            when=welcome_delay,
            data={"chat_id": chat_id, "force": True},
            name=f"welcome_spawn_{chat_id}",
        )

        await update.message.reply_text(
            "🎮 포켓몬 봇이 활성화되었습니다!\n"
            "야생 포켓몬이 나타나면 ㅊ 으로 잡으세요!\n"
            "🌿 곧 첫 번째 포켓몬이 나타날 거예요!"
        )


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /도움말 command."""
    text = (
        "📖 명령어 안내\n"
        "━━━━━━━━━━━━━━━\n\n"
        "🌿 【포획】 — 채팅방에서 사용\n"
        "  ㅊ — 포켓몬 잡기 시도\n"
        "  ㅁ — 마스터볼 사용 (100% 포획)\n"
        "  포켓볼 충전 — 잡기 횟수 +10\n\n"
        "🍚 【육성】 — DM에서 사용\n"
        "  내포켓몬 — 보유 포켓몬 목록\n"
        "  밥 [번호] — 밥 주기 (친밀도↑)\n"
        "  놀기 [번호] — 놀아주기 (친밀도↑)\n"
        "  진화 [번호] — 진화 (친밀도 MAX 시)\n\n"
        "⚔️ 【배틀】 — DM에서 팀 구성, 채팅방에서 대전\n"
        "  파트너 — 파트너 포켓몬 지정\n"
        "  팀등록 — 배틀 팀 등록 (최대 6마리)\n"
        "  팀 — 내 배틀 팀 확인\n"
        "  팀해제 — 배틀 팀 초기화\n"
        "  배틀 — 상대에게 답장하며 배틀 도전 (채팅방)\n"
        "  배틀수락 / 배틀거절 — 도전 응답 (채팅방)\n"
        "  배틀전적 — 승패/연승/BP 확인\n"
        "  배틀랭킹 — 배틀 승률 랭킹 (채팅방)\n"
        "  BP — BP 잔액 확인\n"
        "  BP상점 — BP로 아이템 교환\n\n"
        "🔄 【교환】 — DM에서 사용\n"
        "  교환 @상대 [내몬] — 교환 요청\n"
        "  수락 / 거절 — 교환 응답\n\n"
        "📖 【도감 & 칭호】 — DM에서 사용\n"
        "  도감 — 내 도감 보기\n"
        "  칭호 — 칭호 보기/장착\n"
        "  칭호목록 — 전체 칭호 & 해금 조건\n\n"
        "📊 【정보】\n"
        "  랭킹 — 도감 랭킹 (채팅방)\n"
        "  로그 — 최근 출현 기록 (채팅방)\n"
        "  날씨 — 현재 날씨 & 타입 보너스\n"
        "  대시보드 — 실시간 통계 웹페이지\n\n"
        "━━━━━━━━━━━━━━━\n"
        "💡 Tip: 채팅방 활동이 많을수록 포켓몬이 자주 출현!"
    )
    await update.message.reply_text(text)
