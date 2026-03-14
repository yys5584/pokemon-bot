"""Camp system v2 group handlers — 그룹 채팅 캠프 핸들러.

핸들러 역할:
- 텔레그램 I/O + UI 로직
- 비즈니스 로직은 services/camp_service.py
- DB 직접 호출은 최소화 (서비스 레이어 우선)
"""

import time
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile

import config
from database import camp_queries as cq
from database import queries
from services import camp_service as cs
from handlers.dm_camp import _next_round_countdown
from utils.helpers import schedule_delete, rarity_badge
from utils.camp_map_generator import generate_camp_map

logger = logging.getLogger(__name__)

# ── Duplicate-click guard ──
_callback_dedup: dict[str, float] = {}
CAMP_PAGE_SIZE = 8


def _is_duplicate_callback(query) -> bool:
    key = f"{query.message.message_id}:{query.data}:{query.from_user.id}"
    now = time.monotonic()
    if len(_callback_dedup) > 200:
        cutoff = now - 60
        stale = [k for k, v in _callback_dedup.items() if v < cutoff]
        for k in stale:
            del _callback_dedup[k]
    if key in _callback_dedup:
        return True
    _callback_dedup[key] = now
    return False


# ═══════════════════════════════════════════════════════
# UI 빌더
# ═══════════════════════════════════════════════════════

def _build_field_buttons(user_id: int, fields: list[dict], placements: list[dict], camp: dict) -> tuple[str, InlineKeyboardMarkup]:
    """필드 선택 화면 빌드."""
    level_info = cs.get_level_info(camp["level"])
    level_name = level_info[5]

    placed_fields = {p["field_id"] for p in placements}
    field_lines = []
    for f in fields:
        fi = config.CAMP_FIELDS.get(f["field_type"], {})
        mark = "✅" if f["id"] in placed_fields else ""
        field_lines.append(f"{fi.get('emoji', '🏕')} {fi.get('name', f['field_type'])}{mark}")

    text = (
        f"🏕 포켓몬 캠프 — {level_name}\n"
        f"\n"
        f"필드: {' '.join(field_lines)}\n"
        f"내 배치: {len(placements)}마리\n"
        f"\n"
        f"필드를 선택하세요!"
    )

    buttons = []
    row = []
    for f in fields:
        fi = config.CAMP_FIELDS.get(f["field_type"], {})
        label = f"{fi.get('emoji', '🏕')} {fi.get('name', f['field_type'])}"
        row.append(InlineKeyboardButton(label, callback_data=f"camp_fd_{user_id}_{f['id']}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append([
        InlineKeyboardButton("📋 내 배치", callback_data=f"camp_my_{user_id}"),
        InlineKeyboardButton("❌ 닫기", callback_data=f"camp_close_{user_id}"),
    ])

    return text, InlineKeyboardMarkup(buttons)


async def _build_pokemon_list(user_id: int, field_id: int, field_type: str, page: int, chat_id: int = 0) -> tuple[str, InlineKeyboardMarkup]:
    """필드에 배치 가능한 포켓몬 리스트 빌드 (보너스 추천순 정렬)."""
    pokemon_list = await queries.get_user_pokemon_list(user_id)
    fi = config.CAMP_FIELDS.get(field_type, {})

    # 타입 매칭 필터
    matching = [p for p in pokemon_list if cs.pokemon_matches_field(p["pokemon_id"], field_type)]

    if not matching:
        text = f"{fi.get('emoji', '🏕')} {fi.get('name', field_type)} — 배치 가능한 포켓몬이 없습니다."
        buttons = [[InlineKeyboardButton("◀ 돌아가기", callback_data=f"camp_back_{user_id}")]]
        return text, InlineKeyboardMarkup(buttons)

    # 보너스 기반 점수 계산 + 추천순 정렬
    bonus = None
    if chat_id:
        now = config.get_kst_now()
        current_round = cs._get_current_round_time(now)
        bonuses = await cq.get_round_bonus(chat_id, current_round)
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

    total_pages = max(1, (len(scored) + CAMP_PAGE_SIZE - 1) // CAMP_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * CAMP_PAGE_SIZE
    end = min(start + CAMP_PAGE_SIZE, len(scored))
    page_items = scored[start:end]

    lines = [
        f"{fi.get('emoji', '🏕')} {fi.get('name', field_type)} — 포켓몬 선택 [{page + 1}/{total_pages}]",
        f"타입: {'/'.join(fi.get('types', []))}",
    ]
    if bonus:
        pname = cs._pokemon_name(bonus["pokemon_id"])
        stat_name = config.CAMP_IV_STAT_NAMES.get(bonus["stat_type"], "")
        lines.append(f"⭐ 보너스: {pname} ({stat_name} {bonus['stat_value']}↑)")
    lines.append("")

    for i, p in enumerate(page_items):
        num = start + i + 1
        shiny = "✨" if p.get("is_shiny") else ""
        rarity_tag = rarity_badge(p.get("rarity", ""))
        score_tag = f" ({p['_desc']})" if p["_score"] > 1 else ""
        lines.append(f"{num}. {shiny}{rarity_tag}{p['name_ko']}{score_tag}")

    buttons = []
    row = []
    for i, p in enumerate(page_items):
        idx = start + i
        label = f"{idx + 1}. {p['name_ko']}"
        # callback: camp_pk_{user_id}_{field_id}_{instance_id}
        row.append(InlineKeyboardButton(
            label,
            callback_data=f"camp_pk_{user_id}_{field_id}_{p['id']}",
        ))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    # 페이지네이션
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("◀ 이전", callback_data=f"camp_pp_{user_id}_{field_id}_{page - 1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("다음 ▶", callback_data=f"camp_pp_{user_id}_{field_id}_{page + 1}"))
    if nav_row:
        buttons.append(nav_row)

    buttons.append([InlineKeyboardButton("◀ 필드 선택", callback_data=f"camp_back_{user_id}")])

    return "\n".join(lines), InlineKeyboardMarkup(buttons)


async def _build_my_placements(chat_id: int, user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """내 배치 현황 빌드."""
    placements = await cq.get_user_placements_in_chat(chat_id, user_id)

    if not placements:
        text = "🏕 배치된 포켓몬이 없습니다.\n필드를 선택해 배치하세요!"
        buttons = [[InlineKeyboardButton("◀ 돌아가기", callback_data=f"camp_back_{user_id}")]]
        return text, InlineKeyboardMarkup(buttons)

    lines = ["🏕 내 배치 현황", ""]
    buttons = []

    for p in placements:
        fi = config.CAMP_FIELDS.get(p["field_type"], {})
        shiny = "✨" if p.get("is_shiny") else ""
        score_txt = f" ({p['score']}점)" if p.get("score") else ""
        lines.append(f"{fi.get('emoji', '🏕')} {shiny}{p['name_ko']}{score_txt}")
        buttons.append([InlineKeyboardButton(
            f"❌ {p['name_ko']} 해제",
            callback_data=f"camp_rm_{user_id}_{p['id']}",
        )])

    buttons.append([InlineKeyboardButton("◀ 돌아가기", callback_data=f"camp_back_{user_id}")])
    return "\n".join(lines), InlineKeyboardMarkup(buttons)


# ═══════════════════════════════════════════════════════
# 그룹 명령: 캠프
# ═══════════════════════════════════════════════════════

async def camp_handler(update, context):
    """그룹에서 '캠프' 입력 시 — 필드 선택 UI."""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    user = await queries.get_user(user_id)
    if not user:
        resp = await update.message.reply_text("먼저 포켓몬을 잡아보세요!")
        schedule_delete(resp, 5)
        schedule_delete(update.message, 3)
        return

    camp = await cq.get_camp(chat_id)
    if not camp:
        resp = await update.message.reply_text("이 채팅방에는 캠프가 없습니다.\n소유자가 '캠프개설'로 개설하세요!")
        schedule_delete(resp, 10)
        schedule_delete(update.message, 3)
        return

    # 거점캠프 확인 (1번째 또는 2번째 거점 모두 허용)
    settings = await cq.get_user_camp_settings(user_id)
    is_home = (settings and (settings.get("home_chat_id") == chat_id or settings.get("home_chat_id_2") == chat_id))
    if not is_home:
        home_title = ""
        if settings and settings.get("home_chat_id"):
            home_room = await queries.get_chat_room(settings["home_chat_id"])
            if home_room:
                home_title = f"\n현재 거점: {home_room.get('chat_title', '알 수 없음')}"
        resp = await update.message.reply_text(
            f"여기는 내 거점캠프가 아닙니다!{home_title}\n"
            "DM에서 '거점캠프'로 거점을 설정/변경하세요."
        )
        schedule_delete(resp, 10)
        schedule_delete(update.message, 3)
        return

    fields = await cq.get_fields(chat_id)
    if not fields:
        resp = await update.message.reply_text("캠프에 열린 필드가 없습니다.")
        schedule_delete(resp, 10)
        schedule_delete(update.message, 3)
        return

    placements = await cq.get_user_placements_in_chat(chat_id, user_id)
    text, markup = _build_field_buttons(user_id, fields, placements, camp)
    resp = await update.message.reply_text(text, reply_markup=markup, parse_mode="HTML")
    schedule_delete(update.message, 3)
    schedule_delete(resp, 120)


# ═══════════════════════════════════════════════════════
# 그룹 명령: 캠프맵
# ═══════════════════════════════════════════════════════

async def camp_map_handler(update, context):
    """그룹에서 '캠프맵' 입력 시 — 캠프 월드맵 이미지 전송."""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    user = await queries.get_user(user_id)
    if not user:
        resp = await update.message.reply_text("먼저 포켓몬을 잡아보세요!")
        schedule_delete(resp, 5)
        schedule_delete(update.message, 3)
        return

    camp = await cq.get_camp(chat_id)
    if not camp:
        resp = await update.message.reply_text("이 채팅방에는 캠프가 없습니다.")
        schedule_delete(resp, 10)
        schedule_delete(update.message, 3)
        return

    fields = await cq.get_fields(chat_id)
    if not fields:
        resp = await update.message.reply_text("캠프에 열린 필드가 없습니다.")
        schedule_delete(resp, 10)
        schedule_delete(update.message, 3)
        return

    # 필드별 배치 데이터 수집
    active_fields = []
    field_placements = {}
    for f in fields:
        active_fields.append({"id": f["id"], "field_type": f["field_type"]})
        placements = await cq.get_field_placements(f["id"])
        field_placements[f["id"]] = [
            {
                "pokemon_id": p["pokemon_id"],
                "is_shiny": p.get("is_shiny", False),
                "score": p.get("score", 0),
            }
            for p in placements
        ]

    # 맵 이미지 생성
    try:
        buf = generate_camp_map(
            camp_name=camp.get("name", "캠프"),
            camp_level=camp["level"],
            active_fields=active_fields,
            field_placements=field_placements,
            field_bonuses={},
        )
        resp = await update.message.reply_photo(photo=buf)
        schedule_delete(update.message, 3)
        schedule_delete(resp, 120)
    except Exception:
        logger.exception("[Camp] Map generation failed")
        resp = await update.message.reply_text("맵 생성에 실패했습니다.")
        schedule_delete(resp, 10)
        schedule_delete(update.message, 3)


# ═══════════════════════════════════════════════════════
# 그룹 명령: 캠프개설
# ═══════════════════════════════════════════════════════

async def camp_create_handler(update, context):
    """그룹에서 '캠프개설' — 소유자만 가능."""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    # 소유자 확인
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        if member.status != "creator":
            resp = await update.message.reply_text("캠프 개설은 채팅방 소유자만 가능합니다.")
            schedule_delete(resp, 10)
            schedule_delete(update.message, 3)
            return
    except Exception:
        resp = await update.message.reply_text("권한 확인에 실패했습니다.")
        schedule_delete(resp, 10)
        schedule_delete(update.message, 3)
        return

    # 멤버 수 확인
    try:
        count = await context.bot.get_chat_member_count(chat_id)
        if count < config.CAMP_MIN_MEMBERS:
            resp = await update.message.reply_text(
                f"캠프 개설에는 최소 {config.CAMP_MIN_MEMBERS}명이 필요합니다. (현재: {count}명)"
            )
            schedule_delete(resp, 10)
            schedule_delete(update.message, 3)
            return
    except Exception:
        pass  # 멤버 수 확인 실패 시 진행

    # 이미 존재 확인
    existing = await cq.get_camp(chat_id)
    if existing:
        resp = await update.message.reply_text("이미 캠프가 존재합니다!")
        schedule_delete(resp, 10)
        schedule_delete(update.message, 3)
        return

    # 필드 선택 UI (초기: 풀/불/물 3택)
    buttons = []
    row = []
    for fkey, finfo in config.CAMP_FIELDS.items():
        if fkey not in config.CAMP_STARTER_FIELDS:
            continue
        label = f"{finfo['emoji']} {finfo['name']}"
        row.append(InlineKeyboardButton(label, callback_data=f"camp_create_{user_id}_{fkey}"))
    buttons.append(row)

    text = (
        "🏕 캠프 개설\n"
        "\n"
        "첫 번째 필드를 선택하세요!\n"
        "🌿 숲 / 🔥 화산 / 💧 호수\n"
        "\n"
        "💡 도시·동굴·신전은 레벨업 시 해금됩니다."
    )
    resp = await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    schedule_delete(update.message, 3)
    schedule_delete(resp, 60)


# ═══════════════════════════════════════════════════════
# 그룹 명령: 캠프설정
# ═══════════════════════════════════════════════════════

async def camp_settings_handler(update, context):
    """그룹에서 '캠프설정' — 소유자 전용."""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    # 소유자 확인
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        if member.status != "creator":
            resp = await update.message.reply_text("캠프 설정은 채팅방 소유자만 가능합니다.")
            schedule_delete(resp, 10)
            schedule_delete(update.message, 3)
            return
    except Exception:
        resp = await update.message.reply_text("권한 확인에 실패했습니다.")
        schedule_delete(resp, 10)
        schedule_delete(update.message, 3)
        return

    camp = await cq.get_camp(chat_id)
    if not camp:
        resp = await update.message.reply_text("캠프가 없습니다. '캠프개설'로 먼저 개설하세요!")
        schedule_delete(resp, 10)
        schedule_delete(update.message, 3)
        return

    fields = await cq.get_fields(chat_id)
    settings = await cq.get_chat_camp_settings(chat_id)
    level_info = cs.get_level_info(camp["level"])
    max_fields = level_info[1]

    # 현재 설정 표시
    mode = "🔒 승인제" if settings and settings.get("approval_mode") else "🔓 자유 배치"
    approval_slots = settings.get("approval_slots", 0) if settings else 0

    field_lines = []
    for f in fields:
        fi = config.CAMP_FIELDS.get(f["field_type"], {})
        field_lines.append(f"{fi.get('emoji', '🏕')} {fi.get('name', f['field_type'])}")

    text = (
        f"🏕 캠프 설정 — Lv.{camp['level']} {level_info[5]}\n"
        f"\n"
        f"필드: {' '.join(field_lines)} ({len(fields)}/{max_fields})\n"
        f"배치 모드: {mode}\n"
        f"{'승인 슬롯: ' + str(approval_slots) + '칸' if approval_slots else ''}\n"
        f""
    )

    buttons = []

    # 필드 추가 (가능한 경우)
    if len(fields) < max_fields:
        buttons.append([InlineKeyboardButton("🆕 필드 추가", callback_data=f"camp_addfd_{user_id}")])

    # 필드 변경
    if fields:
        buttons.append([InlineKeyboardButton("🔄 필드 변경", callback_data=f"camp_chgfd_{user_id}")])

    # 배치 모드 토글
    if settings and settings.get("approval_mode"):
        buttons.append([InlineKeyboardButton("🔓 자유 배치로 전환", callback_data=f"camp_mode_{user_id}_free")])
    else:
        buttons.append([InlineKeyboardButton("🔒 승인제로 전환", callback_data=f"camp_mode_{user_id}_approve")])

    # 승인 대기 목록
    pending = await cq.get_pending_approvals(chat_id)
    if pending:
        buttons.append([InlineKeyboardButton(f"📋 승인 대기 ({len(pending)}건)", callback_data=f"camp_approvals_{user_id}")])

    buttons.append([InlineKeyboardButton("❌ 닫기", callback_data=f"camp_close_{user_id}")])

    resp = await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    schedule_delete(update.message, 3)
    schedule_delete(resp, 120)


# ═══════════════════════════════════════════════════════
# 콜백 라우터 (camp_*)
# ═══════════════════════════════════════════════════════

async def camp_callback_handler(update, context):
    """camp_* 콜백 전체 라우터."""
    query = update.callback_query
    if not query or not query.data:
        return

    if _is_duplicate_callback(query):
        await query.answer()
        return

    data = query.data
    parts = data.split("_")

    # ── camp_fd_{uid}_{field_id} — 필드 선택 → 포켓몬 리스트 ──
    if data.startswith("camp_fd_"):
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
        text, markup = await _build_pokemon_list(uid, field_id, field["field_type"], 0, field["chat_id"])
        try:
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
        except Exception:
            pass

    # ── camp_pk_{uid}_{field_id}_{instance_id} — 포켓몬 배치 ──
    elif data.startswith("camp_pk_"):
        uid = int(parts[2])
        field_id = int(parts[3])
        instance_id = int(parts[4])
        if query.from_user.id != uid:
            await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
            return

        chat_id = query.message.chat_id

        # 도감 수 + 멤버 수
        dex_count = await queries.count_pokedex(uid)
        try:
            member_count = await context.bot.get_chat_member_count(chat_id)
        except Exception:
            member_count = 100

        success, msg = await cs.try_place_pokemon(
            chat_id, field_id, uid, instance_id, member_count, dex_count,
        )

        if not success and msg.startswith("승인대기|"):
            req_id = msg.split("|")[1]
            await query.answer("승인 대기 중입니다. 소유자 승인 후 배치됩니다.", show_alert=True)
            # TODO: 소유자에게 DM 알림
        elif not success:
            await query.answer(msg, show_alert=True)
        else:
            await query.answer(msg)

        # 필드 선택 화면으로 복귀
        camp = await cq.get_camp(chat_id)
        if camp:
            fields = await cq.get_fields(chat_id)
            placements = await cq.get_user_placements_in_chat(chat_id, uid)
            text, markup = _build_field_buttons(uid, fields, placements, camp)
            try:
                await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
            except Exception:
                pass

    # ── camp_pp_{uid}_{field_id}_{page} — 페이지네이션 ──
    elif data.startswith("camp_pp_"):
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
        text, markup = await _build_pokemon_list(uid, field_id, field["field_type"], page, field["chat_id"])
        try:
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
        except Exception:
            pass

    # ── camp_rm_{uid}_{placement_id} — 배치 해제 ──
    elif data.startswith("camp_rm_"):
        uid = int(parts[2])
        placement_id = int(parts[3])
        if query.from_user.id != uid:
            await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
            return

        chat_id = query.message.chat_id
        removed = await cq.remove_placement(placement_id, uid)
        if removed:
            await query.answer("배치를 해제했습니다!")
        else:
            await query.answer("이미 해제되었습니다.")

        text, markup = await _build_my_placements(chat_id, uid)
        try:
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
        except Exception:
            pass

    # ── camp_my_{uid} — 내 배치 ──
    elif data.startswith("camp_my_"):
        uid = int(parts[2])
        if query.from_user.id != uid:
            await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
            return
        await query.answer()
        chat_id = query.message.chat_id
        text, markup = await _build_my_placements(chat_id, uid)
        try:
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
        except Exception:
            pass

    # ── camp_back_{uid} — 필드 선택 복귀 ──
    elif data.startswith("camp_back_"):
        uid = int(parts[2])
        if query.from_user.id != uid:
            await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
            return
        await query.answer()
        chat_id = query.message.chat_id
        camp = await cq.get_camp(chat_id)
        if camp:
            fields = await cq.get_fields(chat_id)
            placements = await cq.get_user_placements_in_chat(chat_id, uid)
            text, markup = _build_field_buttons(uid, fields, placements, camp)
            try:
                await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
            except Exception:
                pass

    # ── camp_close_{uid} — 닫기 ──
    elif data.startswith("camp_close_"):
        uid = int(parts[2])
        if query.from_user.id != uid:
            await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
            return
        await query.answer()
        try:
            await query.message.delete()
        except Exception:
            pass

    # ── camp_create_{uid}_{field_type} — 캠프 개설 필드 선택 ──
    elif data.startswith("camp_create_"):
        uid = int(parts[2])
        field_type = parts[3]
        if query.from_user.id != uid:
            await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
            return

        chat_id = query.message.chat_id
        success, msg = await cs.create_camp(chat_id, uid, field_type)
        await query.answer(msg if len(msg) < 200 else "캠프가 개설되었습니다!", show_alert=True)
        try:
            await query.edit_message_text(msg, parse_mode="HTML")
        except Exception:
            pass

    # ── camp_addfd_{uid} — 필드 추가 선택 ──
    elif data.startswith("camp_addfd_"):
        uid = int(parts[2])
        if query.from_user.id != uid:
            await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
            return

        chat_id = query.message.chat_id
        fields = await cq.get_fields(chat_id)
        existing_types = {f["field_type"] for f in fields}

        buttons = []
        row = []
        for fkey, finfo in config.CAMP_FIELDS.items():
            if fkey in existing_types:
                continue
            label = f"{finfo['emoji']} {finfo['name']}"
            row.append(InlineKeyboardButton(label, callback_data=f"camp_newfd_{uid}_{fkey}"))
            if len(row) == 3:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        buttons.append([InlineKeyboardButton("◀ 돌아가기", callback_data=f"camp_close_{uid}")])

        await query.answer()
        try:
            await query.edit_message_text("🆕 추가할 필드를 선택하세요!", reply_markup=InlineKeyboardMarkup(buttons))
        except Exception:
            pass

    # ── camp_newfd_{uid}_{field_type} — 필드 추가 실행 ──
    elif data.startswith("camp_newfd_"):
        uid = int(parts[2])
        field_type = parts[3]
        if query.from_user.id != uid:
            await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
            return

        chat_id = query.message.chat_id
        success, msg = await cs.add_new_field(chat_id, field_type)
        await query.answer(msg, show_alert=True)
        try:
            await query.edit_message_text(msg, parse_mode="HTML")
        except Exception:
            pass

    # ── camp_chgfd_{uid} — 필드 변경 선택 ──
    elif data.startswith("camp_chgfd_"):
        uid = int(parts[2])
        if query.from_user.id != uid:
            await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
            return

        chat_id = query.message.chat_id
        fields = await cq.get_fields(chat_id)

        buttons = []
        for f in fields:
            fi = config.CAMP_FIELDS.get(f["field_type"], {})
            label = f"{fi.get('emoji', '🏕')} {fi.get('name', f['field_type'])} 변경"
            buttons.append([InlineKeyboardButton(label, callback_data=f"camp_chgsel_{uid}_{f['id']}")])
        buttons.append([InlineKeyboardButton("◀ 돌아가기", callback_data=f"camp_close_{uid}")])

        await query.answer()
        try:
            await query.edit_message_text("🔄 변경할 필드를 선택하세요!\n⚠️ 변경 시 해당 필드의 배치가 초기화됩니다.",
                                          reply_markup=InlineKeyboardMarkup(buttons))
        except Exception:
            pass

    # ── camp_chgsel_{uid}_{field_id} — 변경 대상 필드 선택 후 새 타입 선택 ──
    elif data.startswith("camp_chgsel_"):
        uid = int(parts[2])
        field_id = int(parts[3])
        if query.from_user.id != uid:
            await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
            return

        chat_id = query.message.chat_id
        fields = await cq.get_fields(chat_id)
        existing_types = {f["field_type"] for f in fields}

        buttons = []
        row = []
        for fkey, finfo in config.CAMP_FIELDS.items():
            if fkey in existing_types:
                continue
            label = f"{finfo['emoji']} {finfo['name']}"
            row.append(InlineKeyboardButton(label, callback_data=f"camp_chgdo_{uid}_{field_id}_{fkey}"))
            if len(row) == 3:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        buttons.append([InlineKeyboardButton("◀ 취소", callback_data=f"camp_close_{uid}")])

        await query.answer()
        try:
            await query.edit_message_text("새 필드 타입을 선택하세요!", reply_markup=InlineKeyboardMarkup(buttons))
        except Exception:
            pass

    # ── camp_chgdo_{uid}_{field_id}_{new_type} — 필드 변경 실행 ──
    elif data.startswith("camp_chgdo_"):
        uid = int(parts[2])
        field_id = int(parts[3])
        new_type = parts[4]
        if query.from_user.id != uid:
            await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
            return

        chat_id = query.message.chat_id
        success, msg = await cs.change_field_type(chat_id, field_id, new_type)
        await query.answer(msg, show_alert=True)
        try:
            await query.edit_message_text(msg, parse_mode="HTML")
        except Exception:
            pass

    # ── camp_mode_{uid}_{mode} — 배치 모드 전환 ──
    elif data.startswith("camp_mode_"):
        uid = int(parts[2])
        mode = parts[3]
        if query.from_user.id != uid:
            await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
            return

        chat_id = query.message.chat_id
        enable = mode == "approve"
        slots = 3 if enable else 0  # 기본 승인 슬롯 3개
        success, msg = await cs.toggle_approval_mode(chat_id, enable, slots)
        await query.answer(msg, show_alert=True)
        try:
            await query.edit_message_text(msg, parse_mode="HTML")
        except Exception:
            pass

    # ── camp_approvals_{uid} — 승인 대기 목록 ──
    elif data.startswith("camp_approvals_"):
        uid = int(parts[2])
        if query.from_user.id != uid:
            await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
            return

        chat_id = query.message.chat_id
        pending = await cq.get_pending_approvals(chat_id)

        if not pending:
            await query.answer("대기 중인 요청이 없습니다.")
            return

        lines = ["📋 승인 대기 목록", ""]
        buttons = []
        for req in pending:
            fi = config.CAMP_FIELDS.get(req["field_type"], {})
            lines.append(f"{fi.get('emoji', '')} {req['display_name']}: {req['name_ko']}")
            buttons.append([
                InlineKeyboardButton(f"✅ {req['name_ko']}", callback_data=f"camp_apv_{uid}_{req['id']}"),
                InlineKeyboardButton(f"❌ 거절", callback_data=f"camp_rej_{uid}_{req['id']}"),
            ])
        buttons.append([InlineKeyboardButton("◀ 닫기", callback_data=f"camp_close_{uid}")])

        await query.answer()
        try:
            await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")
        except Exception:
            pass

    # ── camp_apv_{uid}_{req_id} — 승인 ──
    elif data.startswith("camp_apv_"):
        uid = int(parts[2])
        req_id = int(parts[3])
        if query.from_user.id != uid:
            await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
            return

        chat_id = query.message.chat_id
        try:
            member_count = await context.bot.get_chat_member_count(chat_id)
        except Exception:
            member_count = 100

        success, msg = await cs.process_approval(req_id, member_count)
        await query.answer(msg, show_alert=True)

        # 승인 목록 갱신
        pending = await cq.get_pending_approvals(chat_id)
        if pending:
            lines = ["📋 승인 대기 목록", ""]
            buttons = []
            for req in pending:
                fi = config.CAMP_FIELDS.get(req["field_type"], {})
                lines.append(f"{fi.get('emoji', '')} {req['display_name']}: {req['name_ko']}")
                buttons.append([
                    InlineKeyboardButton(f"✅ {req['name_ko']}", callback_data=f"camp_apv_{uid}_{req['id']}"),
                    InlineKeyboardButton(f"❌ 거절", callback_data=f"camp_rej_{uid}_{req['id']}"),
                ])
            buttons.append([InlineKeyboardButton("◀ 닫기", callback_data=f"camp_close_{uid}")])
            try:
                await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")
            except Exception:
                pass
        else:
            try:
                await query.edit_message_text("✅ 모든 요청이 처리되었습니다.")
            except Exception:
                pass

    # ── camp_rej_{uid}_{req_id} — 거절 ──
    elif data.startswith("camp_rej_"):
        uid = int(parts[2])
        req_id = int(parts[3])
        if query.from_user.id != uid:
            await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
            return

        rejected = await cq.reject_request(req_id)
        await query.answer("거절했습니다." if rejected else "이미 처리된 요청입니다.")

        # 목록 갱신 (camp_approvals와 동일 로직)
        chat_id = query.message.chat_id
        pending = await cq.get_pending_approvals(chat_id)
        if pending:
            lines = ["📋 승인 대기 목록", ""]
            buttons = []
            for req in pending:
                fi = config.CAMP_FIELDS.get(req["field_type"], {})
                lines.append(f"{fi.get('emoji', '')} {req['display_name']}: {req['name_ko']}")
                buttons.append([
                    InlineKeyboardButton(f"✅ {req['name_ko']}", callback_data=f"camp_apv_{uid}_{req['id']}"),
                    InlineKeyboardButton(f"❌ 거절", callback_data=f"camp_rej_{uid}_{req['id']}"),
                ])
            buttons.append([InlineKeyboardButton("◀ 닫기", callback_data=f"camp_close_{uid}")])
            try:
                await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")
            except Exception:
                pass
        else:
            try:
                await query.edit_message_text("✅ 모든 요청이 처리되었습니다.")
            except Exception:
                pass


# ═══════════════════════════════════════════════════════
# 정산 DM 메시지 빌더
# ═══════════════════════════════════════════════════════

def _build_settlement_dm(result: dict, chat_title: str, camp_level: int) -> str:
    """정산 결과 DM 메시지 생성."""
    level_info = cs.get_level_info(camp_level)
    level_name = level_info[5]

    lines = [
        f"🏕 정산 알림 — {chat_title}",
        f"📊 Lv.{camp_level} {level_name}",
        "",
    ]

    for f in result["fields"]:
        fi = config.CAMP_FIELDS.get(f["field_type"], {})
        emoji = fi.get("emoji", "🏕")
        name = fi.get("name", f["field_type"])

        if not f["users"]:
            lines.append(f"{emoji} {name}: 비어있음")
        else:
            lines.append(f"{emoji} {name}: +{f['per_user']}조각 ({f['capped']}/{f['total_score']}점)")

    if result.get("level_up"):
        lines.append(f"\n🎉 캠프 레벨업! → Lv.{result['level_up']}")

    lines.append("")
    lines.append(f"📋 다음 정산: {_next_round_countdown()}")
    lines.append("💡 '캠프알림'으로 알림 on/off")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════
# 스케줄러 Jobs
# ═══════════════════════════════════════════════════════

async def camp_round_job(context):
    """라운드 정산 + 다음 라운드 보너스 생성 (3시간마다)."""
    chat_ids = await cq.get_camp_enabled_chats()
    now = config.get_kst_now()
    logger.info(f"[Camp] Round job for {len(chat_ids)} chats at {now.strftime('%H:%M')}")

    for chat_id in chat_ids:
        try:
            camp = await cq.get_camp(chat_id)
            if not camp:
                continue

            fields = await cq.get_fields(chat_id)
            if not fields:
                continue

            # 1) 이전 라운드 정산
            prev_round = cs.get_previous_round_time(now)
            result = await cs.settle_round(chat_id, prev_round)

            # 2) 배치 초기화 (매 라운드 리셋)
            cleared = await cq.clear_chat_placements(chat_id)
            if cleared:
                logger.info(f"[Camp] Cleared {cleared} placements for chat {chat_id}")

            # 3) 자동 승인 처리
            try:
                member_count = await context.bot.get_chat_member_count(chat_id)
            except Exception:
                member_count = 100
            await cs.process_auto_approvals(chat_id, member_count)

            # 4) 새 라운드 날씨 갱신
            cs.set_camp_weather(chat_id, cs.roll_weather())

            # 5) 다음 라운드 보너스 생성
            current_round = cs.normalize_round_time(now)
            await cs.generate_round_bonus(chat_id, fields, current_round)
            bonuses = await cq.get_round_bonus(chat_id, current_round)

            # 6) 통합 메시지 1개 발송 (정산 결과 + 새 보너스 + 날씨)
            if result["fields"]:
                text = cs.build_combined_announcement(
                    result, camp["level"], fields, bonuses, chat_id=chat_id,
                )
                msg = await context.bot.send_message(
                    chat_id=chat_id, text=text, parse_mode="HTML",
                )
                schedule_delete(msg, config.CAMP_MSG_DELETE_DELAY)

                # 거점캠프 유저에게 정산 DM
                try:
                    home_users = await cq.get_home_camp_users(chat_id)
                    if home_users:
                        chat_room = await queries.get_chat_room(chat_id)
                        chat_title = (chat_room.get("chat_title") if chat_room else None) or "캠프"
                        dm_text = _build_settlement_dm(result, chat_title, camp["level"])
                        for uid in home_users:
                            try:
                                await context.bot.send_message(chat_id=uid, text=dm_text)
                            except Exception:
                                pass
                except Exception:
                    logger.exception(f"[Camp] Settlement DM failed for chat {chat_id}")
            else:
                # 정산 결과 없어도 보너스 안내는 발송
                text = cs.build_bonus_announcement(fields, bonuses, chat_id=chat_id)
                msg = await context.bot.send_message(
                    chat_id=chat_id, text=text, parse_mode="HTML",
                )
                schedule_delete(msg, config.CAMP_MSG_DELETE_DELAY)

            # 7) 슬롯 빈자리 알림 + 대기 목록 초기화
            try:
                waitlist = await cq.get_slot_waitlist_users(chat_id)
                if waitlist:
                    chat_room_data = await queries.get_chat_room(chat_id)
                    c_title = (chat_room_data.get("chat_title") if chat_room_data else None) or "캠프"
                    for w in waitlist:
                        try:
                            await context.bot.send_message(
                                chat_id=w["user_id"],
                                text=(
                                    f"🔔 <b>{c_title}</b> 새 라운드가 시작되었습니다!\n"
                                    f"배치 슬롯이 초기화되었어요. 지금 배치해보세요."
                                ),
                                parse_mode="HTML",
                            )
                        except Exception:
                            pass
                    await cq.clear_slot_waitlist(chat_id)
            except Exception:
                logger.exception(f"[Camp] Slot waitlist notify failed for {chat_id}")

        except Exception:
            logger.exception(f"[Camp] Round job failed for chat {chat_id}")
