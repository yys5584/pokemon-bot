"""Seed the pokemon_master table with 386 Gen1+Gen2+Gen3 Pokemon."""

from database.connection import get_db
from models.pokemon_data import ALL_POKEMON


async def seed_pokemon_data():
    """Insert all 386 Pokemon into pokemon_master if not already seeded."""
    pool = await get_db()

    row = await pool.fetchrow("SELECT COUNT(*) as cnt FROM pokemon_master")
    count = row["cnt"] if row else 0
    if count >= 386:
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

    return 386


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

    batch_args = [(ptype, stype, pid) for pid, (ptype, stype) in POKEMON_BATTLE_DATA.items()]
    if batch_args:
        await pool.executemany(
            """UPDATE pokemon_master
               SET pokemon_type = $1, stat_type = $2
               WHERE id = $3""",
            batch_args,
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

    batch_args = [(ptype, stype, pid) for pid, (ptype, stype) in POKEMON_BATTLE_DATA.items()]
    if batch_args:
        await pool.executemany(
            """UPDATE pokemon_master
               SET pokemon_type = $1, stat_type = $2
               WHERE id = $3""",
            batch_args,
        )

    return len(batch_args)


async def migrate_assign_ivs():
    """Assign random IVs to all existing Pokemon that have iv_hp IS NULL.

    Shiny Pokemon get minimum IV of 10 (same rule as new catches).
    Normal Pokemon get 0-31 random.
    Runs once — skips if no NULL IVs remain.

    Returns number of updated Pokemon, or False if already done.
    """
    import random
    import config

    pool = await get_db()

    # Check how many Pokemon still need IVs
    row = await pool.fetchrow(
        "SELECT COUNT(*) as cnt FROM user_pokemon WHERE iv_hp IS NULL AND is_active = 1"
    )
    need_count = row["cnt"] if row else 0
    if need_count == 0:
        return False  # All Pokemon already have IVs

    # Fetch all Pokemon that need IVs (id + is_shiny)
    rows = await pool.fetch(
        "SELECT id, is_shiny FROM user_pokemon WHERE iv_hp IS NULL"
    )

    # Build batch args for executemany (much faster than individual queries)
    batch_args = []
    for r in rows:
        is_shiny = bool(r["is_shiny"])
        low = config.IV_SHINY_MIN if is_shiny else config.IV_MIN
        high = config.IV_MAX
        batch_args.append((
            random.randint(low, high),  # hp
            random.randint(low, high),  # atk
            random.randint(low, high),  # def
            random.randint(low, high),  # spa
            random.randint(low, high),  # spdef
            random.randint(low, high),  # spd
            r["id"],
        ))

    if batch_args:
        await pool.executemany(
            """UPDATE user_pokemon
               SET iv_hp = $1, iv_atk = $2, iv_def = $3,
                   iv_spa = $4, iv_spdef = $5, iv_spd = $6
               WHERE id = $7""",
            batch_args,
        )

    return len(batch_args)


async def migrate_rarity_v2():
    """Migrate rarity based on base stat totals (종족값).

    Rules: <400=common, 400-499=rare, >=500=epic, legendary=unchanged.
    Also updates catch_rate to match new rarity.
    Runs once — checks if Arcanine (ID 59) is already epic.
    """
    pool = await get_db()

    # Check if already migrated (Arcanine should be epic, was rare)
    row = await pool.fetchrow(
        "SELECT rarity FROM pokemon_master WHERE id = 59"
    )
    if row and row["rarity"] == "epic":
        return False  # Already migrated

    # Build rarity+catch_rate from ALL_POKEMON (source of truth)
    batch_args = []
    for p in ALL_POKEMON:
        pid, rarity, catch_rate = p[0], p[4], p[5]
        batch_args.append((rarity, catch_rate, pid))

    if batch_args:
        await pool.executemany(
            """UPDATE pokemon_master
               SET rarity = $1, catch_rate = $2
               WHERE id = $3""",
            batch_args,
        )

    return len(batch_args)


async def migrate_ultra_legendary():
    """Promote BST680 pokemon (Mewtwo, Lugia, Ho-Oh) to ultra_legendary.

    user_pokemon reads rarity via JOIN to pokemon_master, so only
    pokemon_master needs updating.
    """
    pool = await get_db()

    # Check if already migrated
    row = await pool.fetchrow(
        "SELECT rarity FROM pokemon_master WHERE id = 150"
    )
    if row and row["rarity"] == "ultra_legendary":
        return False  # Already migrated

    await pool.execute(
        "UPDATE pokemon_master SET rarity = 'ultra_legendary' WHERE id IN (150, 249, 250)"
    )
    return 3


async def migrate_catch_rates_v3():
    """Unify catch_rate per rarity tier.

    common=0.80, rare=0.50, epic=0.15, legendary=0.05, ultra_legendary=0.03
    Runs once — checks if Bulbasaur (ID 1, common) catch_rate is already 0.80.
    """
    pool = await get_db()

    row = await pool.fetchrow(
        "SELECT catch_rate FROM pokemon_master WHERE id = 1"
    )
    if row and abs(float(row["catch_rate"]) - 0.80) < 0.001:
        return False  # Already migrated

    rate_map = {
        "common": 0.80,
        "rare": 0.50,
        "epic": 0.15,
        "legendary": 0.05,
        "ultra_legendary": 0.03,
    }

    for rarity, rate in rate_map.items():
        await pool.execute(
            "UPDATE pokemon_master SET catch_rate = $1 WHERE rarity = $2",
            rate, rarity,
        )

    total = await pool.fetchval("SELECT count(*) FROM pokemon_master")
    return total


async def migrate_add_nurture_locked():
    """Add nurture_locked column to user_pokemon.

    교환으로 받은 진화 포켓몬의 친밀도 강화를 차단하기 위한 플래그.
    """
    pool = await get_db()

    # 컬럼 존재 여부 확인
    exists = await pool.fetchval("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'user_pokemon' AND column_name = 'nurture_locked'
    """)
    if exists:
        return False  # Already migrated

    await pool.execute("""
        ALTER TABLE user_pokemon
        ADD COLUMN nurture_locked BOOLEAN NOT NULL DEFAULT FALSE
    """)
    return True


async def migrate_trade_evo_fix():
    """Fix trade evolution routes for cross-gen Pokemon.

    롱스톤→강철톤, 시드라→킹드라, 스라크→핫삼, 폴리곤→폴리곤2
    evolves_to / evolution_method 가 누락되어 진화 불가였던 버그 수정.
    """
    from database.schema import TRADE_EVO_FIX_MIGRATIONS

    pool = await get_db()

    # 이미 적용됐는지 확인 (시드라의 evolves_to가 230이면 완료)
    row = await pool.fetchrow(
        "SELECT evolves_to FROM pokemon_master WHERE id = 117"
    )
    if row and row["evolves_to"] == 230:
        return False  # Already migrated

    for sql in TRADE_EVO_FIX_MIGRATIONS:
        await pool.execute(sql)

    return True
