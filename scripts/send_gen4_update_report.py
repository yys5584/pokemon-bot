"""v3.0 Gen4 업데이트 전후 비교 보고서 — 다중 페이지 상세 리포트."""
import asyncio, os, io, sys, json
from datetime import datetime, timedelta, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
from database import connection
from telegram import Bot

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 1832746512
KST = timezone(timedelta(hours=9))

# ─── HTML 템플릿 ───
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f0f2f5;color:#1a1a2e;padding:16px;line-height:1.6}}
.report{{max-width:720px;margin:0 auto;background:#fff;border-radius:16px;box-shadow:0 4px 24px rgba(0,0,0,.08);overflow:hidden;margin-bottom:20px}}
.header{{background:linear-gradient(135deg,#1a237e,#4a148c,#e53935);color:#fff;padding:32px;text-align:center}}
.header h1{{font-size:24px;font-weight:800;margin-bottom:6px}}
.header .subtitle{{font-size:14px;opacity:.85;margin-bottom:2px}}
.header .date{{font-size:12px;opacity:.7}}
.body{{padding:28px 32px}}
.page-title{{font-size:20px;font-weight:800;color:#1a237e;margin:28px 0 16px;padding:10px 0;border-bottom:3px solid #e8eaf6;display:flex;align-items:center;gap:10px}}
.page-title:first-child{{margin-top:0}}
.section{{margin-bottom:24px}}
.section-title{{font-size:15px;font-weight:700;color:#e53935;margin-bottom:12px;display:flex;align-items:center;gap:8px;border-bottom:2px solid #fce4ec;padding-bottom:6px}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:10px}}
.grid-3{{grid-template-columns:1fr 1fr 1fr}}
.grid-4{{grid-template-columns:1fr 1fr 1fr 1fr}}
.card{{background:#fafafa;border-radius:10px;padding:14px;text-align:center;border:1px solid #f0f0f0;position:relative}}
.card .label{{font-size:11px;color:#888;margin-bottom:4px;text-transform:uppercase;letter-spacing:.5px}}
.card .value{{font-size:22px;font-weight:700;color:#1a1a2e}}
.card .value.accent{{color:#e53935}}
.card .value.green{{color:#4caf50}}
.card .value.blue{{color:#1565c0}}
.card .sub{{font-size:11px;color:#999;margin-top:2px}}
.compare-row{{display:grid;grid-template-columns:1fr 60px 1fr;gap:8px;align-items:center;margin-bottom:8px;padding:10px 14px;background:#fafafa;border-radius:10px;border:1px solid #f0f0f0}}
.compare-row .before{{text-align:right;font-size:18px;font-weight:700;color:#888}}
.compare-row .arrow{{text-align:center;font-size:14px;font-weight:700}}
.compare-row .after{{font-size:18px;font-weight:700;color:#1a237e}}
.compare-row .metric{{font-size:11px;color:#888;text-transform:uppercase;letter-spacing:.5px;margin-bottom:2px}}
.delta-up{{color:#4caf50;font-weight:700}}
.delta-down{{color:#e53935;font-weight:700}}
.delta-flat{{color:#888}}
table.data-table{{width:100%;border-collapse:collapse;font-size:13px;margin-top:8px}}
table.data-table th{{background:#f5f5f5;padding:8px 10px;text-align:left;font-weight:600;color:#666;border-bottom:2px solid #e0e0e0;font-size:11px;text-transform:uppercase}}
table.data-table td{{padding:8px 10px;border-bottom:1px solid #f0f0f0}}
table.data-table tr:hover{{background:#fafafa}}
.bar-chart{{display:flex;flex-direction:column;gap:4px}}
.bar-row{{display:flex;align-items:center;gap:8px}}
.bar-label{{min-width:80px;font-size:12px;color:#666;text-align:right}}
.bar-track{{flex:1;height:20px;background:#f5f5f5;border-radius:4px;overflow:hidden;position:relative}}
.bar-fill{{height:100%;border-radius:4px;transition:width .3s}}
.bar-value{{font-size:12px;font-weight:600;min-width:50px}}
.highlight-box{{background:linear-gradient(135deg,#e8eaf6,#f3e5f5);border-radius:12px;padding:16px 20px;margin:12px 0;border-left:4px solid #7c4dff}}
.highlight-box .hl-title{{font-size:13px;font-weight:700;color:#4a148c;margin-bottom:6px}}
.highlight-box .hl-body{{font-size:13px;color:#333;line-height:1.7}}
.insight-list{{list-style:none;padding:0}}
.insight-list li{{margin-bottom:8px;font-size:13px;padding:8px 12px;background:#fafafa;border-radius:8px;border-left:3px solid #e53935}}
.divider{{height:2px;background:linear-gradient(90deg,#e53935,#ff6f61,transparent);margin:24px 0;border-radius:2px}}
.footer{{text-align:center;padding:20px;color:#aaa;font-size:11px;border-top:1px solid #f0f0f0}}
.badge{{display:inline-block;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:700;margin-left:4px}}
.badge-up{{background:#e8f5e9;color:#2e7d32}}
.badge-down{{background:#ffebee;color:#c62828}}
.badge-new{{background:#e3f2fd;color:#1565c0}}
.rarity-common{{color:#888}}
.rarity-rare{{color:#2196f3}}
.rarity-epic{{color:#9c27b0}}
.rarity-legendary{{color:#ff9800}}
.rarity-ultra{{color:#e53935}}
.toc{{background:#f5f5f5;border-radius:12px;padding:16px 20px;margin-bottom:24px}}
.toc-title{{font-size:14px;font-weight:700;color:#1a237e;margin-bottom:8px}}
.toc-item{{font-size:13px;color:#666;padding:3px 0}}
.toc-item span{{color:#e53935;font-weight:700;margin-right:6px}}
</style></head><body>
<div class="report">
<div class="header">
<h1>{title}</h1>
<div class="subtitle">{subtitle}</div>
<div class="date">{date_str}</div>
</div>
<div class="body">{body}</div>
<div class="footer">TGPoke v3.0 Gen4 Update Report &mdash; auto-generated</div>
</div></body></html>"""


def delta_badge(today_val, prev_val, reverse=False):
    if prev_val is None or prev_val == 0:
        if today_val and today_val > 0:
            return '<span class="badge badge-new">NEW</span>'
        return ""
    diff = today_val - prev_val
    pct = round(diff / prev_val * 100, 1)
    if diff == 0:
        return '<span class="delta-flat" style="font-size:11px">→ 0%</span>'
    positive = (diff > 0) != reverse
    cls = "badge-up" if positive else "badge-down"
    arrow = "▲" if diff > 0 else "▼"
    return f'<span class="badge {cls}">{arrow} {abs(pct)}%</span>'


def compare_card(label, before, after, fmt=",", suffix=""):
    b_str = f"{before:{fmt}}{suffix}" if before is not None else "-"
    a_str = f"{after:{fmt}}{suffix}" if after is not None else "-"
    badge = delta_badge(after or 0, before or 0)
    return (
        f'<div class="card"><div class="label">{label}</div>'
        f'<div class="value blue">{a_str}</div>'
        f'<div class="sub">이전 {b_str} {badge}</div></div>'
    )


def pct_bar(label, value, max_val, color="#e53935"):
    pct = round(value / max(max_val, 1) * 100)
    return (
        f'<div class="bar-row">'
        f'<div class="bar-label">{label}</div>'
        f'<div class="bar-track"><div class="bar-fill" style="width:{pct}%;background:{color}"></div></div>'
        f'<div class="bar-value">{value:,}</div>'
        f'</div>'
    )


async def main():
    pool = await connection.get_db()
    now_kst = datetime.now(KST)

    # ── 기간 설정 ──
    # "After" = 오늘 (Gen4 배포일)
    today_start = now_kst.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    # "Before" = 최근 7일 평균 (업데이트 전 baseline)
    before_start = today_start - timedelta(days=7)
    before_end = today_start

    # "Yesterday" = 어제 (직전일 비교)
    yesterday_start = today_start - timedelta(days=1)
    yesterday_end = today_start

    # ════════════════════════════════════════════
    # 1. 핵심 KPI 수집
    # ════════════════════════════════════════════

    # --- 오늘 ---
    t_dau = await pool.fetchval(
        "SELECT COUNT(DISTINCT user_id) FROM catch_attempts WHERE attempted_at >= $1 AND attempted_at < $2",
        today_start, today_end) or 0
    t_new = await pool.fetchval(
        "SELECT COUNT(*) FROM users WHERE registered_at >= $1 AND registered_at < $2",
        today_start, today_end) or 0
    total_users = await pool.fetchval("SELECT COUNT(*) FROM users") or 0

    t_spawn_row = await pool.fetchrow(
        "SELECT COUNT(*) as s, COUNT(caught_by_user_id) as c FROM spawn_log WHERE spawned_at >= $1 AND spawned_at < $2",
        today_start, today_end)
    t_spawns = t_spawn_row["s"] if t_spawn_row else 0
    t_catches = t_spawn_row["c"] if t_spawn_row else 0
    t_catch_rate = round(t_catches / max(t_spawns, 1) * 100, 1)

    t_shiny = await pool.fetchval(
        "SELECT COUNT(*) FROM spawn_log WHERE spawned_at >= $1 AND spawned_at < $2 AND is_shiny = 1 AND caught_by_user_id IS NOT NULL",
        today_start, today_end) or 0
    t_battles = await pool.fetchval(
        "SELECT COUNT(*) FROM battle_records WHERE created_at >= $1 AND created_at < $2",
        today_start, today_end) or 0
    t_ranked = await pool.fetchval(
        "SELECT COUNT(*) FROM ranked_battle_log WHERE created_at >= $1 AND created_at < $2",
        today_start, today_end) or 0
    t_mb = await pool.fetchval(
        "SELECT COUNT(*) FROM catch_attempts WHERE used_master_ball = 1 AND attempted_at >= $1 AND attempted_at < $2",
        today_start, today_end) or 0

    # --- 7일 평균 ---
    avg7_dau = await pool.fetchval(
        "SELECT COUNT(DISTINCT user_id)::float / 7 FROM catch_attempts WHERE attempted_at >= $1 AND attempted_at < $2",
        before_start, before_end) or 0
    avg7_dau = round(avg7_dau)

    avg7_spawn_row = await pool.fetchrow(
        "SELECT COUNT(*)::float / 7 as s, COUNT(caught_by_user_id)::float / 7 as c FROM spawn_log WHERE spawned_at >= $1 AND spawned_at < $2",
        before_start, before_end)
    avg7_spawns = round(avg7_spawn_row["s"]) if avg7_spawn_row else 0
    avg7_catches = round(avg7_spawn_row["c"]) if avg7_spawn_row else 0
    avg7_catch_rate = round(avg7_catches / max(avg7_spawns, 1) * 100, 1)

    avg7_shiny = await pool.fetchval(
        "SELECT COUNT(*)::float / 7 FROM spawn_log WHERE spawned_at >= $1 AND spawned_at < $2 AND is_shiny = 1 AND caught_by_user_id IS NOT NULL",
        before_start, before_end) or 0
    avg7_shiny = round(avg7_shiny, 1)
    avg7_battles = await pool.fetchval(
        "SELECT COUNT(*)::float / 7 FROM battle_records WHERE created_at >= $1 AND created_at < $2",
        before_start, before_end) or 0
    avg7_battles = round(avg7_battles)
    avg7_new = await pool.fetchval(
        "SELECT COUNT(*)::float / 7 FROM users WHERE registered_at >= $1 AND registered_at < $2",
        before_start, before_end) or 0
    avg7_new = round(avg7_new, 1)

    # --- 어제 ---
    y_dau = await pool.fetchval(
        "SELECT COUNT(DISTINCT user_id) FROM catch_attempts WHERE attempted_at >= $1 AND attempted_at < $2",
        yesterday_start, yesterday_end) or 0
    y_spawn_row = await pool.fetchrow(
        "SELECT COUNT(*) as s, COUNT(caught_by_user_id) as c FROM spawn_log WHERE spawned_at >= $1 AND spawned_at < $2",
        yesterday_start, yesterday_end)
    y_spawns = y_spawn_row["s"] if y_spawn_row else 0
    y_catches = y_spawn_row["c"] if y_spawn_row else 0

    # ════════════════════════════════════════════
    # 2. Gen4 전용 메트릭
    # ════════════════════════════════════════════

    # Gen4 스폰/포획 (오늘)
    g4_spawn_row = await pool.fetchrow(
        """SELECT COUNT(*) as s, COUNT(caught_by_user_id) as c
           FROM spawn_log WHERE spawned_at >= $1 AND spawned_at < $2
           AND pokemon_id >= 387 AND pokemon_id <= 493""",
        today_start, today_end)
    g4_spawns = g4_spawn_row["s"] if g4_spawn_row else 0
    g4_catches = g4_spawn_row["c"] if g4_spawn_row else 0
    g4_catch_rate = round(g4_catches / max(g4_spawns, 1) * 100, 1)
    g4_spawn_pct = round(g4_spawns / max(t_spawns, 1) * 100, 1)

    # Gen4 인기 포켓몬 (오늘 포획 기준 Top 15)
    g4_popular = await pool.fetch(
        """SELECT sl.pokemon_id, pm.name_ko, pm.rarity, COUNT(*) as cnt
           FROM spawn_log sl
           JOIN pokemon_master pm ON pm.id = sl.pokemon_id
           WHERE sl.spawned_at >= $1 AND sl.spawned_at < $2
           AND sl.pokemon_id >= 387 AND sl.pokemon_id <= 493
           AND sl.caught_by_user_id IS NOT NULL
           GROUP BY sl.pokemon_id, pm.name_ko, pm.rarity
           ORDER BY cnt DESC LIMIT 15""",
        today_start, today_end)

    # Gen4 레어리티별 스폰 분포
    g4_rarity_dist = await pool.fetch(
        """SELECT pm.rarity, COUNT(*) as cnt
           FROM spawn_log sl
           JOIN pokemon_master pm ON pm.id = sl.pokemon_id
           WHERE sl.spawned_at >= $1 AND sl.spawned_at < $2
           AND sl.pokemon_id >= 387 AND sl.pokemon_id <= 493
           GROUP BY pm.rarity ORDER BY cnt DESC""",
        today_start, today_end)

    # Gen1-3 레어리티별 스폰 분포 (비교)
    g13_rarity_dist = await pool.fetch(
        """SELECT pm.rarity, COUNT(*) as cnt
           FROM spawn_log sl
           JOIN pokemon_master pm ON pm.id = sl.pokemon_id
           WHERE sl.spawned_at >= $1 AND sl.spawned_at < $2
           AND sl.pokemon_id < 387
           GROUP BY pm.rarity ORDER BY cnt DESC""",
        today_start, today_end)

    # Gen4 포켓몬 보유자 수 (전체)
    g4_owners = await pool.fetchval(
        "SELECT COUNT(DISTINCT user_id) FROM user_pokemon WHERE pokemon_id >= 387 AND pokemon_id <= 493") or 0
    g4_total_owned = await pool.fetchval(
        "SELECT COUNT(*) FROM user_pokemon WHERE pokemon_id >= 387 AND pokemon_id <= 493") or 0

    # Gen4 전설/초전설 포획 현황
    g4_legend_catches = await pool.fetch(
        """SELECT pm.name_ko, pm.rarity, COUNT(*) as cnt
           FROM user_pokemon up
           JOIN pokemon_master pm ON pm.id = up.pokemon_id
           WHERE up.pokemon_id >= 387 AND up.pokemon_id <= 493
           AND pm.rarity IN ('legendary', 'ultra_legendary')
           GROUP BY pm.name_ko, pm.rarity ORDER BY pm.rarity DESC, cnt DESC""")

    # Gen4 이로치 현황
    g4_shiny = await pool.fetchval(
        "SELECT COUNT(*) FROM user_pokemon WHERE pokemon_id >= 387 AND pokemon_id <= 493 AND is_shiny = true") or 0

    # ════════════════════════════════════════════
    # 3. 세대별 도감 완성도
    # ════════════════════════════════════════════

    dex_stats = await pool.fetch(
        """SELECT
             CASE
               WHEN pokemon_id <= 151 THEN '1세대'
               WHEN pokemon_id <= 251 THEN '2세대'
               WHEN pokemon_id <= 386 THEN '3세대'
               ELSE '4세대'
             END as gen,
             COUNT(DISTINCT pokemon_id) as species_caught,
             COUNT(*) as total_caught,
             COUNT(DISTINCT user_id) as collectors
           FROM user_pokemon
           GROUP BY gen ORDER BY gen""")

    gen_totals = {"1세대": 151, "2세대": 100, "3세대": 135, "4세대": 107}

    # ════════════════════════════════════════════
    # 4. BP 경제 비교
    # ════════════════════════════════════════════

    bp_circulation = await pool.fetchval(
        "SELECT COALESCE(SUM(battle_points), 0) FROM users WHERE battle_points > 0") or 0
    bp_avg = await pool.fetchval(
        "SELECT COALESCE(AVG(battle_points), 0) FROM users WHERE battle_points > 0") or 0
    bp_avg = round(float(bp_avg))

    # BP 로그 (오늘)
    bp_earned_today = await pool.fetchval(
        "SELECT COALESCE(SUM(amount), 0) FROM bp_log WHERE amount > 0 AND created_at >= $1 AND created_at < $2",
        today_start, today_end) or 0
    bp_spent_today = await pool.fetchval(
        "SELECT COALESCE(SUM(ABS(amount)), 0) FROM bp_log WHERE amount < 0 AND created_at >= $1 AND created_at < $2",
        today_start, today_end) or 0

    # BP 소스별
    bp_sources = await pool.fetch(
        """SELECT source,
                  COALESCE(SUM(amount) FILTER (WHERE amount > 0), 0) as earned,
                  COALESCE(SUM(ABS(amount)) FILTER (WHERE amount < 0), 0) as spent
           FROM bp_log WHERE created_at >= $1 AND created_at < $2
           GROUP BY source ORDER BY earned DESC""",
        today_start, today_end)

    # 7일 평균 BP
    avg7_bp_earned = await pool.fetchval(
        "SELECT COALESCE(SUM(amount), 0)::float / 7 FROM bp_log WHERE amount > 0 AND created_at >= $1 AND created_at < $2",
        before_start, before_end) or 0
    avg7_bp_spent = await pool.fetchval(
        "SELECT COALESCE(SUM(ABS(amount)), 0)::float / 7 FROM bp_log WHERE amount < 0 AND created_at >= $1 AND created_at < $2",
        before_start, before_end) or 0

    # 뽑기
    gacha_today = await pool.fetchrow(
        "SELECT COALESCE(SUM(bp_spent), 0) as spent, COUNT(*) as pulls FROM gacha_log WHERE created_at >= $1 AND created_at < $2",
        today_start, today_end)
    gacha_spent = int(gacha_today["spent"]) if gacha_today else 0
    gacha_pulls = int(gacha_today["pulls"]) if gacha_today else 0

    avg7_gacha = await pool.fetchrow(
        "SELECT COALESCE(SUM(bp_spent), 0)::float / 7 as spent, COUNT(*)::float / 7 as pulls FROM gacha_log WHERE created_at >= $1 AND created_at < $2",
        before_start, before_end)
    avg7_gacha_spent = round(avg7_gacha["spent"]) if avg7_gacha else 0
    avg7_gacha_pulls = round(avg7_gacha["pulls"], 1) if avg7_gacha else 0

    # 거래소
    t_market_new = await pool.fetchval(
        "SELECT COUNT(*) FROM market_listings WHERE created_at >= $1 AND created_at < $2",
        today_start, today_end) or 0
    t_market_sold = await pool.fetchval(
        "SELECT COUNT(*) FROM market_listings WHERE sold_at >= $1 AND sold_at < $2 AND status = 'sold'",
        today_start, today_end) or 0
    avg7_market = await pool.fetchval(
        "SELECT COUNT(*)::float / 7 FROM market_listings WHERE created_at >= $1 AND created_at < $2",
        before_start, before_end) or 0

    # ════════════════════════════════════════════
    # 5. 채널별 활성도
    # ════════════════════════════════════════════

    top_channels = await pool.fetch(
        """SELECT cr.chat_title, cr.member_count,
                  COUNT(sl.id) as today_spawns,
                  COUNT(sl.caught_by_user_id) as today_catches
           FROM chat_rooms cr
           LEFT JOIN spawn_log sl ON sl.chat_id = cr.chat_id
               AND sl.spawned_at >= $1 AND sl.spawned_at < $2
           GROUP BY cr.chat_id, cr.chat_title, cr.member_count
           HAVING COUNT(sl.id) > 0
           ORDER BY today_catches DESC LIMIT 10""",
        today_start, today_end)

    # ════════════════════════════════════════════
    # 6. 시간대별 활성도
    # ════════════════════════════════════════════

    hourly_rows = await pool.fetch(
        """SELECT EXTRACT(HOUR FROM attempted_at AT TIME ZONE 'Asia/Seoul')::int as hr,
                  COUNT(DISTINCT user_id) as users, COUNT(*) as actions
           FROM catch_attempts
           WHERE attempted_at >= $1 AND attempted_at < $2
           GROUP BY hr ORDER BY hr""",
        today_start, today_end)
    hourly = {r["hr"]: {"users": r["users"], "actions": r["actions"]} for r in hourly_rows}

    # 어제 시간대별 (비교)
    hourly_y_rows = await pool.fetch(
        """SELECT EXTRACT(HOUR FROM attempted_at AT TIME ZONE 'Asia/Seoul')::int as hr,
                  COUNT(DISTINCT user_id) as users
           FROM catch_attempts
           WHERE attempted_at >= $1 AND attempted_at < $2
           GROUP BY hr ORDER BY hr""",
        yesterday_start, yesterday_end)
    hourly_y = {r["hr"]: r["users"] for r in hourly_y_rows}

    # ════════════════════════════════════════════
    # 7. 7일 일별 트렌드
    # ════════════════════════════════════════════

    daily_trend = await pool.fetch(
        """SELECT (spawned_at AT TIME ZONE 'Asia/Seoul')::date as d,
                  COUNT(*) as spawns,
                  COUNT(caught_by_user_id) as catches,
                  COUNT(*) FILTER (WHERE pokemon_id >= 387 AND pokemon_id <= 493) as gen4_spawns
           FROM spawn_log
           WHERE spawned_at >= $1 AND spawned_at < $2
           GROUP BY d ORDER BY d""",
        before_start, today_end)

    daily_dau = await pool.fetch(
        """SELECT (attempted_at AT TIME ZONE 'Asia/Seoul')::date as d,
                  COUNT(DISTINCT user_id) as dau
           FROM catch_attempts
           WHERE attempted_at >= $1 AND attempted_at < $2
           GROUP BY d ORDER BY d""",
        before_start, today_end)
    dau_by_date = {r["d"]: r["dau"] for r in daily_dau}

    # ════════════════════════════════════════════
    # 8. 배틀 메트릭
    # ════════════════════════════════════════════

    # Gen4 포켓몬 배틀 참여 (오늘)
    g4_in_battles = await pool.fetchval(
        """SELECT COUNT(DISTINCT br.id)
           FROM battle_records br
           WHERE br.created_at >= $1 AND br.created_at < $2
           AND (br.winner_team_snapshot::text LIKE '%"pokemon_id": 4%'
                OR br.loser_team_snapshot::text LIKE '%"pokemon_id": 4%')""",
        today_start, today_end) or 0

    # 구독 현황
    sub_active = await pool.fetchval("SELECT COUNT(*) FROM subscriptions WHERE is_active = 1") or 0

    # ════════════════════════════════════════════
    # HTML 생성
    # ════════════════════════════════════════════

    weekdays = ["월", "화", "수", "목", "금", "토", "일"]
    today_str = now_kst.strftime("%Y-%m-%d")
    weekday = weekdays[now_kst.weekday()]

    # ── 목차 ──
    toc = """
<div class="toc">
<div class="toc-title">📋 목차</div>
<div class="toc-item"><span>01</span> Executive Summary — 업데이트 핵심 요약</div>
<div class="toc-item"><span>02</span> Before vs After — 7일 평균 대비 오늘</div>
<div class="toc-item"><span>03</span> Gen4 콘텐츠 메트릭 — 신규 포켓몬 현황</div>
<div class="toc-item"><span>04</span> 세대별 도감 분석 — 수집 현황</div>
<div class="toc-item"><span>05</span> BP 경제 리포트 — 통화 흐름 분석</div>
<div class="toc-item"><span>06</span> 채널별 활성도 — Top 10 채널</div>
<div class="toc-item"><span>07</span> 시간대별 활성 비교 — 어제 vs 오늘</div>
<div class="toc-item"><span>08</span> 8일 트렌드 — 일별 추이 그래프</div>
<div class="toc-item"><span>09</span> 전략적 인사이트 — 분석 및 제안</div>
</div>"""

    # ═══════════════════════════════════════
    # PAGE 1: Executive Summary
    # ═══════════════════════════════════════

    elapsed_hrs = round((now_kst - today_start).total_seconds() / 3600, 1)

    p1 = f"""
<div class="page-title">📊 01. Executive Summary</div>

<div class="highlight-box">
<div class="hl-title">🎮 v3.0 — 4세대(신오) 107종 대형 업데이트</div>
<div class="hl-body">
배포 후 약 <b>{elapsed_hrs}시간</b> 경과 기준 데이터.<br>
총 도감: 386종 → <b>493종</b> (+107종, +27.7%)<br>
신규 전설 7종 + 초전설 7종 + 분기진화 2종 + 크로스세대 진화 18종
</div>
</div>

<div class="grid grid-3">
{compare_card("DAU", avg7_dau, t_dau)}
{compare_card("스폰", avg7_spawns, t_spawns)}
{compare_card("포획", avg7_catches, t_catches)}
{compare_card("배틀", avg7_battles, t_battles)}
{compare_card("신규가입", round(avg7_new), t_new)}
{compare_card("Gen4 스폰", 0, g4_spawns)}
</div>

<div style="margin-top:12px" class="grid">
<div class="card"><div class="label">Gen4 비중</div><div class="value accent">{g4_spawn_pct}%</div><div class="sub">전체 스폰 중</div></div>
<div class="card"><div class="label">Gen4 포획률</div><div class="value green">{g4_catch_rate}%</div><div class="sub">Gen1-3 평균 {avg7_catch_rate}%</div></div>
</div>"""

    # ═══════════════════════════════════════
    # PAGE 2: Before vs After
    # ═══════════════════════════════════════

    p2 = f"""
<div class="divider"></div>
<div class="page-title">🔄 02. Before vs After</div>

<div style="font-size:12px;color:#888;margin-bottom:12px">
Before = 최근 7일 일평균 ({(before_start).strftime('%m/%d')}~{(before_end - timedelta(days=1)).strftime('%m/%d')}) &nbsp;|&nbsp; After = 오늘 ({today_str}, ~{elapsed_hrs}h 경과)
</div>

<div class="section">
<div class="section-title">👥 유저 지표</div>
<div class="grid">
{compare_card("DAU", avg7_dau, t_dau)}
{compare_card("신규가입", round(avg7_new), t_new)}
</div>
<div class="grid" style="margin-top:10px">
<div class="card"><div class="label">총 유저</div><div class="value">{total_users:,}</div></div>
<div class="card"><div class="label">활성 구독</div><div class="value blue">{sub_active}</div></div>
</div>
</div>

<div class="section">
<div class="section-title">🎯 스폰 / 포획</div>
<div class="grid">
{compare_card("총 스폰", avg7_spawns, t_spawns)}
{compare_card("포획", avg7_catches, t_catches)}
{compare_card("포획률", avg7_catch_rate, t_catch_rate, fmt=".1f", suffix="%")}
{compare_card("이로치", round(avg7_shiny), t_shiny)}
</div>
</div>

<div class="section">
<div class="section-title">⚔️ 배틀</div>
<div class="grid grid-3">
{compare_card("총 배틀", avg7_battles, t_battles)}
<div class="card"><div class="label">랭크전</div><div class="value">{t_ranked}</div></div>
<div class="card"><div class="label">마스터볼</div><div class="value">{t_mb}</div></div>
</div>
</div>"""

    # ═══════════════════════════════════════
    # PAGE 3: Gen4 콘텐츠 메트릭
    # ═══════════════════════════════════════

    # Gen4 인기 포켓몬 테이블
    rarity_cls = {"common": "rarity-common", "rare": "rarity-rare", "epic": "rarity-epic",
                  "legendary": "rarity-legendary", "ultra_legendary": "rarity-ultra"}
    rarity_ko = {"common": "커먼", "rare": "레어", "epic": "에픽",
                 "legendary": "전설", "ultra_legendary": "초전설"}

    popular_rows = ""
    for i, p in enumerate(g4_popular, 1):
        cls = rarity_cls.get(p["rarity"], "")
        rko = rarity_ko.get(p["rarity"], p["rarity"])
        popular_rows += (
            f'<tr><td style="font-weight:700">{i}</td>'
            f'<td>#{p["pokemon_id"]}</td>'
            f'<td><b>{p["name_ko"]}</b></td>'
            f'<td class="{cls}">{rko}</td>'
            f'<td style="font-weight:700">{p["cnt"]}</td></tr>'
        )
    if not popular_rows:
        popular_rows = '<tr><td colspan="5" style="text-align:center;color:#888">아직 포획 데이터 없음</td></tr>'

    # 레어리티 분포 비교
    g4_rarity = {r["rarity"]: r["cnt"] for r in g4_rarity_dist}
    g13_rarity = {r["rarity"]: r["cnt"] for r in g13_rarity_dist}
    g4_total_sp = sum(g4_rarity.values()) or 1
    g13_total_sp = sum(g13_rarity.values()) or 1

    rarity_compare = ""
    for r_key in ["common", "rare", "epic", "legendary", "ultra_legendary"]:
        g4_cnt = g4_rarity.get(r_key, 0)
        g13_cnt = g13_rarity.get(r_key, 0)
        g4_pct = round(g4_cnt / g4_total_sp * 100, 1)
        g13_pct = round(g13_cnt / g13_total_sp * 100, 1)
        cls = rarity_cls.get(r_key, "")
        rko = rarity_ko.get(r_key, r_key)
        rarity_compare += (
            f'<tr><td class="{cls}"><b>{rko}</b></td>'
            f'<td>{g13_cnt:,} ({g13_pct}%)</td>'
            f'<td>{g4_cnt:,} ({g4_pct}%)</td></tr>'
        )

    # 전설/초전설 테이블
    legend_rows = ""
    for p in g4_legend_catches:
        cls = rarity_cls.get(p["rarity"], "")
        rko = rarity_ko.get(p["rarity"], "")
        legend_rows += f'<tr><td><b>{p["name_ko"]}</b></td><td class="{cls}">{rko}</td><td style="font-weight:700">{p["cnt"]}</td></tr>'
    if not legend_rows:
        legend_rows = '<tr><td colspan="3" style="text-align:center;color:#888">아직 포획 기록 없음</td></tr>'

    p3 = f"""
<div class="divider"></div>
<div class="page-title">🌟 03. Gen4 콘텐츠 메트릭</div>

<div class="grid grid-3">
<div class="card"><div class="label">Gen4 스폰</div><div class="value accent">{g4_spawns:,}</div><div class="sub">전체의 {g4_spawn_pct}%</div></div>
<div class="card"><div class="label">Gen4 포획</div><div class="value green">{g4_catches:,}</div><div class="sub">포획률 {g4_catch_rate}%</div></div>
<div class="card"><div class="label">Gen4 이로치</div><div class="value" style="color:#ff9800">{g4_shiny}</div></div>
</div>

<div class="grid" style="margin-top:10px">
<div class="card"><div class="label">Gen4 보유자</div><div class="value blue">{g4_owners:,}명</div></div>
<div class="card"><div class="label">Gen4 총 보유</div><div class="value">{g4_total_owned:,}마리</div></div>
</div>

<div class="section" style="margin-top:16px">
<div class="section-title">🏆 Gen4 인기 포켓몬 Top 15 (포획 기준)</div>
<table class="data-table">
<thead><tr><th>#</th><th>번호</th><th>이름</th><th>등급</th><th>포획수</th></tr></thead>
<tbody>{popular_rows}</tbody>
</table>
</div>

<div class="section">
<div class="section-title">📊 레어리티 분포 비교 (Gen1-3 vs Gen4)</div>
<table class="data-table">
<thead><tr><th>등급</th><th>Gen1-3 (오늘)</th><th>Gen4 (오늘)</th></tr></thead>
<tbody>{rarity_compare}</tbody>
</table>
</div>

<div class="section">
<div class="section-title">👑 Gen4 전설 / 초전설 포획 현황</div>
<table class="data-table">
<thead><tr><th>포켓몬</th><th>등급</th><th>보유 수</th></tr></thead>
<tbody>{legend_rows}</tbody>
</table>
</div>"""

    # ═══════════════════════════════════════
    # PAGE 4: 세대별 도감 분석
    # ═══════════════════════════════════════

    dex_rows = ""
    for d in dex_stats:
        gen = d["gen"]
        total = gen_totals.get(gen, 0)
        species = d["species_caught"]
        completion = round(species / max(total, 1) * 100, 1)
        dex_rows += (
            f'<tr><td><b>{gen}</b></td>'
            f'<td>{total}</td>'
            f'<td>{species} / {total}</td>'
            f'<td>{completion}%</td>'
            f'<td>{d["total_caught"]:,}</td>'
            f'<td>{d["collectors"]:,}</td></tr>'
        )

    p4 = f"""
<div class="divider"></div>
<div class="page-title">📖 04. 세대별 도감 분석</div>

<div class="section">
<div class="section-title">🗂️ 세대별 수집 현황</div>
<table class="data-table">
<thead><tr><th>세대</th><th>총 종</th><th>출현 종</th><th>완성도</th><th>총 포획</th><th>수집가</th></tr></thead>
<tbody>{dex_rows}</tbody>
</table>
</div>

<div class="highlight-box">
<div class="hl-title">📌 도감 확장 효과</div>
<div class="hl-body">
총 도감 386종 → <b>493종</b>으로 확장 (+27.7%).<br>
4세대에서 현재까지 <b>{g4_total_owned:,}마리</b>가 포획되었으며,
<b>{g4_owners:,}명</b>의 트레이너가 Gen4 포켓몬을 보유 중.
</div>
</div>"""

    # ═══════════════════════════════════════
    # PAGE 5: BP 경제
    # ═══════════════════════════════════════

    bp_src_labels = {
        "battle": "⚔️ 배틀", "ranked_battle": "🏟️ 랭크전", "catch": "🎯 포획",
        "tournament": "🏆 토너먼트", "mission": "📋 미션", "bet_win": "🎲 야차(승)",
        "gacha_refund": "🎰 뽑기환급", "gacha_jackpot": "💎 뽑기잭팟",
        "ranked_reward": "🏅 시즌보상", "admin": "🔧 관리자",
        "shop_masterball": "🔴 마볼구매", "shop_hyperball": "🔵 하볼구매",
        "shop_gacha_ticket": "🎫 뽑기권", "shop_arcade_speed": "⚡ 속도부스트",
        "shop_arcade_extend": "⏱️ 연장권",
    }

    bp_src_rows = ""
    for s in bp_sources:
        label = bp_src_labels.get(s["source"], s["source"])
        earned = int(s["earned"])
        spent = int(s["spent"])
        net = earned - spent
        net_color = "#4caf50" if net >= 0 else "#e53935"
        bp_src_rows += (
            f'<tr><td>{label}</td>'
            f'<td style="color:#4caf50;font-weight:600">+{earned:,}</td>'
            f'<td style="color:#e53935;font-weight:600">-{spent:,}</td>'
            f'<td style="color:{net_color};font-weight:700">{net:+,}</td></tr>'
        )
    if not bp_src_rows:
        bp_src_rows = '<tr><td colspan="4" style="text-align:center;color:#888">데이터 없음</td></tr>'

    bp_net = int(bp_earned_today) - int(bp_spent_today)
    sink_ratio = round(int(bp_spent_today) / max(int(bp_earned_today), 1) * 100, 1) if bp_earned_today > 0 else 0

    p5 = f"""
<div class="divider"></div>
<div class="page-title">💰 05. BP 경제 리포트</div>

<div class="grid grid-3">
<div class="card"><div class="label">생성</div><div class="value green">+{int(bp_earned_today):,}</div>{delta_badge(int(bp_earned_today), round(avg7_bp_earned))}<div class="sub">7일 평균 +{round(avg7_bp_earned):,}</div></div>
<div class="card"><div class="label">소각</div><div class="value accent">-{int(bp_spent_today):,}</div>{delta_badge(int(bp_spent_today), round(avg7_bp_spent), reverse=True)}<div class="sub">7일 평균 -{round(avg7_bp_spent):,}</div></div>
<div class="card"><div class="label">순변동</div><div class="value" style="color:{'#4caf50' if bp_net >= 0 else '#e53935'}">{bp_net:+,}</div><div class="sub">소각률 {sink_ratio}%</div></div>
</div>

<div class="grid" style="margin-top:10px">
<div class="card"><div class="label">총 유통량</div><div class="value">{int(bp_circulation):,}</div></div>
<div class="card"><div class="label">보유자 평균</div><div class="value">{bp_avg:,}</div></div>
</div>

<div class="section" style="margin-top:16px">
<div class="section-title">📈 소스별 BP 흐름</div>
<table class="data-table">
<thead><tr><th>소스</th><th>생성</th><th>소각</th><th>순변동</th></tr></thead>
<tbody>{bp_src_rows}</tbody>
</table>
</div>

<div class="section">
<div class="section-title">🎰 뽑기 현황</div>
<div class="grid">
{compare_card("뽑기 횟수", round(avg7_gacha_pulls), gacha_pulls)}
{compare_card("뽑기 소비", avg7_gacha_spent, gacha_spent)}
</div>
<div class="grid" style="margin-top:10px">
{compare_card("거래소 등록", round(avg7_market), t_market_new)}
<div class="card"><div class="label">거래 성사</div><div class="value">{t_market_sold}</div></div>
</div>
</div>"""

    # ═══════════════════════════════════════
    # PAGE 6: 채널별 활성도
    # ═══════════════════════════════════════

    channel_rows = ""
    for i, ch in enumerate(top_channels, 1):
        title = (ch.get("chat_title") or "?")[:20]
        members = ch.get("member_count", 0)
        cr = round(ch["today_catches"] / max(ch["today_spawns"], 1) * 100, 1)
        channel_rows += (
            f'<tr><td style="font-weight:700;color:#e53935">{i}</td>'
            f'<td><b>{title}</b></td>'
            f'<td>{members:,}</td>'
            f'<td>{ch["today_spawns"]:,}</td>'
            f'<td>{ch["today_catches"]:,}</td>'
            f'<td>{cr}%</td></tr>'
        )
    if not channel_rows:
        channel_rows = '<tr><td colspan="6" style="text-align:center;color:#888">데이터 없음</td></tr>'

    p6 = f"""
<div class="divider"></div>
<div class="page-title">📡 06. 채널별 활성도 Top 10</div>

<table class="data-table">
<thead><tr><th>#</th><th>채널</th><th>멤버</th><th>스폰</th><th>포획</th><th>포획률</th></tr></thead>
<tbody>{channel_rows}</tbody>
</table>"""

    # ═══════════════════════════════════════
    # PAGE 7: 시간대별 활성 비교
    # ═══════════════════════════════════════

    max_users = max((hourly.get(h, {}).get("users", 0) for h in range(24)), default=1) or 1
    max_y_users = max((hourly_y.get(h, 0) for h in range(24)), default=1) or 1
    max_all = max(max_users, max_y_users) or 1

    hourly_bars = ""
    for hr in range(24):
        t_u = hourly.get(hr, {}).get("users", 0)
        y_u = hourly_y.get(hr, 0)
        t_pct = round(t_u / max_all * 100)
        y_pct = round(y_u / max_all * 100)
        hourly_bars += (
            f'<div style="display:flex;align-items:center;gap:6px;margin-bottom:3px">'
            f'<span style="min-width:28px;font-size:11px;color:#888;text-align:right">{hr}시</span>'
            f'<div style="flex:1;display:flex;flex-direction:column;gap:1px">'
            f'<div style="display:flex;align-items:center;gap:4px">'
            f'<div style="background:#e53935;height:10px;width:{t_pct}%;border-radius:2px;min-width:{1 if t_u else 0}px"></div>'
            f'<span style="font-size:10px;color:#e53935">{t_u}</span></div>'
            f'<div style="display:flex;align-items:center;gap:4px">'
            f'<div style="background:#ccc;height:10px;width:{y_pct}%;border-radius:2px;min-width:{1 if y_u else 0}px"></div>'
            f'<span style="font-size:10px;color:#999">{y_u}</span></div>'
            f'</div></div>'
        )

    peak_hr = max(range(24), key=lambda h: hourly.get(h, {}).get("users", 0)) if hourly else 0

    p7 = f"""
<div class="divider"></div>
<div class="page-title">🕐 07. 시간대별 활성 비교</div>

<div style="font-size:12px;margin-bottom:10px">
<span style="display:inline-block;width:12px;height:12px;background:#e53935;border-radius:2px;vertical-align:middle"></span> 오늘 &nbsp;
<span style="display:inline-block;width:12px;height:12px;background:#ccc;border-radius:2px;vertical-align:middle"></span> 어제 &nbsp;
| 피크: <b>{peak_hr}시</b> ({hourly.get(peak_hr, {}).get('users', 0)}명)
</div>

{hourly_bars}"""

    # ═══════════════════════════════════════
    # PAGE 8: 8일 트렌드
    # ═══════════════════════════════════════

    max_sp = max((r["spawns"] for r in daily_trend), default=1) or 1
    trend_bars = ""
    for r in daily_trend:
        d_str = r["d"].strftime("%m/%d")
        wd = weekdays[r["d"].weekday()]
        sp = r["spawns"]
        ct = r["catches"]
        g4s = r["gen4_spawns"]
        dau_val = dau_by_date.get(r["d"], 0)
        sp_pct = round(sp / max_sp * 100)
        g4_pct = round(g4s / max(sp, 1) * 100)
        is_today = r["d"] == now_kst.date()
        bg = "linear-gradient(90deg,#e53935,#ff6f61)" if is_today else "#ffcdd2"
        g4_bg = "#7c4dff" if g4s > 0 else "transparent"

        trend_bars += (
            f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;{"font-weight:700" if is_today else ""}">'
            f'<span style="min-width:60px;font-size:12px;color:{"#e53935" if is_today else "#888"}">{d_str}({wd})</span>'
            f'<div style="flex:1;height:22px;background:#f5f5f5;border-radius:4px;overflow:hidden;position:relative">'
            f'<div style="height:100%;width:{sp_pct}%;background:{bg};border-radius:4px"></div>'
            f'{"<div style=&quot;position:absolute;top:0;left:0;height:100%;width:" + str(round(g4s/max_sp*100)) + "%;background:" + g4_bg + ";opacity:.3;border-radius:4px&quot;></div>" if g4s > 0 else ""}'
            f'</div>'
            f'<span style="min-width:130px;font-size:11px;color:#666">'
            f'S:{sp:,} C:{ct:,} DAU:{dau_val}'
            f'{"  <b style=color:#7c4dff>G4:" + str(g4s) + "</b>" if g4s > 0 else ""}'
            f'</span>'
            f'</div>'
        )

    p8 = f"""
<div class="divider"></div>
<div class="page-title">📈 08. 8일 트렌드</div>

<div style="font-size:12px;margin-bottom:8px;color:#888">
<span style="display:inline-block;width:12px;height:12px;background:#e53935;border-radius:2px;vertical-align:middle"></span> 오늘 &nbsp;
<span style="display:inline-block;width:12px;height:12px;background:#ffcdd2;border-radius:2px;vertical-align:middle"></span> 이전 &nbsp;
<span style="display:inline-block;width:12px;height:12px;background:#7c4dff;opacity:.3;border-radius:2px;vertical-align:middle"></span> Gen4 비중
</div>

{trend_bars}"""

    # ═══════════════════════════════════════
    # PAGE 9: 전략적 인사이트
    # ═══════════════════════════════════════

    insights = []

    # DAU 변화
    dau_diff = t_dau - avg7_dau
    if dau_diff > 0:
        insights.append(f"📈 <b>DAU {t_dau}명</b> — 7일 평균({avg7_dau}) 대비 <b>+{dau_diff}명</b> 증가. Gen4 업데이트의 즉각적 유입 효과.")
    elif dau_diff < 0:
        insights.append(f"📉 <b>DAU {t_dau}명</b> — 7일 평균 대비 {dau_diff}명 감소. 아직 경과 시간({elapsed_hrs}h)이 짧아 판단 보류.")
    else:
        insights.append(f"→ DAU {t_dau}명 — 7일 평균과 동일. 안정적.")

    # Gen4 콘텐츠 충격
    if g4_spawns > 0:
        insights.append(
            f"🌟 <b>Gen4 스폰 {g4_spawns:,}회</b> (전체의 {g4_spawn_pct}%). "
            f"포획률 {g4_catch_rate}%{'(Gen1-3 대비 높음 — 신규 콘텐츠 수요)' if g4_catch_rate > avg7_catch_rate else ''}."
        )
    else:
        insights.append("⚠️ Gen4 스폰이 아직 0. 스폰 로직 또는 시딩 확인 필요.")

    # 경제 분석
    if bp_earned_today > 0:
        net_str = f"+{bp_net:,}" if bp_net >= 0 else f"{bp_net:,}"
        insights.append(
            f"💰 <b>BP 순변동 {net_str}</b> — "
            f"소각률 {sink_ratio}%. "
            f"{'건전한 싱크 작동 ✓' if 80 <= sink_ratio <= 150 else '소각 부족, 콘텐츠 싱크 추가 필요' if sink_ratio < 80 else '디플레이션 위험, 생성 채널 보강 필요'}"
        )

    # Gen4 밸런스
    if g4_popular:
        top3 = [p["name_ko"] for p in g4_popular[:3]]
        insights.append(f"🎯 <b>Gen4 인기 Top 3:</b> {', '.join(top3)} — 커먼/레어 중심이면 건전한 수집 순환.")

    # 포획률 변화
    rate_diff = t_catch_rate - avg7_catch_rate
    if abs(rate_diff) > 3:
        direction = "상승" if rate_diff > 0 else "하락"
        insights.append(f"🎯 포획률 {avg7_catch_rate}% → {t_catch_rate}% ({direction} {abs(rate_diff):.1f}p). Gen4 추가에 의한 밸런스 변동 모니터링.")

    # 전설 현황
    if g4_legend_catches:
        total_legends = sum(p["cnt"] for p in g4_legend_catches)
        insights.append(f"👑 Gen4 전설/초전설 <b>{total_legends}마리</b> 포획됨. 희소성 유지 모니터링 필요.")
    else:
        insights.append("👑 Gen4 전설/초전설 아직 미포획 — 예상대로 희소성 유지 중.")

    # 제안
    insights.append("")
    insights.append("💡 <b>향후 모니터링 포인트:</b>")
    insights.append("　• Gen4 포켓몬의 배틀 승률 — 한카리아스(에픽) 밸런스 체크")
    insights.append("　• 분기진화(킬리아/눈꼬마) 50:50 분포 검증")
    insights.append("　• 크로스세대 진화(자포코일 등) 진화 경로 정상 작동 확인")
    insights.append("　• 3일 후 D+3 리텐션 비교 — Gen4가 이탈 방지에 기여하는지")

    insight_items = ""
    for ins in insights:
        if ins == "":
            insight_items += '<div style="height:8px"></div>'
        elif ins.startswith("　"):
            insight_items += f'<div style="font-size:13px;color:#555;padding:2px 12px">{ins}</div>'
        else:
            insight_items += f'<li>{ins}</li>'

    p9 = f"""
<div class="divider"></div>
<div class="page-title">💡 09. 전략적 인사이트</div>

<ul class="insight-list">{insight_items}</ul>

<div class="highlight-box" style="margin-top:16px">
<div class="hl-title">📋 v3.0 업데이트 체크리스트</div>
<div class="hl-body">
✅ 4세대 107종 데이터 정상 시딩 (493종)<br>
✅ 분기진화 시스템 (킬리아/눈꼬마)<br>
✅ 크로스세대 진화 18종 연결<br>
✅ 한카리아스/레지기가스 에픽 조정 + 스킬 너프<br>
✅ 리피아/글레이시아 에픽 통일<br>
✅ 커스텀이모지 전면 적용 (DM/거래소/진화)<br>
✅ 어뷰징 챌린지 5분→3분<br>
✅ 도감 4세대 필터 + 107종 트리비아<br>
✅ 스킬 파워 Gen1-3 기준 보정 (9종)
</div>
</div>"""

    # ═══════════════════════════════════════
    # 최종 조립
    # ═══════════════════════════════════════

    body = toc + p1 + p2 + p3 + p4 + p5 + p6 + p7 + p8 + p9

    html = HTML_TEMPLATE.format(
        title="📊 v3.0 Gen4 업데이트 보고서",
        subtitle="4세대(신오) 107종 대형 업데이트 전후 비교 분석",
        date_str=f"{today_str} ({weekday}) — 보고서 생성 {now_kst.strftime('%H:%M')} KST",
        body=body,
    )

    filename = f"gen4_update_report_{today_str.replace('-', '')}.html"

    bot = Bot(token=BOT_TOKEN)
    buf = io.BytesIO(html.encode("utf-8"))
    buf.name = filename
    await bot.send_document(
        chat_id=ADMIN_ID,
        document=buf,
        caption=f"📊 v3.0 Gen4 업데이트 보고서 — {today_str} ({weekday})\n9개 섹션 상세 분석"
    )
    print(f"✅ Report sent: {filename}")


if __name__ == "__main__":
    asyncio.run(main())
