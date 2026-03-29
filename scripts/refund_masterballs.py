"""Refund master balls to users who lost them in competition."""
import asyncio, asyncpg, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

REFUNDS = {
    7871330013: 1,   # oneday
    1668479932: 1,   # LastMoney
    7050637391: 2,   # 러스트
    6862139153: 1,   # 살려주세요
    8176389709: 2,   # Revuildio
    5823114689: 1,   # Odung2
    1393882896: 3,   # 차가운도쿄
    53720317: 1,     # 크립토비밥
    5223501384: 1,   # Woony|우니
    7165778687: 1,   # Naroo
    1686589353: 2,   # Ho_it
    5255556421: 1,   # 젬하
}

async def refund():
    pool = await asyncpg.create_pool(
        os.getenv("DATABASE_URL"),
        statement_cache_size=0,
    )

    for user_id, count in REFUNDS.items():
        before = await pool.fetchval(
            "SELECT master_balls FROM users WHERE user_id = $1", user_id
        )
        await pool.execute(
            "UPDATE users SET master_balls = master_balls + $1 WHERE user_id = $2",
            count, user_id,
        )
        after = await pool.fetchval(
            "SELECT master_balls FROM users WHERE user_id = $1", user_id
        )
        name = await pool.fetchval(
            "SELECT display_name FROM users WHERE user_id = $1", user_id
        )
        print(f"  {name} (id:{user_id}): +{count} 마볼 ({before} -> {after})")

    total = sum(REFUNDS.values())
    print(f"\n완료: {len(REFUNDS)}명에게 총 {total}개 마볼 지급")
    await pool.close()

asyncio.run(refund())
