"""Battle system handlers: partner, team, challenge, accept/decline, rankings, BP shop."""

import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import config
from database import queries
from database import battle_queries as bq
from utils.battle_calc import calc_battle_stats, format_stats_line, get_type_multiplier, EVO_STAGE_MAP
from utils.helpers import escape_html, truncate_name, rarity_badge, type_badge

logger = logging.getLogger(__name__)

# 마스터볼 일일 구매: DB로 영구 추적 (bp_purchase_log 테이블)

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
        tb = type_badge(p["pokemon_id"], p.get("pokemon_type"))
        lines.append(f"{num}. {tb}{p['emoji']} {p['name_ko']}{mark}")
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

        evo_stage = EVO_STAGE_MAP.get(partner["pokemon_id"], 3)
        stats = calc_battle_stats(
            partner["rarity"], partner["stat_type"], partner["friendship"],
            evo_stage=evo_stage,
            iv_hp=partner.get("iv_hp"), iv_atk=partner.get("iv_atk"),
            iv_def=partner.get("iv_def"), iv_spa=partner.get("iv_spa"),
            iv_spdef=partner.get("iv_spdef"), iv_spd=partner.get("iv_spd"),
        )
        tb = type_badge(partner["pokemon_id"], partner["pokemon_type"])
        from models.pokemon_base_stats import POKEMON_BASE_STATS
        pbs = POKEMON_BASE_STATS.get(partner["pokemon_id"])
        if pbs:
            type_name = "/".join(config.TYPE_NAME_KO.get(t, t) for t in pbs[-1])
        else:
            type_name = config.TYPE_NAME_KO.get(partner["pokemon_type"], "")
        buttons = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔄 변경", callback_data=f"partner_p_{user_id}_0"),
        ]])
        await update.message.reply_text(
            f"🤝 나의 파트너\n\n"
            f"{partner['emoji']} {partner['name_ko']}  {tb}{type_name}\n"
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

    tb = type_badge(chosen["pokemon_id"], chosen.get("pokemon_type"))
    await message.reply_text(
        f"🤝 {tb}{chosen['emoji']} {chosen['name_ko']}을(를) 파트너로 지정했습니다!\n"
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
            await query.edit_message_text(text_msg, reply_markup=markup, parse_mode="HTML")
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

        tb = type_badge(chosen["pokemon_id"], chosen.get("pokemon_type"))
        evo_stage = EVO_STAGE_MAP.get(chosen["pokemon_id"], 3)
        stats = calc_battle_stats(
            chosen["rarity"], chosen.get("stat_type", "balanced"), chosen["friendship"],
            evo_stage=evo_stage,
            iv_hp=chosen.get("iv_hp"), iv_atk=chosen.get("iv_atk"),
            iv_def=chosen.get("iv_def"), iv_spa=chosen.get("iv_spa"),
            iv_spdef=chosen.get("iv_spdef"), iv_spd=chosen.get("iv_spd"),
        )
        try:
            await query.edit_message_text(
                f"🤝 파트너 지정 완료!\n\n"
                f"{tb}{chosen['emoji']} {chosen['name_ko']}\n"
                f"📊 {format_stats_line(stats)}\n\n"
                f"💡 배틀 시 파트너가 팀에 포함되면 ATK +5%!"
            )
        except Exception:
            pass


# ============================================================
# Battle Team (/팀, /팀등록, /팀해제)
# ============================================================

def _build_team_select(user_id: int, pokemon_list: list, selected: list[int],
                       page: int, team_num: int = 1) -> tuple[str, InlineKeyboardMarkup]:
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
    lines = [f"⚔️ 배틀 팀 {team_num} 편집  ({len(selected)}/{TEAM_MAX})"]
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
        tb = type_badge(p["pokemon_id"], p.get("pokemon_type"))
        rb = rarity_badge(p.get("rarity", ""))
        if idx in selected_set:
            slot_num = selected.index(idx)
            lines.append(f"☑ {slot_emojis[slot_num]} {rb}{tb}{p['emoji']} {p['name_ko']}")
        else:
            lines.append(f"☐ {num}. {rb}{tb}{p['emoji']} {p['name_ko']}")

    # Encode selected indices as compact string
    sel_str = ",".join(str(s) for s in selected) if selected else "x"

    # Pokemon buttons (2 per row)
    tn = team_num
    buttons = []
    row = []
    for i, p in enumerate(page_pokemon):
        idx = start + i
        if idx in selected_set:
            slot_num = selected.index(idx)
            label = f"☑ {slot_emojis[slot_num]} {p['name_ko']}"
        else:
            label = f"☐ {p['name_ko']}"
        row.append(InlineKeyboardButton(
            label,
            callback_data=f"ts_{user_id}_{idx}_{page}_{sel_str}_{tn}",
        ))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    # Nav row
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("◀ 이전", callback_data=f"tp_{user_id}_{page - 1}_{sel_str}_{tn}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("다음 ▶", callback_data=f"tp_{user_id}_{page + 1}_{sel_str}_{tn}"))
    if nav_row:
        buttons.append(nav_row)

    # Action row
    action_row = []
    if selected:
        action_row.append(InlineKeyboardButton(
            f"✅ 확정 ({len(selected)}마리)",
            callback_data=f"tok_{user_id}_{sel_str}_{tn}",
        ))
        action_row.append(InlineKeyboardButton(
            "🗑 초기화",
            callback_data=f"tcl_{user_id}_{page}_x_{tn}",
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
    """Handle 팀/팀1/팀2 command (DM). Show current battle team or start selection."""
    if not update.effective_user:
        return

    user_id = update.effective_user.id
    await queries.ensure_user(
        user_id,
        update.effective_user.first_name or "트레이너",
        update.effective_user.username,
    )

    text = (update.message.text or "").strip()
    team_num = 2 if text.endswith("2") else 1

    team = await bq.get_battle_team(user_id, team_num)
    active_num = await bq.get_active_team_number(user_id)

    if not team:
        pokemon_list = await queries.get_user_pokemon_list(user_id)
        if not pokemon_list:
            await update.message.reply_text("보유한 포켓몬이 없습니다.")
            return
        text_msg, markup = _build_team_select(user_id, pokemon_list, [], 0, team_num)
        await update.message.reply_text(text_msg, reply_markup=markup, parse_mode="HTML")
        return

    partner = await bq.get_partner(user_id)
    partner_instance = partner["instance_id"] if partner else None

    active_mark = " ✅" if team_num == active_num else ""
    slot_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣"]
    lines = [f"⚔️ 배틀 팀 {team_num}{active_mark}\n"]

    for i, p in enumerate(team):
        evo_stage = EVO_STAGE_MAP.get(p["pokemon_id"], 3)
        stats = calc_battle_stats(
            p["rarity"], p["stat_type"], p["friendship"],
            evo_stage=evo_stage,
            iv_hp=p.get("iv_hp"), iv_atk=p.get("iv_atk"),
            iv_def=p.get("iv_def"), iv_spa=p.get("iv_spa"),
            iv_spdef=p.get("iv_spdef"), iv_spd=p.get("iv_spd"),
        )
        tb = type_badge(p["pokemon_id"], p["pokemon_type"])
        partner_mark = " 🤝" if p["pokemon_instance_id"] == partner_instance else ""
        rb = rarity_badge(p["rarity"])
        lines.append(
            f"{slot_emojis[i]} {rb}{tb}{p['emoji']} {p['name_ko']}{partner_mark}  "
            f"{format_stats_line(stats)}"
        )

    if team_num != active_num:
        lines.append(f"\n💡 '팀선택 {team_num}'으로 이 팀을 배틀에 사용할 수 있습니다.")

    buttons = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔄 변경", callback_data=f"tcl_{user_id}_0_keep_{team_num}"),
        InlineKeyboardButton("🗑 해제", callback_data=f"tdel_{user_id}_{team_num}"),
    ]])
    await update.message.reply_text("\n".join(lines), reply_markup=buttons, parse_mode="HTML")


def _parse_team_number(text: str) -> int:
    """Extract team number from command text. '팀등록2' → 2, '팀등록' or '팀등록1' → 1."""
    text = text.strip()
    if text.endswith("2"):
        return 2
    return 1


async def team_register_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 팀등록/팀등록1/팀등록2 command (DM). Register battle team via text or show selector."""
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
    team_num = _parse_team_number(parts[0]) if parts else 1

    pokemon_list = await queries.get_user_pokemon_list(user_id)
    if not pokemon_list:
        await update.message.reply_text("보유한 포켓몬이 없습니다.")
        return

    # "팀등록1" alone → show interactive selector
    if len(parts) < 2:
        current_team = await bq.get_battle_team(user_id, team_num)
        pre_selected = _team_to_selected(current_team, pokemon_list) if current_team else []
        text_msg, markup = _build_team_select(user_id, pokemon_list, pre_selected, 0, team_num)
        await update.message.reply_text(text_msg, reply_markup=markup, parse_mode="HTML")
        return

    # "팀등록1 1 3 5" → text-based registration
    try:
        nums = [int(x) for x in parts[1:7]]
    except ValueError:
        await update.message.reply_text("숫자만 입력해주세요. 예: 팀등록1 3 1 5 2")
        return

    if len(set(nums)) != len(nums):
        await update.message.reply_text("중복된 번호가 있습니다.")
        return

    for n in nums:
        if n < 1 or n > len(pokemon_list):
            await update.message.reply_text(f"번호 {n}이(가) 범위 밖입니다. (1~{len(pokemon_list)})")
            return

    # 전설 포켓몬 1마리 제한 + DM 안내
    legendary_count = sum(1 for n in nums if pokemon_list[n - 1].get("rarity") == "legendary")
    if legendary_count > 1:
        legend_names = [
            f"{pokemon_list[n-1]['emoji']} {pokemon_list[n-1]['name_ko']}"
            for n in nums if pokemon_list[n-1].get("rarity") == "legendary"
        ]
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                f"⚠️ 전설 포켓몬은 팀에 1마리만 넣을 수 있습니다!\n\n"
                f"선택한 전설: {', '.join(legend_names)}\n"
                f"전설 포켓몬 중 1마리만 남기고 다시 등록해주세요."
            ),
        )
        return

    # 에픽 포켓몬 같은 종 중복 제한
    epic_seen: set[int] = set()
    epic_dups: list[str] = []
    for n in nums:
        p = pokemon_list[n - 1]
        if p.get("rarity") == "epic":
            if p["pokemon_id"] in epic_seen:
                epic_dups.append(f"{p['emoji']} {p['name_ko']}")
            epic_seen.add(p["pokemon_id"])
    if epic_dups:
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                f"⚠️ 에픽 포켓몬은 같은 종을 팀에 중복으로 넣을 수 없습니다!\n\n"
                f"중복: {', '.join(epic_dups)}\n"
                f"같은 종의 에픽 포켓몬은 1마리만 남기고 다시 등록해주세요."
            ),
        )
        return

    instance_ids = [pokemon_list[n - 1]["id"] for n in nums]
    await bq.set_battle_team(user_id, instance_ids, team_num)

    slot_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣"]
    lines = [f"⚔️ 배틀 팀 {team_num} 등록 완료!\n"]
    for i, n in enumerate(nums):
        p = pokemon_list[n - 1]
        tb = type_badge(p["pokemon_id"], p.get("pokemon_type"))
        lines.append(f"{slot_emojis[i]} {tb}{p['emoji']} {p['name_ko']}")
    await update.message.reply_text("\n".join(lines))


async def team_clear_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 팀해제/팀해제1/팀해제2 command (DM). Clear battle team."""
    if not update.effective_user:
        return

    user_id = update.effective_user.id
    text = (update.message.text or "").strip()
    team_num = 2 if text.endswith("2") else 1
    await bq.clear_battle_team(user_id, team_num)
    await update.message.reply_text(f"⚔️ 배틀 팀 {team_num}이(가) 해제되었습니다.")


async def team_select_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '팀선택 1' or '팀선택 2' command (DM). Switch active battle team."""
    if not update.effective_user:
        return

    user_id = update.effective_user.id
    text = (update.message.text or "").strip()
    parts = text.split()

    team_num = 1
    if len(parts) >= 2 and parts[1] in ("1", "2"):
        team_num = int(parts[1])
    elif text.endswith("2"):
        team_num = 2

    team = await bq.get_battle_team(user_id, team_num)
    if not team:
        await update.message.reply_text(f"⚠️ 팀 {team_num}이(가) 비어있습니다. '팀등록{team_num}'으로 먼저 등록하세요.")
        return

    await bq.set_active_team(user_id, team_num)
    await update.message.reply_text(f"✅ 배틀 팀 {team_num}을(를) 활성 팀으로 설정했습니다!")


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

    # Helper: extract team_num from last element of parts (default 1)
    def _tn(parts_list, idx):
        try:
            return int(parts_list[idx])
        except (IndexError, ValueError):
            return 1

    if prefix == "ts":
        # Toggle select: ts_{uid}_{idx}_{page}_{sel}_{tn}
        owner_id = int(parts[1])
        idx = int(parts[2])
        page = int(parts[3])
        selected = _parse_sel(parts[4]) if len(parts) > 4 else []
        tn = _tn(parts, 5)

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
                    try:
                        await context.bot.send_message(
                            chat_id=owner_id,
                            text="⚠️ 전설 포켓몬은 팀에 1마리만 넣을 수 있습니다!\n전설 포켓몬 중 1마리만 남기고 다시 등록해주세요.",
                        )
                    except Exception:
                        pass
                    await query.answer("⚠️ 전설 포켓몬은 1마리만!", show_alert=True)
                    return

            # 에픽 포켓몬 같은 종 중복 제한
            if (pokemon_list and 0 <= idx < len(pokemon_list)
                    and pokemon_list[idx].get("rarity") == "epic"):
                adding_pid = pokemon_list[idx]["pokemon_id"]
                epic_same = any(
                    0 <= s < len(pokemon_list)
                    and pokemon_list[s].get("rarity") == "epic"
                    and pokemon_list[s]["pokemon_id"] == adding_pid
                    for s in selected
                )
                if epic_same:
                    await query.answer("⚠️ 같은 에픽 포켓몬은 1마리만!", show_alert=True)
                    return

            selected.append(idx)

        pokemon_list = await queries.get_user_pokemon_list(owner_id)
        if not pokemon_list:
            return
        text_msg, markup = _build_team_select(owner_id, pokemon_list, selected, page, tn)
        try:
            await query.edit_message_text(text_msg, reply_markup=markup, parse_mode="HTML")
        except Exception:
            pass

    elif prefix == "tp":
        # Page nav: tp_{uid}_{page}_{sel}_{tn}
        owner_id = int(parts[1])
        page = int(parts[2])
        selected = _parse_sel(parts[3]) if len(parts) > 3 else []
        tn = _tn(parts, 4)

        if query.from_user.id != owner_id:
            await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
            return

        pokemon_list = await queries.get_user_pokemon_list(owner_id)
        if not pokemon_list:
            return
        text_msg, markup = _build_team_select(owner_id, pokemon_list, selected, page, tn)
        try:
            await query.edit_message_text(text_msg, reply_markup=markup, parse_mode="HTML")
        except Exception:
            pass

    elif prefix == "tok":
        # Confirm: tok_{uid}_{sel}_{tn}
        owner_id = int(parts[1])
        selected = _parse_sel(parts[2]) if len(parts) > 2 else []
        tn = _tn(parts, 3)

        if query.from_user.id != owner_id:
            await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
            return

        if not selected:
            await query.answer("최소 1마리를 선택하세요!", show_alert=True)
            return

        pokemon_list = await queries.get_user_pokemon_list(owner_id)
        if not pokemon_list:
            return

        # 전설 포켓몬 1마리 제한 최종 체크 + DM 안내
        legend_count = sum(
            1 for s in selected
            if 0 <= s < len(pokemon_list) and pokemon_list[s].get("rarity") == "legendary"
        )
        if legend_count > 1:
            legend_names = [
                f"{pokemon_list[s]['emoji']} {pokemon_list[s]['name_ko']}"
                for s in selected
                if 0 <= s < len(pokemon_list) and pokemon_list[s].get("rarity") == "legendary"
            ]
            try:
                await context.bot.send_message(
                    chat_id=owner_id,
                    text=(
                        f"⚠️ 전설 포켓몬은 팀에 1마리만 넣을 수 있습니다!\n\n"
                        f"선택한 전설: {', '.join(legend_names)}\n"
                        f"전설 포켓몬 중 1마리만 남기고 다시 등록해주세요."
                    ),
                )
            except Exception:
                pass
            await query.answer("⚠️ 전설 포켓몬은 1마리만!", show_alert=True)
            return

        # 에픽 포켓몬 같은 종 중복 제한 최종 체크
        epic_pid_seen: set[int] = set()
        epic_dup_names: list[str] = []
        for s in selected:
            if 0 <= s < len(pokemon_list) and pokemon_list[s].get("rarity") == "epic":
                pid = pokemon_list[s]["pokemon_id"]
                if pid in epic_pid_seen:
                    epic_dup_names.append(f"{pokemon_list[s]['emoji']} {pokemon_list[s]['name_ko']}")
                epic_pid_seen.add(pid)
        if epic_dup_names:
            try:
                await context.bot.send_message(
                    chat_id=owner_id,
                    text=(
                        f"⚠️ 에픽 포켓몬은 같은 종을 팀에 중복으로 넣을 수 없습니다!\n\n"
                        f"중복: {', '.join(epic_dup_names)}\n"
                        f"같은 종의 에픽 포켓몬은 1마리만 남기고 다시 등록해주세요."
                    ),
                )
            except Exception:
                pass
            await query.answer("⚠️ 같은 에픽은 1마리만!", show_alert=True)
            return

        instance_ids = [pokemon_list[i]["id"] for i in selected if 0 <= i < len(pokemon_list)]
        if not instance_ids:
            return
        await bq.set_battle_team(owner_id, instance_ids, tn)

        slot_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣"]
        lines = [f"⚔️ 배틀 팀 {tn} 등록 완료!\n"]
        for si, idx in enumerate(selected):
            if 0 <= idx < len(pokemon_list):
                p = pokemon_list[idx]
                tb = type_badge(p["pokemon_id"], p.get("pokemon_type"))
                lines.append(f"{slot_emojis[si]} {tb}{p['emoji']} {p['name_ko']}")
        try:
            await query.edit_message_text("\n".join(lines))
        except Exception:
            pass

    elif prefix == "tcl":
        # Change team: tcl_{uid}_{page}_{sel}_{tn}
        owner_id = int(parts[1])
        page = int(parts[2]) if len(parts) > 2 else 0
        sel_param = parts[3] if len(parts) > 3 else ""
        tn = _tn(parts, 4)

        if query.from_user.id != owner_id:
            await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
            return

        pokemon_list = await queries.get_user_pokemon_list(owner_id)
        if not pokemon_list:
            return

        # sel param: "x" = clear all, otherwise pre-fill with current team
        if sel_param == "x":
            pre_selected = []
        else:
            current_team = await bq.get_battle_team(owner_id, tn)
            pre_selected = _team_to_selected(current_team, pokemon_list) if current_team else []
        text_msg, markup = _build_team_select(owner_id, pokemon_list, pre_selected, page, tn)
        try:
            await query.edit_message_text(text_msg, reply_markup=markup, parse_mode="HTML")
        except Exception:
            pass

    elif prefix == "tdel":
        # Delete team: tdel_{uid}_{tn}
        owner_id = int(parts[1])
        tn = _tn(parts, 2)
        if query.from_user.id != owner_id:
            await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
            return
        await bq.clear_battle_team(owner_id, tn)
        try:
            await query.edit_message_text(f"⚔️ 배틀 팀 {tn}이(가) 해제되었습니다.")
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


def _masterball_price(bought_today: int) -> int:
    """Progressive master ball pricing: 200 → 300 → 500."""
    prices = [200, 300, 500]
    if bought_today >= len(prices):
        return 0  # sold out
    return prices[bought_today]


async def bp_shop_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle BP상점/상점 command (DM). Show BP shop."""
    if not update.effective_user:
        return

    user_id = update.effective_user.id
    bp = await bq.get_bp(user_id)

    bought_today = await bq.get_bp_purchases_today(user_id, "masterball")
    remaining = config.BP_MASTERBALL_DAILY_LIMIT - bought_today
    next_price = _masterball_price(bought_today)
    price_str = f"{next_price} BP" if next_price else "매진"

    tickets = await queries.get_force_spawn_tickets(user_id)
    hyper_balls = await queries.get_hyper_balls(user_id)

    fst_label = "🎉 무료!" if config.BP_FORCE_SPAWN_TICKET_COST == 0 else f"{config.BP_FORCE_SPAWN_TICKET_COST} BP"
    pb_label = "🎉 무료!" if config.BP_POKEBALL_RESET_COST == 0 else f"{config.BP_POKEBALL_RESET_COST} BP"

    # Arcade tickets
    arcade_tickets = await queries.get_arcade_tickets(user_id)

    lines = [
        "🏪 BP 상점\n",
        f"💰 보유 BP: {bp}\n",
        f"🟣 마스터볼 x1 — {price_str} (오늘 {remaining}/{config.BP_MASTERBALL_DAILY_LIMIT}개 남음)",
        f"⚡ 강스권 x1 — {fst_label} (보유: {tickets}개, 채널 강제스폰 50회 초기화)",
        f"🔴 포켓볼 충전 리셋 — {pb_label}",
        f"🔵 하이퍼볼 x1 — {config.BP_HYPER_BALL_COST} BP (보유: {hyper_balls}개, 포획률 3배)",
        f"🎮 아케이드 티켓 x1 — {config.ARCADE_PASS_COST} BP (보유: {arcade_tickets}개, 채널 1시간 아케이드화)",
    ]

    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"🟣 마스터볼 ({price_str})", callback_data="shop_masterball"),
            InlineKeyboardButton(f"⚡ 강스권", callback_data="shop_forcespawn"),
        ],
        [
            InlineKeyboardButton(f"🔴 포켓볼 리셋", callback_data="shop_pokeball"),
            InlineKeyboardButton(f"🔵 하이퍼볼", callback_data="shop_hyperball"),
        ],
        [
            InlineKeyboardButton(f"🎮 아케이드 티켓", callback_data="shop_arcade"),
        ],
    ])

    await update.message.reply_text("\n".join(lines), reply_markup=buttons)


async def bp_buy_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 구매/BP구매 command (DM). Purchase from BP shop."""
    if not update.effective_user:
        return

    user_id = update.effective_user.id
    text = (update.message.text or "").strip()
    parts = text.split()

    if len(parts) < 2:
        await update.message.reply_text("사용법: 구매 마스터볼 / 구매 강제스폰 / 구매 포켓볼")
        return

    item = parts[1]
    if item in ("마스터볼", "마볼"):
        bought_today = await bq.get_bp_purchases_today(user_id, "masterball")
        if bought_today >= config.BP_MASTERBALL_DAILY_LIMIT:
            await update.message.reply_text(
                f"🚫 오늘 마스터볼 구매 한도({config.BP_MASTERBALL_DAILY_LIMIT}개)를 초과했습니다.\n"
                "내일 다시 구매할 수 있어요!"
            )
            return

        cost = _masterball_price(bought_today)
        success = await bq.spend_bp(user_id, cost)
        if not success:
            bp = await bq.get_bp(user_id)
            await update.message.reply_text(
                f"BP가 부족합니다. (보유: {bp} / 필요: {cost})"
            )
            return

        await queries.add_master_ball(user_id, 1)
        await bq.log_bp_purchase(user_id, "masterball", 1)
        remaining = config.BP_MASTERBALL_DAILY_LIMIT - bought_today - 1
        bp = await bq.get_bp(user_id)
        next_price = _masterball_price(bought_today + 1)
        next_str = f" (다음: {next_price} BP)" if next_price else ""
        await update.message.reply_text(
            f"🟣 마스터볼 1개 구매 완료! ({cost} BP)\n"
            f"💰 남은 BP: {bp}\n"
            f"📦 오늘 남은 구매: {remaining}개{next_str}"
        )

    elif item in ("강제스폰", "강스", "강제스폰권", "강스권"):
        cost = config.BP_FORCE_SPAWN_TICKET_COST
        success = await bq.spend_bp(user_id, cost)
        if not success:
            bp = await bq.get_bp(user_id)
            await update.message.reply_text(
                f"BP가 부족합니다. (보유: {bp} / 필요: {cost})"
            )
            return

        await queries.add_force_spawn_ticket(user_id)
        await bq.log_bp_purchase(user_id, "force_spawn_ticket", 1)
        bp = await bq.get_bp(user_id)
        tickets = await queries.get_force_spawn_tickets(user_id)
        await update.message.reply_text(
            f"⚡ 강스권 1개 구매 완료!\n"
            f"💰 남은 BP: {bp}\n"
            f"📦 보유 강스권: {tickets}개\n\n"
            "채팅방에서 '강스권' 입력으로 해당 채널의 강제스폰 50회를 초기화합니다!"
        )

    elif item in ("포켓볼", "볼"):
        cost = config.BP_POKEBALL_RESET_COST
        success = await bq.spend_bp(user_id, cost)
        if not success:
            bp = await bq.get_bp(user_id)
            await update.message.reply_text(
                f"BP가 부족합니다. (보유: {bp} / 필요: {cost})"
            )
            return

        today = config.get_kst_today()
        await queries.reset_bonus_catches(user_id, today)
        await bq.log_bp_purchase(user_id, "pokeball_reset", 1)
        bp = await bq.get_bp(user_id)
        await update.message.reply_text(
            f"🔴 포켓볼 충전 한도 리셋 완료!\n"
            f"💰 남은 BP: {bp}\n"
            f"🔄 다시 포켓볼 충전 으로 10개씩 충전 가능! (최대 100개)"
        )

    elif item in ("하이퍼볼", "하이퍼", "ㅎ"):
        # Support quantity: 구매 하이퍼볼 5
        qty = 1
        if len(parts) >= 3:
            try:
                qty = max(1, int(parts[2]))
            except ValueError:
                qty = 1

        cost = config.BP_HYPER_BALL_COST * qty
        success = await bq.spend_bp(user_id, cost)
        if not success:
            bp = await bq.get_bp(user_id)
            await update.message.reply_text(
                f"BP가 부족합니다. (보유: {bp} / 필요: {cost})"
            )
            return

        await queries.add_hyper_ball(user_id, qty)
        await bq.log_bp_purchase(user_id, "hyper_ball", qty)
        bp = await bq.get_bp(user_id)
        hyper_balls = await queries.get_hyper_balls(user_id)
        await update.message.reply_text(
            f"🔵 하이퍼볼 {qty}개 구매 완료! ({cost} BP)\n"
            f"💰 남은 BP: {bp}\n"
            f"📦 보유 하이퍼볼: {hyper_balls}개\n\n"
            "채팅방에서 'ㅎ'으로 사용하세요!"
        )

    elif item in ("아케이드", "이용권", "아케이드이용권", "아케이드티켓", "티켓"):
        # Buy arcade ticket (inventory item, use in group with '아케이드 등록')
        cost = config.ARCADE_PASS_COST
        success = await bq.spend_bp(user_id, cost)
        if not success:
            bp = await bq.get_bp(user_id)
            await update.message.reply_text(
                f"BP가 부족합니다. (보유: {bp} / 필요: {cost})"
            )
            return

        await queries.add_arcade_ticket(user_id)
        await bq.log_bp_purchase(user_id, "arcade_ticket", 1)
        bp = await bq.get_bp(user_id)
        tickets = await queries.get_arcade_tickets(user_id)
        await update.message.reply_text(
            f"🎮 아케이드 티켓 1개 구매 완료! ({cost} BP)\n"
            f"💰 남은 BP: {bp}\n"
            f"📦 보유 티켓: {tickets}개\n\n"
            "채팅방에서 '아케이드 등록'으로 사용하세요!\n"
            f"⏱ 사용 시 {config.ARCADE_PASS_DURATION // 60}분간 아케이드 채널화"
        )

    else:
        await update.message.reply_text("알 수 없는 상품입니다. 상점 으로 목록을 확인하세요.")


async def shop_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle shop inline button purchases."""
    query = update.callback_query
    if not query or not query.data:
        return

    user_id = query.from_user.id
    item_key = query.data.replace("shop_", "")

    # Map callback to item name for bp_buy logic
    item_map = {
        "masterball": "마스터볼",
        "forcespawn": "강제스폰",
        "pokeball": "포켓볼",
        "hyperball": "하이퍼볼",
        "arcade": "아케이드",
    }
    item = item_map.get(item_key)
    if not item:
        await query.answer("알 수 없는 상품입니다.", show_alert=True)
        return

    # --- Purchase logic (same as bp_buy_handler) ---
    if item == "마스터볼":
        bought_today = await bq.get_bp_purchases_today(user_id, "masterball")
        if bought_today >= config.BP_MASTERBALL_DAILY_LIMIT:
            await query.answer(f"오늘 마스터볼 구매 한도({config.BP_MASTERBALL_DAILY_LIMIT}개) 초과!", show_alert=True)
            return
        cost = _masterball_price(bought_today)
        success = await bq.spend_bp(user_id, cost)
        if not success:
            bp = await bq.get_bp(user_id)
            await query.answer(f"BP 부족! (보유: {bp} / 필요: {cost})", show_alert=True)
            return
        await queries.add_master_ball(user_id, 1)
        await bq.log_bp_purchase(user_id, "masterball", 1)
        remaining = config.BP_MASTERBALL_DAILY_LIMIT - bought_today - 1
        bp = await bq.get_bp(user_id)
        await query.answer(f"🟣 마스터볼 구매! (-{cost} BP, 남은 BP: {bp})", show_alert=True)

    elif item == "강제스폰":
        cost = config.BP_FORCE_SPAWN_TICKET_COST
        success = await bq.spend_bp(user_id, cost)
        if not success:
            bp = await bq.get_bp(user_id)
            await query.answer(f"BP 부족! (보유: {bp} / 필요: {cost})", show_alert=True)
            return
        await queries.add_force_spawn_ticket(user_id)
        await bq.log_bp_purchase(user_id, "force_spawn_ticket", 1)
        bp = await bq.get_bp(user_id)
        await query.answer(f"⚡ 강스권 구매! 채팅방에서 '강스권' 입력으로 사용 (남은 BP: {bp})", show_alert=True)

    elif item == "포켓볼":
        cost = config.BP_POKEBALL_RESET_COST
        success = await bq.spend_bp(user_id, cost)
        if not success:
            bp = await bq.get_bp(user_id)
            await query.answer(f"BP 부족! (보유: {bp} / 필요: {cost})", show_alert=True)
            return
        today = config.get_kst_today()
        await queries.reset_bonus_catches(user_id, today)
        await bq.log_bp_purchase(user_id, "pokeball_reset", 1)
        bp = await bq.get_bp(user_id)
        await query.answer(f"🔴 충전 한도 리셋! 다시 충전 가능 (남은 BP: {bp})", show_alert=True)

    elif item == "하이퍼볼":
        cost = config.BP_HYPER_BALL_COST
        success = await bq.spend_bp(user_id, cost)
        if not success:
            bp = await bq.get_bp(user_id)
            await query.answer(f"BP 부족! (보유: {bp} / 필요: {cost})", show_alert=True)
            return
        await queries.add_hyper_ball(user_id, 1)
        await bq.log_bp_purchase(user_id, "hyper_ball", 1)
        bp = await bq.get_bp(user_id)
        hyper_balls = await queries.get_hyper_balls(user_id)
        await query.answer(f"🔵 하이퍼볼 구매! (보유: {hyper_balls}개, 남은 BP: {bp})", show_alert=True)

    elif item == "아케이드":
        cost = config.ARCADE_PASS_COST
        success = await bq.spend_bp(user_id, cost)
        if not success:
            bp = await bq.get_bp(user_id)
            await query.answer(f"BP 부족! (보유: {bp} / 필요: {cost})", show_alert=True)
            return
        await queries.add_arcade_ticket(user_id)
        await bq.log_bp_purchase(user_id, "arcade_ticket", 1)
        bp = await bq.get_bp(user_id)
        tickets = await queries.get_arcade_tickets(user_id)
        await query.answer(f"🎮 아케이드 티켓 구매! (보유: {tickets}개, 남은 BP: {bp})", show_alert=True)

    # Refresh shop display after purchase
    try:
        bought_today = await bq.get_bp_purchases_today(user_id, "masterball")
        remaining = config.BP_MASTERBALL_DAILY_LIMIT - bought_today
        next_price = _masterball_price(bought_today)
        price_str = f"{next_price} BP" if next_price else "매진"
        bp = await bq.get_bp(user_id)
        tickets = await queries.get_force_spawn_tickets(user_id)
        hyper_balls = await queries.get_hyper_balls(user_id)
        arcade_tickets = await queries.get_arcade_tickets(user_id)
        fst_label = "🎉 무료!" if config.BP_FORCE_SPAWN_TICKET_COST == 0 else f"{config.BP_FORCE_SPAWN_TICKET_COST} BP"
        pb_label = "🎉 무료!" if config.BP_POKEBALL_RESET_COST == 0 else f"{config.BP_POKEBALL_RESET_COST} BP"

        lines = [
            "🏪 BP 상점\n",
            f"💰 보유 BP: {bp}\n",
            f"🟣 마스터볼 x1 — {price_str} (오늘 {remaining}/{config.BP_MASTERBALL_DAILY_LIMIT}개 남음)",
            f"⚡ 강스권 x1 — {fst_label} (보유: {tickets}개, 채널 강제스폰 50회 초기화)",
            f"🔴 포켓볼 충전 리셋 — {pb_label}",
            f"🔵 하이퍼볼 x1 — {config.BP_HYPER_BALL_COST} BP (보유: {hyper_balls}개, 포획률 3배)",
            f"🎮 아케이드 티켓 x1 — {config.ARCADE_PASS_COST} BP (보유: {arcade_tickets}개, 채널 1시간 아케이드화)",
        ]

        buttons = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(f"🟣 마스터볼 ({price_str})", callback_data="shop_masterball"),
                InlineKeyboardButton(f"⚡ 강스권", callback_data="shop_forcespawn"),
            ],
            [
                InlineKeyboardButton(f"🔴 포켓볼 리셋", callback_data="shop_pokeball"),
                InlineKeyboardButton(f"🔵 하이퍼볼", callback_data="shop_hyperball"),
            ],
            [
                InlineKeyboardButton(f"🎮 아케이드 티켓", callback_data="shop_arcade"),
            ],
        ])

        await query.edit_message_text("\n".join(lines), reply_markup=buttons)
    except Exception:
        pass


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

        # Replace with delete-only button (keep for scroll cleanup)
        try:
            delete_only = InlineKeyboardMarkup([[
                InlineKeyboardButton("✖️ 삭제", callback_data=f"bdel_{winner_id}_{loser_id}")
            ]])
            await query.edit_message_reply_markup(reply_markup=delete_only)
        except Exception:
            pass

        # Send random teabag message (same pool as yacha)
        msg = random.choice(config.YACHA_TEABAG_MESSAGES).format(
            winner=w_name, loser=l_name,
        )
        try:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=msg,
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
    lines = ["⚔️ <b>배틀 랭킹</b>\n"]

    for i, r in enumerate(rankings):
        rank = medals[i] if i < 3 else f"<b>{i + 1}.</b>"
        name = escape_html(truncate_name(r['display_name'], 5))
        total = r["battle_wins"] + r["battle_losses"]
        rate = round(r["battle_wins"] / total * 100) if total > 0 else 0

        streak_text = f" {r['best_streak']}연승!" if r.get('best_streak', 0) >= 2 else ""

        lines.append(
            f"{rank} {name} — {r['battle_wins']}승 {r['battle_losses']}패 ({rate}%){streak_text}"
        )

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


# ============================================================
# Battle Tier List
# ============================================================

# Cache tier list (computed once, cleared on restart)
_tier_cache: str | None = None


async def tier_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '티어' command (DM). Show battle tier list for epic+ pokemon."""
    global _tier_cache

    if _tier_cache:
        await update.message.reply_text(_tier_cache, parse_mode="HTML")
        return

    # Fetch all epic+ pokemon
    from database.connection import get_db
    pool = await get_db()
    rows = await pool.fetch("""
        SELECT id, name_ko, emoji, rarity, pokemon_type, stat_type
        FROM pokemon_master
        WHERE rarity IN ('epic', 'legendary')
        ORDER BY id
    """)

    from models.pokemon_skills import POKEMON_SKILLS

    # Calculate power score for each (friendship MAX=5)
    scored = []
    for r in rows:
        evo_stage = EVO_STAGE_MAP.get(r["id"], 3)
        stats = calc_battle_stats(r["rarity"], r["stat_type"], 5, evo_stage=evo_stage)
        skill = POKEMON_SKILLS.get(r["id"], ("몸통박치기", 1.2))

        # Effective power: best offensive stat, skill, survivability
        best_atk = max(stats["atk"], stats["spa"])
        eff_def = (stats["def"] + stats["spdef"]) / 2
        eff_atk = best_atk * (1 + config.BATTLE_SKILL_RATE * skill[1])
        eff_tank = stats["hp"] * (1 + eff_def * 0.003)
        power = eff_atk * eff_tank / 1000

        tb = type_badge(r["id"], r["pokemon_type"])
        from models.pokemon_base_stats import POKEMON_BASE_STATS as _PBS
        _pbs = _PBS.get(r["id"])
        if _pbs:
            type_ko = "/".join(config.TYPE_NAME_KO.get(t, t) for t in _pbs[-1])
        else:
            type_ko = config.TYPE_NAME_KO.get(r["pokemon_type"], r["pokemon_type"])
        stat_ko = {"offensive": "공격", "defensive": "방어", "balanced": "균형", "speedy": "속도"}.get(r["stat_type"], r["stat_type"])

        scored.append({
            "id": r["id"], "name": r["name_ko"], "emoji": r["emoji"],
            "rarity": r["rarity"], "type_emoji": tb, "type_ko": type_ko,
            "stat_ko": stat_ko, "power": power, "skill_name": skill[0],
            "skill_power": skill[1], "stats": stats,
        })

    scored.sort(key=lambda x: x["power"], reverse=True)

    # Build tier display
    lines = ["⚔️ <b>배틀 티어표</b> (에픽 이상, 친밀도 MAX)"]
    lines.append("━━━━━━━━━━━━━━━━━━━━")

    current_tier = None
    tier_labels = {
        "S+": ("🔴", "S+"),
        "S": ("🟡", "S"),
        "A+": ("🟠", "A+"),
        "A": ("🔵", "A"),
        "B+": ("🟣", "B+"),
        "B": ("⚪", "B"),
    }

    for i, p in enumerate(scored):
        # Assign tier (using best of ATK/SPA)
        best_atk = max(p["stats"]["atk"], p["stats"]["spa"])
        if p["rarity"] == "legendary":
            if best_atk >= 140:
                tier = "S+"
            else:
                tier = "S"
        else:  # epic
            if best_atk >= 110:
                tier = "A+"
            elif best_atk >= 85:
                tier = "A"
            elif best_atk >= 70:
                tier = "B+"
            else:
                tier = "B"

        # Print tier header
        if tier != current_tier:
            dot, label = tier_labels.get(tier, ("⚪", tier))
            lines.append(f"\n{dot} <b>── {label} 티어 ──</b>")
            current_tier = tier

        lines.append(
            f"{p['emoji']}<b>{p['name']}</b>  "
            f"{p['type_emoji']}{p['type_ko']}/{p['stat_ko']}  "
            f"「{p['skill_name']}」{p['skill_power']}x"
        )

    lines.append("\n─────────────────")
    lines.append("💡 전투력 = (ATK or SPA) x 스킬 x 내구")
    lines.append("💡 같은 티어 내 타입상성으로 역전 가능")

    _tier_cache = "\n".join(lines)
    await update.message.reply_text(_tier_cache, parse_mode="HTML")


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


# ============================================================
# Ranked Battle (랭전 - Coming Soon)
# ============================================================

async def ranked_coming_soon_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '랭전' command (group). Show coming soon message."""
    if not update.effective_user or not update.message:
        return
    await update.message.reply_text("🏟️ 랭크전은 준비 중입니다! (Coming Soon)")


# ============================================================
# Yacha (야차 - Betting Battle)
# ============================================================

import random
from datetime import timedelta, timezone


async def yacha_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '야차' command (group). Start a betting battle challenge."""
    if not update.effective_user or not update.message:
        return

    chat_id = update.effective_chat.id
    challenger_id = update.effective_user.id
    challenger_name = update.effective_user.first_name or "트레이너"

    # Must reply to someone
    reply = update.message.reply_to_message
    if not reply or not reply.from_user:
        await update.message.reply_text(
            "🎰 야차를 신청하려면 상대방의 메시지에 답장하며 '야차'를 입력하세요!"
        )
        return

    defender_id = reply.from_user.id
    defender_name = reply.from_user.first_name or "트레이너"

    if challenger_id == defender_id:
        await update.message.reply_text("자기 자신에게 야차를 신청할 수 없습니다.")
        return

    if reply.from_user.is_bot:
        await update.message.reply_text("봇에게는 야차를 신청할 수 없습니다.")
        return

    await queries.ensure_user(challenger_id, challenger_name, update.effective_user.username)
    await queries.ensure_user(defender_id, defender_name, reply.from_user.username)

    # Yacha cooldown (global 10min)
    from datetime import datetime as dt
    last_any = await bq.get_last_yacha_time_any(challenger_id)
    if last_any:
        last_time = dt.fromisoformat(last_any)
        if last_time.tzinfo is None:
            last_time = last_time.replace(tzinfo=timezone.utc)
        cooldown = timedelta(seconds=config.YACHA_COOLDOWN)
        if dt.now(timezone.utc) - last_time < cooldown:
            remaining = cooldown - (dt.now(timezone.utc) - last_time)
            mins = int(remaining.total_seconds() // 60)
            secs = int(remaining.total_seconds() % 60)
            await update.message.reply_text(
                f"야차 쿨다운 중입니다. ({mins}분 {secs}초 남음)"
            )
            return

    # Check challenger has a team
    c_team = await bq.get_battle_team(challenger_id)
    if not c_team:
        await update.message.reply_text(
            "🎰 배틀 팀이 없습니다!\n"
            "DM에서 '팀등록 [번호들]'로 먼저 팀을 등록하세요."
        )
        return

    # Check for existing pending yacha
    existing = await bq.get_pending_challenge(challenger_id, defender_id)
    if existing:
        await update.message.reply_text("이미 대기 중인 신청이 있습니다.")
        return

    # Show bet type selection
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "💰 BP 베팅",
                callback_data=f"yc_bp_{challenger_id}_{defender_id}",
            ),
            InlineKeyboardButton(
                "🔮 마스터볼 베팅",
                callback_data=f"yc_mb_{challenger_id}_{defender_id}",
            ),
        ],
        [
            InlineKeyboardButton(
                "❌ 취소",
                callback_data=f"yc_cancel_{challenger_id}_{defender_id}",
            ),
        ],
    ])

    await update.message.reply_text(
        f"🎰 {challenger_name}님이 {defender_name}님에게 야차를 신청합니다!\n"
        "베팅 종류를 선택하세요:",
        reply_markup=buttons,
    )


async def yacha_type_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle yacha bet type selection (BP / Masterball / Cancel)."""
    query = update.callback_query
    if not query or not query.data:
        return

    data = query.data  # yc_bp_{c}_{d}, yc_mb_{c}_{d}, yc_cancel_{c}_{d}
    parts = data.split("_")
    bet_type = parts[1]  # bp, mb, cancel
    challenger_id = int(parts[2])
    defender_id = int(parts[3])

    # Only challenger can select
    if query.from_user.id != challenger_id:
        await query.answer("도전자만 선택할 수 있습니다!", show_alert=True)
        return

    await query.answer()

    if bet_type == "cancel":
        try:
            await query.edit_message_text("❌ 야차가 취소되었습니다.")
        except Exception:
            pass
        return

    if bet_type == "bp":
        # Show BP amount options
        bp_buttons = []
        for amount in config.YACHA_BP_OPTIONS:
            bp_buttons.append(
                InlineKeyboardButton(
                    f"💰 {amount} BP",
                    callback_data=f"ya_bp_{amount}_{challenger_id}_{defender_id}",
                )
            )
        buttons = InlineKeyboardMarkup([
            bp_buttons,
            [InlineKeyboardButton("❌ 취소", callback_data=f"yc_cancel_{challenger_id}_{defender_id}")],
        ])
        try:
            await query.edit_message_text(
                "💰 BP 베팅 금액을 선택하세요:",
                reply_markup=buttons,
            )
        except Exception:
            pass

    elif bet_type == "mb":
        # Show masterball count options
        mb_buttons = []
        for count in config.YACHA_MASTERBALL_OPTIONS:
            mb_buttons.append(
                InlineKeyboardButton(
                    f"🔮 {count}개",
                    callback_data=f"ya_mb_{count}_{challenger_id}_{defender_id}",
                )
            )
        buttons = InlineKeyboardMarkup([
            mb_buttons,
            [InlineKeyboardButton("❌ 취소", callback_data=f"yc_cancel_{challenger_id}_{defender_id}")],
        ])
        try:
            await query.edit_message_text(
                "🔮 마스터볼 베팅 개수를 선택하세요:",
                reply_markup=buttons,
            )
        except Exception:
            pass


async def yacha_amount_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle yacha amount selection → verify balance → create challenge."""
    query = update.callback_query
    if not query or not query.data:
        return

    data = query.data  # ya_bp_{amt}_{c}_{d} or ya_mb_{cnt}_{c}_{d}
    parts = data.split("_")
    bet_type_code = parts[1]  # bp or mb
    amount = int(parts[2])
    challenger_id = int(parts[3])
    defender_id = int(parts[4])

    # Only challenger can select
    if query.from_user.id != challenger_id:
        await query.answer("도전자만 선택할 수 있습니다!", show_alert=True)
        return

    await query.answer()

    bet_type = "bp" if bet_type_code == "bp" else "masterball"

    # Verify challenger has enough
    if bet_type == "bp":
        balance = await bq.get_bp(challenger_id)
        if balance < amount:
            try:
                await query.edit_message_text(
                    f"❌ BP가 부족합니다! (보유: {balance} BP, 필요: {amount} BP)"
                )
            except Exception:
                pass
            return
        bet_display = f"💰 {amount} BP"
    else:  # masterball
        mb_count = await queries.get_master_balls(challenger_id)
        if mb_count < amount:
            try:
                await query.edit_message_text(
                    f"❌ 마스터볼이 부족합니다! (보유: {mb_count}개, 필요: {amount}개)"
                )
            except Exception:
                pass
            return
        bet_display = f"🔮 마스터볼 {amount}개"

    # Create the challenge
    from datetime import datetime as dt
    expires = dt.now(timezone.utc) + timedelta(seconds=config.YACHA_CHALLENGE_TIMEOUT)

    challenge_id = await bq.create_challenge(
        challenger_id, defender_id, update.effective_chat.id, expires,
        bet_type=bet_type, bet_amount=amount,
    )

    # Get names
    c_user = await queries.get_user(challenger_id)
    d_user = await queries.get_user(defender_id)
    c_name = c_user["display_name"] if c_user else "???"
    d_name = d_user["display_name"] if d_user else "???"

    # Challenge message to defender
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✅ 수락",
                callback_data=f"yacha_accept_{challenge_id}_{defender_id}",
            ),
            InlineKeyboardButton(
                "❌ 거절",
                callback_data=f"yacha_decline_{challenge_id}_{defender_id}",
            ),
        ]
    ])

    try:
        await query.edit_message_text(
            f"🎰 {c_name}님이 {d_name}님에게 야차 대결을 신청합니다!\n"
            f"배팅: {bet_display}\n\n"
            f"{config.YACHA_CHALLENGE_TIMEOUT}초 내에 수락해주세요!",
            reply_markup=buttons,
        )
    except Exception:
        pass


async def yacha_response_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle yacha accept/decline → deduct resources → run battle → payout."""
    query = update.callback_query
    if not query or not query.data:
        return

    data = query.data  # yacha_accept_{id}_{d} or yacha_decline_{id}_{d}
    parts = data.split("_")
    action = parts[1]  # accept or decline
    challenge_id = int(parts[2])
    expected_defender = int(parts[3])

    # Only defender can respond
    if query.from_user.id != expected_defender:
        await query.answer("본인만 응답할 수 있습니다!", show_alert=True)
        return

    challenge = await bq.get_challenge_by_id(challenge_id)
    if not challenge:
        try:
            await query.edit_message_text("야차 신청을 찾을 수 없습니다.")
        except Exception:
            pass
        return

    if challenge["status"] != "pending":
        try:
            await query.edit_message_text("이미 처리된 야차 신청입니다.")
        except Exception:
            pass
        return

    # Check expiry
    from datetime import datetime as dt
    expires = challenge["expires_at"]
    if hasattr(expires, 'tzinfo') and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if dt.now(timezone.utc) > expires:
        await bq.update_challenge_status(challenge_id, "expired")
        try:
            await query.edit_message_text("⏰ 야차 신청이 만료되었습니다.")
        except Exception:
            pass
        return

    await query.answer()

    if action == "decline":
        await bq.update_challenge_status(challenge_id, "declined")
        try:
            await query.edit_message_text("❌ 야차가 거절되었습니다.")
        except Exception:
            pass
        return

    # === ACCEPT ===
    challenger_id = challenge["challenger_id"]
    bet_type = challenge["bet_type"]
    bet_amount = challenge["bet_amount"]

    # Validate teams
    d_team = await bq.get_battle_team(expected_defender)
    if not d_team:
        try:
            await query.edit_message_text(
                "🎰 수비자의 배틀 팀이 없습니다!\n"
                "DM에서 '팀등록'으로 먼저 팀을 등록하세요."
            )
        except Exception:
            pass
        return

    c_team = await bq.get_battle_team(challenger_id)
    if not c_team:
        try:
            await query.edit_message_text("🎰 도전자의 배틀 팀이 없습니다!")
        except Exception:
            pass
        return

    # Deduct resources from BOTH sides
    if bet_type == "bp":
        c_ok = await bq.spend_bp(challenger_id, bet_amount)
        if not c_ok:
            await bq.update_challenge_status(challenge_id, "expired")
            try:
                await query.edit_message_text(
                    f"❌ 도전자의 BP가 부족합니다! 야차가 취소됩니다."
                )
            except Exception:
                pass
            return
        d_ok = await bq.spend_bp(expected_defender, bet_amount)
        if not d_ok:
            # Refund challenger
            await bq.add_bp(challenger_id, bet_amount)
            await bq.update_challenge_status(challenge_id, "expired")
            try:
                await query.edit_message_text(
                    f"❌ 수비자의 BP가 부족합니다! 야차가 취소됩니다."
                )
            except Exception:
                pass
            return
        bet_display = f"💰 {bet_amount} BP"
        win_display = f"💰 +{bet_amount * 2} BP 획득! (베팅 {bet_amount} BP × 2)"
    else:  # masterball
        c_ok = await bq.use_master_balls(challenger_id, bet_amount)
        if not c_ok:
            await bq.update_challenge_status(challenge_id, "expired")
            try:
                await query.edit_message_text(
                    f"❌ 도전자의 마스터볼이 부족합니다! 야차가 취소됩니다."
                )
            except Exception:
                pass
            return
        d_ok = await bq.use_master_balls(expected_defender, bet_amount)
        if not d_ok:
            # Refund challenger
            await queries.add_master_ball(challenger_id, bet_amount)
            await bq.update_challenge_status(challenge_id, "expired")
            try:
                await query.edit_message_text(
                    f"❌ 수비자의 마스터볼이 부족합니다! 야차가 취소됩니다."
                )
            except Exception:
                pass
            return
        bet_display = f"🔮 마스터볼 {bet_amount}개"
        win_display = f"🔮 마스터볼 {bet_amount * 2}개 획득! (베팅 {bet_amount}개 × 2)"

    await bq.update_challenge_status(challenge_id, "accepted")

    # Run the battle (skip_bp=True: yacha handles its own payout)
    from services.battle_service import execute_battle
    result = await execute_battle(
        challenger_id=challenger_id,
        defender_id=expected_defender,
        challenger_team=c_team,
        defender_team=d_team,
        challenge_id=challenge_id,
        chat_id=challenge["chat_id"],
        skip_bp=True,
    )

    # Pay the winner
    winner_id = result["winner_id"]
    if bet_type == "bp":
        await bq.add_bp(winner_id, bet_amount * 2)
    else:
        await queries.add_master_ball(winner_id, bet_amount * 2)

    # Get names for display
    c_user = await queries.get_user(challenger_id)
    d_user = await queries.get_user(expected_defender)
    c_name = c_user["display_name"] if c_user else "???"
    d_name = d_user["display_name"] if d_user else "???"
    winner_name = c_name if result["winner_id"] == challenger_id else d_name

    # Build yacha result message
    # Replace the header from execute_battle with yacha header
    battle_text = result["display_text"]
    # The first line is "⚔️ 배틀 결과!" - replace it
    lines = battle_text.split("\n")
    # Remove the original first line ("⚔️ 배틀 결과!")
    if lines and lines[0].startswith("⚔️"):
        lines = lines[1:]

    yacha_header = [
        f"🎰 {c_name}와(과) {d_name}가 야차룰을 붙었습니다!",
        f"배팅: {bet_display}",
    ]

    # Append yacha winnings after the battle result
    yacha_footer = [
        "",
        win_display,
    ]

    full_text = "\n".join(yacha_header + lines + yacha_footer)

    # Teabag & delete buttons
    loser_id = result["loser_id"]
    battle_buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "💀 티배깅하기",
                callback_data=f"yres_tbag_{winner_id}_{loser_id}",
            ),
            InlineKeyboardButton(
                "✖️ 삭제",
                callback_data=f"yres_del_{winner_id}_{loser_id}",
            ),
        ]
    ])

    try:
        await query.edit_message_text(
            full_text,
            parse_mode=None,
            reply_markup=battle_buttons,
        )
    except Exception:
        try:
            await context.bot.send_message(
                chat_id=challenge["chat_id"],
                text=full_text,
                reply_markup=battle_buttons,
            )
        except Exception:
            pass


async def yacha_result_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle yacha result buttons (teabag / delete)."""
    query = update.callback_query
    if not query or not query.data:
        return

    data = query.data  # yres_tbag_{w}_{l} or yres_del_{w}_{l}
    parts = data.split("_")
    action = parts[1]  # tbag or del
    winner_id = int(parts[2])
    loser_id = int(parts[3])

    if action == "tbag":
        if query.from_user.id != winner_id:
            await query.answer("승자만 사용할 수 있습니다!", show_alert=True)
            return

        winner_user = await queries.get_user(winner_id)
        loser_user = await queries.get_user(loser_id)
        w_name = winner_user["display_name"] if winner_user else "???"
        l_name = loser_user["display_name"] if loser_user else "???"

        await query.answer()

        # Remove teabag button, keep delete only
        try:
            delete_only = InlineKeyboardMarkup([[
                InlineKeyboardButton("✖️ 삭제", callback_data=f"yres_del_{winner_id}_{loser_id}")
            ]])
            await query.edit_message_reply_markup(reply_markup=delete_only)
        except Exception:
            pass

        # Send random yacha teabag message
        msg = random.choice(config.YACHA_TEABAG_MESSAGES).format(
            winner=w_name, loser=l_name,
        )
        try:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=msg,
            )
        except Exception:
            pass

    elif action == "del":
        if query.from_user.id not in (winner_id, loser_id):
            await query.answer("배틀 참가자만 삭제할 수 있습니다!", show_alert=True)
            return

        await query.answer()
        try:
            await query.message.delete()
        except Exception:
            pass
