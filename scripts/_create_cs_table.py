import asyncio, asyncpg, os
from dotenv import load_dotenv
load_dotenv()

async def main():
    conn = await asyncpg.connect(os.getenv("DATABASE_URL"), statement_cache_size=0)

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS cs_inquiries (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            display_name TEXT,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            admin_reply TEXT,
            replied_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            image_filename TEXT,
            is_public BOOLEAN NOT NULL DEFAULT TRUE,
            like_count INTEGER NOT NULL DEFAULT 0
        )
    """)
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_cs_inquiries_user ON cs_inquiries(user_id)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_cs_inquiries_status ON cs_inquiries(status)")
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS cs_likes (
            user_id BIGINT NOT NULL,
            inquiry_id INTEGER NOT NULL REFERENCES cs_inquiries(id),
            PRIMARY KEY (user_id, inquiry_id)
        )
    """)
    print("done")
    await conn.close()

asyncio.run(main())
