"""랭크전 시즌 관련 스케줄러 job 함수들."""

import asyncio
import logging

import config
from database import title_queries

logger = logging.getLogger(__name__)


async def ranked_weekly_reset_job(context):
    """매주 목요일 00:05 KST: 시즌 보상 → 소프트 리셋 → 새 시즌 공지."""
    try:
        from services import ranked_service as rs
        from database import ranked_queries as rq

        # 목요일(3)만 실행
        now = config.get_kst_now()
        if now.weekday() != config.SEASON_START_WEEKDAY:
            return

        prev_season = await rq.get_current_season()

        # 2주 시즌: 시즌 종료 여부 확인 (시즌이 아직 진행 중이면 스킵)
        if prev_season:
            ends_at = prev_season["ends_at"]
            # ends_at가 datetime 객체면 직접 비교, naive면 KST로 가정
            if ends_at.tzinfo is None:
                ends_at = ends_at.replace(tzinfo=config.KST)
            if now < ends_at:
                # 시즌 아직 진행 중 → 리셋 안 함
                logger.info(f"Season {prev_season['season_id']} still active, skipping reset")
                return

        # 이전 시즌 보상 처리
        if prev_season and not prev_season["rewards_distributed"]:
            rewarded = await rs.process_season_rewards(prev_season["season_id"])
            logger.info(f"Season rewards: {len(rewarded)} users rewarded")

            # 시즌 1위 → 챔피언 칭호 해금
            champion_uid = await rs.get_season_champion(prev_season["season_id"])
            if champion_uid:
                try:
                    await title_queries.unlock_title(champion_uid, "ranked_champion")
                    logger.info(f"Season champion title unlocked for {champion_uid}")
                except Exception:
                    pass

            # 보상 DM 발송
            for r in rewarded:
                try:
                    tier_d = rs.tier_display(r["tier"])
                    parts = []
                    if r.get("masterball", 0):
                        parts.append(f"마스터볼 x{r['masterball']}")
                    if r.get("bp", 0):
                        parts.append(f"BP {r['bp']}")
                    reward_txt = " + ".join(parts)
                    champ_note = ""
                    if r["user_id"] == champion_uid:
                        champ_note = "\n🏆 <b>시즌 챔피언!</b> '시즌 챔피언' 칭호 해금!"
                    await context.bot.send_message(
                        chat_id=r["user_id"],
                        text=f"🏟️ 시즌 {prev_season['season_id']} 보상!\n"
                             f"최고 티어: {tier_d}\n🎁 {reward_txt}{champ_note}",
                        parse_mode="HTML",
                    )
                except Exception:
                    pass

        # 새 시즌 생성 (소프트 리셋 포함)
        if prev_season:
            new_season = await rs.soft_reset_new_season(prev_season["season_id"])
        else:
            new_season = await rs.ensure_current_season()

        if not new_season:
            logger.error("Failed to create new ranked season")
            return

        # 새 시즌 공지 (DM 방식: season_records 보유 유저에게)
        rule_info = config.WEEKLY_RULES.get(new_season["weekly_rule"], {})

        # 지난 시즌 TOP 3
        top3_lines = []
        if prev_season:
            top3 = await rq.get_ranked_ranking(prev_season["season_id"], limit=3)
            medals = ["🥇", "🥈", "🥉"]
            for i, r in enumerate(top3):
                td = rs.tier_display(r["tier"])
                name = r.get("display_name") or "???"
                top3_lines.append(f"  {medals[i]} {name} ({td} {r['rp']} RP)")

        announce = [
            f"🏟️ 시즌 {new_season['season_id']} 시작!",
            f"🔒 시즌 법칙: {rule_info.get('name', new_season['weekly_rule'])}",
            f"   └ {rule_info.get('desc', '')}",
        ]

        if top3_lines:
            announce.append(f"\n🏆 지난 시즌 TOP 3")
            announce.extend(top3_lines)

        announce.append("\n💡 DM에서 '랭전'으로 자동 매칭 대전!")

        text = "\n".join(announce)

        # 시즌 기록 있는 유저에게 DM 알림
        if prev_season:
            all_records = await rq.get_all_season_records(prev_season["season_id"])
            for rec in all_records:
                try:
                    await context.bot.send_message(
                        chat_id=rec["user_id"], text=text, parse_mode="HTML",
                    )
                except Exception:
                    pass
                await asyncio.sleep(0.05)

        logger.info(f"New ranked season started: {new_season['season_id']}")
    except Exception as e:
        logger.error(f"Ranked weekly reset failed: {e}")


async def ranked_mid_season_check_job(context):
    """매일 00:10 KST: 7일차 중간 리셋 체크."""
    try:
        from services import ranked_service as rs
        from database import ranked_queries as rq

        season = await rq.get_current_season()
        if not season:
            return

        # 시즌 시작 후 경과 일수 계산
        starts_at = season["starts_at"]
        if starts_at.tzinfo is None:
            starts_at = starts_at.replace(tzinfo=config.KST)
        now = config.get_kst_now()
        days_elapsed = (now - starts_at).days

        # 7일차에만 중간 리셋 실행
        if days_elapsed == 7 and not season.get("mid_reset_done", False):
            reset_count = await rs.process_mid_season_reset(season)
            logger.info(f"Mid-season reset: {reset_count} users reset in {season['season_id']}")

            # DM 알림 (배치 완료 유저)
            records = await rq.get_all_placed_records(season["season_id"])
            for rec in records:
                try:
                    div_info = config.get_division_info(rec["rp"])
                    tier_disp = config.tier_division_display(
                        div_info[0], div_info[1], div_info[2],
                        placement_done=True, total_rp=rec["rp"])
                    await context.bot.send_message(
                        chat_id=rec["user_id"],
                        text=(
                            f"⚡ 중간 리셋!\n"
                            f"RP가 60%로 조정되었습니다.\n"
                            f"현재: {tier_disp}\n"
                            f"연승이 초기화되었습니다."
                        ),
                        parse_mode="HTML",
                    )
                except Exception:
                    pass
                await asyncio.sleep(0.05)
    except Exception as e:
        logger.error(f"Mid-season check job failed: {e}")


async def ranked_decay_job(context):
    """매일 00:15 KST: 마스터+ 디케이 처리."""
    try:
        from services import ranked_service as rs
        from database import ranked_queries as rq

        season = await rq.get_current_season()
        if not season:
            return

        results = await rs.process_ranked_decay(season["season_id"])

        # 디케이된 유저에게 DM 알림
        for r in results:
            try:
                decay_amount = r["rp_before"] - r["rp_after"]
                div_info = config.get_division_info(r["rp_after"])
                tier_disp = config.tier_division_display(
                    div_info[0], div_info[1], div_info[2],
                    placement_done=True, total_rp=r["rp_after"])
                await context.bot.send_message(
                    chat_id=r["user_id"],
                    text=(
                        f"⏰ 디케이 알림!\n"
                        f"RP -{decay_amount} ({r['rp_before']} → {r['rp_after']})\n"
                        f"현재: {tier_disp}\n"
                        f"랭크전으로 디케이를 막으세요!"
                    ),
                    parse_mode="HTML",
                )
            except Exception:
                pass
    except Exception as e:
        logger.error(f"Ranked decay job failed: {e}")
