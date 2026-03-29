"""Camp v2 DM handlers — 거점캠프, 내캠프, 이로치전환, 분해, 캠프알림, 캠프가이드.

이 파일은 허브 + 콜백 라우터만 담당.
공유 헬퍼/상수는 dm_camp_shared 에,
실제 핸들러 로직은 dm_camp_home, dm_camp_convert, dm_camp_manage 에 분리.
"""

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationHandlerStop

import config
from database import camp_queries as cq
from database import queries
from services import camp_service as cs
from utils.helpers import shiny_emoji, icon_emoji
from utils.i18n import t, get_user_lang

# 공유 헬퍼/상수를 re-export (서브모듈 및 외부에서 handlers.dm_camp 로 접근 가능)
from handlers.dm_camp_shared import (  # noqa: F401
    _callback_dedup, _is_duplicate_callback,
    _pokemon_name, _next_round_countdown,
    CAMP_LIST_PAGE_SIZE, DM_PAGE_SIZE, DECOMPOSE_PAGE_SIZE, CONVERT_PAGE_SIZE, VISIT_PAGE_SIZE,
    _build_camp_list_page, _build_camp2_list_page,
    _GUIDE_STEPS,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════
# DM 명령: 캠프 (메인 허브)
# ═══════════════════════════════════════════════════════

async def camp_hub_handler(update, context):
    """DM '캠프' — 캠프 메인 허브 메뉴."""
    user_id = update.effective_user.id
    lang = await get_user_lang(user_id)
    user = await queries.get_user(user_id)
    if not user:
        await update.message.reply_text(t(lang, "camp.no_pokemon"))
        return

    settings = await cq.get_user_camp_settings(user_id)
    has_home = settings and settings.get("home_chat_id")
    has_home2 = settings and settings.get("home_chat_id_2")

    # 거점 정보 요약
    lines = [
        f"{icon_emoji('pokecenter')} <b>캠프</b>",
        "",
    ]

    if has_home:
        chat_room = await queries.get_chat_room(settings["home_chat_id"])
        camp = await cq.get_camp(settings["home_chat_id"])
        title = (chat_room.get("chat_title") if chat_room else None) or "알 수 없음"
        lv = camp["level"] if camp else 1
        level_info = cs.get_level_info(lv)
        lines.append(f"{icon_emoji('stationery')} 거점1: {title} (Lv.{lv} {level_info[5]})")

        # 배치 현황 간략
        placements = await cq.get_user_placements_in_chat(settings["home_chat_id"], user_id)
        lines.append(f"{icon_emoji('bookmark')} 배치: {len(placements)}마리")

        # 2번째 거점 표시
        if has_home2:
            chat_room2 = await queries.get_chat_room(settings["home_chat_id_2"])
            camp2 = await cq.get_camp(settings["home_chat_id_2"])
            title2 = (chat_room2.get("chat_title") if chat_room2 else None) or "알 수 없음"
            lv2 = camp2["level"] if camp2 else 1
            level_info2 = cs.get_level_info(lv2)
            lines.append(f"{icon_emoji('stationery')} 거점2: {title2} (Lv.{lv2} {level_info2[5]})")
            placements2 = await cq.get_user_placements_in_chat(settings["home_chat_id_2"], user_id)
            lines.append(f"{icon_emoji('bookmark')} 배치: {len(placements2)}마리")

        # 조각 합계
        frags = await cq.get_user_fragments(user_id)
        total_frags = sum(frags.values()) if frags else 0
        crystals = await cq.get_crystals(user_id)
        lines.append(f"{icon_emoji('gotcha')} 조각: {total_frags}개 | {icon_emoji('crystal')} 결정: {crystals['crystal']}개")
    else:
        lines.append("")
        lines.append("아직 거점캠프가 없습니다!")
        lines.append("아래 버튼으로 시작하세요.")

    lines.append("")
    lines.append(f"{icon_emoji('bookmark')} 다음 정산: {_next_round_countdown()}")
    lines.append("")

    # 서브메뉴 버튼
    buttons = []
    if has_home:
        buttons.append([
            InlineKeyboardButton("🏕 배치하기", callback_data=f"cdm_place_{user_id}"),
            InlineKeyboardButton("📋 내캠프", callback_data=f"cdm_hub_mycamp_{user_id}"),
        ])
        buttons.append([
            InlineKeyboardButton("✨ 이로치전환", callback_data=f"cdm_hub_convert_{user_id}"),
            InlineKeyboardButton("🔨 분해", callback_data=f"cdm_hub_decompose_{user_id}"),
        ])
        buttons.append([
            InlineKeyboardButton("🏠 거점캠프", callback_data=f"cdm_hub_home_{user_id}"),
            InlineKeyboardButton("🏆 주간MVP", callback_data=f"cdm_hub_mvp_{user_id}"),
        ])
        buttons.append([
            InlineKeyboardButton("🔔 알림설정", callback_data=f"cdm_hub_notify_{user_id}"),
        ])
        # 소유자면 캠프 관리 버튼 추가
        owned_camp = await cq.get_camp_by_owner(user_id)
        if owned_camp:
            buttons.append([
                InlineKeyboardButton("⚙️ 캠프 관리", callback_data=f"cdm_hub_manage_{user_id}"),
            ])
    else:
        buttons.append([InlineKeyboardButton("🏕 거점 설정하기", callback_data=f"cdm_hub_home_{user_id}")])

    buttons.append([
        InlineKeyboardButton("📖 캠프 가이드", callback_data=f"cdm_guide_{user_id}_0"),
        InlineKeyboardButton("❌ 닫기", callback_data=f"cdm_cancel_{user_id}"),
    ])

    await update.message.reply_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="HTML",
    )


# ═══════════════════════════════════════════════════════
# DM 메시지 핸들러: 환영 멘트 입력
# ═══════════════════════════════════════════════════════

async def camp_welcome_input_handler(update, context):
    """DM에서 환영 멘트 입력 처리 (camp_welcome_input 상태일 때)."""
    if not context.user_data.get("camp_welcome_input"):
        return None  # 상태가 아니면 무시 — 다른 핸들러로 전달

    context.user_data.pop("camp_welcome_input", None)
    user_id = update.effective_user.id
    text = (update.message.text or "").strip()

    if text == "취소":
        await update.message.reply_text("✅ 환영 멘트 설정이 취소되었습니다.")
        raise ApplicationHandlerStop()

    if len(text) > config.CAMP_WELCOME_MSG_MAX_LEN:
        await update.message.reply_text(
            f"❌ 멘트가 너무 깁니다! ({len(text)}자/{config.CAMP_WELCOME_MSG_MAX_LEN}자)\n"
            "다시 설정하려면 캠프 메뉴 → 캠프 관리에서 시도하세요."
        )
        raise ApplicationHandlerStop()

    if not text:
        await update.message.reply_text("❌ 빈 멘트는 설정할 수 없습니다.")
        raise ApplicationHandlerStop()

    owned_camp = await cq.get_camp_by_owner(user_id)
    if not owned_camp:
        await update.message.reply_text("소유한 캠프가 없습니다.")
        raise ApplicationHandlerStop()

    await cq.set_welcome_message(owned_camp["chat_id"], text)
    await update.message.reply_text(
        f"✅ 환영 멘트가 설정되었습니다!\n\n💬 \"{text}\"\n\n방문자에게 이 멘트가 보여집니다 🏕"
    )
    raise ApplicationHandlerStop()


# ═══════════════════════════════════════════════════════
# 콜백 라우터 (cdm_*)
# ═══════════════════════════════════════════════════════

async def camp_dm_callback_handler(update, context):
    """cdm_* 콜백 전체 라우터 — 서브모듈로 위임."""
    query = update.callback_query
    if not query or not query.data:
        return

    if _is_duplicate_callback(query):
        await query.answer()
        return

    data = query.data
    parts = data.split("_")

    # 지연 임포트 — 순환 임포트 방지
    from handlers.dm_camp_home import (
        _handle_home2, _handle_home, _handle_chghome, _handle_place,
        _handle_plc, _handle_rm, _handle_fd, _handle_pk, _handle_pp,
        _handle_fback, _handle_clp, _handle_c2p,
        _handle_sethome2_locked, _handle_sethome2, _handle_delhome2,
        _handle_addfd, _handle_newfd, _handle_chgfd, _handle_chgsel, _handle_chgto,
    )
    from handlers.dm_camp_convert import (
        _handle_conv, _handle_ok, _handle_dec, _handle_decok,
        _handle_convpg, _handle_cf, _handle_decpg,
        _handle_hub_convert, _handle_hub_decompose,
    )
    from handlers.dm_camp_manage import (
        _handle_guide, _handle_noop,
        _handle_hub_mycamp, _handle_hub_home,
        _handle_hub_notify, _handle_hub_manage,
        _handle_mng_welcome, _handle_mng_delwelc, _handle_mng_lang, _handle_setlang,
        _handle_hub_mvp, _handle_hub_back,
        _handle_waitlist, _handle_wl,
        _handle_visitlang, _handle_visit,
        _handle_cancel,
    )

    # ── 거점/배치 관련 ──
    if data.startswith("cdm_home2_"):
        await _handle_home2(query, parts)
    elif data.startswith("cdm_home_"):
        await _handle_home(query, parts)
    elif data.startswith("cdm_chghome_"):
        await _handle_chghome(query, parts)
    elif data.startswith("cdm_place_"):
        await _handle_place(query, parts, context)
    elif data.startswith("cdm_plc_"):
        await _handle_plc(query, parts)
    elif data.startswith("cdm_rm_"):
        await _handle_rm(query, parts)
    elif data.startswith("cdm_fd_"):
        await _handle_fd(query, parts)
    elif data.startswith("cdm_pk_"):
        await _handle_pk(query, parts, context)
    elif data.startswith("cdm_pp_"):
        await _handle_pp(query, parts)
    elif data.startswith("cdm_fback_"):
        await _handle_fback(query, parts)
    elif data.startswith("cdm_clp_"):
        await _handle_clp(query, parts)
    elif data.startswith("cdm_c2p_"):
        await _handle_c2p(query, parts)
    elif data.startswith("cdm_sethome2_locked_"):
        await _handle_sethome2_locked(query, parts)
    elif data.startswith("cdm_sethome2_"):
        await _handle_sethome2(query, parts)
    elif data.startswith("cdm_delhome2_"):
        await _handle_delhome2(query, parts)

    # ── DM 필드 관리 (소유자) ──
    elif data.startswith("cdm_addfd_"):
        await _handle_addfd(query, parts)
    elif data.startswith("cdm_newfd_"):
        await _handle_newfd(query, parts)
    elif data.startswith("cdm_chgfd_"):
        await _handle_chgfd(query, parts)
    elif data.startswith("cdm_chgsel_"):
        await _handle_chgsel(query, parts)
    elif data.startswith("cdm_chgto_"):
        await _handle_chgto(query, parts)

    # ── 이로치전환/분해 관련 ──
    elif data.startswith("cdm_conv_"):
        await _handle_conv(query, parts)
    elif data.startswith("cdm_ok_"):
        await _handle_ok(query, parts, context)
    elif data.startswith("cdm_dec_") and not data.startswith("cdm_decok_") and not data.startswith("cdm_decpg_"):
        await _handle_dec(query, parts)
    elif data.startswith("cdm_decok_"):
        await _handle_decok(query, parts)
    elif data.startswith("cdm_convpg_"):
        await _handle_convpg(query, parts)
    elif data.startswith("cdm_cf_"):
        await _handle_cf(query, parts)
    elif data.startswith("cdm_decpg_"):
        await _handle_decpg(query, parts)
    elif data.startswith("cdm_hub_convert_"):
        await _handle_hub_convert(query, parts)
    elif data.startswith("cdm_hub_decompose_"):
        await _handle_hub_decompose(query, parts)

    # ── 관리/가이드/내캠프/MVP/방문/기타 ──
    elif data.startswith("cdm_guide_"):
        await _handle_guide(query, parts)
    elif data.startswith("cdm_noop_"):
        await _handle_noop(query, parts)
    elif data.startswith("cdm_hub_mycamp_"):
        await _handle_hub_mycamp(query, parts, context)
    elif data.startswith("cdm_hub_home_"):
        await _handle_hub_home(query, parts, context)
    elif data.startswith("cdm_hub_notify_"):
        await _handle_hub_notify(query, parts)
    elif data.startswith("cdm_hub_manage_"):
        await _handle_hub_manage(query, parts, camp_dm_callback_handler)
    elif data.startswith("cdm_hub_mvp_"):
        await _handle_hub_mvp(query, parts)
    elif data.startswith("cdm_hub_back_"):
        await _handle_hub_back(query, parts)
    elif data.startswith("cdm_mng_welcome_"):
        await _handle_mng_welcome(query, parts, context)
    elif data.startswith("cdm_mng_delwelc_"):
        await _handle_mng_delwelc(query, parts, update, camp_dm_callback_handler)
    elif data.startswith("cdm_mng_lang_"):
        await _handle_mng_lang(query, parts)
    elif data.startswith("cdm_setlang_"):
        await _handle_setlang(query, parts, update, camp_dm_callback_handler)
    elif data.startswith("cdm_waitlist_"):
        await _handle_waitlist(query, parts, context)
    elif data.startswith("cdm_wl_"):
        await _handle_wl(query, parts, context)
    elif data.startswith("cdm_visitlang_"):
        await _handle_visitlang(query, parts)
    elif data.startswith("cdm_visit_"):
        await _handle_visit(query, parts)
    elif data.startswith("cdm_cancel_"):
        await _handle_cancel(query, parts)


# ═══════════════════════════════════════════════════════
# Re-exports: _register.py 에서 임포트하는 이름들
# ═══════════════════════════════════════════════════════

from handlers.dm_camp_home import home_camp_handler  # noqa: E402, F401
from handlers.dm_camp_convert import (  # noqa: E402, F401
    shiny_convert_handler, decompose_handler,
)
from handlers.dm_camp_manage import (  # noqa: E402, F401
    my_camp_handler, camp_notify_handler, camp_guide_handler,
)
