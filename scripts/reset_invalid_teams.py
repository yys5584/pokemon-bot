"""Reset all battle teams that exceed COST 18 or have less than 6 members."""
import asyncio
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from database.connection import get_db

RANKED_COST = {
    "common": 1,
    "rare": 2,
    "epic": 4,
    "legendary": 5,
    "ultra_legendary": 6,
}
COST_LIMIT = 18
TEAM_SIZE = 6


async def main():
    pool = await get_db()

    # Get all teams grouped by (user_id, team_number) with rarity info
    rows = await pool.fetch("""
        SELECT bt.user_id, bt.team_number, bt.slot, bt.pokemon_instance_id,
               pm.rarity, pm.name_ko, u.display_name
        FROM battle_teams bt
        JOIN user_pokemon up ON bt.pokemon_instance_id = up.id
        JOIN pokemon_master pm ON up.pokemon_id = pm.id
        JOIN users u ON bt.user_id = u.user_id
        WHERE up.is_active = 1
        ORDER BY bt.user_id, bt.team_number, bt.slot
    """)

    # Group by (user_id, team_number)
    teams: dict[tuple[int, int], list[dict]] = {}
    for r in rows:
        key = (r["user_id"], r["team_number"])
        teams.setdefault(key, []).append(dict(r))

    invalid_teams = []
    for (uid, tn), members in teams.items():
        total_cost = sum(RANKED_COST.get(m["rarity"], 0) for m in members)
        member_count = len(members)
        reasons = []
        if total_cost > COST_LIMIT:
            reasons.append(f"COST {total_cost}/{COST_LIMIT}")
        if member_count < TEAM_SIZE:
            reasons.append(f"{member_count}/{TEAM_SIZE}마리")
        if reasons:
            display = members[0]["display_name"]
            pokemon_names = [f"{m['name_ko']}({m['rarity']})" for m in members]
            invalid_teams.append((uid, tn, display, reasons, pokemon_names, total_cost, member_count))

    if not invalid_teams:
        print("✅ 모든 팀이 정상입니다. 초기화할 팀 없음.")
        return

    print(f"⚠️ 규정 위반 팀 {len(invalid_teams)}개 발견:\n")
    for uid, tn, display, reasons, pokemon_names, cost, count in invalid_teams:
        reason_str = ", ".join(reasons)
        print(f"  [{display}] (uid={uid}) 팀{tn}: {reason_str}")
        print(f"    COST={cost}, 인원={count}, 멤버: {', '.join(pokemon_names)}")

    print(f"\n🔄 {len(invalid_teams)}개 팀 초기화 중...")

    deleted_count = 0
    for uid, tn, display, reasons, pokemon_names, cost, count in invalid_teams:
        result = await pool.execute(
            "DELETE FROM battle_teams WHERE user_id = $1 AND team_number = $2",
            uid, tn,
        )
        deleted_count += 1
        print(f"  ❌ [{display}] 팀{tn} 초기화 완료")

    print(f"\n✅ 총 {deleted_count}개 팀 초기화 완료!")


if __name__ == "__main__":
    asyncio.run(main())
