"""DM 타로 리딩 핸들러 — 신비로운 피카의 타로."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Update
from telegram.ext import ContextTypes

from database import queries
from services.fortune_service import (
    generate_reading, format_reading_message,
    get_zodiac, SPREADS, TOPIC_EMOJIS, TIME_RANGES, DEFAULT_TIME_RANGE,
)

_log = logging.getLogger(__name__)
_TAROT_IMG_DIR = Path(__file__).parent.parent / "assets" / "tarot"
_CARD_SELECT_IMG = _TAROT_IMG_DIR / "card_select.png"

# 엎어진 카드 이모지
_CARD_BACK = "🂠"
_CARD_PICKED = "✦"

# 펼쳐놓을 엎어진 카드 수
_FACEDOWN_COUNT = 7

# ── 주제별 상황 질문 (1단계) ──

_TOPIC_CONTEXTS = {
    "연애": {
        "question": "...지금 어떤 상황인가요?\n상황을 알면 카드가 더 정확히 말해줄 수 있어요.",
        "options": [
            ("💑 연애 중이에요", "연애중"),
            ("💭 짝사랑/썸 타는 중이에요", "짝사랑"),
            ("🙂 솔로예요", "솔로"),
            ("💍 기혼이에요", "기혼"),
            ("💔 이별/별거 중이에요", "이별"),
        ],
    },
    "직장": {
        "question": "...지금 어떤 상황인가요?",
        "options": [
            ("🏢 직장에 다니고 있어요", "재직중"),
            ("🔍 이직/구직 중이에요", "구직중"),
            ("📚 학생이에요", "학생"),
            ("🏪 사업/프리랜서예요", "사업"),
        ],
    },
    "재물": {
        "question": "...재물에 대해 궁금한 게 있군요.\n어떤 부분이 가장 신경 쓰여요?",
        "options": [
            ("💵 수입/월급이 고민이에요", "수입"),
            ("🏦 저축/자산 관리가 궁금해요", "저축"),
            ("💸 지출이 걱정돼요", "지출"),
            ("🍀 횡재/기회가 올까요", "횡재"),
        ],
    },
    "투자": {
        "question": "...투자에 대해 물어보고 싶군요.\n어떤 상황인가요?",
        "options": [
            ("📊 투자 중이에요", "투자중"),
            ("🤔 투자를 시작하려고요", "시작"),
            ("📉 손실이 있어요", "손실"),
            ("💎 장기 투자 중이에요", "장기"),
        ],
    },
    "인간관계": {
        "question": "...누군가와의 관계가 마음에 걸리나요?\n어떤 관계인가요?",
        "options": [
            ("👨‍👩‍👧 가족이에요", "가족"),
            ("👥 친구예요", "친구"),
            ("🏢 직장 동료/상사예요", "직장"),
            ("🤷 그냥 전반적으로요", "전반"),
        ],
    },
    "종합": {
        "question": "...종합 리딩이군요.\n지금 가장 마음에 걸리는 건 뭐예요?",
        "options": [
            ("🔄 변화가 필요해요", "변화"),
            ("😟 고민이 있어요", "고민"),
            ("✨ 앞으로가 궁금해요", "미래"),
            ("🙂 그냥 오늘의 메시지", "메시지"),
        ],
    },
}

# ── 세부 질문 (2단계 — 상태별 분기) ──

_SUB_QUESTIONS: dict[str, dict[str, dict]] = {
    "연애": {
        "연애중": {
            "question": "...어떤 게 궁금한가요?",
            "options": [
                ("💜 상대방 마음이 궁금해요", "상대마음"),
                ("🔮 이 관계의 미래가 궁금해요", "관계미래"),
                ("💍 결혼/다음 단계가 궁금해요", "다음단계"),
                ("😔 요즘 관계가 불안해요", "불안"),
            ],
        },
        "짝사랑": {
            "question": "...두근거리는 마음이 느껴져요.\n뭐가 가장 궁금해요?",
            "options": [
                ("💜 상대방 마음이 궁금해요", "상대마음"),
                ("💌 고백해도 될까요", "고백"),
                ("🌸 이 썸, 이어질까요", "성사"),
                ("🤔 어떻게 다가가야 할까요", "접근법"),
            ],
        },
        "솔로": {
            "question": "...새로운 인연이 기다리고 있을지도 몰라요.\n뭐가 궁금해요?",
            "options": [
                ("🌹 새 만남은 언제 올까요", "새만남"),
                ("✨ 어떤 사람을 만나게 될까요", "이상형"),
                ("💪 연애 준비가 됐을까요", "준비"),
            ],
        },
        "기혼": {
            "question": "...결혼 생활에 대해 물어볼게요.\n어떤 게 궁금한가요?",
            "options": [
                ("💑 부부 관계의 미래", "부부미래"),
                ("😔 권태기/갈등이 있어요", "권태기"),
                ("🤔 배우자 마음이 궁금해요", "상대마음"),
                ("👶 임신/출산이 궁금해요", "임신"),
            ],
        },
        "이별": {
            "question": "...힘든 시기를 보내고 있군요.\n뭐가 가장 궁금해요?",
            "options": [
                ("🔄 재회 가능성이 있을까요", "재회"),
                ("💜 그 사람 지금 마음은", "상대마음"),
                ("🌱 새 연애는 언제 올까요", "새시작"),
                ("💫 지금 나에게 필요한 건", "회복"),
            ],
        },
    },
    "직장": {
        "재직중": {
            "question": "...직장에서 어떤 게 궁금한가요?",
            "options": [
                ("📈 승진/연봉이 궁금해요", "승진"),
                ("🤝 직장 내 관계가 고민이에요", "직장관계"),
                ("🚪 이직을 고민 중이에요", "이직고민"),
                ("📋 지금 프로젝트 결과가 궁금해요", "프로젝트"),
            ],
        },
        "구직중": {
            "question": "...좋은 소식이 오길 바라고 있겠네요.",
            "options": [
                ("⏰ 취업 시기가 궁금해요", "취업시기"),
                ("📝 면접 결과가 궁금해요", "면접"),
                ("🧭 진로 방향이 고민이에요", "진로"),
            ],
        },
        "학생": {
            "question": "...학업에 대해 물어볼게요.",
            "options": [
                ("📖 시험/성적이 궁금해요", "시험"),
                ("🧭 진로/취업 방향이 궁금해요", "진로"),
                ("🤝 학교 인간관계가 고민이에요", "학교관계"),
            ],
        },
        "사업": {
            "question": "...사업가의 에너지가 느껴져요.",
            "options": [
                ("📊 사업 전망이 궁금해요", "사업전망"),
                ("🤝 파트너/거래처 관계", "파트너"),
                ("💰 수익이 나아질까요", "수익"),
            ],
        },
    },
    "인간관계": {
        "가족": {
            "question": "...가족과의 관계군요. 뭐가 궁금해요?",
            "options": [
                ("😤 갈등을 해결하고 싶어요", "갈등"),
                ("💕 관계를 더 좋게 만들고 싶어요", "개선"),
                ("🤔 가족의 마음이 궁금해요", "마음"),
            ],
        },
        "친구": {
            "question": "...친구와의 사이가 마음에 걸리나요?",
            "options": [
                ("😤 갈등이 있어요", "갈등"),
                ("😟 거리감이 느껴져요", "거리감"),
                ("🤔 친구의 마음이 궁금해요", "마음"),
            ],
        },
        "직장": {
            "question": "...직장에서의 관계군요.",
            "options": [
                ("😤 상사/동료와 갈등이 있어요", "갈등"),
                ("🤝 어떻게 잘 지낼 수 있을까요", "개선"),
                ("🙄 그 사람이 나를 어떻게 볼까요", "시선"),
            ],
        },
        "전반": {
            "question": "...전반적인 인간관계군요.",
            "options": [
                ("🌐 대인관계 전체 흐름이 궁금해요", "전체흐름"),
                ("🤝 새로운 인연이 올까요", "새인연"),
                ("😔 외로움/고립감이 있어요", "외로움"),
            ],
        },
    },
}


# ── 주제 + 시간범위 통합 키보드 ──

def _topic_keyboard(user_id: int, selected_time: str = DEFAULT_TIME_RANGE) -> InlineKeyboardMarkup:
    rows = [
        # 기간 선택 (먼저)
        [
            InlineKeyboardButton(
                f"{'✓ ' if k == selected_time else ''}{v['label']}",
                callback_data=f"tarot_time_{user_id}_{k}",
            )
            for k, v in TIME_RANGES.items()
        ],
        # 주제 선택
        [
            InlineKeyboardButton("💕 연애", callback_data=f"tarot_topic_{user_id}_연애"),
            InlineKeyboardButton("💼 직장", callback_data=f"tarot_topic_{user_id}_직장"),
        ],
        [
            InlineKeyboardButton("💰 재물", callback_data=f"tarot_topic_{user_id}_재물"),
            InlineKeyboardButton("📈 투자", callback_data=f"tarot_topic_{user_id}_투자"),
        ],
        [
            InlineKeyboardButton("🤝 인간관계", callback_data=f"tarot_topic_{user_id}_인간관계"),
            InlineKeyboardButton("🌟 종합", callback_data=f"tarot_topic_{user_id}_종합"),
        ],
    ]
    return InlineKeyboardMarkup(rows)


# ── DM: "타로" 명령 ──

async def tarot_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """DM에서 '타로' 입력 시 — 생년월일 없으면 입력 유도, 있으면 주제 선택."""
    user_id = update.effective_user.id

    # 하루 1회 제한 체크
    today = __import__("config").get_kst_now().date()
    last_reading = context.user_data.get("last_tarot_date")
    if last_reading == today.isoformat():
        await update.message.reply_text(
            "🔮 오늘은 이미 리딩을 받았어요.\n"
            "...카드는 하루에 한 번만 답해줘요.\n"
            "내일 다시 와줄래요? 기다리고 있을게.",
            parse_mode="HTML",
        )
        return

    # 생년월일 확인
    birth_date = await _get_birth_date(user_id)

    if birth_date is None:
        # 생년월일 미등록 — 입력 유도
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("📝 생년월일 입력", callback_data=f"tarot_birth_{user_id}")],
            [InlineKeyboardButton("⏭️ 건너뛰기", callback_data=f"tarot_skip_{user_id}")],
        ])
        await update.message.reply_text(
            "🔮 <b>신비로운 피카의 타로</b>\n\n"
            "...어서 와요. 처음이네요.\n"
            "생년월일을 알려주면 별자리도 함께 봐줄 수 있어요.\n\n"
            "<i>한 번 등록하면 다음부터는 묻지 않아요.</i>",
            parse_mode="HTML",
            reply_markup=buttons,
        )
        return

    # 주제 선택
    await _show_topic_menu(update.message, user_id)


async def _show_topic_menu(target, user_id: int, selected_time: str = DEFAULT_TIME_RANGE):
    """주제 선택 메뉴 전송. target = message or query."""
    text = (
        "🔮 <b>신비로운 피카의 타로</b>\n\n"
        "...어서 와요. 기다리고 있었어요.\n"
        "아래에서 기간을 고르고, 관심 주제를 선택해줘요.\n"
    )
    kb = _topic_keyboard(user_id, selected_time)
    if hasattr(target, "edit_message_text"):
        await target.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
    else:
        await target.reply_text(text, parse_mode="HTML", reply_markup=kb)


# ── 생년월일 입력 콜백 ──

async def tarot_birth_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """'생년월일 입력' 버튼 → 텍스트 입력 대기."""
    query = update.callback_query
    await query.answer()

    data = query.data  # tarot_birth_{user_id}
    user_id = int(data.split("_")[2])
    if query.from_user.id != user_id:
        await query.answer("다른 사람의 타로예요!", show_alert=True)
        return

    context.user_data["tarot_birth_waiting"] = True

    await query.edit_message_text(
        "🔮 생년월일을 입력해주세요.\n\n"
        "예시: <code>1995-03-15</code> 또는 <code>19950315</code>\n\n"
        "<i>'취소'를 입력하면 돌아가요.</i>",
        parse_mode="HTML",
    )


async def tarot_birth_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """생년월일 텍스트 입력 처리 (group=-4에서 호출)."""
    if not context.user_data.get("tarot_birth_waiting"):
        return  # 대기 상태가 아니면 무시

    text = update.message.text.strip()
    user_id = update.effective_user.id

    # 취소
    if text in ("취소", "cancel"):
        context.user_data.pop("tarot_birth_waiting", None)
        await _show_topic_menu(update.message, user_id)
        return

    # 파싱
    birth_date = _parse_birth_date(text)
    if birth_date is None:
        await update.message.reply_text(
            "❌ 형식이 맞지 않아요.\n"
            "예시: <code>1995-03-15</code> 또는 <code>19950315</code>",
            parse_mode="HTML",
        )
        return

    # 유효성 검사
    today = __import__("config").get_kst_now().date()
    if birth_date > today:
        await update.message.reply_text("❌ 미래 날짜는 입력할 수 없어요.")
        return
    if birth_date.year < 1920:
        await update.message.reply_text("❌ 1920년 이전 날짜는 입력할 수 없어요.")
        return

    # DB 저장
    try:
        from database.connection import get_db
        pool = await get_db()
        await pool.execute(
            "UPDATE users SET birth_date = $1 WHERE user_id = $2",
            birth_date, user_id,
        )
    except Exception as e:
        _log.warning(f"Failed to save birth_date: {e}")

    context.user_data.pop("tarot_birth_waiting", None)

    zodiac = get_zodiac(birth_date)
    await update.message.reply_text(
        f"✅ 생년월일이 등록되었어요!\n"
        f"{zodiac} — 기억해둘게요.\n",
        parse_mode="HTML",
    )

    # 주제 선택으로 이동
    await _show_topic_menu(update.message, user_id)


async def tarot_skip_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """'건너뛰기' → 별자리 없이 주제 선택으로."""
    query = update.callback_query
    await query.answer()

    user_id = int(query.data.split("_")[2])
    if query.from_user.id != user_id:
        await query.answer("다른 사람의 타로예요!", show_alert=True)
        return

    context.user_data.pop("tarot_birth_waiting", None)
    await _show_topic_menu(query, user_id)


# ── 시간 범위 변경 콜백 ──

async def tarot_time_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """시간 범위 버튼 클릭 → 선택 상태만 업데이트."""
    query = update.callback_query

    data = query.data  # tarot_time_{user_id}_{time_range}
    parts = data.split("_", 3)
    if len(parts) < 4:
        return

    user_id = int(parts[2])
    time_range = parts[3]

    if query.from_user.id != user_id:
        await query.answer("다른 사람의 타로예요!", show_alert=True)
        return

    context.user_data["tarot_time_range"] = time_range
    await query.answer(f"{TIME_RANGES[time_range]['label']} 선택됨")
    await _show_topic_menu(query, user_id, selected_time=time_range)


# ── 주제 선택 콜백 ──

async def tarot_topic_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """주제 선택 → 성별(미등록 시) → 상황 질문 → 카드 뽑기."""
    query = update.callback_query
    await query.answer()

    data = query.data  # tarot_topic_{user_id}_{topic}
    parts = data.split("_")
    if len(parts) < 4:
        return

    user_id = int(parts[2])
    topic = parts[3]

    if query.from_user.id != user_id:
        await query.answer("다른 사람의 타로예요!", show_alert=True)
        return

    # topic 저장 (세부 질문 콜백에서 필요)
    context.user_data["tarot_topic"] = topic

    # 성별 확인 — 미등록이면 먼저 물어보기
    gender = await _get_gender(user_id)
    if gender is None:
        buttons = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🙋‍♂️ 남성", callback_data=f"tarot_gender_{user_id}_M"),
                InlineKeyboardButton("🙋‍♀️ 여성", callback_data=f"tarot_gender_{user_id}_F"),
            ],
        ])
        await query.edit_message_text(
            "🔮 잠깐, 하나만 물어볼게요.\n\n"
            "...성별을 알려주면 카드가 더 정확하게 말해줄 수 있어요.\n\n"
            "<i>한 번 등록하면 다음부터는 묻지 않아요.</i>",
            parse_mode="HTML",
            reply_markup=buttons,
        )
        return

    # 성별 있음 → 상황 질문으로
    await _show_context_question(query, user_id, topic)


async def tarot_gender_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """성별 선택 → DB 저장 → 상황 질문으로."""
    query = update.callback_query
    await query.answer()

    data = query.data  # tarot_gender_{user_id}_{M|F}
    parts = data.split("_")
    if len(parts) < 4:
        return

    user_id = int(parts[2])
    gender = parts[3]  # "M" or "F"

    if query.from_user.id != user_id:
        await query.answer("다른 사람의 타로예요!", show_alert=True)
        return

    # DB 저장
    try:
        from database.connection import get_db
        pool = await get_db()
        await pool.execute(
            "UPDATE users SET gender = $1 WHERE user_id = $2",
            gender, user_id,
        )
    except Exception as e:
        _log.warning(f"Failed to save gender: {e}")

    topic = context.user_data.get("tarot_topic", "종합")
    await _show_context_question(query, user_id, topic)


async def _show_context_question(query, user_id: int, topic: str):
    """상황 질문 표시 (1단계)."""
    ctx_info = _TOPIC_CONTEXTS.get(topic)
    if ctx_info:
        buttons = [
            [InlineKeyboardButton(label, callback_data=f"tarot_ctx_{user_id}_{topic}_{value}")]
            for label, value in ctx_info["options"]
        ]
        await query.edit_message_text(
            f"🔮 {TOPIC_EMOJIS.get(topic, '🔮')} <b>{topic}</b> 리딩\n\n"
            f"{ctx_info['question']}\n",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return

    # 컨텍스트 없는 주제 (예외) — 도달하지 않지만 안전장치
    return


# ── 상황 선택 콜백 (1단계) ──

async def tarot_ctx_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """상황 선택 → 세부 질문(있으면) or 스프레드 선택 or 카드 뽑기."""
    query = update.callback_query
    await query.answer()

    data = query.data  # tarot_ctx_{user_id}_{topic}_{context_value}
    parts = data.split("_", 4)
    if len(parts) < 5:
        return

    user_id = int(parts[2])
    topic = parts[3]
    ctx_value = parts[4]

    if query.from_user.id != user_id:
        await query.answer("다른 사람의 타로예요!", show_alert=True)
        return

    # 상황 저장
    context.user_data["tarot_context"] = ctx_value

    # 세부 질문이 있으면 2단계로
    sub_info = _SUB_QUESTIONS.get(topic, {}).get(ctx_value)
    if sub_info:
        buttons = [
            [InlineKeyboardButton(label, callback_data=f"tarot_sub_{user_id}_{value}")]
            for label, value in sub_info["options"]
        ]
        await query.edit_message_text(
            f"🔮 {TOPIC_EMOJIS.get(topic, '🔮')} <b>{topic}</b> 리딩\n\n"
            f"{sub_info['question']}\n",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return

    # 세부 질문 없음 → 스프레드 선택 or 카드 뽑기
    await _proceed_to_spread_or_pick(query, context, user_id, topic)


# ── 세부 질문 콜백 (2단계) ──

async def tarot_sub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """세부 질문 선택 후 → 스프레드 선택 or 카드 뽑기."""
    query = update.callback_query
    await query.answer()

    data = query.data  # tarot_sub_{user_id}_{sub_value}
    parts = data.split("_", 3)
    if len(parts) < 4:
        return

    user_id = int(parts[2])
    sub_value = parts[3]

    if query.from_user.id != user_id:
        await query.answer("다른 사람의 타로예요!", show_alert=True)
        return

    # 기존 context에 세부 질문 추가 (콤마 구분)
    prev_ctx = context.user_data.get("tarot_context", "")
    context.user_data["tarot_context"] = f"{prev_ctx},{sub_value}"

    # topic은 user_data에서 복원 (세부 콜백에는 topic이 없으므로)
    topic = context.user_data.get("tarot_topic", "종합")
    await _proceed_to_spread_or_pick(query, context, user_id, topic)


async def _proceed_to_spread_or_pick(query, context, user_id: int, topic: str):
    """스프레드 선택(연애/투자) or 쓰리카드 직행."""
    if topic == "연애":
        buttons = [
            [InlineKeyboardButton("🃏 쓰리카드 (과거/현재/미래)", callback_data=f"tarot_read_{user_id}_{topic}_three_card")],
            [InlineKeyboardButton("💕 연애 스프레드 (5장)", callback_data=f"tarot_read_{user_id}_{topic}_love")],
        ]
        await query.edit_message_text(
            f"🔮 {TOPIC_EMOJIS.get(topic, '🔮')} <b>{topic}</b> 리딩\n\n"
            "...카드를 몇 장 펼쳐볼까요?\n",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return

    if topic == "투자":
        buttons = [
            [InlineKeyboardButton("🃏 쓰리카드 (과거/현재/미래)", callback_data=f"tarot_read_{user_id}_{topic}_three_card")],
            [InlineKeyboardButton("📊 투자 스프레드 (4장)", callback_data=f"tarot_read_{user_id}_{topic}_investment")],
        ]
        await query.edit_message_text(
            f"🔮 {TOPIC_EMOJIS.get(topic, '🔮')} <b>{topic}</b> 리딩\n\n"
            "...카드를 몇 장 펼쳐볼까요?\n",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return

    # 나머지 — 쓰리카드 직행
    await _start_card_picking(query, context, user_id, topic, "three_card")


# ── 스프레드 선택 콜백 (투자/연애 전용) ──

async def tarot_read_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """스프레드 선택 후 → 카드 뽑기 시작."""
    query = update.callback_query
    await query.answer()

    data = query.data  # tarot_read_{user_id}_{topic}_{spread}
    parts = data.split("_")
    if len(parts) < 5:
        return

    user_id = int(parts[2])
    topic = parts[3]
    spread_type = "_".join(parts[4:])

    if query.from_user.id != user_id:
        await query.answer("다른 사람의 타로예요!", show_alert=True)
        return

    await _start_card_picking(query, context, user_id, topic, spread_type)


# ── 공통: 집중 + 카드 뽑기 시작 ──

async def _start_card_picking(query, context, user_id: int, topic: str, spread_type: str):
    """집중 단계 → 엎어진 카드 펼치기 → 첫 번째 카드 선택 대기."""
    time_range = context.user_data.get("tarot_time_range", DEFAULT_TIME_RANGE)
    spread = SPREADS.get(spread_type, SPREADS["three_card"])
    need_count = spread["count"]

    # 리딩을 미리 생성 (결과는 이미 정해짐, 카드 선택은 의식)
    birth_date = await _get_birth_date(user_id)
    gender = await _get_gender(user_id)
    tarot_context = context.user_data.get("tarot_context")
    reading = await generate_reading(
        topic=topic,
        spread_type=spread_type,
        birth_date=birth_date,
        user_id=user_id,
        time_range=time_range,
        situation=tarot_context,
        gender=gender,
    )

    # user_data에 진행 상태 저장
    context.user_data["tarot_session"] = {
        "reading": reading,
        "need_count": need_count,
        "picked_count": 0,
        "picked_indices": [],  # 선택된 카드 위치
    }

    # 1단계: 집중 메시지
    await query.edit_message_text(
        "🔮\n\n"
        "...잠시 눈을 감고,\n"
        "마음속 질문에 집중하세요.\n\n"
        f"<i>{TOPIC_EMOJIS.get(topic, '🔮')} {topic} — {TIME_RANGES.get(time_range, {}).get('label', time_range)}</i>",
        parse_mode="HTML",
    )

    await asyncio.sleep(2)

    # 2단계: 엎어진 카드 펼치기 + 첫 번째 카드 선택 안내
    first_card = reading["cards"][0]
    pick_text = (
        f"🔮 <b>{first_card['position_emoji']} {first_card['position']}</b> 카드를 골라주세요.\n\n"
        f"<i>(1/{need_count})</i>"
    )
    kb = _build_facedown_keyboard(user_id, picked=[])

    if _CARD_SELECT_IMG.exists():
        await query.message.reply_photo(
            photo=_CARD_SELECT_IMG.read_bytes(),
            caption=pick_text,
            parse_mode="HTML",
            reply_markup=kb,
        )
    else:
        await query.message.reply_text(
            pick_text,
            parse_mode="HTML",
            reply_markup=kb,
        )


def _build_facedown_keyboard(user_id: int, picked: list[int]) -> InlineKeyboardMarkup:
    """엎어진 카드 7장 버튼. 이미 뽑은 건 ✦ 표시."""
    row = []
    for i in range(_FACEDOWN_COUNT):
        if i in picked:
            row.append(InlineKeyboardButton(_CARD_PICKED, callback_data=f"tarot_pick_{user_id}_x"))
        else:
            row.append(InlineKeyboardButton(_CARD_BACK, callback_data=f"tarot_pick_{user_id}_{i}"))
    return InlineKeyboardMarkup([row])


# ── 카드 선택 콜백 ──

async def tarot_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """유저가 엎어진 카드 탭 → 한 장 공개 → 다음 선택 or 종합 리딩."""
    query = update.callback_query

    data = query.data  # tarot_pick_{user_id}_{card_idx}
    parts = data.split("_")
    if len(parts) < 4:
        return

    user_id = int(parts[2])
    card_idx_str = parts[3]

    if query.from_user.id != user_id:
        await query.answer("다른 사람의 타로예요!", show_alert=True)
        return

    # 이미 뽑은 카드
    if card_idx_str == "x":
        await query.answer("이미 뽑은 자리예요!")
        return

    card_idx = int(card_idx_str)
    session = context.user_data.get("tarot_session")
    if not session:
        await query.answer("세션이 만료되었어요. '타로'를 다시 입력해주세요.", show_alert=True)
        return

    picked_count = session["picked_count"]
    need_count = session["need_count"]
    reading = session["reading"]
    picked_indices = session["picked_indices"]

    # 이미 다 뽑았으면 무시
    if picked_count >= need_count:
        await query.answer()
        return

    # 중복 선택 방지
    if card_idx in picked_indices:
        await query.answer("이미 뽑은 자리예요!")
        return

    picked_indices.append(card_idx)
    session["picked_count"] = picked_count + 1
    pick_num = picked_count + 1

    # 현재 공개할 카드 정보
    card = reading["cards"][picked_count]

    # 카드 이미지 찾기
    card_img_path = _find_card_image(card)

    # 공개 텍스트
    reveal_text = (
        f"{card['position_emoji']} <b>[{card['position']}]</b> {card['card_name']}\n\n"
        f"  {card['meaning']}"
    )

    await query.answer(f"{card['position_emoji']} {card['card_name']}")

    if pick_num < need_count:
        # 아직 더 뽑아야 함 — 카드 공개 + 다음 선택
        next_card = reading["cards"][pick_num]
        next_text = (
            f"\n\n━━━━━━━━━━━━━━\n\n"
            f"🔮 <b>{next_card['position_emoji']} {next_card['position']}</b> 카드를 골라주세요.\n\n"
            f"<i>({pick_num + 1}/{need_count})</i>"
        )
        kb = _build_facedown_keyboard(user_id, picked_indices)

        if card_img_path:
            try:
                await query.edit_message_reply_markup(reply_markup=None)
            except Exception:
                pass
            await query.message.reply_photo(
                photo=card_img_path.read_bytes(),
                caption=reveal_text + next_text,
                parse_mode="HTML",
                reply_markup=kb,
            )
        else:
            try:
                await query.edit_message_caption(
                    caption=reveal_text + next_text,
                    parse_mode="HTML",
                    reply_markup=kb,
                )
            except Exception:
                try:
                    await query.edit_message_text(
                        reveal_text + next_text,
                        parse_mode="HTML",
                        reply_markup=kb,
                    )
                except Exception:
                    pass
    else:
        # 마지막 카드 — 공개 후 종합 리딩
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass

        if card_img_path:
            await query.message.reply_photo(
                photo=card_img_path.read_bytes(),
                caption=reveal_text,
                parse_mode="HTML",
            )
        else:
            await query.message.reply_text(
                reveal_text,
                parse_mode="HTML",
            )

        await asyncio.sleep(1.5)
        await _send_reading_result(query, context, user_id, reading)

        # 세션 정리
        context.user_data.pop("tarot_session", None)


def _find_card_image(card: dict) -> Path | None:
    """카드 이미지 파일 경로 반환."""
    if card.get("card_type") == "major" and card.get("card_number", -1) >= 0:
        p = _TAROT_IMG_DIR / f"{card['card_number']}.jpg"
    elif card.get("card_name_short"):
        p = _TAROT_IMG_DIR / f"{card['card_name_short']}.jpg"
    else:
        return None
    return p if p.exists() else None


# ── 리딩 결과 전송 ──

async def _send_reading_result(query, context, user_id: int, reading: dict):
    """최종 리딩 결과 메시지 전송."""
    msg = format_reading_message(reading)

    # 오늘 리딩 기록 + 공유용 저장
    today = __import__("config").get_kst_now().date()
    context.user_data["last_tarot_date"] = today.isoformat()
    context.user_data["last_tarot_reading"] = reading

    # DB에 리딩 기록 (통계용 + 컨텍스트)
    topic = reading["topic"]
    spread_type = reading["spread"]["name"]
    time_range = reading.get("time_range", DEFAULT_TIME_RANGE)
    situation = context.user_data.get("tarot_context")
    gender = await _get_gender(user_id)
    try:
        from database.connection import get_db
        pool = await get_db()
        await pool.execute(
            """INSERT INTO tarot_readings
               (user_id, topic, spread_type, cards_json, reading_date, gender, situation, time_range)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
            user_id, topic, spread_type,
            __import__("json").dumps(
                [{"card": c["card_name_en"], "reversed": c["reversed"], "position": c["position"]}
                 for c in reading["cards"]],
                ensure_ascii=False,
            ),
            today, gender, situation, time_range,
        )
    except Exception as e:
        _log.warning(f"Failed to log tarot reading: {e}")

    # 결과 메시지 전송
    buttons = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔮 다른 주제로 보기", callback_data=f"tarot_again_{user_id}"),
    ]])

    await query.message.reply_text(
        msg,
        parse_mode="HTML",
        reply_markup=buttons,
    )


async def tarot_again_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """다시 보기 — 하루 1회 이미 사용했으면 안내."""
    query = update.callback_query
    await query.answer("오늘은 이미 리딩을 받았어요 🔮", show_alert=True)


# ── 그룹 공유 ──

def _format_share_message(reading: dict, display_name: str) -> str:
    """그룹 공유용 축약 메시지 — 카드 목록 + AI 서사(있으면)."""
    topic_emoji = reading["topic_emoji"]
    topic = reading["topic"]
    time_range = reading.get("time_range", "이번 주")
    time_label = TIME_RANGES.get(time_range, {}).get("label", f"📆 {time_range}")

    lines = [
        f"🔮 <b>{display_name}</b>님의 타로 리딩",
        f"{topic_emoji} <b>{topic}</b> | {time_label}",
        "",
    ]

    for c in reading["cards"]:
        lines.append(f"{c['position_emoji']} <b>[{c['position']}]</b> {c['card_name']}")

    lines.append("")
    lines.append("━━━━━━━━━━━━━━")

    ai_narrative = reading.get("ai_narrative")
    if ai_narrative:
        lines.append("")
        lines.append(f"🌙 <b>종합 해석</b>")
        lines.append("")
        lines.append(ai_narrative)
    else:
        lines.append(reading.get("summary", ""))

    lines.append(f"\n<i>🔮 DM에서 '타로'를 입력해 나만의 리딩을 받아보세요!</i>")
    return "\n".join(lines)


async def tarot_share_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """그룹 채팅에서 '타로공유' → 오늘 받은 리딩 공유."""
    reading = context.user_data.get("last_tarot_reading")

    if not reading:
        await update.message.reply_text(
            "🔮 아직 오늘 받은 리딩이 없어요.\n"
            "DM에서 '타로'를 입력해 먼저 리딩을 받아보세요!",
        )
        return

    # 오늘 리딩인지 확인
    today = __import__("config").get_kst_now().date()
    if reading.get("date") != today.isoformat():
        await update.message.reply_text(
            "🔮 오늘 받은 리딩이 없어요.\n"
            "DM에서 '타로'를 입력해 새 리딩을 받아보세요!",
        )
        return

    user = update.effective_user
    display_name = user.first_name or user.username or "트레이너"
    msg = _format_share_message(reading, display_name)

    await update.message.reply_text(msg, parse_mode="HTML")


# ── 헬퍼 ──

async def _get_birth_date(user_id: int) -> date | None:
    """DB에서 생년월일 조회."""
    try:
        from database.connection import get_db
        pool = await get_db()
        row = await pool.fetchrow(
            "SELECT birth_date FROM users WHERE user_id = $1", user_id
        )
        if row and row.get("birth_date"):
            bd = row["birth_date"]
            if isinstance(bd, datetime):
                bd = bd.date()
            return bd
    except Exception:
        pass
    return None


async def _get_gender(user_id: int) -> str | None:
    """DB에서 성별 조회. 'M' or 'F' or None."""
    try:
        from database.connection import get_db
        pool = await get_db()
        row = await pool.fetchrow(
            "SELECT gender FROM users WHERE user_id = $1", user_id
        )
        if row and row.get("gender"):
            return row["gender"]
    except Exception:
        pass
    return None


def _parse_birth_date(text: str) -> date | None:
    """다양한 형식의 생년월일 파싱."""
    text = text.replace("/", "-").replace(".", "-").strip()

    # 숫자만 8자리: 19950315
    digits = text.replace("-", "")
    if len(digits) == 8 and digits.isdigit():
        try:
            return date(int(digits[:4]), int(digits[4:6]), int(digits[6:8]))
        except ValueError:
            return None

    # YYYY-MM-DD
    parts = text.split("-")
    if len(parts) == 3:
        try:
            return date(int(parts[0]), int(parts[1]), int(parts[2]))
        except ValueError:
            return None

    return None


# ── DM 운세 핸들러 ──

_horoscope_dm_daily: dict[str, set] = {}  # {date_str: set(user_ids)}

async def horoscope_dm_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """DM '운세' 명령 → 상세 별자리 운세."""
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return

    today_str = str(__import__("config").get_kst_now().date())
    if today_str not in _horoscope_dm_daily:
        _horoscope_dm_daily.clear()
        _horoscope_dm_daily[today_str] = set()

    birth_date = await _get_birth_date(user.id)
    if not birth_date:
        await msg.reply_text(
            "🌟 운세를 보려면 생년월일 등록이 필요해요!\n"
            "<b>/타로</b> 를 입력하면 등록할 수 있어요.",
            parse_mode="HTML",
        )
        return

    from services.horoscope_service import get_daily_horoscope, format_horoscope_dm

    await msg.reply_text("🔮 별자리 운세를 계산하고 있어요...")

    data = await get_daily_horoscope(birth_date, user.first_name)
    if not data:
        await msg.reply_text("운세 생성에 실패했어요. 잠시 후 다시 시도해주세요.")
        return

    display_name = user.first_name or "트레이너"
    text = format_horoscope_dm(data, display_name)

    # 첫 운세 시 성격변경권 1개 지급
    if user.id not in _horoscope_dm_daily[today_str]:
        from database import item_queries
        await item_queries.add_user_item(user.id, "personality_ticket", 1)
        text += "\n\n🎭 <i>성격변경권 1개를 받았어요!</i>"
        _horoscope_dm_daily[today_str].add(user.id)

    await msg.reply_text(text, parse_mode="HTML")
