import asyncio
import asyncpg
import os

async def main():
    DATABASE_URL = os.environ.get("DATABASE_URL")
    if not DATABASE_URL:
        with open(".env") as f:
            for line in f:
                if line.startswith("DATABASE_URL="):
                    DATABASE_URL = line.strip().split("=", 1)[1].strip('"').strip("'")
                    break

    conn = await asyncpg.connect(DATABASE_URL, statement_cache_size=0)

    # battle_records columns
    br_cols = await conn.fetch("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='battle_records' ORDER BY ordinal_position")
    print("battle_records columns:")
    for c in br_cols:
        print(f"  {c['column_name']:30s} {c['data_type']}")

    # Latest 5 ranked battles
    sample = await conn.fetch("""
        SELECT rbl.id, rbl.season_id, rbl.winner_rp_before, rbl.winner_rp_after,
               rbl.loser_rp_before, rbl.loser_rp_after,
               rbl.winner_tier_before, rbl.winner_tier_after,
               rbl.loser_tier_before, rbl.loser_tier_after,
               rbl.winner_mmr_before, rbl.winner_mmr_after,
               rbl.loser_mmr_before, rbl.loser_mmr_after,
               rbl.created_at,
               br.winner_id, br.loser_id
        FROM ranked_battle_log rbl
        JOIN battle_records br ON rbl.battle_record_id = br.id
        ORDER BY rbl.created_at DESC LIMIT 5
    """)
    print("\n=== Latest 5 ranked battles ===")
    for r in sample:
        print(f"  {dict(r)}")

    # season_daily_conditions columns
    sdc_cols = await conn.fetch("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='season_daily_conditions' ORDER BY ordinal_position")
    print(f"\nseason_daily_conditions columns:")
    for c in sdc_cols:
        print(f"  {c['column_name']:30s} {c['data_type']}")

    # current season S02 stats
    s02 = await conn.fetch("""
        SELECT sr.*, u.display_name FROM season_records sr
        JOIN users u ON sr.user_id = u.user_id
        WHERE sr.season_id = '2026-S02'
        ORDER BY sr.rp DESC
    """)
    print(f"\n=== Current Season 2026-S02 Rankings ===")
    for r in s02:
        print(f"  {r['display_name']:20s} RP={r['rp']} tier={r['tier']} W={r['ranked_wins']} L={r['ranked_losses']} streak={r['ranked_streak']} best_streak={r['best_ranked_streak']} peak_rp={r['peak_rp']}")

    # battles per season
    per_season = await conn.fetch("SELECT season_id, COUNT(*) as cnt FROM ranked_battle_log GROUP BY season_id ORDER BY season_id")
    print(f"\n=== Battles per season ===")
    for r in per_season:
        print(f"  {r['season_id']:15s} {r['cnt']} battles")

    # S06 check (odd season id)
    s06 = await conn.fetch("SELECT * FROM ranked_battle_log WHERE season_id = '2026-S06' LIMIT 3")
    print(f"\n=== S06 sample (if any) ===")
    for r in s06:
        print(f"  {dict(r)}")

    await conn.close()

asyncio.run(main())
