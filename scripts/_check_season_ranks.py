import asyncio, asyncpg, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

async def main():
    conn = await asyncpg.connect(os.getenv("DATABASE_URL"), statement_cache_size=0)

    rows = await conn.fetch("""
        SELECT sr.user_id, u.display_name,
               MAX(CASE WHEN sr.season_id = '2026-S01' THEN sr.peak_rp ELSE 0 END) as s01_peak,
               MAX(CASE WHEN sr.season_id = '2026-S01' THEN sr.tier END) as s01_tier,
               MAX(CASE WHEN sr.season_id = '2026-S01' THEN sr.ranked_wins ELSE 0 END) as s01_w,
               MAX(CASE WHEN sr.season_id = '2026-S01' THEN sr.ranked_losses ELSE 0 END) as s01_l,
               MAX(CASE WHEN sr.season_id = '2026-S01.5' THEN sr.peak_rp ELSE 0 END) as s15_peak,
               MAX(CASE WHEN sr.season_id = '2026-S01.5' THEN sr.tier END) as s15_tier,
               MAX(CASE WHEN sr.season_id = '2026-S01.5' THEN sr.ranked_wins ELSE 0 END) as s15_w,
               MAX(CASE WHEN sr.season_id = '2026-S01.5' THEN sr.ranked_losses ELSE 0 END) as s15_l,
               GREATEST(
                   MAX(CASE WHEN sr.season_id = '2026-S01' THEN sr.peak_rp ELSE 0 END),
                   MAX(CASE WHEN sr.season_id = '2026-S01.5' THEN sr.peak_rp ELSE 0 END)
               ) as best_peak
        FROM season_records sr
        JOIN users u ON sr.user_id = u.user_id
        WHERE sr.season_id IN ('2026-S01', '2026-S01.5')
        GROUP BY sr.user_id, u.display_name
        ORDER BY best_peak DESC
    """)

    print(f"{'#':>2} {'이름':20s} {'S01피크':>8} {'S01티어':>12} {'S01전적':>8} {'S1.5피크':>8} {'S1.5티어':>12} {'S1.5전적':>8} {'최고':>6}")
    print("-" * 110)
    for i, r in enumerate(rows):
        s01_wl = f"{r['s01_w']}W{r['s01_l']}L" if r['s01_w'] or r['s01_l'] else "-"
        s15_wl = f"{r['s15_w']}W{r['s15_l']}L" if r['s15_w'] or r['s15_l'] else "-"
        s01_t = r['s01_tier'] or "-"
        s15_t = r['s15_tier'] or "-"
        print(f"{i+1:>2} {r['display_name']:20s} {r['s01_peak']:>8} {s01_t:>12} {s01_wl:>8} {r['s15_peak']:>8} {s15_t:>12} {s15_wl:>8} {r['best_peak']:>6}")

    await conn.close()

asyncio.run(main())
