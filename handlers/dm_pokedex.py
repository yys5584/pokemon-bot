"""DM handlers for Pokedex and My Pokemon."""

import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile, ReplyKeyboardMarkup
from telegram.ext import ContextTypes

import config
from database import queries
from utils.helpers import hearts_display, rarity_display, rarity_badge, rarity_badge_label, escape_html, type_badge, _type_emoji
from utils.card_generator import generate_card
from utils.parse import parse_number, parse_name_arg
from utils.battle_calc import iv_total

logger = logging.getLogger(__name__)

POKEDEX_PAGE_SIZE = 10
MYPOKE_PAGE_SIZE = 10
ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "pokemon")


async def pokedex_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /도감 or /pokedex command (DM only)."""
    if not update.effective_user:
        return

    user_id = update.effective_user.id
    display_name = update.effective_user.first_name or "트레이너"

    await queries.ensure_user(user_id, display_name, update.effective_user.username)

    # Check if searching for a specific Pokemon name
    from utils.parse import parse_args, parse_number
    text = (update.message.text or "").strip()
    args = parse_args(text)

    if args and not args[0].isdigit():
        # Pokemon name search: "도감 파이리"
        name_query = " ".join(args)
        await _show_pokemon_detail(update, user_id, name_query)
        return

    # Get user's pokedex entries
    pokedex = await queries.get_user_pokedex(user_id)
    caught_ids = {p["pokemon_id"]: p for p in pokedex}
    total = len(caught_ids)

    # Get user info for title
    user = await queries.get_user(user_id)
    title_part = f" {user['title_emoji']} {user['title']}" if user and user["title"] else ""

    # Page handling
    page = 0
    num = parse_number(text)
    if num is not None:
        page = num - 1

    # Build Pokedex display
    all_pokemon = await queries.get_all_pokemon()
    start = page * POKEDEX_PAGE_SIZE
    end = start + POKEDEX_PAGE_SIZE
    page_pokemon = all_pokemon[start:end]
    total_pages = (len(all_pokemon) + POKEDEX_PAGE_SIZE - 1) // POKEDEX_PAGE_SIZE

    gen1 = sum(1 for pid in caught_ids if pid <= 151)
    gen2 = sum(1 for pid in caught_ids if 152 <= pid <= 251)
    lines = [f"🏅 {escape_html(display_name)}의 도감 ({total}/251){title_part}"]
    lines.append(f"1세대: {gen1}/151 | 2세대: {gen2}/100\n")

    for pm in page_pokemon:
        pid = pm["id"]
        if pid in caught_ids:
            entry = caught_ids[pid]
            evo_mark = " ★진화" if entry["method"] == "evolve" else ""
            trade_mark = " 🔄교환" if entry["method"] == "trade" else ""
            rb = rarity_badge(pm["rarity"])
            lines.append(
                f"{pid:03d} {rb} {pm['name_ko']}{evo_mark}{trade_mark}"
            )
        else:
            lines.append(f"{pid:03d} ・ ???")

    lines.append(f"\n수집률: {total / 251 * 100:.1f}%  ({page + 1}/{total_pages})")

    # Pagination buttons
    buttons = []
    if page > 0:
        buttons.append(
            InlineKeyboardButton("◀ 이전", callback_data=f"dex_{page}")
        )
    if end < len(all_pokemon):
        buttons.append(
            InlineKeyboardButton("다음 ▶", callback_data=f"dex_{page + 2}")
        )

    markup = InlineKeyboardMarkup([buttons]) if buttons else None

    await update.message.reply_text(
        "\n".join(lines),
        reply_markup=markup,
        parse_mode="HTML",
    )


async def pokedex_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Pokedex pagination callback."""
    query = update.callback_query
    if not query or not query.data.startswith("dex_"):
        return

    await query.answer()

    user_id = query.from_user.id
    page = int(query.data.split("_")[1]) - 1

    pokedex = await queries.get_user_pokedex(user_id)
    caught_ids = {p["pokemon_id"]: p for p in pokedex}
    total = len(caught_ids)

    user = await queries.get_user(user_id)
    display_name = user["display_name"] if user else "트레이너"
    title_part = f" {user['title_emoji']} {user['title']}" if user and user["title"] else ""

    all_pokemon = await queries.get_all_pokemon()
    start = page * POKEDEX_PAGE_SIZE
    end = start + POKEDEX_PAGE_SIZE
    page_pokemon = all_pokemon[start:end]
    total_pages = (len(all_pokemon) + POKEDEX_PAGE_SIZE - 1) // POKEDEX_PAGE_SIZE

    gen1 = sum(1 for pid in caught_ids if pid <= 151)
    gen2 = sum(1 for pid in caught_ids if 152 <= pid <= 251)
    lines = [f"🏅 {escape_html(display_name)}의 도감 ({total}/251){title_part}"]
    lines.append(f"1세대: {gen1}/151 | 2세대: {gen2}/100\n")

    for pm in page_pokemon:
        pid = pm["id"]
        if pid in caught_ids:
            entry = caught_ids[pid]
            evo_mark = " ★진화" if entry["method"] == "evolve" else ""
            trade_mark = " 🔄교환" if entry["method"] == "trade" else ""
            rb = rarity_badge(pm["rarity"])
            lines.append(
                f"{pid:03d} {rb} {pm['name_ko']}{evo_mark}{trade_mark}"
            )
        else:
            lines.append(f"{pid:03d} ・ ???")

    lines.append(f"\n수집률: {total / 251 * 100:.1f}%  ({page + 1}/{total_pages})")

    buttons = []
    if page > 0:
        buttons.append(
            InlineKeyboardButton("◀ 이전", callback_data=f"dex_{page}")
        )
    if end < len(all_pokemon):
        buttons.append(
            InlineKeyboardButton("다음 ▶", callback_data=f"dex_{page + 2}")
        )

    markup = InlineKeyboardMarkup([buttons]) if buttons else None

    try:
        await query.edit_message_text(
            "\n".join(lines),
            reply_markup=markup,
            parse_mode="HTML",
        )
    except Exception:
        pass  # Message might not have changed


async def my_pokemon_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /내포켓몬 command (DM only) — text list view."""
    if not update.effective_user:
        return

    user_id = update.effective_user.id
    await queries.ensure_user(
        user_id,
        update.effective_user.first_name or "트레이너",
        update.effective_user.username,
    )

    pokemon_list = await queries.get_user_pokemon_list(user_id)

    if not pokemon_list:
        await update.message.reply_text(
            "보유한 포켓몬이 없습니다.\n"
            "그룹 채팅방에서 ㅊ 으로 잡아보세요!"
        )
        return

    # Check if a specific index was given: "내포켓몬 3"
    from utils.parse import parse_number
    text = (update.message.text or "").strip()
    num = parse_number(text)

    if num is not None:
        # Direct detail view for a specific pokemon
        idx = max(0, min(num - 1, len(pokemon_list) - 1))
        page = idx // MYPOKE_PAGE_SIZE
        detail_text, detail_markup = _build_detail_view(user_id, pokemon_list, idx, page)
        await update.message.reply_text(detail_text, reply_markup=detail_markup, parse_mode="HTML")
        return

    # Default: show list view page 0
    filt = _get_filter(context)
    list_text, list_markup = _build_list_view(user_id, pokemon_list, page=0, filt=filt)
    await update.message.reply_text(list_text, reply_markup=list_markup, parse_mode="HTML")


def _get_filter(context) -> dict:
    """Get current filter state from user_data."""
    return context.user_data.setdefault("mypoke_filter", {
        "sort": "default",  # default / iv / rarity
        "fav": False,       # 즐겨찾기만 보기
        "type": None,       # None = 전체, "fire" = 특정 타입
    })


def _iv_sum(p: dict) -> int:
    """Calculate IV total for a pokemon dict."""
    if p.get("iv_hp") is None:
        return 0
    return iv_total(p["iv_hp"], p.get("iv_atk", 0), p.get("iv_def", 0),
                    p.get("iv_spa", 0), p.get("iv_spdef", 0), p.get("iv_spd", 0))


def _apply_filters(pokemon_list: list, filt: dict) -> list:
    """Apply filter and sort to pokemon list."""
    filtered = list(pokemon_list)

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

    # Favorite filter
    if filt.get("fav"):
        filtered = [p for p in filtered if p.get("is_favorite")]

    # Sort
    sort_mode = filt.get("sort", "default")
    if sort_mode == "iv":
        filtered.sort(key=lambda p: _iv_sum(p), reverse=True)
    elif sort_mode == "rarity":
        rarity_order = {"legendary": 0, "epic": 1, "rare": 2, "common": 3}
        filtered.sort(key=lambda p: (rarity_order.get(p.get("rarity", "common"), 4), -_iv_sum(p)))

    return filtered


def _build_list_view(user_id: int, pokemon_list: list, page: int,
                     filt: dict = None) -> tuple[str, InlineKeyboardMarkup]:
    """Build a text-based list of pokemon with inline buttons.
    Shows team pokemon first, then groups duplicate species.
    """
    original_total = len(pokemon_list)
    slot_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣"]

    # Apply filters if provided
    if filt is None:
        filt = {"sort": "default", "fav": False, "type": None}
    has_filter = filt.get("sort") != "default" or filt.get("fav") or filt.get("type")

    if has_filter:
        filtered = _apply_filters(pokemon_list, filt)
    else:
        filtered = pokemon_list

    total = len(filtered)

    # Identify team pokemon (for header display) — only in default mode
    team_pokemon = [p for p in pokemon_list if p.get("team_slot") is not None] if not has_filter else []

    # Group ALL pokemon by pokemon_id
    from collections import OrderedDict
    groups = OrderedDict()
    for p in filtered:
        pid = p["pokemon_id"]
        if pid not in groups:
            groups[pid] = []
        groups[pid].append(p)

    # Build display items
    display_items = []
    all_indices = {id(p): i for i, p in enumerate(pokemon_list)}

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
    if filt.get("sort") == "iv":
        filter_tags.append("IV순")
    elif filt.get("sort") == "rarity":
        filter_tags.append("희귀도순")
    if filt.get("fav"):
        filter_tags.append("⭐즐찾")
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
            tn = p.get("team_num", 1)
            if tn not in teams:
                teams[tn] = []
            teams[tn].append(p)
        for tn in sorted(teams.keys()):
            lines.append(f"\n⚔️ 팀{tn}")
            for p in teams[tn]:
                slot = p.get("team_slot", 1) - 1
                se = slot_emojis[slot] if 0 <= slot < 6 else "▸"
                shiny = "✨" if p.get("is_shiny") else ""
                rb = rarity_badge(p.get("rarity", ""))
                tb = type_badge(p["pokemon_id"], p.get("pokemon_type"))
                iv_tag = ""
                if p.get("iv_hp") is not None:
                    grade, _ = config.get_iv_grade(_iv_sum(p))
                    iv_tag = f" [{grade}]"
                lines.append(f"{se} {rb}{tb}{shiny} {p['name_ko']}{iv_tag}")
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
                shiny = "✨" if p.get("is_shiny") else ""
                fav = "⭐" if p.get("is_favorite") else ""
                evo_mark = ""
                if p["evolves_to"] and p["evolution_method"] == "friendship" and p["friendship"] >= config.MAX_FRIENDSHIP:
                    evo_mark = " ⭐"
                # IV grade
                iv_tag = ""
                if p.get("iv_hp") is not None:
                    grade, _ = config.get_iv_grade(_iv_sum(p))
                    iv_tag = f" [{grade}]"
                rb = rarity_badge(p.get("rarity", ""))
                tb = type_badge(p["pokemon_id"], p.get("pokemon_type"))
                lines.append(f"{item_num}. {rb}{tb}{shiny}{fav} {p['name_ko']}{iv_tag}  {hearts}{evo_mark}")
            else:  # group
                _, pid, indices, first, count = item
                rb = rarity_badge(first.get("rarity", ""))
                tb = type_badge(first["pokemon_id"], first.get("pokemon_type"))
                lines.append(f"{item_num}. {rb}{tb} {first['name_ko']}  x{count}")
            item_num += 1

    # Build buttons
    select_buttons = []
    row = []
    for i, item in enumerate(page_items):
        num = start + i + 1
        if item[0] == "single":
            _, idx, p = item
            label = f"{num}. {p['name_ko']}"
            cb = f"mypoke_v_{user_id}_{idx}_{page}"
        else:
            _, pid, indices, first, count = item
            label = f"{num}. {first['name_ko']} x{count}"
            cb = f"mypoke_g_{user_id}_{pid}_{page}"
        row.append(InlineKeyboardButton(label, callback_data=cb))
        if len(row) == 2:
            select_buttons.append(row)
            row = []
    if row:
        select_buttons.append(row)

    # Filter buttons row
    sort_mode = filt.get("sort", "default")
    fav_on = filt.get("fav", False)
    type_on = filt.get("type")
    filter_row = [
        InlineKeyboardButton(
            f"{'✓' if sort_mode == 'iv' else ''}⚡IV순",
            callback_data=f"mypoke_sort_{user_id}_iv",
        ),
        InlineKeyboardButton(
            f"{'✓' if sort_mode == 'rarity' else ''}💎희귀도",
            callback_data=f"mypoke_sort_{user_id}_rarity",
        ),
        InlineKeyboardButton(
            f"{'✓' if fav_on else ''}⭐즐찾",
            callback_data=f"mypoke_favf_{user_id}",
        ),
    ]
    select_buttons.append(filter_row)

    # Type filter row (show active type or "타입" button)
    if type_on:
        type_name = config.TYPE_NAME_KO.get(type_on, type_on)
        select_buttons.append([
            InlineKeyboardButton(f"✓{type_name} 해제", callback_data=f"mypoke_tf_{user_id}_x"),
            InlineKeyboardButton("🔄 타입변경", callback_data=f"mypoke_tmore_{user_id}"),
        ])
    else:
        select_buttons.append([
            InlineKeyboardButton("🏷 타입필터", callback_data=f"mypoke_tmore_{user_id}"),
        ])

    # Pagination
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("◀ 이전", callback_data=f"mypoke_l_{user_id}_{page - 1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("다음 ▶", callback_data=f"mypoke_l_{user_id}_{page + 1}"))
    if nav_row:
        select_buttons.append(nav_row)

    markup = InlineKeyboardMarkup(select_buttons)
    return "\n".join(lines), markup


def _build_group_view(user_id: int, pokemon_list: list, pokemon_id: int, page: int) -> tuple[str, InlineKeyboardMarkup]:
    """Show individual pokemon within a duplicate group."""
    members = [p for p in pokemon_list if p["pokemon_id"] == pokemon_id]
    if not members:
        return "해당 포켓몬을 찾을 수 없습니다.", InlineKeyboardMarkup([])

    first = members[0]
    rb = rarity_badge(first.get("rarity", ""))
    tb = type_badge(first["pokemon_id"], first.get("pokemon_type"))
    lines = [f"{rb}{tb} {first['name_ko']} 보유 목록 ({len(members)}마리)\n"]

    buttons = []
    row = []
    for i, p in enumerate(members):
        idx = pokemon_list.index(p)
        num = i + 1
        shiny = " ✨이로치" if p.get("is_shiny") else ""
        max_f = config.get_max_friendship(p)
        hearts = hearts_display(p["friendship"], max_f)

        # IV grade
        iv_tag = ""
        iv_hp = p.get("iv_hp")
        if iv_hp is not None:
            total = iv_total(iv_hp, p.get("iv_atk"), p.get("iv_def"),
                             p.get("iv_spa"), p.get("iv_spdef"), p.get("iv_spd"))
            grade, _ = config.get_iv_grade(total)
            iv_tag = f" [{grade}]"

        team_mark = f" ⚔{p.get('team_num','')}" if p.get("team_slot") is not None else ""
        lines.append(f"#{num}  {first['name_ko']}{shiny}  {hearts}{iv_tag}{team_mark}")

        label = f"#{num}{shiny[:1]}{iv_tag}"
        row.append(InlineKeyboardButton(label, callback_data=f"mypoke_v_{user_id}_{idx}_{page}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append([InlineKeyboardButton("📋 목록으로", callback_data=f"mypoke_l_{user_id}_{page}")])
    return "\n".join(lines), InlineKeyboardMarkup(buttons)


def _build_detail_view(user_id: int, pokemon_list: list, idx: int, page: int) -> tuple[str, InlineKeyboardMarkup]:
    """Build detail text for a single pokemon with action buttons."""
    p = pokemon_list[idx]
    total = len(pokemon_list)
    num = idx + 1

    max_f = config.get_max_friendship(p)
    hearts = hearts_display(p["friendship"], max_f)
    shiny_mark = "✨" if p.get("is_shiny") else ""

    evo_text = ""
    if p["evolves_to"] and p["evolution_method"] == "friendship" and p["friendship"] >= config.MAX_FRIENDSHIP:
        evo_text = "\n⭐ 진화 가능! → '진화 " + str(num) + "' 입력"
    elif p["evolves_to"] and p["evolution_method"] == "trade":
        evo_text = "\n🔄 교환으로 진화 가능"

    rarity_text = rarity_badge_label(p["rarity"])
    shiny_text = "  ✨이로치" if p.get("is_shiny") else ""

    # IV information
    from utils.battle_calc import calc_battle_stats, format_stats_line, format_power, iv_total, EVO_STAGE_MAP
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
        iv_line = f"\nIV: {iv_hp}/{iv_atk}/{iv_def}/{iv_spa}/{iv_spdef}/{iv_spd} ({total_iv}/186) [{grade}]"

        # Calculate battle stats with IVs
        pid = p["pokemon_id"]
        evo_stage = EVO_STAGE_MAP.get(pid, 3)
        stats = calc_battle_stats(
            p["rarity"], p.get("stat_type", "balanced"), p["friendship"],
            evo_stage=evo_stage,
            iv_hp=iv_hp, iv_atk=iv_atk, iv_def=iv_def,
            iv_spa=iv_spa, iv_spdef=iv_spdef, iv_spd=iv_spd,
        )
        base = calc_battle_stats(
            p["rarity"], p.get("stat_type", "balanced"), p["friendship"],
            evo_stage=evo_stage,
        )
        stats_line = (
            f"\n⚡ 전투력: {format_power(stats, base)}"
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
        f"{shiny_mark}{tb} {p['name_ko']}{shiny_text}",
        f"등급: {rarity_text}{type_display}",
        f"친밀도: {hearts} ({p['friendship']}/{max_f}){evo_text}{iv_line}{stats_line}",
    ]

    # Team info
    team_info = ""
    if p.get("team_slot") is not None:
        team_info = f"\n⚔️ 팀{p.get('team_num', 1)} — {p['team_slot']}번 슬롯"
    lines.append(team_info)

    # Action buttons
    buttons = []

    # Row 1: actions
    action_row = [
        InlineKeyboardButton("📋 감정", callback_data=f"mypoke_appr_{user_id}_{idx}_{page}"),
        InlineKeyboardButton("🍖 밥", callback_data=f"mypoke_feed_{user_id}_{idx}_{page}"),
        InlineKeyboardButton("🎮 놀기", callback_data=f"mypoke_play_{user_id}_{idx}_{page}"),
    ]
    # Add evolution button if eligible
    can_evo_friendship = p["evolves_to"] and p["evolution_method"] == "friendship" and p["friendship"] >= config.MAX_FRIENDSHIP
    can_evo_trade = p["evolves_to"] and p["evolution_method"] == "trade"
    if can_evo_friendship:
        action_row.append(InlineKeyboardButton("⭐ 진화", callback_data=f"mypoke_evo_{user_id}_{idx}_{page}"))
    buttons.append(action_row)

    # Row 2: team add + favorite
    fav_label = "⭐ 즐찾해제" if p.get("is_favorite") else "☆ 즐겨찾기"
    buttons.append([
        InlineKeyboardButton("⚔1 팀1", callback_data=f"mypoke_t1_{user_id}_{idx}_{page}"),
        InlineKeyboardButton("⚔2 팀2", callback_data=f"mypoke_t2_{user_id}_{idx}_{page}"),
        InlineKeyboardButton(fav_label, callback_data=f"mypoke_fav_{user_id}_{idx}_{page}"),
    ])

    # Row 3: navigation
    detail_nav = []
    if idx > 0:
        detail_nav.append(InlineKeyboardButton("◀ 이전", callback_data=f"mypoke_v_{user_id}_{idx - 1}_{page}"))
    detail_nav.append(InlineKeyboardButton("📋 목록", callback_data=f"mypoke_l_{user_id}_{page}"))
    if idx < total - 1:
        detail_nav.append(InlineKeyboardButton("다음 ▶", callback_data=f"mypoke_v_{user_id}_{idx + 1}_{page}"))
    buttons.append(detail_nav)

    markup = InlineKeyboardMarkup(buttons)
    return "\n".join(lines), markup


async def my_pokemon_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 내포켓몬 callbacks: list, detail, group, and action buttons."""
    query = update.callback_query
    if not query or not query.data.startswith("mypoke_"):
        return

    data = query.data
    parts = data.split("_")
    action = parts[1]
    user_id = int(parts[2])

    if query.from_user.id != user_id:
        return

    await query.answer()

    pokemon_list = await queries.get_user_pokemon_list(user_id)
    if not pokemon_list:
        try:
            await query.edit_message_text("보유한 포켓몬이 없습니다.")
        except Exception:
            pass
        return

    filt = _get_filter(context)

    try:
        if action == "l":
            page = int(parts[3])
            text, markup = _build_list_view(user_id, pokemon_list, page, filt=filt)
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")

        elif action == "sort":
            # mypoke_sort_{user_id}_{mode}
            mode = parts[3]
            if filt["sort"] == mode:
                filt["sort"] = "default"  # toggle off
            else:
                filt["sort"] = mode
            text, markup = _build_list_view(user_id, pokemon_list, 0, filt=filt)
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")

        elif action == "favf":
            # mypoke_favf_{user_id} — toggle fav filter
            filt["fav"] = not filt["fav"]
            text, markup = _build_list_view(user_id, pokemon_list, 0, filt=filt)
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")

        elif action == "fav":
            # mypoke_fav_{user_id}_{idx}_{page} — toggle favorite on a pokemon
            idx = int(parts[3])
            page = int(parts[4]) if len(parts) > 4 else 0
            idx = max(0, min(idx, len(pokemon_list) - 1))
            p = pokemon_list[idx]
            new_state = await queries.toggle_favorite(p["id"])
            emoji = "⭐ 즐겨찾기 등록!" if new_state else "즐겨찾기 해제"
            await query.answer(emoji, show_alert=False)
            pokemon_list = await queries.get_user_pokemon_list(user_id)
            idx = max(0, min(idx, len(pokemon_list) - 1))
            text, markup = _build_detail_view(user_id, pokemon_list, idx, page)
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")

        elif action == "tf":
            # mypoke_tf_{user_id}_{type_key} — set type filter
            type_key = parts[3]
            if type_key == "x":
                filt["type"] = None
            else:
                filt["type"] = type_key
            text, markup = _build_list_view(user_id, pokemon_list, 0, filt=filt)
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")

        elif action == "tmore":
            # mypoke_tmore_{user_id} — show type filter grid
            type_keys = ["fire", "water", "grass", "electric", "ice", "fighting",
                         "poison", "ground", "flying", "psychic", "bug", "rock",
                         "ghost", "dragon", "dark", "steel", "fairy", "normal"]
            type_names = config.TYPE_NAME_KO
            btns = []
            row = []
            for tk in type_keys:
                tn = type_names.get(tk, tk)
                emoji = config.TYPE_EMOJI.get(tk, "")
                row.append(InlineKeyboardButton(f"{emoji}{tn}", callback_data=f"mypoke_tf_{user_id}_{tk}"))
                if len(row) == 3:
                    btns.append(row)
                    row = []
            if row:
                btns.append(row)
            btns.append([InlineKeyboardButton("✕ 필터 해제", callback_data=f"mypoke_tf_{user_id}_x")])
            btns.append([InlineKeyboardButton("◀ 돌아가기", callback_data=f"mypoke_l_{user_id}_0")])
            await query.edit_message_text("🏷 타입 필터 선택", reply_markup=InlineKeyboardMarkup(btns))

        elif action == "v":
            idx = int(parts[3])
            page = int(parts[4]) if len(parts) > 4 else idx // MYPOKE_PAGE_SIZE
            idx = max(0, min(idx, len(pokemon_list) - 1))
            text, markup = _build_detail_view(user_id, pokemon_list, idx, page)
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")

        elif action == "g":
            # Group view: mypoke_g_{user_id}_{pokemon_id}_{page}
            pokemon_id = int(parts[3])
            page = int(parts[4]) if len(parts) > 4 else 0
            text, markup = _build_group_view(user_id, pokemon_list, pokemon_id, page)
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")

        elif action == "appr":
            # Appraisal: show IV info inline
            idx = int(parts[3])
            page = int(parts[4]) if len(parts) > 4 else 0
            idx = max(0, min(idx, len(pokemon_list) - 1))
            p = pokemon_list[idx]
            text = _format_appraisal(p)
            # Back button to detail
            markup = InlineKeyboardMarkup([[
                InlineKeyboardButton("◀ 돌아가기", callback_data=f"mypoke_v_{user_id}_{idx}_{page}")
            ]])
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")

        elif action == "feed":
            idx = int(parts[3])
            page = int(parts[4]) if len(parts) > 4 else 0
            idx = max(0, min(idx, len(pokemon_list) - 1))
            p = pokemon_list[idx]
            result = await _do_feed(p, user_id)
            await query.answer(result, show_alert=True)
            # Refresh detail
            pokemon_list = await queries.get_user_pokemon_list(user_id)
            idx = max(0, min(idx, len(pokemon_list) - 1))
            text, markup = _build_detail_view(user_id, pokemon_list, idx, page)
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")

        elif action == "play":
            idx = int(parts[3])
            page = int(parts[4]) if len(parts) > 4 else 0
            idx = max(0, min(idx, len(pokemon_list) - 1))
            p = pokemon_list[idx]
            result = await _do_play(p, user_id)
            await query.answer(result, show_alert=True)
            pokemon_list = await queries.get_user_pokemon_list(user_id)
            idx = max(0, min(idx, len(pokemon_list) - 1))
            text, markup = _build_detail_view(user_id, pokemon_list, idx, page)
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")

        elif action == "evo":
            idx = int(parts[3])
            page = int(parts[4]) if len(parts) > 4 else 0
            idx = max(0, min(idx, len(pokemon_list) - 1))
            p = pokemon_list[idx]
            result = await _do_evolve(p, user_id)
            await query.answer(result, show_alert=True)
            pokemon_list = await queries.get_user_pokemon_list(user_id)
            idx = max(0, min(idx, len(pokemon_list) - 1))
            text, markup = _build_detail_view(user_id, pokemon_list, idx, page)
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")

        elif action in ("t1", "t2"):
            idx = int(parts[3])
            page = int(parts[4]) if len(parts) > 4 else 0
            idx = max(0, min(idx, len(pokemon_list) - 1))
            p = pokemon_list[idx]
            team_num = 1 if action == "t1" else 2
            result = await _do_add_to_team(p, user_id, team_num)
            await query.answer(result, show_alert=True)
            pokemon_list = await queries.get_user_pokemon_list(user_id)
            idx = max(0, min(idx, len(pokemon_list) - 1))
            text, markup = _build_detail_view(user_id, pokemon_list, idx, page)
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")

    except Exception:
        pass


def _format_appraisal(p: dict) -> str:
    """Format IV appraisal text for a pokemon."""
    shiny = "✨" if p.get("is_shiny") else ""
    rb = rarity_badge(p.get("rarity", "common"))
    ivs = {
        "HP": p.get("iv_hp"), "ATK": p.get("iv_atk"), "DEF": p.get("iv_def"),
        "SPA": p.get("iv_spa"), "SPDEF": p.get("iv_spdef"), "SPD": p.get("iv_spd"),
    }
    total = iv_total(ivs["HP"], ivs["ATK"], ivs["DEF"], ivs["SPA"], ivs["SPDEF"], ivs["SPD"])
    grade, _ = config.get_iv_grade(total)
    pct = round(total / 186 * 100, 1)

    stat_labels = {"HP": "HP   ", "ATK": "공격 ", "DEF": "방어 ", "SPA": "특공 ", "SPDEF": "특방 ", "SPD": "스피드"}
    lines = [f"📋 {shiny}{rb} {p['name_ko']} 감정 결과\n"]
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


async def _do_feed(p: dict, user_id: int) -> str:
    """Execute feed action, return result message."""
    if p["fed_today"] >= config.FEED_PER_DAY:
        return f"오늘은 이미 밥을 {config.FEED_PER_DAY}번 줬습니다!"
    max_f = config.get_max_friendship(p)
    if p["friendship"] >= max_f:
        return f"{p['name_ko']} 친밀도 MAX!"
    from services.event_service import get_friendship_boost
    boost = await get_friendship_boost()
    gain = config.FRIENDSHIP_PER_FEED * boost
    new_f = min(max_f, p["friendship"] + gain)
    await queries.update_pokemon_friendship(p["id"], new_f)
    await queries.increment_feed(p["id"])
    remaining = config.FEED_PER_DAY - p["fed_today"] - 1
    return f"🍖 {p['name_ko']}에게 밥! 친밀도 {new_f}/{max_f} (남은: {remaining}회)"


async def _do_play(p: dict, user_id: int) -> str:
    """Execute play action, return result message."""
    if p["played_today"] >= config.PLAY_PER_DAY:
        return f"오늘은 이미 {config.PLAY_PER_DAY}번 놀아줬습니다!"
    max_f = config.get_max_friendship(p)
    if p["friendship"] >= max_f:
        return f"{p['name_ko']} 친밀도 MAX!"
    from services.event_service import get_friendship_boost
    boost = await get_friendship_boost()
    gain = config.FRIENDSHIP_PER_PLAY * boost
    new_f = min(max_f, p["friendship"] + gain)
    await queries.update_pokemon_friendship(p["id"], new_f)
    await queries.increment_play(p["id"])
    remaining = config.PLAY_PER_DAY - p["played_today"] - 1
    return f"🎮 {p['name_ko']}와 놀기! 친밀도 {new_f}/{max_f} (남은: {remaining}회)"


async def _do_evolve(p: dict, user_id: int) -> str:
    """Execute evolution, return result message."""
    if not p["evolves_to"]:
        return "이 포켓몬은 진화할 수 없습니다."
    if p["evolution_method"] == "trade":
        return "이 포켓몬은 교환으로만 진화합니다."
    max_f = config.get_max_friendship(p)
    if p["friendship"] < max_f:
        return f"친밀도가 부족합니다 ({p['friendship']}/{max_f})"
    # Perform evolution
    evo_target = await queries.get_pokemon_master(p["evolves_to"])
    if not evo_target:
        return "진화 대상을 찾을 수 없습니다."
    await queries.evolve_pokemon(p["id"], p["evolves_to"])
    return f"✨ {p['name_ko']}이(가) {evo_target['name_ko']}(으)로 진화했습니다!"


async def _do_add_to_team(p: dict, user_id: int, team_num: int) -> str:
    """Add pokemon to battle team, return result message."""
    from database import battle_queries as bq
    team = await bq.get_battle_team(user_id, team_num)
    # Check if already on this team
    for t in team:
        if t.get("pokemon_instance_id") == p["id"]:
            return f"이미 팀{team_num}에 등록되어 있습니다!"
    if len(team) >= config.TEAM_MAX:
        return f"팀{team_num}이 가득 찼습니다 ({config.TEAM_MAX}마리)!"
    # Legendary limit
    if p["rarity"] == "legendary":
        leg_count = sum(1 for t in team if t.get("rarity") == "legendary")
        if leg_count >= 1:
            return "전설 포켓몬은 팀당 1마리만 가능합니다!"
    # Epic duplicate check
    if p["rarity"] == "epic":
        for t in team:
            if t.get("rarity") == "epic" and t.get("pokemon_id") == p["pokemon_id"]:
                return "같은 종의 에픽 포켓몬은 중복 불가!"
    # Add to team
    instance_ids = [t["pokemon_instance_id"] for t in team] + [p["id"]]
    await bq.set_battle_team(user_id, instance_ids, team_num)
    return f"✅ {p['name_ko']}을(를) 팀{team_num}에 추가! ({len(instance_ids)}/{config.TEAM_MAX})"


# --- Pokemon TMI data (웃긴 버전) ---
POKEMON_TMI = {
    1: "사실 피카츄보다 먼저 디자인된 포켓몬 1호. 도감 번호 001은 우연이 아님. 풀/독이라 약점 4개인데 메가진화 2개 받은 럭키가이.",
    2: "중간 진화라 존재감 제로. 이상해씨 팬도 이상해꽃 팬도 있는데 이상해풀 팬은 찾기 어려움. 중2병 시절 같은 존재.",
    3: "메가진화가 2개나 있는 스타터. 꽃이 피면 암컷이라는 설정 때문에 수컷 이상해꽃 꽃은 뭐냐는 논쟁이 20년째.",
    4: "애니에서 원래 트레이너한테 비 맞으며 버림받은 에피소드가 포켓몬 역대 눈물 TOP5. 지우가 데려간 뒤에도 말 안 들음.",
    5: "리자드 시절부터 지우 말 안 듣기 시작. 진화하면 성격 나빠지는 현실적인 사춘기 포켓몬. 꼬리불 꺼지면 죽는다는 설정 무서움.",
    6: "비행/불꽃인데 드래곤 아님. 30년째 전 세계 팬들이 왜를 외치는 중. PSA 10 1판 카드 4.2억인데 그래도 드래곤 아님. 메가진화 X로 겨우 드래곤 받음.",
    7: "꼬부기부대 선글라스가 밈의 시초. 리더 꼬부기는 뾰족선글라스, 나머지는 둥근 선글라스. 이 디테일 아는 사람이 진짜 팬.",
    8: "꼬부기에서 진화하면 귀가 생김. 거북이한테 귀가 왜 필요한지는 게임프리크만 앎. 중간진화 특유의 애매한 인생.",
    9: "메가거북왕 등에 대포 2개 달림. 초대 스타터 중 경쟁력은 제일 낮았는데 5세대 조개껍질 특성으로 한때 OU급 위엄.",
    10: "캐터피는 버터플 되려고 존재하는 포켓몬. 레벨 7에 진화하니까 사실상 게임 역사상 가장 빠른 중간진화.",
    11: "딱풀은 굳히기만 쓸 수 있음. 현실의 번데기처럼 진짜 아무것도 못 하는 리얼리즘 포켓몬.",
    12: "지우가 버터플 놓아주는 장면이 포켓몬 애니 3대 눈물신. 짝짓기 위해 보내줬는데 시청자들이 더 울었음.",
    13: "독침붕 진화 루트인데 존재감 제로. 뿔충이에서 코쿤, 독침붕까지 가는 라인업에서 코쿤과 함께 누구세요 담당.",
    14: "딱풀이랑 같은 신세. 굳히기만 배우는 번데기 포켓몬 2호. 게임프리크의 복붙 디자인 철학.",
    15: "메가독침붕 공격력 150. 의외로 메가진화 받고 화력깡패 등극. 하지만 내구는 종이라 유리대포 그 자체.",
    16: "초대 노말/비행 새 포켓몬. 모든 세대 초반새의 원조. 피죤투 팬은 있어도 구구 팬은 거의 없는 슬픈 현실.",
    17: "지우의 피죤이 꽤 활약했는데 피죤투 되자마자 풀어줌. 진화시켜놓고 바로 방생하는 갓지우 클래스.",
    18: "지우가 진화 직후 야생 포켓몬 지키라고 놓아줬는데 20년 넘게 안 데리러 옴. 역대급 방치플레이.",
    19: "금은의 반바지 꼬마 민수가 세계 최강의 꼬렛이라고 전화하는 밈이 전설. TOP PERCENTAGE RATTATA 영원히 기억됨.",
    20: "라이벌 그린의 레트라가 상트안느호 이후 사라짐. 그린이 레트라를 죽였다는 팬 이론이 소름. 포켓몬타워에서 그린을 만나는 건 우연이 아닐지도.",
    21: "깨비참은 부리가 짧아서 땅을 잘 못 팜. 설정상 벌레 포켓몬 잡아먹는 포식자인데 게임에선 그냥 약함.",
    22: "깨비드릴조는 무리 지어 공격하는 설정. 애니에서 깨비드릴조 떼가 날아오는 장면은 공포 그 자체.",
    23: "아보는 로켓단 로이의 포켓몬으로 유명. AG 시리즈에서 방생당할 때 로이가 울면서 보내줌.",
    24: "아보크도 로이와 이별. 로켓단 포켓몬 방생 에피소드가 의외로 감동적이었음. 악역도 정이 있다.",
    25: "원래 주인공 파트너는 삐삐였는데 급교체. 지우가 진화석 거부한 건 유명한데 정작 라이츄가 더 강함. 인생은 불공평.",
    26: "마티스 중위의 라이츄가 피카츄한테 지는 장면이 진화만이 답이 아니다의 원조. 근데 경쟁에선 라이츄가 맞음.",
    27: "모래두지는 알로라 폼에서 얼음타입으로 환생. 사막 포켓몬이 북극 포켓몬 되는 극적인 인생역전.",
    28: "고지는 경쟁 환경에서 존재감 거의 없지만 알로라 폼의 숨겨진 특성 눈퍼뜨리기가 의외로 쓸만함.",
    29: "니드런 암컷은 포켓몬 최초의 성별 구분 포켓몬. 암수 구분이 여기서 시작됨.",
    30: "니드리나는 진화했는데 교배가 안 됨. 니드런 암컷은 교배 되는데 진화하면 불임이 되는 의문의 설정.",
    31: "니드퀸도 교배 불가. 포켓몬 세계관 최대 미스터리 중 하나. 게임프리크 코딩 실수라는 게 정설.",
    32: "니드런 수컷은 짝인 니드런 암컷과 함께 성별 시스템의 원조. 근데 인기는 암컷이 더 많음.",
    33: "니드리노는 불레/적 타이틀 화면에 나온 적 있음. 의외로 간판 출연이 있는 중간진화.",
    34: "니드킹은 설정상 꼬리 한 방으로 전봇대를 부러뜨림. 근데 공격 종족값은 102로 그냥 평범.",
    35: "원래 포켓몬 시리즈의 마스코트가 될 뻔했음. 피카츄한테 자리 뺏긴 비운의 포켓몬. 평행세계에선 삐삐가 주인공.",
    36: "6세대에서 노말에서 페어리로 재분류. 경쟁에서 우주파워+지구던지기+따라하기 세트로 의외의 활약. 텔레판 한국 크립토 슈퍼 아이돌이기도 함.",
    37: "식스테일은 알로라 폼에서 얼음/페어리로 환생. 불꽃 여우가 눈의 여우가 되는 디자인 변신이 대성공.",
    38: "나인테일 도감 설정이 꼬리를 잡으면 1000년 저주. 알로라 나인테일은 경쟁에서 오로라베일 세팅용으로 인기.",
    39: "푸린이 노래 부르면 모두 잠듦. 애니에서 잠든 사람 얼굴에 낙서하는 게 시그니처. 화난 푸린 얼굴이 밈.",
    40: "푸크린은 푸린의 진화형인데 존재감이 거의 없음. 진화 전이 더 유명한 슬픈 케이스.",
    41: "게임 역사상 가장 짜증나는 동굴 인카운터. 주바트 없는 동굴이 없음. 또 주바트 밈은 만국공통.",
    42: "골뱃은 입이 몸의 절반. 초대 도트에서는 입이 아예 몸 전체였음. 디자인 공포.",
    43: "뚜벅쵸는 일본 이름이 나조노쿠사(수수께끼의 풀). 이름부터 정체불명인데 실제로도 별 존재감 없음.",
    44: "냄새꼬는 항상 침을 흘리는 디자인. 포켓몬 중 가장 불쾌하게 생긴 Top 10 단골.",
    45: "라플레시아는 세계 최대 꽃 라플레시아에서 따옴. 시체꽃 모티브라 냄새가 역하다는 설정.",
    46: "파라스의 버섯은 동충하초 모티브. 진화하면 버섯이 본체를 완전히 지배함. 파라섹트의 눈이 흰 건 이미 죽었기 때문이라는 설정이 소름.",
    47: "파라섹트는 본체가 아니라 등의 버섯이 조종 중. 포켓몬 세계관에서 가장 무서운 설정 중 하나. 좀비 포켓몬.",
    48: "콘팡은 눈이 엄청 큰데 왜 독타입인지 모르겠는 포켓몬. 모르포나비로 진화하면 눈 디자인이 완전히 바뀜.",
    49: "모르포나비는 원래 버터플의 진화형이었다는 설이 있음. 콘팡과 캐터피의 디자인 스왑 이론이 유명.",
    50: "디그다 땅속 몸이 어떻게 생겼는지 아무도 모름. 포켓몬 최대 미스터리. 공식에서 한 번도 공개 안 함.",
    51: "닥트리오는 디그다 3마리가 모인 건데 속도가 엄청 빠름. 알로라 폼에서 금발 가발 추가되어 헤어샵 다녀옴 밈.",
    52: "로켓단 나옹은 인간 언어를 독학한 천재. 좋아하는 암컷 나옹한테 잘 보이려고 말을 배웠는데 차임. 포켓몬 세계관 최고의 비극.",
    53: "페르시온은 사카키의 무릎 위 포켓몬으로 유명. 보스 고양이 포지션의 원조. 알로라 폼 얼굴이 밈이 됨.",
    54: "고라파덕은 항상 머리가 아프고 초능력이 폭주. 이슬이의 고라파덕은 몬스터볼에서 멋대로 나오는 주인 말 안 듣는 대표 포켓몬.",
    55: "골덕은 진화하면 머리 아픈 게 나음. 수영 속도가 시속 56km. 근데 이슬이 고라파덕은 끝까지 진화 안 함.",
    56: "망키는 분노 포켓몬. 항상 화나있음. 지우 모자 뺏어간 에피소드가 유명. 5분 안에 잡힘.",
    57: "성원숭은 더 화남. 도감 설명이 화나면 죽을 때까지 쫓아옴. 포켓몬 세계관 무서운 설정 시리즈.",
    58: "가디는 전설 포켓몬 분류인데 진짜 전설이 아님. 도감 카테고리가 전설 포켓몬이라 혼동 유발의 원흉.",
    59: "윈디는 한국에서 특히 인기. 해태와 삽살개 모티브설. 경쟁에서도 꾸준히 쓰이는 인기 불꽃타입.",
    60: "발챙이는 배의 소용돌이가 내장이 비치는 거라는 설정. 귀여운 척하지만 설정은 좀 그로테스크.",
    61: "슈륙챙이는 장갑을 끼고 있음. 올챙이가 복싱 글러브를 끼는 진화과정이 포켓몬 로직.",
    62: "강챙이는 의외로 경쟁에서 강함. 숨겨진 특성 쓱쓱으로 비 팀에서 에이스급. 올챙이의 반란.",
    63: "캐이시는 순간이동만 쓰고 도망감. 야생에서 잡기 가장 짜증나는 포켓몬 TOP3. 잠만 자는데 IQ 5000.",
    64: "윤겔라 디자인이 유리 겔러 닮았다고 소송당함. 그래서 TCG에서 수년간 카드 발매 금지. 숟가락이 문제였음.",
    65: "후딘 IQ 5000인데 경쟁에서 메가진화 없으면 애매. 천재인데 취업이 안 되는 현실 반영인가.",
    66: "알통몬은 벨트가 없으면 힘 조절 불가. 포켓몬 세계의 파워 리미터 설정 원조.",
    67: "근력몬은 팔이 4개. 인간형 포켓몬인데 팔이 4개인 건 넘기고 가는 게 포켓몬 팬의 자세.",
    68: "괴력몬은 공식 설정상 이사짐센터에서 일함. 포켓몬 세계관에서 가장 현실적인 취업 사례. 일당이 궁금해짐.",
    69: "모다피 도감번호 69. 영어권 팬들이 매번 킹킹거림. 이름도 Bellsprout인데 번호가 결정적.",
    70: "우츠동은 파리지옥 모티브. 사람을 녹인다는 도감 설정이 있어서 포켓몬인데 살인식물.",
    71: "우츠보트는 로이의 포켓몬인데 맨날 로이를 잡아먹음. 애니에서 매회 로이 머리가 우츠보트 입에.",
    72: "왕눈해는 수중 동굴의 주바트 포지션. 파도타기 하면 1초마다 나옴. 또 왕눈해 트라우마.",
    73: "독파리는 촉수 80개로 독을 쏨. 애니 초기에 거대 독파리가 도시를 습격하는 에피소드는 괴수영화급.",
    74: "꼬마돌은 바위인데 자폭을 배움. 동굴에서 만나면 자폭으로 경험치도 못 주고 아군만 죽이는 테러리스트.",
    75: "데구리는 산에서 굴러다니며 민폐. 도감 설정상 매일 밑으로 굴러가서 누군가 위로 올려줘야 함.",
    76: "딱구리는 자폭의 달인. 경쟁에서 스텔스록 깔고 자폭하는 게 주 전략. 태어난 이유가 자폭.",
    77: "포니타는 불꽃 말인데 가라르에서 유니콘이 됨. 에스퍼/페어리 포니타는 디자인 대호평.",
    78: "날쌩마는 달리는 속도가 시속 240km. 포켓몬 세계에서 교통수단이 왜 필요한지 의문을 갖게 만드는 포켓몬.",
    79: "야돈은 꼬리 물리고 5초 후에 아파함. 공식 설정 IQ가 거의 0에 가까움. 근데 메가진화 받으면 천재가 됨.",
    80: "야도란은 꼬리의 셀러가 본체를 조종한다는 이론. 셀러 떼면 야돈으로 돌아감. 공생인지 기생인지 애매.",
    81: "코일은 전기/강철인데 1세대에선 전기만. 특성 자력으로 메타그로스 잡는 킬러로 활약한 적 있음.",
    82: "레어코일은 코일 3마리가 합체. 왜 3마리가 합치면 이름에 레어가 붙는지는 영원한 의문.",
    83: "일본 속담 오리가 파를 지고 온다=호구 모티브. 파를 들고 다니는 호구 컨셉인데 가라르 폼에서 파를 칼처럼 쓰는 사무라이로 각성.",
    84: "두두는 날개가 없는데 공중날기를 배움. 포켓몬 최대 불가사의 중 하나. 머리로 뛰어서 나는 건가?",
    85: "두트리오는 머리가 3개인데 성격이 다 다름. 알로라 폼에서 금발 가발 쓰고 나와서 웃음벨.",
    86: "쥬쥬는 그냥 물개임. 포켓몬 디자인이 동물 그대로 시대의 유물. 이름도 울음소리 그대로.",
    87: "쥬레곤은 듀공 모티브인데 영어 이름이 Dewgong. 실제 듀공과 이름이 같아서 헷갈리는 희귀 케이스.",
    88: "질퍽이는 슬러지 그 자체. 도감 설정상 걸어간 자리에 풀이 안 자람. 환경파괴 포켓몬.",
    89: "질뻐기는 알로라 폼에서 무지개색. 독극물이 무지개색이 되면 예뻐지는 게 포켓몬 로직. 의외로 알로라 폼 인기 많음.",
    90: "셀러는 혀를 내밀고 있는 조개. 디자인이 좀 그래서 언급하기 어려운 포켓몬 순위 상위권.",
    91: "파르셀은 영어 이름 Cloyster와 디자인이 합쳐져서 인터넷에서 영원히 밈. 경쟁에서 껍질깨기가 사기.",
    92: "고오스는 가스로 이루어진 유령. 초대에서 에스퍼 타입 견제용인데 독타입 때문에 에스퍼한테 약점 잡힘. 본말전도.",
    93: "고우스트는 고오스의 진화형인데 통신교환 안 하면 여기서 멈춤. 친구 없으면 팬텀은 못 쓰는 잔인한 시스템.",
    94: "팬텀은 초대 최강 포켓몬 중 하나. 메가팬텀은 경쟁에서 사용금지급. 그림자밟기로 도망도 못 치게 하는 악마.",
    95: "롱스톤은 크기가 8.8m인데 방어력이 생각보다 낮음. 강철코트 주면 강철톤 되는데 친구가 필요.",
    96: "슬리프는 도감 설정이 아이들의 꿈을 먹음. 포켓몬 세계관 범죄자 포켓몬 1위. 디자인도 수상함.",
    97: "슬리퍼는 슬리프보다 더 무서운 설정. 최면술로 아이를 데려간다는 도감 기록. 이걸 아동용 게임에 넣은 게임프리크 대단.",
    98: "크랩은 그냥 게. 이름도 Krabby. 지우가 잡았는데 오박사 연구소에서 평생 대기.",
    99: "킹크랩은 관장전에서 갑자기 등장해 활약. 지우의 숨겨진 에이스였던 적이 딱 한 번 있음.",
    100: "찌리리공은 몬스터볼을 닮음. 발전소에서 자폭하는 존재. 아이템인 줄 알고 클릭하면 전투 시작되는 트롤.",
    101: "붐볼은 찌리리공의 진화형인데 뒤집은 몬스터볼 디자인. 자폭 위력이 높아서 경쟁에서 자폭셔틀로 쓰임.",
    102: "아라리는 달걀 6개가 모인 포켓몬인데 풀/에스퍼. 달걀이 초능력 쓰는 세계관. 하나가 깨지면 어떻게 되는지는 미지수.",
    103: "나시는 알로라 폼에서 목이 10m로 늘어남. 드래곤 타입 추가. 야자수가 드래곤이 되는 포켓몬 로직에 팬들 폭소.",
    104: "탕구리는 죽은 엄마의 뼈다귀와 두개골을 쓰고 다님. 포켓몬 역대 가장 슬픈 설정. 울음소리도 슬픔.",
    105: "텅구리는 알로라 폼에서 불꽃/고스트. 엄마 원한이 불꽃이 된 건가. 경쟁에서 굵은뼈 아이템으로 화력 2배.",
    106: "시라소몬은 발차기 전문. 일본명이 킥복서 사와무라에서 따옴. 격투 포켓몬의 원조.",
    107: "홍수몬은 펀치 전문. 이름 유래가 복서. 시라소몬이랑 택1 진화라 선택장애 유발.",
    108: "내루미는 혀가 2m. 뭐든 핥는다는 설정. 도감 설명이 점점 이상해지는 포켓몬 대표.",
    109: "또가스는 로켓단 로이의 상징. 독가스인데 이름이 또가스라서 한국에선 방귀 드립의 표적.",
    110: "또도가스는 가라르 폼에서 굴뚝모자 신사가 됨. 독가스가 영국 신사로 변신하는 건 산업혁명 풍자.",
    111: "뿔카노는 시력이 나빠서 직진밖에 못 함. 달리다 멈추면 왜 달렸는지 잊는다는 설정. 공감 가는 포켓몬.",
    112: "코뿌리가 사실 포켓몬 역사상 가장 먼저 프로그래밍된 포켓몬. 도감번호 1번인 이상해씨보다 먼저 만들어짐. 숨겨진 원조.",
    113: "럭키는 경쟁에서 진화의휘석 달면 방특이 미친 수치. HP 255인데 방어 5. 극단적 종족값의 아이콘.",
    114: "덩구리는 덩굴이 얼굴을 가리고 있어서 본체 얼굴을 아무도 모름. 디그다 지하 미스터리와 쌍벽.",
    115: "캥카는 메가진화하면 주머니의 새끼가 나와서 싸움. 아기를 전투에 내보내는 어미라는 윤리적 논쟁 유발.",
    116: "쏘드라는 해마 포켓몬. 킹드라까지 진화하면 드래곤 타입 추가되는데 리자몽은 안 되고 해마는 되는 세상.",
    117: "시드라는 독가시로 기절시킨다는 설정. 중간진화라 존재감 없지만 킹드라 진화 루트의 핵심.",
    118: "콘치는 뿔이 자랑인 금붕어 포켓몬. 이슬이가 좋아하는 포켓몬인데 인기는 별로.",
    119: "왕콘치는 폭포오르기를 배우는 몇 안 되는 포켓몬이었음. 지금은 아무도 안 씀.",
    120: "별가사리는 보석이 본체. 경쟁에서 자연회복과 빛의장막 서포터로 간간이 보임.",
    121: "아쿠스타는 에스퍼/물 복합타입. 보석이 빛나면 뭔가 통신한다는 UFO스러운 설정.",
    122: "배리어는 지우 엄마와 함께 사는 포켓몬. 팬들 사이에서 지우 새아빠라는 밈이 20년째 현역. 가라르에서 배리어드 진화 추가.",
    123: "스라크는 낫 양팔. 도감 설정상 풀을 베는 데 쓰이는데 어떻게 몬스터볼을 터치하는지 의문.",
    124: "루주라는 디자인 인종차별 논란으로 피부색이 검정에서 보라로 변경. 포켓몬 역사상 가장 큰 디자인 수정 사건.",
    125: "에레브는 전기타입 원조 강자. 에레키블로 진화하면서 뚱뚱해져서 팬들 충격.",
    126: "마그마는 불꽃타입 원조. 마그마번으로 진화시 디자인 호불호가 극명.",
    127: "쁘사이저는 메가진화로 비행타입 추가. 사슴벌레가 날게 된 순간. 경쟁에서 깜놀 화력.",
    128: "켄타로스는 지우가 사파리존에서 30마리를 잡음. 한 에피소드에서 30마리. 지우 인생 최고의 사냥 효율.",
    129: "공식 설정 가장 약하고 한심한 포켓몬. 튀어오르기 PP 40짜리 하나로 버팀. 포켓몬센터 앞 상인이 500원에 팔아먹는 사기 이벤트도 있음.",
    130: "갸라도스는 물/비행이지 드래곤 아님. 잉어킹에서 이걸로 싶은 디자인 변화. 색다른 갸라도스는 호수의 분노 이벤트로 유명.",
    131: "라프라스는 바다 위 택시. 파도타기의 상징. 한때 멸종 위기였다가 너무 번식해서 문제라는 도감 설정이 현실적.",
    132: "뮤 복제 실패작이라는 팬 이론이 있음. 교배 만능키라 포켓몬 세계관 최고의 워커홀릭. 좀 쉬어.",
    133: "이브이는 진화형이 8개. 포켓몬 마케팅의 핵심 축. 진화 안 시키고 키우는 팬도 많은 아이돌급 인기.",
    134: "샤미드는 물 이브이. 세포가 물과 비슷해서 물에 녹는다는 설정이 무서움. 인어 모티브 꼬리가 예쁨.",
    135: "쥬피썬더는 번개 이브이. 경쟁에서 볼트체인지 빠른 피봇으로 쓰이기도 함. 털이 바늘처럼 서있는 디자인.",
    136: "부스터는 이브이 진화형 중 가장 불쌍. 1세대에서 불꽃타입인데 물리 불꽃기가 없어서 가장 쓸모없는 이브이 밈의 주인공.",
    137: "포켓몬 쇼크 사건의 억울한 희생양. 실제로 화면 깜빡인 건 피카츄 10만볼트인데 폴리곤이 30년째 방송 출연금지.",
    138: "트위치 플레이즈 포켓몬에서 신 헬릭스로 등극. 화석에서 부활하는데 민주주의 vs 무정부주의 논쟁의 중심이 된 전설의 포켓몬.",
    139: "암스타는 헬릭스의 진화형. 신의 진화형이라 LORD HELIX EVOLVED로 트위치 채팅 폭발했던 순간.",
    140: "투구는 살아있는 화석 포켓몬. 투구벌레 모티브인데 3억년 전 모습 그대로라는 설정.",
    141: "투구푸스는 낫 양팔. 화석 포켓몬인데 의외로 경쟁에서 쓱쓱 비팀 물리어태커로 가끔 보임.",
    142: "프테라는 메가진화 받은 화석 포켓몬. 공중전의 원조 강자. 도감 설정상 고대에는 하늘의 왕이었음.",
    143: "길 막고 서있어서 포켓몬피리 없으면 진행 불가. 하루에 400kg 먹는 설정. 먹고 자고 반복이 라이프스타일의 아이콘.",
    144: "프리져는 3신조 중 얼음. 경쟁에서 가장 약한 편. 가라르 폼에서 에스퍼/비행으로 변경되어 이게 프리져란 반응.",
    145: "썬더는 3신조 중 전기. 경쟁에서 가장 강한 전설의새. 프레셔 특성으로 PP 말리기 전략의 원조.",
    146: "파이어는 3신조 중 불꽃. 디자인이 불붙은 새라서 가장 단순하다는 평가. 가라르 폼은 악/비행으로 변신.",
    147: "미뇽은 바다의 보석이라는 별명. 용 포켓몬의 원조인데 뱀처럼 생김. 귀여움에서 망나뇽으로의 디자인 변화가 충격적.",
    148: "신뇽은 미뇽의 우아한 진화. 망나뇽과 디자인 괴리가 너무 커서 중간에 디자이너 바뀐 거 아니냐는 의혹.",
    149: "신뇽의 우아한 모습에서 갑자기 주황색 카이류. 디자인 변경이 포켓몬 역사상 가장 충격적. 그래도 초대 600족 최강 중 하나.",
    150: "뮤츠는 뮤를 복제해 만든 인공 포켓몬. 극장판 1편의 주인공. 나는 왜 태어났는가가 아동용 영화 대사라니.",
    151: "뮤는 모든 포켓몬의 조상이라는 설정. 151번이라 숨겨진 포켓몬 취급. 트럭 밑에 뮤 있다는 루머로 전 세계가 들썩.",
    152: "죠토 스타터 중 인기 꼴찌. 지우가 선택했지만 왜 치코리타라는 반응이 다수. 풀타입의 한계.",
    153: "베이리프는 지우한테 반해서 들이받는 애정표현. 트레이너에게 사랑을 느끼는 포켓몬 설정이 좀 아슬아슬.",
    154: "메가니움은 경쟁에서 죠토 스타터 중 가장 약함. 풀 단타입에 화력도 내구도 애매. 꽃이 예쁜 게 위안.",
    155: "브케인은 죠토 스타터 인기 1위. 등에 불꽃이 기분에 따라 바뀜. 히노아라시 팬덤이 의외로 거대.",
    156: "마그케인은 중간진화 특유의 존재감 부족. 블레이범으로의 징검다리 인생.",
    157: "블레이범은 죠토 불꽃 스타터 최종. 히스이 폼에서 불꽃/고스트로 부활. 경쟁에서 히스이 폼이 대활약.",
    158: "리아코는 물 악어인데 춤추는 모습이 귀여움. 죠토 물 스타터 팬덤이 꽤 탄탄.",
    159: "엘리게이는 리아코 진화형. 중간진화인데 나름 인기 있음. 악어가 직립보행하는 시점.",
    160: "장크로다일은 영어 이름이 Feraligatr. 10글자 제한 때문에 Feraligator에서 o를 뺌. 글자수 제한의 희생양.",
    161: "꼬리선은 보초 서는 포켓몬. 초반 노말타입의 금은 버전. 꼬렛보다는 귀여운데 그래도 약함.",
    162: "다꼬리는 꼬리선 진화. 길쭉한 몸이 족제비 모티브. 경쟁에서 안 쓰이지만 디자인 팬은 있음.",
    163: "부우부는 올빼미 포켓몬. 야부엉으로 진화. 머리를 180도 돌리는 설정이 현실 올빼미와 동일.",
    164: "야부엉은 지우가 색이 다른 개체를 잡음. 애니에서 색다른 포켓몬 잡는 희귀 이벤트.",
    165: "레디바는 금은 초반 벌레. 5마리가 모여야 활동한다는 설정인데 1마리로 배틀하니 약할 수밖에.",
    166: "레디안은 별빛으로 방향을 잡는다는 로맨틱 설정. 하지만 종족값이 처참해서 경쟁에서는 빛을 못 봄.",
    167: "페이검은 거미 포켓몬. 밤에 거미줄 치고 기다리는 설정. 금은 야간 출현 포켓몬의 대표.",
    168: "아리아도스는 거미줄로 먹이를 잡는 포켓몬. 독/벌레 조합이 약점 투성이라 경쟁에서 고생.",
    169: "크로뱃은 친밀도 진화의 아이콘. 웅이의 크로뱃이 유명. 동굴 악몽 주바트가 최종적으로 강해지는 성장 서사.",
    170: "초라기는 심해어 모티브. 안테나에서 빛을 내는 설정. 물/전기 조합이 독특함.",
    171: "랜턴은 심해에서 빛으로 먹이를 유인. 특성 축전으로 물 기술 흡수. 의외로 방특이 높아서 서포터로 활용.",
    172: "피츄는 피카츄의 베이비 포켓몬. 자기 전기에 자기가 놀라는 설정이 귀여움. 대난투에서도 참전.",
    173: "삐는 삐삐의 베이비. 별똥별 타고 온다는 설정. 우주 포켓몬 팬 이론의 근거.",
    174: "푸푸린은 푸린의 베이비. 공 모양으로 통통 튀는 설정. 존재감은 푸린보다 더 없음.",
    175: "토게피는 금은 발매 전 애니에서 먼저 공개된 2세대 홍보대사. 이슬이의 아기 포켓몬으로 인기폭발.",
    176: "토게틱은 행복한 사람에게만 나타난다는 설정. 4세대에서 토게키스 진화 추가되면서 가치 상승.",
    177: "네이티는 항상 한쪽을 응시하는 새. 토템폴 모티브. 작고 동그란 게 귀여운데 에스퍼/비행이라 약점 많음.",
    178: "네이티오는 미래를 보는 포켓몬. 매직가드 특성으로 경쟁에서 간간이 보임. 항상 같은 방향을 보는 디자인이 독특.",
    179: "메리프는 양 전기 포켓몬. 금은 초반 전기타입 유일한 선택지라 거의 필수 영입.",
    180: "보송송은 메리프 진화. 털이 빠져서 분홍 피부가 드러남. 양모 깎인 양의 현실감.",
    181: "전룡은 메가진화에서 갑자기 드래곤 타입 추가. 양이 용이 되는 이유를 아무도 모름.",
    182: "아르코는 빛의돌로 진화하는 꽃 포켓몬. 냄새꼬의 분기진화인데 존재감이 거의 없는 비운의 진화형.",
    183: "마릴은 금은 발매 전 PIKABLU라는 루머로 유명. 물/페어리가 된 지금도 피카츄 아류 이미지를 벗지 못함.",
    184: "마릴리는 의외로 경쟁에서 강함. 특성 힘세고강한으로 공격력 실질 2배. 귀여운 외모와 달리 물/페어리 격투가.",
    185: "꼬지모는 나무로 위장한 바위 포켓몬. 물뿌리개 쓰면 정체 발각. 금은에서 길 막고 서있는 가짜 나무.",
    186: "왕구리는 왕의징표석으로 진화. 강챙이와 분기진화인데 개구리 왕자 컨셉. 이슬비 특성으로 비팀 서포터.",
    187: "통통코는 바람에 날아가는 민들레 포켓몬. 너무 가벼워서 바람 불면 날아감. 존재 자체가 위태로움.",
    188: "두코는 통통코 진화. 꽃이 피면 기분이 좋아진다는 설정. 중간진화 투명인간.",
    189: "솜솜코는 바람타고 세계여행. 경쟁에서 엽록소 쾌청 세팅으로 가끔 보이지만 대체로 마이너.",
    190: "에이팜은 꼬리 손이 진짜 손보다 기민함. 양손잡이인데 꼬리가 더 유능한 3번째 손.",
    191: "해너츠는 전체 포켓몬 중 종족값 합계가 가장 낮음. 180이라는 처참한 수치.",
    192: "해루미는 해너츠 태양의돌 진화. 맑은 날만 기분 좋고 흐린 날 우울해하는 기상 의존 포켓몬.",
    193: "왕자리는 금은에서 진화가 없었는데 4세대에서 메가자리 진화 추가. 20년 기다린 보람.",
    194: "우파라서 포켓몬 커뮤에서 정치드립 당하는 유일한 포켓몬. 팔데아에서 독타입 우파로 환생. 본인은 그냥 멍때리는 중.",
    195: "누오는 물/땅이라 풀 4배 약점인데 특성 저수면 물 무효. 항상 웃고 있는 얼굴이 밈.",
    196: "에브이는 낮에 친밀도 진화. 에스퍼 이브이라 매직미러 숨특이 핵심. 고양이 같은 우아한 디자인.",
    197: "블래키는 밤에 친밀도 진화. 달빛 링이 빛나는 디자인 인기 1위급. 경쟁에서 막이+독독독 조합으로 상대 멘탈 파괴.",
    198: "니로우는 마피아 보스 모자 디자인. 4세대에서 돈크로우로 진화. 악/비행이라 페어리 등장 전까지 약점 적었음.",
    199: "야도킹은 셀러가 머리를 물어서 천재가 됨. 야도란은 꼬리, 야도킹은 머리. 물리는 위치에 따라 인생이 바뀌는 포켓몬.",
    200: "무우마는 목걸이가 본체라는 설. 금은 유일한 순수 고스트. 4세대에서 무우마직으로 진화하며 경쟁급 상승.",
    201: "안농은 알파벳 26자에 느낌표와 물음표까지 총 28종류. 유적에서만 나오는데 도감 채우려면 28마리 다 잡아야 함.",
    202: "소옹은 반격기만 사용 가능. 카운터와 미러코트뿐. 로켓단 로이의 소옹이 멋대로 볼에서 나오는 게 개그포인트.",
    203: "키링키는 머리와 꼬리가 각각 다른 뇌를 가짐. 꼬리가 잠 안 자고 보초 선다는 설정. 포켓몬계의 투잡러.",
    204: "피콘은 솔방울 모티브인데 벌레타입. 자폭을 배우는 솔방울이라는 위험한 설정.",
    205: "쏘콘은 피콘 진화. 대폭발을 배움. 진화하면 더 크게 자폭하는 게 인생 목표인 포켓몬.",
    206: "노고치는 팬들이 20년 넘게 진화형을 요구. 9세대에서 드디어 노고나가 추가됨. 기다림은 배신하지 않는다.",
    207: "글라이거는 전갈+박쥐 합체 디자인. 4세대에서 글라이온으로 진화하면서 경쟁에서 독살 전략의 핵심이 됨.",
    208: "강철톤은 롱스톤에 금속코트 통신교환 진화. 메가강철톤은 모래힘 특성으로 모래팀 핵심.",
    209: "블루는 불독 모티브인데 페어리 타입. 무서운 얼굴인데 겁쟁이라는 갭 모에 설정.",
    210: "그랑블루는 블루 진화. 입이 거대한데 사실 겁쟁이. 경쟁에서 간간이 위협 특성으로 쓰임.",
    211: "침바루는 복어+성게 합체. 독/물 조합. 히스이 폼에서 독/악으로 변경되고 진화형 하리만론 추가.",
    212: "핫삼은 약점이 불꽃 단 하나. 벌레/강철+테크니션+바렛펀치 조합이 경쟁 역사상 전설. 디자인도 인기도 최상위.",
    213: "단단지는 이론상 포켓몬 중 가장 높은 데미지를 줄 수 있음. 힘세고강한+메트로놈 무한 스택으로 천문학적 수치. 실전에서는 그냥 느림.",
    214: "헤라크로스는 지우의 포켓몬. 벌레타입 최강 중 하나. 메가진화로 스킬링크 연속기 머신.",
    215: "포푸니는 날카로운 발톱의 악/얼음. 4세대에서 포푸니라로 진화. 히스이에서 포푸니치로 분기진화 추가.",
    216: "깜지곰은 꿀 좋아하는 아기곰. 이마의 초승달 마크에 꿀이 스며있다는 설정이 귀여움.",
    217: "링곰은 깜지곰 진화. 숲에서 꿀을 찾아다니는 설정. 히스이에서 다갈곰으로 진화 추가.",
    218: "마그마그는 달팽이 용암 포켓몬. 설정상 체온 1만도인데 옆에 서도 괜찮은 포켓몬 세계관 물리법칙.",
    219: "마그카르고 체온이 1만도. 태양 표면보다 뜨거움. 마그카르고 옆에 서면 증발해야 정상인데 트레이너가 만져도 됨.",
    220: "꾸꾸리는 털이 눈을 가려서 앞이 안 보임. 그래서 코로 냄새 맡으며 다님. 맘모꾸리까지 3단 진화.",
    221: "메꾸리는 꾸꾸리 진화. 4세대에서 맘모꾸리 진화 추가되면서 경쟁에서 스텔스록+얼음뭉치 셔틀로 각광.",
    222: "코산호는 산호 모티브인데 가라르에서 환경파괴로 죽은 고스트 코산호 등장. 포켓몬이 환경문제를 다루는 무거운 순간.",
    223: "총어는 물고기인데 이름에 총이 들어감. 진화하면 문어가 됨. 물고기에서 문어로의 진화가 포켓몬 역사상 가장 이해 안 되는 진화 루트.",
    224: "대포무노는 문어인데 총어에서 진화. 물고기가 문어가 되는 생물학 무시. 먹물 대포를 쏘는 설정.",
    225: "딜리버드는 선물 배달하는 산타 포켓몬. 기술 선물이 랜덤으로 회복이나 데미지. 경쟁에서 쓸 이유가 없는 시즌한정 캐릭터.",
    226: "만타인은 가오리 포켓몬. 7세대에서 만타인서핑 미니게임 추가. 등에 총어가 붙어있는 게 기본 디자인.",
    227: "무장조는 강철/비행. 경쟁에서 스텔스록+회오리바람+도발 깔아놓는 물리수비의 아이콘.",
    228: "델빌은 불꽃/악 개 포켓몬. 밤에 울음소리가 저승사자를 부른다는 설정. 도베르만+지옥견 모티브.",
    229: "헬가는 델빌 진화. 메가진화 시 태양의힘 특성으로 화력 폭발. 디자인이 멋있어서 인기 많은 악타입.",
    230: "킹드라는 물/드래곤. 비바라기팀 에이스. 쓱쓱 특성으로 스피드 2배. 해마가 용이 되는 건 해룡 전설에서 따옴.",
    231: "코코리는 아기 코끼리. 코로 물을 뿌리며 노는 설정이 귀여움. 지우가 알에서 부화시킨 포켓몬.",
    232: "코리갑은 타이어처럼 구르는 코끼리. 구르기 기술이 강력. 방어력이 높아서 물리벽으로 쓰임.",
    233: "폴리곤2는 폴리곤의 업그레이드 진화. 폴리곤 쇼크 사건 때문에 진화형인데도 애니 출연 금지. 연좌제의 피해자.",
    234: "노라키는 뿔 사슴 포켓몬. 뿔에서 공간이 왜곡된다는 설정. 경쟁에서 위협+전기자석파 서포터로 가끔 보임.",
    235: "루브도는 스케치로 모든 기술을 배울 수 있는 유일한 포켓몬. 교배용 기술 유전 필수. 화가 컨셉인데 실전에서는 기술 전달자.",
    236: "배루키는 시라소몬/홍수몬/카포에라 3분기 진화. 공격이 방어보다 높으면 시라소몬, 방어가 높으면 홍수몬, 같으면 카포에라.",
    237: "카포에라는 카포에이라 모티브. 머리로 빙빙 도는 기술. 위협 특성에 마하펀치로 하위 티어에서 활약.",
    238: "뽀뽀라는 루주라의 베이비. 루주라 디자인 논란의 여파로 뽀뽀라도 조용히 처리됨.",
    239: "에레키드는 에레브의 베이비. 전기 플러그 모양 머리가 특징.",
    240: "마그비는 마그마의 베이비. 입에서 불꽃 내뿜는 아기. 포켓몬 세계관 육아의 위험성을 보여줌.",
    241: "목장 관장 꼭두의 구르기 밀탱크가 금은 플레이어 PTSD 원인 1위. 밀탱크만 들어도 손이 떨리는 사람 다수.",
    242: "해피너스는 HP가 255로 전 포켓몬 1위. 자연회복+알낳기로 독살팀의 핵심.",
    243: "라이코는 전설의 3수 중 전기. 금은에서 돌아다니는 로밍 전설의 원조. 잡으려면 마스터볼 아니면 인내심 테스트.",
    244: "앤테이는 전설 3수 중 불꽃. 극장판 3편 주인공. 아빠를 찾는 소녀의 환상으로 등장한 감동 스토리.",
    245: "스이쿤은 전설 3수 중 물. 크리스탈 버전 패키지. 디자인 인기가 3수 중 압도적 1위.",
    246: "애버라스는 유충인데 땅/바위. 마기라스까지 키우는 게 금은의 숨겨진 엔드콘텐츠. 레벨 55에 최종진화라 인내심 필요.",
    247: "데기라스는 번데기인데 격투를 안 배움. 껍질 안에서 움직이는 설정. 중간진화 투명인간 시리즈.",
    248: "마기라스는 고질라 모티브 600족. 모래팀의 핵심. 특성 모래날림으로 등장만 해도 날씨 변경. 메가진화 시 공격 164의 괴물.",
    249: "루기아는 극장판 2편의 주인공. 바다의 신인데 에스퍼/비행. 물타입 아닌 게 30년째 의문.",
    250: "호오우는 애니 1화에서 지우가 처음 본 전설의 포켓몬. 금 버전 패키지인데 루기아가 더 유명한 비운의 전설.",
    251: "세레비는 시간여행 포켓몬. GS볼 이벤트가 미완성으로 남은 포켓몬 역사 최대 미해결 사건. 영원한 떡밥.",
}



async def _show_pokemon_detail(update: Update, user_id: int, name_query: str):
    """Show detailed info for a specific Pokemon."""
    pokemon = await queries.search_pokemon_by_name(name_query)

    if not pokemon:
        await update.message.reply_text(f"'{name_query}' 포켓몬을 찾을 수 없습니다.")
        return

    pid = pokemon["id"]
    rarity_text = rarity_badge_label(pokemon["rarity"])

    # Check if user has it
    pokedex = await queries.get_user_pokedex(user_id)
    caught_ids = {p["pokemon_id"] for p in pokedex}
    owned = "✅ 보유 중" if pid in caught_ids else "❌ 미보유"

    # Evolution chain
    evo_line = await _build_evo_chain(pokemon)

    # TMI
    tmi = POKEMON_TMI.get(pid, "")

    lines = [
        f"No.{pid:03d} {pokemon['name_ko']} ({pokemon['name_en']})",
        f"등급: {rarity_text}",
        f"포획률: {int(pokemon['catch_rate'] * 100)}%",
        f"상태: {owned}",
    ]

    if evo_line:
        lines.append(f"\n📊 진화: {evo_line}")

    if pokemon["evolution_method"] == "trade":
        lines.append("⚠️ 교환으로만 진화 가능!")

    if tmi:
        lines.append(f"\n💡 {tmi}")

    caption = "\n".join(lines)

    # Generate 16:9 card image
    card_buf = generate_card(pid, pokemon["name_ko"], pokemon["rarity"], pokemon["emoji"])
    await update.message.reply_photo(photo=card_buf, caption=caption, parse_mode="HTML")


async def _build_evo_chain(pokemon: dict) -> str:
    """Build evolution chain string like 파이리 → 리자드 → 리자몽"""
    chain = []

    # Go to the base form
    current = pokemon
    while current.get("evolves_from"):
        prev = await queries.get_pokemon(current["evolves_from"])
        if not prev:
            break
        current = prev

    # Walk forward
    while current:
        chain.append(current['name_ko'])
        if current.get("evolves_to"):
            nxt = await queries.get_pokemon(current["evolves_to"])
            current = nxt
        else:
            break

    return " → ".join(chain) if len(chain) > 1 else ""


# ============================================================
# Title List (all titles + how to unlock)
# ============================================================

async def title_list_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '칭호목록' command (DM) — show all titles and unlock conditions."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    await queries.ensure_user(
        user_id,
        update.effective_user.first_name or "트레이너",
        update.effective_user.username,
    )

    # Get user's unlocked titles
    unlocked = await queries.get_user_titles(user_id)
    unlocked_ids = {ut["title_id"] for ut in unlocked}

    lines = ["🏷️ 전체 칭호 목록\n"]

    # Group by category
    categories = {
        "📚 1세대 도감 (관동)": ["beginner", "collector", "trainer", "master", "champion", "living_dex"],
        "🌏 2세대 도감 (성도)": ["gen2_starter", "gen2_collector", "gen2_trainer", "gen2_master"],
        "💫 그랜드": ["grand_master"],
        "🐉 전설": ["legend_hunter"],
        "🎯 활동 기반": ["first_catch", "catch_master", "run_expert", "owl", "decisive", "love_fan", "diligent"],
        "💎 수집 특화": ["furry", "rare_hunter"],
        "🟣 마스터볼": ["masterball_rich"],
        "🤝 교환": ["trader"],
        "⚔️ 배틀": ["battle_first", "battle_fighter", "battle_champion", "battle_legend",
                    "battle_streak3", "battle_streak10", "battle_sweep", "partner_set"],
    }

    for cat_name, title_ids in categories.items():
        cat_lines = []
        for tid in title_ids:
            t_info = config.UNLOCKABLE_TITLES.get(tid)
            if not t_info:
                continue
            name, emoji, desc, _, _ = t_info
            status = "✅" if tid in unlocked_ids else "🔒"
            cat_lines.append(f"  {status} {emoji} {name} — {desc}")

        if cat_lines:
            lines.append(f"\n{cat_name}")
            lines.extend(cat_lines)

    total = len(config.UNLOCKABLE_TITLES)
    got = len(unlocked_ids)
    lines.append(f"\n\n해금: {got}/{total}개")
    lines.append("'칭호' 명령어로 장착할 수 있어요!")

    await update.message.reply_text("\n".join(lines))


# ============================================================
# Title Selection
# ============================================================

async def title_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '칭호' command (DM) — show unlocked titles and let user equip one."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    display_name = update.effective_user.first_name or "트레이너"
    await queries.ensure_user(user_id, display_name, update.effective_user.username)

    # Check and unlock any new titles first
    from utils.title_checker import check_and_unlock_titles
    await check_and_unlock_titles(user_id)

    unlocked = await queries.get_user_titles(user_id)
    user = await queries.get_user(user_id)
    current_title = user.get("title", "") if user else ""

    if not unlocked:
        await update.message.reply_text(
            "🏷️ 아직 해금된 칭호가 없습니다!\n\n"
            "포켓몬을 잡고, 활동하면 칭호가 해금돼요.\n"
            "예: 첫 포획, 도감 15종, 잡기 실패 50회 등"
        )
        return

    lines = ["🏷️ 내 칭호 목록\n"]

    buttons = []
    for ut in unlocked:
        tid = ut["title_id"]
        t_info = config.UNLOCKABLE_TITLES.get(tid)
        if not t_info:
            continue
        name, emoji, desc, _, _ = t_info
        equipped = " ✅" if name == current_title else ""
        lines.append(f"{emoji} {name}{equipped} — {desc}")
        btn_label = f"{'✅ ' if name == current_title else ''}{emoji} {name}"
        buttons.append(InlineKeyboardButton(btn_label, callback_data=f"title_{tid}"))

    # Add "remove title" button
    no_title_mark = " ✅" if not current_title else ""
    lines.append(f"\n🚫 칭호 없음{no_title_mark}")
    buttons.append(InlineKeyboardButton(f"{'✅ ' if not current_title else ''}🚫 해제", callback_data="title_none"))

    # 2 buttons per row
    keyboard = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
    markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "\n".join(lines) + "\n\n⬇️ 장착할 칭호를 선택하세요:",
        reply_markup=markup,
    )


async def title_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle title selection callback."""
    query = update.callback_query
    if not query or not query.data.startswith("title_"):
        return

    await query.answer()
    user_id = query.from_user.id
    title_id = query.data.replace("title_", "")

    if title_id == "none":
        await queries.equip_title(user_id, "", "")
        await query.edit_message_text("🚫 칭호를 해제했습니다.")
        return

    # Check if user has this title
    if not await queries.has_title(user_id, title_id):
        await query.edit_message_text("❌ 해금되지 않은 칭호입니다.")
        return

    t_info = config.UNLOCKABLE_TITLES.get(title_id)
    if not t_info:
        return

    name, emoji, desc, _, _ = t_info
    await queries.equip_title(user_id, name, emoji)
    await query.edit_message_text(f"✅ 칭호 장착: 「{emoji} {name}」\n\n채팅방에서 이름 옆에 표시됩니다!")


# ============================================================
# Status (상태창) — DM only
# ============================================================

async def status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '상태창' command (DM) — show user's full status overview."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    display_name = update.effective_user.first_name or "트레이너"
    await queries.ensure_user(user_id, display_name, update.effective_user.username)

    from database import battle_queries as bq
    from utils.battle_calc import calc_battle_stats, format_stats_line, format_power, calc_power, EVO_STAGE_MAP
    from models.pokemon_skills import POKEMON_SKILLS
    from models.pokemon_base_stats import POKEMON_BASE_STATS

    user = await queries.get_user(user_id)
    pokemon_list = await queries.get_user_pokemon_list(user_id)
    partner = await bq.get_partner(user_id)
    team = await bq.get_battle_team(user_id)
    battle_stats = await bq.get_battle_stats(user_id)
    master_balls = user.get("master_balls", 0) if user else 0
    bp = battle_stats.get("battle_points", 0)

    # 칭호
    title = user.get("title", "") if user else ""
    title_emoji = user.get("title_emoji", "") if user else ""
    title_text = f"「{title_emoji} {title}」" if title else "없음"

    lines = [f"📋 {display_name}님의 상태창\n"]

    # 기본 정보
    lines.append(f"🏷️ 칭호: {title_text}")
    lines.append(f"🔮 마스터볼: {master_balls}개")
    lines.append(f"⚔️ BP: {bp}")
    lines.append(f"📦 보유 포켓몬: {len(pokemon_list)}마리")

    # 도감 수
    unique_ids = {p["pokemon_id"] for p in pokemon_list}
    shiny_count = sum(1 for p in pokemon_list if p.get("is_shiny"))
    lines.append(f"📖 도감: {len(unique_ids)}/251종")
    if shiny_count > 0:
        lines.append(f"✨ 이로치: {shiny_count}마리")

    # 배틀 전적
    wins = battle_stats.get("battle_wins", 0)
    losses = battle_stats.get("battle_losses", 0)
    total = wins + losses
    win_rate = f"{wins / total * 100:.0f}%" if total > 0 else "-"
    best = battle_stats.get("best_streak", 0)
    lines.append(f"\n⚔️ 배틀 전적: {wins}승 {losses}패 (승률 {win_rate})")
    if best > 0:
        lines.append(f"🔥 최고 연승: {best}연승")

    # 파트너
    lines.append("")
    if partner:
        evo = EVO_STAGE_MAP.get(partner["pokemon_id"], 3)
        stats = calc_battle_stats(
            partner["rarity"], partner["stat_type"], partner["friendship"], evo_stage=evo,
            iv_hp=partner.get("iv_hp"), iv_atk=partner.get("iv_atk"),
            iv_def=partner.get("iv_def"), iv_spa=partner.get("iv_spa"),
            iv_spdef=partner.get("iv_spdef"), iv_spd=partner.get("iv_spd"),
        )
        base = calc_battle_stats(partner["rarity"], partner["stat_type"], partner["friendship"], evo_stage=evo)
        tb = type_badge(partner["pokemon_id"], partner["pokemon_type"])
        pbs = POKEMON_BASE_STATS.get(partner["pokemon_id"])
        if pbs:
            type_name = "/".join(config.TYPE_NAME_KO.get(t, t) for t in pbs[-1])
        else:
            type_name = config.TYPE_NAME_KO.get(partner["pokemon_type"], "")
        skill = POKEMON_SKILLS.get(partner["pokemon_id"], ("몸통박치기", 1.2))
        lines.append(f"🤝 파트너: {tb} {partner['name_ko']}  {type_name}  ⚡{format_power(stats, base)}")
        lines.append(f"   ❤️ 친밀도: {hearts_display(partner['friendship'])}")
        lines.append(f"   📊 {format_stats_line(stats, base)}")
        lines.append(f"   💥 기술: {skill[0]}")
    else:
        lines.append("🤝 파트너: 미지정 ('파트너' 명령어로 설정)")

    # 팀
    active_num = await bq.get_active_team_number(user_id)
    team2 = await bq.get_battle_team(user_id, 2)
    lines.append("")
    if team:
        lines.append(f"👥 배틀팀 {active_num} ({len(team)}/6)")
        total_power = 0
        total_base_power = 0
        for i, t in enumerate(team, 1):
            evo = EVO_STAGE_MAP.get(t["pokemon_id"], 3)
            stats = calc_battle_stats(
                t["rarity"], t["stat_type"], t["friendship"], evo_stage=evo,
                iv_hp=t.get("iv_hp"), iv_atk=t.get("iv_atk"),
                iv_def=t.get("iv_def"), iv_spa=t.get("iv_spa"),
                iv_spdef=t.get("iv_spdef"), iv_spd=t.get("iv_spd"),
            )
            tbase = calc_battle_stats(t["rarity"], t["stat_type"], t["friendship"], evo_stage=evo)
            total_power += calc_power(stats)
            total_base_power += calc_power(tbase)
            skill = POKEMON_SKILLS.get(t["pokemon_id"], ("몸통박치기", 1.2))
            ttb = type_badge(t["pokemon_id"], t.get("pokemon_type"))
            lines.append(f"  {i}. {ttb} {t['name_ko']}  💥{skill[0]}  ⚡{format_power(stats, tbase)}")
        iv_diff = total_power - total_base_power
        total_tag = f"{total_power}(+{iv_diff})" if iv_diff > 0 else str(total_power)
        lines.append(f"  💪 팀 전투력: {total_tag}")
        if team2:
            lines.append(f"  (팀2 등록됨: {len(team2)}마리)")
    else:
        lines.append("👥 배틀팀: 미등록 ('팀등록' 명령어로 설정)")

    # 아이템
    arcade_tickets = await queries.get_arcade_tickets(user_id)
    hyper_balls = await queries.get_hyper_balls(user_id)
    if arcade_tickets > 0 or hyper_balls > 0:
        lines.append("")
    if arcade_tickets > 0:
        lines.append(f"🎮 아케이드 티켓: {arcade_tickets}개")
    if hyper_balls > 0:
        lines.append(f"🔵 하이퍼볼: {hyper_balls}개")

    # DM 메뉴 키보드
    menu_keyboard = ReplyKeyboardMarkup(
        [
            ["📋 상태창", "📖 도감"],
            ["📦 내포켓몬", "🤝 파트너"],
            ["⚔️ 팀1", "⚔️ 팀2", "팀등록"],
            ["🏪 상점", "🏆 배틀전적", "티어"],
            ["🏷️ 칭호", "📋 칭호목록"],
            ["상성", "도움말"],
        ],
        resize_keyboard=True,
        input_field_placeholder="명령어를 선택하세요",
    )

    await update.message.reply_text("\n".join(lines), reply_markup=menu_keyboard, parse_mode="HTML")


# ============================================================
# IV Appraisal (감정)
# ============================================================

async def appraisal_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '감정 [이름/번호]' command — show Pokemon IV stats."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    await queries.ensure_user(
        user_id,
        update.effective_user.first_name or "트레이너",
        update.effective_user.username,
    )

    text = update.message.text or ""
    index = parse_number(text)
    name_arg = parse_name_arg(text)

    pokemon = None
    if index is not None:
        pokemon = await queries.get_user_pokemon_by_index(user_id, index)
    elif name_arg:
        pokemon = await queries.get_user_pokemon_by_name(user_id, name_arg)
    else:
        await update.message.reply_text("사용법: 감정 [이름 또는 번호]\n예: 감정 피카츄, 감정 3")
        return

    if not pokemon:
        query = index if index is not None else name_arg
        await update.message.reply_text(
            f"'{query}' 포켓몬을 찾을 수 없습니다.\n내포켓몬 으로 목록을 확인하세요."
        )
        return

    # Read IVs
    ivs = {
        "HP": pokemon.get("iv_hp"),
        "ATK": pokemon.get("iv_atk"),
        "DEF": pokemon.get("iv_def"),
        "SPA": pokemon.get("iv_spa"),
        "SPDEF": pokemon.get("iv_spdef"),
        "SPD": pokemon.get("iv_spd"),
    }

    total = iv_total(
        ivs["HP"], ivs["ATK"], ivs["DEF"],
        ivs["SPA"], ivs["SPDEF"], ivs["SPD"],
    )
    grade, _ = config.get_iv_grade(total)
    pct = round(total / 186 * 100, 1)

    # Build display
    shiny = "✨" if pokemon.get("is_shiny") else ""
    rb = rarity_badge(pokemon.get("rarity", "common"))
    name = pokemon["name_ko"]

    stat_labels = {
        "HP": "HP   ", "ATK": "공격 ", "DEF": "방어 ",
        "SPA": "특공 ", "SPDEF": "특방 ", "SPD": "스피드",
    }

    lines = [f"📋 {shiny}{rb} {name} 감정 결과\n"]
    max_iv = config.IV_MAX  # 31

    for key in ("HP", "ATK", "DEF", "SPA", "SPDEF", "SPD"):
        v = ivs[key] if ivs[key] is not None else 15
        label = stat_labels[key]
        filled = round(v / max_iv * 6)
        bar = "█" * filled + "░" * (6 - filled)
        # Highlight perfect (31) or near-perfect (28+)
        if v >= 28:
            mark = " ★"
        elif v <= 5:
            mark = " ✗"
        else:
            mark = ""
        lines.append(f"{label} {bar} {v}/{max_iv}{mark}")

    lines.append(f"\n총합: {total}/186 ({pct}%)")
    lines.append(f"등급: {grade}")

    # Grade flavor text
    flavor = {
        "S": "이 포켓몬은 최상급 개체입니다!",
        "A": "매우 뛰어난 개체입니다.",
        "B": "괜찮은 개체입니다.",
        "C": "평범한 개체입니다.",
        "D": "개체값이 낮습니다...",
    }
    lines.append(flavor.get(grade, ""))

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


# ============================================================
# Type Chart (상성표)
# ============================================================

async def type_chart_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '상성 [타입]' command — show type effectiveness."""
    if not update.effective_user or not update.message:
        return

    text = update.message.text or ""
    name_arg = parse_name_arg(text)

    if name_arg:
        # Specific type detail
        # Find type by Korean name or English key
        target_type = None
        for eng, ko in config.TYPE_NAME_KO.items():
            if name_arg == ko or name_arg.lower() == eng:
                target_type = eng
                break
        if not target_type:
            type_list = " ".join(f"{_type_emoji(t)}{config.TYPE_NAME_KO[t]}" for t in config.TYPE_ADVANTAGE)
            await update.message.reply_text(f"'{name_arg}' 타입을 찾을 수 없습니다.\n\n사용 가능: {type_list}", parse_mode="HTML")
            return

        te = _type_emoji(target_type)
        ko = config.TYPE_NAME_KO.get(target_type, target_type)

        # Offense: what this type is strong against
        strong = config.TYPE_ADVANTAGE.get(target_type, [])
        # Offense: what this type is immune to (hits for 0.3x)
        immune_vs = config.TYPE_IMMUNITY.get(target_type, [])

        # Defense: what is strong against this type
        weak_to = []
        immune_from = []
        for atk_type, adv_list in config.TYPE_ADVANTAGE.items():
            if target_type in adv_list:
                weak_to.append(atk_type)
        for atk_type, imm_list in config.TYPE_IMMUNITY.items():
            if target_type in imm_list:
                immune_from.append(atk_type)

        def fmt(types):
            if not types:
                return "없음"
            return " ".join(f"{_type_emoji(t)}{config.TYPE_NAME_KO.get(t, t)}" for t in types)

        lines = [
            f"{te} {ko} 타입 상성\n",
            f"⚔️ 공격 시 효과적 (1.3x):",
            f"  {fmt(strong)}",
        ]
        if immune_vs:
            lines.append(f"\n🚫 공격 시 면역 (0.3x):")
            lines.append(f"  {fmt(immune_vs)}")
        lines.append(f"\n🛡️ 방어 시 약점 (1.3x 피해):")
        lines.append(f"  {fmt(weak_to)}")
        if immune_from:
            lines.append(f"\n🛡️ 방어 시 면역 (0.3x 피해):")
            lines.append(f"  {fmt(immune_from)}")

        await update.message.reply_text("\n".join(lines), parse_mode="HTML")
    else:
        # Full chart summary
        lines = ["⚔️ 타입 상성표\n"]
        for atk_type, adv_list in config.TYPE_ADVANTAGE.items():
            if not adv_list:
                continue
            te = _type_emoji(atk_type)
            ko = config.TYPE_NAME_KO.get(atk_type, atk_type)
            targets = " ".join(f"{_type_emoji(t)}{config.TYPE_NAME_KO.get(t, t)}" for t in adv_list)
            lines.append(f"{te}{ko} → {targets}")
        lines.append(f"\n💡 상성 [타입] 으로 상세 보기\n예: 상성 불꽃")
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")
