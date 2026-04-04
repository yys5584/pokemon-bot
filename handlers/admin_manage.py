"""Admin management handlers: 아케이드, 대회, 통계, 채널목록, 어뷰징, KPI."""

import asyncio
import logging
from datetime import datetime, timezone

from telegram import Update
from telegram.ext import ContextTypes

import config

from database import queries, stats_queries
from handlers.admin import is_admin
from services.abuse_service import get_flagged_users, get_user_abuse_detail, admin_reset_score
from utils.helpers import icon_emoji

logger = logging.getLogger(__name__)


# ── Statistics & Channel ──────────────────────────────────

async def stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '통계' command — show overall bot statistics."""
    if not update.effective_user or not update.message:
        return
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("관리자만 사용할 수 있습니다.")
        return

    total = await stats_queries.get_total_stats()
    today = await stats_queries.get_today_stats()
    top_users = await stats_queries.get_rankings(3)
    top_pokemon = await stats_queries.get_top_pokemon_caught(5)

    lines = [
        "📊 봇 전체 통계\n",
        f"👥 총 유저: {total['total_users']}명",
        f"💬 활성 채팅방: {total['total_chats']}개",
        f"🌿 총 스폰: {total['total_spawns']}회",
        f"🎯 총 포획: {total['total_catches']}회",
        f"🔄 총 교환: {total['total_trades']}회",
        "",
        f"📅 오늘 스폰: {today['today_spawns']}회",
        f"📅 오늘 포획: {today['today_catches']}회",
    ]

    if top_users:
        lines.append("\n🏆 도감 TOP 3")
        for i, u in enumerate(top_users, 1):
            medal = ["🥇", "🥈", "🥉"][i - 1]
            lines.append(f"{medal} {u['display_name']} — {u['caught_count']}/151")

    if top_pokemon:
        lines.append("\n🔥 가장 많이 잡힌 포켓몬")
        for p in top_pokemon:
            lines.append(f"  {p['pokemon_emoji']} {p['pokemon_name']} — {p['catch_count']}회")

    await update.message.reply_text("\n".join(lines))


async def channel_list_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '채널목록' command — list all chat rooms."""
    if not update.effective_user or not update.message:
        return
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("관리자만 사용할 수 있습니다.")
        return

    rooms = await stats_queries.get_all_chat_rooms()

    if not rooms:
        await update.message.reply_text("등록된 채팅방이 없습니다.")
        return

    active = [r for r in rooms if r["is_active"]]
    inactive = [r for r in rooms if not r["is_active"]]

    lines = [f"💬 채팅방 목록 (총 {len(rooms)}개)\n"]

    if active:
        lines.append(f"🟢 활성 ({len(active)}개)")
        for r in active:
            title = r["chat_title"] or "(제목 없음)"
            members = r["member_count"]
            joined = (r["joined_at"] or "")[:10]
            last_spawn = (r["last_spawn_at"] or "-")[:16]
            lines.append(f"  {title}")
            lines.append(f"    인원: {members} | 가입: {joined}")
            lines.append(f"    최근스폰: {last_spawn}")

    if inactive:
        lines.append(f"\n🔴 비활성 ({len(inactive)}개)")
        for r in inactive:
            title = r["chat_title"] or "(제목 없음)"
            lines.append(f"  {title}")

    await update.message.reply_text("\n".join(lines))


# ── Arcade ──────────────────────────────────

async def arcade_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '아케이드' command in a group chat."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    text = (update.message.text or "").strip()
    parts = text.split()
    chat_id = update.effective_chat.id

    if len(parts) < 2:
        active_pass = await queries.get_active_arcade_pass(chat_id)
        if chat_id in config.ARCADE_CHAT_IDS:
            status = f"{icon_emoji('check')} 영구 등록"
        elif active_pass:
            expires = active_pass["expires_at"]
            if hasattr(expires, 'tzinfo') and expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            remaining = max(0, int((expires - datetime.now(timezone.utc)).total_seconds()))
            status = f"⏱ 임시 등록 ({remaining // 60}분 남음)"
        else:
            status = "❌ 미등록"

        tickets = await queries.get_arcade_tickets(user_id)
        await update.message.reply_text(
            f"🕹️ 아케이드 채널 ({status})\n\n"
            f"'아케이드 등록' — 아케이드 활성화\n"
            f"'아케이드 해제' — 아케이드 비활성화\n\n"
            f"🎮 내 아케이드 티켓: {tickets}개",
            parse_mode="HTML",
        )
        return

    action = parts[1]

    if action == "등록":
        # 관리자(chat admin) 체크: 봇 관리자가 아니면 채팅방 관리자인지 확인
        if not is_admin(user_id):
            try:
                member = await context.bot.get_chat_member(chat_id, user_id)
                if member.status not in ("administrator", "creator"):
                    await update.message.reply_text("🚫 아케이드 등록은 채팅방 관리자만 가능합니다.")
                    return
            except Exception:
                await update.message.reply_text("🚫 관리자 권한을 확인할 수 없습니다.")
                return

            room = await queries.get_chat_room(chat_id)
            member_count = room["member_count"] if room else 0
            if member_count < config.SPAWN_MIN_MEMBERS and chat_id not in config.EVENT_CHAT_IDS and not is_admin(user_id):
                await update.message.reply_text(
                    f"🚫 멤버가 {config.SPAWN_MIN_MEMBERS}명 이상인 방에서만 아케이드를 사용할 수 있습니다. (현재 {member_count}명)"
                )
                return

        if chat_id in config.ARCADE_CHAT_IDS:
            await update.message.reply_text("🕹️ 이미 영구 아케이드 채널입니다!")
            return

        active_pass = await queries.get_active_arcade_pass(chat_id)
        if active_pass:
            await update.message.reply_text("🕹️ 이미 아케이드가 활성화되어 있습니다!")
            return

        used = await queries.use_arcade_ticket(user_id)
        if used:
            await queries.create_arcade_pass(chat_id, user_id, config.ARCADE_PASS_DURATION)

            from services.spawn_service import start_temp_arcade
            start_temp_arcade(context.application, chat_id, config.ARCADE_PASS_DURATION, interval=config.ARCADE_TICKET_SPAWN_INTERVAL)

            display_name = update.effective_user.first_name or "트레이너"
            remaining_tickets = await queries.get_arcade_tickets(user_id)
            await update.message.reply_text(
                f"🕹️ {display_name}이(가) 아케이드 활성화!\n"
                f"⏱️ {config.ARCADE_PASS_DURATION // 60}분간 {config.ARCADE_TICKET_SPAWN_INTERVAL}초마다 스폰\n"
                f"🎮 남은 티켓: {remaining_tickets}개"
            )
            logger.info(f"Temp arcade activated by {user_id} (ticket) in chat {chat_id}")
            return

        if is_admin(user_id):
            config.ARCADE_CHAT_IDS.add(chat_id)
            await queries.set_arcade(chat_id, True)
            from services.spawn_service import schedule_arcade_spawns
            schedule_arcade_spawns(context.application)
            await update.message.reply_text(
                f"🕹️ 아케이드 채널 영구 등록 완료!\n"
                f"⏱️ {config.ARCADE_SPAWN_INTERVAL}초마다 포켓몬이 출현합니다."
            )
            logger.info(f"Arcade channel registered (permanent): {chat_id}")
            return

        await update.message.reply_text(
            "🎮 아케이드 티켓이 없습니다!\nDM 상점에서 '구매 아케이드'로 구매하세요."
        )

    elif action == "해제":
        if chat_id in config.ARCADE_CHAT_IDS:
            if not is_admin(user_id):
                await update.message.reply_text("🚫 영구 아케이드 해제는 관리자만 가능합니다.")
                return
            config.ARCADE_CHAT_IDS.discard(chat_id)
            await queries.set_arcade(chat_id, False)
        else:
            # 티켓 아케이드: 시작한 사람 또는 채팅방 관리자만 해제 가능
            if not is_admin(user_id):
                active_pass = await queries.get_active_arcade_pass(chat_id)
                is_activator = active_pass and active_pass.get("activated_by") == user_id
                is_chat_admin = False
                if not is_activator:
                    try:
                        member = await context.bot.get_chat_member(chat_id, user_id)
                        is_chat_admin = member.status in ("administrator", "creator")
                    except Exception:
                        pass
                if not is_activator and not is_chat_admin:
                    await update.message.reply_text("🚫 아케이드 해제는 시작한 사람 또는 관리자만 가능합니다.")
                    return

        from services.spawn_service import stop_arcade_for_chat
        stop_arcade_for_chat(context.application, chat_id)

        from database.connection import get_db
        pool = await get_db()
        await pool.execute(
            "UPDATE arcade_passes SET is_active = 0 WHERE chat_id = $1 AND is_active = 1",
            chat_id,
        )

        await update.message.reply_text("🕹️ 아케이드 해제됨. 일반 스폰으로 복구됩니다.")
        logger.info(f"Arcade channel unregistered: {chat_id}")


# ── Tournament ──────────────────────────────────

async def tournament_chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: '대회방등록' / '대회방해제'."""
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    text = (update.message.text or "").strip()
    chat_id = update.effective_chat.id

    if "해제" in text:
        await queries.set_tournament_chat_id(None)
        config.TOURNAMENT_CHAT_ID = None
        await update.message.reply_text("🏟️ 대회방 해제 완료.")
    else:
        await queries.set_tournament_chat_id(chat_id)
        config.TOURNAMENT_CHAT_ID = chat_id
        await update.message.reply_text(f"🏟️ 대회방 등록 완료!\n채팅방 ID: {chat_id}")


async def force_tournament_reg_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: 대회시작 — manually trigger tournament registration."""
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    from services.tournament_service import start_registration
    await start_registration(context)
    await update.message.reply_text("✅ 대회 등록 수동 시작!")


async def force_tournament_run_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: 대회진행 — manually trigger tournament execution."""
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    from services.tournament_service import start_tournament
    await update.message.reply_text("⚔️ 대회 진행 시작!")
    await start_tournament(context)


async def mock_tournament_reg_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: 모의대회 — start mock tournament registration (no rewards)."""
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    from services.tournament_service import start_registration
    await start_registration(context, mock=True)
    await update.message.reply_text("✅ 모의대회 등록 시작! (보상 없음)")


async def mock_tournament_run_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: 모의진행 — manually trigger mock tournament execution."""
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    from services.tournament_service import start_tournament
    await update.message.reply_text("⚔️ 모의대회 진행 시작!")
    await start_tournament(context)


async def event_tournament_reg_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: 이벤트대회 — 랜덤 1마리 이벤트 토너먼트 등록 시작."""
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    import config
    chat_id = update.effective_chat.id
    config.EVENT_CHAT_IDS.add(chat_id)
    config.TOURNAMENT_CHAT_ID = chat_id
    from services.tournament_service import start_registration
    await start_registration(context, mock=True, random_1v1=True)


async def event_tournament_run_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: 이벤트진행 — 이벤트 토너먼트 즉시 실행."""
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    # 스폰 job 중지 (대회 진행 중에는 스폰 불필요)
    chat_id = update.effective_chat.id
    chat_str = str(chat_id)
    for job in context.job_queue.jobs():
        if job.name and chat_str in job.name and (
            job.name.startswith("spawn_") or job.name.startswith("arcade_")
        ):
            job.schedule_removal()
    from services.tournament_service import snapshot_teams, start_tournament
    await update.message.reply_text("⚔️ 이벤트 대회 진행!")
    await snapshot_teams(context)
    await asyncio.sleep(3)
    await start_tournament(context)


async def resume_tournament_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: 대회재개 — 3/29 준결승부터 재개 (일시적)."""
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    from services.tournament_service import resume_tournament_from_semi
    await update.message.reply_text("⚔️ 대회 재개 시작! (준결승부터)")
    await resume_tournament_from_semi(context)


async def co_champion_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: 공동우승 — 3/29 대회 4명 공동우승 보상 (일시적)."""
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    from scripts.award_co_champions import award_co_champions
    await update.message.reply_text("🏆 공동우승 보상 지급 시작!")
    await award_co_champions(context)


# ── Abuse ──────────────────────────────────

async def abuse_list_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """관리자 명령 '어뷰징' — 의심 유저 목록."""
    if not update.effective_user or update.effective_user.id not in config.ADMIN_IDS:
        return
    flagged = await get_flagged_users(20)
    if not flagged:
        await update.message.reply_text("✅ 현재 의심 유저가 없습니다.")
        return

    lines = ["🚨 <b>봇 의심 유저 목록</b>\n"]
    for u in flagged:
        name = u.get("display_name", "???")
        uname = f"@{u['username']}" if u.get("username") else ""
        score = u.get("bot_score", 0)
        total = u.get("total_challenges", 0)
        fails = u.get("challenge_fails", 0)
        lines.append(
            f"• {name} {uname} — 점수: <b>{score:.2f}</b> "
            f"(챌린지 {total}회, 실패 {fails}회)\n"
            f"  <code>/어뷰징상세 {u['user_id']}</code>"
        )
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def abuse_detail_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """관리자 명령 '어뷰징상세 ID' — 특정 유저 상세."""
    if not update.effective_user or update.effective_user.id not in config.ADMIN_IDS:
        return
    text = update.message.text.strip()
    parts = text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await update.message.reply_text("사용법: 어뷰징상세 <유저ID>")
        return

    target_id = int(parts[1])
    detail = await get_user_abuse_detail(target_id)
    if not detail or not detail.get("score"):
        await update.message.reply_text(f"유저 {target_id}의 어뷰징 기록이 없습니다.")
        return

    s = detail["score"]
    lines = [
        f"🔍 <b>어뷰징 상세</b> — <code>{target_id}</code>\n",
        f"봇 점수: <b>{s.get('bot_score', 0):.3f}</b>",
        f"챌린지: 총 {s.get('total_challenges', 0)}회 | 통과 {s.get('challenge_passes', 0)} | 실패 {s.get('challenge_fails', 0)}",
        f"마지막 챌린지: {s.get('last_challenge_at', '-')}",
        f"마지막 플래그: {s.get('last_flagged_at', '-')}",
    ]

    reactions = detail.get("reactions", [])
    if reactions:
        ms_list = [r["reaction_ms"] for r in reactions if r.get("reaction_ms")]
        if ms_list:
            avg_ms = sum(ms_list) / len(ms_list)
            min_ms = min(ms_list)
            max_ms = max(ms_list)
            lines.append(f"\n📊 최근 반응시간 ({len(ms_list)}회):")
            lines.append(f"  평균: {avg_ms:.0f}ms | 최소: {min_ms}ms | 최대: {max_ms}ms")
            lines.append(f"  상세: {', '.join(f'{m}ms' for m in ms_list[:10])}")

    challenges = detail.get("challenges", [])
    if challenges:
        lines.append(f"\n📋 최근 챌린지:")
        for c in challenges[:5]:
            status = "✅" if c.get("passed") else "❌"
            ans = c.get("given_answer", "무응답") or "무응답"
            lines.append(f"  {status} 정답: {c.get('expected_answer')} | 입력: {ans}")

    lines.append(f"\n점수 초기화: <code>어뷰징초기화 {target_id}</code>")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def abuse_reset_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """관리자 명령 '어뷰징초기화 ID' — 점수 리셋."""
    if not update.effective_user or update.effective_user.id not in config.ADMIN_IDS:
        return
    text = update.message.text.strip()
    parts = text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await update.message.reply_text("사용법: 어뷰징초기화 <유저ID>")
        return

    target_id = int(parts[1])
    await admin_reset_score(target_id)
    # 잠금도 함께 해제
    from services.abuse_service import _catch_locks, _db_lock_cache
    _catch_locks.pop(target_id, None)
    _db_lock_cache.pop(target_id, None)
    try:
        from database.connection import get_db
        pool = await get_db()
        await pool.execute("UPDATE abuse_scores SET locked_until = NULL WHERE user_id = $1", target_id)
    except Exception:
        pass
    await update.message.reply_text(f"✅ 유저 {target_id}의 점수 + 포획 잠금 초기화 완료.")


# ── KPI Report ──────────────────────────────────

async def report_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '!리포트 MMDD' — 특정 날짜 일일 리포트 수동 트리거."""
    if not update.effective_user or not update.message:
        return
    if not is_admin(update.effective_user.id):
        return
    text = update.message.text.strip()
    parts = text.split()
    if len(parts) < 2 or len(parts[1]) != 4 or not parts[1].isdigit():
        await update.message.reply_text("사용법: !리포트 0316 (MMDD)")
        return

    from main import _send_daily_kpi_report
    mm, dd = int(parts[1][:2]), int(parts[1][2:])
    now = config.get_kst_now()
    target = now.replace(month=mm, day=dd, hour=0, minute=0, second=0, microsecond=0)
    await update.message.reply_text(f"📊 {mm}/{dd} 리포트 생성 중...")
    await _send_daily_kpi_report(context, target_date=target)
