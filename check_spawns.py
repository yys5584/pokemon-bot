"""Quick DB check for spawn debugging."""
import sqlite3

db = sqlite3.connect("data/pokemon_bot.db")
db.row_factory = sqlite3.Row

print("=== Chat Rooms ===")
for r in db.execute("SELECT * FROM chat_rooms"):
    print(dict(r))

print("\n=== Recent Spawns (last 20) ===")
for r in db.execute(
    "SELECT id, chat_id, pokemon_id, is_resolved, expires_at, spawned_at FROM spawn_sessions ORDER BY id DESC LIMIT 20"
):
    print(dict(r))

print("\n=== Spawns in last 2 hours ===")
for r in db.execute(
    "SELECT chat_id, COUNT(*) as cnt FROM spawn_sessions WHERE spawned_at > datetime('now', '-2 hours') GROUP BY chat_id"
):
    print(dict(r))

print("\n=== Unresolved spawns ===")
for r in db.execute("SELECT * FROM spawn_sessions WHERE is_resolved = 0"):
    print(dict(r))

db.close()
