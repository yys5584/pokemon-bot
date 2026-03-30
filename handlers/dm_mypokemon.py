"""DM handlers for My Pokemon (내포켓몬) — list, filter, detail views."""

import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import config

from database import queries
from utils.helpers import hearts_display, rarity_badge, rarity_badge_label, escape_html, type_badge, _type_emoji, shiny_emoji, icon_emoji, ball_emoji, resolve_title_badge, pokemon_iv_total as _iv_sum, iv_grade, format_personality_iv_tag
from utils.card_generator import generate_card, generate_pokedex_card
from utils.parse import parse_number, parse_name_arg
from utils.battle_calc import iv_total
from utils.i18n import t, get_user_lang, poke_name

logger = logging.getLogger(__name__)

MYPOKE_PAGE_SIZE = 10


def _get_filter(context) -> dict:
    """Get current filter state from user_data."""
    filt = context.user_data.setdefault("mypoke_filter", {
        "sort": "default",  # default / iv / rarity
        "fav": False,       # (미사용, 하위호환)
        "type": None,       # None = 전체, "fire" = 특정 타입
        "gen": None,        # None = 전체, 1/2/3 = 세대 필터
        "shiny": False,     # 이로치만 보기
        "gen_open": False,  # 세대 서브필터 열림 상태
    })
    # Ensure keys exist for old sessions
    if "gen" not in filt:
        filt["gen"] = None
    if "shiny" not in filt:
        filt["shiny"] = False
    if "gen_open" not in filt:
        filt["gen_open"] = False
    return filt



def _apply_filters(pokemon_list: list, filt: dict) -> list:
    """Apply filter and sort to pokemon list."""
    filtered = list(pokemon_list)

    # Generation filter
    gen = filt.get("gen")
    if gen == 1:
        filtered = [p for p in filtered if 1 <= p["pokemon_id"] <= 151]
    elif gen == 2:
        filtered = [p for p in filtered if 152 <= p["pokemon_id"] <= 251]
    elif gen == 3:
        filtered = [p for p in filtered if 252 <= p["pokemon_id"] <= 386]
    elif gen == 4:
        filtered = [p for p in filtered if 387 <= p["pokemon_id"] <= 493]

    # Type filter
    if filt.get("type"):
        from models.pokemon_base_stats import POKEMON_BASE_STATS
        target = filt["type"]
        result = []
        for p in filtered:
            pbs = POKEMON_BASE_STATS.get(p["pokemon_id"])
            types = pbs[-1] if pbs else [p.get("pokemon_type", "")]
            if target in types:
                result.append(p)
        filtered = result

    # Shiny filter
    if filt.get("shiny"):
        filtered = [p for p in filtered if p.get("is_shiny")]


    # Sort
    sort_mode = filt.get("sort", "default")
    if sort_mode == "iv":
        filtered.sort(key=lambda p: _iv_sum(p), reverse=True)
    elif sort_mode == "rarity":
        rarity_order = {"ultra_legendary": 0, "legendary": 1, "epic": 2, "rare": 3, "common": 4}
        filtered.sort(key=lambda p: (rarity_order.get(p.get("rarity", "common"), 4), -_iv_sum(p)))

    return filtered


def _build_list_view(user_id: int, pokemon_list: list, page: int,
                     filt: dict = None, lang: str = "ko") -> tuple[str, InlineKeyboardMarkup]:
    """Build a text-based list of pokemon with inline buttons.
    Shows team pokemon first, then groups duplicate species.
    """
    original_total = len(pokemon_list)
    slot_emojis = [icon_emoji(str(i)) for i in range(1, 7)]

    # Apply filters if provided
    if filt is None:
        filt = {"sort": "default", "fav": False, "type": None, "gen": None, "shiny": False}
    has_filter = filt.get("sort") != "default" or filt.get("type") or filt.get("gen") or filt.get("shiny")

    if has_filter:
        filtered = _apply_filters(pokemon_list, filt)
    else:
        filtered = pokemon_list

    total = len(filtered)

    # Identify team pokemon (for header display) — only in default mode
    team_pokemon = [p for p in pokemon_list if p.get("team_slot") is not None] if not has_filter else []

    # Group pokemon by pokemon_id — skip grouping in IV sort mode (show individual ranking)
    from collections import OrderedDict
    all_indices = {id(p): i for i, p in enumerate(pokemon_list)}
    skip_grouping = filt.get("sort") == "iv"

    if skip_grouping:
        display_items = [("single", all_indices[id(p)], p) for p in filtered]
    else:
        groups = OrderedDict()
        for p in filtered:
            pid = p["pokemon_id"]
            if pid not in groups:
                groups[pid] = []
            groups[pid].append(p)

        display_items = []
        for pid, members in groups.items():
            if len(members) == 1:
                p = members[0]
                display_items.append(("single", all_indices[id(p)], p))
            else:
                first = members[0]
                indices = [all_indices[id(m)] for m in members]
                display_items.append(("group", pid, indices, first, len(members)))

    # Paginate
    total_items = len(display_items)
    total_pages = max(1, (total_items + MYPOKE_PAGE_SIZE - 1) // MYPOKE_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * MYPOKE_PAGE_SIZE
    end = min(start + MYPOKE_PAGE_SIZE, total_items)
    page_items = display_items[start:end]

    # Header
    filter_tags = []
    if filt.get("gen"):
        filter_tags.append(f"{filt['gen']}세대")
    if filt.get("sort") == "iv":
        filter_tags.append("IV순")
    elif filt.get("sort") == "rarity":
        filter_tags.append("등급순")
    if filt.get("shiny"):
        filter_tags.append("✨이로치")
    if filt.get("type"):
        type_name = config.TYPE_NAME_KO.get(filt["type"], filt["type"])
        filter_tags.append(type_name)
    filter_str = f"  {'·'.join(filter_tags)}" if filter_tags else ""
    count_str = f"{total}/{original_total}마리" if has_filter else f"{original_total}마리"
    lines = [f"🎒 내 포켓몬 ({count_str}){filter_str}  [{page + 1}/{total_pages}]"]

    # Show team section only on first page, default mode
    if page == 0 and team_pokemon and not has_filter:
        teams = {}
        for p in team_pokemon:
            tn = p.get("team_num") or 1
            if tn not in teams:
                teams[tn] = []
            teams[tn].append(p)
        for tn in sorted(teams.keys()):
            lines.append(f"\n{icon_emoji('battle')} 팀{tn}")
            for p in teams[tn]:
                slot = p.get("team_slot", 1) - 1
                se = slot_emojis[slot] if 0 <= slot < 6 else "▸"
                shiny = shiny_emoji() if p.get("is_shiny") else ""
                rb = rarity_badge(p.get("rarity", ""))
                tb = type_badge(p["pokemon_id"], p.get("pokemon_type"))
                iv_tag = ""
                if p.get("iv_hp") is not None:
                    grade, _ = config.get_iv_grade(_iv_sum(p))
                    iv_tag = format_personality_iv_tag(p.get("personality"), grade)
                lines.append(f"{se} {rb}{tb}{shiny} {poke_name(p, lang)}{iv_tag}")
        lines.append("━━━━━━━")

    lines.append("")

    if total == 0:
        lines.append("(조건에 맞는 포켓몬이 없습니다)")
    else:
        item_num = start + 1
        for item in page_items:
            if item[0] == "single":
                _, idx, p = item
                max_f = config.get_max_friendship(p)
                hearts = hearts_display(p["friendship"], max_f)
                shiny = shiny_emoji() if p.get("is_shiny") else ""
                evo_mark = ""
                if p["evolves_to"] and p["evolution_method"] == "friendship" and p["friendship"] >= config.get_max_friendship(p):
                    evo_mark = " ⭐"
                # IV grade + personality
                iv_tag = ""
                if p.get("iv_hp") is not None:
                    iv_sum = _iv_sum(p)
                    grade, _ = config.get_iv_grade(iv_sum)
                    if filt.get("sort") == "iv":
                        iv_tag = f"{format_personality_iv_tag(p.get('personality'), grade)}{iv_sum}"
                    else:
                        iv_tag = format_personality_iv_tag(p.get("personality"), grade)
                rb = rarity_badge(p.get("rarity", ""))
                tb = type_badge(p["pokemon_id"], p.get("pokemon_type"))
                team_tag = f" 🎯{p['team_num']}" if p.get("team_num") else ""
                lines.append(f"{item_num}. {rb}{tb}{shiny} {poke_name(p, lang)}{iv_tag}  {hearts}{evo_mark}{team_tag}")
            else:  # group
                _, pid, indices, first, count = item
                rb = rarity_badge(first.get("rarity", ""))
                tb = type_badge(first["pokemon_id"], first.get("pokemon_type"))
                lines.append(f"{item_num}. {rb}{tb} {poke_name(first, lang)}  x{count}")
            item_num += 1

    # Build buttons
    select_buttons = []

    # Filter/sort row (above pokemon list for easy access)
    sort_mode = filt.get("sort", "default")
    type_on = filt.get("type")
    filter_row = [
        InlineKeyboardButton(
            f"{'✓' if sort_mode == 'iv' else ''}⚡IV순",
            callback_data=f"mypoke_sort_{user_id}_iv",
        ),
        InlineKeyboardButton(
            f"{'✓' if sort_mode == 'rarity' else ''}💎등급",
            callback_data=f"mypoke_sort_{user_id}_rarity",
        ),
    ]
    select_buttons.append(filter_row)

    # Compact filter row 2: Type + Generation + Shiny
    gen_on = filt.get("gen")
    shiny_on = filt.get("shiny", False)
    gen_label = f"✓{gen_on}세대" if gen_on else "📅세대"

    if type_on:
        type_name = config.TYPE_NAME_KO.get(type_on, type_on)
        type_btn = InlineKeyboardButton(f"✓{type_name}", callback_data=f"mypoke_tmore_{user_id}")
    else:
        type_btn = InlineKeyboardButton("🏷타입", callback_data=f"mypoke_tmore_{user_id}")

    filter_row2 = [
        type_btn,
        InlineKeyboardButton(gen_label, callback_data=f"mypoke_genm_{user_id}"),
        InlineKeyboardButton(
            f"{'✓' if shiny_on else ''}✨이로치",
            callback_data=f"mypoke_shiny_{user_id}",
        ),
    ]
    select_buttons.append(filter_row2)

    # Generation sub-filter row (expanded when gen_open is True)
    if filt.get("gen_open"):
        gen_sub_row = [
            InlineKeyboardButton(
                f"{'✓' if gen_on == 1 else ''}1세대",
                callback_data=f"mypoke_gen_{user_id}_1",
            ),
            InlineKeyboardButton(
                f"{'✓' if gen_on == 2 else ''}2세대",
                callback_data=f"mypoke_gen_{user_id}_2",
            ),
            InlineKeyboardButton(
                f"{'✓' if gen_on == 3 else ''}3세대",
                callback_data=f"mypoke_gen_{user_id}_3",
            ),
            InlineKeyboardButton(
                f"{'✓' if gen_on == 4 else ''}4세대",
                callback_data=f"mypoke_gen_{user_id}_4",
            ),
            InlineKeyboardButton("← 닫기", callback_data=f"mypoke_genc_{user_id}"),
        ]
        select_buttons.append(gen_sub_row)

    # Pokemon selection buttons
    row = []
    for i, item in enumerate(page_items):
        num = start + i + 1
        if item[0] == "single":
            _, idx, p = item
            label = f"{num}. {poke_name(p, lang)}"
            cb = f"mypoke_v_{user_id}_{idx}_{page}"
        else:
            _, pid, indices, first, count = item
            label = f"{num}. {poke_name(first, lang)} x{count}"
            cb = f"mypoke_g_{user_id}_{pid}_{page}"
        row.append(InlineKeyboardButton(label, callback_data=cb))
        if len(row) == 2:
            select_buttons.append(row)
            row = []
    if row:
        select_buttons.append(row)

    # Pagination
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("◀ 이전", callback_data=f"mypoke_l_{user_id}_{page - 1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("다음 ▶", callback_data=f"mypoke_l_{user_id}_{page + 1}"))
    if nav_row:
        select_buttons.append(nav_row)

    # Action row: 팀설정 + 방생 + 파트너
    select_buttons.append([
        InlineKeyboardButton("⚔️ 팀설정", callback_data=f"mypoke_team_{user_id}"),
        InlineKeyboardButton("🔄 방생", callback_data=f"mypoke_rel_{user_id}"),
        InlineKeyboardButton("🤝 파트너", callback_data=f"mypoke_partner_{user_id}"),
    ])

    markup = InlineKeyboardMarkup(select_buttons)
    return "\n".join(lines), markup


def _build_group_view(user_id: int, pokemon_list: list, pokemon_id: int, page: int, lang: str = "ko") -> tuple[str, InlineKeyboardMarkup]:
    """Show individual pokemon within a duplicate group."""
    members = [p for p in pokemon_list if p["pokemon_id"] == pokemon_id]
    if not members:
        return t(lang, "error.pokemon_not_found"), InlineKeyboardMarkup([])

    first = members[0]
    rb = rarity_badge(first.get("rarity", ""))
    tb = type_badge(first["pokemon_id"], first.get("pokemon_type"))
    lines = [f"{rb}{tb} {poke_name(first, lang)} 보유 목록 ({len(members)}마리)\n"]

    buttons = []
    row = []
    for i, p in enumerate(members):
        idx = pokemon_list.index(p)
        num = i + 1
        shiny = f" {shiny_emoji()}이로치" if p.get("is_shiny") else ""
        max_f = config.get_max_friendship(p)
        hearts = hearts_display(p["friendship"], max_f)

        # IV grade + personality
        iv_tag = ""
        iv_hp = p.get("iv_hp")
        if iv_hp is not None:
            total = iv_total(iv_hp, p.get("iv_atk"), p.get("iv_def"),
                             p.get("iv_spa"), p.get("iv_spdef"), p.get("iv_spd"))
            grade, _ = config.get_iv_grade(total)
            iv_tag = format_personality_iv_tag(p.get("personality"), grade)

        team_mark = f" ⚔{p.get('team_num') or 1}" if p.get("team_slot") is not None else ""
        lines.append(f"#{num}  {poke_name(first, lang)}{shiny}  {hearts}{iv_tag}{team_mark}")

        label = f"#{num}{shiny[:1]}{iv_tag}"
        row.append(InlineKeyboardButton(label, callback_data=f"mypoke_v_{user_id}_{idx}_{page}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append([InlineKeyboardButton("📋 목록으로", callback_data=f"mypoke_l_{user_id}_{page}")])
    return "\n".join(lines), InlineKeyboardMarkup(buttons)


def _build_detail_view(user_id: int, pokemon_list: list, idx: int, page: int, lang: str = "ko") -> tuple[str, InlineKeyboardMarkup]:
    """Build detail text for a single pokemon with action buttons."""
    p = pokemon_list[idx]
    total = len(pokemon_list)
    num = idx + 1

    max_f = config.get_max_friendship(p)
    hearts = hearts_display(p["friendship"], max_f)
    shiny_mark = shiny_emoji() if p.get("is_shiny") else ""

    evo_text = ""
    if p["evolves_to"] and p["evolution_method"] == "friendship" and p["friendship"] >= config.get_max_friendship(p):
        evo_text = "\n⭐ 진화 가능! → '진화 " + str(num) + "' 입력"
    elif p["evolves_to"] and p["evolution_method"] == "trade":
        evo_text = "\n🔄 교환으로 진화 가능"

    rarity_text = rarity_badge_label(p["rarity"])
    shiny_text = f"  {shiny_emoji()}이로치" if p.get("is_shiny") else ""

    # IV information
    from utils.battle_calc import calc_battle_stats, format_stats_line, format_power, iv_total, EVO_STAGE_MAP, get_normalized_base_stats
    iv_hp = p.get("iv_hp")
    iv_atk = p.get("iv_atk")
    iv_def = p.get("iv_def")
    iv_spa = p.get("iv_spa")
    iv_spdef = p.get("iv_spdef")
    iv_spd = p.get("iv_spd")
    has_iv = iv_hp is not None

    iv_line = ""
    stats_line = ""
    if has_iv:
        total_iv = iv_total(iv_hp, iv_atk, iv_def, iv_spa, iv_spdef, iv_spd)
        grade, _stars = config.get_iv_grade(total_iv)
        from utils.helpers import format_personality_tag as _fpt
        _pers_tag = _fpt(p.get("personality")).strip()
        _pers_label = f" {_pers_tag}" if _pers_tag else ""
        iv_line = f"\nIV: {iv_hp}/{iv_atk}/{iv_def}/{iv_spa}/{iv_spdef}/{iv_spd} ({total_iv}/186) [{grade}]{_pers_label}"

        # Calculate battle stats with IVs (배틀 엔진과 동일하게 종족값 반영)
        pid = p["pokemon_id"]
        _base_stats = get_normalized_base_stats(pid)
        evo_stage = 3 if _base_stats else EVO_STAGE_MAP.get(pid, 3)
        stats = calc_battle_stats(
            p["rarity"], p.get("stat_type", "balanced"), p["friendship"],
            evo_stage=evo_stage,
            iv_hp=iv_hp, iv_atk=iv_atk, iv_def=iv_def,
            iv_spa=iv_spa, iv_spdef=iv_spdef, iv_spd=iv_spd,
            **(_base_stats or {}),
            personality_str=p.get("personality"),
        )
        base = calc_battle_stats(
            p["rarity"], p.get("stat_type", "balanced"), p["friendship"],
            evo_stage=evo_stage,
            **(_base_stats or {}),
        )
        stats_line = (
            f"\n{icon_emoji('bolt')} 전투력: {format_power(stats, base)}"
            f"\n{format_stats_line(stats, base)}"
        )

    tb = type_badge(p["pokemon_id"], p.get("pokemon_type"))
    # Type name display
    from models.pokemon_base_stats import POKEMON_BASE_STATS
    pbs = POKEMON_BASE_STATS.get(p["pokemon_id"])
    if pbs:
        types = pbs[-1]
        type_names = "/".join(config.TYPE_NAME_KO.get(t, t) for t in types)
    else:
        type_names = config.TYPE_NAME_KO.get(p.get("pokemon_type", ""), "")
    type_display = f"  {tb}{type_names}" if type_names else ""

    lines = [
        f"내 포켓몬 상세 ({num}/{total})\n",
        f"{shiny_mark}{tb} {poke_name(p, lang)}{shiny_text}",
        f"등급: {rarity_text}{type_display}",
        f"친밀도: {hearts} ({p['friendship']}/{max_f}){evo_text}{iv_line}{stats_line}",
    ]

    # Team info
    team_info = ""
    if p.get("team_slot") is not None:
        team_info = f"\n{icon_emoji('battle')} 팀{p.get('team_num') or 1} — {p['team_slot']}번 슬롯"
    lines.append(team_info)

    # Action buttons
    buttons = []

    # Row 1: care actions (most used)
    care_row = [
        InlineKeyboardButton("🍖 밥", callback_data=f"mypoke_feed_{user_id}_{idx}_{page}"),
        InlineKeyboardButton("🎮 놀기", callback_data=f"mypoke_play_{user_id}_{idx}_{page}"),
    ]
    can_evo_friendship = p["evolves_to"] and p["evolution_method"] == "friendship" and p["friendship"] >= config.get_max_friendship(p)
    can_evo_trade = p["evolves_to"] and p["evolution_method"] == "trade"
    if can_evo_friendship:
        care_row.append(InlineKeyboardButton("⭐ 진화", callback_data=f"mypoke_evo_{user_id}_{idx}_{page}"))
    buttons.append(care_row)

    # Row 2: info + team + release
    buttons.append([
        InlineKeyboardButton("📋 감정", callback_data=f"mypoke_appr_{user_id}_{idx}_{page}"),
        InlineKeyboardButton("🔄 방생", callback_data=f"mypoke_relone_{user_id}_{idx}_{page}"),
        InlineKeyboardButton("⚔1 팀1", callback_data=f"mypoke_t1_{user_id}_{p['id']}_{page}"),
        InlineKeyboardButton("⚔2 팀2", callback_data=f"mypoke_t2_{user_id}_{p['id']}_{page}"),
    ])

    # Row 4: navigation
    detail_nav = []
    if idx > 0:
        detail_nav.append(InlineKeyboardButton("◀ 이전", callback_data=f"mypoke_v_{user_id}_{idx - 1}_{page}"))
    detail_nav.append(InlineKeyboardButton("📋 목록", callback_data=f"mypoke_l_{user_id}_{page}"))
    if idx < total - 1:
        detail_nav.append(InlineKeyboardButton("다음 ▶", callback_data=f"mypoke_v_{user_id}_{idx + 1}_{page}"))
    buttons.append(detail_nav)

    markup = InlineKeyboardMarkup(buttons)
    return "\n".join(lines), markup


def _format_appraisal(p: dict, lang: str = "ko") -> str:
    """Format IV appraisal text for a pokemon."""
    shiny = shiny_emoji() if p.get("is_shiny") else ""
    rb = rarity_badge(p.get("rarity", "common"))
    ivs = {
        "HP": p.get("iv_hp"), "ATK": p.get("iv_atk"), "DEF": p.get("iv_def"),
        "SPA": p.get("iv_spa"), "SPDEF": p.get("iv_spdef"), "SPD": p.get("iv_spd"),
    }
    total = iv_total(ivs["HP"], ivs["ATK"], ivs["DEF"], ivs["SPA"], ivs["SPDEF"], ivs["SPD"])
    grade, _ = config.get_iv_grade(total)
    pct = round(total / 186 * 100, 1)

    stat_labels = {"HP": "HP   ", "ATK": "공격 ", "DEF": "방어 ", "SPA": "특공 ", "SPDEF": "특방 ", "SPD": "스피드"}
    lines = [f"{icon_emoji('bookmark')} {shiny}{rb} {poke_name(p, lang)} 감정 결과\n"]
    for key in ("HP", "ATK", "DEF", "SPA", "SPDEF", "SPD"):
        v = ivs[key] if ivs[key] is not None else 15
        filled = round(v / 31 * 6)
        bar = "█" * filled + "░" * (6 - filled)
        mark = " ★" if v >= 28 else (" ✗" if v <= 5 else "")
        lines.append(f"{stat_labels[key]} {bar} {v}/31{mark}")
    lines.append(f"\n총합: {total}/186 ({pct}%)")
    lines.append(f"등급: {grade}")
    flavor = {"S": "최상급 개체!", "A": "매우 뛰어남", "B": "괜찮은 개체", "C": "평범", "D": "개체값 낮음"}
    lines.append(flavor.get(grade, ""))
    return "\n".join(lines)


async def my_pokemon_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /내포켓몬 command (DM only) — text list view."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    lang = await get_user_lang(user_id)
    await queries.ensure_user(
        user_id,
        update.effective_user.first_name or t(lang, "common.trainer"),
        update.effective_user.username,
    )

    pokemon_list = await queries.get_user_pokemon_list(user_id)
    # Sync cache so callback handler uses the same list/order
    context.user_data["mypoke_cache"] = pokemon_list
    context.user_data["mypoke_cache_uid"] = user_id

    if not pokemon_list:
        await update.message.reply_text(t(lang, "my_pokemon.no_pokemon"))
        return

    # Check if a specific index was given: "내포켓몬 3"
    from utils.parse import parse_number
    text = (update.message.text or "").strip()
    num = parse_number(text)

    if num is not None:
        # Direct detail view for a specific pokemon
        idx = max(0, min(num - 1, len(pokemon_list) - 1))
        page = idx // MYPOKE_PAGE_SIZE
        detail_text, detail_markup = _build_detail_view(user_id, pokemon_list, idx, page, lang=lang)
        await update.message.reply_text(detail_text, reply_markup=detail_markup, parse_mode="HTML")
        return

    # Check if a name search was given: "내포켓몬 리자몽"
    import re
    name_match = re.sub(r"(?i)^(📦\s*)?(내포켓몬|mypokemon|my\s*pokemon|我的宝可梦|我的寶可夢)\s*", "", text).strip()
    if name_match:
        matches = [
            (i, p) for i, p in enumerate(pokemon_list)
            if name_match in p["name_ko"] or name_match.lower() in (p.get("name_en") or "").lower()
        ]
        if not matches:
            await update.message.reply_text(f"'{name_match}' 이름의 포켓몬을 보유하고 있지 않습니다.")
            return
        if len(matches) == 1:
            # Single match → detail view
            idx = matches[0][0]
            page = idx // MYPOKE_PAGE_SIZE
            detail_text, detail_markup = _build_detail_view(user_id, pokemon_list, idx, page, lang=lang)
            await update.message.reply_text(detail_text, reply_markup=detail_markup, parse_mode="HTML")
        else:
            # Multiple matches → show list with select buttons
            lines = [f"🔍 '{name_match}' 검색 결과 ({len(matches)}마리)"]
            buttons = []
            for i, (idx, p) in enumerate(matches[:20]):
                s = shiny_emoji() if p.get("is_shiny") else ""
                rb = rarity_badge(p.get("rarity", ""))
                tb = type_badge(p["pokemon_id"], p.get("pokemon_type"))
                iv_tag = ""
                if p.get("iv_hp") is not None:
                    grade, _ = config.get_iv_grade(_iv_sum(p))
                    iv_tag = format_personality_iv_tag(p.get("personality"), grade)
                team_tag = f" 🎯팀{p['team_num']}" if p.get("team_num") else ""
                lines.append(f"{i+1}. {rb}{tb}{s} {poke_name(p, lang)}{iv_tag}{team_tag}")
                page = idx // MYPOKE_PAGE_SIZE
                buttons.append([InlineKeyboardButton(
                    f"{i+1}. {poke_name(p, lang)}{' ✨' if p.get('is_shiny') else ''}",
                    callback_data=f"mypoke_v_{user_id}_{idx}_{page}",
                )])
            from telegram import InlineKeyboardMarkup
            await update.message.reply_text(
                "\n".join(lines),
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode="HTML",
            )
        return

    # Default: show list view page 0
    filt = _get_filter(context)
    list_text, list_markup = _build_list_view(user_id, pokemon_list, page=0, filt=filt, lang=lang)
    await update.message.reply_text(list_text, reply_markup=list_markup, parse_mode="HTML")
