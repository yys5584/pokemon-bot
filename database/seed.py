"""Seed the pokemon_master table with 251 Gen1+Gen2 Pokemon."""

from database.connection import get_db
from models.pokemon_data import ALL_POKEMON


async def seed_pokemon_data():
    """Insert all 251 Pokemon into pokemon_master if not already seeded."""
    pool = await get_db()

    row = await pool.fetchrow("SELECT COUNT(*) as cnt FROM pokemon_master")
    count = row["cnt"] if row else 0
    if count >= 251:
        return  # Already seeded

    for p in ALL_POKEMON:
        await pool.execute(
            """INSERT INTO pokemon_master
               (id, name_ko, name_en, emoji, rarity, catch_rate,
                evolves_from, evolves_to, evolution_method)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
               ON CONFLICT (id) DO NOTHING""",
            *p,
        )

    # Update Gen1 Pokemon that now evolve into Gen2
    await pool.execute(
        "UPDATE pokemon_master SET evolves_to = 169 WHERE id = 42 AND evolves_to IS NULL"
    )
    await pool.execute(
        "UPDATE pokemon_master SET evolves_to = 242 WHERE id = 113 AND evolves_to IS NULL"
    )
