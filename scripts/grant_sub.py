"""관리자에게 channel_owner 구독 부여."""
import asyncio
import os
import asyncpg
from dotenv import load_dotenv
load_dotenv()

async def main():
    conn = await asyncpg.connect(dsn=os.getenv("DATABASE_URL"), statement_cache_size=0)
    pay_row = await conn.fetchrow(
        "INSERT INTO subscription_payments (user_id, tier, amount_raw, amount_usd, token, status, expires_at) "
        "VALUES (1832746512, 'channel_owner', 0, 0, 'ADMIN_GRANT', 'confirmed', NOW() + INTERVAL '1 year') "
        "RETURNING id"
    )
    payment_id = pay_row["id"]
    await conn.execute(
        "UPDATE subscriptions SET is_active = 0 WHERE user_id = 1832746512 AND is_active = 1"
    )
    row = await conn.fetchrow(
        "INSERT INTO subscriptions (user_id, tier, expires_at, payment_id) "
        "VALUES (1832746512, 'channel_owner', NOW() + INTERVAL '1 year', $1) "
        "RETURNING id, tier, expires_at",
        payment_id,
    )
    print(f"Created: id={row['id']}, tier={row['tier']}, expires={row['expires_at']}")
    await conn.close()

asyncio.run(main())
