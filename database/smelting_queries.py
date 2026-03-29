"""이로치 제련소 DB 쿼리."""

from database.connection import get_db
import json


async def get_smelting_gauge(user_id: int) -> dict:
    """유저의 현재 제련 게이지 조회. 없으면 기본값 반환."""
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT gauge, highest_rarity, rarity_contributions FROM smelting_gauge WHERE user_id = $1",
        user_id,
    )
    if row:
        contribs = row["rarity_contributions"]
        if isinstance(contribs, str):
            contribs = json.loads(contribs)
        return {
            "gauge": float(row["gauge"]),
            "highest_rarity": row["highest_rarity"],
            "rarity_contributions": contribs or {},
        }
    return {"gauge": 0.0, "highest_rarity": "common", "rarity_contributions": {}}


async def update_smelting_gauge(
    user_id: int, gauge: float, highest_rarity: str, contributions: dict
):
    """게이지 업데이트 (upsert)."""
    pool = await get_db()
    await pool.execute(
        """INSERT INTO smelting_gauge (user_id, gauge, highest_rarity, rarity_contributions, updated_at)
           VALUES ($1, $2, $3, $4::jsonb, NOW())
           ON CONFLICT (user_id) DO UPDATE
           SET gauge = $2, highest_rarity = $3, rarity_contributions = $4::jsonb, updated_at = NOW()""",
        user_id, gauge, highest_rarity, json.dumps(contributions),
    )


async def reset_smelting_gauge(user_id: int):
    """게이지 0% 리셋 (대성공/메가스톤 획득 시)."""
    pool = await get_db()
    await pool.execute(
        """UPDATE smelting_gauge
           SET gauge = 0, highest_rarity = 'common', rarity_contributions = '{}', updated_at = NOW()
           WHERE user_id = $1""",
        user_id,
    )


async def log_smelting(
    user_id: int,
    materials: dict,
    gauge_before: float,
    gauge_after: float,
    result: str,
    result_detail: dict | None = None,
    reward_detail: dict | None = None,
):
    """제련 기록 저장."""
    pool = await get_db()
    await pool.execute(
        """INSERT INTO smelting_log (user_id, materials, gauge_before, gauge_after, result, result_detail, reward_detail)
           VALUES ($1, $2::jsonb, $3, $4, $5, $6::jsonb, $7::jsonb)""",
        user_id,
        json.dumps(materials),
        gauge_before,
        gauge_after,
        result,
        json.dumps(result_detail) if result_detail else None,
        json.dumps(reward_detail) if reward_detail else None,
    )
