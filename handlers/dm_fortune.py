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
    """주제 선택 후 스프레드 선택."""
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

    # 투자/연애는 전용 스프레드 선택지 제공
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
    elif topic == "연애":
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

    # 나머지 주제 — 쓰리카드 직행
    await _start_card_picking(query, context, user_id, topic, "three_card")


# ── 공통: 집중 + 순차 카드 뽑기 시작 ──

async def _start_card_picking(query, context, user_id: int, topic: str, spread_type: str):
    """집중 단계 → 첫 번째 카드 뽑기 화면 전송."""
    time_range = context.user_data.get("tarot_time_range", DEFAULT_TIME_RANGE)
    spread = SPREADS.get(spread_type, SPREADS["three_card"])
    need_count = spread["count"]

    # 리딩을 미리 생성 (결과는 이미 정해짐, 카드 뽑기는 의식)
    birth_date = await _get_birth_date(user_id)
    reading = await generate_reading(
        topic=topic,
        spread_type=spread_type,
        birth_date=birth_date,
        user_id=user_id,
        time_range=time_range,
    )

    # user_data에 진행 상태 저장
    context.user_data["tarot_session"] = {
        "reading": reading,
        "need_count": need_count,
        "picked_count": 0,
    }

    # 1단계: 집중 메시지
    await query.edit_message_text(
        "🔮\n\n"
        "...잠시 눈을 감고,\n"
        "마음속 질문에 집중하세요.\n\n"
        f"<i>{TOPIC_EMOJIS.get(topic, '🔮')} {topic} — {TIME_RANGES.get(time_range, {}).get('label', time_range)}</i>",
        parse_mode="HTML",
    )

    # 2초 대기 후 카드 뽑기 화면
    await asyncio.sleep(2)

    # 2단계: 첫 번째 카드 뽑기
    first_card = reading["cards"][0]
    pick_text = (
        f"🔮 <b>{first_card['position_emoji']} {first_card['position']}</b> 카드를 뽑아주세요.\n\n"
        f"<i>(1/{need_count})</i>"
    )
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton(f"{_CARD_BACK} 카드 뽑기", callback_data=f"tarot_pick_{user_id}"),
    ]])

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


# ── 스프레드 선택 콜백 (투자/연애 전용) ──

async def tarot_read_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """투자/연애 스프레드 선택 후 → 카드 뽑기 시작."""
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


# ── 카드 뽑기 콜백 ──

async def tarot_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """유저가 '카드 뽑기' 탭 → 한 장 공개 → 다음 카드 or 종합 리딩."""
    query = update.callback_query

    data = query.data  # tarot_pick_{user_id}
    parts = data.split("_")
    if len(parts) < 3:
        return

    user_id = int(parts[2])
    if query.from_user.id != user_id:
        await query.answer("다른 사람의 타로예요!", show_alert=True)
        return

    session = context.user_data.get("tarot_session")
    if not session:
        await query.answer("세션이 만료되었어요. '타로'를 다시 입력해주세요.", show_alert=True)
        return

    picked_count = session["picked_count"]
    need_count = session["need_count"]
    reading = session["reading"]

    # 이미 다 뽑았으면 무시
    if picked_count >= need_count:
        await query.answer()
        return

    # 현재 카드 공개
    card = reading["cards"][picked_count]
    session["picked_count"] = picked_count + 1
    pick_num = picked_count + 1

    # 카드 이미지 찾기
    card_img_path = None
    if card.get("card_type") == "major" and card.get("card_number", -1) >= 0:
        card_img_path = _TAROT_IMG_DIR / f"{card['card_number']}.jpg"
    elif card.get("card_name_short"):
        card_img_path = _TAROT_IMG_DIR / f"{card['card_name_short']}.jpg"
    if card_img_path and not card_img_path.exists():
        card_img_path = None

    # 공개 텍스트
    reveal_text = (
        f"{card['position_emoji']} <b>[{card['position']}]</b> {card['card_name']}\n\n"
        f"  {card['meaning']}"
    )

    await query.answer(f"{card['position_emoji']} {card['card_name']}")

    if pick_num < need_count:
        # 아직 더 뽑아야 함 — 카드 공개 + 다음 카드 뽑기 버튼
        next_card = reading["cards"][pick_num]
        next_text = (
            f"\n\n━━━━━━━━━━━━━━\n\n"
            f"🔮 <b>{next_card['position_emoji']} {next_card['position']}</b> 카드를 뽑아주세요.\n\n"
            f"<i>({pick_num + 1}/{need_count})</i>"
        )
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton(f"{_CARD_BACK} 카드 뽑기", callback_data=f"tarot_pick_{user_id}"),
        ]])

        # 카드 이미지와 함께 공개
        if card_img_path:
            # 이전 메시지 캡션/버튼 정리
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
        # 이전 메시지 정리
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass

        # 마지막 카드 이미지 공개
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

        # 대기 후 종합 리딩
        await asyncio.sleep(1.5)
        await _send_reading_result(query, context, user_id, reading)

        # 세션 정리
        context.user_data.pop("tarot_session", None)


# ── 리딩 결과 전송 ──

async def _send_reading_result(query, context, user_id: int, reading: dict):
    """최종 리딩 결과 메시지 + 카드 이미지 전송."""
    msg = format_reading_message(reading)

    # 오늘 리딩 기록 + 공유용 저장
    today = __import__("config").get_kst_now().date()
    context.user_data["last_tarot_date"] = today.isoformat()
    context.user_data["last_tarot_reading"] = reading

    # DB에 리딩 기록 (통계용)
    topic = reading["topic"]
    spread_type = reading["spread"]["name"]
    try:
        from database.connection import get_db
        pool = await get_db()
        await pool.execute(
            """INSERT INTO tarot_readings (user_id, topic, spread_type, cards_json, reading_date)
               VALUES ($1, $2, $3, $4, $5)""",
            user_id, topic, spread_type,
            __import__("json").dumps(
                [{"card": c["card_name_en"], "reversed": c["reversed"], "position": c["position"]}
                 for c in reading["cards"]],
                ensure_ascii=False,
            ),
            today,
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

    # 카드 이미지 전송
    try:
        media = []
        for c in reading["cards"]:
            if c.get("card_type") == "major" and c.get("card_number", -1) >= 0:
                img_path = _TAROT_IMG_DIR / f"{c['card_number']}.jpg"
            elif c.get("card_name_short"):
                img_path = _TAROT_IMG_DIR / f"{c['card_name_short']}.jpg"
            else:
                continue
            if img_path.exists():
                media.append(InputMediaPhoto(
                    media=img_path.read_bytes(),
                    caption=f"🔮 {c['card_name']}",
                ))
        if len(media) == 1:
            await query.message.reply_photo(
                photo=media[0].media,
                caption=media[0].caption,
            )
        elif media:
            await query.message.reply_media_group(media=media)
    except Exception as e:
        _log.warning(f"Failed to send tarot card images: {e}")


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
