"""Camp v2 DM handlers — 거점캠프, 내캠프, 이로치전환, 분해, 캠프알림, 캠프가이드."""

import time
import logging
from datetime import timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import config
from database import camp_queries as cq
from database import queries
from services import camp_service as cs
from utils.helpers import rarity_badge, shiny_emoji, icon_emoji, _type_emoji

logger = logging.getLogger(__name__)

# ── Duplicate-click guard ──
_callback_dedup: dict[str, float] = {}


def _is_duplicate_callback(query, cooldown: float = 1.5) -> bool:
    key = f"{query.message.message_id}:{query.data}:{query.from_user.id}"
    now = time.monotonic()
    if len(_callback_dedup) > 200:
        cutoff = now - 60
        stale = [k for k, v in _callback_dedup.items() if v < cutoff]
        for k in stale:
            del _callback_dedup[k]
    prev = _callback_dedup.get(key)
    if prev is not None and (now - prev) < cooldown:
        return True
    _callback_dedup[key] = now
    return False


def _pokemon_name(pid: int) -> str:
    """포켓몬 ID → 이름 (camp_service 캐시 활용)."""
    return cs._pokemon_name(pid)


def _next_round_countdown() -> str:
    """다음 정산까지 남은 시간 문자열."""
    now = config.get_kst_now()
    hours = sorted(config.CAMP_ROUND_HOURS)
    current_h = now.hour
    current_m = now.minute

    next_hour = None
    for h in hours:
        if h > current_h or (h == current_h and current_m == 0):
            next_hour = h
            break
    if next_hour is None:
        next_hour = hours[0]  # 내일 첫 라운드

    if next_hour > current_h:
        remain_min = (next_hour - current_h) * 60 - current_m
    elif next_hour == current_h:
        remain_min = 0
    else:
        remain_min = (24 - current_h + next_hour) * 60 - current_m

    h = remain_min // 60
    m = remain_min % 60
    next_time = f"{next_hour:02d}:00"
    if h > 0:
        return f"{next_time} ({h}시간 {m}분 후)"
    return f"{next_time} ({m}분 후)"


# ═══════════════════════════════════════════════════════
# DM 명령: 캠프 (메인 허브)
# ═══════════════════════════════════════════════════════

async def camp_hub_handler(update, context):
    """DM '캠프' — 캠프 메인 허브 메뉴."""
    user_id = update.effective_user.id
    user = await queries.get_user(user_id)
    if not user:
        await update.message.reply_text("먼저 포켓몬을 잡아보세요!")
        return

    settings = await cq.get_user_camp_settings(user_id)
    has_home = settings and settings.get("home_chat_id")

    # 거점 정보 요약
    lines = [
        f"{icon_emoji('pokecenter')} <b>캠프</b>",
        "━━━━━━━━━━━━━",
    ]

    if has_home:
        chat_room = await queries.get_chat_room(settings["home_chat_id"])
        camp = await cq.get_camp(settings["home_chat_id"])
        title = (chat_room.get("chat_title") if chat_room else None) or "알 수 없음"
        lv = camp["level"] if camp else 1
        level_info = cs.get_level_info(lv)
        lines.append(f"{icon_emoji('stationery')} 거점: {title} (Lv.{lv} {level_info[5]})")

        # 배치 현황 간략
        placements = await cq.get_user_placements_in_chat(settings["home_chat_id"], user_id)
        lines.append(f"{icon_emoji('bookmark')} 배치: {len(placements)}마리")

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
    lines.append("━━━━━━━━━━━━━")

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
    else:
        buttons.append([InlineKeyboardButton("🏕 거점 설정하기", callback_data=f"cdm_hub_home_{user_id}")])

    buttons.append([InlineKeyboardButton("📖 캠프 가이드", callback_data=f"cdm_guide_{user_id}_0")])

    await update.message.reply_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="HTML",
    )


CAMP_LIST_PAGE_SIZE = 5


def _build_camp_list_page(camps: list[dict], user_id: int, page: int,
                          is_change: bool = False, exclude_chat_id: int | None = None) -> tuple[str, InlineKeyboardMarkup]:
    """캠프 목록 페이지 빌드 (거점 설정 / 거점 변경 공용)."""
    filtered = [c for c in camps if c["chat_id"] != exclude_chat_id] if exclude_chat_id else camps
    total_pages = max(1, (len(filtered) + CAMP_LIST_PAGE_SIZE - 1) // CAMP_LIST_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * CAMP_LIST_PAGE_SIZE
    page_items = filtered[start:start + CAMP_LIST_PAGE_SIZE]

    if is_change:
        lines = ["🔄 거점 변경", "━━━━━━━━━━━━━", "⚠️ 변경 후 7일간 재변경 불가!", ""]
    else:
        lines = ["🏕 거점캠프를 설정하세요!", "━━━━━━━━━━━━━",
                 "거점을 설정하면 DM으로 정산 결과를 받을 수 있어요.", ""]

    for c in page_items:
        title = c.get("chat_title") or f"채팅방 {c['chat_id']}"
        lv = c.get("level", 1)
        members = c.get("member_count") or 0
        lines.append(f"🏕 {title} (Lv.{lv}, {members}명)")

    if total_pages > 1:
        lines.append(f"\n📄 {page + 1}/{total_pages} 페이지")
    lines.append("━━━━━━━━━━━━━")

    buttons = []
    for c in page_items:
        title = c.get("chat_title") or f"채팅방 {c['chat_id']}"
        buttons.append([InlineKeyboardButton(
            f"🏕 {title}",
            callback_data=f"cdm_home_{user_id}_{c['chat_id']}",
        )])

    # 페이지네이션 버튼
    nav = []
    mode = "chg" if is_change else "set"
    if page > 0:
        nav.append(InlineKeyboardButton("◀ 이전", callback_data=f"cdm_clp_{user_id}_{mode}_{page - 1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("다음 ▶", callback_data=f"cdm_clp_{user_id}_{mode}_{page + 1}"))
    if nav:
        buttons.append(nav)

    buttons.append([InlineKeyboardButton("❌ 닫기" if not is_change else "❌ 취소",
                                         callback_data=f"cdm_cancel_{user_id}")])
    return "\n".join(lines), InlineKeyboardMarkup(buttons)


# ═══════════════════════════════════════════════════════
# DM 명령: 거점캠프
# ═══════════════════════════════════════════════════════

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
                "🏕 거점캠프\n━━━━━━━━━━━━━\n"
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

    lines.append("━━━━━━━━━━━━━")
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

    lines.append("━━━━━━━━━━━━━")
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

    lines.append("━━━━━━━━━━━━━")

    # 버튼
    buttons = []
    buttons.append([InlineKeyboardButton("🏕 배치하기", callback_data=f"cdm_place_{user_id}")])

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

    await update.message.reply_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")


# ═══════════════════════════════════════════════════════
# DM 명령: 캠프알림
# ═══════════════════════════════════════════════════════

async def camp_notify_handler(update, context):
    """DM '캠프알림' — 정산 DM 알림 on/off 토글."""
    user_id = update.effective_user.id
    new_state = await cq.toggle_camp_notify(user_id)
    if new_state:
        await update.message.reply_text("🔔 캠프 정산 알림이 켜졌습니다.")
    else:
        await update.message.reply_text("🔕 캠프 정산 알림이 꺼졌습니다.")


# ═══════════════════════════════════════════════════════
# DM 명령: 캠프가이드
# ═══════════════════════════════════════════════════════

_GUIDE_STEPS = [
    # 1/8 — 전체 흐름
    (
        "🏕 【캠프 가이드 1/8】전체 흐름\n\n"
        "캠프는 포켓몬을 배치해서 조각을 모으고,\n"
        "조각으로 이로치를 만드는 시스템이에요!\n\n"
        "📋 흐름:\n"
        "1️⃣ 거점캠프 설정 (DM: '거점캠프')\n"
        "2️⃣ 필드에 포켓몬 배치 (DM: '캠프')\n"
        "3️⃣ 3시간마다 자동 정산 → 조각 획득\n"
        "4️⃣ 조각으로 이로치 전환 (DM: '이로치전환')\n"
        "5️⃣ 이로치 분해 → 결정 획득 (DM: '분해')\n"
        "6️⃣ 결정으로 에픽+ 이로치 전환!"
    ),
    # 2/8 — 필드와 타입
    (
        "🏕 【캠프 가이드 2/8】필드와 타입\n\n"
        "캠프에는 6가지 필드가 있고,\n"
        "각 필드에 맞는 타입의 포켓몬만 배치 가능!\n\n"
        "🌿 숲 — 풀/벌레/독\n"
        "🔥 화산 — 불/드래곤/격투\n"
        "💧 호수 — 물/얼음/비행\n"
        "⚡ 도시 — 전기/강철/노말\n"
        "🪨 동굴 — 땅/바위/고스트\n"
        "🔮 신전 — 에스퍼/악/페어리\n\n"
        "💡 배치할 때 타입이 맞는 포켓몬이\n"
        "자동으로 추천돼요!"
    ),
    # 3/8 — 보너스 조건
    (
        "🏕 【캠프 가이드 3/8】보너스 조건\n\n"
        "매 라운드 필드별로 보너스 포켓몬이 지정돼요.\n"
        "예) 🌿숲: 이상해씨 (공격 12↑)\n\n"
        "이 포켓몬을 갖고 있으면 점수가 높아져요!\n\n"
        "⭐ 핵심: 보너스에 나온 포켓몬을\n"
        "미리 잡아두거나 합성으로 만들어두세요.\n"
        "이로치 + 높은 개체값이면 최대 7점!\n\n"
        "💡 보너스 조건은 '거점캠프'에서 확인"
    ),
    # 4/8 — 점수 시스템
    (
        "🏕 【캠프 가이드 4/8】점수 시스템\n\n"
        "점수가 높을수록 조각을 더 많이 받아요!\n\n"
        "  ✅ 타입만 맞음 → 1점\n"
        "  ⭐ 보너스 포켓몬 → 2점\n"
        "  ⭐ + 개체값 충족 → 4점\n"
        "  ⭐ + 이로치 → 4점\n"
        "  🌟 보너스 + 개체값 + 이로치 → 7점\n\n"
        "💡 배치 후 1시간 이상 유지해야 정산 반영!"
    ),
    # 5/8 — 정산과 조각
    (
        "🏕 【캠프 가이드 5/8】정산과 조각\n\n"
        "📋 정산 시간 (매일 6회):\n"
        "09:00 / 12:00 / 15:00 / 18:00 / 21:00 / 00:00\n\n"
        "정산 때 점수만큼 해당 필드 조각을 받아요.\n"
        "예) 🌿숲에 3점 배치 → 🌿숲 조각 3개\n\n"
        "⚠️ 중요: 조각은 필드별로 따로 쌓여요!\n"
        "🌿숲 조각은 풀/벌레/독 포켓몬 전환에,\n"
        "🔥화산 조각은 불/드래곤/격투 전환에 사용!\n\n"
        "💡 '내캠프'로 보유 조각 현황 확인"
    ),
    # 6/8 — 이로치 전환
    (
        "🏕 【캠프 가이드 6/8】이로치 전환\n\n"
        "조각이 모이면 보유 포켓몬을 이로치로!\n"
        "DM에서 '이로치전환' 입력\n\n"
        "📋 등급별 전환 비용:\n"
        "  ⬜ 커먼: 조각 12개\n"
        "  🟦 레어: 조각 24개\n"
        "  🟪 에픽: 조각 42개 + 💎결정 5개\n"
        "  🟨 전설: 조각 60개 + 💎결정 15개\n"
        "  🌟 초전설: 조각 84개 + 💎결정 25개 + 🌈무지개 3개\n\n"
        "💡 에픽 이상은 결정이 필요해요 → 다음 단계!"
    ),
    # 7/8 — 이로치 분해
    (
        "🏕 【캠프 가이드 7/8】이로치 분해\n\n"
        "이로치를 분해하면 결정을 얻어요!\n"
        "DM에서 '분해' 입력\n\n"
        "📋 분해 결과 (이로치 → 결정):\n"
        "  ⬜ 커먼: 💎×1\n"
        "  🟦 레어: 💎×2\n"
        "  🟪 에픽: 💎×3\n"
        "  🟨 전설: 💎×5 + 🌈×1\n"
        "  🌟 초전설: 💎×15 + 🌈×2\n\n"
        "⚠️ 분해하면 이로치가 일반으로 돌아가요!\n"
        "💡 커먼/레어 이로치를 분해해서\n"
        "   에픽+ 전환에 필요한 결정을 모으세요."
    ),
    # 8/8 — DM 명령어 정리
    (
        "🏕 【캠프 가이드 8/8】명령어 정리\n\n"
        "📋 DM 명령어 한눈에:\n"
        "  '거점캠프' — 거점 설정 + 보너스 확인\n"
        "  '캠프' — 포켓몬 배치하기\n"
        "  '내캠프' — 조각/결정/배치 현황\n"
        "  '이로치전환' — 조각으로 이로치 만들기\n"
        "  '분해' — 이로치 → 결정 획득\n"
        "  '캠프알림' — 정산 DM 알림 on/off\n\n"
        "💡 전략 팁:\n"
        "• 보너스 포켓몬을 미리 잡아두세요\n"
        "• 개체값 높은 포켓몬일수록 유리\n"
        "• 커먼 이로치 분해 → 결정 모으기\n"
        "• 결정이 모이면 에픽+ 전환 도전!\n\n"
        "지금 '거점캠프'를 입력해서 시작하세요! 🎉"
    ),
]


DM_PAGE_SIZE = 8


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
        "━━━━━━━━━━━━━",
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

    lines.append("━━━━━━━━━━━━━")
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
        buttons = [[InlineKeyboardButton("◀ 돌아가기", callback_data=f"cdm_fback_{user_id}")]]
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

    buttons.append([InlineKeyboardButton("◀ 필드 선택", callback_data=f"cdm_fback_{user_id}")])
    return "\n".join(lines), InlineKeyboardMarkup(buttons)


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


# ═══════════════════════════════════════════════════════
# DM 명령: 내캠프
# ═══════════════════════════════════════════════════════

async def my_camp_handler(update, context):
    """DM '내캠프' — 배치 현황 + 조각 + 결정."""
    user_id = update.effective_user.id
    user = await queries.get_user(user_id)
    if not user:
        await update.message.reply_text("먼저 포켓몬을 잡아보세요!")
        return

    summary = await cs.get_user_camp_summary(user_id)

    lines = ["🏕 내 캠프 현황", "━━━━━━━━━━━━━"]

    # 거점 캠프
    if summary["home_camp"]:
        chat_room = await queries.get_chat_room(summary["home_camp"])
        title = (chat_room.get("chat_title") if chat_room else None) or "알 수 없음"
        lines.append(f"🏠 거점: {title}")
    else:
        lines.append("🏠 거점: 미설정 ('거점캠프' 입력)")

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

    # 쿨타임
    if summary["cooldown_remaining"]:
        hours = int(summary["cooldown_remaining"] // 3600)
        mins = int((summary["cooldown_remaining"] % 3600) // 60)
        lines.append(f"\n⏰ 전환 쿨타임: {hours}시간 {mins}분 남음")

    lines.append("\n━━━━━━━━━━━━━")

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

    lines.append("━━━━━━━━━━━━━")

    # 힌트
    hints = []
    total_frags = sum(frags.values()) if frags else 0
    if total_frags >= 12:
        hints.append(f"{shiny_emoji()} '이로치전환'으로 이로치 변환!")
    if crystals["crystal"] == 0 and total_frags > 0:
        hints.append("🔨 '분해'로 이로치를 결정으로!")
    if hints:
        lines.extend(hints)

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


# ═══════════════════════════════════════════════════════
# DM 명령: 이로치전환
# ═══════════════════════════════════════════════════════

async def shiny_convert_handler(update, context):
    """DM '이로치전환' — 전환 가능 포켓몬 리스트."""
    user_id = update.effective_user.id
    user = await queries.get_user(user_id)
    if not user:
        await update.message.reply_text("먼저 포켓몬을 잡아보세요!")
        return

    frags = await cq.get_user_fragments(user_id)
    crystals = await cq.get_crystals(user_id)

    pokemon_list = await queries.get_user_pokemon_list(user_id)
    eligible = []
    for p in pokemon_list:
        if p.get("is_shiny"):
            continue
        matching_fields = cs.get_matching_fields(p["pokemon_id"])
        if not matching_fields:
            continue

        rarity = p.get("rarity", "common")
        frag_cost = config.CAMP_SHINY_COST.get(rarity, 12)
        crystal_cost = config.CAMP_CRYSTAL_COST.get(rarity, 0)
        rainbow_cost = config.CAMP_RAINBOW_COST.get(rarity, 0)

        can_afford_frags = any(frags.get(f, 0) >= frag_cost for f in matching_fields)
        can_afford_crystal = crystals["crystal"] >= crystal_cost
        can_afford_rainbow = crystals["rainbow"] >= rainbow_cost
        can_afford = can_afford_frags and can_afford_crystal and can_afford_rainbow

        eligible.append({
            "instance_id": p["id"],
            "pokemon_id": p["pokemon_id"],
            "name_ko": p["name_ko"],
            "rarity": rarity,
            "frag_cost": frag_cost,
            "crystal_cost": crystal_cost,
            "rainbow_cost": rainbow_cost,
            "can_afford": can_afford,
            "matching_fields": matching_fields,
        })

    if not eligible:
        await update.message.reply_text(
            f"{shiny_emoji()} 이로치 전환 가능한 포켓몬이 없습니다.\n"
            "조각이 부족하거나, 보유 포켓몬이 모두 이로치입니다.",
            parse_mode="HTML",
        )
        return

    affordable = [e for e in eligible if e["can_afford"]][:10]
    unaffordable = [e for e in eligible if not e["can_afford"]][:5]

    total_frags = sum(frags.values())
    lines = [
        f"{shiny_emoji()} 이로치 전환",
        "━━━━━━━━━━━━━",
        f"🧩 보유 조각: {total_frags}개",
        f"💎 결정: {crystals['crystal']}개 | 🌈 무지개: {crystals['rainbow']}개",
        "",
    ]

    buttons = []
    if affordable:
        lines.append("── 전환 가능 ──")
        for e in affordable:
            cost_parts = [f"{e['frag_cost']}조각"]
            if e["crystal_cost"]:
                cost_parts.append(f"결정{e['crystal_cost']}")
            if e["rainbow_cost"]:
                cost_parts.append(f"무지개{e['rainbow_cost']}")
            rarity_tag = rarity_badge(e.get("rarity", ""))
            lines.append(f"{icon_emoji('check')} {rarity_tag}{e['name_ko']} — {'+'.join(cost_parts)}")
            buttons.append([InlineKeyboardButton(
                f"✨ {e['name_ko']} 전환",
                callback_data=f"cdm_conv_{user_id}_{e['instance_id']}",
            )])

    if unaffordable:
        lines.append("\n── 자원 부족 ──")
        for e in unaffordable:
            cost_parts = [f"{e['frag_cost']}조각"]
            if e["crystal_cost"]:
                cost_parts.append(f"결정{e['crystal_cost']}")
            rarity_tag = rarity_badge(e.get("rarity", ""))
            lines.append(f"❌ {rarity_tag}{e['name_ko']} — {'+'.join(cost_parts)}")

    lines.append("━━━━━━━━━━━━━")

    markup = InlineKeyboardMarkup(buttons) if buttons else None
    await update.message.reply_text("\n".join(lines), reply_markup=markup, parse_mode="HTML")


# ═══════════════════════════════════════════════════════
# DM 명령: 분해
# ═══════════════════════════════════════════════════════

async def decompose_handler(update, context):
    """DM '분해' — 이로치 분해로 결정 획득."""
    user_id = update.effective_user.id
    user = await queries.get_user(user_id)
    if not user:
        await update.message.reply_text("먼저 포켓몬을 잡아보세요!")
        return

    pokemon_list = await queries.get_user_pokemon_list(user_id)
    shinies = [p for p in pokemon_list if p.get("is_shiny")]

    if not shinies:
        await update.message.reply_text("분해할 이로치 포켓몬이 없습니다.")
        return

    crystals = await cq.get_crystals(user_id)

    lines = [
        "🔨 이로치 분해",
        "━━━━━━━━━━━━━",
        f"💎 결정: {crystals['crystal']}개 | 🌈 무지개: {crystals['rainbow']}개",
        "",
        "⚠️ 분해하면 이로치가 해제됩니다!",
        "",
    ]

    buttons = []
    for p in shinies[:15]:
        rarity = p.get("rarity", "common")
        crystal_gain = config.CAMP_DECOMPOSE_CRYSTAL.get(rarity, 1)
        rainbow_gain = config.CAMP_DECOMPOSE_RAINBOW.get(rarity, 0)

        gain_parts = [f"💎+{crystal_gain}"]
        if rainbow_gain:
            gain_parts.append(f"🌈+{rainbow_gain}")

        rarity_tag = rarity_badge(rarity or "")
        lines.append(f"{shiny_emoji()} {rarity_tag}{p['name_ko']} → {' '.join(gain_parts)}")
        buttons.append([InlineKeyboardButton(
            f"🔨 {p['name_ko']} 분해",
            callback_data=f"cdm_dec_{user_id}_{p['id']}",
        )])

    lines.append("━━━━━━━━━━━━━")

    await update.message.reply_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")


# ═══════════════════════════════════════════════════════
# 콜백 라우터 (cdm_*)
# ═══════════════════════════════════════════════════════

async def camp_dm_callback_handler(update, context):
    """cdm_* 콜백 전체 라우터."""
    query = update.callback_query
    if not query or not query.data:
        return

    if _is_duplicate_callback(query):
        await query.answer()
        return

    data = query.data
    parts = data.split("_")

    # ── cdm_home_{uid}_{chat_id} — 거점 설정 ──
    if data.startswith("cdm_home_"):
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

    # ── cdm_chghome_{uid} — 거점 변경 목록 ──
    elif data.startswith("cdm_chghome_"):
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

    # ── cdm_place_{uid} — DM에서 거점캠프 필드 선택 ──
    elif data.startswith("cdm_place_"):
        uid = int(parts[2])
        if query.from_user.id != uid:
            await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
            return

        settings = await cq.get_user_camp_settings(uid)
        if not settings or not settings.get("home_chat_id"):
            await query.answer("먼저 거점캠프를 설정하세요!", show_alert=True)
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

    # ── cdm_rm_{uid}_{placement_id} — DM 배치 해제 ──
    elif data.startswith("cdm_rm_"):
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

        # 필드 선택 화면 새로고침
        settings = await cq.get_user_camp_settings(uid)
        if settings and settings.get("home_chat_id"):
            chat_id = settings["home_chat_id"]
            camp = await cq.get_camp(chat_id)
            if camp:
                fields = await cq.get_fields(chat_id)
                text, markup = await _build_dm_field_buttons(uid, chat_id, fields, camp)
                try:
                    await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
                except Exception:
                    pass

    # ── cdm_fd_{uid}_{field_id} — DM 필드 선택 → 포켓몬 리스트 ──
    elif data.startswith("cdm_fd_"):
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

    # ── cdm_pk_{uid}_{field_id}_{instance_id} — DM에서 포켓몬 배치 ──
    elif data.startswith("cdm_pk_"):
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

    # ── cdm_pp_{uid}_{field_id}_{page} — DM 포켓몬 리스트 페이지네이션 ──
    elif data.startswith("cdm_pp_"):
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

    # ── cdm_fback_{uid} — DM 필드 선택으로 복귀 ──
    elif data.startswith("cdm_fback_"):
        uid = int(parts[2])
        if query.from_user.id != uid:
            await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
            return

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

    # ── cdm_guide_{uid}_{step} — 캠프 가이드 페이지 ──
    elif data.startswith("cdm_guide_"):
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

    # ── cdm_noop_{uid} — 아무 동작 없음 ──
    elif data.startswith("cdm_noop_"):
        await query.answer("거점 변경 쿨다운 중입니다.", show_alert=True)

    # ── cdm_conv_{uid}_{instance_id} — 전환 확인 ──
    elif data.startswith("cdm_conv_"):
        uid = int(parts[2])
        instance_id = int(parts[3])
        if query.from_user.id != uid:
            await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
            return

        pokemon = await queries.get_user_pokemon_by_id(instance_id)
        if not pokemon or pokemon["user_id"] != uid:
            await query.answer("잘못된 선택입니다.", show_alert=True)
            return

        rarity = pokemon.get("rarity", "common")
        frag_cost = config.CAMP_SHINY_COST.get(rarity, 12)
        crystal_cost = config.CAMP_CRYSTAL_COST.get(rarity, 0)
        rainbow_cost = config.CAMP_RAINBOW_COST.get(rarity, 0)
        cooldown_sec = config.CAMP_SHINY_COOLDOWN.get(rarity, 21600)
        cooldown_h = cooldown_sec // 3600

        matching_fields = cs.get_matching_fields(pokemon["pokemon_id"])
        field_names = "/".join(config.CAMP_FIELDS[f]["name"] for f in matching_fields)

        cost_parts = [f"🧩 {field_names} 조각 {frag_cost}개"]
        if crystal_cost:
            cost_parts.append(f"💎 결정 {crystal_cost}개")
        if rainbow_cost:
            cost_parts.append(f"🌈 무지개 결정 {rainbow_cost}개")

        text = (
            f"✨ {pokemon['name_ko']}을(를) 이로치로 전환하시겠습니까?\n\n"
            f"비용:\n" + "\n".join(f"  {c}" for c in cost_parts) + "\n\n"
            f"⏰ 전환 후 쿨타임: {cooldown_h}시간\n"
            f"⚠️ 되돌릴 수 없습니다!"
        )
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ 전환!", callback_data=f"cdm_ok_{uid}_{instance_id}")],
            [InlineKeyboardButton("❌ 취소", callback_data=f"cdm_cancel_{uid}")],
        ])

        await query.answer()
        try:
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
        except Exception:
            pass

    # ── cdm_ok_{uid}_{instance_id} — 전환 실행 ──
    elif data.startswith("cdm_ok_"):
        uid = int(parts[2])
        instance_id = int(parts[3])
        if query.from_user.id != uid:
            await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
            return

        success, msg = await cs.convert_to_shiny(uid, instance_id)
        await query.answer(msg[:200], show_alert=True)
        try:
            await query.edit_message_text(msg, parse_mode="HTML")
        except Exception:
            pass

    # ── cdm_dec_{uid}_{instance_id} — 분해 확인 ──
    elif data.startswith("cdm_dec_"):
        uid = int(parts[2])
        instance_id = int(parts[3])
        if query.from_user.id != uid:
            await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
            return

        pokemon = await queries.get_user_pokemon_by_id(instance_id)
        if not pokemon or pokemon["user_id"] != uid:
            await query.answer("잘못된 선택입니다.", show_alert=True)
            return

        rarity = pokemon.get("rarity", "common")
        crystal_gain = config.CAMP_DECOMPOSE_CRYSTAL.get(rarity, 1)
        rainbow_gain = config.CAMP_DECOMPOSE_RAINBOW.get(rarity, 0)

        gain_parts = [f"💎 결정 +{crystal_gain}"]
        if rainbow_gain:
            gain_parts.append(f"🌈 무지개 결정 +{rainbow_gain}")

        text = (
            f"🔨 {pokemon['name_ko']}(이로치)를 분해하시겠습니까?\n\n"
            f"획득:\n" + "\n".join(f"  {g}" for g in gain_parts) + "\n\n"
            f"⚠️ 이로치가 해제됩니다! 되돌릴 수 없습니다!"
        )
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔨 분해!", callback_data=f"cdm_decok_{uid}_{instance_id}")],
            [InlineKeyboardButton("❌ 취소", callback_data=f"cdm_cancel_{uid}")],
        ])

        await query.answer()
        try:
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
        except Exception:
            pass

    # ── cdm_decok_{uid}_{instance_id} — 분해 실행 ──
    elif data.startswith("cdm_decok_"):
        uid = int(parts[2])
        instance_id = int(parts[3])
        if query.from_user.id != uid:
            await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
            return

        success, msg = await cs.decompose_shiny(uid, instance_id)
        await query.answer(msg[:200], show_alert=True)
        try:
            await query.edit_message_text(msg, parse_mode="HTML")
        except Exception:
            pass

    # ── cdm_clp_{uid}_{mode}_{page} — 캠프 목록 페이지네이션 ──
    elif data.startswith("cdm_clp_"):
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

    # ── cdm_hub_mycamp_{uid} — 내캠프 (허브에서) ──
    elif data.startswith("cdm_hub_mycamp_"):
        uid = int(parts[3])
        if query.from_user.id != uid:
            await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
            return

        await query.answer()
        summary = await cs.get_user_camp_summary(uid)

        lines = [f"{icon_emoji('pokecenter')} 내 캠프 현황", "━━━━━━━━━━━━━"]

        if summary["home_camp"]:
            chat_room = await queries.get_chat_room(summary["home_camp"])
            title = (chat_room.get("chat_title") if chat_room else None) or "알 수 없음"
            lines.append(f"🏠 거점: {title}")
        else:
            lines.append("🏠 거점: 미설정")

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

        if summary["cooldown_remaining"]:
            hours = int(summary["cooldown_remaining"] // 3600)
            mins = int((summary["cooldown_remaining"] % 3600) // 60)
            lines.append(f"\n⏰ 전환 쿨타임: {hours}시간 {mins}분 남음")

        placements = summary["placements"]
        lines.append("\n━━━━━━━━━━━━━")
        if placements:
            lines.append(f"{icon_emoji('bookmark')} 배치 ({len(placements)}마리)")
            for p in placements:
                fi = config.CAMP_FIELDS.get(p.get("field_type", ""), {})
                shiny = shiny_emoji() if p.get("is_shiny") else ""
                lines.append(f"  {fi.get('emoji', '🏕')} {shiny}{p['name_ko']} ({p['score']}점)")
        else:
            lines.append(f"{icon_emoji('bookmark')} 배치: 없음")

        lines.append("━━━━━━━━━━━━━")

        try:
            await query.edit_message_text("\n".join(lines), parse_mode="HTML")
        except Exception:
            pass

    # ── cdm_hub_convert_{uid} — 이로치전환 (허브에서) ──
    elif data.startswith("cdm_hub_convert_"):
        uid = int(parts[3])
        if query.from_user.id != uid:
            await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
            return

        await query.answer()
        # 기존 shiny_convert_handler 로직을 인라인으로 실행
        frags = await cq.get_user_fragments(uid)
        crystals_data = await cq.get_crystals(uid)
        pokemon_list = await queries.get_user_pokemon_list(uid)
        eligible = []
        for p in pokemon_list:
            if p.get("is_shiny"):
                continue
            matching_fields = cs.get_matching_fields(p["pokemon_id"])
            if not matching_fields:
                continue
            rarity = p.get("rarity", "common")
            frag_cost = config.CAMP_SHINY_COST.get(rarity, 12)
            crystal_cost = config.CAMP_CRYSTAL_COST.get(rarity, 0)
            rainbow_cost = config.CAMP_RAINBOW_COST.get(rarity, 0)
            can_afford_frags = any(frags.get(f, 0) >= frag_cost for f in matching_fields)
            can_afford = can_afford_frags and crystals_data["crystal"] >= crystal_cost and crystals_data["rainbow"] >= rainbow_cost
            eligible.append({
                "instance_id": p["id"], "name_ko": p["name_ko"], "rarity": rarity,
                "frag_cost": frag_cost, "crystal_cost": crystal_cost, "can_afford": can_afford,
            })

        if not eligible:
            try:
                await query.edit_message_text(
                    f"{shiny_emoji()} 이로치 전환 가능한 포켓몬이 없습니다.\n"
                    "조각이 부족하거나, 보유 포켓몬이 모두 이로치입니다.",
                    parse_mode="HTML",
                )
            except Exception:
                pass
            return

        affordable = [e for e in eligible if e["can_afford"]][:10]
        total_frags = sum(frags.values())
        lines = [
            f"{shiny_emoji()} 이로치 전환", "━━━━━━━━━━━━━",
            f"{icon_emoji('gotcha')} 보유 조각: {total_frags}개",
            f"{icon_emoji('crystal')} 결정: {crystals_data['crystal']}개 | 🌈 무지개: {crystals_data['rainbow']}개", "",
        ]
        buttons = []
        if affordable:
            lines.append("── 전환 가능 ──")
            for e in affordable:
                cost_parts = [f"{e['frag_cost']}조각"]
                if e["crystal_cost"]:
                    cost_parts.append(f"결정{e['crystal_cost']}")
                rarity_tag = rarity_badge(e.get("rarity", ""))
                lines.append(f"{icon_emoji('check')} {rarity_tag}{e['name_ko']} — {'+'.join(cost_parts)}")
                buttons.append([InlineKeyboardButton(
                    f"✨ {e['name_ko']} 전환",
                    callback_data=f"cdm_conv_{uid}_{e['instance_id']}",
                )])
        lines.append("━━━━━━━━━━━━━")
        markup = InlineKeyboardMarkup(buttons) if buttons else None
        try:
            await query.edit_message_text("\n".join(lines), reply_markup=markup, parse_mode="HTML")
        except Exception:
            pass

    # ── cdm_hub_decompose_{uid} — 분해 (허브에서) ──
    elif data.startswith("cdm_hub_decompose_"):
        uid = int(parts[3])
        if query.from_user.id != uid:
            await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
            return

        await query.answer()
        pokemon_list = await queries.get_user_pokemon_list(uid)
        shinies = [p for p in pokemon_list if p.get("is_shiny")]

        if not shinies:
            try:
                await query.edit_message_text("분해할 이로치 포켓몬이 없습니다.")
            except Exception:
                pass
            return

        crystals_data = await cq.get_crystals(uid)
        lines = [
            "🔨 이로치 분해", "━━━━━━━━━━━━━",
            f"{icon_emoji('crystal')} 결정: {crystals_data['crystal']}개 | 🌈 무지개: {crystals_data['rainbow']}개",
            "", "⚠️ 분해하면 이로치가 해제됩니다!", "",
        ]
        buttons = []
        for p in shinies[:15]:
            rarity = p.get("rarity", "common")
            crystal_gain = config.CAMP_DECOMPOSE_CRYSTAL.get(rarity, 1)
            rainbow_gain = config.CAMP_DECOMPOSE_RAINBOW.get(rarity, 0)
            gain_parts = [f"💎+{crystal_gain}"]
            if rainbow_gain:
                gain_parts.append(f"🌈+{rainbow_gain}")
            rarity_tag = rarity_badge(rarity or "")
            lines.append(f"{shiny_emoji()} {rarity_tag}{p['name_ko']} → {' '.join(gain_parts)}")
            buttons.append([InlineKeyboardButton(
                f"🔨 {p['name_ko']} 분해",
                callback_data=f"cdm_dec_{uid}_{p['id']}",
            )])
        lines.append("━━━━━━━━━━━━━")
        try:
            await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")
        except Exception:
            pass

    # ── cdm_hub_home_{uid} — 거점캠프 (허브에서) ──
    elif data.startswith("cdm_hub_home_"):
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
                        "🏕 거점캠프\n━━━━━━━━━━━━━\n"
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

        hlines = [f"🏕 거점캠프 — {chat_title}"]
        if chat_room and chat_room.get("invite_link"):
            hlines.append(f"👉 {chat_room['invite_link']}")
        hlines.append("━━━━━━━━━━━━━")
        hlines.append(f"{icon_emoji('stationery')} 캠프 레벨: Lv.{camp['level']} {level_info[5]}")

        for f in fields:
            fi = config.CAMP_FIELDS.get(f["field_type"], {})
            emoji = fi.get("emoji", "🏕")
            name = fi.get("name", f["field_type"])
            placed = placed_map.get(f["id"])
            if placed:
                shiny = shiny_emoji() if placed.get("is_shiny") else ""
                hlines.append(f"{emoji} {name} — {shiny}{placed['name_ko']} ({placed['score']}점)")
            else:
                hlines.append(f"{emoji} {name} — 비어있음")

        hlines.append("━━━━━━━━━━━━━")
        hlines.append(f"{icon_emoji('bookmark')} 다음 정산: {_next_round_countdown()}")

        if bonuses:
            hlines.append("")
            hlines.append("🔄 라운드 보너스 조건:")
            for f in fields:
                bonus = bonus_map.get(f["id"])
                if bonus:
                    fi = config.CAMP_FIELDS.get(f["field_type"], {})
                    pname = _pokemon_name(bonus["pokemon_id"])
                    stat_name = config.CAMP_IV_STAT_NAMES.get(bonus["stat_type"], "")
                    hlines.append(f"  {fi.get('emoji', '🏕')} {fi.get('name', '')}: {pname} ({stat_name} {bonus['stat_value']}↑)")

        hlines.append("━━━━━━━━━━━━━")

        hbuttons = []
        hbuttons.append([InlineKeyboardButton("🏕 배치하기", callback_data=f"cdm_place_{uid}")])
        if settings.get("home_camp_set_at"):
            elapsed = (now - settings["home_camp_set_at"]).total_seconds()
            if elapsed >= config.CAMP_HOME_COOLDOWN:
                hbuttons.append([InlineKeyboardButton("🔄 거점변경", callback_data=f"cdm_chghome_{uid}")])
            else:
                change_date = (settings["home_camp_set_at"] + timedelta(days=7)).strftime("%m/%d")
                hbuttons.append([InlineKeyboardButton(f"🔒 거점변경 ({change_date} 이후)", callback_data=f"cdm_noop_{uid}")])
        else:
            hbuttons.append([InlineKeyboardButton("🔄 거점변경", callback_data=f"cdm_chghome_{uid}")])

        try:
            await query.edit_message_text("\n".join(hlines), reply_markup=InlineKeyboardMarkup(hbuttons), parse_mode="HTML")
        except Exception:
            pass

    # ── cdm_hub_notify_{uid} — 알림 토글 (허브에서) ──
    elif data.startswith("cdm_hub_notify_"):
        uid = int(parts[3])
        if query.from_user.id != uid:
            await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
            return

        new_state = await cq.toggle_camp_notify(uid)
        if new_state:
            await query.answer("🔔 캠프 정산 알림이 켜졌습니다!", show_alert=True)
        else:
            await query.answer("🔕 캠프 정산 알림이 꺼졌습니다.", show_alert=True)

    # ── cdm_hub_mvp_{uid} — 주간 MVP 랭킹 ──
    elif data.startswith("cdm_hub_mvp_"):
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
            "━━━━━━━━━━━━━",
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
        lines.append("━━━━━━━━━━━━━")
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

    # ── cdm_hub_back_{uid} — 허브로 돌아가기 ──
    elif data.startswith("cdm_hub_back_"):
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
            "━━━━━━━━━━━━━",
        ]
        if has_home:
            chat_room = await queries.get_chat_room(settings["home_chat_id"])
            camp = await cq.get_camp(settings["home_chat_id"])
            t = (chat_room.get("chat_title") if chat_room else None) or "알 수 없음"
            lv = camp["level"] if camp else 1
            level_info = cs.get_level_info(lv)
            hub_lines.append(f"{icon_emoji('stationery')} 거점: {t} (Lv.{lv} {level_info[5]})")
            placements = await cq.get_user_placements_in_chat(settings["home_chat_id"], uid)
            hub_lines.append(f"{icon_emoji('bookmark')} 배치: {len(placements)}마리")
            frags = await cq.get_user_fragments(uid)
            total_frags = sum(frags.values()) if frags else 0
            crystals = await cq.get_crystals(uid)
            hub_lines.append(f"{icon_emoji('gotcha')} 조각: {total_frags}개 | {icon_emoji('crystal')} 결정: {crystals['crystal']}개")
        else:
            hub_lines += ["", "아직 거점캠프가 없습니다!", "아래 버튼으로 시작하세요."]

        hub_lines += ["", f"{icon_emoji('bookmark')} 다음 정산: {_next_round_countdown()}", "━━━━━━━━━━━━━"]

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
        else:
            btns.append([InlineKeyboardButton("🏕 거점 설정하기", callback_data=f"cdm_hub_home_{uid}")])
        btns.append([InlineKeyboardButton("📖 캠프 가이드", callback_data=f"cdm_guide_{uid}_0")])

        try:
            await query.edit_message_text(
                "\n".join(hub_lines),
                reply_markup=InlineKeyboardMarkup(btns),
                parse_mode="HTML",
            )
        except Exception:
            pass

    # ── cdm_cancel_{uid} — 취소 ──
    elif data.startswith("cdm_cancel_"):
        uid = int(parts[2])
        if query.from_user.id != uid:
            await query.answer()
            return
        await query.answer()
        try:
            await query.edit_message_text("취소되었습니다.")
        except Exception:
            pass
