"""DM handler for Weekly Boss raid."""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import config
from database import boss_queries as bq
from services.boss_service import (
    get_current_boss, attack_boss, current_week_key, today_kst,
    get_weakness_types,
)
from utils.helpers import icon_emoji

logger = logging.getLogger(__name__)


def _hp_bar(current: int, max_hp: int, length: int = 10) -> str:
    pct = max(0, current / max_hp) if max_hp > 0 else 0
    filled = round(pct * length)
    return "█" * filled + "░" * (length - filled)


def _format_number(n: int) -> str:
    return f"{n:,}"


async def boss_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """DM '보스' command — show boss info + attack button."""
    if not update.effective_user or not update.message:
        return
    user_id = update.effective_user.id

    boss = await get_current_boss()
    if not boss:
        await update.message.reply_text("❌ 현재 활성 보스가 없습니다.")
        return

    await _show_boss_info(update.message, user_id, boss)


async def _show_boss_info(message, user_id: int, boss: dict):
    """Render boss info screen."""
    wk = boss["week_key"]
    pct = max(0, boss["current_hp"] / boss["max_hp"] * 100) if boss["max_hp"] > 0 else 0
    bar = _hp_bar(boss["current_hp"], boss["max_hp"])

    # Weakness
    weaknesses = get_weakness_types(boss["boss_types"])
    type_names = [config.TYPE_NAME_KO.get(t, t) for t in boss["boss_types"]]
    type_emojis = " ".join(config.TYPE_EMOJI.get(t, "") for t in boss["boss_types"])
    weak_names = ", ".join(config.TYPE_NAME_KO.get(t, t) for t in weaknesses)

    # User stats
    weekly = await bq.get_weekly_damage(wk, user_id)
    rank = await bq.get_user_rank(wk, user_id)
    today = today_kst()
    attacked = await bq.has_attacked_today(wk, user_id, today)
    today_dmg = await bq.get_today_damage(wk, user_id, today) if attacked else 0
    participant_count = await bq.get_participant_count(wk)

    defeated_mark = " ✅ 처치!" if boss["defeated"] else ""

    lines = [
        f"{icon_emoji('battle')} <b>주간보스: {boss['pokemon_name']}</b>{defeated_mark}",
        "━━━━━━━━━━━━━━━",
        f"❤️ HP: {_format_number(boss['current_hp'])} / {_format_number(boss['max_hp'])} ({pct:.1f}%)",
        f"{bar}",
        "",
        f"{type_emojis} 속성: {'/'.join(type_names)}",
        f"💡 약점: {weak_names}" if weak_names else "",
        f"👥 참여자: {participant_count}명",
        "",
        "━━━━━━━━━━━━━━━",
        f"📊 <b>내 기록</b>",
        f"  오늘: {'✅ ' + _format_number(today_dmg) + ' 딜' if attacked else '미공격'}",
        f"  주간: {_format_number(weekly['total_damage'])} ({weekly['attack_count']}회)" + (f" — {rank}위" if rank else ""),
    ]

    buttons = []
    if not attacked and not boss["defeated"]:
        buttons.append([InlineKeyboardButton("⚔️ 공격!", callback_data=f"boss_atk_{user_id}")])
    buttons.append([InlineKeyboardButton("📊 랭킹", callback_data=f"boss_rank_{user_id}")])

    markup = InlineKeyboardMarkup(buttons) if buttons else None
    await message.reply_text(
        "\n".join(l for l in lines if l is not None),
        reply_markup=markup,
        parse_mode="HTML",
    )


async def boss_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle boss_* callbacks."""
    query = update.callback_query
    if not query or not query.data:
        return

    data = query.data
    user_id = query.from_user.id

    if data.startswith("boss_atk_"):
        target_uid = int(data.split("_")[2])
        if user_id != target_uid:
            await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
            return
        await _handle_attack(query, context, user_id)

    elif data.startswith("boss_rank_"):
        await _handle_ranking(query, user_id)

    elif data.startswith("boss_back_"):
        target_uid = int(data.split("_")[2])
        if user_id != target_uid:
            await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
            return
        boss = await get_current_boss()
        if boss:
            await query.answer()
            await _edit_boss_info(query, user_id, boss)


async def _handle_attack(query, context, user_id: int):
    """Execute boss attack."""
    await query.answer("⚔️ 보스전 시작!")

    result = await attack_boss(user_id)

    if not result["success"]:
        if result.get("error") == "already_attacked":
            await query.edit_message_text(
                f"❌ 오늘은 이미 공격했습니다!\n"
                f"딜량: {_format_number(result.get('today_damage', 0))}",
                parse_mode="HTML",
            )
        else:
            await query.edit_message_text(f"❌ {result['error']}", parse_mode="HTML")
        return

    damage = result["damage"]
    boss = result["boss"]
    milestones = result["milestones"]
    defeated_now = result["defeated_now"]

    pct = max(0, boss["current_hp"] / boss["max_hp"] * 100) if boss["max_hp"] > 0 else 0
    bar = _hp_bar(boss["current_hp"], boss["max_hp"])

    # Battle summary
    br = result["battle_result"]
    winner_side = br.get("winner", "")
    remaining = br.get("winner_remaining", 0)

    lines = [
        f"⚔️ <b>보스전 결과!</b>",
        "━━━━━━━━━━━━━━━",
        f"🐉 {boss['pokemon_name']} vs 내 팀",
        "",
        f"💥 총 딜량: <b>{_format_number(damage)}</b>",
        f"❤️ 보스 HP: {_format_number(boss['current_hp'])} / {_format_number(boss['max_hp'])} ({pct:.1f}%)",
        f"{bar}",
    ]

    # Milestone rewards
    if milestones:
        reward_parts = []
        if milestones.get("bp"):
            reward_parts.append(f"💰 {milestones['bp']}BP")
        if milestones.get("fragments"):
            reward_parts.append(f"🧩 조각 {milestones['fragments']}개")
        if milestones.get("iv_reroll_one"):
            reward_parts.append(f"🔄 IV리롤 {milestones['iv_reroll_one']}개")
        lines.append("")
        lines.append(f"🎁 보상: {' + '.join(reward_parts)}")

    # Defeated
    if defeated_now:
        lines.extend([
            "",
            "🎉🎉🎉 <b>보스 처치!</b> 🎉🎉🎉",
            "참여자 전원에게 보너스가 지급됩니다!",
        ])

    buttons = [[InlineKeyboardButton("📊 랭킹", callback_data=f"boss_rank_{user_id}")]]
    markup = InlineKeyboardMarkup(buttons)

    try:
        await query.edit_message_text(
            "\n".join(lines),
            reply_markup=markup,
            parse_mode="HTML",
        )
    except Exception:
        pass


async def _handle_ranking(query, user_id: int):
    """Show weekly boss ranking."""
    await query.answer()

    boss = await get_current_boss()
    if not boss:
        await query.edit_message_text("❌ 활성 보스가 없습니다.")
        return

    wk = boss["week_key"]
    ranking = await bq.get_weekly_ranking(wk, limit=20)
    user_rank = await bq.get_user_rank(wk, user_id)
    user_weekly = await bq.get_weekly_damage(wk, user_id)

    pct = max(0, boss["current_hp"] / boss["max_hp"] * 100) if boss["max_hp"] > 0 else 0
    defeated_mark = "✅ 처치!" if boss["defeated"] else f"HP {pct:.1f}%"

    lines = [
        f"📊 <b>주간보스 랭킹</b>",
        f"🐉 {boss['pokemon_name']} | {defeated_mark}",
        "━━━━━━━━━━━━━━━",
    ]

    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    for i, entry in enumerate(ranking):
        rank = i + 1
        medal = medals.get(rank, f"{rank}.")
        name = entry["display_name"]
        dmg = _format_number(entry["total_damage"])
        is_me = " ◀" if entry["user_id"] == user_id else ""
        lines.append(f"{medal} {name} — {dmg}{is_me}")

    if user_rank and user_rank > len(ranking):
        lines.append(f"\n내 순위: {user_rank}위 ({_format_number(user_weekly['total_damage'])})")
    elif not user_rank:
        lines.append("\n아직 참여하지 않았습니다.")

    buttons = [[InlineKeyboardButton("🔙 보스 정보", callback_data=f"boss_back_{user_id}")]]
    markup = InlineKeyboardMarkup(buttons)

    try:
        await query.edit_message_text("\n".join(lines), reply_markup=markup, parse_mode="HTML")
    except Exception:
        pass


async def _edit_boss_info(query, user_id: int, boss: dict):
    """Edit message to show boss info (for back button)."""
    wk = boss["week_key"]
    pct = max(0, boss["current_hp"] / boss["max_hp"] * 100) if boss["max_hp"] > 0 else 0
    bar = _hp_bar(boss["current_hp"], boss["max_hp"])

    weaknesses = get_weakness_types(boss["boss_types"])
    type_names = [config.TYPE_NAME_KO.get(t, t) for t in boss["boss_types"]]
    type_emojis = " ".join(config.TYPE_EMOJI.get(t, "") for t in boss["boss_types"])
    weak_names = ", ".join(config.TYPE_NAME_KO.get(t, t) for t in weaknesses)

    weekly = await bq.get_weekly_damage(wk, user_id)
    rank = await bq.get_user_rank(wk, user_id)
    today = today_kst()
    attacked = await bq.has_attacked_today(wk, user_id, today)
    today_dmg = await bq.get_today_damage(wk, user_id, today) if attacked else 0
    participant_count = await bq.get_participant_count(wk)

    defeated_mark = " ✅ 처치!" if boss["defeated"] else ""

    lines = [
        f"{icon_emoji('battle')} <b>주간보스: {boss['pokemon_name']}</b>{defeated_mark}",
        "━━━━━━━━━━━━━━━",
        f"❤️ HP: {_format_number(boss['current_hp'])} / {_format_number(boss['max_hp'])} ({pct:.1f}%)",
        f"{bar}",
        "",
        f"{type_emojis} 속성: {'/'.join(type_names)}",
        f"💡 약점: {weak_names}" if weak_names else "",
        f"👥 참여자: {participant_count}명",
        "",
        "━━━━━━━━━━━━━━━",
        f"📊 <b>내 기록</b>",
        f"  오늘: {'✅ ' + _format_number(today_dmg) + ' 딜' if attacked else '미공격'}",
        f"  주간: {_format_number(weekly['total_damage'])} ({weekly['attack_count']}회)" + (f" — {rank}위" if rank else ""),
    ]

    buttons = []
    if not attacked and not boss["defeated"]:
        buttons.append([InlineKeyboardButton("⚔️ 공격!", callback_data=f"boss_atk_{user_id}")])
    buttons.append([InlineKeyboardButton("📊 랭킹", callback_data=f"boss_rank_{user_id}")])

    markup = InlineKeyboardMarkup(buttons) if buttons else None
    try:
        await query.edit_message_text(
            "\n".join(l for l in lines if l is not None),
            reply_markup=markup,
            parse_mode="HTML",
        )
    except Exception:
        pass
