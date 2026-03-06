"""Tutorial onboarding system — DM-based step-by-step guide."""

import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from database import queries

logger = logging.getLogger(__name__)

# ============================================================
# Tutorial step messages & buttons
# ============================================================

TUTORIAL_MESSAGES = {
    1: (
        "🎮 포켓몬 봇에 오신 걸 환영합니다!\n"
        "\n"
        "방금 첫 포획을 시도하셨네요!\n"
        "이 봇에는 포획 외에도 다양한 시스템이 있어요:\n"
        "\n"
        "🍚 육성 — 밥/놀기로 친밀도 올리기\n"
        "⚔️ 배틀 — 팀을 짜서 다른 트레이너와 대전\n"
        "📖 도감 — 포켓몬 수집 & 칭호 해금\n"
        "🌐 대시보드 — 실시간 통계 웹사이트\n"
        "\n"
        "하나씩 알려드릴게요!"
    ),
    2: (
        "🌿 【포획 시스템】\n"
        "━━━━━━━━━━━━━━━\n"
        "\n"
        "채팅방에 야생 포켓몬이 나타나면:\n"
        "  ㅊ — 일반 포켓볼 (확률 포획)\n"
        "  ㅎ — 하이퍼볼 (확률 1.5배)\n"
        "  ㅁ — 마스터볼 (100% 포획!)\n"
        "\n"
        "💡 하루 20회까지 시도 가능\n"
        "💡 포켓볼 충전 으로 +10회 추가 (1회/일)\n"
        "💡 채팅방 활동이 많을수록 포켓몬이 자주 등장!\n"
        "\n"
        "✨ 이로치(색이 다른) 포켓몬은 매우 희귀해요!"
    ),
    3: (
        "🍚 【육성 시스템】\n"
        "━━━━━━━━━━━━━━━\n"
        "\n"
        "잡은 포켓몬을 키워보세요! (DM에서 사용)\n"
        "\n"
        "📦 내포켓몬 — 보유 목록 확인\n"
        "🍚 밥 [번호] — 밥 주기 (하루 3회)\n"
        "🎾 놀기 [번호] — 놀아주기 (하루 2회)\n"
        "💕 친밀도가 MAX가 되면 진화할 수 있어요!\n"
        "\n"
        "👉 지금 \"내포켓몬\"을 입력해서 목록을 확인해보세요!"
    ),
    4: (
        "🤝 【파트너 시스템】\n"
        "━━━━━━━━━━━━━━━\n"
        "\n"
        "파트너 포켓몬을 지정하면 상태창에 표시돼요!\n"
        "가장 좋아하는 포켓몬을 파트너로 골라보세요.\n"
        "\n"
        "👉 \"파트너\"를 입력해서 파트너를 골라보세요!"
    ),
    5: (
        "⚔️ 【배틀 시스템】\n"
        "━━━━━━━━━━━━━━━\n"
        "\n"
        "1️⃣ 팀등록 — 최대 6마리로 배틀 팀 구성\n"
        "2️⃣ 채팅방에서 상대에게 답장 + \"배틀\" → 도전!\n"
        "3️⃣ 상대가 \"배틀수락\"하면 자동 대전!\n"
        "\n"
        "💰 승리 시 BP(배틀포인트) 획득\n"
        "🏪 BP상점에서 마스터볼/강스권 교환 가능\n"
        "\n"
        "🎲 야차 — BP/마스터볼을 걸고 베팅 배틀!\n"
        "\n"
        "👉 \"팀등록\"으로 첫 팀을 만들어보세요!"
    ),
    6: (
        "📖 【도감 & 칭호】\n"
        "━━━━━━━━━━━━━━━\n"
        "\n"
        "📖 도감 — 수집한 포켓몬 확인 (1세대/2세대)\n"
        "🏷️ 칭호 — 조건 달성 시 칭호 해금!\n"
        "📋 칭호목록 — 모든 칭호 & 해금 조건\n"
        "\n"
        "🎯 도감 완성률을 높이면 특별 칭호를 얻을 수 있어요!\n"
        "\n"
        "👉 \"도감\"을 입력해서 확인해보세요!"
    ),
    7: (
        "🎓 튜토리얼 완료! 축하합니다!\n"
        "\n"
        "📊 대시보드에서 실시간 통계를 확인하세요:\n"
        "🌐 tgpoke.com\n"
        "\n"
        "🎁 졸업 보상:\n"
        "  🔮 마스터볼 x2\n"
        "  💰 BP +200\n"
        "\n"
        "━━━━━━━━━━━━━━━\n"
        "📌 유용한 꿀팁:\n"
        "• 감정 [이름] — 개체값(IV) 확인\n"
        "• 상성 [타입] — 배틀 타입 상성표\n"
        "• 출석 — 매일 출석 보상\n"
        "• 날씨에 따라 특정 타입 포획률 UP!\n"
        "━━━━━━━━━━━━━━━\n"
        "\n"
        "도움이 필요하면 언제든 \"도움말\"을 입력하세요!"
    ),
}

# Step title labels for progress indicator
_STEP_TITLES = {
    1: "환영",
    2: "포획",
    3: "육성",
    4: "파트너",
    5: "배틀",
    6: "도감",
    7: "졸업",
}


def _progress_bar(step: int) -> str:
    """Build a visual progress indicator like [1/7] ● ● ○ ○ ○ ○ ○."""
    dots = []
    for i in range(1, 8):
        if i < step:
            dots.append("●")
        elif i == step:
            dots.append("◉")
        else:
            dots.append("○")
    return f"[{step}/7] {' '.join(dots)}"


def _build_buttons(step: int) -> InlineKeyboardMarkup:
    """Build navigation buttons for the given tutorial step."""
    buttons = []

    if step == 1:
        # First step: start + skip
        buttons.append([
            InlineKeyboardButton("▶️ 튜토리얼 시작", callback_data="tut_next_2"),
            InlineKeyboardButton("⏭️ 스킵", callback_data="tut_skip"),
        ])
    elif step == 7:
        # Last step: prev + complete
        buttons.append([
            InlineKeyboardButton("◀️ 이전", callback_data="tut_prev_6"),
            InlineKeyboardButton("🎓 완료!", callback_data="tut_done"),
        ])
    else:
        # Middle steps: prev + next + skip
        buttons.append([
            InlineKeyboardButton("◀️ 이전", callback_data=f"tut_prev_{step - 1}"),
            InlineKeyboardButton("▶️ 다음", callback_data=f"tut_next_{step + 1}"),
            InlineKeyboardButton("⏭️ 스킵", callback_data="tut_skip"),
        ])

    return InlineKeyboardMarkup(buttons)


def _build_step_message(step: int) -> str:
    """Combine progress bar + step message."""
    progress = _progress_bar(step)
    title = _STEP_TITLES.get(step, "")
    body = TUTORIAL_MESSAGES.get(step, "")
    return f"{progress}  {title}\n\n{body}"


# ============================================================
# Send tutorial step (used from catch_handler trigger too)
# ============================================================

async def send_tutorial_step(context: ContextTypes.DEFAULT_TYPE, user_id: int, step: int):
    """Send a tutorial step message via DM."""
    text = _build_step_message(step)
    markup = _build_buttons(step)
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=text,
            reply_markup=markup,
        )
    except Exception as e:
        logger.warning(f"Failed to send tutorial DM to {user_id}: {e}")


# ============================================================
# Graduation rewards
# ============================================================

async def _give_graduation_rewards(user_id: int):
    """Grant tutorial completion rewards: 2 master balls + 200 BP."""
    await queries.add_master_ball(user_id, 2)
    pool = await queries.get_db()
    await pool.execute(
        "UPDATE users SET battle_points = battle_points + 200 WHERE user_id = $1",
        user_id,
    )


# ============================================================
# Callback handler
# ============================================================

async def tutorial_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all tut_* inline button callbacks."""
    query = update.callback_query
    if not query or not query.data:
        return

    await query.answer()
    user_id = query.from_user.id
    data = query.data

    # tut_next_N — go to step N (forward)
    if data.startswith("tut_next_"):
        step = int(data.split("_")[2])
        await queries.update_tutorial_step(user_id, step)
        text = _build_step_message(step)
        markup = _build_buttons(step)
        try:
            await query.edit_message_text(text, reply_markup=markup)
        except BadRequest as e:
            if "not modified" not in str(e).lower():
                raise

    # tut_prev_N — go to step N (backward)
    elif data.startswith("tut_prev_"):
        step = int(data.split("_")[2])
        await queries.update_tutorial_step(user_id, step)
        text = _build_step_message(step)
        markup = _build_buttons(step)
        try:
            await query.edit_message_text(text, reply_markup=markup)
        except BadRequest as e:
            if "not modified" not in str(e).lower():
                raise

    # tut_skip — skip tutorial completely
    elif data == "tut_skip":
        await queries.update_tutorial_step(user_id, 99)
        try:
            await query.edit_message_text(
                "⏭️ 튜토리얼을 건너뛰었습니다.\n"
                "나중에 궁금한 게 있으면 \"도움말\"을 입력하세요!"
            )
        except BadRequest:
            pass

    # tut_done — complete tutorial with rewards
    elif data == "tut_done":
        await queries.update_tutorial_step(user_id, 99)
        await _give_graduation_rewards(user_id)
        try:
            await query.edit_message_text(
                "🎓 튜토리얼 완료! 축하합니다!\n"
                "\n"
                "🎁 졸업 보상이 지급되었습니다:\n"
                "  🔮 마스터볼 x2\n"
                "  💰 BP +200\n"
                "\n"
                "━━━━━━━━━━━━━━━\n"
                "📌 유용한 꿀팁:\n"
                "• 감정 [이름] — 개체값(IV) 확인\n"
                "• 상성 [타입] — 배틀 타입 상성표\n"
                "• 출석 — 매일 출석 보상\n"
                "• 날씨에 따라 특정 타입 포획률 UP!\n"
                "━━━━━━━━━━━━━━━\n"
                "\n"
                "🌐 tgpoke.com 에서 실시간 통계를 확인하세요!\n"
                "도움이 필요하면 \"도움말\"을 입력하세요!"
            )
        except BadRequest:
            pass
