"""Fix shiny Entei (id=13985) IVs — re-roll with shiny minimum 10."""
import asyncio
import asyncpg
import os
import random
from dotenv import load_dotenv

load_dotenv()

async def main():
    conn = await asyncpg.connect(os.getenv("DATABASE_URL"), statement_cache_size=0)

    # Check current IVs
    row = await conn.fetchrow(
        "SELECT iv_hp, iv_atk, iv_def, iv_spa, iv_spdef, iv_spd FROM user_pokemon WHERE id = 13985"
    )
    print(f"Before: HP={row[0]} ATK={row[1]} DEF={row[2]} SPA={row[3]} SPDEF={row[4]} SPD={row[5]} (total={sum(row)}/186)")

    # Re-roll with shiny minimum (10~31)
    low, high = 10, 31
    ivs = [random.randint(low, high) for _ in range(6)]

    await conn.execute(
        "UPDATE user_pokemon SET iv_hp=$1, iv_atk=$2, iv_def=$3, iv_spa=$4, iv_spdef=$5, iv_spd=$6 WHERE id=13985",
        *ivs,
    )

    # Verify
    row2 = await conn.fetchrow(
        "SELECT iv_hp, iv_atk, iv_def, iv_spa, iv_spdef, iv_spd FROM user_pokemon WHERE id = 13985"
    )
    print(f"After:  HP={row2[0]} ATK={row2[1]} DEF={row2[2]} SPA={row2[3]} SPDEF={row2[4]} SPD={row2[5]} (total={sum(row2)}/186)")
    await conn.close()

asyncio.run(main())
