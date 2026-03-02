"""Battle system handlers: partner, team, challenge, accept/decline, rankings, BP shop."""

import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import config
from database import queries
from database import battle_queries as bq
from utils.battle_calc import calc_battle_stats, format_stats_line, get_type_multiplier
from utils.helpers import escape_html

logger = logging.getLogger(__name__)

# 마스터볼 일일 구매 추적: {(user_id, "YYYY-MM-DD"): count}
_masterball_daily_purchases: dict[tuple[int, str], int] = {}

PARTNER_PAGE_SIZE = 10
TEAM_PAGE_SIZE = 10
TEAM_MAX = 6


# ============================================================
# Partner Pokemon (/파트너)
# ============================================================

def _build_partner_list(user_id: int, pokemon_list: list, page: int,
                        current_partner_id: int | None = None) -> tuple[str, InlineKeyboardMarkup]:
    """Build partner selection list with inline buttons."""
    total = len(pokemon_list)
    total_pages = max(1, (total + PARTNER_PAGE_SIZE - 1) // PARTNER_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))

    start = page * PARTNER_PAGE_SIZE
    end = min(start + PARTNER_PAGE_SIZE, total)
    page_pokemon = pokemon_list[start:end]

    lines = [f"🤝 파트너 선택  [{page + 1}/{total_pages}]\n"]
    for i, p in enumerate(page_pokemon):
        num = start + i + 1
        mark = " ✅" if p["id"] == current_partner_id else ""
        type_emoji = config.TYPE_EMOJI.get(p.get("pokemon_type", "normal"), "")
        lines.append(f"{num}. {type_emoji}{p['emoji']} {p['name_ko']}{mark}")
    lines.append("\n포켓몬을 눌러 파트너로 지정!")

    # Buttons: 2 per row
    buttons = []
    row = []
    for i, p in enumerate(page_pokemon):
        idx = start + i
        row.append(InlineKeyboardButton(
            f"{idx + 1}. {p['emoji']}{p['name_ko']}",
            callback_data=f"partner_s_{user_id}_{idx}_{page}",
        ))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    # Pagination
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("◀ 이전", callback_data=f"partner_p_{user_id}_{page - 1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("다음 ▶", callback_data=f"partner_p_{user_id}_{page + 1}"))
    if nav_row:
        buttons.append(nav_row)

    return "\n".join(lines), InlineKeyboardMarkup(buttons)


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

    # "파트너" alone → show current partner + 변경 버튼
    if len(parts) == 1:
        partner = await bq.get_partner(user_id)
        if not partner:
            # 파트너 없음 → 바로 선택 리스트
            pokemon_list = await queries.get_user_pokemon_list(user_id)
            if not pokemon_list:
                await update.message.reply_text("보유한 포켓몬이 없습니다.")
                return
            text_msg, markup = _build_partner_list(user_id, pokemon_list, 0)
            await update.message.reply_text(text_msg, reply_markup=markup)
            return

        stats = calc_battle_stats(partner["rarity"], partner["stat_type"], partner["friendship"])
        type_emoji = config.TYPE_EMOJI.get(partner["pokemon_type"], "")
        type_name = config.TYPE_NAME_KO.get(partner["pokemon_type"], "")
        buttons = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔄 변경", callback_data=f"partner_p_{user_id}_0"),
        ]])
        await update.message.reply_text(
            f"🤝 나의 파트너\n\n"
            f"{partner['emoji']} {partner['name_ko']}  {type_emoji}{type_name}\n"
            f"📊 {format_stats_line(stats)}\n\n"
            f"💡 배틀 시 파트너가 팀에 포함되면 ATK +5%!",
            reply_markup=buttons,
        )
        return

    # "파트너 3" (번호) or "파트너 삐삐" (이름) → 직접 지정도 유지
    arg = parts[1] if len(parts) >= 2 else ""
    search_name = " ".join(parts[1:]).strip()

    pokemon_list = await queries.get_user_pokemon_list(user_id)
    if not pokemon_list:
        await update.message.reply_text("보유한 포켓몬이 없습니다.")
        return

    chosen = None

    # 1) 번호로 시도
    try:
        num = int(arg)
        if 1 <= num <= len(pokemon_list):
            chosen = pokemon_list[num - 1]
    except ValueError:
        pass

    # 2) 이름으로 검색 (한글/영문)
    if chosen is None and search_name:
        name_lower = search_name.lower()
        matches = [
            p for p in pokemon_list
            if name_lower in p["name_ko"].lower() or name_lower in p["name_en"].lower()
        ]
        if len(matches) == 1:
            chosen = matches[0]
        elif len(matches) > 1:
            lines = [f"'{search_name}' 검색 결과가 {len(matches)}마리입니다:\n"]
            for p in matches:
                idx = pokemon_list.index(p) + 1
                lines.append(f"  {idx}. {p['emoji']} {p['name_ko']}")
            lines.append("\n번호로 지정: 파트너 [번호]")
            await update.message.reply_text("\n".join(lines))
            return
        else:
            await update.message.reply_text(
                f"'{search_name}' 이름의 포켓몬을 보유하고 있지 않습니다.\n"
                f"내포켓몬 으로 보유 목록을 확인하세요."
            )
            return

    if chosen is None:
        # 인식 불가 → 선택 리스트 보여주기
        partner = await bq.get_partner(user_id)
        partner_id = partner["instance_id"] if partner else None
        text_msg, markup = _build_partner_list(user_id, pokemon_list, 0, partner_id)
        await update.message.reply_text(text_msg, reply_markup=markup)
        return

    await _set_partner_and_reply(update.message, user_id, chosen)


async def _set_partner_and_reply(message, user_id: int, chosen: dict):
    """Set partner and send confirmation."""
    await bq.set_partner(user_id, chosen["id"])

    type_emoji = config.TYPE_EMOJI.get(chosen.get("pokemon_type", "normal"), "")
    await message.reply_text(
        f"🤝 {type_emoji}{chosen['emoji']} {chosen['name_ko']}을(를) 파트너로 지정했습니다!\n"
        f"배틀 시 파트너가 팀에 포함되면 ATK +5% 보너스!"
    )

    # Unlock partner title
    if not await queries.has_title(user_id, "partner_set"):
        await queries.unlock_title(user_id, "partner_set")


async def partner_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle partner selection inline button callbacks."""
    query = update.callback_query
    if not query or not query.data:
        return

    data = query.data
    if not data.startswith("partner_"):
        return

    await query.answer()

    parts = data.split("_")
    # partner_p_{user_id}_{page}  — page navigation
    # partner_s_{user_id}_{idx}_{page}  — select pokemon
    action = parts[1]
    owner_id = int(parts[2])

    if query.from_user.id != owner_id:
        await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
        return

    pokemon_list = await queries.get_user_pokemon_list(owner_id)
    if not pokemon_list:
        try:
            await query.edit_message_text("보유한 포켓몬이 없습니다.")
        except Exception:
            pass
        return

    if action == "p":
        # Page navigation
        page = int(parts[3])
        partner = await bq.get_partner(owner_id)
        partner_id = partner["instance_id"] if partner else None
        text_msg, markup = _build_partner_list(owner_id, pokemon_list, page, partner_id)
        try:
            await query.edit_message_text(text_msg, reply_markup=markup)
        except Exception:
            pass

    elif action == "s":
        # Select partner
        idx = int(parts[3])
        if idx < 0 or idx >= len(pokemon_list):
            await query.answer("잘못된 선택입니다.", show_alert=True)
            return

        chosen = pokemon_list[idx]
        await bq.set_partner(owner_id, chosen["id"])

        # Unlock partner title
        if not await queries.has_title(owner_id, "partner_set"):
            await queries.unlock_title(owner_id, "partner_set")

        type_emoji = config.TYPE_EMOJI.get(chosen.get("pokemon_type", "normal"), "")
        stats = calc_battle_stats(chosen["rarity"], chosen.get("stat_type", "balanced"), chosen["friendship"])
        try:
            await query.edit_message_text(
                f"🤝 파트너 지정 완료!\n\n"
                f"{type_emoji}{chosen['emoji']} {chosen['name_ko']}\n"
                f"📊 {format_stats_line(stats)}\n\n"
                f"💡 배틀 시 파트너가 팀에 포함되면 ATK +5%!"
            )
        except Exception:
            pass


# ============================================================
# Battle Team (/팀, /팀등록, /팀해제)
# ============================================================

def _build_team_select(user_id: int, pokemon_list: list, selected: list[int],
                       page: int) -> tuple[str, InlineKeyboardMarkup]:
    """Build team selection UI with inline buttons.
    selected = list of pokemon_list indices (0-based) in team order.
    """
    total = len(pokemon_list)
    total_pages = max(1, (total + TEAM_PAGE_SIZE - 1) // TEAM_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * TEAM_PAGE_SIZE
    end = min(start + TEAM_PAGE_SIZE, total)
    page_pokemon = pokemon_list[start:end]

    slot_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣"]

    # Header with current selection
    lines = [f"⚔️ 배틀 팀 편집  ({len(selected)}/{TEAM_MAX})"]
    if selected:
        sel_names = []
        for si in selected:
            if 0 <= si < total:
                p = pokemon_list[si]
                sel_names.append(f"{p['emoji']}{p['name_ko']}")
        lines.append("▸ " + " → ".join(sel_names))
    lines.append(f"\n[{page + 1}/{total_pages}]  포켓몬을 눌러 추가/제거\n")

    selected_set = set(selected)
    for i, p in enumerate(page_pokemon):
        idx = start + i
        num = idx + 1
        type_emoji = config.TYPE_EMOJI.get(p.get("pokemon_type", "normal"), "")
        if idx in selected_set:
            slot_num = selected.index(idx)
            lines.append(f"{slot_emojis[slot_num]} {type_emoji}{p['emoji']} {p['name_ko']}")
        else:
            lines.append(f"　 {num}. {type_emoji}{p['emoji']} {p['name_ko']}")

    # Encode selected indices as compact string
    sel_str = ",".join(str(s) for s in selected) if selected else "x"

    # Pokemon buttons (2 per row)
    buttons = []
    row = []
    for i, p in enumerate(page_pokemon):
        idx = start + i
        if idx in selected_set:
            slot_num = selected.index(idx)
            label = f"{slot_emojis[slot_num]} {p['emoji']}{p['name_ko']}"
        else:
            label = f"{p['emoji']}{p['name_ko']}"
        row.append(InlineKeyboardButton(
            label,
            callback_data=f"ts_{user_id}_{idx}_{page}_{sel_str}",
        ))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    # Nav row
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("◀ 이전", callback_data=f"tp_{user_id}_{page - 1}_{sel_str}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("다음 ▶", callback_data=f"tp_{user_id}_{page + 1}_{sel_str}"))
    if nav_row:
        buttons.append(nav_row)

    # Action row
    action_row = []
    if selected:
        action_row.append(InlineKeyboardButton(
            f"✅ 확정 ({len(selected)}마리)",
            callback_data=f"tok_{user_id}_{sel_str}",
        ))
        action_row.append(InlineKeyboardButton(
            "🗑 초기화",
            callback_data=f"tcl_{user_id}_{page}_x",
        ))
    buttons.append(action_row if action_row else [
        InlineKeyboardButton("❌ 취소", callback_data=f"tno_{user_id}")
    ])

    return "\n".join(lines), InlineKeyboardMarkup(buttons)


def _parse_sel(sel_str: str) -> list[int]:
    """Parse selected indices from callback data."""
    if sel_str == "x" or not sel_str:
        return []
    return [int(s) for s in sel_str.split(",") if s.isdigit()]


def _team_to_selected(team: list[dict], pokemon_list: list[dict]) -> list[int]:
    """Convert current battle team to pokemon_list indices for pre-filling selection."""
    id_to_idx = {p["id"]: i for i, p in enumerate(pokemon_list)}
    selected = []
    for t in team:
        inst_id = t.get("pokemon_instance_id") or t.get("id")
        idx = id_to_idx.get(inst_id)
        if idx is not None:
            selected.append(idx)
    return selected


async def team_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 팀 command (DM). Show current battle team or start selection."""
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
        # 팀 없음 → 바로 선택 UI
        pokemon_list = await queries.get_user_pokemon_list(user_id)
        if not pokemon_list:
            await update.message.reply_text("보유한 포켓몬이 없습니다.")
            return
        text_msg, markup = _build_team_select(user_id, pokemon_list, [], 0)
        await update.message.reply_text(text_msg, reply_markup=markup)
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

    buttons = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔄 변경", callback_data=f"tcl_{user_id}_0_keep"),
        InlineKeyboardButton("🗑 해제", callback_data=f"tdel_{user_id}"),
    ]])
    await update.message.reply_text("\n".join(lines), reply_markup=buttons)


async def team_register_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 팀등록 command (DM). Register battle team via text or show selector."""
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

    pokemon_list = await queries.get_user_pokemon_list(user_id)
    if not pokemon_list:
        await update.message.reply_text("보유한 포켓몬이 없습니다.")
        return

    # "팀등록" alone → show interactive selector (pre-fill current team)
    if len(parts) < 2:
        current_team = await bq.get_battle_team(user_id)
        pre_selected = _team_to_selected(current_team, pokemon_list) if current_team else []
        text_msg, markup = _build_team_select(user_id, pokemon_list, pre_selected, 0)
        await update.message.reply_text(text_msg, reply_markup=markup)
        return

    # "팀등록 1 3 5" → text-based registration (kept for power users)
    try:
        nums = [int(x) for x in parts[1:7]]
    except ValueError:
        await update.message.reply_text("숫자만 입력해주세요. 예: 팀등록 3 1 5 2")
        return

    if len(set(nums)) != len(nums):
        await update.message.reply_text("중복된 번호가 있습니다.")
        return

    for n in nums:
        if n < 1 or n > len(pokemon_list):
            await update.message.reply_text(f"번호 {n}이(가) 범위 밖입니다. (1~{len(pokemon_list)})")
            return

    # 전설 포켓몬 1마리 제한
    legendary_count = sum(1 for n in nums if pokemon_list[n - 1].get("rarity") == "legendary")
    if legendary_count > 1:
        await update.message.reply_text("⚠️ 전설 포켓몬은 팀에 1마리만 넣을 수 있습니다!")
        return

    instance_ids = [pokemon_list[n - 1]["id"] for n in nums]
    await bq.set_battle_team(user_id, instance_ids)

    slot_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣"]
    lines = ["⚔️ 배틀 팀 등록 완료!\n"]
    for i, n in enumerate(nums):
        p = pokemon_list[n - 1]
        type_emoji = config.TYPE_EMOJI.get(p.get("pokemon_type", "normal"), "")
        lines.append(f"{slot_emojis[i]} {type_emoji}{p['emoji']} {p['name_ko']}")
    await update.message.reply_text("\n".join(lines))


async def team_clear_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 팀해제 command (DM). Clear battle team."""
    if not update.effective_user:
        return

    user_id = update.effective_user.id
    await bq.clear_battle_team(user_id)
    await update.message.reply_text("⚔️ 배틀 팀이 해제되었습니다.")


async def team_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle team selection inline callbacks."""
    query = update.callback_query
    if not query or not query.data:
        return

    data = query.data
    await query.answer()

    # ts_{uid}_{idx}_{page}_{sel} — toggle pokemon
    # tp_{uid}_{page}_{sel} — page nav
    # tok_{uid}_{sel} — confirm
    # tcl_{uid}_{page}_{sel} — clear/start fresh
    # tdel_{uid} — delete team
    # tno_{uid} — cancel

    parts = data.split("_")
    prefix = parts[0]

    if prefix == "ts":
        # Toggle select: ts_{uid}_{idx}_{page}_{sel}
        owner_id = int(parts[1])
        idx = int(parts[2])
        page = int(parts[3])
        selected = _parse_sel(parts[4]) if len(parts) > 4 else []

        if query.from_user.id != owner_id:
            await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
            return

        if idx in selected:
            selected.remove(idx)
        else:
            if len(selected) >= TEAM_MAX:
                await query.answer(f"최대 {TEAM_MAX}마리까지 선택 가능합니다!", show_alert=True)
                return

            # 전설 포켓몬 1마리 제한
            pokemon_list = await queries.get_user_pokemon_list(owner_id)
            if (pokemon_list and 0 <= idx < len(pokemon_list)
                    and pokemon_list[idx].get("rarity") == "legendary"):
                legend_in_team = sum(
                    1 for s in selected
                    if 0 <= s < len(pokemon_list) and pokemon_list[s].get("rarity") == "legendary"
                )
                if legend_in_team >= 1:
                    await query.answer("⚠️ 전설 포켓몬은 1마리만 넣을 수 있습니다!", show_alert=True)
                    return

            selected.append(idx)

        pokemon_list = await queries.get_user_pokemon_list(owner_id)
        if not pokemon_list:
            return
        text_msg, markup = _build_team_select(owner_id, pokemon_list, selected, page)
        try:
            await query.edit_message_text(text_msg, reply_markup=markup)
        except Exception:
            pass

    elif prefix == "tp":
        # Page nav: tp_{uid}_{page}_{sel}
        owner_id = int(parts[1])
        page = int(parts[2])
        selected = _parse_sel(parts[3]) if len(parts) > 3 else []

        if query.from_user.id != owner_id:
            await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
            return

        pokemon_list = await queries.get_user_pokemon_list(owner_id)
        if not pokemon_list:
            return
        text_msg, markup = _build_team_select(owner_id, pokemon_list, selected, page)
        try:
            await query.edit_message_text(text_msg, reply_markup=markup)
        except Exception:
            pass

    elif prefix == "tok":
        # Confirm: tok_{uid}_{sel}
        owner_id = int(parts[1])
        selected = _parse_sel(parts[2]) if len(parts) > 2 else []

        if query.from_user.id != owner_id:
            await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
            return

        if not selected:
            await query.answer("최소 1마리를 선택하세요!", show_alert=True)
            return

        pokemon_list = await queries.get_user_pokemon_list(owner_id)
        if not pokemon_list:
            return

        # 전설 포켓몬 1마리 제한 최종 체크
        legend_count = sum(
            1 for s in selected
            if 0 <= s < len(pokemon_list) and pokemon_list[s].get("rarity") == "legendary"
        )
        if legend_count > 1:
            await query.answer("⚠️ 전설 포켓몬은 1마리만 넣을 수 있습니다!", show_alert=True)
            return

        instance_ids = [pokemon_list[i]["id"] for i in selected if 0 <= i < len(pokemon_list)]
        if not instance_ids:
            return
        await bq.set_battle_team(owner_id, instance_ids)

        slot_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣"]
        lines = ["⚔️ 배틀 팀 등록 완료!\n"]
        for si, idx in enumerate(selected):
            if 0 <= idx < len(pokemon_list):
                p = pokemon_list[idx]
                type_emoji = config.TYPE_EMOJI.get(p.get("pokemon_type", "normal"), "")
                lines.append(f"{slot_emojis[si]} {type_emoji}{p['emoji']} {p['name_ko']}")
        try:
            await query.edit_message_text("\n".join(lines))
        except Exception:
            pass

    elif prefix == "tcl":
        # Change team: tcl_{uid}_{page}_{sel}
        owner_id = int(parts[1])
        page = int(parts[2]) if len(parts) > 2 else 0

        if query.from_user.id != owner_id:
            await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
            return

        pokemon_list = await queries.get_user_pokemon_list(owner_id)
        if not pokemon_list:
            return

        # sel param: "x" = clear all, otherwise pre-fill with current team
        sel_param = parts[3] if len(parts) > 3 else ""
        if sel_param == "x":
            pre_selected = []
        else:
            current_team = await bq.get_battle_team(owner_id)
            pre_selected = _team_to_selected(current_team, pokemon_list) if current_team else []
        text_msg, markup = _build_team_select(owner_id, pokemon_list, pre_selected, page)
        try:
            await query.edit_message_text(text_msg, reply_markup=markup)
        except Exception:
            pass

    elif prefix == "tdel":
        # Delete team: tdel_{uid}
        owner_id = int(parts[1])
        if query.from_user.id != owner_id:
            await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
            return
        await bq.clear_battle_team(owner_id)
        try:
            await query.edit_message_text("⚔️ 배틀 팀이 해제되었습니다.")
        except Exception:
            pass

    elif prefix == "tno":
        # Cancel: tno_{uid}
        owner_id = int(parts[1])
        if query.from_user.id != owner_id:
            await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
            return
        try:
            await query.edit_message_text("팀 등록이 취소되었습니다.")
        except Exception:
            pass


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

    today = datetime.now().strftime("%Y-%m-%d")
    bought_today = _masterball_daily_purchases.get((user_id, today), 0)
    remaining = config.BP_MASTERBALL_DAILY_LIMIT - bought_today

    lines = [
        "🏪 BP 상점\n",
        f"💰 보유 BP: {bp}\n",
        f"🟣 마스터볼 x1 — {config.BP_MASTERBALL_COST} BP (오늘 {remaining}/{config.BP_MASTERBALL_DAILY_LIMIT}개 구매 가능)",
        f"🔵 하이퍼볼 x1 — Coming Soon",
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
        # 일일 구매 제한 체크
        today = datetime.now().strftime("%Y-%m-%d")
        bought_today = _masterball_daily_purchases.get((user_id, today), 0)
        if bought_today >= config.BP_MASTERBALL_DAILY_LIMIT:
            await update.message.reply_text(
                f"🚫 오늘 마스터볼 구매 한도({config.BP_MASTERBALL_DAILY_LIMIT}개)를 초과했습니다.\n"
                "내일 다시 구매할 수 있어요!"
            )
            return

        cost = config.BP_MASTERBALL_COST
        success = await bq.spend_bp(user_id, cost)
        if not success:
            bp = await bq.get_bp(user_id)
            await update.message.reply_text(
                f"BP가 부족합니다. (보유: {bp} / 필요: {cost})"
            )
            return

        await queries.add_master_ball(user_id, 1)
        _masterball_daily_purchases[(user_id, today)] = bought_today + 1
        remaining = config.BP_MASTERBALL_DAILY_LIMIT - bought_today - 1
        bp = await bq.get_bp(user_id)
        await update.message.reply_text(
            f"🟣 마스터볼 1개 구매 완료!\n"
            f"💰 남은 BP: {bp}\n"
            f"📦 오늘 남은 구매: {remaining}개"
        )
    elif item in ("하이퍼볼", "하볼"):
        await update.message.reply_text("🔵 하이퍼볼은 아직 준비 중입니다! (Coming Soon)")
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
    from datetime import datetime, timedelta, timezone

    # Same opponent cooldown
    last_vs = await bq.get_last_battle_time(challenger_id, defender_id)
    if last_vs:
        last_time = datetime.fromisoformat(last_vs)
        if last_time.tzinfo is None:
            last_time = last_time.replace(tzinfo=timezone.utc)
        cooldown = timedelta(seconds=config.BATTLE_COOLDOWN_SAME)
        if datetime.now(timezone.utc) - last_time < cooldown:
            remaining = cooldown - (datetime.now(timezone.utc) - last_time)
            mins = int(remaining.total_seconds() // 60)
            await update.message.reply_text(
                f"같은 상대와의 배틀은 {config.BATTLE_COOLDOWN_SAME // 60}분 쿨다운입니다. "
                f"({mins}분 남음)"
            )
            return

    # Global cooldown
    last_any = await bq.get_last_battle_time_any(challenger_id)
    if last_any:
        last_time = datetime.fromisoformat(last_any)
        if last_time.tzinfo is None:
            last_time = last_time.replace(tzinfo=timezone.utc)
        cooldown = timedelta(seconds=config.BATTLE_COOLDOWN_GLOBAL)
        if datetime.now(timezone.utc) - last_time < cooldown:
            remaining = cooldown - (datetime.now(timezone.utc) - last_time)
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
    expires = (datetime.now(timezone.utc) + timedelta(seconds=config.BATTLE_CHALLENGE_TIMEOUT))

    challenge_id = await bq.create_challenge(
        challenger_id, defender_id, chat_id, expires
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

        # Add teabag & delete buttons
        winner_id = result["winner_id"]
        loser_id = result["loser_id"]
        battle_buttons = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "💀 티배깅하기",
                    callback_data=f"btbag_{winner_id}_{loser_id}",
                ),
                InlineKeyboardButton(
                    "✖️ 삭제",
                    callback_data=f"bdel_{winner_id}_{loser_id}",
                ),
            ]
        ])

        try:
            await query.edit_message_text(
                result["display_text"],
                parse_mode=None,
                reply_markup=battle_buttons,
            )
        except Exception:
            # If message too long, try sending new message
            try:
                await context.bot.send_message(
                    chat_id=challenge["chat_id"],
                    text=result["display_text"],
                    reply_markup=battle_buttons,
                )
            except Exception:
                pass


# ============================================================
# Battle Result Buttons (Teabag / Delete)
# ============================================================

async def battle_result_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle teabag / delete buttons on battle results."""
    query = update.callback_query
    if not query or not query.data:
        return

    data = query.data
    parts = data.split("_")
    prefix = parts[0]

    if prefix == "btbag":
        # Teabag: btbag_{winner_id}_{loser_id}
        winner_id = int(parts[1])
        loser_id = int(parts[2])

        if query.from_user.id != winner_id:
            await query.answer("승자만 사용할 수 있습니다!", show_alert=True)
            return

        winner_user = await queries.get_user(winner_id)
        loser_user = await queries.get_user(loser_id)
        w_name = winner_user["display_name"] if winner_user else "???"
        l_name = loser_user["display_name"] if loser_user else "???"

        await query.answer()

        # Remove buttons from result message
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass

        # Send teabag as new message in chat
        try:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"🫖 {w_name}이(가) {l_name}을(를) 조롱했다!",
            )
        except Exception:
            pass

    elif prefix == "bdel":
        # Delete: bdel_{winner_id}_{loser_id}
        winner_id = int(parts[1])
        loser_id = int(parts[2])

        # Both winner and loser can delete
        if query.from_user.id not in (winner_id, loser_id):
            await query.answer("배틀 참가자만 삭제할 수 있습니다!", show_alert=True)
            return

        await query.answer()
        try:
            await query.message.delete()
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
    lines = ["⚔️ <b>배틀 랭킹</b>"]
    lines.append("─────────────")

    for i, r in enumerate(rankings):
        rank = medals[i] if i < 3 else f"<b>{i + 1}.</b>"
        name = escape_html(r['display_name'])
        total = r["battle_wins"] + r["battle_losses"]
        rate = round(r["battle_wins"] / total * 100) if total > 0 else 0

        # 승률 바 (10칸 기준)
        filled = round(rate / 10)
        bar = "▓" * filled + "░" * (10 - filled)

        lines.append(
            f"{rank} <b>{name}</b>\n"
            f"    {r['battle_wins']}승 {r['battle_losses']}패 "
            f"<code>{bar}</code> {rate}%  🔥{r['best_streak']}"
        )

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


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
