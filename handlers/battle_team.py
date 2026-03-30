"""Battle team handlers: team edit, register, clear, swap, callbacks."""

import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes

import config

from database import queries
from database import battle_queries as bq
from utils.battle_calc import calc_battle_stats, format_stats_line, calc_power, format_power, EVO_STAGE_MAP, iv_total, get_normalized_base_stats
from utils.helpers import escape_html, truncate_name, rarity_badge, type_badge, icon_emoji, ball_emoji, iv_grade_tag
from utils.i18n import t, get_user_lang, poke_name

logger = logging.getLogger(__name__)

TEAM_PAGE_SIZE = 10
TEAM_MAX = 6


# ============================================================
# Battle Team (/팀, /팀등록, /팀해제)
# ============================================================

def _iv_grade_tag(p: dict) -> str:
    return iv_grade_tag(p, show_total=True)


def _build_team_slots(user_id: int, draft: dict, team_num: int, lang: str = "ko") -> tuple[str, InlineKeyboardMarkup]:
    """Build slot-first team editor main view.
    Shows 6 slots as 3x2 grid buttons + done/cancel.
    Supports swap mode for reordering slots.
    """
    current = draft["current"]
    names = draft["names"]
    rarities = draft.get("rarities", {})
    swap_mode = draft.get("swap_mode", False)
    swap_first = draft.get("swap_first")
    filled = sum(1 for v in current.values() if v is not None)
    slot_plain = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣"]
    empty = t(lang, "team.empty_slot")

    # Calculate total cost
    total_cost = 0
    for inst_id in current.values():
        if inst_id is not None:
            rarity = rarities.get(inst_id, "")
            total_cost += config.RANKED_COST.get(rarity, 0)

    cost_warn = f" {t(lang, 'team.cost_exceeded_warn')}" if total_cost > config.RANKED_COST_LIMIT else ""
    header = f"{icon_emoji('battle')} {t(lang, 'team.team_header', num=team_num, filled=filled, max=TEAM_MAX, cost=total_cost, limit=config.RANKED_COST_LIMIT)}{cost_warn}"
    if swap_mode:
        if swap_first is not None:
            first_name = names.get(current.get(swap_first), empty)
            header += f"\n\n🔀 {slot_plain[swap_first-1]} {t(lang, 'team.swap_selected', name=first_name)}"
        else:
            header += f"\n\n🔀 {t(lang, 'team.swap_first_prompt')}"
    lines = [header + "\n"]

    for s in range(1, 7):
        inst_id = current.get(s)
        if inst_id:
            cost = config.RANKED_COST.get(rarities.get(inst_id, ""), 0)
            mark = " ✓" if swap_mode and swap_first == s else ""
            lines.append(f"{slot_plain[s-1]} {names.get(inst_id, '???')} (💰{cost}){mark}")
        else:
            lines.append(f"{slot_plain[s-1]} {empty}")

    if not swap_mode:
        lines.append(f"\n{t(lang, 'team.slot_place_hint')}")

    # 3x2 grid buttons
    buttons = []
    row = []
    for s in range(1, 7):
        inst_id = current.get(s)
        if inst_id:
            label = f"{slot_plain[s-1]} {names.get(inst_id, '???')}"
        else:
            label = f"{slot_plain[s-1]} {empty}"

        if swap_mode:
            row.append(InlineKeyboardButton(
                label, callback_data=f"tsw_{user_id}_{s}_{team_num}",
            ))
        else:
            row.append(InlineKeyboardButton(
                label, callback_data=f"tslot_view_{user_id}_{s}_{team_num}",
            ))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    # Action row
    if swap_mode:
        buttons.append([
            InlineKeyboardButton(t(lang, "team.btn_swap_cancel"), callback_data=f"tswap_cancel_{user_id}_{team_num}"),
        ])
    else:
        buttons.append([
            InlineKeyboardButton(t(lang, "team.btn_swap_order"), callback_data=f"tswap_{user_id}_{team_num}"),
        ])
        buttons.append([
            InlineKeyboardButton(t(lang, "team.btn_done"), callback_data=f"tdone_{user_id}_{team_num}"),
            InlineKeyboardButton(t(lang, "team.btn_cancel"), callback_data=f"tcancel_{user_id}_{team_num}"),
        ])

    return "\n".join(lines), InlineKeyboardMarkup(buttons)


_FILTER_RARITY_MAP = {
    "all": None, "ul": "ultra_legendary", "leg": "legendary",
    "epc": "epic", "rar": "rare", "com": "common",
}
_FILTER_KEYS = {
    "all": ("team.filter_all", "team.filter_all"),
    "ul": ("team.filter_ul", "team.filter_ul_short"),
    "leg": ("team.filter_leg", "team.filter_leg"),
    "epc": ("team.filter_epc", "team.filter_epc"),
    "rar": ("team.filter_rar", "team.filter_rar"),
    "com": ("team.filter_com", "team.filter_com"),
}


async def _build_slot_pokemon_list(user_id: int, slot: int, draft: dict,
                                   page: int, team_num: int,
                                   lang: str = "ko") -> tuple[str, InlineKeyboardMarkup]:
    """Build pokemon list for placing into a specific slot.
    Shows all pokemon (including those in other slots, marked with slot number).
    """
    current = draft["current"]
    names = draft["names"]
    slot_plain = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣"]
    active_filter = draft.get("filter", "all")

    # Cache pokemon list in draft to avoid repeated DB queries
    pokemon_list = draft.get("pokemon_cache")
    if pokemon_list is None:
        pokemon_list = await queries.get_user_pokemon_list(user_id)
        draft["pokemon_cache"] = pokemon_list
    if not pokemon_list:
        return t(lang, "team.no_pokemon"), InlineKeyboardMarkup([])

    # Apply rarity filter
    filter_rarity = _FILTER_RARITY_MAP.get(active_filter)
    if filter_rarity:
        pokemon_list = [p for p in pokemon_list if p.get("rarity") == filter_rarity]

    # Build reverse map: inst_id → slot
    inst_to_slot = {}
    for s, iid in current.items():
        if iid is not None:
            inst_to_slot[iid] = s

    total = len(pokemon_list)
    total_pages = max(1, (total + TEAM_PAGE_SIZE - 1) // TEAM_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * TEAM_PAGE_SIZE
    end = min(start + TEAM_PAGE_SIZE, total)
    page_items = pokemon_list[start:end]

    # Header
    label_key, _ = _FILTER_KEYS.get(active_filter, ("team.filter_all", "team.filter_all"))
    filter_label = t(lang, label_key)
    inst_id = current.get(slot)
    if inst_id:
        lines = [t(lang, "team.slot_replace", slot=slot_plain[slot-1], name=names.get(inst_id, '???')) + f"  [{page+1}/{total_pages}]"]
    else:
        lines = [t(lang, "team.slot_empty_place", slot=slot_plain[slot-1]) + f"  [{page+1}/{total_pages}]"]
    lines.append(t(lang, "team.filter_label", label=filter_label, count=total) + "\n")

    buttons = []

    # Filter buttons row
    filter_row = []
    for code in _FILTER_KEYS:
        _, short_key = _FILTER_KEYS[code]
        short = t(lang, short_key)
        mark = "✓" if code == active_filter else ""
        filter_row.append(InlineKeyboardButton(
            f"{mark}{short}",
            callback_data=f"tf_{user_id}_{slot}_{code}_{team_num}",
        ))
    buttons.append(filter_row)

    # Remove button if slot is occupied
    if inst_id:
        buttons.append([InlineKeyboardButton(
            t(lang, "team.btn_remove"), callback_data=f"trem_{user_id}_{slot}_{team_num}",
        )])

    # Pokemon list buttons (2 per row)
    row = []
    for p in page_items:
        iv_tag = _iv_grade_tag(p)
        shiny = "✨" if p.get("is_shiny") else ""
        rl = config.RARITY_LABEL.get(p.get("rarity", ""), "")
        rl_tag = f"({rl})" if rl else ""
        cost = config.RANKED_COST.get(p.get("rarity", ""), 0)
        in_slot = inst_to_slot.get(p["id"])
        slot_mark = f"[⚔{in_slot}]" if in_slot else ""
        label = f"{p['name_ko']}{shiny}{rl_tag}{iv_tag} 💰{cost} {slot_mark}"
        # callback: tpick_{uid}_{slot}_{instance_id}_{page}_{tn}
        row.append(InlineKeyboardButton(
            label, callback_data=f"tpick_{user_id}_{slot}_{p['id']}_{page}_{team_num}",
        ))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    # Nav row
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(t(lang, "team.btn_prev"), callback_data=f"tp_{user_id}_{slot}_{page - 1}_{team_num}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton(t(lang, "team.btn_next"), callback_data=f"tp_{user_id}_{slot}_{page + 1}_{team_num}"))
    if nav_row:
        buttons.append(nav_row)

    # Back button
    buttons.append([InlineKeyboardButton(
        t(lang, "team.btn_back"), callback_data=f"tcl_{user_id}_{team_num}",
    )])

    return "\n".join(lines), InlineKeyboardMarkup(buttons)


async def _init_draft(context, user_id: int, team_num: int) -> dict:
    """Initialize or refresh team draft in context.user_data."""
    team = await bq.get_battle_team(user_id, team_num)
    # Build names map from team data + will be enriched later
    names = {}
    rarities = {}
    current = {}
    for t in team:
        current[t["slot"]] = t["pokemon_instance_id"]
        shiny = "✨" if t.get("is_shiny") else ""
        names[t["pokemon_instance_id"]] = f"{t['name_ko']}{shiny}"
        rarities[t["pokemon_instance_id"]] = t["rarity"]

    draft = {
        "original": dict(current),
        "current": current,
        "names": names,
        "rarities": rarities,
        "swap_mode": False,
        "swap_first": None,
    }
    context.user_data[f"team_draft_{team_num}"] = draft
    return draft


async def team_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 팀/팀1/팀2 command (DM). Show current battle team or start selection."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    lang = await get_user_lang(user_id)
    await queries.ensure_user(
        user_id,
        update.effective_user.first_name or t(lang, "common.trainer"),
        update.effective_user.username,
    )

    text = (update.message.text or "").strip()
    team_num = 2 if text.endswith("2") else 1

    team, active_num, partner = await asyncio.gather(
        bq.get_battle_team(user_id, team_num),
        bq.get_active_team_number(user_id),
        bq.get_partner(user_id),
    )

    if not team:
        # No team → go straight to slot editor
        draft = await _init_draft(context, user_id, team_num)
        text_msg, markup = _build_team_slots(user_id, draft, team_num, lang=lang)
        await update.message.reply_text(text_msg, reply_markup=markup, parse_mode="HTML")
        return
    partner_instance = partner["instance_id"] if partner else None

    active_mark = f" {icon_emoji('check')}" if team_num == active_num else ""
    slot_emojis = [icon_emoji(str(i)) for i in range(1, 7)]
    lines = [f"{icon_emoji('battle')} {t(lang, 'team.team_header', num=team_num, filled=len(team), max=TEAM_MAX, cost=0, limit=config.RANKED_COST_LIMIT).split('💰')[0].strip()}{active_mark}\n"]

    total_power = 0
    total_base_power = 0
    total_cost = 0
    for i, p in enumerate(team):
        _t_base = get_normalized_base_stats(p["pokemon_id"])
        evo_stage = 3 if _t_base else EVO_STAGE_MAP.get(p["pokemon_id"], 3)
        stats = calc_battle_stats(
            p["rarity"], p["stat_type"], p["friendship"],
            evo_stage=evo_stage,
            iv_hp=p.get("iv_hp"), iv_atk=p.get("iv_atk"),
            iv_def=p.get("iv_def"), iv_spa=p.get("iv_spa"),
            iv_spdef=p.get("iv_spdef"), iv_spd=p.get("iv_spd"),
            **(_t_base or {}),
        )
        base = calc_battle_stats(
            p["rarity"], p["stat_type"], p["friendship"],
            evo_stage=evo_stage, **(_t_base or {}),
        )
        total_power += calc_power(stats)
        total_base_power += calc_power(base)
        tb = type_badge(p["pokemon_id"], p["pokemon_type"])
        partner_mark = " 🤝" if p["pokemon_instance_id"] == partner_instance else ""
        rb = rarity_badge(p["rarity"])
        rl = config.RARITY_LABEL.get(p["rarity"], "")
        cost = config.RANKED_COST.get(p["rarity"], 0)
        total_cost += cost
        iv_sum = iv_total(p.get("iv_hp"), p.get("iv_atk"), p.get("iv_def"),
                          p.get("iv_spa"), p.get("iv_spdef"), p.get("iv_spd"))
        iv_grade, _ = config.get_iv_grade(iv_sum)
        from utils.helpers import format_personality_tag as _fpt
        _pt = _fpt(p.get("personality")).strip()
        iv_tag = f"[{iv_grade}: {iv_sum}] {_pt+' ' if _pt else ''}" if iv_sum > 0 else ""
        shiny_mark = "✨" if p.get("is_shiny") else ""
        display_name = poke_name(p, lang)
        lines.append(
            f"{slot_emojis[i]} {rb}{tb} {display_name}{shiny_mark} ({rl}){partner_mark}  {icon_emoji('bolt')}{format_power(stats, base)}\n"
            f"    {iv_tag}{format_stats_line(stats, base, lang=lang)}  💰{cost}"
        )
    iv_diff = total_power - total_base_power
    total_tag = f"{total_power}(+{iv_diff})" if iv_diff > 0 else str(total_power)
    lines.append(f"\n{icon_emoji('bolt')} {t(lang, 'team.team_power_label', power=total_tag)}")
    lines.append(f"💰 {t(lang, 'team.team_cost_label', cost=total_cost, limit=config.RANKED_COST_LIMIT)}")

    if total_cost > config.RANKED_COST_LIMIT:
        lines.append(f"\n{t(lang, 'team.cost_over_warning', cost=total_cost, limit=config.RANKED_COST_LIMIT)}")

    if team_num != active_num:
        lines.append(f"\n💡 {t(lang, 'team.team_use_hint', num=team_num)}")

    buttons = InlineKeyboardMarkup([[
        InlineKeyboardButton(t(lang, "team.btn_edit"), callback_data=f"tedit_{user_id}_{team_num}"),
        InlineKeyboardButton(t(lang, "team.btn_delete"), callback_data=f"tdel_{user_id}_{team_num}"),
    ]])
    await update.message.reply_text("\n".join(lines), reply_markup=buttons, parse_mode="HTML")


def _parse_team_number(text: str) -> int:
    """Extract team number from command text. '팀등록2' → 2, '팀등록' or '팀등록1' → 1."""
    text = text.strip()
    if text.endswith("2"):
        return 2
    return 1


async def team_edit_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '팀편집' command (DM). Show team 1/2 edit selector."""
    if not update.effective_user or not update.message:
        return
    user_id = update.effective_user.id
    lang = await get_user_lang(user_id)

    team1, team2, active = await asyncio.gather(
        bq.get_battle_team(user_id, 1),
        bq.get_battle_team(user_id, 2),
        bq.get_active_team_number(user_id),
    )

    t1_label = t(lang, "team.team_label", num=1, count=len(team1)) if team1 else t(lang, "team.team_label_empty", num=1)
    t2_label = t(lang, "team.team_label", num=2, count=len(team2)) if team2 else t(lang, "team.team_label_empty", num=2)
    if active == 1:
        t1_label += " ✅"
    else:
        t2_label += " ✅"

    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"✏️ {t1_label}", callback_data=f"tedit_{user_id}_1"),
            InlineKeyboardButton(f"✏️ {t2_label}", callback_data=f"tedit_{user_id}_2"),
        ],
        [
            InlineKeyboardButton(t(lang, "team.btn_swap_teams"), callback_data=f"tswap_teams_{user_id}"),
        ],
    ])
    await update.message.reply_text(
        f"{icon_emoji('battle')} {t(lang, 'team.edit_select')}",
        reply_markup=buttons,
        parse_mode="HTML",
    )


async def team_register_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 팀등록/팀등록1/팀등록2 command (DM). Register battle team via text or show selector."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    lang = await get_user_lang(user_id)
    await queries.ensure_user(
        user_id,
        update.effective_user.first_name or t(lang, "common.trainer"),
        update.effective_user.username,
    )

    text = (update.message.text or "").strip()
    parts = text.split()
    team_num = _parse_team_number(parts[0]) if parts else 1

    pokemon_list = await queries.get_user_pokemon_list(user_id)
    if not pokemon_list:
        await update.message.reply_text(t(lang, "team.no_pokemon"))
        return

    # "팀등록1" alone → show slot editor
    if len(parts) < 2:
        draft = await _init_draft(context, user_id, team_num)
        text_msg, markup = _build_team_slots(user_id, draft, team_num, lang=lang)
        await update.message.reply_text(text_msg, reply_markup=markup, parse_mode="HTML")
        return

    # "팀등록1 1 3 5" → text-based registration
    try:
        nums = [int(x) for x in parts[1:7]]
    except ValueError:
        await update.message.reply_text(t(lang, "team.numbers_only"))
        return

    if len(nums) != config.RANKED_TEAM_SIZE:
        await update.message.reply_text(f"❌ {t(lang, 'team.team_size_required', required=config.RANKED_TEAM_SIZE, current=len(nums))}")
        return

    if len(set(nums)) != len(nums):
        await update.message.reply_text(t(lang, "team.duplicate_numbers"))
        return

    for n in nums:
        if n < 1 or n > len(pokemon_list):
            await update.message.reply_text(t(lang, "team.number_out_of_range", n=n, max=len(pokemon_list)))
            return

    # Ultra legendary 1 per team limit
    ultra_count = sum(1 for n in nums if pokemon_list[n - 1].get("rarity") == "ultra_legendary")
    if ultra_count > 1:
        ultra_names = [
            poke_name(pokemon_list[n-1], lang)
            for n in nums if pokemon_list[n-1].get("rarity") == "ultra_legendary"
        ]
        await context.bot.send_message(
            chat_id=user_id,
            text=f"⚠️ {t(lang, 'team.ultra_limit_msg', names=', '.join(ultra_names))}",
        )
        return

    # Epic+ same species duplicate limit
    high_seen: set[int] = set()
    high_dups: list[str] = []
    for n in nums:
        p = pokemon_list[n - 1]
        if p.get("rarity") in ("epic", "legendary", "ultra_legendary"):
            if p["pokemon_id"] in high_seen:
                high_dups.append(poke_name(p, lang))
            high_seen.add(p["pokemon_id"])
    if high_dups:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"⚠️ {t(lang, 'team.epic_dup_msg', names=', '.join(high_dups))}",
        )
        return

    # COST validation
    total_cost = sum(config.RANKED_COST.get(pokemon_list[n - 1].get("rarity", ""), 0) for n in nums)
    if total_cost > config.RANKED_COST_LIMIT:
        cost_lines = []
        for n in nums:
            p = pokemon_list[n - 1]
            c = config.RANKED_COST.get(p.get("rarity", ""), 0)
            cost_lines.append(f"  {poke_name(p, lang)} 💰{c}")
        await context.bot.send_message(
            chat_id=user_id,
            text=f"❌ {t(lang, 'team.cost_over_detail', cost=total_cost, limit=config.RANKED_COST_LIMIT, lines=chr(10).join(cost_lines))}",
        )
        return

    instance_ids = [pokemon_list[n - 1]["id"] for n in nums]
    await bq.set_battle_team(user_id, instance_ids, team_num)

    slot_emojis = [icon_emoji(str(i)) for i in range(1, 7)]
    lines = [f"{icon_emoji('battle')} {t(lang, 'team.team_registered', num=team_num)}\n"]
    for i, n in enumerate(nums):
        p = pokemon_list[n - 1]
        tb = type_badge(p["pokemon_id"], p.get("pokemon_type"))
        lines.append(f"{slot_emojis[i]} {tb} {poke_name(p, lang)}")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def team_clear_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 팀해제/팀해제1/팀해제2 command (DM). Clear battle team."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    lang = await get_user_lang(user_id)
    text = (update.message.text or "").strip()
    team_num = 2 if text.endswith("2") else 1
    await bq.clear_battle_team(user_id, team_num)
    await update.message.reply_text(f"{icon_emoji('battle')} {t(lang, 'team.team_cleared', num=team_num)}", parse_mode="HTML")


async def team_select_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '팀선택 1' or '팀선택 2' command (DM). Switch active battle team."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    lang = await get_user_lang(user_id)
    text = (update.message.text or "").strip()
    parts = text.split()

    team_num = 1
    if len(parts) >= 2 and parts[1] in ("1", "2"):
        team_num = int(parts[1])
    elif text.endswith("2"):
        team_num = 2

    team = await bq.get_battle_team(user_id, team_num)
    if not team:
        await update.message.reply_text(f"⚠️ {t(lang, 'team.team_empty_msg', num=team_num)}")
        return

    await bq.set_active_team(user_id, team_num)
    await update.message.reply_text(f"{icon_emoji('check')} {t(lang, 'team.team_activated', num=team_num)}", parse_mode="HTML")


async def team_swap_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '팀스왑' command (DM). Swap team 1 ↔ team 2."""
    if not update.effective_user or not update.message:
        return
    user_id = update.effective_user.id
    lang = await get_user_lang(user_id)
    team1, team2 = await asyncio.gather(
        bq.get_battle_team(user_id, 1),
        bq.get_battle_team(user_id, 2),
    )
    if not team1 and not team2:
        await update.message.reply_text(t(lang, "team.no_teams_to_swap"))
        return
    await bq.swap_teams(user_id)
    active = await bq.get_active_team_number(user_id)
    await update.message.reply_text(
        f"🔀 {t(lang, 'team.team_swapped', active=active)}",
        parse_mode="HTML",
    )


async def team_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle team editor inline callbacks (slot-first draft architecture)."""
    query = update.callback_query
    if not query or not query.data:
        return

    data = query.data
    parts = data.split("_")
    lang = await get_user_lang(query.from_user.id)

    # Helper: ownership check
    def _check_owner(uid):
        return query.from_user.id == uid

    # Helper: get or init draft
    async def _get_draft(uid, tn):
        key = f"team_draft_{tn}"
        draft = context.user_data.get(key)
        if not draft:
            draft = await _init_draft(context, uid, tn)
        return draft

    # tedit_{uid}_{tn} — enter slot editor from team view
    if data.startswith("tedit_"):
        owner_id = int(parts[1])
        tn = int(parts[2])
        if not _check_owner(owner_id):
            await query.answer(t(lang, "error.not_your_button"), show_alert=True)
            return
        await query.answer()
        draft = await _init_draft(context, owner_id, tn)

        text_msg, markup = _build_team_slots(owner_id, draft, tn, lang=lang)
        try:
            await query.edit_message_text(text_msg, reply_markup=markup, parse_mode="HTML")
        except BadRequest as e:
            if "not modified" not in str(e).lower():
                raise
        except Exception:
            logger.exception("tedit edit_message_text failed")

    # tslot_view_{uid}_{slot}_{tn} — view slot → show pokemon list
    elif data.startswith("tslot_view_"):
        # tslot_view_{uid}_{slot}_{tn}
        owner_id = int(parts[2])
        slot = int(parts[3])
        tn = int(parts[4])
        if not _check_owner(owner_id):
            await query.answer(t(lang, "error.not_your_button"), show_alert=True)
            return
        await query.answer()
        draft = await _get_draft(owner_id, tn)
        text_msg, markup = await _build_slot_pokemon_list(owner_id, slot, draft, 0, tn, lang=lang)
        try:
            await query.edit_message_text(text_msg, reply_markup=markup, parse_mode="HTML")
        except BadRequest as e:
            if "not modified" not in str(e).lower():
                raise
        except Exception:
            logger.exception("tslot_view edit_message_text failed")

    # tpick_{uid}_{slot}_{instance_id}_{page}_{tn} — pick pokemon for slot
    elif data.startswith("tpick_"):
        owner_id = int(parts[1])
        slot = int(parts[2])
        inst_id = int(parts[3])
        page = int(parts[4])
        tn = int(parts[5])
        if not _check_owner(owner_id):
            await query.answer(t(lang, "error.not_your_button"), show_alert=True)
            return
        draft = await _get_draft(owner_id, tn)

        # Get pokemon info for validation
        pokemon = await queries.get_user_pokemon_by_id(inst_id)
        if not pokemon or pokemon["user_id"] != owner_id:
            await query.answer()
            return

        # Swap logic: if pokemon is in another slot, swap
        current = draft["current"]
        other_slot = None
        for s, iid in list(current.items()):
            if iid == inst_id and s != slot:
                other_slot = s
                break

        if other_slot is not None:
            # Swap: other_slot gets current slot's pokemon
            current[other_slot] = current.get(slot)
            if current[other_slot] is None:
                del current[other_slot]

        # Validate ultra_legendary limit (draft-based, exclude target slot)
        if pokemon.get("rarity") == "ultra_legendary":
            ul_count = 0
            for s, iid in current.items():
                if s != slot and iid is not None and iid != inst_id:
                    p_info = await queries.get_user_pokemon_by_id(iid)
                    if p_info and p_info.get("rarity") == "ultra_legendary":
                        ul_count += 1
            if ul_count >= 1:
                await query.answer(f"⚠️ {t(lang, 'team.ultra_only_one')}", show_alert=True)
                return

        # Validate same-species duplicate (epic/legendary/ultra_legendary)
        if pokemon.get("rarity") in ("epic", "legendary", "ultra_legendary"):
            for s, iid in current.items():
                if s != slot and iid is not None and iid != inst_id:
                    p_info = await queries.get_user_pokemon_by_id(iid)
                    if p_info and p_info.get("rarity") in ("epic", "legendary", "ultra_legendary") and p_info.get("pokemon_id") == pokemon["pokemon_id"]:
                        await query.answer(f"⚠️ {t(lang, 'team.same_species_one')}", show_alert=True)
                        return

        # Place pokemon
        current[slot] = inst_id
        shiny_tag = "✨" if pokemon.get("is_shiny") else ""
        draft["names"][inst_id] = f"{pokemon['name_ko']}{shiny_tag}"
        draft.setdefault("rarities", {})[inst_id] = pokemon.get("rarity", "")

        await query.answer()
        # Return to slot main view
        text_msg, markup = _build_team_slots(owner_id, draft, tn, lang=lang)
        try:
            await query.edit_message_text(text_msg, reply_markup=markup, parse_mode="HTML")
        except BadRequest as e:
            if "not modified" not in str(e).lower():
                raise
        except Exception:
            logger.exception("tpick edit_message_text failed")

    # trem_{uid}_{slot}_{tn} — remove pokemon from slot
    elif data.startswith("trem_"):
        owner_id = int(parts[1])
        slot = int(parts[2])
        tn = int(parts[3])
        if not _check_owner(owner_id):
            await query.answer(t(lang, "error.not_your_button"), show_alert=True)
            return
        await query.answer()
        draft = await _get_draft(owner_id, tn)
        removed = draft["current"].pop(slot, None)
        name = draft["names"].get(removed, "")

        # Return to slot main view
        text_msg, markup = _build_team_slots(owner_id, draft, tn, lang=lang)
        try:
            await query.edit_message_text(text_msg, reply_markup=markup, parse_mode="HTML")
        except BadRequest as e:
            if "not modified" not in str(e).lower():
                raise
        except Exception:
            logger.exception("trem edit_message_text failed")

    # tp_{uid}_{slot}_{page}_{tn} — pokemon list pagination
    elif data.startswith("tp_"):
        owner_id = int(parts[1])
        slot = int(parts[2])
        page = int(parts[3])
        tn = int(parts[4])
        if not _check_owner(owner_id):
            await query.answer(t(lang, "error.not_your_button"), show_alert=True)
            return
        await query.answer()
        draft = await _get_draft(owner_id, tn)
        text_msg, markup = await _build_slot_pokemon_list(owner_id, slot, draft, page, tn, lang=lang)
        try:
            await query.edit_message_text(text_msg, reply_markup=markup, parse_mode="HTML")
        except BadRequest as e:
            if "not modified" not in str(e).lower():
                raise
        except Exception:
            logger.exception("tp edit_message_text failed")

    # tf_{uid}_{slot}_{filter}_{tn} — rarity filter change
    elif data.startswith("tf_"):
        owner_id = int(parts[1])
        slot = int(parts[2])
        filter_code = parts[3]
        tn = int(parts[4])
        if not _check_owner(owner_id):
            await query.answer(t(lang, "error.not_your_button"), show_alert=True)
            return
        await query.answer()
        draft = await _get_draft(owner_id, tn)
        draft["filter"] = filter_code
        text_msg, markup = await _build_slot_pokemon_list(owner_id, slot, draft, 0, tn, lang=lang)
        try:
            await query.edit_message_text(text_msg, reply_markup=markup, parse_mode="HTML")
        except BadRequest as e:
            if "not modified" not in str(e).lower():
                raise
        except Exception:
            logger.exception("tf edit_message_text failed")

    # tcl_{uid}_{tn} — back to slot main view
    elif data.startswith("tcl_"):
        owner_id = int(parts[1])
        tn = int(parts[2])
        if not _check_owner(owner_id):
            await query.answer(t(lang, "error.not_your_button"), show_alert=True)
            return
        await query.answer()
        draft = await _get_draft(owner_id, tn)
        text_msg, markup = _build_team_slots(owner_id, draft, tn, lang=lang)
        try:
            await query.edit_message_text(text_msg, reply_markup=markup, parse_mode="HTML")
        except BadRequest as e:
            if "not modified" not in str(e).lower():
                raise
        except Exception:
            logger.exception("tcl edit_message_text failed")

    # tswap_{uid}_{tn} — enter swap mode
    elif data.startswith("tswap_") and not data.startswith("tswap_cancel_") and not data.startswith("tswap_teams_"):
        owner_id = int(parts[1])
        tn = int(parts[2])
        if not _check_owner(owner_id):
            await query.answer(t(lang, "error.not_your_button"), show_alert=True)
            return
        await query.answer()
        draft = await _get_draft(owner_id, tn)
        draft["swap_mode"] = True
        draft["swap_first"] = None
        text_msg, markup = _build_team_slots(owner_id, draft, tn, lang=lang)
        try:
            await query.edit_message_text(text_msg, reply_markup=markup, parse_mode="HTML")
        except BadRequest as e:
            if "not modified" not in str(e).lower():
                raise
        except Exception:
            logger.exception("tswap edit_message_text failed")

    # tswap_cancel_{uid}_{tn} — cancel swap mode
    elif data.startswith("tswap_cancel_"):
        owner_id = int(parts[2])
        tn = int(parts[3])
        if not _check_owner(owner_id):
            await query.answer(t(lang, "error.not_your_button"), show_alert=True)
            return
        await query.answer()
        draft = await _get_draft(owner_id, tn)
        draft["swap_mode"] = False
        draft["swap_first"] = None
        text_msg, markup = _build_team_slots(owner_id, draft, tn, lang=lang)
        try:
            await query.edit_message_text(text_msg, reply_markup=markup, parse_mode="HTML")
        except BadRequest as e:
            if "not modified" not in str(e).lower():
                raise
        except Exception:
            logger.exception("tswap_cancel edit_message_text failed")

    # tsw_{uid}_{slot}_{tn} — swap slot selection
    elif data.startswith("tsw_"):
        owner_id = int(parts[1])
        slot = int(parts[2])
        tn = int(parts[3])
        if not _check_owner(owner_id):
            await query.answer(t(lang, "error.not_your_button"), show_alert=True)
            return
        await query.answer()
        draft = await _get_draft(owner_id, tn)
        current = draft["current"]

        if draft.get("swap_first") is None:
            # First selection
            draft["swap_first"] = slot
        else:
            # Second selection — execute swap
            s1 = draft["swap_first"]
            s2 = slot
            if s1 != s2:
                v1, v2 = current.get(s1), current.get(s2)
                # Swap
                if v1 is not None:
                    current[s2] = v1
                elif s2 in current:
                    del current[s2]
                if v2 is not None:
                    current[s1] = v2
                elif s1 in current:
                    del current[s1]
            # Exit swap mode
            draft["swap_mode"] = False
            draft["swap_first"] = None

        text_msg, markup = _build_team_slots(owner_id, draft, tn, lang=lang)
        try:
            await query.edit_message_text(text_msg, reply_markup=markup, parse_mode="HTML")
        except BadRequest as e:
            if "not modified" not in str(e).lower():
                raise
        except Exception:
            logger.exception("tsw edit_message_text failed")

    # tswap_teams_{uid} — swap team 1 ↔ team 2 (from edit menu)
    elif data.startswith("tswap_teams_"):
        owner_id = int(parts[2])
        if not _check_owner(owner_id):
            await query.answer(t(lang, "error.not_your_button"), show_alert=True)
            return
        team1 = await bq.get_battle_team(owner_id, 1)
        team2 = await bq.get_battle_team(owner_id, 2)
        if not team1 and not team2:
            await query.answer(t(lang, "team.no_teams_to_swap"), show_alert=True)
            return
        await query.answer()
        await bq.swap_teams(owner_id)
        active = await bq.get_active_team_number(owner_id)
        try:
            await query.edit_message_text(
                f"🔀 {t(lang, 'team.team_swapped', active=active)}",
                parse_mode="HTML",
            )
        except BadRequest as e:
            if "not modified" not in str(e).lower():
                raise
        except Exception:
            logger.exception("tswap_teams edit_message_text failed")

    # tdone_{uid}_{tn} — save draft to DB
    elif data.startswith("tdone_"):
        owner_id = int(parts[1])
        tn = int(parts[2])
        if not _check_owner(owner_id):
            await query.answer(t(lang, "error.not_your_button"), show_alert=True)
            return

        # Check if editing session is still alive (draft exists in memory)
        key = f"team_draft_{tn}"
        draft = context.user_data.get(key)
        if not draft:
            await query.answer(t(lang, "team.session_expired"), show_alert=True)
            return

        await query.answer()
        current = draft["current"]

        if not current:
            await query.answer(t(lang, "team.team_empty_alert"), show_alert=True)
            return

        # --- Team size required ---
        filled = sum(1 for v in current.values() if v is not None)
        if filled < config.RANKED_TEAM_SIZE:
            try:
                await query.edit_message_text(
                    f"❌ {t(lang, 'team.team_size_short', required=config.RANKED_TEAM_SIZE, current=filled)}",
                    parse_mode="HTML",
                )
            except Exception:
                pass
            context.user_data.pop(f"team_draft_{tn}", None)
            return

        # --- COST 검증 ---
        rarities = draft.get("rarities", {})
        total_cost = 0
        ultra_count = 0
        for inst_id in current.values():
            if inst_id is not None:
                rar = rarities.get(inst_id, "")
                total_cost += config.RANKED_COST.get(rar, 0)
                if rar == "ultra_legendary":
                    ultra_count += 1
        if total_cost > config.RANKED_COST_LIMIT:
            try:
                await query.edit_message_text(
                    f"❌ {t(lang, 'team.cost_over_detail', cost=total_cost, limit=config.RANKED_COST_LIMIT, lines='')}",
                    parse_mode="HTML",
                )
            except Exception:
                pass
            context.user_data.pop(f"team_draft_{tn}", None)
            return
        if ultra_count > config.RANKED_ULTRA_MAX:
            try:
                await query.edit_message_text(
                    f"❌ {t(lang, 'team.ultra_max_msg', max=config.RANKED_ULTRA_MAX)}",
                    parse_mode="HTML",
                )
            except Exception:
                pass
            context.user_data.pop(f"team_draft_{tn}", None)
            return

        # Save to DB: build ordered instance_ids (filter None safety)
        instance_ids = [current[s] for s in sorted(current.keys()) if current[s] is not None]
        await bq.set_battle_team(owner_id, instance_ids, tn)

        # Clean up draft
        context.user_data.pop(f"team_draft_{tn}", None)

        slot_plain = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣"]
        lines = [f"{icon_emoji('battle')} {t(lang, 'team.team_saved', num=tn)}\n"]
        for s in sorted(current.keys()):
            lines.append(f"{slot_plain[s-1]} {draft['names'].get(current[s], '???')}")
        try:
            await query.edit_message_text("\n".join(lines), parse_mode="HTML")
        except BadRequest as e:
            if "not modified" not in str(e).lower():
                raise
        except Exception:
            logger.exception("tdone edit_message_text failed")

    # tcancel_{uid}_{tn} — cancel and restore original
    elif data.startswith("tcancel_"):
        owner_id = int(parts[1])
        tn = int(parts[2])
        if not _check_owner(owner_id):
            await query.answer(t(lang, "error.not_your_button"), show_alert=True)
            return
        await query.answer()
        # Clean up draft — original team is still in DB
        context.user_data.pop(f"team_draft_{tn}", None)
        try:
            await query.edit_message_text(t(lang, "team.edit_cancelled"))
        except BadRequest as e:
            if "not modified" not in str(e).lower():
                raise
        except Exception:
            logger.exception("tcancel edit_message_text failed")

    # tdel_{uid}_{tn} — delete team
    elif data.startswith("tdel_"):
        owner_id = int(parts[1])
        tn = int(parts[2])
        if not _check_owner(owner_id):
            await query.answer(t(lang, "error.not_your_button"), show_alert=True)
            return
        await query.answer()
        await bq.clear_battle_team(owner_id, tn)
        context.user_data.pop(f"team_draft_{tn}", None)
        try:
            await query.edit_message_text(f"{icon_emoji('battle')} {t(lang, 'team.team_cleared', num=tn)}", parse_mode="HTML")
        except Exception:
            pass
