"""16일자 일일 리포트를 수동 생성해서 관리자 DM으로 발송."""
import asyncio
import os
import sys
import io

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from database.connection import get_db, close_db
from database import queries
from datetime import datetime, timedelta, timezone


KST = timezone(timedelta(hours=9))
TARGET_DATE = datetime(2026, 3, 16, 0, 0, 0, tzinfo=KST)
ADMIN_ID = 1832746512


async def main():
    pool = await get_db()

    # 16일자 기준 데이터 수집
    today = TARGET_DATE
    one_hour_before_midnight = today.replace(hour=23, minute=55)

    print("Collecting data for 2026-03-16...")

    # 기본 KPI
    dau_row = await pool.fetchrow(
        "SELECT COUNT(DISTINCT user_id) as cnt FROM catch_attempts WHERE attempted_at >= $1 AND attempted_at < $1 + INTERVAL '1 day'",
        today)
    new_row = await pool.fetchrow(
        "SELECT COUNT(*) as cnt FROM users WHERE registered_at >= $1 AND registered_at < $1 + INTERVAL '1 day'",
        today)
    total_users_row = await pool.fetchrow("SELECT COUNT(*) as cnt FROM users")
    spawn_row = await pool.fetchrow(
        """SELECT COUNT(*) as spawns, COUNT(caught_by_user_id) as catches
           FROM spawn_log WHERE spawned_at >= $1 AND spawned_at < $1 + INTERVAL '1 day'""",
        today)
    shiny_row = await pool.fetchrow(
        """SELECT COUNT(*) as cnt FROM spawn_log
           WHERE spawned_at >= $1 AND spawned_at < $1 + INTERVAL '1 day'
             AND is_shiny = 1 AND caught_by_user_id IS NOT NULL""",
        today)
    mb_row = await pool.fetchrow(
        "SELECT COUNT(*) as cnt FROM catch_attempts WHERE used_master_ball = 1 AND attempted_at >= $1 AND attempted_at < $1 + INTERVAL '1 day'",
        today)
    battle_row = await pool.fetchrow(
        "SELECT COUNT(*) as cnt FROM battle_records WHERE created_at >= $1 AND created_at < $1 + INTERVAL '1 day'",
        today)
    ranked_row = await pool.fetchrow(
        """SELECT COUNT(*) as cnt FROM battle_records
           WHERE created_at >= $1 AND created_at < $1 + INTERVAL '1 day' AND bp_earned > 0""",
        today)
    bp_row = await pool.fetchrow(
        "SELECT COALESCE(SUM(amount), 0) as total FROM bp_log WHERE amount > 0 AND created_at >= $1 AND created_at < $1 + INTERVAL '1 day'",
        today)
    market_new_row = await pool.fetchrow(
        "SELECT COUNT(*) as cnt FROM market_listings WHERE created_at >= $1 AND created_at < $1 + INTERVAL '1 day'",
        today)
    market_sold_row = await pool.fetchrow(
        "SELECT COUNT(*) as cnt FROM market_listings WHERE sold_at >= $1 AND sold_at < $1 + INTERVAL '1 day' AND status = 'sold'",
        today)
    sub_active_row = await pool.fetchrow("SELECT COUNT(*) as cnt FROM subscriptions WHERE is_active = 1")
    bp_spent_row = await pool.fetchrow(
        "SELECT COALESCE(SUM(ABS(amount)), 0) as total FROM bp_log WHERE amount < 0 AND created_at >= $1 AND created_at < $1 + INTERVAL '1 day'",
        today)

    dau = dau_row["cnt"] if dau_row else 0
    spawns = spawn_row["spawns"] if spawn_row else 0
    catches = spawn_row["catches"] if spawn_row else 0
    catch_rate = round(catches / spawns * 100, 1) if spawns > 0 else 0
    shiny_caught = shiny_row["cnt"] if shiny_row else 0
    battles = battle_row["cnt"] if battle_row else 0
    bp_earned = int(bp_row["total"]) if bp_row else 0
    bp_total_spent = int(bp_spent_row["total"]) if bp_spent_row else 0
    bp_net = bp_earned - bp_total_spent

    # Top 활동 유저 (포획 기준)
    top_users = await pool.fetch(
        """SELECT u.user_id, u.display_name,
                  COALESCE(c.catches, 0) as catches,
                  0 as battles, 0 as wins
           FROM users u
           JOIN (SELECT user_id, COUNT(*) as catches FROM catch_attempts
                 WHERE attempted_at >= $1 AND attempted_at < $1 + INTERVAL '1 day' GROUP BY user_id) c ON u.user_id = c.user_id
           ORDER BY c.catches DESC LIMIT 10""",
        today)

    # 신규 유저
    new_users_detail = await pool.fetch(
        """SELECT u.user_id, u.display_name,
                  COALESCE(c.catches, 0) as catches, 0 as battles
           FROM users u
           LEFT JOIN (SELECT user_id, COUNT(*) as catches FROM catch_attempts
                      WHERE attempted_at >= $1 AND attempted_at < $1 + INTERVAL '1 day' GROUP BY user_id) c ON u.user_id = c.user_id
           WHERE u.registered_at >= $1 AND u.registered_at < $1 + INTERVAL '1 day'
           ORDER BY c.catches DESC NULLS LAST LIMIT 10""",
        today)

    # 이로치 포획
    shiny_catches = await pool.fetch(
        """SELECT sl.caught_by_user_id, u.display_name, pm.name_ko, 0 as used_master_ball
           FROM spawn_log sl
           JOIN pokemon_master pm ON sl.pokemon_id = pm.id
           LEFT JOIN users u ON sl.caught_by_user_id = u.user_id
           WHERE sl.spawned_at >= $1 AND sl.spawned_at < $1 + INTERVAL '1 day'
             AND sl.is_shiny = 1 AND sl.caught_by_user_id IS NOT NULL
           ORDER BY sl.spawned_at DESC""",
        today)

    # 배틀 메타 — winner팀 기준
    battle_meta = await pool.fetch(
        """SELECT pm.name_ko, COUNT(*) as uses, 0.0 as win_rate
           FROM battle_records br
           JOIN battle_teams bt ON br.winner_id = bt.user_id AND bt.team_number = 1
           JOIN user_pokemon up ON bt.pokemon_instance_id = up.id
           JOIN pokemon_master pm ON up.pokemon_id = pm.id
           WHERE br.created_at >= $1 AND br.created_at < $1 + INTERVAL '1 day'
           GROUP BY pm.name_ko ORDER BY uses DESC LIMIT 8""",
        today)

    # 거래소
    market_trends = await pool.fetch(
        """SELECT ml.pokemon_name as name_ko, ml.price_bp as price, ml.is_shiny,
                  seller.display_name as seller_name, buyer.display_name as buyer_name
           FROM market_listings ml
           LEFT JOIN users seller ON ml.seller_id = seller.user_id
           LEFT JOIN users buyer ON ml.buyer_id = buyer.user_id
           WHERE ml.sold_at >= $1 AND ml.sold_at < $1 + INTERVAL '1 day' AND ml.status = 'sold'
           ORDER BY ml.price_bp DESC LIMIT 10""",
        today)

    # 채팅방 건강도
    chat_health = await pool.fetch(
        """SELECT cr.chat_id, cr.chat_title, cr.member_count,
                  COALESCE(t.today_spawns, 0) as today_spawns,
                  COALESCE(y.yesterday_spawns, 0) as yesterday_spawns
           FROM chat_rooms cr
           LEFT JOIN (SELECT chat_id, COUNT(*) as today_spawns FROM spawn_log
                      WHERE spawned_at >= $1 AND spawned_at < $1 + INTERVAL '1 day' GROUP BY chat_id) t ON cr.chat_id = t.chat_id
           LEFT JOIN (SELECT chat_id, COUNT(*) as yesterday_spawns FROM spawn_log
                      WHERE spawned_at >= $1 - INTERVAL '1 day' AND spawned_at < $1 GROUP BY chat_id) y ON cr.chat_id = y.chat_id
           WHERE COALESCE(t.today_spawns, 0) + COALESCE(y.yesterday_spawns, 0) > 0
           ORDER BY t.today_spawns DESC LIMIT 10""",
        today)

    # 시간대별 활성
    hourly_rows = await pool.fetch(
        """SELECT EXTRACT(HOUR FROM attempted_at AT TIME ZONE 'Asia/Seoul')::int as hr,
                  COUNT(DISTINCT user_id) as users
           FROM catch_attempts
           WHERE attempted_at >= $1 AND attempted_at < $1 + INTERVAL '1 day'
           GROUP BY hr ORDER BY hr""",
        today)
    hourly = {r["hr"]: r["users"] for r in hourly_rows}

    # 출석 체크
    checkin_row = await pool.fetchrow(
        "SELECT COUNT(*) as cnt FROM bp_log WHERE source = 'daily_checkin' AND created_at >= $1 AND created_at < $1 + INTERVAL '1 day'",
        today)
    checkin_cnt = checkin_row["cnt"] if checkin_row else 0

    print(f"DAU={dau}, spawns={spawns}, catches={catches}, shinies={shiny_caught}, battles={battles}")

    # HTML 생성
    # Top 유저
    top_html = ""
    if top_users:
        medals = ["🥇", "🥈", "🥉"]
        items = ""
        for i, u in enumerate(top_users):
            medal = medals[i] if i < 3 else f"{i+1}."
            name = (u["display_name"] or "?")[:12]
            items += (f'<div style="display:flex;justify-content:space-between;padding:6px 10px;'
                      f'background:{"#fff3e0" if i < 3 else "#fafafa"};border-radius:6px;margin-bottom:3px;font-size:12px">'
                      f'<span><b>{medal}</b> {name}</span>'
                      f'<span style="color:#666">🎯{u["catches"]} ⚔️{u["battles"]}({u["wins"]}승)</span></div>')
        top_html = f'<div class="section"><div class="section-title">🏆 Top 활동 유저</div>{items}</div>'

    # 신규
    new_html = ""
    if new_users_detail:
        items = ""
        for u in new_users_detail:
            name = (u["display_name"] or "?")[:12]
            act = []
            if u["catches"]: act.append(f"포획 {u['catches']}")
            if u["battles"]: act.append(f"배틀 {u['battles']}")
            items += f'<div style="font-size:12px;padding:4px 0;border-bottom:1px solid #f5f5f5">🆕 <b>{name}</b> — {", ".join(act) if act else "활동없음"}</div>'
        new_html = f'<div class="section"><div class="section-title">🆕 신규 가입 ({new_row["cnt"] if new_row else 0}명)</div>{items}</div>'

    # 이로치
    shiny_html = ""
    if shiny_catches:
        items = ""
        for s in shiny_catches:
            name = (s["display_name"] or "?")[:10]
            ball = "🔴" if s.get("used_master_ball") else "🔵"
            items += f'<div style="font-size:12px;padding:3px 0;border-bottom:1px solid #f5f5f5">✨ <b>{s["name_ko"]}</b> — {name} {ball}</div>'
        shiny_html = f'<div class="section"><div class="section-title">✨ 이로치 포획 ({len(shiny_catches)}마리)</div>{items}</div>'

    # 배틀 메타
    meta_html = ""
    if battle_meta:
        items = ""
        max_uses = battle_meta[0]["uses"] if battle_meta else 1
        for m in battle_meta:
            bar_w = min(100, int(m["uses"] / max(max_uses, 1) * 100))
            wr = m.get("win_rate") or 0
            wr_color = "#4caf50" if wr >= 55 else "#ff9800" if wr >= 45 else "#e53935"
            items += (f'<div style="display:flex;align-items:center;gap:6px;font-size:12px;margin-bottom:4px">'
                      f'<span style="min-width:70px"><b>{m["name_ko"]}</b></span>'
                      f'<div style="flex:1;background:#f5f5f5;border-radius:3px;height:14px;overflow:hidden">'
                      f'<div style="width:{bar_w}%;height:100%;background:#ffcdd2;border-radius:3px"></div></div>'
                      f'<span style="min-width:40px;text-align:right">{m["uses"]}회</span>'
                      f'<span style="min-width:45px;text-align:right;color:{wr_color};font-weight:600">{wr}%</span></div>')
        meta_html = f'<div class="section"><div class="section-title">⚔️ 배틀 메타</div>{items}</div>'

    # 거래소
    market_html = ""
    if market_trends:
        items = ""
        for m in market_trends:
            shiny_mark = "✨" if m.get("is_shiny") else ""
            currency = m.get("currency", "bp")
            price_str = f"{m['price']:,} {'BP' if currency == 'bp' else '마볼'}"
            items += (f'<div style="font-size:12px;padding:3px 0;border-bottom:1px solid #f5f5f5">'
                      f'{shiny_mark}<b>{m["name_ko"]}</b> — {price_str} '
                      f'<span style="color:#888">({(m.get("seller_name") or "?")[:8]} → {(m.get("buyer_name") or "?")[:8]})</span></div>')
        market_html = f'<div class="section"><div class="section-title">🏪 거래소 ({market_sold_row["cnt"] if market_sold_row else 0}건)</div>{items}</div>'

    # 채팅방
    chat_html = ""
    if chat_health:
        items = ""
        for ch in chat_health:
            title = (ch.get("chat_title") or "?")[:15]
            t_s = ch["today_spawns"]
            y_s = ch["yesterday_spawns"]
            if y_s > 0:
                diff_pct = round((t_s - y_s) / y_s * 100)
                trend = f'<span style="color:{"#4caf50" if diff_pct >= 0 else "#e53935"};font-weight:600">{"▲" if diff_pct >= 0 else "▼"}{abs(diff_pct)}%</span>'
            else:
                trend = '<span style="color:#888">NEW</span>'
            items += (f'<div style="display:flex;justify-content:space-between;font-size:12px;padding:4px 0;border-bottom:1px solid #f5f5f5">'
                      f'<span>{title} ({ch.get("member_count", 0)}명)</span>'
                      f'<span>{y_s}→{t_s} {trend}</span></div>')
        chat_html = f'<div class="section"><div class="section-title">💬 채팅방 건강도</div>{items}</div>'

    # 시간대별
    hourly_html = ""
    if hourly:
        max_users = max(hourly.values()) or 1
        peak_hr = max(hourly, key=hourly.get)
        bars = ""
        for hr in range(24):
            users = hourly.get(hr, 0)
            pct = round(users / max_users * 100) if max_users else 0
            is_peak = hr == peak_hr and users > 0
            bar_color = "#e53935" if is_peak else "#ffcdd2" if pct > 0 else "#f5f5f5"
            label_style = "font-weight:700;color:#e53935" if is_peak else "color:#888"
            bars += (f'<div style="display:flex;flex-direction:column;align-items:center;flex:1;min-width:0">'
                     f'<div style="width:100%;background:{bar_color};height:{max(pct, 2)}px;border-radius:2px 2px 0 0;min-height:2px"></div>'
                     f'<div style="font-size:9px;{label_style};margin-top:2px">{hr}</div></div>')
        hourly_html = (f'<div class="section"><div class="section-title">🕐 시간대별 활성 (피크: {peak_hr}시, {hourly.get(peak_hr, 0)}명)</div>'
                       f'<div style="display:flex;gap:1px;align-items:flex-end;height:80px;padding:0 4px">{bars}</div></div>')

    # 출석
    checkin_html = ""
    if checkin_cnt > 0:
        checkin_rate = round(checkin_cnt / max(dau, 1) * 100, 1)
        checkin_html = f'<div class="card"><div class="label">!돈 출석</div><div class="value">{checkin_cnt}명</div><div class="sub">DAU 대비 {checkin_rate}%</div></div>'

    body = f"""
<div class="section">
<div class="section-title">👥 유저</div>
<div class="grid grid-3">
<div class="card"><div class="label">DAU</div><div class="value accent">{dau}</div></div>
<div class="card"><div class="label">신규가입</div><div class="value">{new_row["cnt"] if new_row else 0}</div></div>
<div class="card"><div class="label">총 유저</div><div class="value">{total_users_row["cnt"] if total_users_row else 0}</div></div>
</div>
{f'<div class="grid" style="margin-top:8px">{checkin_html}</div>' if checkin_html else ""}
</div>

{top_html}
{new_html}

{shiny_html}

<div class="section">
<div class="section-title">🎯 스폰 / 포획</div>
<div class="grid">
<div class="card"><div class="label">총 스폰</div><div class="value">{spawns:,}</div></div>
<div class="card"><div class="label">포획</div><div class="value accent">{catches:,}</div><div class="sub">포획률 {catch_rate}%</div></div>
<div class="card"><div class="label">이로치 포획</div><div class="value" style="color:#ff9800">{shiny_caught}</div></div>
<div class="card"><div class="label">마스터볼 사용</div><div class="value">{mb_row["cnt"] if mb_row else 0}</div></div>
</div></div>

{meta_html}

<div class="section">
<div class="section-title">⚔️ 배틀</div>
<div class="grid grid-3">
<div class="card"><div class="label">총 배틀</div><div class="value">{battles}</div></div>
<div class="card"><div class="label">랭크전</div><div class="value">{ranked_row["cnt"] if ranked_row else 0}</div></div>
<div class="card"><div class="label">BP 생성</div><div class="value">+{bp_earned:,}</div></div>
</div></div>

<div class="section">
<div class="section-title">💰 BP 흐름</div>
<div class="grid grid-3">
<div class="card"><div class="label">생성</div><div class="value" style="color:#4caf50">+{bp_earned:,}</div></div>
<div class="card"><div class="label">소각</div><div class="value accent">-{bp_total_spent:,}</div></div>
<div class="card"><div class="label">순변동</div><div class="value" style="color:{'#4caf50' if bp_net >= 0 else '#e53935'}">{bp_net:+,}</div></div>
</div></div>

<div class="section">
<div class="section-title">💰 경제</div>
<div class="grid">
<div class="card"><div class="label">거래소</div><div class="value">{market_sold_row["cnt"] if market_sold_row else 0}</div><div class="sub">신규 {market_new_row["cnt"] if market_new_row else 0}건</div></div>
<div class="card"><div class="label">구독</div><div class="value">{sub_active_row["cnt"] if sub_active_row else 0}명</div></div>
</div></div>

{market_html}
{chat_html}
{hourly_html}
"""

    html = f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>📊 일일 KPI 리포트</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f0f2f5;color:#1a1a2e;padding:24px;line-height:1.6}}
.report{{max-width:640px;margin:0 auto;background:#fff;border-radius:16px;box-shadow:0 4px 24px rgba(0,0,0,.08);overflow:hidden}}
.header{{background:linear-gradient(135deg,#e53935,#ff6f61);color:#fff;padding:28px 32px;text-align:center}}
.header h1{{font-size:22px;font-weight:700;margin-bottom:4px}}
.header .date{{font-size:14px;opacity:.85}}
.body{{padding:24px 28px}}
.section{{margin-bottom:20px}}
.section-title{{font-size:15px;font-weight:700;color:#e53935;margin-bottom:10px;display:flex;align-items:center;gap:8px;border-bottom:2px solid #fce4ec;padding-bottom:6px}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:10px}}
.grid-3{{grid-template-columns:1fr 1fr 1fr}}
.card{{background:#fafafa;border-radius:10px;padding:14px;text-align:center;border:1px solid #f0f0f0}}
.card .label{{font-size:11px;color:#888;margin-bottom:4px;text-transform:uppercase;letter-spacing:.5px}}
.card .value{{font-size:22px;font-weight:700;color:#1a1a2e}}
.card .value.accent{{color:#e53935}}
.card .sub{{font-size:11px;color:#999;margin-top:2px}}
.footer{{text-align:center;padding:16px;color:#aaa;font-size:11px;border-top:1px solid #f0f0f0}}
</style></head><body>
<div class="report">
<div class="header"><h1>📊 일일 KPI 리포트</h1><div class="date">2026-03-16 (월)</div></div>
<div class="body">{body}</div>
<div class="footer">TGPoke KPI Report — auto-generated (수동 발송)</div>
</div></body></html>"""

    # DM 발송
    from telegram import Bot
    token = os.environ.get("BOT_TOKEN")
    if not token:
        # .env에서 읽기
        env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.startswith("BOT_TOKEN="):
                        token = line.strip().split("=", 1)[1]
                        break

    if not token:
        print("BOT_TOKEN not found, saving HTML only")
        with open("report_20260316.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("Saved to report_20260316.html")
    else:
        bot = Bot(token=token)
        buf = io.BytesIO(html.encode("utf-8"))
        buf.name = "kpi_daily_20260316.html"
        await bot.send_document(
            chat_id=ADMIN_ID,
            document=buf,
            caption="📊 일일 KPI 리포트 — 2026-03-16 (월) [수동 발송]",
        )
        print(f"Report sent to admin {ADMIN_ID}")

    await close_db()


asyncio.run(main())
