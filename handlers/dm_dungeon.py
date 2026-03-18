"""Dungeon roguelike handler — DM only."""

import asyncio
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import config
from database import queries
from database import dungeon_queries as dq
from services import dungeon_service as ds
from utils.battle_calc import calc_battle_stats, calc_power, get_normalized_base_stats, EVO_STAGE_MAP, iv_total
from utils.helpers import icon_emoji, shiny_emoji, rarity_badge

logger = logging.getLogger(__name__)

PAGE_SIZE = 8
_dungeon_locks: set[int] = set()


# ══════════════════════════════════════════════════════════
# 유틸리티
# ══════════════════════════════════════════════════════════

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
    except Exception:
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
    display_name = update.effective_user.first_name or "트레이너"
    await queries.ensure_user(user_id, display_name, update.effective_user.username)

    # 진행 중 런 확인
    active = await dq.get_active_run(user_id)
    if active:
        st = _state(context)
        st["run_id"] = active["id"]
        text, kb = await _build_resume_screen(user_id, active)
        msg = await update.message.reply_text(text, reply_markup=kb, parse_mode="HTML")
        st["msg_id"] = msg.message_id
        return

    text, kb = await _build_entry_screen(user_id)
    st = _state(context)
    msg = await update.message.reply_text(text, reply_markup=kb, parse_mode="HTML")
    st["msg_id"] = msg.message_id
    st.pop("run_id", None)


async def _build_entry_screen(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    tickets = await dq.get_dungeon_tickets(user_id)
    best = await dq.get_user_best_floor(user_id)
    theme = ds.get_today_theme()
    sub_tier = await _get_sub_tier(user_id)

    adv_types = " / ".join(config.TYPE_EMOJI.get(t, "") + config.TYPE_NAME_KO.get(t, t) for t in theme["advantage"])
    theme_types = " / ".join(config.TYPE_EMOJI.get(t, "") + config.TYPE_NAME_KO.get(t, t) for t in theme["types"])

    CASTLE = icon_emoji("container")
    TICKET = icon_emoji("stationery")
    CROWN = icon_emoji("crown")
    FOOT = icon_emoji("footsteps")
    BOLT = icon_emoji("bolt")

    text = (
        f"{CASTLE} <b>포켓몬 던전</b>\n\n"
        f"{TICKET} 입장권: <b>{tickets}장</b>\n"
        f"{CROWN} 내 최고: <b>{best}층</b>\n\n"
        f"{FOOT} 오늘의 던전: {theme['emoji']} <b>{theme['name']}</b>\n"
        f"   {theme_types} 타입 적 출현!\n"
        f"   {BOLT} 유리: {adv_types}\n"
    )

    buttons = []
    if tickets > 0:
        buttons.append([InlineKeyboardButton("⚔️ 포켓몬 선택", callback_data=f"dg_list_{user_id}_all_0")])
    else:
        buttons.append([InlineKeyboardButton("🎫 입장권 없음", callback_data=f"dg_noop_{user_id}")])

    # BP 구매
    bp_cost = config.DUNGEON_TICKET_BP_COST.get(sub_tier or "free", 50)
    bought = await dq.get_bought_today(user_id)
    buy_limit = config.DUNGEON_DAILY_BUY_LIMIT.get(sub_tier or "free", 3)
    if bought < buy_limit:
        buttons.append([InlineKeyboardButton(
            f"🎫 입장권 구매 ({bp_cost}BP) [{bought}/{buy_limit}]",
            callback_data=f"dg_buy_{user_id}"
        )])

    buttons.append([
        InlineKeyboardButton("📊 랭킹", callback_data=f"dg_rank_{user_id}"),
        InlineKeyboardButton("❌ 닫기", callback_data=f"dg_close_{user_id}"),
    ])

    return text, InlineKeyboardMarkup(buttons)


async def _build_resume_screen(user_id: int, run: dict) -> tuple[str, InlineKeyboardMarkup]:
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

    text = (
        f"{CASTLE} <b>진행 중인 던전</b>\n\n"
        f"{FOOT} {run['floor_reached']}층 | {theme_info['emoji']} {run['theme']}\n"
        f"{rb} {shiny}{run['pokemon_name']} [{run['iv_grade']}]\n"
        f"{HEART} {hp_bar} {hp_pct}%\n"
        f"{SKILL} 버프 {len(buffs)}개\n"
    )
    buttons = [
        [InlineKeyboardButton("⚔️ 다음 층으로!", callback_data=f"dg_go_{user_id}")],
        [InlineKeyboardButton("🏳️ 포기", callback_data=f"dg_quit_{user_id}")],
    ]
    return text, InlineKeyboardMarkup(buttons)


# ══════════════════════════════════════════════════════════
# 포켓몬 선택 UI
# ══════════════════════════════════════════════════════════

async def _build_pokemon_list(user_id: int, filter_key: str, page: int, theme: dict) -> tuple[str, InlineKeyboardMarkup]:
    """포켓몬 선택 리스트 빌드."""
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
    filters = [("all", "전체"), ("rec", "⭐추천")]
    for t in theme["advantage"]:
        filters.append((t, config.TYPE_EMOJI.get(t, "") + config.TYPE_NAME_KO.get(t, t)[:2]))
    filters.extend([("shiny", "✨이로치"), ("sgrade", "S급")])

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
        label = f"{shiny}{p['name_ko']} {grade}{type_e} {power}"
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
    buttons.append([InlineKeyboardButton("🔙 돌아가기", callback_data=f"dg_back_{user_id}")])

    theme_name = f"{theme['emoji']} {theme['name']}"
    text = f"{icon_emoji('container')} 던전 — {theme_name}\n포켓몬을 선택하세요 ({total}마리)"

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
    """다음 층 배틀 진행."""
    floor = run["floor_reached"] + 1
    theme_data = None
    for t in config.DUNGEON_THEMES:
        if t["name"] == run["theme"]:
            theme_data = t
            break
    if not theme_data:
        theme_data = ds.get_today_theme()

    # 적 생성
    enemy = ds.generate_enemy(floor, theme_data)

    # 플레이어 스탯
    pokemon = await _load_pokemon(run["pokemon_instance_id"])
    if not pokemon:
        await _send_fresh(query, context, user_id, "포켓몬 정보를 불러올 수 없습니다.")
        return

    player_stats, player_types = ds.build_player_stats(pokemon)
    buffs = run.get("buffs_json", [])
    if isinstance(buffs, str):
        import json
        buffs = json.loads(buffs)

    # 배틀 실행 (carry-over HP를 엔진에 전달 — 단일 진실 소스)
    result = ds.resolve_dungeon_battle(
        player_stats, player_types, pokemon["rarity"], enemy, buffs,
        current_hp=run["current_hp"], max_hp=run["max_hp"],
    )
    remaining_hp = result["remaining_hp"]
    won = result["won"]

    # 부활이 사용됐으면 버프에서 제거
    if result.get("revive_used"):
        buffs = [b for b in buffs if b.get("effect", {}).get("type") != "revive"]

    # 배틀 GIF 생성 — Canvas GIF (내 공격 + 적 반격)
    import asyncio as _aio

    floor_type = "★ 관장전" if enemy["is_boss"] else ("⚡ 엘리트" if enemy["is_elite"] else "")
    battle_card = None      # 내 공격 GIF
    counter_card = None     # 적 반격 GIF

    try:
        from utils.battle_canvas import render_battle_gif
        from models.pokemon_skills import get_primary_skill
        from models.pokemon_battle_data import POKEMON_BATTLE_DATA

        _floor_label = f"{floor}F"
        if floor_type:
            _floor_label += f" {floor_type}"

        _p_hp_before = run["current_hp"] / run["max_hp"] if run["max_hp"] else 1.0
        _p_hp_after = remaining_hp / run["max_hp"] if run["max_hp"] else 0.0
        _enemy_hp_after = 0.0 if won else 0.15

        # 1) 내 공격 GIF
        _skill_name, _ = get_primary_skill(pokemon["pokemon_id"])
        _atk_type = POKEMON_BATTLE_DATA.get(pokemon["pokemon_id"], ("normal",))[0]

        loop = _aio.get_event_loop()
        battle_card, _ = await loop.run_in_executor(
            None, render_battle_gif,
            pokemon["pokemon_id"], run["pokemon_name"],
            enemy["id"], enemy["name_ko"],
            _skill_name, _atk_type, result["total_damage_dealt"],
            bool(run["is_shiny"]), False,
            False,
            pokemon["rarity"], enemy["rarity"],
            1.0, _enemy_hp_after,
            _p_hp_before,
            _floor_label,
        )

        # 2) 적 반격 GIF (피해를 입었을 때만)
        if result["total_damage_taken"] > 0:
            _e_skill, _ = get_primary_skill(enemy["id"])
            _e_type = POKEMON_BATTLE_DATA.get(enemy["id"], ("normal",))[0]

            counter_card, _ = await loop.run_in_executor(
                None, render_battle_gif,
                enemy["id"], enemy["name_ko"],
                pokemon["pokemon_id"], run["pokemon_name"],
                _e_skill, _e_type, result["total_damage_taken"],
                False, bool(run["is_shiny"]),
                False,
                enemy["rarity"], pokemon["rarity"],
                _p_hp_before, _p_hp_after,  # 내 HP: before → after
                _enemy_hp_after,  # 적 남은 HP
                _floor_label,
            )
    except Exception:
        import logging
        logging.getLogger(__name__).error("Canvas GIF 실패, PIL 폴백", exc_info=True)

    # Canvas GIF 실패 시 기존 PIL GIF 폴백
    if battle_card is None:
        from utils.card_generator import generate_dungeon_battle_gif
        loop = _aio.get_event_loop()
        battle_card = await loop.run_in_executor(
            None, generate_dungeon_battle_gif,
            pokemon["pokemon_id"], run["pokemon_name"], pokemon["rarity"],
            run["current_hp"], run["max_hp"], bool(run["is_shiny"]),
            enemy["id"], enemy["name_ko"], enemy["rarity"],
            floor, floor_type, result["type_display"],
            result["total_damage_dealt"], result["total_damage_taken"],
            won, remaining_hp,
        )

    # GIF 전송: 내 공격 → (적 반격) → 결과 텍스트
    # 내 공격 GIF를 먼저 보내고, 결과는 적 반격 GIF(있으면)와 함께
    _result_gif = battle_card  # 기본: 내 공격 GIF만
    if counter_card is not None:
        # 내 공격 GIF를 먼저 별도 전송
        st = _state(context)
        old_photo_id = st.pop("photo_msg_id", None)
        if old_photo_id:
            try:
                await context.bot.delete_message(chat_id=user_id, message_id=old_photo_id)
            except Exception:
                pass
        try:
            atk_msg = await context.bot.send_animation(chat_id=user_id, animation=battle_card)
            st["photo_msg_id"] = atk_msg.message_id
        except Exception:
            pass
        await _aio.sleep(4)  # 내 공격 GIF 감상 시간
        _result_gif = counter_card  # 결과 화면에는 적 반격 GIF

    if won:
        # 층간 회복 적용
        heal_rate = ds.get_floor_heal_rate(buffs)
        if heal_rate > 0:
            remaining_hp = min(run["max_hp"], remaining_hp + int(run["max_hp"] * heal_rate))

        # DB 업데이트
        await dq.update_run_progress(run["id"], floor, remaining_hp, buffs)

        # 배틀 결과 텍스트
        hp_bar = _hp_bar(remaining_hp, run["max_hp"])
        hp_pct = int(remaining_hp / run["max_hp"] * 100) if run["max_hp"] else 0

        CHECK = icon_emoji("check")
        HEART = icon_emoji("pokecenter")
        SKILL = icon_emoji("skill")
        text = (
            f"{CHECK} <b>{floor}층 승리!</b> {HEART} {hp_bar} {hp_pct}%\n"
            f"{SKILL} 버프 {len(buffs)}개"
        )

        # 버프 제공 여부 확인
        cost = _get_pokemon_cost(pokemon["rarity"])
        st = _state(context)

        if ds.should_offer_buff(floor, cost):
            choices = ds.generate_buff_choices(floor, buffs)
            st["buff_choices"] = choices

            text += f"\n\n{icon_emoji('gotcha')} <b>버프를 선택하세요:</b>"
            buttons = []
            for i, buff in enumerate(choices):
                emoji = ds.GRADE_EMOJI.get(buff["grade"], "⬜")
                grade_ko = ds.GRADE_KO.get(buff["grade"], "")
                buttons.append([InlineKeyboardButton(
                    f"{emoji} {buff['name']} [{grade_ko}] — {buff['desc']}",
                    callback_data=f"dg_buf_{user_id}_{i}"
                )])
            # 스킵 옵션
            skips = run.get("skips_used", 0)
            if skips < config.DUNGEON_MAX_SKIPS:
                buttons.append([InlineKeyboardButton(
                    f"⏭ 스킵 (HP 5% 회복) [{skips}/{config.DUNGEON_MAX_SKIPS}]",
                    callback_data=f"dg_skip_{user_id}"
                )])
            await _send_fresh(query, context, user_id, text, reply_markup=InlineKeyboardMarkup(buttons), photo=_result_gif)
        else:
            # 버프 없이 다음 층
            buttons = [
                [InlineKeyboardButton("⚔️ 다음 층으로!", callback_data=f"dg_go_{user_id}")],
                [InlineKeyboardButton("🏳️ 포기", callback_data=f"dg_quit_{user_id}")],
            ]
            await _send_fresh(query, context, user_id, text, reply_markup=InlineKeyboardMarkup(buttons), photo=_result_gif)
    else:
        # 패배 — 도달 층은 마지막 클리어 층 (이번 층은 실패)
        await _finish_run(query, context, user_id, run, run["floor_reached"], battle_card=_result_gif)


async def _finish_run(query, context, user_id: int, run: dict, final_floor: int, battle_card=None):
    """런 종료 + 보상 정산."""
    sub_tier = await _get_sub_tier(user_id)
    rewards = ds.calculate_rewards(final_floor, run["theme"], sub_tier)

    # DB 업데이트
    await dq.end_run(run["id"], final_floor, rewards["bp"], rewards["fragments"])
    await dq.update_pokemon_record(user_id, run["pokemon_instance_id"], final_floor, run["theme"])
    is_new_record = await dq.update_user_best_floor(user_id, final_floor)

    # BP 지급
    if rewards["bp"] > 0:
        await queries.add_battle_points(user_id, rewards["bp"])

    # 입장권 지급
    if rewards.get("tickets", 0) > 0:
        await dq.add_dungeon_tickets(user_id, rewards["tickets"])

    # 칭호 해금
    unlocked_titles = []
    for t_info in rewards.get("new_titles", []):
        title_id = f"dungeon_{t_info['floor']}"
        has = await queries.has_title(user_id, title_id)
        if not has:
            await queries.unlock_title(user_id, title_id)
            unlocked_titles.append(t_info)

    # 결과 화면
    shiny = "✨" if run["is_shiny"] else ""
    buffs = run.get("buffs_json", [])
    record_text = " 🎉 최고 갱신!" if is_new_record else ""

    SKULL = icon_emoji("skull")
    CASTLE = icon_emoji("container")
    FOOT = icon_emoji("footsteps")
    SKILL = icon_emoji("skill")
    COIN = icon_emoji("coin")
    CROWN = icon_emoji("crown")
    TICKET = icon_emoji("stationery")
    rb = rarity_badge(run.get("rarity", "common"))
    shiny = shiny_emoji() + " " if run["is_shiny"] else ""

    text = (
        f"{SKULL} <b>{final_floor}층에서 패배...</b>\n\n"
        f"{CASTLE} <b>던전 결과</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"{FOOT} 도달: <b>{final_floor}층</b>{record_text}\n"
        f"{rb} {shiny}{run['pokemon_name']} [{run['iv_grade']}]\n"
        f"{SKILL} 버프 {len(buffs)}개\n\n"
        f"{COIN} <b>보상:</b>\n"
        f"  BP +{rewards['bp']}\n"
    )
    if rewards["fragments"] > 0:
        text += f"  🧩 조각 ×{rewards['fragments']}\n"
    if rewards.get("tickets", 0) > 0:
        text += f"  {TICKET} 입장권 ×{rewards['tickets']}\n"
    for t_info in unlocked_titles:
        text += f"  {CROWN} 칭호 해금: \"{t_info['title']}\"\n"

    # 랭킹 표시
    rank = await dq.get_user_rank(user_id)
    if rank:
        text += f"\n📊 랭킹: 서버 {rank}위"

    tickets = await dq.get_dungeon_tickets(user_id)
    buttons = []
    if tickets > 0:
        buttons.append([InlineKeyboardButton(f"🔄 다시 도전 (🎫{tickets}장)", callback_data=f"dg_retry_{user_id}")])
    buttons.append([
        InlineKeyboardButton("📊 랭킹", callback_data=f"dg_rank_{user_id}"),
        InlineKeyboardButton("❌ 닫기", callback_data=f"dg_close_{user_id}"),
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
        await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
        return

    # 동시성 락
    if user_id in _dungeon_locks:
        await query.answer("처리 중...")
        return
    _dungeon_locks.add(user_id)
    try:
        await _handle_action(query, context, user_id, action, parts)
    except Exception as e:
        logger.error(f"dungeon_callback error: {e}", exc_info=True)
        try:
            await query.answer("오류가 발생했습니다.", show_alert=True)
        except Exception:
            pass
    finally:
        _dungeon_locks.discard(user_id)


async def _handle_action(query, context, user_id: int, action: str, parts: list[str]):
    st = _state(context)

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
        text, kb = await _build_entry_screen(user_id)
        await _send_fresh(query, context, user_id, text, reply_markup=kb)
        return

    elif action == "list":
        # 포켓몬 리스트
        filter_key = parts[3] if len(parts) > 3 else "all"
        page = int(parts[4]) if len(parts) > 4 else 0
        await query.answer()
        theme = ds.get_today_theme()
        text, kb = await _build_pokemon_list(user_id, filter_key, page, theme)
        await _send_fresh(query, context, user_id, text, reply_markup=kb)
        return

    elif action == "flt":
        # 필터 변경
        filter_key = parts[3] if len(parts) > 3 else "all"
        await query.answer()
        theme = ds.get_today_theme()
        text, kb = await _build_pokemon_list(user_id, filter_key, 0, theme)
        await _send_fresh(query, context, user_id, text, reply_markup=kb)
        return

    elif action == "sel":
        # 포켓몬 선택 → 런 시작
        instance_id = int(parts[3])
        await query.answer("던전 입장!")
        await _start_run(query, context, user_id, instance_id)
        return

    elif action == "go":
        # 다음 층 진행
        run = await dq.get_active_run(user_id)
        if not run:
            await query.answer("진행 중인 던전이 없습니다.", show_alert=True)
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
            await query.answer("잘못된 선택입니다.", show_alert=True)
            return

        run = await dq.get_active_run(user_id)
        if not run:
            await query.answer("진행 중인 던전이 없습니다.", show_alert=True)
            return

        chosen = choices[idx]
        buffs = run.get("buffs_json", [])
        if isinstance(buffs, str):
            import json
            buffs = json.loads(buffs)
        buffs.append(chosen)

        # HP 버프면 max_hp도 갱신
        new_max_hp = run["max_hp"]
        new_hp = run["current_hp"]
        eff = chosen.get("effect", {})
        if eff.get("stat") == "hp":
            mult = eff.get("mult", 1.0)
            new_max_hp = int(new_max_hp * mult)
            new_hp = int(new_hp * mult)  # 현재 HP도 비례 증가
        elif eff.get("stat") == "all":
            mult = eff.get("mult", 1.0)
            new_max_hp = int(new_max_hp * mult)
            new_hp = int(new_hp * mult)

        await dq.update_run_progress(run["id"], run["floor_reached"], new_hp, buffs)
        if new_max_hp != run["max_hp"]:
            pool = await queries.get_db()
            await pool.execute(
                "UPDATE dungeon_runs SET max_hp = $1, current_hp = $2 WHERE id = $3",
                new_max_hp, new_hp, run["id"],
            )

        emoji = ds.GRADE_EMOJI.get(chosen["grade"], "")
        await query.answer(f"{emoji} {chosen['name']} 획득!")

        # 다음 층 진행 화면
        run_updated = await dq.get_active_run(user_id)
        hp_bar = _hp_bar(run_updated["current_hp"], run_updated["max_hp"])
        hp_pct = int(run_updated["current_hp"] / run_updated["max_hp"] * 100) if run_updated["max_hp"] else 0

        text = (
            f"🏰 <b>{run_updated['floor_reached']}층 클리어!</b>\n\n"
            f"{emoji} <b>{chosen['name']}</b> 획득! — {chosen['desc']}\n\n"
            f"❤️ {hp_bar} {hp_pct}%\n"
            f"🗡 버프 {len(buffs)}개\n"
        )
        buttons = [
            [InlineKeyboardButton("⚔️ 다음 층으로!", callback_data=f"dg_go_{user_id}")],
            [InlineKeyboardButton("🏳️ 포기", callback_data=f"dg_quit_{user_id}")],
        ]
        await _send_fresh(query, context, user_id, text, reply_markup=InlineKeyboardMarkup(buttons))
        return

    elif action == "skip":
        # 버프 스킵 + HP 5% 회복
        run = await dq.get_active_run(user_id)
        if not run:
            await query.answer("진행 중인 던전이 없습니다.", show_alert=True)
            return

        skips = run.get("skips_used", 0)
        if skips >= config.DUNGEON_MAX_SKIPS:
            await query.answer("스킵 횟수를 모두 사용했습니다.", show_alert=True)
            return

        heal = int(run["max_hp"] * config.DUNGEON_SKIP_HEAL)
        new_hp = min(run["max_hp"], run["current_hp"] + heal)
        skips += 1

        await dq.update_run_progress(run["id"], run["floor_reached"], new_hp, run.get("buffs_json", []))
        await dq.update_run_skips(run["id"], skips)

        await query.answer(f"HP +{heal} 회복!")

        hp_bar = _hp_bar(new_hp, run["max_hp"])
        hp_pct = int(new_hp / run["max_hp"] * 100) if run["max_hp"] else 0
        buffs = run.get("buffs_json", [])

        text = (
            f"🏰 <b>{run['floor_reached']}층 클리어!</b>\n\n"
            f"⏭ 버프 스킵 — HP +{heal} 회복\n\n"
            f"❤️ {hp_bar} {hp_pct}%\n"
            f"🗡 버프 {len(buffs)}개\n"
        )
        buttons = [
            [InlineKeyboardButton("⚔️ 다음 층으로!", callback_data=f"dg_go_{user_id}")],
            [InlineKeyboardButton("🏳️ 포기", callback_data=f"dg_quit_{user_id}")],
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
            await query.answer("오늘 구매 한도를 초과했습니다.", show_alert=True)
            return

        success = await dq.buy_ticket_with_bp(user_id, bp_cost)
        if not success:
            await query.answer(f"BP가 부족합니다. ({bp_cost}BP 필요)", show_alert=True)
            return

        await query.answer(f"🎫 입장권 1장 구매! (-{bp_cost}BP)")
        text, kb = await _build_entry_screen(user_id)
        await _send_fresh(query, context, user_id, text, reply_markup=kb)
        return

    elif action == "quit":
        # 포기
        run = await dq.get_active_run(user_id)
        if run:
            await _finish_run(query, context, user_id, run, run["floor_reached"])
        else:
            await query.answer("진행 중인 던전이 없습니다.")
        return

    elif action == "retry":
        # 재도전 → 입장 화면
        await query.answer()
        text, kb = await _build_entry_screen(user_id)
        await _send_fresh(query, context, user_id, text, reply_markup=kb)
        return

    elif action == "rank":
        # 랭킹
        await query.answer()
        ranking = await dq.get_weekly_ranking(20)
        if not ranking:
            text = "📊 <b>이번 주 던전 랭킹</b>\n\n기록이 없습니다."
        else:
            lines = ["📊 <b>이번 주 던전 랭킹</b>\n"]
            for i, r in enumerate(ranking):
                medal = ["🥇", "🥈", "🥉"][i] if i < 3 else f"{i+1}."
                shiny = "✨" if r.get("is_shiny") else ""
                lines.append(
                    f"{medal} {r['display_name']} — <b>{r['floor_reached']}층</b> "
                    f"({shiny}{r['pokemon_name']} [{r.get('iv_grade', '?')}])"
                )
            text = "\n".join(lines)

        buttons = [[InlineKeyboardButton("🔙 돌아가기", callback_data=f"dg_back_{user_id}")]]
        await _send_fresh(query, context, user_id, text, reply_markup=InlineKeyboardMarkup(buttons))
        return

    else:
        await query.answer()


# ══════════════════════════════════════════════════════════
# 런 시작
# ══════════════════════════════════════════════════════════

async def _start_run(query, context, user_id: int, instance_id: int):
    """포켓몬 선택 → 입장권 차감 → 런 시작."""
    # 입장권 차감
    success = await dq.deduct_dungeon_ticket(user_id)
    if not success:
        await _send_fresh(query, context, user_id, "🎫 입장권이 부족합니다!")
        return

    # 포켓몬 로드 (소유권 검증)
    pokemon = await _load_pokemon(instance_id, user_id=user_id)
    if not pokemon:
        await dq.add_dungeon_tickets(user_id, 1)  # 환불
        await _send_fresh(query, context, user_id, "포켓몬을 찾을 수 없습니다.")
        return

    # 스탯 계산
    stats, types = ds.build_player_stats(pokemon)
    hp_mult = getattr(config, 'BATTLE_HP_MULTIPLIER', 1)
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
        theme=theme["name"],
        current_hp=max_hp,
        max_hp=max_hp,
    )

    st = _state(context)
    st["run_id"] = run_id

    # 시작 화면
    shiny = "✨" if pokemon.get("is_shiny") else ""
    type_str = "/".join(config.TYPE_EMOJI.get(t, "") + config.TYPE_NAME_KO.get(t, t) for t in types)
    cost = _get_pokemon_cost(pokemon["rarity"])
    freq = config.DUNGEON_BUFF_FREQUENCY.get(cost, 1)

    text = (
        f"🏰 <b>던전 입장!</b>\n\n"
        f"📍 {theme['emoji']} {theme['name']}\n"
        f"🐉 {shiny}<b>{pokemon['name_ko']}</b> [{grade}]\n"
        f"   {type_str} | 전투력 {calc_power(stats)}\n"
        f"   코스트 {cost} → 버프 {freq}층마다\n\n"
        f"❤️ HP: {max_hp}\n\n"
        f"준비되면 시작하세요!"
    )

    buttons = [
        [InlineKeyboardButton("⚔️ 1층 시작!", callback_data=f"dg_go_{user_id}")],
        [InlineKeyboardButton("🏳️ 포기", callback_data=f"dg_quit_{user_id}")],
    ]
    await _send_fresh(query, context, user_id, text, reply_markup=InlineKeyboardMarkup(buttons))
