"""매일 이벤트 — 포켓몬 퀴즈 서비스.

5문제 × 30초, 문제당 선착순 5명 IV선택리롤, 일괄 정산.
"""

from __future__ import annotations

import asyncio
import io
import logging
import random
import time
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import config
from database import event_queries as eq
from database import item_queries as iq
from database import queries

_log = logging.getLogger(__name__)

# ── 에셋 경로 ──

ASSETS_DIR = Path(__file__).parent.parent / "assets" / "pokemon"

_FONT_PATHS = [
    "C:/Windows/Fonts/NotoSansKR-VF.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "C:/Windows/Fonts/malgun.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
]
_FONT_BOLD_PATHS = [
    "C:/Windows/Fonts/NotoSansKR-VF.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "C:/Windows/Fonts/malgunbd.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
]


def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    paths = _FONT_BOLD_PATHS if bold else _FONT_PATHS
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


# ── 1세대 포켓몬 데이터 ──

_gen1_cache: list[tuple] | None = None


def _get_gen1() -> list[tuple]:
    global _gen1_cache
    if _gen1_cache is None:
        from models.pokemon_data import ALL_POKEMON
        _gen1_cache = [p for p in ALL_POKEMON if 1 <= p[0] <= 151]
    return _gen1_cache


# ── 퀴즈 문제 생성 ──

def generate_quiz_questions(count: int = 5) -> list[dict]:
    """1세대 포켓몬 중 랜덤 count종 선택하여 퀴즈 문제 생성."""
    gen1 = _get_gen1()
    chosen = random.sample(gen1, min(count, len(gen1)))
    questions = []
    for p in chosen:
        pokemon_id, name_ko, name_en, emoji, rarity, *_ = p
        questions.append({
            "pokemon_id": pokemon_id,
            "name_ko": name_ko,
            "name_en": name_en,
            "emoji": emoji,
            "rarity": rarity,
        })
    return questions


# ── 실루엣 이미지 생성 ──

IMG_WIDTH = 600
IMG_HEIGHT = 600
BG_COLOR = (13, 17, 23)          # #0d1117
SILHOUETTE_COLOR = (30, 30, 50)  # 약간 밝은 검정


def generate_silhouette_image(pokemon_id: int, question_num: int, total: int) -> io.BytesIO:
    """포켓몬 실루엣 이미지 → BytesIO (JPEG)."""
    img = Image.new("RGBA", (IMG_WIDTH, IMG_HEIGHT), BG_COLOR + (255,))
    draw = ImageDraw.Draw(img)

    # 포켓몬 스프라이트 로드
    sprite_path = ASSETS_DIR / f"{pokemon_id}.png"
    if sprite_path.exists():
        sprite = Image.open(sprite_path).convert("RGBA")
        # 크기 조절 (최대 400px)
        max_size = 400
        ratio = min(max_size / sprite.width, max_size / sprite.height)
        new_size = (int(sprite.width * ratio), int(sprite.height * ratio))
        sprite = sprite.resize(new_size, Image.LANCZOS)

        # 실루엣 변환: 알파 > 30인 픽셀 → 검정
        silhouette = Image.new("RGBA", sprite.size, (0, 0, 0, 0))
        pixels = sprite.load()
        sil_pixels = silhouette.load()
        for y in range(sprite.height):
            for x in range(sprite.width):
                _, _, _, a = pixels[x, y]
                if a > 30:
                    sil_pixels[x, y] = SILHOUETTE_COLOR + (255,)

        # 중앙 배치
        offset_x = (IMG_WIDTH - sprite.width) // 2
        offset_y = (IMG_HEIGHT - sprite.height) // 2 + 20
        img.paste(silhouette, (offset_x, offset_y), silhouette)

    # 상단: "Q{n}/5"
    font_q = _get_font(36, bold=True)
    q_text = f"Q{question_num}/{total}"
    bbox = draw.textbbox((0, 0), q_text, font=font_q)
    tw = bbox[2] - bbox[0]
    draw.text(((IMG_WIDTH - tw) // 2, 15), q_text, fill=(88, 166, 255), font=font_q)

    # 하단: "이 포켓몬은 누~구일까요?"
    font_title = _get_font(28, bold=True)
    title = "이 포켓몬은 누~구일까요?"
    bbox2 = draw.textbbox((0, 0), title, font=font_title)
    tw2 = bbox2[2] - bbox2[0]
    draw.text(((IMG_WIDTH - tw2) // 2, IMG_HEIGHT - 60), title, fill=(230, 237, 243), font=font_title)

    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=85)
    buf.seek(0)
    return buf


def generate_reveal_image(pokemon_id: int, name_ko: str, question_num: int, total: int) -> io.BytesIO:
    """정답 공개 이미지 (컬러) → BytesIO (JPEG)."""
    img = Image.new("RGBA", (IMG_WIDTH, IMG_HEIGHT), BG_COLOR + (255,))
    draw = ImageDraw.Draw(img)

    sprite_path = ASSETS_DIR / f"{pokemon_id}.png"
    if sprite_path.exists():
        sprite = Image.open(sprite_path).convert("RGBA")
        max_size = 400
        ratio = min(max_size / sprite.width, max_size / sprite.height)
        new_size = (int(sprite.width * ratio), int(sprite.height * ratio))
        sprite = sprite.resize(new_size, Image.LANCZOS)
        offset_x = (IMG_WIDTH - sprite.width) // 2
        offset_y = (IMG_HEIGHT - sprite.height) // 2 + 20
        img.paste(sprite, (offset_x, offset_y), sprite)

    # 상단: "Q{n}/5 정답!"
    font_q = _get_font(36, bold=True)
    q_text = f"Q{question_num}/{total} 정답!"
    bbox = draw.textbbox((0, 0), q_text, font=font_q)
    tw = bbox[2] - bbox[0]
    draw.text(((IMG_WIDTH - tw) // 2, 15), q_text, fill=(63, 185, 80), font=font_q)

    # 하단: 포켓몬 이름
    font_name = _get_font(40, bold=True)
    bbox2 = draw.textbbox((0, 0), name_ko, font=font_name)
    tw2 = bbox2[2] - bbox2[0]
    draw.text(((IMG_WIDTH - tw2) // 2, IMG_HEIGHT - 65), name_ko, fill=(255, 255, 255), font=font_name)

    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=85)
    buf.seek(0)
    return buf


# ── 퀴즈 상태 머신 ──

@dataclass
class QuizState:
    event_id: int
    chat_id: int
    questions: list[dict]
    current_q: int = 0                          # 0-indexed
    answers: dict[int, list[tuple]] = field(default_factory=dict)  # {q_num: [(user_id, rank)]}
    answer_count: int = 0                       # 현재 문제 정답자 수
    total_participants: set[int] = field(default_factory=set)
    question_started_at: float = 0.0
    is_accepting: bool = False
    test_mode: bool = False
    _ending: bool = False  # _end_question 재진입 방지


def _roll_reward(table: list[tuple]) -> tuple[str, int, str]:
    """랜덤 보상 상자 — (item_name, amount, label) 반환."""
    roll = random.random()
    cumulative = 0.0
    for prob, item_name, amount, label in table:
        cumulative += prob
        if roll < cumulative:
            return item_name, amount, label
    # fallback: 마지막 항목
    return table[-1][1], table[-1][2], table[-1][3]


# 채팅방별 활성 퀴즈 (메모리)
_active_quizzes: dict[int, QuizState] = {}

# 오답 쿨다운: {(chat_id, user_id): timestamp}
_wrong_answer_cooldowns: dict[tuple[int, int], float] = {}


def get_active_quiz(chat_id: int) -> QuizState | None:
    return _active_quizzes.get(chat_id)


async def start_quiz(context, chat_id: int, *, test_mode: bool = False) -> bool:
    """퀴즈 시작. test_mode=True면 보상 없이 진행."""
    if chat_id in _active_quizzes:
        _log.warning(f"Quiz already active in {chat_id}")
        return False

    questions = generate_quiz_questions(config.QUIZ_QUESTION_COUNT)
    quiz_data = [{"pokemon_id": q["pokemon_id"], "name_ko": q["name_ko"]} for q in questions]

    kst_today = config.get_kst_now().date()
    event_id = await eq.create_daily_event(kst_today, chat_id, quiz_data)
    await eq.update_event_status(event_id, "active")

    state = QuizState(
        event_id=event_id,
        chat_id=chat_id,
        questions=questions,
        test_mode=test_mode,
    )
    _active_quizzes[chat_id] = state

    _log.info(f"Quiz started: event_id={event_id}, chat_id={chat_id}")

    # 첫 문제 시작
    await _send_question(context, state)
    return True


async def _send_question(context, state: QuizState):
    """현재 문제 실루엣 이미지 전송 + 타이머."""
    q = state.questions[state.current_q]
    q_num = state.current_q + 1
    total = len(state.questions)

    # 실루엣 이미지 (blocking → executor)
    loop = asyncio.get_event_loop()
    buf = await loop.run_in_executor(
        None, generate_silhouette_image, q["pokemon_id"], q_num, total,
    )

    state.answer_count = 0
    state.answers[q_num] = []
    state.question_started_at = time.time()
    state.is_accepting = True
    state._ending = False  # 다음 문제 시작 시 리셋

    await context.bot.send_photo(
        chat_id=state.chat_id,
        photo=buf,
        caption=(
            f"🧠 <b>Q{q_num}/{total}</b> — 이 포켓몬은 누~구일까요?\n"
            f"⏰ {config.QUIZ_TIME_PER_QUESTION}초! (선착순 {config.QUIZ_MAX_WINNERS_PER_Q}명)\n"
            f"💡 <code>ㄷ 포켓몬이름</code> 으로 정답 제출!"
        ),
        parse_mode="HTML",
    )

    # 타임아웃 스케줄
    context.job_queue.run_once(
        _question_timeout,
        when=config.QUIZ_TIME_PER_QUESTION,
        data={"chat_id": state.chat_id, "q_num": q_num, "event_id": state.event_id},
        name=f"quiz_timeout_{state.chat_id}_{q_num}",
    )


async def handle_answer(context, chat_id: int, user_id: int, text: str, display_name: str) -> bool:
    """유저 정답 시도 처리. 정답이면 True."""
    state = _active_quizzes.get(chat_id)
    if not state or not state.is_accepting:
        return False

    q = state.questions[state.current_q]
    q_num = state.current_q + 1

    # "ㄷ" 접두사 체크
    stripped = text.strip()
    if not stripped.startswith("ㄷ ") and not stripped.startswith("ㄷ"):
        return False
    answer = stripped[1:].strip()
    if not answer:
        return False

    # 오답 쿨다운 체크 (3초)
    cooldown_key = (chat_id, user_id)
    now = time.time()
    if cooldown_key in _wrong_answer_cooldowns:
        if now - _wrong_answer_cooldowns[cooldown_key] < 3.0:
            return False  # 쿨다운 중 → 무시

    # 정답 체크
    if answer != q["name_ko"]:
        _wrong_answer_cooldowns[cooldown_key] = now
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"❌ <b>{display_name}</b> 오답! (3초 제한)",
            parse_mode="HTML",
        )
        return False

    # 이미 이 문제 맞춘 유저인지 확인
    for uid, _ in state.answers.get(q_num, []):
        if uid == user_id:
            return False

    state.answer_count += 1
    rank = state.answer_count
    state.answers[q_num].append((user_id, rank))
    state.total_participants.add(user_id)

    # DB 기록
    await eq.record_quiz_answer(state.event_id, user_id, q_num, rank)

    # 응답 메시지 (채팅방에는 등수만, 상세 보상은 DM)
    rank_emojis = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    if rank <= 5:
        rank_emoji = rank_emojis[rank - 1]
    elif rank <= 10:
        rank_emoji = f"{rank}등"
    else:
        rank_emoji = f"{rank}등"
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"✅ {rank_emoji} <b>{display_name}</b> 정답!",
        parse_mode="HTML",
    )

    # 5명 마감 → 다음 문제
    if rank >= config.QUIZ_MAX_WINNERS_PER_Q:
        state.is_accepting = False
        # 기존 타임아웃 취소
        jobs = context.job_queue.get_jobs_by_name(f"quiz_timeout_{chat_id}_{q_num}")
        for j in jobs:
            j.schedule_removal()
        await _end_question(context, state)

    return True


async def _question_timeout(context):
    """30초 타임아웃 → 문제 종료."""
    data = context.job.data
    chat_id = data["chat_id"]
    state = _active_quizzes.get(chat_id)
    if not state:
        return
    q_num = data["q_num"]
    if state.current_q + 1 != q_num:
        return
    if not state.is_accepting:
        return
    state.is_accepting = False
    await _end_question(context, state)


async def _end_question(context, state: QuizState):
    """문제 종료 → 정답 공개 → 다음 문제 or 최종 정산."""
    # 레이스컨디션 방지: timeout + 5th winner 동시 호출 시 한 번만 실행
    if state._ending:
        return
    state._ending = True
    q = state.questions[state.current_q]
    q_num = state.current_q + 1
    total = len(state.questions)

    # 정답 공개 이미지
    loop = asyncio.get_event_loop()
    buf = await loop.run_in_executor(
        None, generate_reveal_image, q["pokemon_id"], q["name_ko"], q_num, total,
    )

    answer_count = len(state.answers.get(q_num, []))
    await context.bot.send_photo(
        chat_id=state.chat_id,
        photo=buf,
        caption=f"정답: <b>{q['name_ko']}</b>! ({answer_count}명 정답)",
        parse_mode="HTML",
    )

    # 다음 문제 or 최종 정산
    state.current_q += 1
    if state.current_q < total:
        await asyncio.sleep(config.QUIZ_BETWEEN_QUESTIONS_DELAY)
        await _send_question(context, state)
    else:
        await asyncio.sleep(2)
        await _finalize_quiz(context, state)


async def _finalize_quiz(context, state: QuizState):
    """최종 정산 — 보상 지급 + 결과 메시지."""
    chat_id = state.chat_id
    event_id = state.event_id

    # 활성 상태 제거
    _active_quizzes.pop(chat_id, None)
    await eq.update_event_status(event_id, "ended")

    # 결과 집계
    results = await eq.get_event_results(event_id)
    all_participant_ids = state.total_participants.copy()
    rewarded_uids: set[int] = set()

    # 보상 계산 + 지급
    reward_lines = []
    # {uid: {"items": [(name, amount)], "bp": int}}
    user_rewards: dict[int, dict] = {}

    for r in results:
        uid = r["user_id"]
        rewarded_uids.add(uid)
        user_rewards[uid] = {"items": [], "bp": 0, "correct": r["correct_count"]}

        # 각 문제별 보상 계산
        for q_num, ans_list in state.answers.items():
            for a_uid, a_rank in ans_list:
                if a_uid != uid:
                    continue
                if a_rank == 1:
                    # 1등: 랜덤 상자 + 500BP
                    item_name, amount, label = _roll_reward(config.QUIZ_REWARD_RANK1)
                    user_rewards[uid]["items"].append((item_name, amount, label))
                    user_rewards[uid]["bp"] += config.QUIZ_REWARD_TOP5_BP
                elif a_rank <= 3:
                    # 2~3등
                    item_name, amount, label = _roll_reward(config.QUIZ_REWARD_RANK2_3)
                    user_rewards[uid]["items"].append((item_name, amount, label))
                    user_rewards[uid]["bp"] += config.QUIZ_REWARD_TOP5_BP
                elif a_rank <= 5:
                    # 4~5등
                    item_name, amount, label = _roll_reward(config.QUIZ_REWARD_RANK4_5)
                    user_rewards[uid]["items"].append((item_name, amount, label))
                    user_rewards[uid]["bp"] += config.QUIZ_REWARD_TOP5_BP
                elif a_rank <= 10:
                    # 6~10등
                    user_rewards[uid]["bp"] += config.QUIZ_REWARD_RANK6_10_BP
                else:
                    # 11등+
                    user_rewards[uid]["bp"] += config.QUIZ_REWARD_RANK11_BP

    # 지급 (test_mode면 스킵)
    for uid, rew in user_rewards.items():
        if not state.test_mode:
            # 아이템 지급
            item_totals: dict[str, int] = {}
            for item_name, amount, _ in rew["items"]:
                item_totals[item_name] = item_totals.get(item_name, 0) + amount
            for item_name, total in item_totals.items():
                if item_name == "iv_stone":
                    await iq.add_iv_stones(uid, total)
                elif item_name == "shiny_spawn_ticket":
                    await iq.add_shiny_spawn_ticket(uid, total)
                else:
                    await iq.add_user_item(uid, item_name, total)
            # BP 지급
            if rew["bp"] > 0:
                await queries.add_battle_points(uid, rew["bp"])

        user = await queries.get_user(uid)
        name = user["display_name"] if user else str(uid)
        correct = rew["correct"]
        reward_lines.append(f"  {name} — {correct}/{len(state.questions)}")

    # 정답 0문제인 참가자에게도 참가 보상
    for uid in all_participant_ids:
        if uid not in rewarded_uids:
            if not state.test_mode:
                await queries.add_battle_points(uid, config.QUIZ_REWARD_PARTICIPATION_BP)
            user_rewards[uid] = {"items": [], "bp": config.QUIZ_REWARD_PARTICIPATION_BP, "correct": 0}

    # 결과 메시지
    total_q = len(state.questions)
    test_label = " [테스트]" if state.test_mode else ""
    msg = f"🏆 <b>퀴즈 종료!{test_label}</b> ({total_q}문제)\n\n"

    if reward_lines:
        msg += "\n".join(reward_lines[:15])
        if len(reward_lines) > 15:
            msg += f"\n  ... 외 {len(reward_lines) - 15}명"
    else:
        msg += "정답자 없음!"

    msg += f"\n\n👥 참가자 {len(all_participant_ids)}명 전원 참가보상 {config.QUIZ_REWARD_PARTICIPATION_BP:,} BP"

    await context.bot.send_message(
        chat_id=chat_id,
        text=msg,
        parse_mode="HTML",
    )

    # 개인 DM 보상 알림
    if not state.test_mode:
        asyncio.create_task(_send_reward_dms(context, state, user_rewards))

    _log.info(f"Quiz finalized: event_id={event_id}, participants={len(all_participant_ids)}")


async def _send_reward_dms(context, state: QuizState, user_rewards: dict[int, dict]):
    """개인별 보상 DM 발송."""
    total_q = len(state.questions)

    for uid, rew in user_rewards.items():
        correct = rew["correct"]
        items = rew["items"]  # [(item_name, amount, label), ...]
        bp = rew["bp"]

        lines = [f"🧠 <b>퀴즈 결과: {correct}/{total_q} 정답!</b>\n"]

        if items:
            lines.append("🎁 <b>보상:</b>")
            for _, _, label in items:
                lines.append(f"  • {label}")

        if bp > 0:
            lines.append(f"💰 {bp:,} BP")

        try:
            await context.bot.send_message(
                chat_id=uid, text="\n".join(lines), parse_mode="HTML",
            )
        except Exception:
            pass
