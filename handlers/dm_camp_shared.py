"""Camp DM handlers — 공유 헬퍼, 상수, 빌더 함수.

dm_camp.py 와 dm_camp_home/convert/manage 서브모듈 모두에서 임포트.
순환 임포트 방지를 위해 이 모듈은 서브모듈을 임포트하지 않는다.
"""

import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import config
from services import camp_service as cs
from utils.helpers import icon_emoji

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


# ── 공용 상수 ──
CAMP_LIST_PAGE_SIZE = 5
DM_PAGE_SIZE = 8
DECOMPOSE_PAGE_SIZE = 8
CONVERT_PAGE_SIZE = 8
VISIT_PAGE_SIZE = 6


# ── 공용 빌더 함수 ──

def _build_camp_list_page(camps: list[dict], user_id: int, page: int,
                          is_change: bool = False, exclude_chat_id: int | None = None) -> tuple[str, InlineKeyboardMarkup]:
    """캠프 목록 페이지 빌드 (거점 설정 / 거점 변경 공용)."""
    filtered = [c for c in camps if c["chat_id"] != exclude_chat_id] if exclude_chat_id else camps
    total_pages = max(1, (len(filtered) + CAMP_LIST_PAGE_SIZE - 1) // CAMP_LIST_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * CAMP_LIST_PAGE_SIZE
    page_items = filtered[start:start + CAMP_LIST_PAGE_SIZE]

    if is_change:
        lines = ["🔄 거점 변경", "", "⚠️ 변경 후 7일간 재변경 불가!", ""]
    else:
        lines = ["🏕 거점캠프를 설정하세요!", "",
                 "거점을 설정하면 DM으로 정산 결과를 받을 수 있어요.", ""]

    for c in page_items:
        title = c.get("chat_title") or f"채팅방 {c['chat_id']}"
        lv = c.get("level", 1)
        members = c.get("member_count") or 0
        lines.append(f"🏕 {title} (Lv.{lv}, {members}명)")

    if total_pages > 1:
        lines.append(f"\n📄 {page + 1}/{total_pages} 페이지")
    lines.append("")

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


def _build_camp2_list_page(camps: list[dict], user_id: int, page: int) -> tuple[str, InlineKeyboardMarkup]:
    """2번째 거점 캠프 목록 페이지 빌드 (페이지네이션 지원)."""
    total_pages = max(1, (len(camps) + CAMP_LIST_PAGE_SIZE - 1) // CAMP_LIST_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * CAMP_LIST_PAGE_SIZE
    page_items = camps[start:start + CAMP_LIST_PAGE_SIZE]

    lines = ["🏠 2번째 거점캠프를 설정하세요!", "", "⚠️ 설정 후 7일간 재변경 불가!", ""]

    for c in page_items:
        title = c.get("chat_title") or f"채팅방 {c['chat_id']}"
        lv = c.get("level", 1)
        members = c.get("member_count") or 0
        lines.append(f"🏕 {title} (Lv.{lv}, {members}명)")

    if total_pages > 1:
        lines.append(f"\n📄 {page + 1}/{total_pages} 페이지")
    lines.append("")

    buttons = []
    for c in page_items:
        title = c.get("chat_title") or f"채팅방 {c['chat_id']}"
        buttons.append([InlineKeyboardButton(
            f"🏕 {title}",
            callback_data=f"cdm_home2_{user_id}_{c['chat_id']}",
        )])

    # 페이지네이션 버튼
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀ 이전", callback_data=f"cdm_c2p_{user_id}_{page - 1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("다음 ▶", callback_data=f"cdm_c2p_{user_id}_{page + 1}"))
    if nav:
        buttons.append(nav)

    buttons.append([InlineKeyboardButton("❌ 취소", callback_data=f"cdm_cancel_{user_id}")])
    return "\n".join(lines), InlineKeyboardMarkup(buttons)


# ── 캠프 가이드 텍스트 ──
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
