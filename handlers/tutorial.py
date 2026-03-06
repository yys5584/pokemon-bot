"""Tutorial onboarding system — DM-based step-by-step guide with interactive catches."""

import logging
import random

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from database import queries

logger = logging.getLogger(__name__)

# ============================================================
# Tutorial Pokemon IDs (pokemon_master.id)
# ============================================================

_EEVEE_ID = 133        # 이브이 (rare)
_DRATINI_ID = 147      # 미뇽 (rare)
_LEGENDARY_IDS = [      # 전설 (랜덤 1마리)
    144,  # 프리저
    145,  # 썬더
    146,  # 파이어
    150,  # 뮤츠
    151,  # 뮤
    243,  # 라이코
    244,  # 앤테이
    245,  # 스이쿤
    249,  # 루기아
    250,  # 칠색조
]

# Pokemon display info (name, emoji, rarity_label, rarity_color)
_POKEMON_INFO = {
    133: ("이브이", "🦊", "일반", "🟢"),
    147: ("미뇽", "🐉", "희귀", "🔵"),
    144: ("프리저", "❄️", "전설", "🟡"),
    145: ("썬더", "⚡", "전설", "🟡"),
    146: ("파이어", "🔥", "전설", "🟡"),
    150: ("뮤츠", "🧬", "전설", "🟡"),
    151: ("뮤", "🩷", "전설", "🟡"),
    243: ("라이코", "⚡", "전설", "🟡"),
    244: ("앤테이", "🔥", "전설", "🟡"),
    245: ("스이쿤", "💧", "전설", "🟡"),
    249: ("루기아", "🔮", "전설", "🟡"),
    250: ("칠색조", "🔥", "전설", "🟡"),
}

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
    # Step 2 is handled dynamically (interactive catch)
    3: (
        "🍚 【육성 시스템】\n"
        "━━━━━━━━━━━━━━━\n"
        "\n"
        "잡은 포켓몬을 키워보세요! (DM에서 사용)\n"
        "\n"
        "📦 내포켓몬 — 보유 포켓몬과 다양한 상호작용!\n"
        "🍚 밥 [번호] — 밥 주기 (하루 3회)\n"
        "🎾 놀기 [번호] — 놀아주기 (하루 2회)\n"
        "\n"
        "💕 친밀도가 MAX가 되면 진화할 수 있어요!\n"
        "💪 친밀도 MAX 포켓몬은 배틀에서 20% 더 강해져요!\n"
        "\n"
        "👉 지금 \"내포켓몬\"을 입력해서 목록을 확인해보세요!"
    ),
    4: (
        "🤝 【파트너 시스템】\n"
        "━━━━━━━━━━━━━━━\n"
        "\n"
        "파트너 포켓몬을 지정하면 상태창에 표시돼요!\n"
        "💪 파트너 포켓몬은 배틀에서 5% 더 강해져요!\n"
        "\n"
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
        "🏪 BP상점에서 마스터볼 등 다양한 상품을 구매할 수 있어요!\n"
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
        "📦 내포켓몬 — 보유 포켓몬과 다양한 상호작용!\n"
        "🏷️ 칭호 — 조건 달성 시 칭호 해금!\n"
        "\n"
        "🎯 도감 완성률을 높이면 특별 칭호를 얻을 수 있어요!\n"
        "\n"
        "👉 \"도감\"을 입력해서 확인해보세요!"
    ),
    7: (
        "🎓 튜토리얼 완료! 축하합니다!\n"
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
        "🏠 공식방: https://t.me/tg_poke\n"
        "🌿 30초마다 포켓몬이 출현해요!\n"
        "🏆 매일 저녁 9시 대회 접수, 10시 포켓몬 마스터 대회!\n"
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
        buttons.append([
            InlineKeyboardButton("▶️ 튜토리얼 시작", callback_data="tut_next_2"),
            InlineKeyboardButton("⏭️ 스킵", callback_data="tut_skip"),
        ])
    elif step == 7:
        buttons.append([
            InlineKeyboardButton("◀️ 이전", callback_data="tut_prev_6"),
            InlineKeyboardButton("🎓 완료!", callback_data="tut_done"),
        ])
    else:
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
# Step 2: Interactive catch sub-steps
# ============================================================

def _build_catch_step_a() -> tuple[str, InlineKeyboardMarkup]:
    """Step 2a: Explain pokeball + Eevee appears."""
    progress = _progress_bar(2)
    text = (
        f"{progress}  포획 체험\n\n"
        "🌿 【포획 체험】\n"
        "━━━━━━━━━━━━━━━\n"
        "\n"
        "채팅방에서 포켓몬이 나타나면\n"
        "ㅊ 을 입력하면 포켓볼이 나갑니다!\n"
        "\n"
        "💡 하루 20회까지 시도 가능\n"
        "💡 봇이 있는 채팅방에서 \"포켓볼 충전\"을 입력하면\n"
        "   10회를 추가 충전할 수 있어요! (1일 1회)\n"
        "\n"
        "━━━━━━━━━━━━━━━\n"
        "\n"
        "🟢 야생 이브이 🦊 가 나타났다!\n"
        "등급: 🟢 일반 (Common)\n"
        "\n"
        "포켓볼을 던져보세요!"
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("ㅊ 포켓볼 던지기!", callback_data="tut_catch_poke")],
        [
            InlineKeyboardButton("◀️ 이전", callback_data="tut_prev_1"),
            InlineKeyboardButton("⏭️ 스킵", callback_data="tut_skip"),
        ],
    ])
    return text, markup


def _build_catch_step_b() -> tuple[str, InlineKeyboardMarkup]:
    """Step 2b: Explain hyperball + Dratini appears."""
    progress = _progress_bar(2)
    text = (
        f"{progress}  포획 체험\n\n"
        "✅ 이브이 🦊 포획 성공! 내 포켓몬에 추가되었어요.\n"
        "\n"
        "━━━━━━━━━━━━━━━\n"
        "\n"
        "🔵 야생 미뇽 🐉 이 나타났다!\n"
        "등급: 🔵 희귀 (Rare)\n"
        "\n"
        "⚠️ 희귀 등급은 일반보다 포획률이 낮아요!\n"
        "\n"
        "💡 하이퍼볼(ㅎ)은 포켓볼보다 포획률이 3배 높아요.\n"
        "   하나 지급해 드릴테니 던져볼까요?"
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("ㅎ 하이퍼볼 던지기!", callback_data="tut_catch_hyper")],
        [InlineKeyboardButton("⏭️ 스킵", callback_data="tut_skip")],
    ])
    return text, markup


def _build_catch_step_c(legendary_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Step 2c: Explain masterball + Legendary appears."""
    info = _POKEMON_INFO.get(legendary_id, ("???", "❓", "전설", "🟡"))
    name, emoji, _, _ = info
    progress = _progress_bar(2)
    text = (
        f"{progress}  포획 체험\n\n"
        "✅ 미뇽 🐉 포획 성공! 내 포켓몬에 추가되었어요.\n"
        "\n"
        "━━━━━━━━━━━━━━━\n"
        "\n"
        f"🟡 야생 {name} {emoji} 이(가) 나타났다!\n"
        "등급: 🟡 전설 (Legendary)\n"
        "\n"
        "⚠️ 전설 포켓몬은 포획 확률이 매우 낮아요!\n"
        "   일반 포켓볼이나 하이퍼볼로는 거의 잡을 수 없어요.\n"
        "\n"
        "💡 마스터볼(ㅁ)은 100% 포획!\n"
        "   포켓몬을 잡을 때 굉장히 낮은 확률로 나오거나\n"
        "   상점에서 BP로 구매할 수 있어요.\n"
        "\n"
        "   하나 지급해 드릴테니 던져보세요!"
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("ㅁ 마스터볼 던지기!", callback_data=f"tut_catch_master_{legendary_id}")],
        [InlineKeyboardButton("⏭️ 스킵", callback_data="tut_skip")],
    ])
    return text, markup


def _build_catch_complete(legendary_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Step 2 complete: all 3 Pokemon caught."""
    info = _POKEMON_INFO.get(legendary_id, ("???", "❓", "전설", "🟡"))
    name, emoji, _, _ = info
    progress = _progress_bar(2)
    text = (
        f"{progress}  포획 체험\n\n"
        f"✅ {name} {emoji} 포획 성공! 내 포켓몬에 추가되었어요.\n"
        "\n"
        "━━━━━━━━━━━━━━━\n"
        "\n"
        "🎉 3마리 모두 잡았어요!\n"
        "\n"
        "📝 포획 정리:\n"
        "  ㅊ 포켓볼 — 기본 포획\n"
        "  ㅎ 하이퍼볼 — 포획률 3배 (BP상점에서 구매)\n"
        "  ㅁ 마스터볼 — 100% 포획 (매우 귀중!)\n"
        "\n"
        "💡 채팅방 활동이 많을수록 포켓몬이 자주 등장!\n"
        "✨ 이로치(색이 다른) 포켓몬은 매우 희귀해요!"
    )
    markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("◀️ 이전", callback_data="tut_prev_1"),
            InlineKeyboardButton("▶️ 다음: 육성", callback_data="tut_next_3"),
            InlineKeyboardButton("⏭️ 스킵", callback_data="tut_skip"),
        ],
    ])
    return text, markup


# ============================================================
# Send tutorial step (used from catch_handler trigger too)
# ============================================================

async def send_tutorial_step(context: ContextTypes.DEFAULT_TYPE, user_id: int, step: int):
    """Send a tutorial step message via DM."""
    if step == 2:
        # Interactive catch — start with step 2a
        text, markup = _build_catch_step_a()
    else:
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
# Give tutorial Pokemon to user
# ============================================================

async def _give_tutorial_pokemon(user_id: int, pokemon_id: int):
    """Add a tutorial Pokemon to user's collection."""
    try:
        await queries.give_pokemon_to_user(user_id, pokemon_id, chat_id=None)
    except Exception as e:
        logger.error(f"Failed to give tutorial pokemon {pokemon_id} to {user_id}: {e}")


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

    # tut_next_N — go to step N
    if data.startswith("tut_next_"):
        step = int(data.split("_")[2])
        await queries.update_tutorial_step(user_id, step)
        if step == 2:
            # Start interactive catch
            text, markup = _build_catch_step_a()
        else:
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
        if step == 2:
            text, markup = _build_catch_step_a()
        else:
            text = _build_step_message(step)
            markup = _build_buttons(step)
        try:
            await query.edit_message_text(text, reply_markup=markup)
        except BadRequest as e:
            if "not modified" not in str(e).lower():
                raise

    # tut_catch_poke — catch Eevee with pokeball (step 2a → 2b)
    elif data == "tut_catch_poke":
        await _give_tutorial_pokemon(user_id, _EEVEE_ID)
        text, markup = _build_catch_step_b()
        try:
            await query.edit_message_text(text, reply_markup=markup)
        except BadRequest as e:
            if "not modified" not in str(e).lower():
                raise

    # tut_catch_hyper — catch Dratini with hyperball (step 2b → 2c)
    elif data == "tut_catch_hyper":
        await _give_tutorial_pokemon(user_id, _DRATINI_ID)
        # Pick a random legendary for the masterball step
        legendary_id = random.choice(_LEGENDARY_IDS)
        text, markup = _build_catch_step_c(legendary_id)
        try:
            await query.edit_message_text(text, reply_markup=markup)
        except BadRequest as e:
            if "not modified" not in str(e).lower():
                raise

    # tut_catch_master_{id} — catch legendary with masterball (step 2c → complete)
    elif data.startswith("tut_catch_master_"):
        legendary_id = int(data.split("_")[3])
        await _give_tutorial_pokemon(user_id, legendary_id)
        text, markup = _build_catch_complete(legendary_id)
        try:
            await query.edit_message_text(text, reply_markup=markup)
        except BadRequest as e:
            if "not modified" not in str(e).lower():
                raise

    # tut_skip — skip tutorial
    elif data == "tut_skip":
        restarted = await queries.get_tutorial_restarted(user_id)
        if restarted:
            # Already restarted once — no more restarts
            await queries.update_tutorial_step(user_id, 99)
            try:
                await query.edit_message_text(
                    "⏭️ 튜토리얼을 건너뛰었습니다.\n"
                    "나중에 궁금한 게 있으면 \"도움말\"을 입력하세요!"
                )
            except BadRequest:
                pass
        else:
            # First skip — offer restart option
            await queries.update_tutorial_step(user_id, 98)
            try:
                await query.edit_message_text(
                    "⏭️ 튜토리얼을 건너뛰었습니다.\n\n"
                    "💡 나중에 다시 보고 싶다면 아래 버튼으로\n"
                    "   튜토리얼을 재시작할 수 있어요! (1회 제한)\n\n"
                    "궁금한 게 있으면 \"도움말\"을 입력하세요!",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔄 튜토리얼 재시작", callback_data="tut_restart")],
                    ]),
                )
            except BadRequest:
                pass

    # tut_restart — restart tutorial (one-time only)
    elif data == "tut_restart":
        restarted = await queries.get_tutorial_restarted(user_id)
        if restarted:
            try:
                await query.edit_message_text(
                    "⚠️ 튜토리얼 재시작은 1회만 가능합니다.\n"
                    "궁금한 게 있으면 \"도움말\"을 입력하세요!"
                )
            except BadRequest:
                pass
        else:
            await queries.restart_tutorial(user_id)
            text = _build_step_message(1)
            markup = _build_buttons(1)
            try:
                await query.edit_message_text(text, reply_markup=markup)
            except BadRequest as e:
                if "not modified" not in str(e).lower():
                    raise

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
                "🏠 공식방: https://t.me/tg_poke\n"
                "🌿 30초마다 포켓몬이 출현해요!\n"
                "🏆 매일 저녁 9시 대회 접수, 10시 포켓몬 마스터 대회!\n"
                "\n"
                "도움이 필요하면 \"도움말\"을 입력하세요!"
            )
        except BadRequest:
            pass
