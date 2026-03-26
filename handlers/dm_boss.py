"""DM handler for Weekly Boss raid."""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import config
from database import boss_queries as bq
from database import queries
from services.boss_service import (
    get_current_boss, attack_boss, current_week_key, today_kst,
    get_weakness_types,
)
from utils.helpers import icon_emoji, type_badge, rarity_badge, shiny_emoji

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

    # Boss team info
    has_team = await bq.has_boss_team(user_id)
    boss_team = await bq.get_boss_team(user_id) if has_team else None
    if boss_team and has_team:
        team_names = ", ".join(f"{type_badge(p['pokemon_id'], p.get('pokemon_type'))}{p['name_ko']}" for p in boss_team)
        team_line = f"🎯 보스팀: {team_names}"
    else:
        team_line = "🎯 보스팀: 미설정 (배틀팀 사용)"

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
        team_line,
        "",
        "━━━━━━━━━━━━━━━",
        f"📊 <b>내 기록</b>",
        f"  오늘: {'✅ ' + _format_number(today_dmg) + ' 딜' if attacked else '미공격'}",
        f"  주간: {_format_number(weekly['total_damage'])} ({weekly['attack_count']}회)" + (f" — {rank}위" if rank else ""),
    ]

    buttons = []
    if not attacked and not boss["defeated"]:
        buttons.append([InlineKeyboardButton("⚔️ 공격!", callback_data=f"boss_atk_{user_id}")])
    buttons.append([
        InlineKeyboardButton("🔧 보스팀", callback_data=f"boss_team_{user_id}"),
        InlineKeyboardButton("📊 랭킹", callback_data=f"boss_rank_{user_id}"),
    ])

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

    elif data.startswith("boss_team_"):
        target_uid = int(data.split("_")[2])
        if user_id != target_uid:
            await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
            return
        await _handle_team_select(query, user_id, page=0)

    elif data.startswith("boss_tpg_"):
        # boss_tpg_{uid}_{page} — 팀 선택 페이지
        parts = data.split("_")
        target_uid, page = int(parts[2]), int(parts[3])
        if user_id != target_uid:
            await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
            return
        await _handle_team_select(query, user_id, page=page)

    elif data.startswith("boss_tsel_"):
        # boss_tsel_{uid}_{instance_id} — 포켓몬 토글
        parts = data.split("_")
        target_uid, inst_id = int(parts[2]), int(parts[3])
        if user_id != target_uid:
            await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
            return
        await _handle_team_toggle(query, user_id, inst_id)

    elif data.startswith("boss_tsave_"):
        target_uid = int(data.split("_")[2])
        if user_id != target_uid:
            await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
            return
        await _handle_team_save(query, user_id)

    elif data.startswith("boss_tclear_"):
        target_uid = int(data.split("_")[2])
        if user_id != target_uid:
            await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
            return
        await _handle_team_clear(query, user_id)

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

    buttons = [[InlineKeyboardButton("📊 리더보드", callback_data=f"boss_rank_{user_id}")]]
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
        f"📊 <b>리더보드</b>",
        f"🐉 {boss['pokemon_name']} | {defeated_mark}",
        "━━━━━━━━━━━━━━━",
    ]

    total_dmg = sum(r["total_damage"] for r in ranking)
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    for i, entry in enumerate(ranking):
        rank = i + 1
        medal = medals.get(rank, f"{rank}.")
        name = entry["display_name"]
        dmg = _format_number(entry["total_damage"])
        pct_dmg = (entry["total_damage"] / total_dmg * 100) if total_dmg > 0 else 0
        is_me = " ◀" if entry["user_id"] == user_id else ""
        lines.append(f"{medal} {name} — {dmg} ({pct_dmg:.1f}%){is_me}")

    if user_rank and user_rank > len(ranking):
        my_pct = (user_weekly['total_damage'] / total_dmg * 100) if total_dmg > 0 else 0
        lines.append(f"\n내 순위: {user_rank}위 — {_format_number(user_weekly['total_damage'])} ({my_pct:.1f}%)")
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

    has_team = await bq.has_boss_team(user_id)
    boss_team = await bq.get_boss_team(user_id) if has_team else None
    if boss_team and has_team:
        team_names = ", ".join(f"{type_badge(p['pokemon_id'], p.get('pokemon_type'))}{p['name_ko']}" for p in boss_team)
        team_line = f"🎯 보스팀: {team_names}"
    else:
        team_line = "🎯 보스팀: 미설정 (배틀팀 사용)"

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
        team_line,
        "",
        "━━━━━━━━━━━━━━━",
        f"📊 <b>내 기록</b>",
        f"  오늘: {'✅ ' + _format_number(today_dmg) + ' 딜' if attacked else '미공격'}",
        f"  주간: {_format_number(weekly['total_damage'])} ({weekly['attack_count']}회)" + (f" — {rank}위" if rank else ""),
    ]

    buttons = []
    if not attacked and not boss["defeated"]:
        buttons.append([InlineKeyboardButton("⚔️ 공격!", callback_data=f"boss_atk_{user_id}")])
    buttons.append([
        InlineKeyboardButton("🔧 보스팀", callback_data=f"boss_team_{user_id}"),
        InlineKeyboardButton("📊 랭킹", callback_data=f"boss_rank_{user_id}"),
    ])

    markup = InlineKeyboardMarkup(buttons) if buttons else None
    try:
        await query.edit_message_text(
            "\n".join(l for l in lines if l is not None),
            reply_markup=markup,
            parse_mode="HTML",
        )
    except Exception:
        pass


# ── Boss Team Selection ───────────────────────────────────

# In-memory draft for team building (user_id -> list of instance_ids)
_team_drafts: dict[int, list[int]] = {}
PAGE_SIZE = 8


async def _handle_team_select(query, user_id: int, page: int = 0):
    """Show pokemon list for boss team selection."""
    await query.answer()

    # Init draft from current boss team
    if user_id not in _team_drafts:
        if await bq.has_boss_team(user_id):
            current = await bq.get_boss_team(user_id)
            _team_drafts[user_id] = [p["pokemon_instance_id"] for p in current]
        else:
            _team_drafts[user_id] = []

    draft = _team_drafts[user_id]

    # Get all pokemon
    pokemon_list = await queries.get_user_pokemon_list(user_id)
    if not pokemon_list:
        await query.edit_message_text("❌ 포켓몬이 없습니다.")
        return

    total_pages = max(1, (len(pokemon_list) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * PAGE_SIZE
    page_pokemon = pokemon_list[start:start + PAGE_SIZE]

    # Header
    selected_names = []
    for inst_id in draft:
        for p in pokemon_list:
            pid = p.get("pokemon_instance_id") or p.get("id")
            if pid == inst_id:
                selected_names.append(f"{type_badge(p['pokemon_id'], p.get('pokemon_type'))}{p['name_ko']}")
                break

    lines = [
        "🔧 <b>보스팀 설정</b>",
        f"선택: {len(draft)}/6",
    ]
    if selected_names:
        lines.append(" ".join(selected_names))
    lines.append("")
    lines.append("포켓몬을 눌러 추가/제거:")

    # Pokemon buttons
    buttons = []
    for p in page_pokemon:
        inst_id = p.get("pokemon_instance_id") or p.get("id")
        name = p["name_ko"]
        tb = type_badge(p["pokemon_id"], p.get("pokemon_type"))
        shiny_mark = "✨" if p.get("is_shiny") else ""
        selected = "✅ " if inst_id in draft else ""
        rarity_short = {"common": "C", "rare": "R", "epic": "E", "legendary": "L", "ultra_legendary": "UL"}.get(p.get("rarity", ""), "")
        buttons.append([InlineKeyboardButton(
            f"{selected}{shiny_mark}{name} [{rarity_short}]",
            callback_data=f"boss_tsel_{user_id}_{inst_id}",
        )])

    # Pagination
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀", callback_data=f"boss_tpg_{user_id}_{page-1}"))
    nav.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="boss_noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("▶", callback_data=f"boss_tpg_{user_id}_{page+1}"))
    buttons.append(nav)

    # Action buttons
    actions = []
    if len(draft) == 6:
        actions.append(InlineKeyboardButton("💾 저장", callback_data=f"boss_tsave_{user_id}"))
    actions.append(InlineKeyboardButton("🗑 초기화", callback_data=f"boss_tclear_{user_id}"))
    actions.append(InlineKeyboardButton("🔙 돌아가기", callback_data=f"boss_back_{user_id}"))
    buttons.append(actions)

    try:
        await query.edit_message_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="HTML",
        )
    except Exception:
        pass


async def _handle_team_toggle(query, user_id: int, instance_id: int):
    """Toggle a pokemon in/out of boss team draft."""
    draft = _team_drafts.get(user_id, [])

    if instance_id in draft:
        draft.remove(instance_id)
        await query.answer("제거됨")
    elif len(draft) >= 6:
        await query.answer("이미 6마리 선택됨!", show_alert=True)
        return
    else:
        draft.append(instance_id)
        await query.answer("추가됨")

    _team_drafts[user_id] = draft

    # Re-render current page (extract page from message buttons)
    page = 0
    if query.message and query.message.reply_markup:
        for row in query.message.reply_markup.inline_keyboard:
            for btn in row:
                if btn.callback_data and btn.callback_data.startswith(f"boss_tpg_{user_id}_"):
                    # Find current page from nav button text
                    try:
                        page = int(btn.text.split("/")[0]) - 1
                    except (ValueError, IndexError):
                        pass
                    break

    await _handle_team_select(query, user_id, page=page)


async def _handle_team_save(query, user_id: int):
    """Save boss team from draft."""
    draft = _team_drafts.get(user_id, [])
    if len(draft) != 6:
        await query.answer("6마리를 선택해주세요!", show_alert=True)
        return

    await bq.set_boss_team(user_id, draft)
    _team_drafts.pop(user_id, None)
    await query.answer("✅ 보스팀 저장 완료!")

    boss = await get_current_boss()
    if boss:
        await _edit_boss_info(query, user_id, boss)


async def _handle_team_clear(query, user_id: int):
    """Clear boss team (revert to battle team)."""
    await bq.clear_boss_team(user_id)
    _team_drafts.pop(user_id, None)
    await query.answer("🗑 보스팀 초기화 (배틀팀 사용)")

    boss = await get_current_boss()
    if boss:
        await _edit_boss_info(query, user_id, boss)
