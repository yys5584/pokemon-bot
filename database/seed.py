"""Seed the pokemon_master table with 251 Gen1+Gen2 Pokemon."""

from database.connection import get_db
from models.pokemon_data import ALL_POKEMON


async def seed_pokemon_data():
    """Insert all 251 Pokemon into pokemon_master if not already seeded."""
    db = await get_db()

    row = await db.execute_fetchall("SELECT COUNT(*) as cnt FROM pokemon_master")
    count = row[0][0] if row else 0
    if count >= 251:
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

    # Update Gen1 Pokemon that now evolve into Gen2
    cross_gen_updates = [
        # Golbat -> Crobat
        ("UPDATE pokemon_master SET evolves_to = 169 WHERE id = 42 AND evolves_to IS NULL",),
        # Chansey -> Blissey
        ("UPDATE pokemon_master SET evolves_to = 242 WHERE id = 113 AND evolves_to IS NULL",),
    ]
    for sql in cross_gen_updates:
        await db.execute(sql[0])

    await db.commit()

    # Re-enable foreign keys
    await db.execute("PRAGMA foreign_keys=ON")
