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
            f"🎮 안녕하세요, {display_name} 트레이너님!\n\n"
            "포켓몬 봇에 오신 걸 환영합니다!\n"
            "그룹 채팅방에서 야생 포켓몬이 출현하면\n"
            "ㅊ 을 입력해서 잡을 수 있어요.\n\n"
            "도움말 로 명령어를 확인하세요!"
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
        "📖 명령어 안내\n\n"
        "【채팅방】\n"
        "ㅊ — 포켓몬 잡기 시도\n"
        "ㅁ — 마스터볼 사용 (100% 포획)\n"
        "랭킹 — 도감 랭킹\n"
        "로그 — 최근 출현 기록\n"
        "날씨 — 현재 날씨 & 출현 보너스\n"
        "포켓볼 충전 — 잡기 횟수 +5\n"
        "대시보드 — 실시간 통계 보기\n\n"
        "【DM 전용】\n"
        "도움말 — 명령어 안내\n"
        "도감 — 내 도감 보기\n"
        "내포켓몬 — 보유 포켓몬 목록\n"
        "밥 [번호] — 밥 주기 (친밀도↑)\n"
        "놀기 [번호] — 놀아주기 (친밀도↑)\n"
        "진화 [번호] — 진화 (친밀도 MAX 시)\n"
        "교환 @상대 [내몬] — 교환 요청\n"
        "수락 — 교환 수락\n"
        "거절 — 교환 거절\n"
        "칭호 — 칭호 보기/장착\n"
        "칭호목록 — 전체 칭호 & 해금 조건\n\n"
        "【관리자】\n"
        "스폰배율 [배율] — 채팅방 스폰 배율 (채팅방)\n"
        "강제스폰 — 즉시 포켓몬 출현 (채팅방)\n"
        "이벤트시작 [이름] [시간] — 이벤트 (DM)\n"
        "이벤트목록 — 진행 중 이벤트 (DM)\n"
        "이벤트종료 [번호] — 이벤트 종료 (DM)"
    )
    await update.message.reply_text(text)
