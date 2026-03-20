"""Camp DM handlers — 캠프 관리, 가이드, 내캠프, MVP, 알림, 방문, 기타."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import config
from database import camp_queries as cq
from database import queries
from services import camp_service as cs
from utils.helpers import rarity_badge, shiny_emoji, icon_emoji

from handlers.dm_camp_shared import (
    _is_duplicate_callback, _pokemon_name, _next_round_countdown,
    _build_camp_list_page, _GUIDE_STEPS, VISIT_PAGE_SIZE,
)


async def camp_guide_handler(update, context):
    """DM '캠프가이드' — 캠프 튜토리얼 시작."""
    user_id = update.effective_user.id

    buttons = [[
        InlineKeyboardButton("다음 ▶", callback_data=f"cdm_guide_{user_id}_1"),
        InlineKeyboardButton("건너뛰기", callback_data=f"cdm_cancel_{user_id}"),
    ]]
    await update.message.reply_text(
        _GUIDE_STEPS[0],
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def my_camp_handler(update, context):
    """DM '내캠프' — 배치 현황 + 조각 + 결정."""
    user_id = update.effective_user.id
    user = await queries.get_user(user_id)
    if not user:
        await update.message.reply_text("먼저 포켓몬을 잡아보세요!")
        return

    summary = await cs.get_user_camp_summary(user_id)

    lines = ["🏕 내 캠프 현황", ""]

    # 거점 캠프
    if summary["home_camp"]:
        chat_room = await queries.get_chat_room(summary["home_camp"])
        title = (chat_room.get("chat_title") if chat_room else None) or "알 수 없음"
        lines.append(f"🏠 거점1: {title}")
    else:
        lines.append("🏠 거점: 미설정 ('거점캠프' 입력)")

    # 2번째 거점
    settings_for_home2 = await cq.get_user_camp_settings(user_id)
    if settings_for_home2 and settings_for_home2.get("home_chat_id_2"):
        chat_room2 = await queries.get_chat_room(settings_for_home2["home_chat_id_2"])
        title2 = (chat_room2.get("chat_title") if chat_room2 else None) or "알 수 없음"
        lines.append(f"🏠 거점2: {title2}")

    # 조각
    frags = summary["fragments"]
    if frags:
        total = sum(frags.values())
        lines.append(f"\n🧩 조각 (총 {total}개)")
        for fkey, finfo in config.CAMP_FIELDS.items():
            amount = frags.get(fkey, 0)
            if amount > 0:
                lines.append(f"  {finfo['emoji']} {finfo['name']}: {amount}개")
    else:
        lines.append("\n🧩 조각: 없음")

    # 결정
    crystals = summary["crystals"]
    if crystals["crystal"] > 0 or crystals["rainbow"] > 0:
        lines.append(f"\n💎 결정: {crystals['crystal']}개")
        if crystals["rainbow"] > 0:
            lines.append(f"🌈 무지개 결정: {crystals['rainbow']}개")

    # 전환 대기 중
    pendings = summary.get("shiny_pendings", [])
    if pendings:
        lines.append(f"\n✨ 전환 대기 중 ({len(pendings)}건)")
        import config as _cfg
        now = _cfg.get_kst_now()
        for p in pendings[:3]:
            pname = _pokemon_name(p["pokemon_id"])
            remaining = (p["completes_at"] - now).total_seconds()
            if remaining <= 0:
                lines.append(f"  • {pname} — 곧 완료!")
            else:
                h = int(remaining // 3600)
                m = int((remaining % 3600) // 60)
                lines.append(f"  • {pname} — {h}시간 {m}분 남음")
        if len(pendings) > 3:
            lines.append(f"  ... 외 {len(pendings) - 3}건")

    lines.append("\n")

    # 배치 현황
    placements = summary["placements"]
    if placements:
        lines.append(f"{icon_emoji('bookmark')} 배치 현황 ({len(placements)}마리)")
        for p in placements:
            fi = config.CAMP_FIELDS.get(p.get("field_type", ""), {})
            shiny = shiny_emoji() if p.get("is_shiny") else ""
            lines.append(f"  {fi.get('emoji', '🏕')} {shiny}{p['name_ko']} ({p['score']}점)")
    else:
        lines.append(f"{icon_emoji('bookmark')} 배치: 없음")

    lines.append("")

    # 힌트
    hints = []
    total_frags = sum(frags.values()) if frags else 0
    if total_frags >= 12:
        hints.append(f"{shiny_emoji()} '이로치전환'으로 이로치 변환!")
    if crystals["crystal"] == 0 and total_frags > 0:
        hints.append("🔨 '분해'로 이로치를 결정으로!")
    if hints:
        lines.extend(hints)

    # 버튼
    buttons = [
        [
            InlineKeyboardButton("🏕 배치하기", callback_data=f"cdm_place_{user_id}"),
            InlineKeyboardButton("✨ 이로치전환", callback_data=f"cdm_hub_convert_{user_id}"),
        ],
        [
            InlineKeyboardButton("🔨 분해", callback_data=f"cdm_hub_decompose_{user_id}"),
            InlineKeyboardButton("🏠 거점캠프", callback_data=f"cdm_hub_home_{user_id}"),
        ],
        [
            InlineKeyboardButton("👣 방문하기", callback_data=f"cdm_visitlang_{user_id}"),
        ],
    ]

    # 소유자면 캠프 관리 버튼 추가
    owned_camp = await cq.get_camp_by_owner(user_id)
    if owned_camp:
        buttons.append([
            InlineKeyboardButton("⚙️ 캠프 관리", callback_data=f"cdm_hub_manage_{user_id}"),
        ])

    buttons.append([InlineKeyboardButton("❌ 닫기", callback_data=f"cdm_cancel_{user_id}")])

    await update.message.reply_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="HTML",
    )


async def camp_notify_handler(update, context):
    """DM '캠프알림' — 정산 DM 알림 on/off 토글."""
    user_id = update.effective_user.id
    new_state = await cq.toggle_camp_notify(user_id)
    if new_state:
        await update.message.reply_text("🔔 캠프 정산 알림이 켜졌습니다.")
    else:
        await update.message.reply_text("🔕 캠프 정산 알림이 꺼졌습니다.")


# ═══════════════════════════════════════════════════════
# 콜백 핸들러: 관리/가이드/내캠프/MVP/방문/기타
# ═══════════════════════════════════════════════════════

async def _handle_guide(query, parts):
    """cdm_guide_{uid}_{step} — 캠프 가이드 페이지."""
    uid = int(parts[2])
    step = int(parts[3])
    if query.from_user.id != uid:
        await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
        return

    if step >= len(_GUIDE_STEPS):
        await query.answer()
        try:
            await query.edit_message_text(_GUIDE_STEPS[-1], parse_mode="HTML")
        except Exception:
            pass
        return

    await query.answer()
    buttons = []
    if step < len(_GUIDE_STEPS) - 1:
        buttons.append([
            InlineKeyboardButton("다음 ▶", callback_data=f"cdm_guide_{uid}_{step + 1}"),
            InlineKeyboardButton("건너뛰기", callback_data=f"cdm_cancel_{uid}"),
        ])

    try:
        await query.edit_message_text(
            _GUIDE_STEPS[step],
            reply_markup=InlineKeyboardMarkup(buttons) if buttons else None,
            parse_mode="HTML",
        )
    except Exception:
        pass


async def _handle_noop(query, parts):
    """cdm_noop_{uid} — 아무 동작 없음."""
    await query.answer("거점 변경 쿨다운 중입니다.", show_alert=True)


async def _handle_hub_mycamp(query, parts, context):
    """cdm_hub_mycamp_{uid} — 내캠프 (허브에서)."""
    uid = int(parts[3])
    if query.from_user.id != uid:
        await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
        return

    await query.answer()
    summary = await cs.get_user_camp_summary(uid)

    lines = [f"{icon_emoji('pokecenter')} <b>내 캠프 현황</b>", ""]

    if summary["home_camp"]:
        chat_room = await queries.get_chat_room(summary["home_camp"])
        camp = await cq.get_camp(summary["home_camp"])
        title = (chat_room.get("chat_title") if chat_room else None) or "알 수 없음"
        lines.append(f"🏠 거점1: {title}")
        if camp:
            lv = camp["level"]
            xp = camp["xp"]
            level_info = cs.get_level_info(lv)
            if lv < config.CAMP_MAX_LEVEL:
                xp_needed = cs.get_level_info(lv + 1)[4]
            else:
                xp_needed = level_info[4]  # max level
            lines.append(f"{icon_emoji('stationery')} Lv.{lv} {level_info[5]} — XP {xp}/{xp_needed}")

            # 필드별 슬롯 현황
            slot_info = await cq.get_field_slot_info(summary["home_camp"])
            if slot_info:
                try:
                    member_count = await context.bot.get_chat_member_count(summary["home_camp"])
                except Exception:
                    member_count = 100
                total_slots = cs.calc_total_slots(lv, member_count)
                lines.append("")
                for si in slot_info:
                    fi = config.CAMP_FIELDS.get(si["field_type"], {})
                    cnt = si["placed_count"]
                    status = "🔴 풀방" if cnt >= total_slots else f"🟢 {total_slots - cnt}자리"
                    lines.append(f"  {fi.get('emoji', '🏕')} {fi.get('name', '')}: {cnt}/{total_slots} ({status})")
    else:
        lines.append("🏠 거점: 미설정")

    # 2번째 거점
    settings_mycamp = await cq.get_user_camp_settings(uid)
    if settings_mycamp and settings_mycamp.get("home_chat_id_2"):
        chat_room2 = await queries.get_chat_room(settings_mycamp["home_chat_id_2"])
        camp2 = await cq.get_camp(settings_mycamp["home_chat_id_2"])
        title2 = (chat_room2.get("chat_title") if chat_room2 else None) or "알 수 없음"
        lv2 = camp2["level"] if camp2 else 1
        lines.append(f"\n🏠 거점2: {title2} (Lv.{lv2})")

    frags = summary["fragments"]
    if frags:
        total = sum(frags.values())
        lines.append(f"\n{icon_emoji('gotcha')} 조각 (총 {total}개)")
        for fkey, finfo in config.CAMP_FIELDS.items():
            amount = frags.get(fkey, 0)
            if amount > 0:
                lines.append(f"  {finfo['emoji']} {finfo['name']}: {amount}개")
    else:
        lines.append(f"\n{icon_emoji('gotcha')} 조각: 없음")

    crystals = summary["crystals"]
    if crystals["crystal"] > 0 or crystals["rainbow"] > 0:
        lines.append(f"\n{icon_emoji('crystal')} 결정: {crystals['crystal']}개")
        if crystals["rainbow"] > 0:
            lines.append(f"🌈 무지개 결정: {crystals['rainbow']}개")

    pendings = summary.get("shiny_pendings", [])
    if pendings:
        import config as _cfg
        now = _cfg.get_kst_now()
        lines.append(f"\n✨ 전환 대기 중 ({len(pendings)}건)")
        for p in pendings[:3]:
            pname = _pokemon_name(p["pokemon_id"])
            remaining = (p["completes_at"] - now).total_seconds()
            if remaining <= 0:
                lines.append(f"  • {pname} — 곧 완료!")
            else:
                h = int(remaining // 3600)
                m = int((remaining % 3600) // 60)
                lines.append(f"  • {pname} — {h}시간 {m}분 남음")

    placements = summary["placements"]
    lines.append("\n")
    if placements:
        lines.append(f"{icon_emoji('bookmark')} 배치 ({len(placements)}마리)")
        for p in placements:
            fi = config.CAMP_FIELDS.get(p.get("field_type", ""), {})
            shiny = shiny_emoji() if p.get("is_shiny") else ""
            lines.append(f"  {fi.get('emoji', '🏕')} {shiny}{p['name_ko']} ({p['score']}점)")
    else:
        lines.append(f"{icon_emoji('bookmark')} 배치: 없음")

    lines.append(f"\n⏰ 다음 정산: {_next_round_countdown()}")
    lines.append("ℹ️ 배치는 매 라운드(3시간) 초기화됩니다.")
    lines.append("")

    try:
        await query.edit_message_text("\n".join(lines), parse_mode="HTML")
    except Exception:
        pass


async def _handle_hub_home(query, parts, context):
    """cdm_hub_home_{uid} — 거점캠프 (허브에서)."""
    uid = int(parts[3])
    if query.from_user.id != uid:
        await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
        return

    await query.answer()
    settings = await cq.get_user_camp_settings(uid)

    if not settings or not settings.get("home_chat_id"):
        camps = await cq.get_available_camps()
        if not camps:
            try:
                await query.edit_message_text(
                    "🏕 거점캠프\n\n"
                    "활성화된 캠프가 없습니다.\n"
                    "채팅방에서 '캠프개설'로 캠프를 만들어보세요!"
                )
            except Exception:
                pass
            return
        text, markup = _build_camp_list_page(camps, uid, 0, is_change=False)
        try:
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
        except Exception:
            pass
        return

    # 거점 설정됨 → 상세 현황
    chat_id = settings["home_chat_id"]
    camp = await cq.get_camp(chat_id)
    if not camp:
        try:
            await query.edit_message_text("거점 캠프가 삭제되었습니다.")
        except Exception:
            pass
        return

    chat_room = await queries.get_chat_room(chat_id)
    chat_title = (chat_room.get("chat_title") if chat_room else None) or "채팅방"
    fields = await cq.get_fields(chat_id)
    level_info = cs.get_level_info(camp["level"])

    now = config.get_kst_now()
    current_round = cs._get_current_round_time(now)
    bonuses = await cq.get_round_bonus(chat_id, current_round)
    bonus_map = {b["field_id"]: b for b in bonuses}
    user_placements = await cq.get_user_placements_in_chat(chat_id, uid)
    placed_map = {p["field_id"]: p for p in user_placements}

    if camp["level"] < config.CAMP_MAX_LEVEL:
        xp_needed = cs.get_level_info(camp["level"] + 1)[4]
    else:
        xp_needed = level_info[4]  # max level
    try:
        member_count = await context.bot.get_chat_member_count(chat_id)
    except Exception:
        member_count = 100
    total_slots = cs.calc_total_slots(camp["level"], member_count)

    # 필드별 배치 수 조회
    slot_info = await cq.get_field_slot_info(chat_id)
    slot_count_map = {si["field_id"]: si["placed_count"] for si in slot_info}

    hlines = [
        f"🏕 <b>{chat_title}</b>",
        f"Lv.{camp['level']} {level_info[5]} — XP {camp['xp']}/{xp_needed}",
        "",
    ]

    any_full = False
    for f in fields:
        fi = config.CAMP_FIELDS.get(f["field_type"], {})
        emoji = fi.get("emoji", "🏕")
        placed = placed_map.get(f["id"])
        bonus = bonus_map.get(f["id"])
        bonus_tag = " 🔥" if bonus else ""
        cnt = slot_count_map.get(f["id"], 0)
        slot_tag = f" [{cnt}/{total_slots}]"
        if cnt >= total_slots:
            any_full = True
        if placed:
            shiny = shiny_emoji() if placed.get("is_shiny") else ""
            hlines.append(f"{emoji} {shiny}{placed['name_ko']} ({placed['score']}점){slot_tag}{bonus_tag}")
        else:
            hlines.append(f"{emoji} 비어있음{slot_tag}{bonus_tag}")

    hlines.append(f"")
    hlines.append(f"⏰ 다음 정산: {_next_round_countdown()}")
    hlines.append("ℹ️ 배치는 매 라운드 초기화됩니다.")

    # 2번째 거점 표시
    if settings.get("home_chat_id_2"):
        camp2 = await cq.get_camp(settings["home_chat_id_2"])
        if camp2:
            chat_room2 = await queries.get_chat_room(settings["home_chat_id_2"])
            chat_title2 = (chat_room2.get("chat_title") if chat_room2 else None) or "채팅방"
            hlines.append("")
            hlines.append(f"🏠 2번째 거점: {chat_title2} (Lv.{camp2['level']})")

    hbuttons = []
    hbuttons.append([
        InlineKeyboardButton("🏕 배치하기", callback_data=f"cdm_place_{uid}"),
        InlineKeyboardButton("🔄 거점변경", callback_data=f"cdm_chghome_{uid}"),
    ])
    # 풀방인 필드가 있으면 알림 버튼
    if any_full:
        hbuttons.append([InlineKeyboardButton("🔔 빈자리 알림 설정", callback_data=f"cdm_waitlist_{uid}")])

    # 2번째 거점 설정/해제 (구독자: 활성, 비구독자: 잠금)
    from services.subscription_service import get_user_tier
    tier = await get_user_tier(uid)
    has_dual = config.SUBSCRIPTION_TIERS.get(tier, {}).get("benefits", {}).get("dual_home_camp")
    if settings.get("home_chat_id_2"):
        hbuttons.append([InlineKeyboardButton("🏠 2번째 거점 해제", callback_data=f"cdm_delhome2_{uid}")])
    elif has_dual:
        hbuttons.append([InlineKeyboardButton("🏠 2번째 거점 설정", callback_data=f"cdm_sethome2_{uid}")])
    else:
        hbuttons.append([InlineKeyboardButton("🔒 2번째 거점 설정 (프리미엄)", callback_data=f"cdm_sethome2_locked_{uid}")])

    hbuttons.append([InlineKeyboardButton("◀ 캠프 메뉴", callback_data=f"cdm_hub_back_{uid}")])

    try:
        await query.edit_message_text("\n".join(hlines), reply_markup=InlineKeyboardMarkup(hbuttons), parse_mode="HTML")
    except Exception:
        pass


async def _handle_waitlist(query, parts, context):
    """cdm_waitlist_{uid} — 빈자리 알림 필드 선택."""
    uid = int(parts[2])
    if query.from_user.id != uid:
        await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
        return

    await query.answer()
    settings = await cq.get_user_camp_settings(uid)
    if not settings or not settings.get("home_chat_id"):
        return

    chat_id = settings["home_chat_id"]
    fields = await cq.get_fields(chat_id)
    camp = await cq.get_camp(chat_id)
    if not camp or not fields:
        return

    try:
        member_count = await context.bot.get_chat_member_count(chat_id)
    except Exception:
        member_count = 100
    total_slots = cs.calc_total_slots(camp["level"], member_count)
    slot_info = await cq.get_field_slot_info(chat_id)
    slot_count_map = {si["field_id"]: si["placed_count"] for si in slot_info}

    wlines = ["🔔 <b>빈자리 알림 설정</b>", "다음 라운드 시작 시 알림을 받습니다.", ""]
    wbuttons = []
    for f in fields:
        fi = config.CAMP_FIELDS.get(f["field_type"], {})
        cnt = slot_count_map.get(f["id"], 0)
        on_wl = await cq.is_on_waitlist(uid, f["id"])
        icon = "🔔" if on_wl else "🔕"
        label = f"{icon} {fi.get('name', '')} [{cnt}/{total_slots}]"
        wbuttons.append([InlineKeyboardButton(label, callback_data=f"cdm_wl_{uid}_{f['id']}")])

    wbuttons.append([InlineKeyboardButton("◀ 거점캠프", callback_data=f"cdm_hub_home_{uid}")])

    try:
        await query.edit_message_text(
            "\n".join(wlines),
            reply_markup=InlineKeyboardMarkup(wbuttons),
            parse_mode="HTML",
        )
    except Exception:
        pass


async def _handle_wl(query, parts, context):
    """cdm_wl_{uid}_{field_id} — 필드별 알림 토글."""
    uid = int(parts[2])
    field_id = int(parts[3])
    if query.from_user.id != uid:
        await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
        return

    settings = await cq.get_user_camp_settings(uid)
    if not settings or not settings.get("home_chat_id"):
        await query.answer("거점 캠프를 먼저 설정하세요!", show_alert=True)
        return
    chat_id = settings["home_chat_id"]

    on_wl = await cq.is_on_waitlist(uid, field_id)
    if on_wl:
        await cq.remove_slot_waitlist(uid, field_id)
        await query.answer("🔕 알림을 해제했습니다.")
    else:
        await cq.add_slot_waitlist(uid, chat_id, field_id)
        await query.answer("🔔 빈자리 알림을 설정했습니다!")

    # 화면 갱신 — waitlist 화면 다시 그리기
    fields = await cq.get_fields(chat_id)
    camp = await cq.get_camp(chat_id)
    if not camp or not fields:
        return

    try:
        member_count = await context.bot.get_chat_member_count(chat_id)
    except Exception:
        member_count = 100
    total_slots = cs.calc_total_slots(camp["level"], member_count)
    slot_info = await cq.get_field_slot_info(chat_id)
    slot_count_map = {si["field_id"]: si["placed_count"] for si in slot_info}

    wlines = ["🔔 <b>빈자리 알림 설정</b>", "다음 라운드 시작 시 알림을 받습니다.", ""]
    wbuttons = []
    for f in fields:
        fi = config.CAMP_FIELDS.get(f["field_type"], {})
        cnt = slot_count_map.get(f["id"], 0)
        is_on = await cq.is_on_waitlist(uid, f["id"])
        icon = "🔔" if is_on else "🔕"
        label = f"{icon} {fi.get('name', '')} [{cnt}/{total_slots}]"
        wbuttons.append([InlineKeyboardButton(label, callback_data=f"cdm_wl_{uid}_{f['id']}")])

    wbuttons.append([InlineKeyboardButton("◀ 거점캠프", callback_data=f"cdm_hub_home_{uid}")])

    try:
        await query.edit_message_text(
            "\n".join(wlines),
            reply_markup=InlineKeyboardMarkup(wbuttons),
            parse_mode="HTML",
        )
    except Exception:
        pass


async def _handle_hub_notify(query, parts):
    """cdm_hub_notify_{uid} — 알림 토글 (허브에서)."""
    uid = int(parts[3])
    if query.from_user.id != uid:
        await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
        return

    new_state = await cq.toggle_camp_notify(uid)
    if new_state:
        await query.answer("🔔 캠프 정산 알림이 켜졌습니다!", show_alert=True)
    else:
        await query.answer("🔕 캠프 정산 알림이 꺼졌습니다.", show_alert=True)


async def _handle_hub_manage(query, parts, camp_dm_callback_handler):
    """cdm_hub_manage_{uid} — 캠프 관리 (소유자)."""
    uid = int(parts[3])
    if query.from_user.id != uid:
        await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
        return
    await query.answer()

    owned_camp = await cq.get_camp_by_owner(uid)
    if not owned_camp:
        try:
            await query.edit_message_text("소유한 캠프가 없습니다!")
        except Exception:
            pass
        return

    home_chat_id = owned_camp["chat_id"]
    welcome = await cq.get_welcome_message(home_chat_id)
    camp_lang = await cq.get_camp_language(home_chat_id)
    lang_info = config.CAMP_LANGUAGES.get(camp_lang, config.CAMP_LANGUAGES["ko"])
    lines = [
        "⚙️ <b>캠프 관리</b>",
        "",
        "💬 <b>환영 멘트</b> (캠꾸)",
    ]
    if welcome:
        lines.append(f"  현재: \"{welcome}\"")
    else:
        lines.append("  현재: (미설정)")
    lines.append("")
    lines.append(f"🌐 <b>캠프 언어</b>: {lang_info['flag']} {lang_info['name']}")
    lines.append("")
    lines.append("방문자가 올 때 보여지는 메시지입니다.")

    mbuttons = []
    mbuttons.append([
        InlineKeyboardButton(
            "✏️ 멘트 설정" if not welcome else "✏️ 멘트 변경",
            callback_data=f"cdm_mng_welcome_{uid}",
        ),
    ])
    if welcome:
        mbuttons.append([
            InlineKeyboardButton("🗑 멘트 삭제", callback_data=f"cdm_mng_delwelc_{uid}"),
        ])
    mbuttons.append([
        InlineKeyboardButton(f"🌐 언어 변경", callback_data=f"cdm_mng_lang_{uid}"),
    ])
    mbuttons.append([InlineKeyboardButton("◀ 캠프 메뉴", callback_data=f"cdm_hub_back_{uid}")])

    try:
        await query.edit_message_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(mbuttons),
            parse_mode="HTML",
        )
    except Exception:
        pass


async def _handle_mng_welcome(query, parts, context):
    """cdm_mng_welcome_{uid} — 환영 멘트 입력 대기."""
    uid = int(parts[3])
    if query.from_user.id != uid:
        await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
        return
    await query.answer()
    # 유저 데이터에 상태 저장 (다음 메시지를 환영 멘트로 처리)
    context.user_data["camp_welcome_input"] = True
    try:
        await query.edit_message_text(
            f"💬 환영 멘트를 입력해주세요! (최대 {config.CAMP_WELCOME_MSG_MAX_LEN}자)\n\n"
            "예: 피카츄가 반겨줍니다! ⚡\n\n"
            "취소하려면 '취소'를 입력하세요.",
            parse_mode="HTML",
        )
    except Exception:
        pass


async def _handle_mng_delwelc(query, parts, update, camp_dm_callback_handler):
    """cdm_mng_delwelc_{uid} — 환영 멘트 삭제."""
    uid = int(parts[3])
    if query.from_user.id != uid:
        await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
        return
    owned_camp = await cq.get_camp_by_owner(uid)
    if owned_camp:
        await cq.set_welcome_message(owned_camp["chat_id"], None)
    await query.answer("🗑 환영 멘트가 삭제되었습니다!", show_alert=True)
    # 관리 화면으로 돌아가기
    query.data = f"cdm_hub_manage_{uid}"
    await camp_dm_callback_handler(update, None)


async def _handle_mng_lang(query, parts):
    """cdm_mng_lang_{uid} — 캠프 언어 선택 화면."""
    uid = int(parts[3])
    if query.from_user.id != uid:
        await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
        return
    await query.answer()

    owned_camp = await cq.get_camp_by_owner(uid)
    if not owned_camp:
        return
    current_lang = await cq.get_camp_language(owned_camp["chat_id"])

    lines = [
        "🌐 <b>캠프 언어 설정</b>",
        "",
        "캠프의 언어를 선택하세요.",
        "방문하기에서 언어별로 분류됩니다.",
        "",
    ]
    lbuttons = []
    for lk, lv in config.CAMP_LANGUAGES.items():
        check = " ✅" if lk == current_lang else ""
        lbuttons.append([InlineKeyboardButton(
            f"{lv['flag']} {lv['name']}{check}",
            callback_data=f"cdm_setlang_{uid}_{lk}",
        )])
    lbuttons.append([InlineKeyboardButton("◀ 캠프 관리", callback_data=f"cdm_hub_manage_{uid}")])

    try:
        await query.edit_message_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(lbuttons),
            parse_mode="HTML",
        )
    except Exception:
        pass


async def _handle_setlang(query, parts, update, camp_dm_callback_handler):
    """cdm_setlang_{uid}_{lang} — 캠프 언어 적용."""
    uid = int(parts[2])
    lang_code = parts[3]
    if query.from_user.id != uid:
        await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
        return

    if lang_code not in config.CAMP_LANGUAGES:
        await query.answer("지원하지 않는 언어입니다!", show_alert=True)
        return

    owned_camp = await cq.get_camp_by_owner(uid)
    if not owned_camp:
        await query.answer("소유한 캠프가 없습니다!", show_alert=True)
        return

    await cq.set_camp_language(owned_camp["chat_id"], lang_code)
    lang_info = config.CAMP_LANGUAGES[lang_code]
    await query.answer(f"{lang_info['flag']} 캠프 언어가 {lang_info['name']}(으)로 변경되었습니다!", show_alert=True)
    # 관리 화면으로 돌아가기
    query.data = f"cdm_hub_manage_{uid}"
    await camp_dm_callback_handler(update, None)


async def _handle_hub_mvp(query, parts):
    """cdm_hub_mvp_{uid} — 주간 MVP 랭킹."""
    uid = int(parts[3])
    if query.from_user.id != uid:
        await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
        return

    await query.answer()
    settings = await cq.get_user_camp_settings(uid)
    if not settings or not settings.get("home_chat_id"):
        try:
            await query.edit_message_text("먼저 거점 캠프를 설정해주세요!")
        except Exception:
            pass
        return

    chat_id = settings["home_chat_id"]
    chat_room = await queries.get_chat_room(chat_id)
    title = (chat_room.get("chat_title") if chat_room else None) or "알 수 없음"

    mvp_list = await cs.get_weekly_mvp(chat_id)

    lines = [
        f"{icon_emoji('pokecenter')} <b>주간 MVP 랭킹</b>",
        f"📍 {title}",
        "",
    ]
    if not mvp_list:
        lines.append("")
        lines.append("아직 이번 주 정산 기록이 없습니다.")
    else:
        RANK_EMOJI = ["🥇", "🥈", "🥉"]
        for r in mvp_list:
            rank = r["rank"]
            medal = RANK_EMOJI[rank - 1] if rank <= 3 else f" {rank}."
            name = r.get("first_name") or r.get("username") or str(r["user_id"])
            total = r["total"]
            me_tag = " ← 나" if r["user_id"] == uid else ""
            lines.append(f"{medal} <b>{name}</b> — {total}조각{me_tag}")

    lines.append("")
    lines.append("")
    lines.append(f"최근 7일 기준 | {icon_emoji('gotcha')} 정산 조각 합계")

    buttons = [[InlineKeyboardButton("◀ 캠프 메뉴", callback_data=f"cdm_hub_back_{uid}")]]
    try:
        await query.edit_message_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="HTML",
        )
    except Exception:
        pass


async def _handle_hub_back(query, parts):
    """cdm_hub_back_{uid} — 허브로 돌아가기."""
    uid = int(parts[3])
    if query.from_user.id != uid:
        await query.answer()
        return
    await query.answer()
    # 허브 메시지 재생성
    settings = await cq.get_user_camp_settings(uid)
    has_home = settings and settings.get("home_chat_id")

    hub_lines = [
        f"{icon_emoji('pokecenter')} <b>캠프</b>",
        "",
    ]
    if has_home:
        chat_room = await queries.get_chat_room(settings["home_chat_id"])
        camp = await cq.get_camp(settings["home_chat_id"])
        t = (chat_room.get("chat_title") if chat_room else None) or "알 수 없음"
        lv = camp["level"] if camp else 1
        level_info = cs.get_level_info(lv)
        hub_lines.append(f"{icon_emoji('stationery')} 거점1: {t} (Lv.{lv} {level_info[5]})")
        placements = await cq.get_user_placements_in_chat(settings["home_chat_id"], uid)
        hub_lines.append(f"{icon_emoji('bookmark')} 배치: {len(placements)}마리")
        # 2번째 거점
        if settings.get("home_chat_id_2"):
            chat_room2 = await queries.get_chat_room(settings["home_chat_id_2"])
            camp2 = await cq.get_camp(settings["home_chat_id_2"])
            t2 = (chat_room2.get("chat_title") if chat_room2 else None) or "알 수 없음"
            lv2 = camp2["level"] if camp2 else 1
            level_info2 = cs.get_level_info(lv2)
            hub_lines.append(f"{icon_emoji('stationery')} 거점2: {t2} (Lv.{lv2} {level_info2[5]})")
            placements2 = await cq.get_user_placements_in_chat(settings["home_chat_id_2"], uid)
            hub_lines.append(f"{icon_emoji('bookmark')} 배치: {len(placements2)}마리")
        frags = await cq.get_user_fragments(uid)
        total_frags = sum(frags.values()) if frags else 0
        crystals = await cq.get_crystals(uid)
        hub_lines.append(f"{icon_emoji('gotcha')} 조각: {total_frags}개 | {icon_emoji('crystal')} 결정: {crystals['crystal']}개")
    else:
        hub_lines += ["", "아직 거점캠프가 없습니다!", "아래 버튼으로 시작하세요."]

    hub_lines += ["", f"{icon_emoji('bookmark')} 다음 정산: {_next_round_countdown()}", ""]

    btns = []
    if has_home:
        btns.append([
            InlineKeyboardButton("🏕 배치하기", callback_data=f"cdm_place_{uid}"),
            InlineKeyboardButton("📋 내캠프", callback_data=f"cdm_hub_mycamp_{uid}"),
        ])
        btns.append([
            InlineKeyboardButton("✨ 이로치전환", callback_data=f"cdm_hub_convert_{uid}"),
            InlineKeyboardButton("🔨 분해", callback_data=f"cdm_hub_decompose_{uid}"),
        ])
        btns.append([
            InlineKeyboardButton("🏠 거점캠프", callback_data=f"cdm_hub_home_{uid}"),
            InlineKeyboardButton("🏆 주간MVP", callback_data=f"cdm_hub_mvp_{uid}"),
        ])
        btns.append([
            InlineKeyboardButton("🔔 알림설정", callback_data=f"cdm_hub_notify_{uid}"),
        ])
        # 소유자면 관리 버튼
        owned_camp = await cq.get_camp_by_owner(uid)
        if owned_camp:
            btns.append([
                InlineKeyboardButton("⚙️ 캠프 관리", callback_data=f"cdm_hub_manage_{uid}"),
            ])
    else:
        btns.append([InlineKeyboardButton("🏕 거점 설정하기", callback_data=f"cdm_hub_home_{uid}")])
    btns.append([
        InlineKeyboardButton("📖 캠프 가이드", callback_data=f"cdm_guide_{uid}_0"),
        InlineKeyboardButton("❌ 닫기", callback_data=f"cdm_cancel_{uid}"),
    ])

    try:
        await query.edit_message_text(
            "\n".join(hub_lines),
            reply_markup=InlineKeyboardMarkup(btns),
            parse_mode="HTML",
        )
    except Exception:
        pass


async def _handle_visitlang(query, parts):
    """cdm_visitlang_{uid} — 방문하기 언어 선택 화면."""
    uid = int(parts[2])
    if query.from_user.id != uid:
        await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
        return
    await query.answer()

    settings = await cq.get_user_camp_settings(uid)
    home_ids = set()
    if settings:
        if settings.get("home_chat_id"):
            home_ids.add(settings["home_chat_id"])
        if settings.get("home_chat_id_2"):
            home_ids.add(settings["home_chat_id_2"])

    all_camps = await cq.get_available_camps()
    camps = [c for c in all_camps if c["chat_id"] not in home_ids]
    visited_ids = await cq.get_today_visited_chat_ids(uid)

    # 언어별 캠프 수 / 방문 수 집계
    lang_stats = {}
    for lk in config.CAMP_LANGUAGES:
        lang_camps = [c for c in camps if c.get("language", "ko") == lk]
        lang_visited = len([c for c in lang_camps if c["chat_id"] in visited_ids])
        lang_stats[lk] = (len(lang_camps), lang_visited)

    total_visited = len([c for c in camps if c["chat_id"] in visited_ids])
    lines = [
        "👣 <b>캠프 방문하기</b>",
        "",
        f"오늘 방문: {total_visited}/{len(camps)}",
        "",
        "언어를 선택하세요!",
        "",
    ]

    lbuttons = []
    for lk, lv in config.CAMP_LANGUAGES.items():
        total, visited = lang_stats.get(lk, (0, 0))
        if total == 0:
            continue  # 캠프 없는 언어는 숨김
        check = "✅" if visited == total and total > 0 else ""
        lbuttons.append([InlineKeyboardButton(
            f"{lv['flag']} {lv['name']} ({visited}/{total}) {check}",
            callback_data=f"cdm_visit_{uid}_{lk}_0",
        )])
    if not lbuttons:
        lines.append("방문할 수 있는 캠프가 없습니다.")
    lbuttons.append([InlineKeyboardButton("❌ 닫기", callback_data=f"cdm_cancel_{uid}")])

    try:
        await query.edit_message_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(lbuttons),
            parse_mode="HTML",
        )
    except Exception:
        pass


async def _handle_visit(query, parts):
    """cdm_visit_{uid}_{lang}_{page} — 언어별 방문 캠프 목록."""
    uid = int(parts[2])
    lang_code = parts[3]
    page = int(parts[4]) if len(parts) > 4 else 0
    if query.from_user.id != uid:
        await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
        return
    await query.answer()

    settings = await cq.get_user_camp_settings(uid)
    home_ids = set()
    if settings:
        if settings.get("home_chat_id"):
            home_ids.add(settings["home_chat_id"])
        if settings.get("home_chat_id_2"):
            home_ids.add(settings["home_chat_id_2"])

    all_camps = await cq.get_available_camps()
    # 거점 제외 + 언어 필터
    camps = [c for c in all_camps
             if c["chat_id"] not in home_ids and c.get("language", "ko") == lang_code]

    lang_info = config.CAMP_LANGUAGES.get(lang_code, config.CAMP_LANGUAGES["ko"])

    if not camps:
        try:
            await query.edit_message_text(
                f"{lang_info['flag']} {lang_info['name']} 캠프가 없습니다.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("◀ 언어 선택", callback_data=f"cdm_visitlang_{uid}")],
                ]),
            )
        except Exception:
            pass
        return

    visited_ids = await cq.get_today_visited_chat_ids(uid)
    total_pages = max(1, (len(camps) + VISIT_PAGE_SIZE - 1) // VISIT_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * VISIT_PAGE_SIZE
    page_items = camps[start:start + VISIT_PAGE_SIZE]

    visited_count = len([c for c in camps if c["chat_id"] in visited_ids])
    lines = [
        f"👣 <b>캠프 방문하기</b> — {lang_info['flag']} {lang_info['name']}",
        "",
        f"오늘 방문: {visited_count}/{len(camps)}",
        "",
        "해당 채팅방에서 <b>방문</b>을 입력하세요!",
        "",
    ]

    for c in page_items:
        title = c.get("chat_title") or "채팅방"
        lv = c.get("level", 1)
        members = c.get("member_count") or 0
        done = "✅" if c["chat_id"] in visited_ids else "⬜"
        reward_range = config.CAMP_VISIT_REWARD.get(lv, (1, 1))
        reward_str = f"{reward_range[0]}~{reward_range[1]}" if reward_range[0] != reward_range[1] else str(reward_range[0])
        lines.append(f"{done} <b>{title}</b>")
        lines.append(f"    Lv.{lv} | {members}명 | 조각 {reward_str}개")

    if total_pages > 1:
        lines.append(f"\n📄 {page + 1}/{total_pages}")

    lines.append("")

    buttons = []
    # 초대링크 있는 캠프는 바로가기 버튼
    for c in page_items:
        if c.get("invite_link") and c["chat_id"] not in visited_ids:
            title = c.get("chat_title") or "캠프"
            buttons.append([InlineKeyboardButton(
                f"👣 {title} 가기",
                url=c["invite_link"],
            )])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀ 이전", callback_data=f"cdm_visit_{uid}_{lang_code}_{page - 1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("다음 ▶", callback_data=f"cdm_visit_{uid}_{lang_code}_{page + 1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton("◀ 언어 선택", callback_data=f"cdm_visitlang_{uid}")])
    buttons.append([InlineKeyboardButton("❌ 닫기", callback_data=f"cdm_cancel_{uid}")])

    try:
        await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")
    except Exception:
        pass


async def _handle_cancel(query, parts):
    """cdm_cancel_{uid} — 취소."""
    uid = int(parts[2])
    if query.from_user.id != uid:
        await query.answer()
        return
    await query.answer()
    try:
        await query.edit_message_text("취소되었습니다.")
    except Exception:
        pass
