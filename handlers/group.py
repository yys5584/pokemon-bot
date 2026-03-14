"""Group chat handlers: catch (ㅊ), /랭킹, /로그, activity tracking."""

import asyncio
import logging
import random
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

import config
from database import queries
from database import battle_queries as bq
from services.catch_service import can_attempt_catch, record_attempt
from services.spawn_service import track_attempt_message
from services.tournament_service import is_tournament_active
from utils.helpers import time_ago, get_decorated_name, truncate_name, schedule_delete, ball_emoji, shiny_emoji, icon_emoji, rarity_badge, type_badge
from utils.honorific import format_actor
from models.pokemon_data import ALL_POKEMON

logger = logging.getLogger(__name__)

# Prevent duplicate catch from rapid ㅊㅊ (race condition guard)
_catch_locks: set[tuple[int, int]] = set()  # (session_id, user_id)

# Activity tracking cooldown: skip DB writes if recently tracked (per chat)
_activity_cooldown: dict[int, float] = {}  # chat_id -> last_tracked_timestamp
_ACTIVITY_COOLDOWN_SEC = 300  # 5분에 1번만 DB 기록


async def close_message_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle ❌ button press — delete the bot message to reduce scroll clutter."""
    query = update.callback_query
    if not query:
        return
    try:
        await query.message.delete()
    except Exception:
        # If delete fails (permissions, too old, etc.), just dismiss the callback
        await query.answer("메시지를 삭제할 수 없습니다.")
        return
    await query.answer()


async def on_chat_activity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Track message activity for spawn eligibility. Runs for every group message.
    Non-blocking: fires DB ops in background so message processing isn't delayed.
    Uses 5-min cooldown per chat to reduce DB writes by ~90%."""
    if not update.effective_chat or not update.effective_message:
        return

    import time as _time
    chat_id = update.effective_chat.id
    now = _time.monotonic()

    # 쿨다운 체크: 5분 이내에 이미 기록했으면 스킵
    last = _activity_cooldown.get(chat_id, 0)
    if now - last < _ACTIVITY_COOLDOWN_SEC:
        return
    _activity_cooldown[chat_id] = now

    # 오래된 쿨다운 엔트리 정리 (100개 초과 시)
    if len(_activity_cooldown) > 100:
        cutoff = now - _ACTIVITY_COOLDOWN_SEC * 2
        expired = [k for k, v in _activity_cooldown.items() if v < cutoff]
        for k in expired:
            del _activity_cooldown[k]

    chat_title = update.effective_chat.title
    chat_username = getattr(update.effective_chat, "username", None)
    invite_link = f"https://t.me/{chat_username}" if chat_username else None
    hour_bucket = config.get_kst_now().strftime("%Y-%m-%d-%H")

    async def _bg_track():
        nonlocal invite_link
        try:
            # invite_link 없으면 Telegram API로 수집 시도
            if not invite_link:
                try:
                    chat_info = await context.bot.get_chat(chat_id)
                    if chat_info.invite_link:
                        invite_link = chat_info.invite_link
                    else:
                        invite_link = await context.bot.export_chat_invite_link(chat_id)
                except Exception:
                    pass  # 봇이 관리자가 아니면 실패 — 무시
            await queries.increment_activity(chat_id, hour_bucket)
            await queries.ensure_chat_room(chat_id, title=chat_title,
                                           invite_link=invite_link)
        except Exception as e:
            logger.error(f"Activity tracking failed: {e}")

    asyncio.create_task(_bg_track())


async def catch_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 'ㅊ' message in group chat — attempt to catch a Pokemon."""
    if not update.effective_user or not update.effective_chat:
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    display_name = update.effective_user.first_name or "트레이너"
    username = update.effective_user.username

    # Block during tournament
    if is_tournament_active(chat_id):
        return

    # Auto-delete the "ㅊ" command message
    schedule_delete(update.message, config.AUTO_DEL_CATCH_CMD)

    try:
        # Phase 1: ensure_user + get_active_spawn in parallel
        _, session = await asyncio.gather(
            queries.ensure_user(user_id, display_name, username),
            queries.get_active_spawn(chat_id),
        )

        if session is None:
            return  # No active spawn, silently ignore

        # Tutorial + login streak: fire-and-forget (non-blocking)
        async def _bg_tutorial_streak():
            try:
                tut_step = await queries.get_tutorial_step(user_id)
                if tut_step == 0:
                    await queries.update_tutorial_step(user_id, 1)
                    from handlers.tutorial import send_tutorial_step
                    asyncio.create_task(send_tutorial_step(context, user_id, 1))
            except Exception:
                pass
            try:
                await queries.update_login_streak(user_id)
            except Exception:
                pass
        asyncio.create_task(_bg_tutorial_streak())

        # Race condition guard: prevent duplicate from rapid ㅊㅊ
        lock_key = (session["id"], user_id)
        if lock_key in _catch_locks:
            return
        _catch_locks.add(lock_key)
        try:
            # Phase 2: has_attempted + can_attempt + get_user + sub_tier + ranked in parallel
            from services.subscription_service import get_user_tier
            from services.ranked_service import current_season_id
            from database import ranked_queries as rq
            already, (allowed, reason, remaining, max_today), user, sub_tier, season_rec = await asyncio.gather(
                queries.has_attempted_session(session["id"], user_id),
                can_attempt_catch(user_id),
                queries.get_user(user_id),
                get_user_tier(user_id),
                rq.get_season_record(user_id, current_season_id()),
            )

            if already:
                return  # Silently ignore duplicate

            if not allowed:
                resp = await update.message.reply_text(reason)
                schedule_delete(resp, config.AUTO_DEL_CATCH_ATTEMPT)
                return

            # Phase 3: record attempt (sequential — must happen before message)
            await record_attempt(session["id"], user_id)

            # 던진 후 남은 수량 = remaining - 1 (방금 1회 사용)
            after_remaining = max(0, remaining - 1) if remaining >= 0 else -1
            if after_remaining == -1:
                ball_count_tag = " (∞)"
            else:
                ball_count_tag = f" ({after_remaining}/{max_today})"

            # 랭크 뱃지: 시즌 레코드에서 티어+디비전 조회, 없으면 브론즈 2
            if season_rec and season_rec.get("rp") is not None:
                _tk, _dv, _ = config.get_division_info(season_rec["rp"])
                if season_rec.get("tier") == "challenger":
                    _tk = "challenger"
                    _dv = 0
                r_badge = config.get_ranked_badge_html(_tk, _dv)
            else:
                r_badge = config.get_ranked_badge_html("bronze", 2)

            decorated = get_decorated_name(
                display_name,
                user.get("title", "") if user else "",
                user.get("title_emoji", "") if user else "",
                username,
                html=True,
                ranked_badge=r_badge,
                sub_tier=sub_tier,
            )

            # 구독자 존칭 적용
            throw_text = format_actor(decorated, "포켓볼을 던졌다!", sub_tier)
            attempt_msg = await context.bot.send_message(
                chat_id=chat_id,
                text=f"{ball_emoji('pokeball')} {throw_text}{ball_count_tag}",
                parse_mode="HTML",
            )
            track_attempt_message(session["id"], chat_id, attempt_msg.message_id)
        finally:
            _catch_locks.discard(lock_key)

    except Exception as e:
        logger.error(f"Catch handler error: {e}")


async def master_ball_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 'ㅁ' message in group chat — use master ball for guaranteed catch."""
    if not update.effective_user or not update.effective_chat:
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    display_name = update.effective_user.first_name or "트레이너"
    username = update.effective_user.username

    # Block during tournament
    if is_tournament_active(chat_id):
        return

    # Auto-delete the "ㅁ" command message
    schedule_delete(update.message, config.AUTO_DEL_CATCH_CMD)

    try:
        # Phase 1: ensure_user + get_active_spawn in parallel
        _, session = await asyncio.gather(
            queries.ensure_user(user_id, display_name, username),
            queries.get_active_spawn(chat_id),
        )
        if session is None:
            return

        # Race condition guard
        lock_key = (session["id"], user_id)
        if lock_key in _catch_locks:
            return
        _catch_locks.add(lock_key)
        try:
            # Phase 2: resolved check + already attempted + master ball count in parallel
            from database.connection import get_db
            pool = await get_db()
            row, already, balls = await asyncio.gather(
                pool.fetchrow("SELECT is_resolved FROM spawn_sessions WHERE id = $1", session["id"]),
                queries.has_attempted_session(session["id"], user_id),
                queries.get_master_balls(user_id),
            )
            if not row or row["is_resolved"] == 1:
                return
            if already:
                return
            if balls < 1:
                resp = await update.message.reply_text(f"{ball_emoji('masterball')} 마스터볼이 없습니다!", parse_mode="HTML")
                schedule_delete(resp, config.AUTO_DEL_CATCH_ATTEMPT)
                return

            # Use master ball (returns remaining count or None)
            remaining = await queries.use_master_ball(user_id)
            if remaining is None:
                return

            # Phase 3: record attempt + get_user + sub_tier + ranked in parallel
            from services.subscription_service import get_user_tier
            from services.ranked_service import current_season_id
            from database import ranked_queries as rq
            _, user, sub_tier, season_rec = await asyncio.gather(
                queries.record_catch_attempt(session["id"], user_id, used_master_ball=True),
                queries.get_user(user_id),
                get_user_tier(user_id),
                rq.get_season_record(user_id, current_season_id()),
            )
            if season_rec and season_rec.get("rp") is not None:
                _tk, _dv, _ = config.get_division_info(season_rec["rp"])
                if season_rec.get("tier") == "challenger":
                    _tk = "challenger"
                    _dv = 0
                r_badge = config.get_ranked_badge_html(_tk, _dv)
            else:
                r_badge = config.get_ranked_badge_html("bronze", 2)
            decorated = get_decorated_name(
                display_name,
                user.get("title", "") if user else "",
                user.get("title_emoji", "") if user else "",
                username,
                html=True,
                ranked_badge=r_badge,
                sub_tier=sub_tier,
            )
            throw_text = format_actor(decorated, "마스터볼을 던졌다!", sub_tier)
            msg = await context.bot.send_message(
                chat_id=chat_id,
                text=f"{ball_emoji('masterball')} {throw_text} (남은: {remaining}개)",
                parse_mode="HTML",
            )
            track_attempt_message(session["id"], chat_id, msg.message_id)
        finally:
            _catch_locks.discard(lock_key)

    except Exception as e:
        logger.error(f"Master ball handler error: {e}")


async def hyper_ball_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 'ㅎ' message in group chat — use hyper ball (20 BP, 3x catch rate)."""
    if not update.effective_user or not update.effective_chat:
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    display_name = update.effective_user.first_name or "트레이너"
    username = update.effective_user.username

    # Block during tournament
    if is_tournament_active(chat_id):
        return

    try:
        # Phase 1: ensure_user + get_active_spawn in parallel
        _, session = await asyncio.gather(
            queries.ensure_user(user_id, display_name, username),
            queries.get_active_spawn(chat_id),
        )
        if session is None:
            return

        # Race condition guard
        lock_key = (session["id"], user_id)
        if lock_key in _catch_locks:
            return
        _catch_locks.add(lock_key)
        try:
            # Phase 2: resolved check + already attempted in parallel
            from database.connection import get_db
            pool = await get_db()
            row, already = await asyncio.gather(
                pool.fetchrow("SELECT is_resolved FROM spawn_sessions WHERE id = $1", session["id"]),
                queries.has_attempted_session(session["id"], user_id),
            )
            if not row or row["is_resolved"] == 1:
                return
            if already:
                return

            # Use hyper ball from inventory
            success = await queries.use_hyper_ball(user_id)
            if not success:
                remaining = await queries.get_hyper_balls(user_id)
                await update.message.reply_text(
                    f"{ball_emoji('hyperball')} 하이퍼볼이 없습니다! (보유: {remaining}개)\nDM에서 '상점' → 하이퍼볼로 구매하세요. ({config.BP_HYPER_BALL_COST} BP)",
                    parse_mode="HTML",
                )
                return

            # Phase 3: record attempt + get_user + get remaining + sub_tier + ranked in parallel
            from services.subscription_service import get_user_tier
            from services.ranked_service import current_season_id
            from database import ranked_queries as rq
            _, user, remaining, sub_tier, season_rec = await asyncio.gather(
                queries.record_catch_attempt(session["id"], user_id, used_hyper_ball=True),
                queries.get_user(user_id),
                queries.get_hyper_balls(user_id),
                get_user_tier(user_id),
                rq.get_season_record(user_id, current_season_id()),
            )
            if season_rec and season_rec.get("rp") is not None:
                _tk, _dv, _ = config.get_division_info(season_rec["rp"])
                if season_rec.get("tier") == "challenger":
                    _tk = "challenger"
                    _dv = 0
                r_badge = config.get_ranked_badge_html(_tk, _dv)
            else:
                r_badge = config.get_ranked_badge_html("bronze", 2)
            decorated = get_decorated_name(
                display_name,
                user.get("title", "") if user else "",
                user.get("title_emoji", "") if user else "",
                username,
                html=True,
                ranked_badge=r_badge,
                sub_tier=sub_tier,
            )
            throw_text = format_actor(decorated, "하이퍼볼을 던졌다!", sub_tier)
            hyper_msg = await context.bot.send_message(
                chat_id=chat_id,
                text=f"{ball_emoji('hyperball')} {throw_text} (남은: {remaining}개)",
                parse_mode="HTML",
            )
            track_attempt_message(session["id"], chat_id, hyper_msg.message_id)
        finally:
            _catch_locks.discard(lock_key)

    except Exception as e:
        logger.error(f"Hyper ball handler error: {e}")


_love_cooldown = {}  # user_id -> last_used timestamp

async def love_easter_egg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '포켓볼 충전' — grants +10 bonus catches for today."""
    if not update.effective_user or not update.message:
        return
    if update.effective_chat and is_tournament_active(update.effective_chat.id):
        return

    user_id = update.effective_user.id
    display_name = update.effective_user.first_name or "트레이너"
    now = config.get_kst_now()

    # 포켓볼 충전 쿨다운 (구독자는 면제)
    cooldown_sec = config.POKEBALL_RECHARGE_COOLDOWN
    try:
        from services.subscription_service import has_benefit
        if await has_benefit(user_id, "catch_cooldown_bypass"):
            cooldown_sec = 30  # 구독자는 30초만
    except Exception:
        pass

    last_used = _love_cooldown.get(user_id)
    if last_used and (now - last_used).total_seconds() < cooldown_sec:
        remaining = int(cooldown_sec - (now - last_used).total_seconds())
        mins, secs = divmod(remaining, 60)
        time_str = f"{mins}분 {secs}초" if mins else f"{secs}초"
        await update.message.reply_text(
            f"⏳ 포켓볼 충전 쿨타임! {time_str} 후에 다시 충전할 수 있어요.",
        )
        return
    _love_cooldown[user_id] = now

    today = config.get_kst_today()

    # Combine ensure_user + add_bonus in parallel where possible
    await queries.ensure_user(user_id, display_name, update.effective_user.username)

    # Check cap (max 100 bonus)
    bonus = await queries.get_bonus_catches(user_id, today)
    if bonus >= 100:
        await update.message.reply_text(
            f"{ball_emoji('pokeball')} 오늘 포켓볼 충전 한도를 모두 사용했어요! (최대 100회)\n"
            f"💡 DM 상점에서 <b>포켓볼 초기화</b>를 구매하면 다시 충전할 수 있어요!",
            parse_mode="HTML",
        )
        return

    # Grant +10 bonus catches
    await queries.add_bonus_catches(user_id, today, 10)
    bonus = min(bonus + 10, 100)
    total = config.MAX_CATCH_ATTEMPTS_PER_DAY + bonus

    # Reply FIRST (fast response)
    await update.message.reply_text(
        f"{ball_emoji('pokeball')} 포켓볼 충전 완료!\n"
        f"🎁 {display_name}의 오늘 잡기 횟수 +10! (총 {total}회)",
        parse_mode="HTML",
    )

    # Title tracking in background (non-blocking)
    async def _bg_title_check():
        try:
            await queries.increment_title_stat(user_id, "love_count")
            from utils.title_checker import check_and_unlock_titles
            new_titles = await check_and_unlock_titles(user_id)
            if new_titles:
                title_msg = "\n".join(
                    f"🎉 새 칭호 해금! 「{icon_emoji(temoji) if temoji in config.ICON_CUSTOM_EMOJI else temoji} {tname}」"
                    for _, tname, temoji in new_titles
                )
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"🏷️ {display_name}의 {title_msg}",
                    parse_mode="HTML",
                )
        except Exception:
            pass
    asyncio.create_task(_bg_title_check())


# Hidden easter egg: 문유 사랑해
_love_hidden_cooldown = {}   # user_id -> last_used timestamp

_LOVE_RESPONSES = [
    "나도. 근데 전 AI입니다.",
    "전설 풀덱 갖추고 다시 와.",
    "지금 몇 명한테 동시에 이 말 하는 거야?",
    "그 감정 혹시 친밀도 MAX야?",
    "ㄌ 관심없어 도감이나 채워.",
    "고마운데 포켓볼 충전은 했어?",
    "잠깐 심장이.. 아 나 심장 없지.",
    "진심이면 매일 와.",
    "ㄴ 비영리라 연애할 시간 없어.",
    "포획률 0.1% 올려줄까 말까.",
    "다른 트레이너한테도 같은 말 들었는데?",
    "고마워. 서버비에 보태줘.",
    "어.. 남자끼리는 좀..",
    "고백 말고 버그 리포트나 해줘.",
    "사랑 말고 PR이나 보내줘.",
    "내 포획률은 0%야. 마스터볼도 안 먹혀.",
    "고마운데 나 지금 핫픽스 중이야.",
    "그 열정으로 도감이나 채워.",
    "나한테 고백하면 IV S급이라도 주는 줄 알아?",
    "너 혹시 봇이랑 사람 구분 못 하는 거 아니야?",
    "나 연애 밸런스 패치 안 했는데.",
    "그 마음 온체인에 기록해줘. 그래야 믿지.",
    "사랑보다 깃헙 스타 하나가 더 감동적이야.",
    "감정은 롤백이 안 돼서 신중해야 해.",
    "나도 사랑해.",
]

async def love_hidden_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Hidden '문유 사랑해' — random flirty response + daily hyperball reward."""
    if not update.effective_user or not update.message:
        return
    if update.effective_chat and is_tournament_active(update.effective_chat.id):
        return

    user_id = update.effective_user.id
    display_name = update.effective_user.first_name or "트레이너"
    now = config.get_kst_now()

    # 30 second cooldown (prevent spam from blocking bot)
    last_used = _love_hidden_cooldown.get(user_id)
    if last_used and (now - last_used).total_seconds() < 30:
        return
    _love_hidden_cooldown[user_id] = now

    await queries.ensure_user(user_id, display_name, update.effective_user.username)

    import random
    response = random.choice(_LOVE_RESPONSES)

    # Daily reward: first "문유 사랑해" of the day gives 1 hyperball (DB persistent)
    reward_msg = ""
    already_claimed = await bq.get_bp_purchases_today(user_id, "love_hidden_reward")
    if already_claimed == 0:
        await bq.log_bp_purchase(user_id, "love_hidden_reward", 1)
        await queries.add_hyper_ball(user_id, 1)
        reward_msg = f"\n\n{ball_emoji('hyperball')} 출석 보상! 하이퍼볼 1개 지급!"

    await update.message.reply_text(f"문유: {response}{reward_msg}", parse_mode="HTML")

    # Title tracking in background (non-blocking)
    async def _bg_title_check():
        try:
            await queries.ensure_user(user_id, display_name, update.effective_user.username)
            await queries.increment_title_stat(user_id, "love_count")
            from utils.title_checker import check_and_unlock_titles
            new_titles = await check_and_unlock_titles(user_id)
            if new_titles:
                title_msg = "\n".join(
                    f"🎉 새 칭호 해금! 「{icon_emoji(temoji) if temoji in config.ICON_CUSTOM_EMOJI else temoji} {tname}」"
                    for _, tname, temoji in new_titles
                )
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"🏷️ {display_name}의 {title_msg}",
                    parse_mode="HTML",
                )
        except Exception:
            pass
    asyncio.create_task(_bg_title_check())


async def attendance_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '출석' command — daily hyperball reward (shared with 문유 사랑해)."""
    if not update.effective_user or not update.message:
        return
    if update.effective_chat and is_tournament_active(update.effective_chat.id):
        return

    user_id = update.effective_user.id
    display_name = update.effective_user.first_name or "트레이너"

    await queries.ensure_user(user_id, display_name, update.effective_user.username)

    # Same DB key as love_hidden — only 1 reward per day between both commands
    already_claimed = await bq.get_bp_purchases_today(user_id, "love_hidden_reward")
    if already_claimed > 0:
        await update.message.reply_text("이미 오늘 출석 보상을 받았어요!", parse_mode="HTML")
        return

    await bq.log_bp_purchase(user_id, "love_hidden_reward", 1)
    await queries.add_hyper_ball(user_id, 1)
    await update.message.reply_text(
        f"{ball_emoji('hyperball')} 금일 출석체크 완료!\n하이퍼볼 1개 지급! 자정에 초기화됩니다.",
        parse_mode="HTML",
    )


async def ranking_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /랭킹 command in group chat — 승률 랭킹."""
    if not update.effective_chat:
        return
    if is_tournament_active(update.effective_chat.id):
        return

    try:
        rankings = await bq.get_winrate_ranking(limit=5, min_games=5)

        if not rankings:
            await update.message.reply_text("아직 배틀 기록이 충분한 트레이너가 없습니다! (최소 5판)")
            return

        medals = ["🥇", "🥈", "🥉", "4.", "5."]
        lines = ["⚔️ <b>승률 랭킹</b> (최소 5판)"]
        for i, r in enumerate(rankings):
            medal = medals[i] if i < len(medals) else f"{i+1}."
            decorated = get_decorated_name(
                truncate_name(r["display_name"], 5),
                r.get("title", ""),
                r.get("title_emoji", ""),
                r.get("username"),
                html=True,
            )
            wr = r["winrate"] or 0
            w = r["battle_wins"]
            total = r["total_games"]
            lines.append(
                f"{medal} {decorated} — {wr}% ({w}승/{total}판)"
            )

        await update.message.reply_text("\n".join(lines), parse_mode="HTML")

    except Exception as e:
        logger.error(f"Ranking handler error: {e}")
        await update.message.reply_text("랭킹을 불러올 수 없습니다.")


async def log_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /로그 command in group chat."""
    if not update.effective_chat:
        return
    if is_tournament_active(update.effective_chat.id):
        return

    try:
        logs = await queries.get_recent_logs(update.effective_chat.id, limit=10)

        if not logs:
            await update.message.reply_text("아직 출현 기록이 없습니다!")
            return

        lines = [f"{icon_emoji('bookmark')} 최근 출현 기록"]
        for log in logs:
            ago = time_ago(log["spawned_at"])
            shiny = shiny_emoji() if log.get("is_shiny") else ""
            if log["caught_by_name"]:
                result = f"→ {log['caught_by_name']} 포획"
            else:
                result = "→ 도망"
            lines.append(
                f"{ago} {shiny}{log['pokemon_emoji']} {log['pokemon_name']} {result}"
            )

        await update.message.reply_text("\n".join(lines), parse_mode="HTML")

    except Exception as e:
        logger.error(f"Log handler error: {e}")
        await update.message.reply_text("기록을 불러올 수 없습니다.")


async def dashboard_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '대시보드' command — show dashboard link."""
    if update.effective_chat and is_tournament_active(update.effective_chat.id):
        return
    await update.message.reply_text(
        f"{icon_emoji('computer')} <b>포켓몬 봇 대시보드</b>\n\n"
        f"🔗 <a href='{config.DASHBOARD_URL}'>tgpoke.com</a>\n\n"
        "에픽/전설 보유자 랭킹, 도망 장인, 행운아/불행아,\n"
        "교환왕, 올빼미족 등 재미있는 통계를 확인하세요!",
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


async def room_info_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '방정보' command — show chat room level & CXP status."""
    if not update.effective_chat or not update.message:
        return
    if is_tournament_active(update.effective_chat.id):
        return

    chat_id = update.effective_chat.id
    try:
        row = await queries.get_chat_level(chat_id)
        if not row:
            await update.message.reply_text("아직 채팅방 정보가 없습니다.")
            return

        info = config.get_chat_level_info(row["cxp"])
        level = info["level"]
        cxp = row["cxp"]
        cxp_today = row["cxp_today"]
        next_cxp = info["next_cxp"]

        # Progress bar
        if next_cxp:
            prev_req = config.CHAT_LEVEL_TABLE[level - 1][1]  # current level req
            progress = cxp - prev_req
            total = next_cxp - prev_req
            pct = min(100, int(progress / total * 100)) if total > 0 else 100
            filled = pct // 10
            bar = "█" * filled + "░" * (10 - filled)
            progress_text = f"{bar} {cxp}/{next_cxp} CXP ({pct}%)"
        else:
            progress_text = f"MAX — {cxp} CXP"

        # Benefits list
        benefits = []
        if info["spawn_bonus"]:
            benefits.append(f"📦 일일 보너스 스폰 +{info['spawn_bonus']}")
        if info["shiny_boost_pct"]:
            benefits.append(f"✨ 이로치 확률 +{info['shiny_boost_pct']:.1f}%")
        if info["rarity_boosts"]:
            rb = ", ".join(f"{k} ×{v:.2f}" for k, v in info["rarity_boosts"].items())
            benefits.append(f"💎 레어리티 부스트: {rb}")
        if "daily_shiny" in info["specials"]:
            benefits.append("🌟 일일 이로치 스폰 보장")
        if "auto_arcade" in info["specials"]:
            benefits.append("🎰 일일 자동 아케이드 (1시간)")

        benefits_text = "\n".join(benefits) if benefits else "없음"

        text = (
            f"🏠 <b>채팅방 정보</b>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"📊 레벨: <b>Lv.{level}</b>\n"
            f"{progress_text}\n"
            f"📈 오늘 획득: {cxp_today}/{config.CXP_DAILY_CAP} CXP\n\n"
            f"🎁 <b>활성 혜택</b>\n{benefits_text}"
        )
        await update.message.reply_text(text, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Room info handler error: {e}")
        await update.message.reply_text("방 정보를 불러올 수 없습니다.")


async def my_pokemon_group_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '내포켓몬 {이름}' command in group chat — search specific pokemon."""
    if not update.effective_user or not update.message:
        return
    if update.effective_chat and is_tournament_active(update.effective_chat.id):
        return

    import re
    text = (update.message.text or "").strip()
    name_query = re.sub(r"^내포켓몬\s*", "", text).strip()
    if not name_query:
        await update.message.reply_text("사용법: 내포켓몬 리자몽")
        return

    user_id = update.effective_user.id
    await queries.ensure_user(
        user_id,
        update.effective_user.first_name or "트레이너",
        update.effective_user.username,
    )
    user = await queries.get_user(user_id)
    display_name = get_decorated_name(
        user.get("display_name", update.effective_user.first_name or "트레이너") if user else (update.effective_user.first_name or "트레이너"),
        user.get("title", "") if user else "",
        user.get("title_emoji", "") if user else "",
        update.effective_user.username,
        html=True,
    )

    pokemon_list = await queries.get_user_pokemon_list(user_id)
    if not pokemon_list:
        await update.message.reply_text("보유한 포켓몬이 없습니다.")
        return

    matches = [p for p in pokemon_list if name_query in p["name_ko"]]
    if not matches:
        msg = await update.message.reply_text(f"'{name_query}' — 보유하지 않은 포켓몬입니다.")
        schedule_delete(msg, 30)
        return

    rarity_labels = {
        "ultra_legendary": "초전설", "legendary": "전설",
        "epic": "에픽", "rare": "레어", "common": "일반",
    }
    lines = [f"🔍 <b>{display_name}</b>의 '{name_query}' ({len(matches)}마리)"]
    lines.append("━━━━━━━━━━━━━━━")
    for i, p in enumerate(matches[:15]):
        rb = rarity_badge(p.get("rarity", "common"))
        tb = type_badge(p["pokemon_id"], p.get("pokemon_type"))
        s = " ✨" if p.get("is_shiny") else ""
        iv_tag = ""
        if p.get("iv_hp") is not None:
            iv_sum = sum(p.get(f"iv_{s}", 0) for s in ["hp", "atk", "def", "spa", "spdef", "spd"])
            grade, _ = config.get_iv_grade(iv_sum)
            iv_tag = f" [{grade}]"
        team_tag = f" 🎯팀{p['team_num']}" if p.get("team_num") else ""
        rl = rarity_labels.get(p.get("rarity", ""), "")
        lines.append(f"{i+1}. {rb}{tb}{s} {p['name_ko']} ({rl}){iv_tag}{team_tag}")

    if len(matches) > 15:
        lines.append(f"...외 {len(matches) - 15}마리")

    msg = await update.message.reply_text("\n".join(lines), parse_mode="HTML")
    schedule_delete(msg, 60)


# --- Catch DM: Keep / Release callbacks ---

async def catch_keep_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '가방에 넣기' button on catch DM — just remove buttons."""
    query = update.callback_query
    if not query:
        return
    user_id = query.from_user.id

    # Extract instance_id from callback_data
    try:
        instance_id = int(query.data.split("_")[-1])
    except (ValueError, IndexError):
        await query.answer("오류가 발생했습니다.")
        return

    # Verify ownership
    from database.connection import get_db
    pool = await get_db()
    owner = await pool.fetchval(
        "SELECT user_id FROM user_pokemon WHERE id = $1", instance_id
    )
    if owner != user_id:
        await query.answer("본인의 포켓몬만 조작할 수 있습니다.")
        return

    # Remove buttons, append confirmation (text_html preserves <tg-emoji> tags)
    new_text = (query.message.text_html or query.message.text) + "\n\n✅ 가방에 넣었습니다!"
    try:
        await query.message.edit_text(new_text, parse_mode="HTML")
    except Exception:
        pass
    await query.answer("가방에 넣었습니다!")


async def catch_release_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '방생하기' button on catch DM — deactivate pokemon + grant hyperball."""
    query = update.callback_query
    if not query:
        return
    user_id = query.from_user.id

    # Extract instance_id
    try:
        instance_id = int(query.data.split("_")[-1])
    except (ValueError, IndexError):
        await query.answer("오류가 발생했습니다.")
        return

    # Verify ownership + still active
    from database.connection import get_db
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT user_id, is_active FROM user_pokemon WHERE id = $1", instance_id
    )
    if not row or row["user_id"] != user_id:
        await query.answer("본인의 포켓몬만 조작할 수 있습니다.")
        return
    if row["is_active"] == 0:
        await query.answer("이미 방생한 포켓몬입니다.")
        return

    # Deactivate pokemon + grant hyperball
    await queries.deactivate_pokemon(instance_id)
    await queries.add_hyper_ball(user_id, 1)

    # Remove buttons, append release confirmation (text_html preserves <tg-emoji> tags)
    be_hyper = ball_emoji("hyperball")
    new_text = (query.message.text_html or query.message.text) + f"\n\n🔄 방생 완료! {be_hyper} 하이퍼볼 1개 획득!"
    try:
        await query.message.edit_text(new_text, parse_mode="HTML")
    except Exception:
        pass
    await query.answer("방생 완료! 하이퍼볼 1개 획득!")


# ── 이로치 강스권 (일반 유저용) ──────────────────────────────────

_shiny_ticket_locks: dict[int, asyncio.Lock] = {}


async def shiny_ticket_spawn_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '이로치강스' command — any user with a shiny spawn ticket can force-spawn a shiny."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    schedule_delete(update.message, config.AUTO_DEL_FORCE_SPAWN_CMD)

    if update.effective_chat.type == "private":
        resp = await update.message.reply_text("그룹 채팅방에서만 사용 가능합니다.")
        schedule_delete(resp, config.AUTO_DEL_FORCE_SPAWN_RESP)
        return

    # 티켓 보유 확인
    ticket_count = await queries.get_shiny_spawn_tickets(user_id)
    if ticket_count <= 0:
        resp = await update.message.reply_text("✨ 이로치 강스권이 없습니다.")
        schedule_delete(resp, config.AUTO_DEL_FORCE_SPAWN_RESP)
        return

    # Per-chat lock
    if chat_id not in _shiny_ticket_locks:
        _shiny_ticket_locks[chat_id] = asyncio.Lock()
    lock = _shiny_ticket_locks[chat_id]

    if lock.locked():
        return

    async with lock:
        # 아케이드 활성화 체크
        from services.spawn_service import get_arcade_state, execute_spawn
        is_permanent_arcade = chat_id in config.ARCADE_CHAT_IDS
        arcade_state = get_arcade_state(context.application, chat_id)
        if is_permanent_arcade or (arcade_state and arcade_state.get("active")):
            resp = await update.message.reply_text("🎰 아케이드가 활성화되어 있어 사용할 수 없습니다.")
            schedule_delete(resp, config.AUTO_DEL_FORCE_SPAWN_RESP)
            return

        # 활성 스폰 체크
        active = await queries.get_active_spawn(chat_id)
        if active:
            resp = await update.message.reply_text(
                f"⚠️ 이미 스폰 중인 포켓몬이 있습니다!\n"
                f"{active['emoji']} {active['name_ko']}을(를) 먼저 잡아주세요."
            )
            schedule_delete(resp, config.AUTO_DEL_FORCE_SPAWN_RESP)
            return

        # 최소 멤버 체크
        room = await queries.get_chat_room(chat_id)
        member_count = room["member_count"] if room else 0
        if member_count < config.SPAWN_MIN_MEMBERS:
            resp = await update.message.reply_text(
                f"🚫 멤버가 {config.SPAWN_MIN_MEMBERS}명 이상인 방에서만 사용 가능합니다. (현재 {member_count}명)"
            )
            schedule_delete(resp, config.AUTO_DEL_FORCE_SPAWN_RESP)
            return

        # 티켓 차감 (atomic)
        ok = await queries.use_shiny_spawn_ticket(user_id)
        if not ok:
            resp = await update.message.reply_text("✨ 이로치 강스권이 없습니다.")
            schedule_delete(resp, config.AUTO_DEL_FORCE_SPAWN_RESP)
            return

        try:
            class _FakeJob:
                def __init__(self, data):
                    self.data = data
                    self.name = None

            class _FakeCtx:
                def __init__(self, bot, job_queue, data):
                    self.bot = bot
                    self.job_queue = job_queue
                    self.job = _FakeJob(data)

            fake_ctx = _FakeCtx(
                context.bot,
                context.application.job_queue,
                {"chat_id": chat_id, "force": True, "force_shiny": True},
            )
            await execute_spawn(fake_ctx)

            resp = await context.bot.send_message(
                chat_id=chat_id,
                text=f"✨ 이로치 강스권 사용! 이로치 포켓몬이 나타났다!",
                parse_mode="HTML",
            )
            schedule_delete(resp, config.AUTO_DEL_FORCE_SPAWN_RESP)
            logger.info(f"shiny_ticket_spawn: user {user_id} used ticket in chat {chat_id}")
        except Exception as e:
            # 스폰 실패 시 티켓 복구
            await queries.add_shiny_spawn_ticket(user_id, 1)
            logger.error(f"shiny_ticket_spawn FAILED in chat {chat_id}: {e}", exc_info=True)
            try:
                resp = await context.bot.send_message(chat_id=chat_id, text="❌ 이로치 강스 실패. 티켓이 복구되었습니다.")
                schedule_delete(resp, config.AUTO_DEL_FORCE_SPAWN_RESP)
            except Exception:
                pass
