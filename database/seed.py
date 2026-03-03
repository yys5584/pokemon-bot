"""Seed the pokemon_master table with 251 Gen1+Gen2 Pokemon."""

from database.connection import get_db
from models.pokemon_data import ALL_POKEMON


async def seed_pokemon_data():
    """Insert all 251 Pokemon into pokemon_master if not already seeded."""
    pool = await get_db()

    row = await pool.fetchrow("SELECT COUNT(*) as cnt FROM pokemon_master")
    count = row["cnt"] if row else 0
    if count >= 251:
        return count

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

    return 251


async def seed_battle_data():
    """Seed pokemon_type and stat_type into pokemon_master for battle system."""
    from models.pokemon_battle_data import POKEMON_BATTLE_DATA

    pool = await get_db()

    # Check if already seeded (if any pokemon has a non-default type)
    row = await pool.fetchrow(
        "SELECT COUNT(*) as cnt FROM pokemon_master WHERE pokemon_type != 'normal'"
    )
    if row and row["cnt"] > 50:
        return  # Already seeded

    for pid, (ptype, stype) in POKEMON_BATTLE_DATA.items():
        await pool.execute(
            """UPDATE pokemon_master
               SET pokemon_type = $1, stat_type = $2
               WHERE id = $3""",
            ptype, stype, pid,
        )


async def migrate_18_types():
    """Migrate from old 10-type to 18-type system.

    Checks for 18-type-only types (fairy, bug, rock, steel, ground, ice).
    If none found, forces a full re-seed of types from POKEMON_BATTLE_DATA.
    """
    from models.pokemon_battle_data import POKEMON_BATTLE_DATA

    pool = await get_db()

    # Check if 18-type migration already applied
    row = await pool.fetchrow(
        "SELECT COUNT(*) as cnt FROM pokemon_master "
        "WHERE pokemon_type IN ('fairy','bug','rock','steel','ground','ice')"
    )
    if row and row["cnt"] > 0:
        return False  # Already migrated

    updated = 0
    for pid, (ptype, stype) in POKEMON_BATTLE_DATA.items():
        await pool.execute(
            """UPDATE pokemon_master
               SET pokemon_type = $1, stat_type = $2
               WHERE id = $3""",
            ptype, stype, pid,
        )
        updated += 1

    return updated
