"""스케줄러 job 등록 — main.py의 Schedule jobs 섹션을 함수로 추출."""

import logging
import os
from datetime import time as dt_time, timezone, timedelta

import config
from jobs.kpi_report import _send_daily_kpi_report, _send_weekly_kpi_report
from jobs.midnight import midnight_reset
from jobs.ranked_jobs import (
    ranked_weekly_reset_job,
    ranked_mid_season_check_job,
    ranked_decay_job,
)
from services.tournament_service import start_registration, start_tournament, snapshot_teams

logger = logging.getLogger(__name__)

# KST = UTC+9
_KST = timezone(timedelta(hours=9))


def register_all_jobs(app):
    """Application에 모든 스케줄 job을 등록한다."""
    jq = app.job_queue

    # --- KPI 리포트 ---
    # 일일 리포트 (23:55 KST — 리셋 전 데이터 캡처)
    jq.run_daily(
        _send_daily_kpi_report,
        time=dt_time(23, 55, 0, tzinfo=_KST),
        name="daily_kpi_report",
    )

    # 주간 리포트 (월요일 00:01 KST)
    jq.run_daily(
        _send_weekly_kpi_report,
        time=dt_time(0, 1, 0, tzinfo=_KST),
        name="weekly_kpi_report",
    )

    # --- 자정 리셋 ---
    jq.run_daily(
        midnight_reset,
        time=dt_time(0, 0, 0, tzinfo=_KST),
        name="reset_midnight",
    )

    # --- 3시간마다 잡기횟수 충전 ---
    from database import spawn_queries

    async def catch_recharge_job(context):
        """Recharge 50% of used catches every 3 hours (between full resets)."""
        logger.info("Running 3-hourly catch recharge (50%)...")
        await spawn_queries.recharge_catch_limits()
        logger.info("Catch recharge complete.")

    for hour in (0, 3, 6, 12, 15, 18):
        jq.run_daily(
            catch_recharge_job,
            time=dt_time(hour, 0, 0, tzinfo=_KST),
            name=f"recharge_{hour:02d}",
        )

    # --- 날씨 업데이트 (1시간마다) ---
    from services.weather_service import update_weather

    async def weather_update_job(context):
        """Periodic weather update (every hour)."""
        weather_city = os.getenv("WEATHER_CITY", "Seoul")
        await update_weather(weather_city)

    jq.run_repeating(
        weather_update_job,
        interval=3600,
        first=3600,
        name="weather_update",
    )

    # --- 랭크전 시즌 ---
    # 주간 리셋 (목요일 00:05 KST)
    jq.run_daily(
        ranked_weekly_reset_job,
        time=dt_time(0, 5, 0, tzinfo=_KST),
        name="ranked_weekly_reset",
    )

    # 중간 시즌 체크 (매일 00:10 KST)
    jq.run_daily(
        ranked_mid_season_check_job,
        time=dt_time(0, 10, 0, tzinfo=_KST),
        name="ranked_mid_season_check",
    )

    # 디케이 (마스터+, 매일 00:15 KST)
    jq.run_daily(
        ranked_decay_job,
        time=dt_time(0, 15, 0, tzinfo=_KST),
        name="ranked_decay",
    )

    # --- 구독 결제 ---
    # 결제 폴링 (60초마다)
    async def _subscription_poll_job(context):
        try:
            from services.subscription_service import poll_chain_transfers
            await poll_chain_transfers(context.bot)
        except Exception as e:
            logger.error(f"Subscription poll job error: {e}")

    jq.run_repeating(
        _subscription_poll_job,
        interval=60,
        first=10,
        name="subscription_poll",
    )

    # 만료 체크 + 갱신 알림 (매일 09:00 KST)
    async def _subscription_expiry_job(context):
        try:
            from services.subscription_service import check_expiry_and_notify
            await check_expiry_and_notify(context.bot)
        except Exception as e:
            logger.error(f"Subscription expiry job error: {e}")

    jq.run_daily(
        _subscription_expiry_job,
        time=dt_time(9, 0, 0, tzinfo=_KST),
        name="subscription_expiry",
    )

    # --- 토너먼트 ---
    # 21:00 등록, 21:50 스냅샷, 22:00 시작 (KST)
    jq.run_daily(
        start_registration,
        time=dt_time(config.TOURNAMENT_REG_HOUR, 0, 0, tzinfo=_KST),
        name="tournament_reg",
    )
    jq.run_daily(
        snapshot_teams,
        time=dt_time(config.TOURNAMENT_REG_HOUR, 50, 0, tzinfo=_KST),
        name="tournament_snapshot",
    )
    jq.run_daily(
        start_tournament,
        time=dt_time(config.TOURNAMENT_START_HOUR, 0, 0, tzinfo=_KST),
        name="tournament_start",
    )

    # --- 캠프 라운드 (3시간 간격) ---
    from handlers._register import HAS_CAMP
    if HAS_CAMP:
        from handlers._register import camp_round_job
        for hour in config.CAMP_ROUND_HOURS:
            jq.run_daily(
                camp_round_job,
                time=dt_time(hour, 0, 0, tzinfo=_KST),
                name=f"camp_round_{hour:02d}",
            )

    # --- 이로치 알 부화 (10분마다) ---
    async def _egg_hatch_job(context):
        try:
            from services.gacha_service import hatch_ready_eggs
            hatched = await hatch_ready_eggs(context.bot)
            for h in hatched:
                try:
                    rarity_labels = {"common": "일반", "rare": "레어", "epic": "에픽",
                                     "legendary": "전설", "ultra_legendary": "초전설"}
                    rarity_name = rarity_labels.get(h["rarity"], h["rarity"])
                    iv_sum = sum(h["ivs"].values())
                    await context.bot.send_message(
                        chat_id=h["user_id"],
                        text=(
                            f"🥚✨ <b>알이 부화했습니다!</b>\n\n"
                            f"✨ <b>{h['name_ko']}</b> (이로치)\n"
                            f"등급: {rarity_name}\n"
                            f"IV 합계: {iv_sum}/186\n\n"
                            f"🎉 도감에 자동 등록되었습니다!"
                        ),
                        parse_mode="HTML",
                    )
                except Exception as e:
                    logger.error(f"Egg hatch DM failed for {h['user_id']}: {e}")
        except Exception as e:
            logger.error(f"Egg hatch job failed: {e}")

    jq.run_repeating(
        _egg_hatch_job,
        interval=600,  # 10분마다
        first=60,
        name="egg_hatch_check",
    )

    logger.info("All scheduled jobs registered.")
