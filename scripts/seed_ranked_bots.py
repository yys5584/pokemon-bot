"""NPC 봇 초기 시딩 스크립트.

현재 시즌에 대해 모든 봇을 생성하고 팀을 구성한다.
이후 시즌 전환 시에는 ensure_current_season()에서 자동 시딩됨.

Usage:
    cd ~/pokemon-bot
    python scripts/seed_ranked_bots.py
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import config
from database.connection import get_db
from services.ranked_service import ensure_current_season
from services.bot_team_builder import seed_bots_for_season


async def main():
    pool = await get_db()

    # is_bot 컬럼 추가 (없으면)
    try:
        await pool.execute(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_bot BOOLEAN NOT NULL DEFAULT FALSE")
        print("✅ is_bot 컬럼 확인/추가 완료")
    except Exception as e:
        print(f"is_bot 컬럼: {e}")

    # 현재 시즌 확인/생성
    season = await ensure_current_season()
    season_id = season["season_id"]
    weekly_rule = season["weekly_rule"]
    rule_info = config.WEEKLY_RULES.get(weekly_rule, {})
    cost_limit = rule_info.get("cost_limit", config.RANKED_COST_LIMIT)

    print(f"\n시즌: {season_id}")
    print(f"룰: {weekly_rule} (코스트 제한: {cost_limit})")
    print(f"봇 수: {len(config.RANKED_BOTS)}명")
    print()

    # 봇 시딩
    await seed_bots_for_season(season_id, weekly_rule)

    # 결과 확인
    print("\n=== 시딩 결과 ===")
    for bot_def in config.RANKED_BOTS:
        uid = bot_def[0]
        name = bot_def[1]
        tier = bot_def[2]

        team = await pool.fetch(
            """SELECT bt.slot, pm.name_ko, pm.rarity, up.is_shiny,
                      up.iv_hp + up.iv_atk + up.iv_def + up.iv_spa + up.iv_spdef + up.iv_spd as total_iv
               FROM battle_teams bt
               JOIN user_pokemon up ON bt.pokemon_instance_id = up.id
               JOIN pokemon_master pm ON up.pokemon_id = pm.id
               WHERE bt.user_id = $1 AND bt.team_number = 1
               ORDER BY bt.slot""", uid)

        if not team:
            print(f"❌ {name} ({tier}) — 팀 없음!")
            continue

        total_cost = sum(config.RANKED_COST.get(t["rarity"], 1) for t in team)
        members = ", ".join(
            f"{t['name_ko']}({'✨' if t['is_shiny'] else ''}{t['rarity'][:3]})"
            for t in team)
        print(f"{'✅' if total_cost <= cost_limit else '❌'} {name} ({tier}) "
              f"cost={total_cost}/{cost_limit} | {members}")


if __name__ == "__main__":
    asyncio.run(main())
