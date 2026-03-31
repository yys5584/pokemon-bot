"""매일 이벤트 — 포켓몬 퀴즈 서비스.

5문제 × 30초, 누구나 정답 제출 가능, 등수별 차등 보상.
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


def _get_opaque_bbox(sprite: Image.Image) -> tuple[int, int, int, int]:
    """불투명 픽셀(alpha>30) 영역의 바운딩 박스 반환."""
    pixels = sprite.load()
    min_x, min_y = sprite.width, sprite.height
    max_x, max_y = 0, 0
    for y in range(sprite.height):
        for x in range(sprite.width):
            if pixels[x, y][3] > 30:
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)
    return (min_x, min_y, max_x, max_y)


def generate_zoom_hint_image(
    pokemon_id: int, question_num: int, total: int, hint_level: int,
) -> io.BytesIO:
    """단계별 줌 힌트 이미지 생성.

    hint_level: 1=줌인 크롭(컬러), 2=중간 크롭(컬러), 3=전체 실루엣.
    """
    if hint_level >= 3:
        return generate_silhouette_image(pokemon_id, question_num, total)

    zoom_ratio = config.QUIZ_ZOOM_LEVELS[hint_level - 1]  # 0.3 or 0.55
    img = Image.new("RGBA", (IMG_WIDTH, IMG_HEIGHT), BG_COLOR + (255,))
    draw = ImageDraw.Draw(img)

    sprite_path = ASSETS_DIR / f"{pokemon_id}.png"
    if sprite_path.exists():
        sprite = Image.open(sprite_path).convert("RGBA")
        max_size = 400
        ratio = min(max_size / sprite.width, max_size / sprite.height)
        new_size = (int(sprite.width * ratio), int(sprite.height * ratio))
        sprite = sprite.resize(new_size, Image.LANCZOS)

        bbox = _get_opaque_bbox(sprite)
        bw = bbox[2] - bbox[0]
        bh = bbox[3] - bbox[1]

        if bw > 0 and bh > 0:
            crop_w = max(int(bw * zoom_ratio), 40)
            crop_h = max(int(bh * zoom_ratio), 40)

            # pokemon_id 기반 시드 → 같은 포켓몬은 같은 크롭 위치
            rng = random.Random(pokemon_id * 1000 + question_num)
            off_x = rng.randint(bbox[0], max(bbox[0], bbox[2] - crop_w))
            off_y = rng.randint(bbox[1], max(bbox[1], bbox[3] - crop_h))

            cropped = sprite.crop((off_x, off_y, off_x + crop_w, off_y + crop_h))

            # 화면에 꽉 차게 확대
            scale = min(380 / max(cropped.width, 1), 380 / max(cropped.height, 1))
            scaled_size = (int(cropped.width * scale), int(cropped.height * scale))
            cropped = cropped.resize(scaled_size, Image.LANCZOS)

            ox = (IMG_WIDTH - cropped.width) // 2
            oy = (IMG_HEIGHT - cropped.height) // 2 + 20
            img.paste(cropped, (ox, oy), cropped)

    # 상단: "Q{n}/5"
    font_q = _get_font(36, bold=True)
    q_text = f"Q{question_num}/{total}"
    bb = draw.textbbox((0, 0), q_text, font=font_q)
    tw = bb[2] - bb[0]
    draw.text(((IMG_WIDTH - tw) // 2, 15), q_text, fill=(88, 166, 255), font=font_q)

    # 하단: 힌트 단계 표시
    font_hint = _get_font(24, bold=True)
    hint_labels = {1: "🔍 힌트 1/3", 2: "🔍 힌트 2/3"}
    hint_text = hint_labels.get(hint_level, "")
    bb2 = draw.textbbox((0, 0), hint_text, font=font_hint)
    tw2 = bb2[2] - bb2[0]
    draw.text(((IMG_WIDTH - tw2) // 2, IMG_HEIGHT - 55), hint_text, fill=(180, 180, 180), font=font_hint)

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
    # {q_num: [(user_id, display_name, rank)]}
    answers: dict[int, list[tuple]] = field(default_factory=dict)
    answer_count: int = 0                       # 현재 문제 정답자 수
    total_participants: set[int] = field(default_factory=set)
    # 오답만 제출한 유저도 참가자로 기록
    attempted_participants: set[int] = field(default_factory=set)
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
    """현재 문제 줌 힌트 1단계 전송 + 단계별 힌트 태스크 + 타이머."""
    q = state.questions[state.current_q]
    q_num = state.current_q + 1
    total = len(state.questions)

    # 힌트 1: 줌인 크롭 (blocking → executor)
    loop = asyncio.get_event_loop()
    buf = await loop.run_in_executor(
        None, generate_zoom_hint_image, q["pokemon_id"], q_num, total, 1,
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
            f"⏰ {config.QUIZ_TIME_PER_QUESTION}초!\n"
            f"💡 <code>ㄷ 포켓몬이름</code> 으로 정답 제출!\n"
            f"🏆 빠를수록 좋은 보상! 누구나 참여 가능!"
        ),
        parse_mode="HTML",
    )

    # 단계별 힌트 백그라운드 태스크 (힌트 2, 3)
    asyncio.create_task(_send_progressive_hints(context, state, q_num))

    # 타임아웃 스케줄
    context.job_queue.run_once(
        _question_timeout,
        when=config.QUIZ_TIME_PER_QUESTION,
        data={"chat_id": state.chat_id, "q_num": q_num, "event_id": state.event_id},
        name=f"quiz_timeout_{state.chat_id}_{q_num}",
    )


async def _send_progressive_hints(context, state: QuizState, q_num: int):
    """10초, 20초에 힌트 2, 3 이미지 전송."""
    q = state.questions[q_num - 1]  # 0-indexed
    total = len(state.questions)
    intervals = config.QUIZ_HINT_INTERVALS  # [0, 10, 20]

    for i in range(1, len(intervals)):
        delay = intervals[i] - intervals[i - 1]
        await asyncio.sleep(delay)

        # 이미 다음 문제로 넘어갔거나 퀴즈 종료 시 중단
        if state.current_q + 1 != q_num or not state.is_accepting:
            return

        hint_level = i + 1  # 2 or 3
        try:
            loop = asyncio.get_event_loop()
            buf = await loop.run_in_executor(
                None, generate_zoom_hint_image, q["pokemon_id"], q_num, total, hint_level,
            )
            hint_labels = {2: "🔍 힌트 2/3 — 좀 더 보여줄게요!", 3: "👀 힌트 3/3 — 실루엣 공개!"}
            await context.bot.send_photo(
                chat_id=state.chat_id,
                photo=buf,
                caption=hint_labels.get(hint_level, ""),
                parse_mode="HTML",
            )
        except Exception as e:
            _log.warning(f"Failed to send hint {hint_level} for Q{q_num}: {e}")


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

    # 정답 시도 = 참가자로 기록
    state.attempted_participants.add(user_id)

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
    for uid, _, _ in state.answers.get(q_num, []):
        if uid == user_id:
            return False

    state.answer_count += 1
    rank = state.answer_count
    state.answers[q_num].append((user_id, display_name, rank))
    state.total_participants.add(user_id)

    # DB 기록
    await eq.record_quiz_answer(state.event_id, user_id, q_num, rank)

    # 응답 메시지
    rank_emojis = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    if rank <= 5:
        rank_emoji = rank_emojis[rank - 1]
    else:
        rank_emoji = f"{rank}등"
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"✅ {rank_emoji} <b>{display_name}</b> 정답!",
        parse_mode="HTML",
    )

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
    # 레이스컨디션 방지
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
    """최종 정산 — state.answers 기반으로 보상 계산 + 지급."""
    chat_id = state.chat_id
    event_id = state.event_id
    total_q = len(state.questions)

    # 활성 상태 제거
    _active_quizzes.pop(chat_id, None)
    await eq.update_event_status(event_id, "ended")

    # ── 유저별 보상 집계 (state.answers 기반) ──
    # {uid: {"display_name": str, "correct": int, "ranks": {1: n, 2: n, ...}, "items": [...], "bp": int}}
    user_rewards: dict[int, dict] = {}

    for q_num, ans_list in state.answers.items():
        for uid, dname, rank in ans_list:
            if uid not in user_rewards:
                user_rewards[uid] = {
                    "display_name": dname,
                    "correct": 0,
                    "ranks": {},
                    "items": [],
                    "bp": 0,
                }
            rew = user_rewards[uid]
            rew["correct"] += 1
            rew["ranks"][rank] = rew["ranks"].get(rank, 0) + 1

            # 등수별 보상 계산
            if rank == 1:
                item_name, amount, label = _roll_reward(config.QUIZ_REWARD_RANK1)
                rew["items"].append((item_name, amount, label))
                rew["bp"] += config.QUIZ_REWARD_TOP5_BP
            elif rank <= 3:
                item_name, amount, label = _roll_reward(config.QUIZ_REWARD_RANK2_3)
                rew["items"].append((item_name, amount, label))
                rew["bp"] += config.QUIZ_REWARD_TOP5_BP
            elif rank <= 5:
                item_name, amount, label = _roll_reward(config.QUIZ_REWARD_RANK4_5)
                rew["items"].append((item_name, amount, label))
                rew["bp"] += config.QUIZ_REWARD_TOP5_BP
            elif rank <= 10:
                rew["bp"] += config.QUIZ_REWARD_RANK6_10_BP
            else:
                rew["bp"] += config.QUIZ_REWARD_RANK11_BP

    # 오답만 제출/정답 0문제인 참가자 → 참가 보상
    all_participants = state.total_participants | state.attempted_participants
    for uid in all_participants:
        if uid not in user_rewards:
            user_rewards[uid] = {
                "display_name": str(uid),
                "correct": 0,
                "ranks": {},
                "items": [],
                "bp": config.QUIZ_REWARD_PARTICIPATION_BP,
            }

    # 참가 보상: 정답 0문제 유저
    for uid, rew in user_rewards.items():
        if rew["correct"] == 0:
            rew["bp"] = config.QUIZ_REWARD_PARTICIPATION_BP

    # ── 실제 지급 (test_mode면 스킵) ──
    if not state.test_mode:
        for uid, rew in user_rewards.items():
            # 아이템 지급
            item_totals: dict[str, int] = {}
            for item_name, amount, _ in rew["items"]:
                item_totals[item_name] = item_totals.get(item_name, 0) + amount
            for item_name, total_amt in item_totals.items():
                if item_name == "iv_stone":
                    await iq.add_iv_stones(uid, total_amt)
                elif item_name == "shiny_spawn_ticket":
                    await iq.add_shiny_spawn_ticket(uid, total_amt)
                else:
                    await iq.add_user_item(uid, item_name, total_amt)
            # BP 지급
            if rew["bp"] > 0:
                await queries.add_battle_points(uid, rew["bp"])

    # ── 결과 메시지 (채팅방) ──
    # 정답 수 기준 내림차순 정렬
    sorted_users = sorted(
        user_rewards.items(),
        key=lambda x: (-x[1]["correct"], min(x[1]["ranks"].keys()) if x[1]["ranks"] else 999),
    )

    test_label = " [테스트]" if state.test_mode else ""
    msg = f"🏆 <b>퀴즈 종료!{test_label}</b> ({total_q}문제)\n\n"

    if sorted_users:
        for i, (uid, rew) in enumerate(sorted_users[:15]):
            name = rew["display_name"]
            correct = rew["correct"]

            # 등수 요약: 🥇×2 🥈×1 형태
            rank_parts = []
            rank_icons = {1: "🥇", 2: "🥈", 3: "🥉"}
            for r in sorted(rew["ranks"].keys()):
                cnt = rew["ranks"][r]
                icon = rank_icons.get(r, f"{r}등")
                rank_parts.append(f"{icon}×{cnt}" if cnt > 1 else f"{icon}")

            rank_str = " ".join(rank_parts) if rank_parts else ""
            msg += f"  <b>{name}</b> — {correct}/{total_q} {rank_str}\n"

        if len(sorted_users) > 15:
            msg += f"  ... 외 {len(sorted_users) - 15}명\n"
    else:
        msg += "정답자 없음!\n"

    msg += f"\n👥 참가자 {len(all_participants)}명 전원 참가보상 {config.QUIZ_REWARD_PARTICIPATION_BP:,} BP"

    await context.bot.send_message(
        chat_id=chat_id,
        text=msg,
        parse_mode="HTML",
    )

    # 개인 DM 보상 알림
    if not state.test_mode:
        asyncio.create_task(_send_reward_dms(context, state, user_rewards))

    _log.info(f"Quiz finalized: event_id={event_id}, participants={len(all_participants)}")


async def _send_reward_dms(context, state: QuizState, user_rewards: dict[int, dict]):
    """개인별 보상 DM 발송."""
    total_q = len(state.questions)

    for uid, rew in user_rewards.items():
        correct = rew["correct"]
        items = rew["items"]  # [(item_name, amount, label), ...]
        bp = rew["bp"]
        ranks = rew["ranks"]

        lines = [f"🧠 <b>퀴즈 결과: {correct}/{total_q} 정답!</b>\n"]

        # 등수별 횟수
        if ranks:
            rank_icons = {1: "🥇", 2: "🥈", 3: "🥉"}
            rank_parts = []
            for r in sorted(ranks.keys()):
                cnt = ranks[r]
                icon = rank_icons.get(r, f"{r}등")
                rank_parts.append(f"{icon}×{cnt}" if cnt > 1 else f"{icon}")
            lines.append("📊 " + " ".join(rank_parts))

        lines.append("")

        if items:
            lines.append("🎁 <b>보상:</b>")
            for _, _, label in items:
                lines.append(f"  • {label}")

        if bp > 0:
            lines.append(f"💰 {bp:,} BP")

        if not items and bp == 0:
            lines.append("다음에는 더 빨리 도전해보세요!")

        try:
            await context.bot.send_message(
                chat_id=uid, text="\n".join(lines), parse_mode="HTML",
            )
        except Exception:
            pass
