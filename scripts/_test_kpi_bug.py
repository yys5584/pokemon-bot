import asyncio
async def test():
    from database.connection import get_db
    import config
    pool = await get_db()
    today = config.get_kst_now().replace(hour=0, minute=0, second=0, microsecond=0)
    print(f"today={today} type={type(today)}")

    # Test the exact churned_users query
    try:
        rows = await pool.fetch(
            """SELECT u.user_id, u.display_name
               FROM users u
               WHERE u.last_active_at >= $1 - INTERVAL '7 days'
               LIMIT 1""",
            today,
        )
        print(f"Simple query OK: {len(rows)} rows")
    except Exception as e:
        print(f"Simple query FAILED: {e}")

    # Check column type
    col = await pool.fetchrow(
        "SELECT data_type FROM information_schema.columns WHERE table_name='users' AND column_name='last_active_at'"
    )
    print(f"last_active_at type: {col['data_type'] if col else 'not found'}")

    # Full churned query
    try:
        from database.kpi_queries import report_churned_users
        r = await report_churned_users(today)
        print(f"report_churned_users OK: {len(r)}")
    except Exception as e:
        import traceback
        traceback.print_exc()

asyncio.run(test())
