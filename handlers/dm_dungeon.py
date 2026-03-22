"""Dungeon roguelike handler — DM only."""

import asyncio
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import config

from database import queries, item_queries, title_queries
from database import dungeon_queries as dq
from database import camp_queries as cq
from services import dungeon_service as ds
from utils.battle_calc import calc_battle_stats, calc_power, get_normalized_base_stats, EVO_STAGE_MAP, iv_total
from utils.helpers import icon_emoji, shiny_emoji, rarity_badge, _type_emoji
from utils.i18n import t, get_user_lang, poke_name

logger = logging.getLogger(__name__)

PAGE_SIZE = 8
_dungeon_locks: set[int] = set()


# ══════════════════════════════════════════════════════════
# 유틸리티
# ══════════════════════════════════════════════════════════

def _type_name(lang: str, type_key: str) -> str:
    """Get translated type name."""
    return t(lang, f"type.{type_key}")


async def _send_fresh(query, context, user_id: int, text: str, reply_markup=None, photo=None):
    """이전 메시지 삭제 후 새 메시지 전송 (항상 최하단 유지)."""
    st = _state(context)
    # 이전 메시지 삭제 시도
    old_msg_id = st.get("msg_id")
    if old_msg_id:
        try:
            await context.bot.delete_message(chat_id=user_id, message_id=old_msg_id)
        except Exception:
            pass
    # 이미지 메시지도 삭제
    old_photo_id = st.pop("photo_msg_id", None)
    if old_photo_id:
        try:
            await context.bot.delete_message(chat_id=user_id, message_id=old_photo_id)
        except Exception:
            pass
    # 이미지/GIF 전송
    if photo:
        name = getattr(photo, "name", "")
        if name.endswith(".gif"):
            photo_msg = await context.bot.send_animation(
                chat_id=user_id, animation=photo,
            )
        else:
            photo_msg = await context.bot.send_photo(
                chat_id=user_id, photo=photo, parse_mode="HTML",
            )
        st["photo_msg_id"] = photo_msg.message_id
    # 텍스트 메시지 전송
    msg = await context.bot.send_message(
        chat_id=user_id, text=text, reply_markup=reply_markup, parse_mode="HTML"
    )
    st["msg_id"] = msg.message_id
    return msg


def _hp_bar(current: int, maximum: int, length: int = 10) -> str:
    ratio = max(0, min(1, current / maximum)) if maximum > 0 else 0
    filled = int(ratio * length)
    return "█" * filled + "░" * (length - filled)


def _state(context) -> dict:
    return context.user_data.setdefault("dungeon", {})


def _get_pokemon_cost(rarity: str) -> int:
    return config.RANKED_COST.get(rarity, 1)


async def _get_sub_tier(user_id: int) -> str | None:
    try:
        from services.subscription_service import get_user_tier
        return await get_user_tier(user_id)
    except Exception as e:
        logger.error(f"_get_sub_tier failed for {user_id}: {e}")
        return None


# ══════════════════════════════════════════════════════════
# 메인 입장 핸들러
# ══════════════════════════════════════════════════════════

async def dungeon_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """DM: '던전' → 입장 화면."""
    if not update.effective_user or not update.message:
        return
    if update.effective_chat.type != "private":
        return

    user_id = update.effective_user.id
    lang = await get_user_lang(user_id)
    display_name = update.effective_user.first_name or t(lang, "common.trainer")
    await queries.ensure_user(user_id, display_name, update.effective_user.username)

    # 진행 중 런 확인
    active = await dq.get_active_run(user_id)
    if active:
        st = _state(context)
        st["run_id"] = active["id"]
        text, kb = await _build_resume_screen(user_id, active, lang)
        msg = await update.message.reply_text(text, reply_markup=kb, parse_mode="HTML")
        st["msg_id"] = msg.message_id
        return

    text, kb = await _build_entry_screen(user_id, lang)
    st = _state(context)
    msg = await update.message.reply_text(text, reply_markup=kb, parse_mode="HTML")
    st["msg_id"] = msg.message_id
    st.pop("run_id", None)


async def _build_entry_screen(user_id: int, lang: str | None = None) -> tuple[str, InlineKeyboardMarkup]:
    if lang is None:
        lang = await get_user_lang(user_id)

    tickets = await dq.get_dungeon_tickets(user_id)
    best = await dq.get_user_best_floor(user_id)
    theme = ds.get_today_theme()
    sub_tier = await _get_sub_tier(user_id)

    adv_types = " / ".join(_type_emoji(tp) + _type_name(lang, tp) for tp in theme["advantage"])
    theme_types = " / ".join(_type_emoji(tp) + _type_name(lang, tp) for tp in theme["types"])

    CASTLE = icon_emoji("container")
    TICKET = icon_emoji("stationery")
    CROWN = icon_emoji("crown")
    FOOT = icon_emoji("footsteps")
    BOLT = icon_emoji("bolt")

    daily_count = await dq.get_daily_run_count(user_id)
    daily_max = config.DUNGEON_MAX_DAILY_RUNS.get(sub_tier or "free", 3)
    daily_left = max(0, daily_max - daily_count)

    # 조각 타입 표시
    field_key = config.DUNGEON_THEME_TO_FIELD.get(theme["name"], "forest")
    field_info = config.CAMP_FIELDS.get(field_key, {})
    field_name = field_info.get("name", field_key)
    field_emoji = field_info.get("emoji", "🧩")

    # 시즌 정보
    season_key = dq._current_season_key()
    rank = await dq.get_user_rank(user_id)
    rank_text = f" (현재 {rank}위)" if rank else ""

    text = (
        f"{CASTLE} <b>{t(lang, 'dungeon.title')}</b>\n"
        f"📅 시즌 {season_key}{rank_text}\n\n"
        f"{TICKET} {t(lang, 'dungeon.tickets_info', tickets=tickets, left=daily_left, max=daily_max)}\n"
        f"{CROWN} {t(lang, 'dungeon.best_floor', floor=best)}\n\n"
        f"{FOOT} {t(lang, 'dungeon.today_theme', emoji=theme['emoji'], name=theme['name'])}\n"
        f"   {t(lang, 'dungeon.enemy_types_appear', types=theme_types)}\n"
        f"   {BOLT} {t(lang, 'dungeon.advantage_types', types=adv_types)}\n"
        f"   🧩 {t(lang, 'dungeon.fragment_reward', field_emoji=field_emoji, field=field_name)}\n"
    )

    buttons = []
    # BP 구매 정보
    bp_cost = config.DUNGEON_TICKET_BP_COST.get(sub_tier or "free", 50)
    bought = await dq.get_bought_today(user_id)
    buy_limit = config.DUNGEON_DAILY_BUY_LIMIT.get(sub_tier or "free", 3)
    can_buy = bought < buy_limit

    if tickets > 0 and daily_left > 0:
        buttons.append([InlineKeyboardButton(t(lang, "dungeon.btn_select_pokemon"), callback_data=f"dg_list_{user_id}_all_0")])
    elif daily_left == 0:
        # 횟수 소진
        buttons.append([InlineKeyboardButton(f"⚠️ 오늘 횟수 소진 ({daily_max}/{daily_max})", callback_data=f"dg_noop_{user_id}")])
    else:
        # 입장권 0, 횟수 남아있음 → 구매 유도
        if can_buy:
            buttons.append([InlineKeyboardButton(
                f"🎫 입장권 구매하고 입장 ({bp_cost}BP)",
                callback_data=f"dg_buy_{user_id}"
            )])
        else:
            buttons.append([InlineKeyboardButton(f"🎫 오늘 구매 한도 소진 ({buy_limit}/{buy_limit})", callback_data=f"dg_noop_{user_id}")])

    # BP 구매 (입장권 있어도 추가 구매 가능하도록)
    if tickets > 0 and can_buy:
        buttons.append([InlineKeyboardButton(
            t(lang, "dungeon.btn_buy_ticket", cost=bp_cost, bought=bought, limit=buy_limit),
            callback_data=f"dg_buy_{user_id}"
        )])

    buttons.append([
        InlineKeyboardButton(t(lang, "dungeon.btn_ranking"), callback_data=f"dg_rank_{user_id}"),
        InlineKeyboardButton(t(lang, "dungeon.btn_close"), callback_data=f"dg_close_{user_id}"),
    ])

    return text, InlineKeyboardMarkup(buttons)


async def _build_resume_screen(user_id: int, run: dict, lang: str | None = None) -> tuple[str, InlineKeyboardMarkup]:
    if lang is None:
        lang = await get_user_lang(user_id)

    theme_info = ds.get_today_theme()
    hp_bar = _hp_bar(run["current_hp"], run["max_hp"])
    hp_pct = int(run["current_hp"] / run["max_hp"] * 100) if run["max_hp"] else 0
    shiny = shiny_emoji() + " " if run["is_shiny"] else ""
    buffs = run.get("buffs_json", [])
    CASTLE = icon_emoji("container")
    FOOT = icon_emoji("footsteps")
    HEART = icon_emoji("pokecenter")
    SKILL = icon_emoji("skill")
    rb = rarity_badge(run.get("rarity", "common"))

    # 보유 버프 요약
    buff_summary = ""
    if buffs:
        for b in buffs:
            blv = b.get("lv", 1)
            buff_summary += f"  {ds.LV_EMOJI.get(blv, '⬜')} {b.get('name', '?')} Lv.{blv}\n"
    # 시너지
    active_syn = ds._get_active_synergies(buffs)
    syn_line = ""
    if active_syn:
        syn_line = "\n✨ " + " / ".join(f"{s['emoji']}{s['name']}" for s in active_syn)

    text = (
        f"{CASTLE} <b>{t(lang, 'dungeon.in_progress')}</b>\n\n"
        f"{FOOT} {t(lang, 'dungeon.floor_info', floor=run['floor_reached'])} | {theme_info['emoji']} {run['theme']}\n"
        f"{rb} {shiny}{run['pokemon_name']} [{run['iv_grade']}]\n"
        f"{HEART} {hp_bar} {hp_pct}%\n"
        f"{SKILL} {t(lang, 'dungeon.buffs_count', count=len(buffs))}{syn_line}\n"
    )
    if buff_summary:
        text += buff_summary
    buttons = [
        [InlineKeyboardButton(t(lang, "dungeon.btn_next_floor"), callback_data=f"dg_go_{user_id}")],
        [InlineKeyboardButton(t(lang, "dungeon.btn_give_up"), callback_data=f"dg_quit_{user_id}")],
    ]
    return text, InlineKeyboardMarkup(buttons)


# ══════════════════════════════════════════════════════════
# 포켓몬 선택 UI
# ══════════════════════════════════════════════════════════

async def _build_pokemon_list(user_id: int, filter_key: str, page: int, theme: dict, lang: str | None = None) -> tuple[str, InlineKeyboardMarkup]:
    """포켓몬 선택 리스트 빌드."""
    if lang is None:
        lang = await get_user_lang(user_id)

    pokemon_list = await queries.get_user_pokemon_list(user_id)

    # 필터링
    if filter_key == "rec":
        adv_set = set(theme["advantage"])
        from models.pokemon_base_stats import POKEMON_BASE_STATS
        pokemon_list = [p for p in pokemon_list if _pokemon_has_type(p, adv_set)]
    elif filter_key == "shiny":
        pokemon_list = [p for p in pokemon_list if p.get("is_shiny")]
    elif filter_key == "sgrade":
        pokemon_list = [p for p in pokemon_list if _iv_grade(p) == "S"]
    elif filter_key == "fav":
        pokemon_list = [p for p in pokemon_list if p.get("is_favorite")]
    elif filter_key != "all":
        # 타입 필터
        pokemon_list = [p for p in pokemon_list if _pokemon_has_type(p, {filter_key})]

    # 정렬: 전투력 순
    for p in pokemon_list:
        p["_power"] = _quick_power(p)
    pokemon_list.sort(key=lambda x: x["_power"], reverse=True)

    total = len(pokemon_list)
    max_page = max(0, (total - 1) // PAGE_SIZE)
    page = min(page, max_page)

    start = page * PAGE_SIZE
    page_items = pokemon_list[start:start + PAGE_SIZE]

    # 필터 탭
    filter_buttons = []
    filters = [("all", t(lang, "dungeon.filter_all")), ("rec", t(lang, "dungeon.filter_rec"))]
    for tp in theme["advantage"]:
        filters.append((tp, config.TYPE_EMOJI.get(tp, "") + _type_name(lang, tp)[:2]))
    filters.extend([("shiny", t(lang, "dungeon.filter_shiny")), ("sgrade", t(lang, "dungeon.filter_sgrade"))])

    row = []
    for fk, label in filters:
        prefix = "▸" if fk == filter_key else ""
        row.append(InlineKeyboardButton(f"{prefix}{label}", callback_data=f"dg_flt_{user_id}_{fk}"))
        if len(row) >= 4:
            filter_buttons.append(row)
            row = []
    if row:
        filter_buttons.append(row)

    # 포켓몬 버튼
    poke_buttons = []
    for p in page_items:
        shiny = "✨" if p.get("is_shiny") else ""
        grade = _iv_grade(p)
        type_e = config.TYPE_EMOJI.get(p.get("pokemon_type", "normal"), "")
        power = p["_power"]
        p_name = poke_name(p, lang)
        label = f"{shiny}{p_name} {grade}{type_e} {power}"
        poke_buttons.append([InlineKeyboardButton(
            label, callback_data=f"dg_sel_{user_id}_{p['id']}"
        )])

    # 페이지네이션
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀", callback_data=f"dg_list_{user_id}_{filter_key}_{page-1}"))
    nav.append(InlineKeyboardButton(f"{page+1}/{max_page+1}", callback_data=f"dg_noop_{user_id}"))
    if page < max_page:
        nav.append(InlineKeyboardButton("▶", callback_data=f"dg_list_{user_id}_{filter_key}_{page+1}"))

    buttons = filter_buttons + poke_buttons + [nav]
    buttons.append([InlineKeyboardButton(t(lang, "dungeon.btn_back"), callback_data=f"dg_back_{user_id}")])

    theme_name = f"{theme['emoji']} {theme['name']}"
    text = f"{icon_emoji('container')} {t(lang, 'dungeon.select_pokemon_header', theme=theme_name, count=total)}"

    return text, InlineKeyboardMarkup(buttons)


def _pokemon_has_type(p: dict, type_set: set[str]) -> bool:
    from models.pokemon_base_stats import POKEMON_BASE_STATS
    entry = POKEMON_BASE_STATS.get(p.get("pokemon_id"))
    if entry and len(entry) > 6:
        return bool(set(entry[6]) & type_set)
    return p.get("pokemon_type", "normal") in type_set


def _iv_grade(p: dict) -> str:
    total = iv_total(
        p.get("iv_hp"), p.get("iv_atk"), p.get("iv_def"),
        p.get("iv_spa"), p.get("iv_spdef"), p.get("iv_spd")
    )
    grade, _ = config.get_iv_grade(total)
    return grade


def _quick_power(p: dict) -> int:
    """빠른 전투력 계산."""
    base_kw = get_normalized_base_stats(p["pokemon_id"]) or {}
    evo = EVO_STAGE_MAP.get(p["pokemon_id"], 3)
    friendship = 7 if p.get("is_shiny") else 5
    stats = calc_battle_stats(
        p["rarity"], p.get("stat_type", "balanced"), friendship, evo,
        p.get("iv_hp"), p.get("iv_atk"), p.get("iv_def"),
        p.get("iv_spa"), p.get("iv_spdef"), p.get("iv_spd"),
        **base_kw,
    )
    return calc_power(stats)


# ══════════════════════════════════════════════════════════
# 배틀 + 버프 선택 UI
# ══════════════════════════════════════════════════════════

async def _process_floor(query, context, user_id: int, run: dict):
    """다음 층 배틀 진행 — 현재는 자동배틀, 턴제는 추후 활성화."""
    USE_TURN_BASED = True

    lang = await get_user_lang(user_id)
    floor = run["floor_reached"] + 1
    theme_data = None
    for td in config.DUNGEON_THEMES:
        if td["name"] == run["theme"]:
            theme_data = td
            break
    if not theme_data:
        theme_data = ds.get_today_theme()

    # 플레이어 스탯
    pokemon = await _load_pokemon(run["pokemon_instance_id"])
    if not pokemon:
        await dq.abandon_run(run["id"])
        await dq.add_dungeon_tickets(user_id, 1)
        await _send_fresh(query, context, user_id, t(lang, "dungeon.pokemon_error"))
        return

    player_stats, player_types = ds.build_player_stats(pokemon)

    # 적 생성 (코스트 보정 적용)
    enemy = ds.generate_enemy(floor, theme_data, player_rarity=pokemon["rarity"])

    buffs = run.get("buffs_json", [])
    if isinstance(buffs, str):
        import json
        buffs = json.loads(buffs)

    if USE_TURN_BASED:
        await _process_floor_turnbased(query, context, user_id, run, floor, theme_data,
                                        pokemon, player_stats, player_types, enemy, buffs)
        return

    # ══ 자동배틀 (기존) ══
    # 로그라이크 1턴 스탯 적용
    rogue_mults = ds.get_rogue_stat_mults(buffs)
    if rogue_mults:
        for stat, mult in rogue_mults.items():
            if stat in player_stats:
                player_stats[stat] = int(player_stats[stat] * mult)

    result = ds.resolve_dungeon_battle(
        player_stats, player_types, pokemon["rarity"], enemy, buffs,
        current_hp=run["current_hp"], max_hp=run["max_hp"],
    )
    remaining_hp = result["remaining_hp"]
    won = result["won"]

    buffs = ds.consume_rogue_buffs(buffs)
    if result.get("revive_used"):
        buffs = [b for b in buffs if b.get("id") != "revive"]
        if not any(b.get("id") == "_revive_consumed" for b in buffs):
            buffs.append({"id": "_revive_consumed", "name": "", "lv": 0})

    if won:
        heal_rate = ds.get_floor_heal_rate(buffs)
        if heal_rate > 0:
            remaining_hp = min(run["max_hp"], remaining_hp + int(run["max_hp"] * heal_rate))
        await dq.update_run_progress(run["id"], floor, remaining_hp, buffs)

        hp_bar = _hp_bar(remaining_hp, run["max_hp"])
        hp_pct = int(remaining_hp / run["max_hp"] * 100) if run["max_hp"] else 0

        CHECK = icon_emoji("check")
        HEART = icon_emoji("pokecenter")
        SKILL = icon_emoji("skill")
        BATTLE = icon_emoji("battle")

        enemy_rb = rarity_badge(enemy["rarity"])
        enemy_types = " ".join(_type_emoji(tp) for tp in enemy.get("types", []))
        enemy_name = enemy.get("name_ko", "???")
        enemy_label = f"{enemy_rb}{enemy_name} {enemy_types}"
        if enemy["is_boss"]:
            enemy_label = t(lang, "dungeon.boss_label", name=enemy_label)
        elif enemy["is_elite"]:
            enemy_label = t(lang, "dungeon.elite_label", name=enemy_label)

        battle_lines = f"{BATTLE} {t(lang, 'dungeon.battle_vs', enemy=enemy_label)}\n"
        battle_lines += f"  {t(lang, 'dungeon.battle_damage_dealt', dmg=result['total_damage_dealt'])}"
        if result["total_damage_taken"] > 0:
            battle_lines += f" | {t(lang, 'dungeon.battle_damage_taken', dmg=result['total_damage_taken'])}"
        battle_lines += f" | {t(lang, 'dungeon.battle_turns', n=result['turns'])}"

        if result.get("type_display"):
            battle_lines += f"\n  🔮 상성: {result['type_display']}"

        hl = result.get("highlights", {})
        hl_parts = []
        if hl.get("crit"): hl_parts.append(f"💥크리 {hl['crit']}회")
        if hl.get("skill"): hl_parts.append(f"⚡스킬 {hl['skill']}회")
        if hl.get("dodge"): hl_parts.append(f"💨회피 {hl['dodge']}회")
        if hl.get("double"): hl_parts.append(f"✌️이중타격 {hl['double']}회")
        if hl_parts:
            battle_lines += f"\n  {' · '.join(hl_parts)}"

        effect_lines = ""
        if result.get("revive_used"):
            effect_lines += "\n  💫 부활의 깃털 발동!"
        if hl.get("lifesteal_heal", 0) > 0:
            effect_lines += f"\n  🩸 흡혈 +{hl['lifesteal_heal']}HP"
        heal_rate_val = ds.get_floor_heal_rate(buffs)
        if heal_rate_val > 0:
            effect_lines += f"\n  {t(lang, 'dungeon.floor_heal', hp=int(run['max_hp'] * heal_rate_val))}"

        buff_summary = ""
        for b in buffs:
            if b.get("id", "").startswith("_"): continue
            blv = b.get("lv", 1)
            buff_summary += f"  {ds.LV_EMOJI.get(blv, '⬜')} {b.get('name', '?')} Lv.{blv}\n"

        text = (
            f"{CHECK} {t(lang, 'dungeon.floor_victory', floor=floor)}\n"
            f"━━━━━━━━━━━━━━\n"
            f"{battle_lines}{effect_lines}\n\n"
            f"{HEART} {hp_bar} {hp_pct}%\n"
            f"{SKILL} {t(lang, 'dungeon.buffs_count', count=len([b for b in buffs if not b.get('id','').startswith('_')]))}\n"
        )
        if buff_summary:
            text += buff_summary

        cost = _get_pokemon_cost(pokemon["rarity"])
        st = _state(context)

        if ds.should_offer_buff(floor):
            choices = ds.generate_buff_choices(floor, buffs)
            st["buff_choices"] = choices
            if not choices:
                text += "\n\n🎲 <b>버프 슬롯 가득!</b>\n<i>랜덤 이벤트를 발동하시겠습니까?</i>"
                buttons = [
                    [InlineKeyboardButton("🎲 랜덤 이벤트!", callback_data=f"dg_rogue_{user_id}_roll")],
                    [InlineKeyboardButton("➡️ 지나가기", callback_data=f"dg_rogue_{user_id}_pass")],
                ]
                await _send_fresh(query, context, user_id, text, reply_markup=InlineKeyboardMarkup(buttons))
                return
            text += f"\n\n{icon_emoji('gotcha')} <b>{t(lang, 'dungeon.buff_select_title')}</b>"
            buttons = []
            for i, buff in enumerate(choices):
                lv = buff.get("lv", 1)
                lv_emoji = ds.LV_EMOJI.get(lv, "⬜")
                tag = t(lang, "dungeon.buff_tag_upgrade", **{"from": lv-1, "to": lv}) if buff.get("is_upgrade") else t(lang, "dungeon.buff_tag_new")
                buttons.append([InlineKeyboardButton(
                    f"{lv_emoji} {buff['name']} [{tag}] — {buff['desc']}",
                    callback_data=f"dg_buf_{user_id}_{i}"
                )])
            buttons.append([InlineKeyboardButton("➡️ 지나가기", callback_data=f"dg_skip_{user_id}")])
            await _send_fresh(query, context, user_id, text, reply_markup=InlineKeyboardMarkup(buttons))
        else:
            buttons = [
                [InlineKeyboardButton(t(lang, "dungeon.btn_next_floor"), callback_data=f"dg_go_{user_id}")],
                [InlineKeyboardButton(t(lang, "dungeon.btn_give_up"), callback_data=f"dg_quit_{user_id}")],
            ]
            await _send_fresh(query, context, user_id, text, reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await _finish_run(query, context, user_id, run, run["floor_reached"],
                          death_enemy=enemy.get("name_ko"), death_enemy_rarity=enemy.get("rarity"),
                          death_floor=floor, revive_used=result.get("revive_used", False))

async def _process_floor_turnbased(query, context, user_id, run, floor, theme_data,
                                    pokemon, player_stats, player_types, enemy, buffs):
    """턴제 전투 시작 (USE_TURN_BASED=True 시 호출)."""
    rogue_mults = ds.get_rogue_stat_mults(buffs)
    if rogue_mults:
        for stat, mult in rogue_mults.items():
            if stat in player_stats:
                player_stats[stat] = int(player_stats[stat] * mult)

    combat = ds.init_combat_state(
        player_stats, player_types, pokemon["rarity"],
        pokemon["pokemon_id"], enemy, buffs,
        current_hp=run["current_hp"], max_hp=run["max_hp"],
        floor=floor,
    )

    st = _state(context)
    if "pp_state" not in st:
        pp_max = combat["pp_max"]
        pp_list = [{"current": pp_max, "max": pp_max} for _ in combat["skills"]]
        st["pp_state"] = pp_list
    combat["pp"] = st["pp_state"]
    st["combat"] = combat

    await _show_battle_turn(query, context, user_id)


async def _show_battle_turn(query, context, user_id: int):
    """현재 전투 상태를 메시지로 표시 (edit 또는 새 메시지)."""
    lang = await get_user_lang(user_id)
    st = _state(context)
    combat = st.get("combat")
    if not combat:
        return

    floor = combat["floor"]
    turn = combat["turn"]
    enemy = combat["enemy"]
    e_hp = combat["e_hp"]
    e_max_hp = combat["e_max_hp"]
    p_hp = combat["p_hp"]
    p_max_hp = combat["p_max_hp"]
    skills = combat["skills"]
    pp = combat["pp"]
    e_intent = combat["e_intent"]

    # 적 정보
    enemy_rb = rarity_badge(enemy["rarity"])
    enemy_types = "/".join(_type_emoji(tp) for tp in enemy.get("types", []))
    enemy_name = enemy.get("name_ko", "???")
    boss_label = ""
    if enemy["is_boss"]:
        boss_label = "👑 BOSS — "
    elif enemy.get("is_elite"):
        boss_label = "⭐ ELITE — "

    e_hp_bar = _hp_bar(e_hp, e_max_hp)
    e_hp_pct = int(e_hp / e_max_hp * 100) if e_max_hp else 0
    p_hp_bar = _hp_bar(p_hp, p_max_hp)
    p_hp_pct = int(p_hp / p_max_hp * 100) if p_max_hp else 0

    # 적 의도 표시
    intent_warning = ds.get_intent_warning(e_intent, combat["p_types"])

    # 상성 팁
    type_hint = ds.get_type_hint(
        combat["p_types"], enemy.get("types", []),
        skills, combat["skill_type_mults"])

    # 분노 표시
    rage_text = "\n🔥 <b>분노 상태!</b> 공격력 1.5배" if combat.get("e_rage") else ""

    text = (
        f"━━ {floor}층{' [턴 ' + str(turn) + ']' if turn > 1 else ''} ━━\n"
        f"{boss_label}{enemy_rb}{enemy_name} ({enemy_types})\n"
        f"❤️ {e_hp_bar} {e_hp_pct}% ({e_hp}/{e_max_hp}){rage_text}\n\n"
        f"{intent_warning}\n\n"
        f"━━━━━━━━━━━━━━\n"
        f"❤️ {p_hp_bar} {p_hp_pct}% ({p_hp}/{p_max_hp})\n"
        f"{type_hint}\n"
    )

    # 보호막 표시
    if combat["p_shield"] > 0:
        text += f"🛡️ 보호막: {combat['p_shield']}\n"

    # 게으름 특성: 짝수 턴 빈둥빈둥
    is_truant = combat.get("is_truant", False)
    is_loaf_turn = is_truant and turn % 2 == 0

    if is_loaf_turn:
        text += "😴 <b>빈둥빈둥...</b> 이번 턴은 방어만 가능!\n"

    # 4버튼
    buttons = []
    if is_loaf_turn:
        # 빈둥빈둥 턴: 방어만
        buttons.append([InlineKeyboardButton("🛡️ 방어 (빈둥빈둥)", callback_data=f"dg_def_{user_id}")])
    else:
        row1 = [InlineKeyboardButton("⚔️ 일반공격", callback_data=f"dg_atk_{user_id}")]

        if len(skills) >= 1 and len(pp) >= 1:
            sk1 = skills[0]
            pp1 = pp[0]
            pp_text = f"{pp1['current']}/{pp1['max']}"
            label = f"{sk1['emoji']} {sk1['name']} {pp_text}"
            if pp1["current"] <= 0:
                label = f"❌ {sk1['name']} 0/{pp1['max']}"
            row1.append(InlineKeyboardButton(label, callback_data=f"dg_sk1_{user_id}"))
        buttons.append(row1)

        row2 = []
        if len(skills) >= 2 and len(pp) >= 2:
            sk2 = skills[1]
            pp2 = pp[1]
            pp_text = f"{pp2['current']}/{pp2['max']}"
            label = f"{sk2['emoji']} {sk2['name']} {pp_text}"
            if pp2["current"] <= 0:
                label = f"❌ {sk2['name']} 0/{pp2['max']}"
            row2.append(InlineKeyboardButton(label, callback_data=f"dg_sk2_{user_id}"))

        row2.append(InlineKeyboardButton("🛡️ 방어", callback_data=f"dg_def_{user_id}"))
        buttons.append(row2)

    # 포기 버튼
    buttons.append([InlineKeyboardButton("🏳️ 포기", callback_data=f"dg_quit_{user_id}")])

    await _send_fresh(query, context, user_id, text, reply_markup=InlineKeyboardMarkup(buttons))


async def _process_turn_action(query, context, user_id: int, action: str):
    """플레이어 행동 선택 → 턴 실행 → 결과 표시."""
    lang = await get_user_lang(user_id)
    st = _state(context)
    combat = st.get("combat")
    if not combat:
        await query.answer("전투 상태 없음", show_alert=True)
        return

    # PP 부족 체크
    if action == "skill1" and (len(combat["pp"]) < 1 or combat["pp"][0]["current"] <= 0):
        await query.answer("PP가 부족합니다! 일반공격을 사용하세요.", show_alert=True)
        return
    if action == "skill2" and (len(combat["pp"]) < 2 or combat["pp"][1]["current"] <= 0):
        await query.answer("PP가 부족합니다! 일반공격을 사용하세요.", show_alert=True)
        return

    # 턴 실행
    result = ds.resolve_turn(combat, action)

    # PP state 동기화 (런 전체 공유)
    st["pp_state"] = combat["pp"]

    # 턴 결과 텍스트
    floor = combat["floor"]
    turn = combat["turn"] - 1  # resolve_turn이 이미 +1 했음

    lines = [f"━━ {floor}층 [턴 {turn}] ━━"]
    if result["player_line"]:
        lines.append(f"⚔️ {result['player_line']}")
    if result["enemy_line"]:
        lines.append(f"🆚 {result['enemy_line']}")
    for extra in result.get("extra_lines", []):
        lines.append(extra)

    await query.answer()

    if result["floor_clear"]:
        # 층 클리어!
        await _handle_floor_clear(query, context, user_id, combat, result)
    elif result["player_dead"]:
        # 사망
        await _handle_player_death(query, context, user_id, combat, result)
    else:
        # 전투 계속 — 다음 턴 표시
        await _show_battle_turn(query, context, user_id)


async def _handle_floor_clear(query, context, user_id: int, combat: dict, turn_result: dict):
    """층 클리어 처리 — DB 저장 + 버프 선택 또는 다음 층."""
    lang = await get_user_lang(user_id)
    st = _state(context)
    floor = combat["floor"]
    buffs = combat["buffs"]
    remaining_hp = max(0, combat["p_hp"])
    max_hp = combat["p_max_hp"]

    # 로그라이크 1턴 버프 소모
    buffs = ds.consume_rogue_buffs(buffs)

    # 부활 사용 시 버프 제거 + 마커
    if combat.get("revive_used"):
        buffs = [b for b in buffs if b.get("id") != "revive"]
        if not any(b.get("id") == "_revive_consumed" for b in buffs):
            buffs.append({"id": "_revive_consumed", "name": "", "lv": 0})

    # 층간 회복 (기본 5% + 버프)
    base_heal = config.DUNGEON_BASE_FLOOR_HEAL
    heal_rate = base_heal + ds.get_floor_heal_rate(buffs)
    remaining_hp = min(max_hp, remaining_hp + int(max_hp * heal_rate))

    # DB 업데이트
    run = await dq.get_active_run(user_id)
    if run:
        await dq.update_run_progress(run["id"], floor, remaining_hp, buffs)

    # 전투 상태 클리어
    st.pop("combat", None)

    # 결과 화면
    hp_bar = _hp_bar(remaining_hp, max_hp)
    hp_pct = int(remaining_hp / max_hp * 100) if max_hp else 0

    CHECK = icon_emoji("check")
    HEART = icon_emoji("pokecenter")
    SKILL = icon_emoji("skill")

    # 전투 하이라이트
    hl = combat.get("highlights", {})
    hl_parts = []
    if hl.get("crit"):
        hl_parts.append(f"💥크리 {hl['crit']}회")
    if hl.get("special_used"):
        hl_parts.append(f"⚡스킬 {hl['special_used']}회")
    if hl.get("dodge"):
        hl_parts.append(f"💨회피 {hl['dodge']}회")
    if hl.get("defend_used"):
        hl_parts.append(f"🛡️방어 {hl['defend_used']}회")
    if hl.get("double"):
        hl_parts.append(f"✌️이중타격 {hl['double']}회")
    hl_text = " · ".join(hl_parts) if hl_parts else ""

    # PP 상태 표시
    pp_parts = []
    for i, sk in enumerate(combat.get("skills", [])):
        if i < len(st.get("pp_state", [])):
            pp_info = st["pp_state"][i]
            pp_parts.append(f"{sk['emoji']} {sk['name']} {pp_info['current']}/{pp_info['max']}")
    pp_text = " · ".join(pp_parts)

    # 특수 효과
    effect_lines = ""
    if combat.get("revive_used"):
        effect_lines += "\n  💫 부활의 깃털 발동! HP 30% 회복"
    if hl.get("lifesteal_heal", 0) > 0:
        effect_lines += f"\n  🩸 흡혈 +{hl['lifesteal_heal']}HP"
    if heal_rate > 0:
        effect_lines += f"\n  🌿 층간 회복 +{int(max_hp * heal_rate)}HP"

    text = (
        f"{CHECK} {floor}층 클리어!\n"
        f"━━━━━━━━━━━━━━\n"
        f"{hl_text}{effect_lines}\n"
        f"{HEART} {hp_bar} {hp_pct}% ({remaining_hp}/{max_hp})\n"
        f"{pp_text}\n"
    )

    # 존 프리뷰 (보스 클리어 시)
    if floor % 5 == 0 and floor < 50:
        run_data = await dq.get_active_run(user_id)
        theme_name = run_data.get("theme") if run_data else None
        theme_td = None
        if theme_name:
            for td in config.DUNGEON_THEMES:
                if td["name"] == theme_name:
                    theme_td = td
                    break
        if theme_td:
            zone_preview = ds.get_zone_preview(floor, theme_td)
            if zone_preview:
                text += zone_preview + "\n"

    # 버프 제공 (5층마다 = 보스)
    if ds.should_offer_buff(floor):
        choices = ds.generate_buff_choices(floor, buffs)
        st["buff_choices"] = choices

        if not choices:
            # 8버프 포화 → 로그라이크
            text += (
                f"\n🎲 <b>버프 슬롯 가득!</b>\n"
                f"<i>랜덤 이벤트를 발동하시겠습니까?</i>"
            )
            buttons = [
                [InlineKeyboardButton("🎲 랜덤 이벤트!", callback_data=f"dg_rogue_{user_id}_roll")],
                [InlineKeyboardButton("➡️ 지나가기", callback_data=f"dg_rogue_{user_id}_pass")],
            ]
            await _send_fresh(query, context, user_id, text, reply_markup=InlineKeyboardMarkup(buttons))
            return

        # PP 회복 버프 체크
        for b in buffs:
            if b.get("id") == "pp_recovery":
                pp_recover = b["effect"].get("rate", 2)
                for pp_info in st.get("pp_state", []):
                    pp_info["current"] = min(pp_info["max"], pp_info["current"] + pp_recover)
                text += f"\n🔮 PP 회복! +{pp_recover}\n"
                break

        text += f"\n{icon_emoji('gotcha')} <b>버프 선택</b>"
        buttons = []
        for i, buff in enumerate(choices):
            lv = buff.get("lv", 1)
            lv_emoji = ds.LV_EMOJI.get(lv, "⬜")
            if buff.get("is_upgrade"):
                tag = f"Lv.{lv-1}→{lv}"
            else:
                tag = "NEW"
            buttons.append([InlineKeyboardButton(
                f"{lv_emoji} {buff['name']} [{tag}] — {buff['desc']}",
                callback_data=f"dg_buf_{user_id}_{i}"
            )])
        buttons.append([InlineKeyboardButton("➡️ 지나가기", callback_data=f"dg_skip_{user_id}")])
        await _send_fresh(query, context, user_id, text, reply_markup=InlineKeyboardMarkup(buttons))
    else:
        # 버프 없이 다음 층
        buttons = [
            [InlineKeyboardButton(t(lang, "dungeon.btn_next_floor"), callback_data=f"dg_go_{user_id}")],
            [InlineKeyboardButton(t(lang, "dungeon.btn_give_up"), callback_data=f"dg_quit_{user_id}")],
        ]
        await _send_fresh(query, context, user_id, text, reply_markup=InlineKeyboardMarkup(buttons))


async def _handle_player_death(query, context, user_id: int, combat: dict, turn_result: dict):
    """플레이어 사망 처리."""
    st = _state(context)
    st.pop("combat", None)

    run = await dq.get_active_run(user_id)
    if run:
        enemy = combat.get("enemy", {})
        await _finish_run(
            query, context, user_id, run, run["floor_reached"],
            death_enemy=enemy.get("name_ko"),
            death_enemy_rarity=enemy.get("rarity"),
            death_floor=combat["floor"],
            revive_used=combat.get("revive_used", False),
        )


async def _finish_run(query, context, user_id: int, run: dict, final_floor: int,
                      battle_card=None, death_enemy=None, death_enemy_rarity=None, death_floor=None,
                      revive_used: bool = False):
    """런 종료 + 보상 정산."""
    lang = await get_user_lang(user_id)
    sub_tier = await _get_sub_tier(user_id)
    rewards = ds.calculate_rewards(final_floor, run["theme"], sub_tier)

    # DB 업데이트
    await dq.end_run(run["id"], final_floor, rewards["bp"], rewards["fragments"],
                     death_enemy=death_enemy, death_enemy_rarity=death_enemy_rarity, death_floor=death_floor)
    await dq.update_pokemon_record(user_id, run["pokemon_instance_id"], final_floor, run["theme"])
    is_new_record = await dq.update_user_best_floor(user_id, final_floor)

    # 보상 지급 (각각 try/except — 하나 실패해도 나머지 지급)
    reward_errors = []
    try:
        if rewards["bp"] > 0:
            await queries.add_battle_points(user_id, rewards["bp"])
    except Exception as e:
        reward_errors.append(f"BP: {e}")

    try:
        if rewards.get("tickets", 0) > 0:
            await dq.add_dungeon_tickets(user_id, rewards["tickets"])
    except Exception as e:
        reward_errors.append(f"tickets: {e}")

    try:
        if rewards.get("fragments", 0) > 0:
            await cq.add_fragments(user_id, rewards["field_type"], rewards["fragments"])
    except Exception as e:
        reward_errors.append(f"fragments: {e}")

    try:
        if rewards.get("crystals", 0) > 0 or rewards.get("rainbow", 0) > 0:
            await cq.add_crystals(user_id, rewards.get("crystals", 0), rewards.get("rainbow", 0))
    except Exception as e:
        reward_errors.append(f"crystals: {e}")

    try:
        if rewards.get("iv_stones", 0) > 0:
            await item_queries.add_iv_stones(user_id, rewards["iv_stones"])
    except Exception as e:
        reward_errors.append(f"iv_stones: {e}")

    # 신규 아이템 지급
    for i_type, i_qty in rewards.get("items", {}).items():
        try:
            if i_type == "iv_stone_3":
                # IV스톤은 기존 시스템 재활용
                await item_queries.add_iv_stones(user_id, i_qty)
            else:
                await item_queries.add_user_item(user_id, i_type, i_qty)
        except Exception as e:
            reward_errors.append(f"item_{i_type}: {e}")

    if reward_errors:
        logger.error(f"dungeon reward errors for user {user_id}: {reward_errors}")

    # 칭호 해금
    unlocked_titles = []
    for t_info in rewards.get("new_titles", []):
        title_id = f"dungeon_{t_info['floor']}"
        try:
            has = await title_queries.has_title(user_id, title_id)
            if not has:
                await title_queries.unlock_title(user_id, title_id)
                unlocked_titles.append(t_info)
        except Exception as e:
            logger.error(f"dungeon title unlock error: {e}")

    # 결과 화면
    buffs = run.get("buffs_json", [])
    record_text = t(lang, "dungeon.result_new_record") if is_new_record else ""

    SKULL = icon_emoji("skull")
    CASTLE = icon_emoji("container")
    FOOT = icon_emoji("footsteps")
    SKILL = icon_emoji("skill")
    COIN = icon_emoji("coin")
    CROWN = icon_emoji("crown")
    TICKET = icon_emoji("stationery")
    rb = rarity_badge(run.get("rarity", "common"))
    shiny = shiny_emoji() + " " if run["is_shiny"] else ""

    revive_line = "\n💫 부활의 깃털 발동! → HP 30% 회복 후 재도전했으나 패배\n" if revive_used else ""
    text = (
        f"{SKULL} {t(lang, 'dungeon.floor_defeated', floor=final_floor)}\n"
        f"{revive_line}\n"
        f"{CASTLE} <b>{t(lang, 'dungeon.result_title')}</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"{FOOT} {t(lang, 'dungeon.result_floor', floor=final_floor)}{record_text}\n"
        f"{rb} {shiny}{run['pokemon_name']} [{run['iv_grade']}]\n"
        f"{SKILL} {t(lang, 'dungeon.buffs_count', count=len(buffs))}\n\n"
        f"{COIN} {t(lang, 'dungeon.result_reward_title')}\n"
        f"{t(lang, 'dungeon.result_bp', amount=rewards['bp'])}\n"
    )
    if rewards["fragments"] > 0:
        field_name = config.CAMP_FIELDS.get(rewards["field_type"], {}).get("name", "")
        text += t(lang, "dungeon.result_fragments", field=field_name, amount=rewards["fragments"]) + "\n"
    if rewards.get("crystals", 0) > 0:
        text += t(lang, "dungeon.result_crystals", amount=rewards["crystals"]) + "\n"
    if rewards.get("rainbow", 0) > 0:
        text += t(lang, "dungeon.result_rainbow", amount=rewards["rainbow"]) + "\n"
    if rewards.get("iv_stones", 0) > 0:
        text += t(lang, "dungeon.result_iv_stones", amount=rewards["iv_stones"]) + "\n"
    if rewards.get("tickets", 0) > 0:
        text += f"  {TICKET} {t(lang, 'dungeon.result_tickets', amount=rewards['tickets'])}\n"
    # 신규 아이템 표시
    for i_type, i_qty in rewards.get("items", {}).items():
        item_def = config.DUNGEON_ITEM_DEFS.get(i_type, {})
        item_name = item_def.get("name", i_type)
        item_emoji = item_def.get("emoji", "📦")
        if i_type == "iv_stone_3":
            item_name = "IV스톤(+3)"
            item_emoji = "💎"
        text += f"  {item_emoji} {item_name} ×{i_qty}\n"

    for t_info in unlocked_titles:
        text += f"  {CROWN} {t(lang, 'dungeon.result_title_unlock', title=t_info['title'])}\n"

    # 랭킹 표시
    rank = await dq.get_user_rank(user_id)
    if rank:
        text += f"\n{t(lang, 'dungeon.result_rank', rank=rank)}"

    tickets = await dq.get_dungeon_tickets(user_id)
    buttons = []
    if tickets > 0:
        buttons.append([InlineKeyboardButton(t(lang, "dungeon.btn_retry", tickets=tickets), callback_data=f"dg_retry_{user_id}")])
    buttons.append([
        InlineKeyboardButton(t(lang, "dungeon.btn_ranking"), callback_data=f"dg_rank_{user_id}"),
        InlineKeyboardButton(t(lang, "dungeon.btn_close"), callback_data=f"dg_close_{user_id}"),
    ])

    await _send_fresh(query, context, user_id, text, reply_markup=InlineKeyboardMarkup(buttons), photo=battle_card)
    _state(context).pop("run_id", None)


async def _load_pokemon(instance_id: int, user_id: int | None = None) -> dict | None:
    """인스턴스 ID로 포켓몬 로드. user_id 지정 시 소유권 검증."""
    pool = await queries.get_db()
    sql = (
        "SELECT up.id, up.user_id, up.pokemon_id, up.friendship, up.is_shiny, "
        "up.iv_hp, up.iv_atk, up.iv_def, up.iv_spa, up.iv_spdef, up.iv_spd, "
        "pm.name_ko, pm.rarity, pm.pokemon_type, pm.stat_type "
        "FROM user_pokemon up "
        "JOIN pokemon_master pm ON up.pokemon_id = pm.id "
        "WHERE up.id = $1 AND up.is_active = 1"
    )
    if user_id is not None:
        sql += " AND up.user_id = $2"
        row = await pool.fetchrow(sql, instance_id, user_id)
    else:
        row = await pool.fetchrow(sql, instance_id)
    return dict(row) if row else None


# ══════════════════════════════════════════════════════════
# 콜백 라우터
# ══════════════════════════════════════════════════════════

async def dungeon_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """모든 dg_* 콜백 처리."""
    query = update.callback_query
    if not query or not query.data:
        return

    data = query.data
    parts = data.split("_")
    if len(parts) < 3:
        await query.answer()
        return

    action = parts[1]

    try:
        user_id = int(parts[2])
    except (IndexError, ValueError):
        await query.answer()
        return

    if query.from_user.id != user_id:
        lang = await get_user_lang(query.from_user.id)
        await query.answer(t(lang, "dungeon.only_owner"), show_alert=True)
        return

    # 동시성 락
    if user_id in _dungeon_locks:
        lang = await get_user_lang(user_id)
        await query.answer(t(lang, "dungeon.processing"))
        return
    _dungeon_locks.add(user_id)
    try:
        await _handle_action(query, context, user_id, action, parts)
    except Exception as e:
        logger.error(f"dungeon_callback error: {e}", exc_info=True)
        try:
            lang = await get_user_lang(user_id)
            await query.answer(t(lang, "dungeon.error"), show_alert=True)
        except Exception:
            pass
    finally:
        _dungeon_locks.discard(user_id)


async def _handle_action(query, context, user_id: int, action: str, parts: list[str]):
    st = _state(context)
    lang = await get_user_lang(user_id)

    if action == "noop":
        await query.answer()
        return

    elif action == "close":
        await query.answer()
        try:
            await query.delete_message()
        except Exception:
            pass
        return

    elif action == "back":
        # 입장 화면으로
        await query.answer()
        text, kb = await _build_entry_screen(user_id, lang)
        await _send_fresh(query, context, user_id, text, reply_markup=kb)
        return

    elif action == "list":
        # 포켓몬 리스트
        filter_key = parts[3] if len(parts) > 3 else "all"
        page = int(parts[4]) if len(parts) > 4 else 0
        await query.answer()
        theme = ds.get_today_theme()
        text, kb = await _build_pokemon_list(user_id, filter_key, page, theme, lang)
        await _send_fresh(query, context, user_id, text, reply_markup=kb)
        return

    elif action == "flt":
        # 필터 변경
        filter_key = parts[3] if len(parts) > 3 else "all"
        await query.answer()
        theme = ds.get_today_theme()
        text, kb = await _build_pokemon_list(user_id, filter_key, 0, theme, lang)
        await _send_fresh(query, context, user_id, text, reply_markup=kb)
        return

    elif action == "sel":
        # 포켓몬 선택 → 런 시작
        instance_id = int(parts[3])
        await query.answer(t(lang, "dungeon.entering"))
        await _start_run(query, context, user_id, instance_id)
        return

    elif action in ("atk", "sk1", "sk2", "def"):
        # 턴제 전투 행동
        action_map = {"atk": "normal", "sk1": "skill1", "sk2": "skill2", "def": "defend"}
        await _process_turn_action(query, context, user_id, action_map[action])
        return

    elif action == "go":
        # 다음 층 진행
        run = await dq.get_active_run(user_id)
        if not run:
            await query.answer(t(lang, "dungeon.no_active_run"), show_alert=True)
            return
        await query.answer()
        st["run_id"] = run["id"]
        await _process_floor(query, context, user_id, run)
        return

    elif action == "buf":
        # 버프 선택
        idx = int(parts[3]) if len(parts) > 3 else 0
        choices = st.get("buff_choices", [])
        if idx >= len(choices):
            await query.answer(t(lang, "dungeon.invalid_choice"), show_alert=True)
            return

        run = await dq.get_active_run(user_id)
        if not run:
            await query.answer(t(lang, "dungeon.no_active_run"), show_alert=True)
            return

        chosen = choices[idx]
        buffs = run.get("buffs_json", [])
        if isinstance(buffs, str):
            import json
            buffs = json.loads(buffs)

        old_buffs = list(buffs)
        buffs = ds.apply_buff_choice(buffs, chosen)

        # HP 버프면 max_hp도 갱신 (레벨업 시 이전 레벨 효과 제거 후 재적용)
        new_max_hp = run["max_hp"]
        new_hp = run["current_hp"]
        eff = chosen.get("effect", {})
        if chosen["id"] == "hp" and "mult" in eff:
            # 이전 레벨 mult 제거 후 새 mult 적용
            old_lv = ds._get_buff_level("hp", old_buffs)
            if old_lv > 0:
                old_mult = ds.BUFF_DEFS["hp"]["levels"][old_lv - 1]["mult"]
                new_max_hp = int(new_max_hp / old_mult)
                new_hp = int(new_hp / old_mult)
            new_max_hp = int(new_max_hp * eff["mult"])
            new_hp = int(new_hp * eff["mult"])
        elif chosen["id"] == "allstat" and "mult" in eff:
            new_max_hp = int(new_max_hp * eff["mult"])
            new_hp = int(new_hp * eff["mult"])

        await dq.update_run_progress(run["id"], run["floor_reached"], new_hp, buffs)
        if new_max_hp != run["max_hp"]:
            pool = await queries.get_db()
            await pool.execute(
                "UPDATE dungeon_runs SET max_hp = $1, current_hp = $2 WHERE id = $3",
                new_max_hp, new_hp, run["id"],
            )

        lv = chosen.get("lv", 1)
        lv_emoji = ds.LV_EMOJI.get(lv, "⬜")
        if chosen.get("is_upgrade"):
            tag = f"Lv.{lv}"
        else:
            tag = t(lang, "dungeon.buff_tag_new")
        await query.answer(t(lang, "dungeon.buff_acquired_popup", emoji=lv_emoji, name=chosen['name'], tag=tag))

        # 히든 시너지 체크
        new_synergies = ds.check_new_synergies(old_buffs, buffs)
        if new_synergies:
            syn_texts = []
            for s in new_synergies:
                syn_texts.append(f"{s['emoji']} {t(lang, 'dungeon.synergy_activated', name=s['name'], desc=s['desc'])}")
            syn_msg = "\n".join(syn_texts)
            try:
                await context.bot.send_message(chat_id=user_id, text=syn_msg)
            except Exception:
                pass

        # 다음 층 진행 화면
        run_updated = await dq.get_active_run(user_id)
        hp_bar = _hp_bar(run_updated["current_hp"], run_updated["max_hp"])
        hp_pct = int(run_updated["current_hp"] / run_updated["max_hp"] * 100) if run_updated["max_hp"] else 0

        CASTLE = icon_emoji("container")
        HEART = icon_emoji("pokecenter")
        SKILL = icon_emoji("skill")

        # 보유 버프 요약
        buff_summary = ""
        for b in buffs:
            blv = b.get("lv", 1)
            bname = b.get("name", "?")
            buff_summary += f"  {ds.LV_EMOJI.get(blv, '⬜')} {bname} Lv.{blv}\n"

        text = (
            f"{CASTLE} {t(lang, 'dungeon.floor_cleared', floor=run_updated['floor_reached'])}\n\n"
            f"{lv_emoji} <b>{chosen['name']} [{tag}]</b> — {chosen['desc']}\n\n"
            f"{HEART} {hp_bar} {hp_pct}%\n"
            f"{SKILL} {t(lang, 'dungeon.buffs_label')}\n{buff_summary}"
        )
        buttons = [
            [InlineKeyboardButton(t(lang, "dungeon.btn_next_floor"), callback_data=f"dg_go_{user_id}")],
            [InlineKeyboardButton(t(lang, "dungeon.btn_give_up"), callback_data=f"dg_quit_{user_id}")],
        ]
        await _send_fresh(query, context, user_id, text, reply_markup=InlineKeyboardMarkup(buttons))
        return

    elif action == "rogue":
        # 로그라이크 이벤트 선택: accept / pass
        run = await dq.get_active_run(user_id)
        if not run:
            await query.answer(t(lang, "dungeon.no_active_run"), show_alert=True)
            return

        choice = parts[3] if len(parts) > 3 else "pass"  # dg_rogue_{uid}_{roll|pass}
        buffs = run.get("buffs_json", [])
        new_hp = run["current_hp"]

        if choice == "roll":
            # 지금 랜덤 결정 + 즉시 적용
            event = ds.generate_roguelike_event()
            new_hp, buffs, event_msg = ds.apply_roguelike_event(
                event, run["current_hp"], run["max_hp"], buffs
            )
            await dq.update_run_progress(run["id"], run["floor_reached"], new_hp, buffs)
            type_tag = "✅" if event["type"] == "positive" else "⚠️"
            one_floor_note = "\n💡 다음 층 1턴만 적용" if event["action"] == "stat_mult" else ""
            await query.answer(f"🎲 {event['name']}!", show_alert=True)
        else:
            event = None
            await query.answer("➡️ 지나갑니다!")

        hp_bar = _hp_bar(new_hp, run["max_hp"])
        hp_pct = int(new_hp / run["max_hp"] * 100) if run["max_hp"] else 0
        SKILL = icon_emoji("skill")
        buff_line = f"{SKILL} {t(lang, 'dungeon.buffs_count', count=len(buffs))}"
        # 이벤트 결과 표시
        event_result = ""
        if event:
            type_tag = "✅" if event["type"] == "positive" else "⚠️"
            one_floor = " (다음 층 1턴)" if event["action"] == "stat_mult" else ""
            event_result = f"\n🎲 {type_tag} {event['name']}\n   {event['desc']}{one_floor}\n"
        text = (
            f"{t(lang, 'dungeon.floor_label', floor=run['floor_reached'])}\n"
            f"{hp_bar} {hp_pct}% ({new_hp}/{run['max_hp']})\n"
            f"{event_result}"
            f"{buff_line}\n"
        )
        buttons = [
            [InlineKeyboardButton(t(lang, "dungeon.btn_next_floor"), callback_data=f"dg_go_{user_id}")],
            [InlineKeyboardButton(t(lang, "dungeon.btn_give_up"), callback_data=f"dg_quit_{user_id}")],
        ]
        await _send_fresh(query, context, user_id, text, reply_markup=InlineKeyboardMarkup(buttons))
        return

    elif action == "skip":
        # 지나가기 — 버프 선택 안 하고 다음 층
        run = await dq.get_active_run(user_id)
        if not run:
            await query.answer(t(lang, "dungeon.no_active_run"), show_alert=True)
            return

        max_hp = run["max_hp"]
        heal = int(max_hp * config.DUNGEON_SKIP_HEAL)
        new_hp = min(run["current_hp"] + heal, max_hp)
        await dq.update_run_progress(run["id"], run["floor_reached"], new_hp, run.get("buffs_json", []))
        await query.answer("➡️ 지나갑니다!")

        hp_bar = _hp_bar(new_hp, max_hp)
        hp_pct = int(new_hp / max_hp * 100) if max_hp else 0
        buffs = run.get("buffs_json", [])

        CASTLE = icon_emoji("container")
        HEART = icon_emoji("pokecenter")
        SKILL = icon_emoji("skill")

        text = (
            f"{CASTLE} {t(lang, 'dungeon.floor_cleared', floor=run['floor_reached'])}\n\n"
            f"{t(lang, 'dungeon.skip_heal_text', hp=heal)}\n\n"
            f"{HEART} {hp_bar} {hp_pct}%\n"
            f"{SKILL} {t(lang, 'dungeon.buffs_count', count=len(buffs))}\n"
        )
        buttons = [
            [InlineKeyboardButton(t(lang, "dungeon.btn_next_floor"), callback_data=f"dg_go_{user_id}")],
            [InlineKeyboardButton(t(lang, "dungeon.btn_give_up"), callback_data=f"dg_quit_{user_id}")],
        ]
        await _send_fresh(query, context, user_id, text, reply_markup=InlineKeyboardMarkup(buttons))
        return

    elif action == "buy":
        # 입장권 BP 구매
        sub_tier = await _get_sub_tier(user_id)
        bp_cost = config.DUNGEON_TICKET_BP_COST.get(sub_tier or "free", 50)
        bought = await dq.get_bought_today(user_id)
        buy_limit = config.DUNGEON_DAILY_BUY_LIMIT.get(sub_tier or "free", 3)

        if bought >= buy_limit:
            await query.answer(t(lang, "dungeon.buy_limit_exceeded"), show_alert=True)
            return

        success = await dq.buy_ticket_with_bp(user_id, bp_cost, buy_limit)
        if not success:
            await query.answer(t(lang, "dungeon.bp_insufficient", cost=bp_cost), show_alert=True)
            return

        await query.answer(t(lang, "dungeon.buy_success", cost=bp_cost))
        text, kb = await _build_entry_screen(user_id, lang)
        await _send_fresh(query, context, user_id, text, reply_markup=kb)
        return

    elif action == "quit":
        # 포기
        run = await dq.get_active_run(user_id)
        if run:
            await _finish_run(query, context, user_id, run, run["floor_reached"])
        else:
            await query.answer(t(lang, "dungeon.no_active_run"))
        return

    elif action == "retry":
        # 재도전 → 입장 화면
        await query.answer()
        text, kb = await _build_entry_screen(user_id, lang)
        await _send_fresh(query, context, user_id, text, reply_markup=kb)
        return

    elif action == "rank":
        # 랭킹
        await query.answer()
        ranking = await dq.get_weekly_ranking(20)
        if not ranking:
            text = f"📊 <b>{t(lang, 'dungeon.ranking_title')}</b>\n\n{t(lang, 'dungeon.ranking_empty')}"
        else:
            lines = [f"📊 <b>{t(lang, 'dungeon.ranking_title')}</b>\n"]
            for i, r in enumerate(ranking):
                medal = ["🥇", "🥈", "🥉"][i] if i < 3 else f"{i+1}."
                shiny = "✨" if r.get("is_shiny") else ""
                pokemon_info = f"{shiny}{r['pokemon_name']} [{r.get('iv_grade', '?')}]"
                lines.append(
                    t(lang, "dungeon.ranking_entry",
                      medal=medal, name=r['display_name'],
                      floor=r['floor_reached'], pokemon=pokemon_info)
                )
            text = "\n".join(lines)

        buttons = [[InlineKeyboardButton(t(lang, "dungeon.btn_back"), callback_data=f"dg_back_{user_id}")]]
        await _send_fresh(query, context, user_id, text, reply_markup=InlineKeyboardMarkup(buttons))
        return

    else:
        await query.answer()


# ══════════════════════════════════════════════════════════
# 런 시작
# ══════════════════════════════════════════════════════════

async def _start_run(query, context, user_id: int, instance_id: int):
    """포켓몬 선택 → 입장권 차감 → 런 시작."""
    lang = await get_user_lang(user_id)

    # 이미 활성 런이 있으면 차단
    existing = await dq.get_active_run(user_id)
    if existing:
        await _send_fresh(query, context, user_id, t(lang, "dungeon.already_active"))
        return

    # 일일 런 제한 (구독별)
    sub_tier = await _get_sub_tier(user_id)
    max_runs = config.DUNGEON_MAX_DAILY_RUNS.get(sub_tier or "free", 3)
    daily_count = await dq.get_daily_run_count(user_id)
    if daily_count >= max_runs:
        await _send_fresh(query, context, user_id,
            t(lang, "dungeon.daily_exhausted", used=daily_count, max=max_runs))
        return

    # 입장권 차감
    success = await dq.deduct_dungeon_ticket(user_id)
    if not success:
        await _send_fresh(query, context, user_id, t(lang, "dungeon.no_tickets"))
        return

    # 포켓몬 로드 (소유권 검증)
    pokemon = await _load_pokemon(instance_id, user_id=user_id)
    if not pokemon:
        await dq.add_dungeon_tickets(user_id, 1)  # 환불
        await _send_fresh(query, context, user_id, t(lang, "dungeon.pokemon_not_found"))
        return

    # 스탯 계산
    stats, types = ds.build_player_stats(pokemon)
    max_hp = stats["hp"]

    grade = _iv_grade(pokemon)
    theme = ds.get_today_theme()

    # 런 생성
    run_id = await dq.create_dungeon_run(
        user_id=user_id,
        pokemon_instance_id=instance_id,
        pokemon_id=pokemon["pokemon_id"],
        pokemon_name=pokemon["name_ko"],
        is_shiny=bool(pokemon.get("is_shiny")),
        iv_grade=grade,
        rarity=pokemon.get("rarity", "common"),
        theme=theme["name"],
        current_hp=max_hp,
        max_hp=max_hp,
    )

    st = _state(context)
    st["run_id"] = run_id
    # PP 상태 초기화 (런 시작 시)
    st.pop("combat", None)
    st.pop("pp_state", None)

    # 던전부적 자동 소비 → 초기 버프 1개
    amulet_text = ""
    amulet_qty = await item_queries.get_user_item(user_id, "dungeon_amulet")
    if amulet_qty > 0:
        used = await item_queries.use_user_item(user_id, "dungeon_amulet")
        if used:
            initial_buff = ds.generate_buff_choices(0, [], count=1)
            if initial_buff:
                buff = initial_buff[0]
                await dq.update_run_progress(run_id, 0, max_hp, [buff])
                amulet_text = f"\n🔮 던전부적 발동! 초기 버프: {buff['name']}\n"

    # 시작 화면
    shiny = "✨" if pokemon.get("is_shiny") else ""
    p_name = poke_name(pokemon, lang)
    type_str = "/".join(_type_emoji(tp) + _type_name(lang, tp) for tp in types)
    cost = _get_pokemon_cost(pokemon["rarity"])
    freq = config.DUNGEON_BUFF_FREQUENCY.get(cost, 1)

    text = (
        f"🏰 <b>{t(lang, 'dungeon.entering')}</b>\n\n"
        f"{t(lang, 'dungeon.enter_theme', emoji=theme['emoji'], name=theme['name'])}\n"
        f"{t(lang, 'dungeon.enter_pokemon', shiny=shiny, name=p_name, grade=grade)}\n"
        f"{t(lang, 'dungeon.enter_type_power', types=type_str, power=calc_power(stats))}\n"
        f"{t(lang, 'dungeon.enter_cost_buff', cost=cost, freq=freq)}\n\n"
        f"{t(lang, 'dungeon.enter_hp', hp=max_hp)}\n"
        f"{amulet_text}\n"
        f"{t(lang, 'dungeon.enter_ready')}"
    )

    buttons = [
        [InlineKeyboardButton(t(lang, "dungeon.btn_start_floor1"), callback_data=f"dg_go_{user_id}")],
        [InlineKeyboardButton(t(lang, "dungeon.btn_give_up"), callback_data=f"dg_quit_{user_id}")],
    ]
    await _send_fresh(query, context, user_id, text, reply_markup=InlineKeyboardMarkup(buttons))
