"""Battle system handlers: partner, team, challenge, accept/decline, rankings, BP shop."""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import config
from database import queries
from database import battle_queries as bq
from utils.battle_calc import calc_battle_stats, format_stats_line, get_type_multiplier

logger = logging.getLogger(__name__)


# ============================================================
# Partner Pokemon (/파트너)
# ============================================================

async def partner_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 파트너 command (DM). Show current or set partner."""
    if not update.effective_user:
        return

    user_id = update.effective_user.id
    await queries.ensure_user(
        user_id,
        update.effective_user.first_name or "트레이너",
        update.effective_user.username,
    )

    text = (update.message.text or "").strip()
    parts = text.split()

    # "파트너" alone → show current partner
    if len(parts) == 1:
        partner = await bq.get_partner(user_id)
        if not partner:
            await update.message.reply_text(
                "🤝 아직 파트너 포켓몬이 없습니다.\n\n"
                "파트너 [번호] — 내포켓몬 번호로 파트너 지정\n"
                "예: 파트너 3"
            )
            return

        stats = calc_battle_stats(partner["rarity"], partner["stat_type"], partner["friendship"])
        type_emoji = config.TYPE_EMOJI.get(partner["pokemon_type"], "")
        type_name = config.TYPE_NAME_KO.get(partner["pokemon_type"], "")
        await update.message.reply_text(
            f"🤝 나의 파트너\n\n"
            f"{partner['emoji']} {partner['name_ko']}  {type_emoji}{type_name}\n"
            f"📊 {format_stats_line(stats)}\n\n"
            f"💡 배틀 시 파트너가 팀에 포함되면 ATK +5%!"
        )
        return

    # "파트너 3" → set partner
    try:
        num = int(parts[1])
    except (ValueError, IndexError):
        await update.message.reply_text("사용법: 파트너 [내포켓몬 번호]")
        return

    pokemon_list = await queries.get_user_pokemon_list(user_id)
    if not pokemon_list:
        await update.message.reply_text("보유한 포켓몬이 없습니다.")
        return

    if num < 1 or num > len(pokemon_list):
        await update.message.reply_text(f"1~{len(pokemon_list)} 범위에서 선택해주세요.")
        return

    chosen = pokemon_list[num - 1]
    instance_id = chosen["id"]

    await bq.set_partner(user_id, instance_id)

    await update.message.reply_text(
        f"🤝 {chosen['emoji']} {chosen['name_ko']}을(를) 파트너로 지정했습니다!\n"
        f"배틀 시 파트너가 팀에 포함되면 ATK +5% 보너스!"
    )

    # Unlock partner title
    if not await queries.has_title(user_id, "partner_set"):
        await queries.unlock_title(user_id, "partner_set")


# ============================================================
# Battle Team (/팀, /팀등록, /팀해제)
# ============================================================

async def team_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 팀 command (DM). Show current battle team."""
    if not update.effective_user:
        return

    user_id = update.effective_user.id
    await queries.ensure_user(
        user_id,
        update.effective_user.first_name or "트레이너",
        update.effective_user.username,
    )

    team = await bq.get_battle_team(user_id)
    if not team:
        await update.message.reply_text(
            "⚔️ 배틀 팀이 없습니다.\n\n"
            "팀등록 [번호들] — 내포켓몬 번호로 팀 등록 (최대 6마리)\n"
            "예: 팀등록 3 1 5 2"
        )
        return

    # Get partner for marking
    partner = await bq.get_partner(user_id)
    partner_instance = partner["instance_id"] if partner else None

    slot_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣"]
    lines = ["⚔️ 나의 배틀 팀\n"]

    for i, p in enumerate(team):
        stats = calc_battle_stats(p["rarity"], p["stat_type"], p["friendship"])
        type_emoji = config.TYPE_EMOJI.get(p["pokemon_type"], "")
        partner_mark = " 🤝" if p["pokemon_instance_id"] == partner_instance else ""
        lines.append(
            f"{slot_emojis[i]} {type_emoji}{p['emoji']} {p['name_ko']}{partner_mark}  "
            f"{format_stats_line(stats)}"
        )

    lines.append(f"\n팀등록 [번호들] 로 변경 가능")
    await update.message.reply_text("\n".join(lines))


async def team_register_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 팀등록 command (DM). Register battle team."""
    if not update.effective_user:
        return

    user_id = update.effective_user.id
    await queries.ensure_user(
        user_id,
        update.effective_user.first_name or "트레이너",
        update.effective_user.username,
    )

    text = (update.message.text or "").strip()
    parts = text.split()

    if len(parts) < 2:
        await update.message.reply_text(
            "사용법: 팀등록 [내포켓몬 번호들]\n"
            "예: 팀등록 3 1 5 2 (최소 1마리, 최대 6마리)"
        )
        return

    # Parse numbers
    try:
        nums = [int(x) for x in parts[1:7]]  # Max 6
    except ValueError:
        await update.message.reply_text("숫자만 입력해주세요. 예: 팀등록 3 1 5 2")
        return

    if len(nums) < 1:
        await update.message.reply_text("최소 1마리 이상 등록해야 합니다.")
        return

    if len(set(nums)) != len(nums):
        await update.message.reply_text("중복된 번호가 있습니다. 서로 다른 포켓몬을 선택하세요.")
        return

    # Get user's pokemon list
    pokemon_list = await queries.get_user_pokemon_list(user_id)
    if not pokemon_list:
        await update.message.reply_text("보유한 포켓몬이 없습니다.")
        return

    # Validate all numbers are in range
    for n in nums:
        if n < 1 or n > len(pokemon_list):
            await update.message.reply_text(
                f"번호 {n}이(가) 범위를 벗어났습니다. (1~{len(pokemon_list)})"
            )
            return

    # Map numbers to instance IDs
    instance_ids = [pokemon_list[n - 1]["id"] for n in nums]

    await bq.set_battle_team(user_id, instance_ids)

    # Build confirmation
    lines = ["⚔️ 배틀 팀 등록 완료!\n"]
    slot_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣"]
    for i, n in enumerate(nums):
        p = pokemon_list[n - 1]
        type_emoji = config.TYPE_EMOJI.get(
            getattr(p, "pokemon_type", "normal") if hasattr(p, "pokemon_type") else "normal",
            ""
        )
        lines.append(f"{slot_emojis[i]} {p['emoji']} {p['name_ko']}")

    await update.message.reply_text("\n".join(lines))


async def team_clear_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 팀해제 command (DM). Clear battle team."""
    if not update.effective_user:
        return

    user_id = update.effective_user.id
    await bq.clear_battle_team(user_id)
    await update.message.reply_text("⚔️ 배틀 팀이 해제되었습니다.")


# ============================================================
# Battle Stats (/배틀전적, /BP)
# ============================================================

async def battle_stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 배틀전적 command (DM). Show user's battle record."""
    if not update.effective_user:
        return

    user_id = update.effective_user.id
    stats = await bq.get_battle_stats(user_id)

    wins = stats["battle_wins"]
    losses = stats["battle_losses"]
    total = wins + losses
    win_rate = round(wins / total * 100, 1) if total > 0 else 0

    lines = [
        "⚔️ 나의 배틀 전적\n",
        f"🏆 {wins}승 {losses}패  ({win_rate}%)",
        f"🔥 현재 연승: {stats['battle_streak']}",
        f"💫 최고 연승: {stats['best_streak']}",
        f"💰 보유 BP: {stats['battle_points']}",
    ]

    await update.message.reply_text("\n".join(lines))


async def bp_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle BP command (DM). Show BP balance."""
    if not update.effective_user:
        return

    user_id = update.effective_user.id
    bp = await bq.get_bp(user_id)
    await update.message.reply_text(f"💰 보유 BP: {bp}\n\nBP상점 으로 교환 가능")


async def bp_shop_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle BP상점 command (DM). Show BP shop."""
    if not update.effective_user:
        return

    user_id = update.effective_user.id
    bp = await bq.get_bp(user_id)

    lines = [
        "🏪 BP 상점\n",
        f"💰 보유 BP: {bp}\n",
        f"🟣 마스터볼 x1 — {config.BP_MASTERBALL_COST} BP",
        "",
        "구매: BP구매 마스터볼",
    ]

    await update.message.reply_text("\n".join(lines))


async def bp_buy_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle BP구매 command (DM). Purchase from BP shop."""
    if not update.effective_user:
        return

    user_id = update.effective_user.id
    text = (update.message.text or "").strip()
    parts = text.split()

    if len(parts) < 2:
        await update.message.reply_text("사용법: BP구매 마스터볼")
        return

    item = parts[1]
    if item in ("마스터볼", "마볼"):
        cost = config.BP_MASTERBALL_COST
        success = await bq.spend_bp(user_id, cost)
        if not success:
            bp = await bq.get_bp(user_id)
            await update.message.reply_text(
                f"BP가 부족합니다. (보유: {bp} / 필요: {cost})"
            )
            return

        await queries.add_master_ball(user_id, 1)
        bp = await bq.get_bp(user_id)
        await update.message.reply_text(
            f"🟣 마스터볼 1개 구매 완료!\n"
            f"💰 남은 BP: {bp}"
        )
    else:
        await update.message.reply_text("알 수 없는 상품입니다. BP상점 으로 목록을 확인하세요.")


# ============================================================
# Battle Challenge (Group: 배틀 @유저)
# ============================================================

async def battle_challenge_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 배틀 command (group). Challenge another user."""
    if not update.effective_user or not update.message:
        return

    chat_id = update.effective_chat.id
    challenger_id = update.effective_user.id
    challenger_name = update.effective_user.first_name or "트레이너"

    # Must reply to someone or mention
    reply = update.message.reply_to_message
    if not reply or not reply.from_user:
        await update.message.reply_text(
            "⚔️ 배틀을 신청하려면 상대방의 메시지에 답장하며 '배틀'을 입력하세요!"
        )
        return

    defender_id = reply.from_user.id
    defender_name = reply.from_user.first_name or "트레이너"

    # Can't battle yourself
    if challenger_id == defender_id:
        await update.message.reply_text("자기 자신에게 배틀을 신청할 수 없습니다.")
        return

    # Can't battle bots
    if reply.from_user.is_bot:
        await update.message.reply_text("봇에게는 배틀을 신청할 수 없습니다.")
        return

    # Ensure both users exist
    await queries.ensure_user(challenger_id, challenger_name, update.effective_user.username)
    await queries.ensure_user(defender_id, defender_name, reply.from_user.username)

    # Check cooldowns
    from datetime import datetime, timedelta

    # Same opponent cooldown
    last_vs = await bq.get_last_battle_time(challenger_id, defender_id)
    if last_vs:
        last_time = datetime.fromisoformat(last_vs.replace("+00:00", "+00:00"))
        cooldown = timedelta(seconds=config.BATTLE_COOLDOWN_SAME)
        if datetime.now(last_time.tzinfo) - last_time < cooldown:
            remaining = cooldown - (datetime.now(last_time.tzinfo) - last_time)
            mins = int(remaining.total_seconds() // 60)
            await update.message.reply_text(
                f"같은 상대와의 배틀은 {config.BATTLE_COOLDOWN_SAME // 60}분 쿨다운입니다. "
                f"({mins}분 남음)"
            )
            return

    # Global cooldown
    last_any = await bq.get_last_battle_time_any(challenger_id)
    if last_any:
        last_time = datetime.fromisoformat(last_any.replace("+00:00", "+00:00"))
        cooldown = timedelta(seconds=config.BATTLE_COOLDOWN_GLOBAL)
        if datetime.now(last_time.tzinfo) - last_time < cooldown:
            remaining = cooldown - (datetime.now(last_time.tzinfo) - last_time)
            secs = int(remaining.total_seconds())
            await update.message.reply_text(
                f"배틀 쿨다운 중입니다. ({secs}초 남음)"
            )
            return

    # Check challenger has a team
    c_team = await bq.get_battle_team(challenger_id)
    if not c_team:
        await update.message.reply_text(
            "⚔️ 배틀 팀이 없습니다!\n"
            "DM에서 '팀등록 [번호들]'로 먼저 팀을 등록하세요."
        )
        return

    # Check for existing pending challenge
    existing = await bq.get_pending_challenge(challenger_id, defender_id)
    if existing:
        await update.message.reply_text("이미 대기 중인 배틀 신청이 있습니다.")
        return

    # Create challenge
    from datetime import timezone
    expires = (datetime.now(timezone.utc) + timedelta(seconds=config.BATTLE_CHALLENGE_TIMEOUT))
    expires_str = expires.isoformat()

    challenge_id = await bq.create_challenge(
        challenger_id, defender_id, chat_id, expires_str
    )

    # Send challenge message with inline buttons
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✅ 수락",
                callback_data=f"battle_accept_{challenge_id}_{defender_id}",
            ),
            InlineKeyboardButton(
                "❌ 거절",
                callback_data=f"battle_decline_{challenge_id}_{defender_id}",
            ),
        ]
    ])

    await update.message.reply_text(
        f"⚔️ {challenger_name}님이 {defender_name}님에게 배틀을 신청했습니다!\n"
        f"{config.BATTLE_CHALLENGE_TIMEOUT}초 내에 수락해주세요!",
        reply_markup=buttons,
    )


# ============================================================
# Battle Accept/Decline Callback
# ============================================================

async def battle_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle battle accept/decline inline button callbacks."""
    query = update.callback_query
    if not query or not query.data:
        return

    data = query.data
    if not data.startswith("battle_"):
        return

    await query.answer()

    parts = data.split("_")
    # battle_accept_{challenge_id}_{defender_id}
    # battle_decline_{challenge_id}_{defender_id}
    action = parts[1]
    challenge_id = int(parts[2])
    expected_defender = int(parts[3])

    # Only the defender can respond
    if query.from_user.id != expected_defender:
        await query.answer("본인만 응답할 수 있습니다!", show_alert=True)
        return

    challenge = await bq.get_challenge_by_id(challenge_id)
    if not challenge:
        try:
            await query.edit_message_text("배틀 신청을 찾을 수 없습니다.")
        except Exception:
            pass
        return

    if challenge["status"] != "pending":
        try:
            await query.edit_message_text("이미 처리된 배틀 신청입니다.")
        except Exception:
            pass
        return

    # Check if expired
    from datetime import datetime, timezone
    expires = challenge["expires_at"]
    if hasattr(expires, 'tzinfo') and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expires:
        await bq.update_challenge_status(challenge_id, "expired")
        try:
            await query.edit_message_text("⏰ 배틀 신청이 만료되었습니다.")
        except Exception:
            pass
        return

    if action == "decline":
        await bq.update_challenge_status(challenge_id, "declined")
        try:
            await query.edit_message_text("❌ 배틀이 거절되었습니다.")
        except Exception:
            pass
        return

    if action == "accept":
        # Check defender has a team
        d_team = await bq.get_battle_team(expected_defender)
        if not d_team:
            try:
                await query.edit_message_text(
                    "⚔️ 수비자의 배틀 팀이 없습니다!\n"
                    "DM에서 '팀등록 [번호들]'로 먼저 팀을 등록하세요."
                )
            except Exception:
                pass
            return

        c_team = await bq.get_battle_team(challenge["challenger_id"])
        if not c_team:
            try:
                await query.edit_message_text("⚔️ 도전자의 배틀 팀이 없습니다!")
            except Exception:
                pass
            return

        await bq.update_challenge_status(challenge_id, "accepted")

        # Run the battle!
        from services.battle_service import execute_battle
        result = await execute_battle(
            challenger_id=challenge["challenger_id"],
            defender_id=expected_defender,
            challenger_team=c_team,
            defender_team=d_team,
            challenge_id=challenge_id,
            chat_id=challenge["chat_id"],
        )

        try:
            await query.edit_message_text(
                result["display_text"],
                parse_mode=None,
            )
        except Exception:
            # If message too long, try sending new message
            try:
                await context.bot.send_message(
                    chat_id=challenge["chat_id"],
                    text=result["display_text"],
                )
            except Exception:
                pass


# ============================================================
# Battle Ranking (Group: 배틀랭킹)
# ============================================================

async def battle_ranking_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 배틀랭킹 command (group). Show battle leaderboard."""
    rankings = await bq.get_battle_ranking(10)

    if not rankings:
        await update.message.reply_text("아직 배틀 기록이 없습니다.")
        return

    medals = ["🥇", "🥈", "🥉"]
    lines = ["⚔️ 배틀 랭킹\n"]

    for i, r in enumerate(rankings):
        rank = medals[i] if i < 3 else f"{i + 1}."
        title = f"「{r['title_emoji']}{r['title']}」" if r["title"] else ""
        total = r["battle_wins"] + r["battle_losses"]
        rate = round(r["battle_wins"] / total * 100) if total > 0 else 0
        lines.append(
            f"{rank} {title}{r['display_name']}  "
            f"{r['battle_wins']}승 {r['battle_losses']}패 ({rate}%) "
            f"🔥{r['best_streak']}"
        )

    await update.message.reply_text("\n".join(lines))


# ============================================================
# Text command aliases for accept/decline
# ============================================================

async def battle_accept_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '배틀수락' text command in group."""
    if not update.effective_user:
        return
    # For simplicity, just remind to use the button
    await update.message.reply_text(
        "배틀 수락은 위의 ✅ 수락 버튼을 눌러주세요!"
    )


async def battle_decline_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '배틀거절' text command in group."""
    if not update.effective_user:
        return
    await update.message.reply_text(
        "배틀 거절은 위의 ❌ 거절 버튼을 눌러주세요!"
    )
