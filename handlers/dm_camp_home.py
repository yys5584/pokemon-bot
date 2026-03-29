"""Camp DM handlers — 거점캠프, 배치, 필드 선택, 거점 변경."""

from datetime import timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import config
from database import camp_queries as cq
from database import queries
from services import camp_service as cs
from utils.helpers import rarity_badge, shiny_emoji, icon_emoji, _type_emoji
from utils.i18n import get_user_lang

from handlers.dm_camp_shared import (
    _is_duplicate_callback, _pokemon_name, _next_round_countdown,
    _build_camp_list_page, _build_camp2_list_page,
    CAMP_LIST_PAGE_SIZE, DM_PAGE_SIZE, _GUIDE_STEPS,
)


async def _build_dm_field_buttons(user_id: int, chat_id: int, fields: list[dict], camp: dict) -> tuple[str, InlineKeyboardMarkup]:
    """DM 배치: 필드 선택 화면 빌드."""
    level_info = cs.get_level_info(camp["level"])
    level_name = level_info[5]

    placements = await cq.get_user_placements_in_chat(chat_id, user_id)
    placed_fields = {p["field_id"] for p in placements}

    # 현재 라운드 보너스
    now = config.get_kst_now()
    current_round = cs._get_current_round_time(now)
    bonuses = await cq.get_round_bonus(chat_id, current_round)
    bonus_map = {b["field_id"]: b for b in bonuses}

    chat_room = await queries.get_chat_room(chat_id)
    chat_title = (chat_room.get("chat_title") if chat_room else None) or "캠프"

    lines = [
        f"🏕 배치하기 — {chat_title}",
        f"{icon_emoji('stationery')} Lv.{camp['level']} {level_name}",
        "",
    ]

    for f in fields:
        fi = config.CAMP_FIELDS.get(f["field_type"], {})
        emoji = fi.get("emoji", "🏕")
        name = fi.get("name", f["field_type"])
        mark = f" {icon_emoji('check')}" if f["id"] in placed_fields else ""

        bonus = bonus_map.get(f["id"])
        if bonus:
            pname = _pokemon_name(bonus["pokemon_id"])
            stat_name = config.CAMP_IV_STAT_NAMES.get(bonus["stat_type"], "")
            lines.append(f"{emoji} {name}{mark} — ⭐{pname} ({stat_name}{bonus['stat_value']}↑)")
        else:
            lines.append(f"{emoji} {name}{mark}")

    lines.append("")
    lines.append("배치할 필드를 선택하세요!")

    # 배치 중인 포켓몬 해제 버튼
    placed_map = {p["field_id"]: p for p in placements}

    buttons = []
    row = []
    for f in fields:
        fi = config.CAMP_FIELDS.get(f["field_type"], {})
        label = f"{fi.get('emoji', '🏕')} {fi.get('name', f['field_type'])}"
        row.append(InlineKeyboardButton(label, callback_data=f"cdm_fd_{user_id}_{f['id']}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    # 배치 해제 버튼 (배치 중인 필드가 있으면)
    for f in fields:
        p = placed_map.get(f["id"])
        if p:
            fi = config.CAMP_FIELDS.get(f["field_type"], {})
            shiny = "✨" if p.get("is_shiny") else ""
            buttons.append([InlineKeyboardButton(
                f"🔓 {fi.get('emoji', '')} {shiny}{p['name_ko']} 해제",
                callback_data=f"cdm_rm_{user_id}_{p['id']}",
            )])

    buttons.append([InlineKeyboardButton("❌ 닫기", callback_data=f"cdm_cancel_{user_id}")])
    return "\n".join(lines), InlineKeyboardMarkup(buttons)


async def _build_dm_pokemon_list(user_id: int, field_id: int, field_type: str, chat_id: int, page: int) -> tuple[str, InlineKeyboardMarkup]:
    """DM 배치: 필드에 배치 가능한 포켓몬 리스트 (보너스 추천순 정렬)."""
    pokemon_list = await queries.get_user_pokemon_list(user_id)
    fi = config.CAMP_FIELDS.get(field_type, {})

    # 타입 매칭 필터
    matching = [p for p in pokemon_list if cs.pokemon_matches_field(p["pokemon_id"], field_type)]

    if not matching:
        text = f"{fi.get('emoji', '🏕')} {fi.get('name', field_type)} — 배치 가능한 포켓몬이 없습니다."
        buttons = [[InlineKeyboardButton("◀ 돌아가기", callback_data=f"cdm_fback_{user_id}_{chat_id}")]]
        return text, InlineKeyboardMarkup(buttons)

    # 현재 라운드 보너스로 점수 미리보기 + 정렬
    now = config.get_kst_now()
    current_round = cs._get_current_round_time(now)
    bonuses = await cq.get_round_bonus(chat_id, current_round)
    bonus = None
    for b in bonuses:
        if b["field_id"] == field_id:
            bonus = b
            break

    scored = []
    for p in matching:
        ivs = {
            "iv_hp": p.get("iv_hp", 0), "iv_atk": p.get("iv_atk", 0),
            "iv_def": p.get("iv_def", 0), "iv_spa": p.get("iv_spa", 0),
            "iv_spdef": p.get("iv_spdef", 0), "iv_spd": p.get("iv_spd", 0),
        }
        score, desc = cs.calc_placement_score(
            p["pokemon_id"], bool(p.get("is_shiny")), ivs,
            bonus["pokemon_id"] if bonus else None,
            bonus["stat_type"] if bonus else None,
            bonus["stat_value"] if bonus else None,
        )
        scored.append({**p, "_score": score, "_desc": desc})

    scored.sort(key=lambda x: (-x["_score"], x["name_ko"]))

    total_pages = max(1, (len(scored) + DM_PAGE_SIZE - 1) // DM_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * DM_PAGE_SIZE
    end = min(start + DM_PAGE_SIZE, len(scored))
    page_items = scored[start:end]

    lines = [
        f"{fi.get('emoji', '🏕')} {fi.get('name', field_type)} — 포켓몬 선택 [{page + 1}/{total_pages}]",
        f"타입: {'/'.join(fi.get('types', []))}",
    ]

    if bonus:
        pname = _pokemon_name(bonus["pokemon_id"])
        stat_name = config.CAMP_IV_STAT_NAMES.get(bonus["stat_type"], "")
        lines.append(f"⭐ 보너스: {pname} ({stat_name} {bonus['stat_value']}↑)")
    lines.append("")

    for i, p in enumerate(page_items):
        num = start + i + 1
        shiny = shiny_emoji() if p.get("is_shiny") else ""
        rarity_tag = rarity_badge(p.get("rarity", ""))
        score_tag = f" ({p['_desc']})" if p["_score"] > 1 else ""
        lines.append(f"{num}. {shiny}{rarity_tag}{p['name_ko']}{score_tag}")

    buttons = []
    row = []
    for i, p in enumerate(page_items):
        idx = start + i
        label = f"{idx + 1}. {p['name_ko']}"
        row.append(InlineKeyboardButton(
            label,
            callback_data=f"cdm_pk_{user_id}_{field_id}_{p['id']}",
        ))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    # 페이지네이션
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("◀ 이전", callback_data=f"cdm_pp_{user_id}_{field_id}_{page - 1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("다음 ▶", callback_data=f"cdm_pp_{user_id}_{field_id}_{page + 1}"))
    if nav_row:
        buttons.append(nav_row)

    buttons.append([InlineKeyboardButton("◀ 필드 선택", callback_data=f"cdm_fback_{user_id}_{chat_id}")])
    return "\n".join(lines), InlineKeyboardMarkup(buttons)


async def home_camp_handler(update, context):
    """DM '거점캠프' — 거점 상세 현황 + 보너스 조건 표시."""
    user_id = update.effective_user.id
    user = await queries.get_user(user_id)
    if not user:
        await update.message.reply_text("먼저 포켓몬을 잡아보세요!")
        return

    settings = await cq.get_user_camp_settings(user_id)

    # 거점 미설정 → 캠프 목록 표시
    if not settings or not settings.get("home_chat_id"):
        camps = await cq.get_available_camps()
        if not camps:
            await update.message.reply_text(
                "🏕 거점캠프\n\n"
                "활성화된 캠프가 없습니다.\n"
                "채팅방에서 '캠프개설'로 캠프를 만들어보세요!"
            )
            return

        text, markup = _build_camp_list_page(camps, user_id, 0, is_change=False)
        await update.message.reply_text(text, reply_markup=markup)
        return

    # 거점 설정됨 → 상세 현황 표시
    chat_id = settings["home_chat_id"]
    camp = await cq.get_camp(chat_id)
    if not camp:
        await update.message.reply_text("거점 캠프가 삭제되었습니다. 새 거점을 설정해주세요.")
        return

    chat_room = await queries.get_chat_room(chat_id)
    chat_title = (chat_room.get("chat_title") if chat_room else None) or "채팅방"

    fields = await cq.get_fields(chat_id)
    level_info = cs.get_level_info(camp["level"])

    # 현재 라운드 보너스
    now = config.get_kst_now()
    current_round = cs._get_current_round_time(now)
    bonuses = await cq.get_round_bonus(chat_id, current_round)
    bonus_map = {b["field_id"]: b for b in bonuses}

    # 유저 배치 현황
    placements = await cq.get_user_placements_in_chat(chat_id, user_id)
    placed_map = {p["field_id"]: p for p in placements}

    lines = [
        f"🏕 거점캠프 — {chat_title}",
    ]

    # invite link
    if chat_room and chat_room.get("invite_link"):
        lines.append(f"👉 {chat_room['invite_link']}")

    lines.append("")
    lines.append(f"{icon_emoji('stationery')} 캠프 레벨: Lv.{camp['level']} {level_info[5]}")

    for f in fields:
        fi = config.CAMP_FIELDS.get(f["field_type"], {})
        emoji = fi.get("emoji", "🏕")
        name = fi.get("name", f["field_type"])

        placed = placed_map.get(f["id"])
        if placed:
            shiny = shiny_emoji() if placed.get("is_shiny") else ""
            lines.append(f"{emoji} {name} — {shiny}{placed['name_ko']} 배치 중 ({placed['score']}점)")
        else:
            lines.append(f"{emoji} {name} — 비어있음")

    lines.append("")
    lines.append(f"{icon_emoji('bookmark')} 다음 정산: {_next_round_countdown()}")

    # 보너스 조건
    if bonuses:
        lines.append("")
        lines.append("🔄 라운드 보너스 조건:")
        for f in fields:
            bonus = bonus_map.get(f["id"])
            if bonus:
                fi = config.CAMP_FIELDS.get(f["field_type"], {})
                emoji = fi.get("emoji", "🏕")
                name = fi.get("name", f["field_type"])
                pname = _pokemon_name(bonus["pokemon_id"])
                stat_name = config.CAMP_IV_STAT_NAMES.get(bonus["stat_type"], "")
                lines.append(f"  {emoji} {name}: {pname} ({stat_name} {bonus['stat_value']}↑) → 7점")

    lines.append("")

    # 2번째 거점 표시
    if settings.get("home_chat_id_2"):
        lines.append("")
        chat_id_2 = settings["home_chat_id_2"]
        camp2 = await cq.get_camp(chat_id_2)
        if camp2:
            chat_room2 = await queries.get_chat_room(chat_id_2)
            chat_title2 = (chat_room2.get("chat_title") if chat_room2 else None) or "채팅방"
            lv2 = camp2["level"]
            level_info2 = cs.get_level_info(lv2)
            lines.append(f"🏠 2번째 거점 — {chat_title2}")
            lines.append(f"{icon_emoji('stationery')} 캠프 레벨: Lv.{lv2} {level_info2[5]}")

    lines.append("")

    # 버튼
    buttons = []
    buttons.append([InlineKeyboardButton("🏕 배치하기", callback_data=f"cdm_place_{user_id}")])

    # 캠프 소유자 → 필드 관리 버튼
    if camp.get("created_by") == user_id:
        max_fields = level_info[1]
        field_btns = []
        if len(fields) < max_fields:
            field_btns.append(InlineKeyboardButton("🆕 필드 추가", callback_data=f"cdm_addfd_{user_id}_{chat_id}"))
        if fields:
            field_btns.append(InlineKeyboardButton("🔄 필드 변경", callback_data=f"cdm_chgfd_{user_id}_{chat_id}"))
        if field_btns:
            buttons.append(field_btns)

    # 거점 변경 가능 여부
    if settings.get("home_camp_set_at"):
        elapsed = (now - settings["home_camp_set_at"]).total_seconds()
        cooldown = config.CAMP_HOME_COOLDOWN
        if elapsed >= cooldown:
            buttons.append([InlineKeyboardButton("🔄 거점변경", callback_data=f"cdm_chghome_{user_id}")])
        else:
            change_date = (settings["home_camp_set_at"] + timedelta(days=7)).strftime("%m/%d")
            buttons.append([InlineKeyboardButton(f"🔒 거점변경 ({change_date} 이후)", callback_data=f"cdm_noop_{user_id}")])
    else:
        buttons.append([InlineKeyboardButton("🔄 거점변경", callback_data=f"cdm_chghome_{user_id}")])

    # 2번째 거점 설정/해제 버튼 (구독자: 활성, 비구독자: 잠금)
    from services.subscription_service import get_user_tier
    tier = await get_user_tier(user_id)
    has_dual = config.SUBSCRIPTION_TIERS.get(tier, {}).get("benefits", {}).get("dual_home_camp")
    if settings.get("home_chat_id_2"):
        buttons.append([InlineKeyboardButton("🏠 2번째 거점 해제", callback_data=f"cdm_delhome2_{user_id}")])
    elif has_dual:
        buttons.append([InlineKeyboardButton("🏠 2번째 거점 설정", callback_data=f"cdm_sethome2_{user_id}")])
    else:
        buttons.append([InlineKeyboardButton("🔒 2번째 거점 설정 (프리미엄)", callback_data=f"cdm_sethome2_locked_{user_id}")])

    await update.message.reply_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")


# ═══════════════════════════════════════════════════════
# 콜백 핸들러: 거점/배치 관련
# ═══════════════════════════════════════════════════════

async def _handle_home2(query, parts):
    """cdm_home2_{uid}_{chat_id} — 2번째 거점 설정 실행."""
    uid = int(parts[2])
    target_chat_id = int(parts[3])
    if query.from_user.id != uid:
        await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
        return

    success, msg = await cs.set_home_camp_2(uid, target_chat_id)
    if success:
        await query.answer(msg)
        try:
            await query.edit_message_text(msg, parse_mode="HTML")
        except Exception:
            pass
    else:
        await query.answer(msg, show_alert=True)


async def _handle_home(query, parts):
    """cdm_home_{uid}_{chat_id} — 거점 설정."""
    uid = int(parts[2])
    target_chat_id = int(parts[3])
    if query.from_user.id != uid:
        await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
        return

    success, msg = await cs.set_home_camp(uid, target_chat_id)
    if success and msg == "FIRST_HOME":
        # 첫 거점 설정 → 캠프 가이드 시작
        await query.answer("거점 캠프가 설정되었습니다!")
        buttons = [[
            InlineKeyboardButton("다음 ▶", callback_data=f"cdm_guide_{uid}_1"),
            InlineKeyboardButton("건너뛰기", callback_data=f"cdm_cancel_{uid}"),
        ]]
        text = "🏠 거점 캠프가 설정되었습니다!\n\n" + _GUIDE_STEPS[0]
        try:
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")
        except Exception:
            pass
    elif success:
        await query.answer(msg)
        try:
            await query.edit_message_text(msg, parse_mode="HTML")
        except Exception:
            pass
    else:
        await query.answer(msg, show_alert=True)


async def _handle_chghome(query, parts):
    """cdm_chghome_{uid} — 거점 변경 목록."""
    uid = int(parts[2])
    if query.from_user.id != uid:
        await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
        return

    camps = await cq.get_available_camps()
    settings = await cq.get_user_camp_settings(uid)
    current_home = settings.get("home_chat_id") if settings else None

    text, markup = _build_camp_list_page(camps, uid, 0, is_change=True, exclude_chat_id=current_home)
    await query.answer()
    try:
        await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
    except Exception:
        pass


async def _handle_place(query, parts, context):
    """cdm_place_{uid} — DM에서 거점캠프 필드 선택."""
    uid = int(parts[2])
    if query.from_user.id != uid:
        await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
        return

    settings = await cq.get_user_camp_settings(uid)
    if not settings or not settings.get("home_chat_id"):
        await query.answer("먼저 거점캠프를 설정하세요!", show_alert=True)
        return

    # 2번째 거점이 있으면 캠프 선택 화면 표시
    if settings.get("home_chat_id_2"):
        home1 = settings["home_chat_id"]
        home2 = settings["home_chat_id_2"]
        room1 = await queries.get_chat_room(home1)
        room2 = await queries.get_chat_room(home2)
        t1 = (room1.get("chat_title") if room1 else None) or "거점1"
        t2 = (room2.get("chat_title") if room2 else None) or "거점2"
        text = "🏕 배치할 캠프를 선택하세요!"
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"🏠 {t1}", callback_data=f"cdm_plc_{uid}_{home1}")],
            [InlineKeyboardButton(f"🏠 {t2}", callback_data=f"cdm_plc_{uid}_{home2}")],
            [InlineKeyboardButton("❌ 닫기", callback_data=f"cdm_cancel_{uid}")],
        ])
        await query.answer()
        try:
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
        except Exception:
            pass
        return

    chat_id = settings["home_chat_id"]
    camp = await cq.get_camp(chat_id)
    if not camp:
        await query.answer("거점 캠프가 삭제되었습니다.", show_alert=True)
        return

    fields = await cq.get_fields(chat_id)
    if not fields:
        await query.answer("캠프에 열린 필드가 없습니다.", show_alert=True)
        return

    await query.answer()
    text, markup = await _build_dm_field_buttons(uid, chat_id, fields, camp)
    try:
        await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
    except Exception:
        pass


async def _handle_plc(query, parts):
    """cdm_plc_{uid}_{chat_id} — DM에서 특정 거점 캠프 필드 선택 (듀얼 거점)."""
    uid = int(parts[2])
    target_chat_id = int(parts[3])
    if query.from_user.id != uid:
        await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
        return

    camp = await cq.get_camp(target_chat_id)
    if not camp:
        await query.answer("거점 캠프가 삭제되었습니다.", show_alert=True)
        return

    fields = await cq.get_fields(target_chat_id)
    if not fields:
        await query.answer("캠프에 열린 필드가 없습니다.", show_alert=True)
        return

    await query.answer()
    text, markup = await _build_dm_field_buttons(uid, target_chat_id, fields, camp)
    try:
        await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
    except Exception:
        pass


async def _handle_rm(query, parts):
    """cdm_rm_{uid}_{placement_id} — DM 배치 해제."""
    uid = int(parts[2])
    placement_id = int(parts[3])
    if query.from_user.id != uid:
        await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
        return

    removed = await cq.remove_placement(placement_id, uid)
    if removed:
        # 일일 배치 횟수 복구
        await cq.decrement_daily_placement(uid)
        await query.answer("배치를 해제했습니다!")
    else:
        await query.answer("이미 해제되었습니다.", show_alert=True)

    # 필드 선택 화면 새로고침 (어떤 거점이든 표시)
    settings = await cq.get_user_camp_settings(uid)
    home_ids = []
    if settings:
        if settings.get("home_chat_id"):
            home_ids.append(settings["home_chat_id"])
        if settings.get("home_chat_id_2"):
            home_ids.append(settings["home_chat_id_2"])
    if home_ids:
        # 첫 번째 거점의 필드 화면으로 복귀 (단일 거점인 경우)
        chat_id = home_ids[0]
        camp = await cq.get_camp(chat_id)
        if camp:
            fields = await cq.get_fields(chat_id)
            text, markup = await _build_dm_field_buttons(uid, chat_id, fields, camp)
            try:
                await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
            except Exception:
                pass


async def _handle_fd(query, parts):
    """cdm_fd_{uid}_{field_id} — DM 필드 선택 → 포켓몬 리스트."""
    uid = int(parts[2])
    field_id = int(parts[3])
    if query.from_user.id != uid:
        await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
        return

    field = await cq.get_field_by_id(field_id)
    if not field:
        await query.answer("필드를 찾을 수 없습니다.", show_alert=True)
        return

    await query.answer()
    text, markup = await _build_dm_pokemon_list(uid, field_id, field["field_type"], field["chat_id"], 0)
    try:
        await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
    except Exception:
        pass


async def _handle_pk(query, parts, context):
    """cdm_pk_{uid}_{field_id}_{instance_id} — DM에서 포켓몬 배치."""
    uid = int(parts[2])
    field_id = int(parts[3])
    instance_id = int(parts[4])
    if query.from_user.id != uid:
        await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
        return

    field = await cq.get_field_by_id(field_id)
    if not field:
        await query.answer("필드를 찾을 수 없습니다.", show_alert=True)
        return
    chat_id = field["chat_id"]

    dex_count = await queries.count_pokedex(uid)
    try:
        member_count = await context.bot.get_chat_member_count(chat_id)
    except Exception:
        member_count = 100

    success, msg = await cs.try_place_pokemon(
        chat_id, field_id, uid, instance_id, member_count, dex_count,
    )

    if success:
        await query.answer(msg)
    else:
        await query.answer(msg, show_alert=True)

    # 필드 선택 화면으로 복귀
    camp = await cq.get_camp(chat_id)
    if camp:
        fields = await cq.get_fields(chat_id)
        text, markup = await _build_dm_field_buttons(uid, chat_id, fields, camp)
        try:
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
        except Exception:
            pass


async def _handle_pp(query, parts):
    """cdm_pp_{uid}_{field_id}_{page} — DM 포켓몬 리스트 페이지네이션."""
    uid = int(parts[2])
    field_id = int(parts[3])
    page = int(parts[4])
    if query.from_user.id != uid:
        await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
        return

    field = await cq.get_field_by_id(field_id)
    if not field:
        await query.answer("필드를 찾을 수 없습니다.", show_alert=True)
        return

    await query.answer()
    text, markup = await _build_dm_pokemon_list(uid, field_id, field["field_type"], field["chat_id"], page)
    try:
        await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
    except Exception:
        pass


async def _handle_fback(query, parts):
    """cdm_fback_{uid}_{chat_id} — DM 필드 선택으로 복귀."""
    uid = int(parts[2])
    if query.from_user.id != uid:
        await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
        return

    # chat_id가 콜백에 포함된 경우 사용, 아닌 경우 home_chat_id 기본값
    if len(parts) >= 4:
        chat_id = int(parts[3])
    else:
        settings = await cq.get_user_camp_settings(uid)
        if not settings or not settings.get("home_chat_id"):
            await query.answer()
            return
        chat_id = settings["home_chat_id"]

    camp = await cq.get_camp(chat_id)
    if not camp:
        await query.answer()
        return

    fields = await cq.get_fields(chat_id)
    await query.answer()
    text, markup = await _build_dm_field_buttons(uid, chat_id, fields, camp)
    try:
        await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
    except Exception:
        pass


async def _handle_clp(query, parts):
    """cdm_clp_{uid}_{mode}_{page} — 캠프 목록 페이지네이션."""
    uid = int(parts[2])
    mode = parts[3]  # "set" or "chg"
    page = int(parts[4])
    if query.from_user.id != uid:
        await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
        return

    camps = await cq.get_available_camps()
    if mode == "chg":
        settings = await cq.get_user_camp_settings(uid)
        current_home = settings.get("home_chat_id") if settings else None
        text, markup = _build_camp_list_page(camps, uid, page, is_change=True, exclude_chat_id=current_home)
    else:
        text, markup = _build_camp_list_page(camps, uid, page, is_change=False)

    await query.answer()
    try:
        await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
    except Exception:
        pass


async def _handle_c2p(query, parts):
    """cdm_c2p_{uid}_{page} — 2번째 거점 목록 페이지네이션."""
    uid = int(parts[2])
    page = int(parts[3])
    if query.from_user.id != uid:
        await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
        return

    settings = await cq.get_user_camp_settings(uid)
    current_home = settings.get("home_chat_id") if settings else None
    camps = await cq.get_available_camps()
    filtered = [c for c in camps if c["chat_id"] != current_home]

    text, markup = _build_camp2_list_page(filtered, uid, page)
    await query.answer()
    try:
        await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
    except Exception:
        pass


async def _handle_sethome2_locked(query, parts):
    """cdm_sethome2_locked_{uid} — 비구독자 잠금 안내."""
    uid = int(parts[3])
    if query.from_user.id != uid:
        await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
        return
    await query.answer("🔒 프리미엄 구독 시 2번째 거점을 설정할 수 있습니다!\nDM에서 '프리미엄'을 입력해 구독 정보를 확인하세요.", show_alert=True)


async def _handle_sethome2(query, parts):
    """cdm_sethome2_{uid} — 2번째 거점 설정 목록."""
    uid = int(parts[2])
    if query.from_user.id != uid:
        await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
        return

    await query.answer()
    settings = await cq.get_user_camp_settings(uid)
    current_home = settings.get("home_chat_id") if settings else None

    camps = await cq.get_available_camps()
    # 1번째 거점 제외
    filtered = [c for c in camps if c["chat_id"] != current_home]

    if not filtered:
        try:
            await query.edit_message_text("설정 가능한 다른 캠프가 없습니다.")
        except Exception:
            pass
        return

    page = 0
    text, markup = _build_camp2_list_page(filtered, uid, page)

    try:
        await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
    except Exception:
        pass


async def _handle_delhome2(query, parts):
    """cdm_delhome2_{uid} — 2번째 거점 해제."""
    uid = int(parts[2])
    if query.from_user.id != uid:
        await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
        return

    success, msg = await cs.remove_home_camp_2(uid)
    await query.answer(msg, show_alert=True)
    try:
        await query.edit_message_text(msg, parse_mode="HTML")
    except Exception:
        pass


# ═══════════════════════════════════════════════════════
# DM 필드 관리 (캠프 소유자 전용)
# ═══════════════════════════════════════════════════════

async def _handle_addfd(query, parts):
    """cdm_addfd_{uid}_{chat_id} — DM에서 필드 추가 선택."""
    uid = int(parts[2])
    chat_id = int(parts[3])
    if query.from_user.id != uid:
        await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
        return

    camp = await cq.get_camp(chat_id)
    if not camp or camp.get("created_by") != uid:
        await query.answer("캠프 소유자만 가능합니다!", show_alert=True)
        return

    fields = await cq.get_fields(chat_id)
    existing_types = {f["field_type"] for f in fields}

    buttons = []
    row = []
    for fkey, finfo in config.CAMP_FIELDS.items():
        if fkey in existing_types:
            continue
        label = f"{finfo['emoji']} {finfo['name']}"
        row.append(InlineKeyboardButton(label, callback_data=f"cdm_newfd_{uid}_{chat_id}_{fkey}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("❌ 닫기", callback_data=f"cdm_cancel_{uid}")])

    await query.answer()
    try:
        await query.edit_message_text("🆕 추가할 필드를 선택하세요!", reply_markup=InlineKeyboardMarkup(buttons))
    except Exception:
        pass


async def _handle_newfd(query, parts):
    """cdm_newfd_{uid}_{chat_id}_{field_type} — DM에서 필드 추가 실행."""
    uid = int(parts[2])
    chat_id = int(parts[3])
    field_type = parts[4]
    if query.from_user.id != uid:
        await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
        return

    camp = await cq.get_camp(chat_id)
    if not camp or camp.get("created_by") != uid:
        await query.answer("캠프 소유자만 가능합니다!", show_alert=True)
        return

    success, msg = await cs.add_new_field(chat_id, field_type)
    await query.answer(msg, show_alert=True)
    try:
        await query.edit_message_text(msg, parse_mode="HTML")
    except Exception:
        pass


async def _handle_chgfd(query, parts):
    """cdm_chgfd_{uid}_{chat_id} — DM에서 필드 변경 선택."""
    uid = int(parts[2])
    chat_id = int(parts[3])
    if query.from_user.id != uid:
        await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
        return

    camp = await cq.get_camp(chat_id)
    if not camp or camp.get("created_by") != uid:
        await query.answer("캠프 소유자만 가능합니다!", show_alert=True)
        return

    fields = await cq.get_fields(chat_id)
    buttons = []
    for f in fields:
        fi = config.CAMP_FIELDS.get(f["field_type"], {})
        label = f"{fi.get('emoji', '🏕')} {fi.get('name', f['field_type'])} 변경"
        buttons.append([InlineKeyboardButton(label, callback_data=f"cdm_chgsel_{uid}_{chat_id}_{f['id']}")])
    buttons.append([InlineKeyboardButton("❌ 닫기", callback_data=f"cdm_cancel_{uid}")])

    await query.answer()
    try:
        await query.edit_message_text(
            "🔄 변경할 필드를 선택하세요!\n⚠️ 변경 시 해당 필드의 배치가 초기화됩니다.",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
    except Exception:
        pass


async def _handle_chgsel(query, parts):
    """cdm_chgsel_{uid}_{chat_id}_{field_id} — 변경 대상 필드 선택 후 새 타입 선택."""
    uid = int(parts[2])
    chat_id = int(parts[3])
    field_id = int(parts[4])
    if query.from_user.id != uid:
        await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
        return

    camp = await cq.get_camp(chat_id)
    if not camp or camp.get("created_by") != uid:
        await query.answer("캠프 소유자만 가능합니다!", show_alert=True)
        return

    fields = await cq.get_fields(chat_id)
    existing_types = {f["field_type"] for f in fields}

    buttons = []
    row = []
    for fkey, finfo in config.CAMP_FIELDS.items():
        if fkey in existing_types:
            continue
        label = f"{finfo['emoji']} {finfo['name']}"
        row.append(InlineKeyboardButton(label, callback_data=f"cdm_chgto_{uid}_{chat_id}_{field_id}_{fkey}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("❌ 닫기", callback_data=f"cdm_cancel_{uid}")])

    await query.answer()
    try:
        await query.edit_message_text("🔄 변경할 새 필드 타입을 선택하세요!", reply_markup=InlineKeyboardMarkup(buttons))
    except Exception:
        pass


async def _handle_chgto(query, parts):
    """cdm_chgto_{uid}_{chat_id}_{field_id}_{field_type} — 필드 변경 실행."""
    uid = int(parts[2])
    chat_id = int(parts[3])
    field_id = int(parts[4])
    field_type = parts[5]
    if query.from_user.id != uid:
        await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
        return

    camp = await cq.get_camp(chat_id)
    if not camp or camp.get("created_by") != uid:
        await query.answer("캠프 소유자만 가능합니다!", show_alert=True)
        return

    success, msg = await cs.change_field_type(chat_id, field_id, field_type)
    await query.answer(msg, show_alert=True)
    try:
        await query.edit_message_text(msg, parse_mode="HTML")
    except Exception:
        pass
