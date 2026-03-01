"""Seed the pokemon_master table with 151 Gen1 Pokemon."""

from database.connection import get_db
from models.pokemon_data import ALL_POKEMON


async def seed_pokemon_data():
    """Insert all 151 Pokemon into pokemon_master if not already seeded."""
    db = await get_db()

    row = await db.execute_fetchall("SELECT COUNT(*) as cnt FROM pokemon_master")
    count = row[0][0] if row else 0
    if count >= 151:
        return  # Already seeded

    # Temporarily disable foreign keys for self-referential insert
    await db.execute("PRAGMA foreign_keys=OFF")

    for p in ALL_POKEMON:
        await db.execute(
            """INSERT OR IGNORE INTO pokemon_master
               (id, name_ko, name_en, emoji, rarity, catch_rate,
                evolves_from, evolves_to, evolution_method)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            p,
        )
    await db.commit()

    # Re-enable foreign keys
    await db.execute("PRAGMA foreign_keys=ON")
