"""Tutorial onboarding system — conversational DM-based step-by-step guide.

Messages flow like a real chat (send_message, not edit_message_text).
Step 2 uses actual card images and ㅊ/ㅎ/ㅁ text input for catches.
Steps 3-7: user runs the real command, then types "튜토" to advance.
"""

import asyncio
import logging
import random

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from database import queries
from utils.card_generator import generate_card
from utils.helpers import ball_emoji, icon_emoji

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


# ============================================================
# Helper: send card image
# ============================================================

async def _send_card(context, user_id: int, pokemon_id: int, caption: str):
    """Generate and send a pokemon card image to user DM."""
    poke = await queries.get_pokemon(pokemon_id)
    if not poke:
        logger.error(f"Tutorial: pokemon {pokemon_id} not found in DB")
        return
    loop = asyncio.get_event_loop()
    card_buf = await loop.run_in_executor(
        None, generate_card,
        pokemon_id, poke["name_ko"], poke["rarity"], poke["emoji"], False,
    )
    await context.bot.send_photo(
        chat_id=user_id,
        photo=card_buf,
        caption=caption,
        parse_mode="HTML",
    )


async def _give_tutorial_pokemon(user_id: int, pokemon_id: int):
    """Add a tutorial Pokemon to user's collection."""
    try:
        await queries.give_pokemon_to_user(user_id, pokemon_id, chat_id=None)
    except Exception as e:
        logger.error(f"Failed to give tutorial pokemon {pokemon_id} to {user_id}: {e}")


async def _give_graduation_rewards(user_id: int):
    """Grant tutorial completion rewards: 2 master balls + 200 BP."""
    await queries.add_master_ball(user_id, 2)
    pool = await queries.get_db()
    await pool.execute(
        "UPDATE users SET battle_points = battle_points + 200 WHERE user_id = $1",
        user_id,
    )


# ============================================================
# Step dispatcher — sends the message(s) for each step
# ============================================================

async def _send_step(context, user_id: int, step: int):
    """Send tutorial messages for the given step."""
    bot = context.bot

    if step == 1:
        game = icon_emoji("game")
        ham = icon_emoji("ham")
        battle = icon_emoji("battle")
        pokedex = icon_emoji("pokedex")
        await bot.send_message(
            chat_id=user_id,
            text=(
                f"{game} <b>포켓몬 봇에 오신 걸 환영합니다!</b>\n"
                "\n"
                "방금 첫 포획을 시도하셨네요!\n"
                "이 봇에는 포획 외에도 다양한 시스템이 있어요:\n"
                "\n"
                f"{ham} 육성 — 밥/놀기로 친밀도 올리기\n"
                f"{battle} 배틀 — 팀을 짜서 다른 트레이너와 대전\n"
                f"{pokedex} 도감 — 포켓몬 수집 & 칭호 해금\n"
                "\n"
                "하나씩 알려드릴게요!"
            ),
            parse_mode="HTML",
        )
        await bot.send_message(
            chat_id=user_id,
            text="💡 시작하려면 <b>\"튜토\"</b>를 입력하세요!",
            parse_mode="HTML",
        )

    elif step == 20:
        # Step 2a: 포켓볼 설명 + 이브이 카드
        pokeball = ball_emoji("pokeball")
        gotcha = icon_emoji("gotcha")
        await bot.send_message(
            chat_id=user_id,
            text=(
                f"{gotcha} <b>【포획 체험】</b>\n"
                "━━━━━━━━━━━━━━━\n"
                "\n"
                "채팅방에서 포켓몬이 나타나면\n"
                f"<b>ㅊ</b> 을 입력하면 {pokeball} 포켓볼이 나갑니다!\n"
                "\n"
                "💡 하루 20회까지 시도 가능\n"
                "💡 봇이 있는 채팅방에서 \"포켓볼 충전\"을 입력하면\n"
                "   10회를 추가 충전할 수 있어요! (1일 1회)"
            ),
            parse_mode="HTML",
        )
        # 이브이 카드 이미지 + 안내
        pokeball = ball_emoji("pokeball")
        await _send_card(context, user_id, _EEVEE_ID,
            f"🟢 야생 <b>이브이</b> 🦊 가 나타났다!\n\n"
            f"{pokeball} <b>ㅊ</b> 을 입력해서 포켓볼을 던져보세요!"
        )

    elif step == 21:
        # Step 2b: 하이퍼볼 설명 + 미뇽 카드
        hyperball = ball_emoji("hyperball")
        await bot.send_message(
            chat_id=user_id,
            text=(
                f"⚠️ 희귀 등급은 일반보다 포획률이 낮아요!\n\n"
                f"💡 {hyperball} <b>하이퍼볼(ㅎ)</b>은 포켓볼보다 포획률이 3배 높아요.\n"
                f"   하나 지급해 드릴테니 던져볼까요?"
            ),
            parse_mode="HTML",
        )
        await _send_card(context, user_id, _DRATINI_ID,
            f"🔵 야생 <b>미뇽</b> 🐉 이 나타났다!\n\n"
            f"{hyperball} <b>ㅎ</b> 을 입력해서 하이퍼볼을 던져보세요!"
        )

    elif step == 22:
        # Step 2c: 마스터볼 구매 안내
        masterball = ball_emoji("masterball")
        await bot.send_message(
            chat_id=user_id,
            text=(
                f"⚠️ 전설 포켓몬은 포획 확률이 매우 낮아요!\n"
                f"   일반 포켓볼이나 하이퍼볼로는 거의 잡을 수 없어요.\n\n"
                f"💡 {masterball} <b>마스터볼(ㅁ)</b>은 100% 포획!\n"
                f"   포켓몬을 잡을 때 굉장히 낮은 확률로 나오거나\n"
                f"   BP상점에서 구매할 수 있어요.\n\n"
                f"🏪 상점에서 마스터볼을 사볼까요?"
            ),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏪 마스터볼 구매!", callback_data="tut_buy_masterball")],
            ]),
        )

    elif step == 23:
        # Step 2d: 전설 카드 이미지 + ㅁ 안내
        legendary_id = await queries.get_tutorial_legendary(user_id)
        if not legendary_id:
            legendary_id = random.choice(_LEGENDARY_IDS)
            await queries.set_tutorial_legendary(user_id, legendary_id)

        poke = await queries.get_pokemon(legendary_id)
        name = poke["name_ko"] if poke else "???"
        emoji = poke["emoji"] if poke else "❓"
        masterball = ball_emoji("masterball")

        await _send_card(context, user_id, legendary_id,
            f"🟡 야생 <b>{name}</b> {emoji} 이(가) 나타났다!\n"
            f"등급: 🟡 전설 (Legendary)\n\n"
            f"{masterball} <b>ㅁ</b> 을 입력해서 마스터볼을 던져보세요!"
        )

    elif step == 24:
        # Step 2 완료: 포획 정리
        pokeball = ball_emoji("pokeball")
        hyperball = ball_emoji("hyperball")
        masterball = ball_emoji("masterball")
        crystal = icon_emoji("crystal")
        await bot.send_message(
            chat_id=user_id,
            text=(
                "🎉 <b>3마리 모두 잡았어요!</b>\n\n"
                "📝 포획 정리:\n"
                f"  {pokeball} <b>ㅊ</b> 포켓볼 — 기본 포획\n"
                f"  {hyperball} <b>ㅎ</b> 하이퍼볼 — 포획률 3배 (BP상점에서 구매)\n"
                f"  {masterball} <b>ㅁ</b> 마스터볼 — 100% 포획 (매우 귀중!)\n\n"
                "💡 채팅방 활동이 많을수록 포켓몬이 자주 등장!\n"
                f"{crystal} 이로치(색이 다른) 포켓몬은 매우 희귀해요!\n\n"
                "👉 <b>\"튜토\"</b>를 입력해서 다음 단계로!"
            ),
            parse_mode="HTML",
        )

    elif step == 3:
        ham = icon_emoji("ham")
        container = icon_emoji("container")
        game = icon_emoji("game")
        love = icon_emoji("pokemon-love")
        await bot.send_message(
            chat_id=user_id,
            text=(
                f"{ham} <b>【육성 시스템】</b>\n"
                "━━━━━━━━━━━━━━━\n\n"
                "잡은 포켓몬을 키워보세요! (DM에서 사용)\n\n"
                f"{container} 내포켓몬 — 보유 포켓몬과 다양한 상호작용!\n"
                f"{ham} 밥 [번호] — 밥 주기 (하루 3회)\n"
                f"{game} 놀기 [번호] — 놀아주기 (하루 2회)\n\n"
                f"{love} 친밀도가 MAX가 되면 진화할 수 있어요!\n"
                "💪 친밀도 MAX 포켓몬은 배틀에서 20% 더 강해져요!\n\n"
                "👉 지금 <b>\"내포켓몬\"</b>을 입력해서 목록을 확인해보세요!\n"
                "   확인 후 <b>\"튜토\"</b>로 다음 단계!"
            ),
            parse_mode="HTML",
        )

    elif step == 4:
        favorite = icon_emoji("favorite")
        eevee = icon_emoji("eevee")
        await bot.send_message(
            chat_id=user_id,
            text=(
                f"{favorite} <b>【파트너 시스템】</b>\n"
                "━━━━━━━━━━━━━━━\n\n"
                f"파트너 포켓몬을 지정하면 상태창에 표시돼요!\n"
                "💪 파트너 포켓몬은 배틀에서 5% 더 강해져요!\n\n"
                f"{eevee} 가장 좋아하는 포켓몬을 파트너로 골라보세요.\n\n"
                "👉 <b>\"파트너\"</b>를 입력해서 파트너를 골라보세요!\n"
                "   확인 후 <b>\"튜토\"</b>로 다음 단계!"
            ),
            parse_mode="HTML",
        )

    elif step == 5:
        battle = icon_emoji("battle")
        masterball = ball_emoji("masterball")
        await bot.send_message(
            chat_id=user_id,
            text=(
                f"{battle} <b>【배틀 시스템】</b>\n"
                "━━━━━━━━━━━━━━━\n\n"
                "1️⃣ 팀등록 — 최대 6마리로 배틀 팀 구성\n"
                "2️⃣ 채팅방에서 상대에게 답장 + \"배틀\" → 도전!\n"
                "3️⃣ 상대가 \"배틀수락\"하면 자동 대전!\n\n"
                "💰 승리 시 BP(배틀포인트) 획득\n"
                f"🏪 BP상점에서 {masterball} 마스터볼 등 다양한 상품을 구매할 수 있어요!\n\n"
                "🎲 야차 — BP/마스터볼을 걸고 베팅 배틀!\n\n"
                "👉 <b>\"팀등록\"</b>으로 첫 팀을 만들어보세요!\n"
                "   확인 후 <b>\"튜토\"</b>로 다음 단계!"
            ),
            parse_mode="HTML",
        )

    elif step == 6:
        pokedex = icon_emoji("pokedex")
        container = icon_emoji("container")
        bookmark = icon_emoji("bookmark")
        gotcha = icon_emoji("gotcha")
        await bot.send_message(
            chat_id=user_id,
            text=(
                f"{pokedex} <b>【도감 & 칭호】</b>\n"
                "━━━━━━━━━━━━━━━\n\n"
                f"{pokedex} 도감 — 수집한 포켓몬 확인 (1세대/2세대)\n"
                f"{container} 내포켓몬 — 보유 포켓몬과 다양한 상호작용!\n"
                f"{bookmark} 칭호 — 조건 달성 시 칭호 해금!\n\n"
                f"{gotcha} 도감 완성률을 높이면 특별 칭호를 얻을 수 있어요!\n\n"
                "👉 <b>\"도감\"</b>을 입력해서 확인해보세요!\n"
                "   확인 후 <b>\"튜토\"</b>로 다음 단계!"
            ),
            parse_mode="HTML",
        )

    elif step == 7:
        computer = icon_emoji("computer")
        pikachu = icon_emoji("pikachu")
        await bot.send_message(
            chat_id=user_id,
            text=(
                f"{computer} <b>【채팅방 셋팅】</b>\n"
                "━━━━━━━━━━━━━━━\n\n"
                "내 채팅방에도 봇을 추가할 수 있어요!\n\n"
                "1️⃣ 10명 이상인 채팅방에 봇을 초대\n"
                "2️⃣ /start 입력으로 봇 활성화\n"
                f"3️⃣ \"강스\" 입력하면 즉시 {pikachu} 포켓몬 출현!\n\n"
                "💡 채팅방 인원이 많을수록 포켓몬이 자주 나와요!\n\n"
                "👉 <b>\"튜토\"</b>를 입력해서 다음 단계로!"
            ),
            parse_mode="HTML",
        )

    elif step == 8:
        # 졸업! 보상 지급 + 칭호 해금
        await _give_graduation_rewards(user_id)
        await queries.unlock_title(user_id, "tutorial_grad")
        await queries.update_tutorial_step(user_id, 99)
        pikachu = icon_emoji("pikachu")
        masterball = ball_emoji("masterball")
        bookmark = icon_emoji("bookmark")
        crystal = icon_emoji("crystal")
        battle = icon_emoji("battle")
        windy = icon_emoji("windy")
        await bot.send_message(
            chat_id=user_id,
            text=(
                "🎓 <b>튜토리얼 완료! 축하합니다!</b>\n\n"
                "🎁 졸업 보상이 지급되었습니다:\n"
                f"  {masterball} 마스터볼 x2\n"
                "  💰 BP +200\n"
                f"  {bookmark} 칭호 「{pikachu} 내 꿈은 피카츄!」 해금!\n\n"
                "━━━━━━━━━━━━━━━\n"
                "📌 유용한 꿀팁:\n"
                f"• 감정 [이름] — 개체값(IV) 확인\n"
                f"• {battle} 상성 [타입] — 배틀 타입 상성표\n"
                f"• 출석 — 매일 출석 보상\n"
                f"• {windy} 날씨에 따라 특정 타입 포획률 UP!\n"
                "━━━━━━━━━━━━━━━\n\n"
                "🏠 공식방: https://t.me/tg_poke\n"
                f"{crystal} 30초마다 포켓몬이 출현해요!\n"
                "🏆 매일 저녁 9시 대회 접수, 10시 포켓몬 마스터 대회!\n\n"
                "도움이 필요하면 언제든 \"도움말\"을 입력하세요!"
            ),
            parse_mode="HTML",
        )


# ============================================================
# send_tutorial_step — called from group catch_handler trigger
# ============================================================

async def send_tutorial_step(context: ContextTypes.DEFAULT_TYPE, user_id: int, step: int):
    """Send a tutorial step message via DM (used by group catch trigger)."""
    try:
        await _send_step(context, user_id, step)
    except Exception as e:
        logger.warning(f"Failed to send tutorial DM to {user_id}: {e}")


# ============================================================
# "튜토" DM handler — advance to next step
# ============================================================

# Step transition map: current_step → next_step
_NEXT_STEP = {
    1: 20,     # 환영 → 포획 체험 시작
    24: 3,     # 포획 완료 → 육성
    3: 4,      # 육성 → 파트너
    4: 5,      # 파트너 → 배틀
    5: 6,      # 배틀 → 도감
    6: 7,      # 도감 → 채팅방
    7: 8,      # 채팅방 → 졸업
}


async def tutorial_dm_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '튜토' text in DM — advance tutorial to next step."""
    user_id = update.effective_user.id
    step = await queries.get_tutorial_step(user_id)

    # 비-튜토리얼 유저는 무시 (0=미시작, 98=스킵, 99=완료)
    if step in (0, 98, 99):
        return

    next_step = _NEXT_STEP.get(step)
    if not next_step:
        # 현재 스텝에서 "튜토"가 의미 없음 (예: step 20/21/22/23은 ㅊ/ㅎ/ㅁ 대기 중)
        await update.message.reply_text(
            "💡 현재 단계를 먼저 완료해주세요!"
        )
        return

    await queries.update_tutorial_step(user_id, next_step)
    await _send_step(context, user_id, next_step)


# ============================================================
# ㅊ/ㅎ/ㅁ DM handler — tutorial catch actions
# ============================================================

async def tutorial_dm_catch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle ㅊ/ㅎ/ㅁ text in DM — tutorial catch actions."""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    step = await queries.get_tutorial_step(user_id)

    # ㅊ — 포켓볼 (step 20 대기 중일 때만)
    if text == "ㅊ" and step == 20:
        pokeball = ball_emoji("pokeball")
        await update.message.reply_text(f"{pokeball} 포켓볼을 던졌다!", parse_mode="HTML")
        await asyncio.sleep(3)
        await _give_tutorial_pokemon(user_id, _EEVEE_ID)
        await context.bot.send_message(
            chat_id=user_id,
            text="✅ <b>이브이</b> 🦊 포획 성공! 내 포켓몬에 추가되었어요.",
            parse_mode="HTML",
        )
        # 다음: 미뇽 (step 21)
        await queries.update_tutorial_step(user_id, 21)
        await asyncio.sleep(1)
        await _send_step(context, user_id, 21)

    # ㅎ — 하이퍼볼 (step 21 대기 중일 때만)
    elif text == "ㅎ" and step == 21:
        hyperball = ball_emoji("hyperball")
        await update.message.reply_text(f"{hyperball} 하이퍼볼을 던졌다!", parse_mode="HTML")
        await asyncio.sleep(3)
        await _give_tutorial_pokemon(user_id, _DRATINI_ID)
        await context.bot.send_message(
            chat_id=user_id,
            text="✅ <b>미뇽</b> 🐉 포획 성공! 내 포켓몬에 추가되었어요.",
            parse_mode="HTML",
        )
        # 다음: 마스터볼 구매 안내 (step 22)
        await queries.update_tutorial_step(user_id, 22)
        await asyncio.sleep(1)
        await _send_step(context, user_id, 22)

    # ㅁ — 마스터볼 (step 23 대기 중일 때만)
    elif text == "ㅁ" and step == 23:
        legendary_id = await queries.get_tutorial_legendary(user_id)
        if not legendary_id:
            legendary_id = random.choice(_LEGENDARY_IDS)
            await queries.set_tutorial_legendary(user_id, legendary_id)

        poke = await queries.get_pokemon(legendary_id)
        name = poke["name_ko"] if poke else "???"
        emoji = poke["emoji"] if poke else "❓"

        masterball = ball_emoji("masterball")
        await update.message.reply_text(f"{masterball} 마스터볼을 던졌다!", parse_mode="HTML")
        await asyncio.sleep(3)
        await _give_tutorial_pokemon(user_id, legendary_id)
        await context.bot.send_message(
            chat_id=user_id,
            text=f"✅ <b>{name}</b> {emoji} 포획 성공! 내 포켓몬에 추가되었어요.",
            parse_mode="HTML",
        )
        # 다음: 포획 완료 정리 (step 24)
        await queries.update_tutorial_step(user_id, 24)
        await asyncio.sleep(1)
        await _send_step(context, user_id, 24)

    else:
        # 현재 스텝에서 이 입력은 의미 없음 → 무시 (다른 핸들러로 fall-through)
        return


# ============================================================
# Callback handler — 스킵/재시작/마볼 구매 버튼만
# ============================================================

async def tutorial_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle tut_* inline button callbacks."""
    query = update.callback_query
    if not query or not query.data:
        return

    await query.answer()
    user_id = query.from_user.id
    data = query.data

    # tut_buy_masterball — 마스터볼 구매 (튜토리얼 무료)
    if data == "tut_buy_masterball":
        step = await queries.get_tutorial_step(user_id)
        if step != 22:
            return  # 이미 지나간 단계
        masterball = ball_emoji("masterball")
        await context.bot.send_message(
            chat_id=user_id,
            text=f"{masterball} 마스터볼 1개 구매 완료! (튜토리얼 무료)",
            parse_mode="HTML",
        )
        # 다음: 전설 카드 (step 23)
        # 전설 포켓몬 랜덤 선정 + 저장
        legendary_id = random.choice(_LEGENDARY_IDS)
        await queries.set_tutorial_legendary(user_id, legendary_id)
        await queries.update_tutorial_step(user_id, 23)
        await asyncio.sleep(1)
        await _send_step(context, user_id, 23)
