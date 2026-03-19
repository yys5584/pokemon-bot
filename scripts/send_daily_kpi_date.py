"""특정 날짜 일일 KPI 리포트 발송 스크립트. 사용법: python scripts/send_daily_kpi_date.py 2026-03-11"""
import asyncio, os, io, sys, subprocess
from datetime import datetime, timedelta, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
from database import connection
from telegram import Bot

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 1832746512

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;background:#f0f2f5;color:#1a1a2e;padding:24px;line-height:1.6}}
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
.channel-list{{list-style:none}}
.channel-list li{{display:flex;justify-content:space-between;align-items:center;padding:8px 12px;border-radius:8px;margin-bottom:4px;background:#fafafa;font-size:13px}}
.channel-list li:nth-child(1){{background:#fff3e0;font-weight:600}}
.channel-list li:nth-child(2){{background:#fce4ec}}
.channel-list .rank{{font-weight:700;color:#e53935;min-width:24px}}
.channel-list .cnt{{color:#666;font-size:12px}}
.footer{{text-align:center;padding:16px;color:#aaa;font-size:11px;border-top:1px solid #f0f0f0}}
</style></head><body>
<div class="report">
<div class="header"><h1>{title}</h1><div class="date">{date_str}</div></div>
<div class="body">{body}</div>
<div class="footer">TGPoke KPI Report &mdash; auto-generated</div>
</div></body></html>"""


def delta_badge(today_val, prev_val):
    if prev_val is None or prev_val == 0:
        return ""
    diff = today_val - prev_val
    pct = round(diff / prev_val * 100)
    if diff == 0:
        return '<span style="color:#888;font-size:11px">→ 0%</span>'
    color = "#4caf50" if diff > 0 else "#e53935"
    arrow = "▲" if diff > 0 else "▼"
    return f'<span style="color:{color};font-size:11px;font-weight:600">{arrow} {abs(pct)}%</span>'


def get_patches_for_date(date_str):
    """특정 날짜의 git 커밋 목록."""
    try:
        result = subprocess.run(
            ["git", "log", f"--since={date_str} 00:00", f"--until={date_str} 23:59",
             "--pretty=format:%s", "--no-merges"],
            capture_output=True, text=True, timeout=5,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        )
        lines = [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
        return [l for l in lines if any(l.startswith(p) for p in ("feat:", "fix:", "refactor:", "chore:"))]
    except Exception:
        return []


async def main():
    target_date = sys.argv[1] if len(sys.argv) > 1 else None
    if not target_date:
        print("Usage: python scripts/send_daily_kpi_date.py 2026-03-11")
        return

    pool = await connection.get_db()
    KST = timezone(timedelta(hours=9))
    dt = datetime.strptime(target_date, "%Y-%m-%d")
    # KST 00:00 ~ 23:59:59 (UTC 기준으로 -9시간)
    day_start = dt.replace(tzinfo=KST)
    day_end = day_start + timedelta(days=1)
    prev_start = day_start - timedelta(days=1)
    weekdays = ["월", "화", "수", "목", "금", "토", "일"]
    weekday = weekdays[dt.weekday()]

    # 당일 데이터
    dau = await pool.fetchval(
        "SELECT COUNT(DISTINCT user_id) FROM catch_attempts WHERE attempted_at >= $1 AND attempted_at < $2",
        day_start, day_end) or 0
    new_users = await pool.fetchval(
        "SELECT COUNT(*) FROM users WHERE registered_at >= $1 AND registered_at < $2",
        day_start, day_end) or 0
    total_users = await pool.fetchval("SELECT COUNT(*) FROM users") or 0

    spawn_row = await pool.fetchrow(
        """SELECT COUNT(*) as spawns, COUNT(caught_by_user_id) as catches
           FROM spawn_log WHERE spawned_at >= $1 AND spawned_at < $2""",
        day_start, day_end)
    spawns = spawn_row["spawns"] if spawn_row else 0
    catches = spawn_row["catches"] if spawn_row else 0
    catch_rate = round(catches / spawns * 100, 1) if spawns > 0 else 0

    shiny_caught = await pool.fetchval(
        """SELECT COUNT(*) FROM spawn_log
           WHERE spawned_at >= $1 AND spawned_at < $2 AND is_shiny = 1 AND caught_by_user_id IS NOT NULL""",
        day_start, day_end) or 0
    mb_used = await pool.fetchval(
        "SELECT COUNT(*) FROM catch_attempts WHERE used_master_ball = 1 AND attempted_at >= $1 AND attempted_at < $2",
        day_start, day_end) or 0

    battles = await pool.fetchval(
        "SELECT COUNT(*) FROM battle_records WHERE created_at >= $1 AND created_at < $2",
        day_start, day_end) or 0
    ranked_battles = await pool.fetchval(
        "SELECT COUNT(*) FROM ranked_battle_log WHERE created_at >= $1 AND created_at < $2",
        day_start, day_end) or 0
    # BP earned: bp_log 우선, 없으면 기존 테이블에서 소스별 추정
    bp_log_exists = await pool.fetchval(
        "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name='bp_log')")
    bp_log_has_data = False
    if bp_log_exists:
        bp_log_count = await pool.fetchval(
            "SELECT COUNT(*) FROM bp_log WHERE created_at >= $1 AND created_at < $2",
            day_start, day_end) or 0
        bp_log_has_data = bp_log_count > 0

    if bp_log_has_data:
        bp_earned = await pool.fetchval(
            "SELECT COALESCE(SUM(amount), 0) FROM bp_log WHERE amount > 0 AND created_at >= $1 AND created_at < $2",
            day_start, day_end) or 0
        bp_total_spent = await pool.fetchval(
            "SELECT COALESCE(SUM(ABS(amount)), 0) FROM bp_log WHERE amount < 0 AND created_at >= $1 AND created_at < $2",
            day_start, day_end) or 0
        bp_source_rows = await pool.fetch(
            """SELECT source,
                      COALESCE(SUM(amount) FILTER (WHERE amount > 0), 0) as earned,
                      COALESCE(SUM(ABS(amount)) FILTER (WHERE amount < 0), 0) as spent
               FROM bp_log WHERE created_at >= $1 AND created_at < $2
               GROUP BY source ORDER BY earned DESC""",
            day_start, day_end)
        bp_sources = {r["source"]: {"earned": int(r["earned"]), "spent": int(r["spent"])} for r in bp_source_rows}
    else:
        # fallback: 기존 테이블에서 소스별 BP 추정
        bp_sources = {}
        # battle_type별 배틀 BP
        bt_rows = await pool.fetch(
            """SELECT battle_type, COALESCE(SUM(bp_earned), 0) as earned
               FROM battle_records WHERE created_at >= $1 AND created_at < $2
               GROUP BY battle_type""",
            day_start, day_end)
        for r in bt_rows:
            btype = r["battle_type"]
            earned = int(r["earned"])
            if earned <= 0:
                continue
            if btype == "ranked":
                bp_sources["ranked_battle"] = {"earned": earned, "spent": 0}
            else:
                bp_sources["battle"] = {"earned": bp_sources.get("battle", {"earned": 0, "spent": 0})["earned"] + earned, "spent": 0}
        # 포획 BP 추정 (평균 CATCH_BP_MIN~MAX의 중간값 * 포획수)
        catch_count = await pool.fetchval(
            """SELECT COUNT(*) FROM spawn_log
               WHERE spawned_at >= $1 AND spawned_at < $2 AND caught_by_user_id IS NOT NULL""",
            day_start, day_end) or 0
        if catch_count > 0:
            try:
                import config as _cfg
                avg_catch_bp = (_cfg.CATCH_BP_MIN + _cfg.CATCH_BP_MAX) // 2
            except Exception:
                avg_catch_bp = 5
            bp_sources["catch"] = {"earned": int(catch_count * avg_catch_bp), "spent": 0}
        # 토너먼트 BP 추정 (참가자 수 기반)
        try:
            tourn_participants = await pool.fetchval(
                """SELECT COUNT(DISTINCT winner_id) + COUNT(DISTINCT loser_id)
                   FROM battle_records WHERE battle_type = 'tournament'
                   AND created_at >= $1 AND created_at < $2""",
                day_start, day_end) or 0
            tourn_battle_bp = await pool.fetchval(
                """SELECT COALESCE(SUM(bp_earned), 0) FROM battle_records
                   WHERE battle_type = 'tournament' AND created_at >= $1 AND created_at < $2""",
                day_start, day_end) or 0
            if tourn_participants > 0:
                # 배틀 BP + 참가자 보상 추정 (참가자 * 평균 보상)
                import config as _cfg
                avg_reward = _cfg.TOURNAMENT_PRIZE_PARTICIPANT_BP  # 최소 보상 기준
                est_reward = int(tourn_participants * avg_reward) + int(tourn_battle_bp)
                bp_sources["tournament"] = {"earned": est_reward, "spent": 0}
                # tournament 배틀 BP는 battle에서 제거
                if "battle" in bp_sources:
                    bp_sources["battle"]["earned"] = max(0, bp_sources["battle"]["earned"] - int(tourn_battle_bp))
                    if bp_sources["battle"]["earned"] == 0:
                        del bp_sources["battle"]
        except Exception:
            pass
        bp_earned = sum(v["earned"] for v in bp_sources.values())
        if bp_earned == 0:
            bp_earned = await pool.fetchval(
                "SELECT COALESCE(SUM(bp_earned), 0) FROM battle_records WHERE created_at >= $1 AND created_at < $2",
                day_start, day_end) or 0
        bp_total_spent = 0

    # BP 소스별 카드 HTML 생성
    _bp_src_labels = {
        "battle": "⚔️ 배틀", "ranked_battle": "🏟️ 랭크전", "catch": "🎯 포획",
        "tournament": "🏆 토너먼트", "mission": "📋 미션", "bet_win": "🎲 야차(승)",
        "gacha_refund": "🎰 뽑기환급", "gacha_jackpot": "💎 뽑기잭팟",
        "ranked_reward": "🏅 시즌보상", "admin": "🔧 관리자",
        "shop_masterball": "🔴 상점(마볼)", "shop_hyperball": "🔵 상점(하볼)",
        "shop_gacha_ticket": "🎫 상점(뽑기권)", "shop_arcade_speed": "⚡ 상점(속도)",
        "shop_arcade_extend": "⏱️ 상점(연장)",
        "bet_refund": "🎲 야차(환불)", "trade_refund": "🔄 교환(환불)",
    }
    _bp_src_order = ["battle", "ranked_battle", "catch", "tournament", "mission", "bet_win",
                     "gacha_refund", "gacha_jackpot", "ranked_reward", "admin"]
    _bp_src_cards = []
    for _src in _bp_src_order:
        if _src in bp_sources and bp_sources[_src]["earned"] > 0:
            _lbl = _bp_src_labels.get(_src, _src)
            _val = bp_sources[_src]["earned"]
            _bp_src_cards.append(
                f'<div class="card"><div class="label">{_lbl}</div>'
                f'<div class="value" style="font-size:18px;color:#4caf50">+{_val:,}</div></div>')
    for _src, _v in sorted(bp_sources.items(), key=lambda x: x[1]["earned"], reverse=True):
        if _src not in _bp_src_order and _v["earned"] > 0:
            _lbl = _bp_src_labels.get(_src, _src)
            _bp_src_cards.append(
                f'<div class="card"><div class="label">{_lbl}</div>'
                f'<div class="value" style="font-size:18px;color:#4caf50">+{_v["earned"]:,}</div></div>')
    if _bp_src_cards:
        _cols = "1fr 1fr 1fr" if len(_bp_src_cards) >= 3 else "1fr " * len(_bp_src_cards)
        bp_source_cards_html = (
            f'<div style="margin-top:6px;font-size:11px;color:#888;margin-bottom:4px">📈 소스별 생성</div>'
            f'<div class="grid" style="grid-template-columns:{_cols.strip()}">'
            + "".join(_bp_src_cards) + '</div>')
    else:
        bp_source_cards_html = ""

    # 뽑기 데이터
    gacha_row = await pool.fetchrow(
        "SELECT COALESCE(SUM(bp_spent), 0) as total, COUNT(*) as pulls FROM gacha_log WHERE created_at >= $1 AND created_at < $2",
        day_start, day_end)
    gacha_spent = int(gacha_row["total"]) if gacha_row else 0
    gacha_pulls = int(gacha_row["pulls"]) if gacha_row else 0
    # bp_log 없으면 gacha 소비를 bp_total_spent에 반영
    if not bp_log_exists or bp_total_spent == 0:
        bp_total_spent = max(bp_total_spent, gacha_spent)

    market_new = await pool.fetchval(
        "SELECT COUNT(*) FROM market_listings WHERE created_at >= $1 AND created_at < $2",
        day_start, day_end) or 0
    market_sold = await pool.fetchval(
        "SELECT COUNT(*) FROM market_listings WHERE sold_at >= $1 AND sold_at < $2 AND status = 'sold'",
        day_start, day_end) or 0

    sub_active = await pool.fetchval("SELECT COUNT(*) FROM subscriptions WHERE is_active = 1") or 0
    sub_revenue = await pool.fetchval(
        """SELECT COALESCE(SUM(amount_usd), 0) FROM subscription_payments
           WHERE status = 'confirmed' AND confirmed_at >= $1 AND confirmed_at < $2""",
        day_start, day_end) or 0

    eco_mb = await pool.fetchval("SELECT COALESCE(SUM(master_balls), 0) FROM users") or 0
    eco_hb = await pool.fetchval("SELECT COALESCE(SUM(hyper_balls), 0) FROM users") or 0
    bp_circulation = await pool.fetchval(
        "SELECT COALESCE(SUM(battle_points), 0) FROM users WHERE battle_points > 0") or 0
    bp_avg = await pool.fetchval(
        "SELECT COALESCE(AVG(battle_points), 0) FROM users WHERE battle_points > 0") or 0
    bp_avg = round(float(bp_avg), 1)

    # 전일 BP 유통량 (스냅샷에서)
    prev_bp_snap = await pool.fetchrow(
        "SELECT bp_circulation, bp_earned FROM kpi_daily_snapshots WHERE date = $1",
        (day_start - timedelta(days=1)).date() if hasattr(day_start, 'date') else prev_start.date())
    prev_bp_circulation = int(prev_bp_snap["bp_circulation"]) if prev_bp_snap and prev_bp_snap["bp_circulation"] else None
    prev_bp_earned = int(prev_bp_snap["bp_earned"]) if prev_bp_snap and prev_bp_snap["bp_earned"] else 0

    # Top 채널
    top_chats = await pool.fetch(
        """SELECT cr.chat_title, cr.member_count, COUNT(sl.id) as today_spawns
           FROM chat_rooms cr
           LEFT JOIN spawn_log sl ON sl.chat_id = cr.chat_id
               AND sl.spawned_at >= $1 AND sl.spawned_at < $2
           GROUP BY cr.chat_id, cr.chat_title, cr.member_count
           ORDER BY today_spawns DESC LIMIT 3""",
        day_start, day_end)

    # 시간대별 활성
    hourly_rows = await pool.fetch(
        """SELECT EXTRACT(HOUR FROM attempted_at AT TIME ZONE 'Asia/Seoul')::int as hr,
                  COUNT(DISTINCT user_id) as users
           FROM catch_attempts
           WHERE attempted_at >= $1 AND attempted_at < $2
           GROUP BY hr ORDER BY hr""",
        day_start, day_end)
    hourly = {r["hr"]: r["users"] for r in hourly_rows}

    # 전일 데이터 (간단히)
    prev_dau = await pool.fetchval(
        "SELECT COUNT(DISTINCT user_id) FROM catch_attempts WHERE attempted_at >= $1 AND attempted_at < $2",
        prev_start, day_start) or 0
    prev_spawn_row = await pool.fetchrow(
        """SELECT COUNT(*) as spawns, COUNT(caught_by_user_id) as catches
           FROM spawn_log WHERE spawned_at >= $1 AND spawned_at < $2""",
        prev_start, day_start)
    prev_spawns = prev_spawn_row["spawns"] if prev_spawn_row else 0
    prev_catches = prev_spawn_row["catches"] if prev_spawn_row else 0
    prev_battles = await pool.fetchval(
        "SELECT COUNT(*) FROM battle_records WHERE created_at >= $1 AND created_at < $2",
        prev_start, day_start) or 0
    prev_new = await pool.fetchval(
        "SELECT COUNT(*) FROM users WHERE registered_at >= $1 AND registered_at < $2",
        prev_start, day_start) or 0
    prev_shiny = await pool.fetchval(
        """SELECT COUNT(*) FROM spawn_log
           WHERE spawned_at >= $1 AND spawned_at < $2 AND is_shiny = 1 AND caught_by_user_id IS NOT NULL""",
        prev_start, day_start) or 0

    # 전일 대비 섹션
    delta_html = f"""
<div class="section">
<div class="section-title">📊 전일 대비</div>
<div class="grid grid-3">
<div class="card"><div class="label">DAU</div><div class="value">{dau}</div>{delta_badge(dau, prev_dau)}</div>
<div class="card"><div class="label">스폰</div><div class="value">{spawns:,}</div>{delta_badge(spawns, prev_spawns)}</div>
<div class="card"><div class="label">포획</div><div class="value">{catches:,}</div>{delta_badge(catches, prev_catches)}</div>
<div class="card"><div class="label">배틀</div><div class="value">{battles}</div>{delta_badge(battles, prev_battles)}</div>
<div class="card"><div class="label">신규가입</div><div class="value">{new_users}</div>{delta_badge(new_users, prev_new)}</div>
<div class="card"><div class="label">이로치</div><div class="value">{shiny_caught}</div>{delta_badge(shiny_caught, prev_shiny)}</div>
</div></div>"""

    # 패치 섹션
    patches = get_patches_for_date(target_date)
    if patches:
        patch_items = ""
        feat_count = sum(1 for p in patches if p.startswith("feat:"))
        fix_count = sum(1 for p in patches if p.startswith("fix:"))
        for p in patches[:10]:
            prefix = p.split(":")[0]
            emoji = "🆕" if prefix == "feat" else "🔧" if prefix == "fix" else "♻️"
            msg = p.split(":", 1)[1].strip() if ":" in p else p
            patch_items += f'<div style="display:flex;gap:6px;align-items:start;margin-bottom:6px;font-size:13px"><span>{emoji}</span><span>{msg}</span></div>'
        if len(patches) > 10:
            patch_items += f'<div style="font-size:12px;color:#888">외 {len(patches) - 10}건</div>'
        patch_html = f"""
<div class="section">
<div class="section-title">🛠️ 패치 ({feat_count} feat / {fix_count} fix)</div>
{patch_items}
</div>"""
    else:
        patch_html = '<div class="section"><div class="section-title">🛠️ 패치</div><div style="font-size:13px;color:#888">배포 없음</div></div>'

    # 마일스톤 로드
    milestones_today = []
    milestones_recent = []
    try:
        import json as _json
        ms_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "milestones.json")
        with open(ms_path, "r", encoding="utf-8") as f:
            all_ms = _json.load(f)
        for ms in all_ms:
            if ms["date"] == target_date:
                milestones_today.append(ms)
            ms_dt = datetime.strptime(ms["date"], "%Y-%m-%d")
            if 0 < (dt - ms_dt).days <= 7:
                milestones_recent.append(ms)
    except Exception:
        pass

    # 인사이트
    insights = []

    # 오늘 마일스톤
    for ms in milestones_today:
        tag_emoji = {"content": "🎮", "system": "⚙️", "balance": "⚖️", "monetization": "💎", "event": "🎪"}.get(ms["tag"], "📌")
        insights.append(f"{tag_emoji} <b>오늘 마일스톤:</b> {ms['title']}")

    # 최근 마일스톤 영향 분석
    dau_diff = dau - prev_dau
    if milestones_recent:
        recent_titles = [ms["title"] for ms in milestones_recent[:3]]
        context_str = " / ".join(recent_titles)
        if dau_diff > 0:
            insights.append(f"DAU +{dau_diff}명 증가. 최근 주요 업데이트({context_str}) 영향 가능성.")
        elif dau_diff < 0:
            insights.append(f"DAU {dau_diff}명 감소. 최근 업데이트({context_str}) 후 안정화 구간 또는 추가 조치 필요.")
    else:
        if dau_diff > 0 and patches:
            insights.append(f"DAU +{dau_diff}명 증가. 오늘 패치({len(patches)}건)의 긍정적 영향 가능성.")
        elif dau_diff < 0:
            insights.append(f"DAU {dau_diff}명 감소. 자연 이탈 또는 콘텐츠 소진 모니터링 필요.")

    if prev_catches and catches:
        prev_rate = round(prev_catches / max(prev_spawns, 1) * 100, 1)
        if abs(catch_rate - prev_rate) > 3:
            insights.append(f"포획률 {prev_rate}% → {catch_rate}% ({'상승' if catch_rate > prev_rate else '하락'}). 밸런스 패치 영향 확인.")
    if battles == 0 and dau > 0:
        insights.append("배틀 0건 — 매칭 시스템 또는 동기 부여 점검 필요.")

    # BP 경제 인사이트
    bp_net = int(bp_earned) - int(bp_total_spent)
    source_labels = _bp_src_labels

    insights.append("💰 <b>BP 경제:</b>")

    # 유통량 + 전일 대비
    circ_delta_str = ""
    if prev_bp_circulation is not None and prev_bp_circulation > 0:
        circ_diff = bp_circulation - prev_bp_circulation
        circ_pct = round(circ_diff / prev_bp_circulation * 100, 1)
        circ_delta_str = f" ({circ_diff:+,}, {circ_pct:+.1f}%)"
    insights.append(
        f"  └ 총 유통량 <b>{int(bp_circulation):,}</b>BP{circ_delta_str}, "
        f"보유자 평균 {int(bp_avg):,}BP")

    if bp_earned > 0 or bp_total_spent > 0:
        insights.append(
            f"  └ 당일 생성 <b>+{int(bp_earned):,}</b> / 소각 <b>-{int(bp_total_spent):,}</b> / "
            f"순변동 <b>{bp_net:+,}</b>BP")

        # 전일 대비 생성량 변화
        if prev_bp_earned > 0:
            earn_diff = int(bp_earned) - prev_bp_earned
            earn_pct = round(earn_diff / max(prev_bp_earned, 1) * 100, 1)
            if abs(earn_pct) > 10:
                insights.append(
                    f"  └ BP 생성 전일 대비 {earn_pct:+.1f}% "
                    f"({'📈 증가' if earn_diff > 0 else '📉 감소'})")

    # 소스별 상세
    if bp_sources:
        earn_parts = []
        spend_parts = []
        for src, vals in sorted(bp_sources.items(), key=lambda x: x[1]["earned"], reverse=True):
            label = source_labels.get(src, src)
            if vals["earned"] > 0:
                earn_parts.append(f"{label} +{vals['earned']:,}")
            if vals["spent"] > 0:
                spend_parts.append(f"{label} -{vals['spent']:,}")
        if earn_parts:
            insights.append(f"  └ 📈 <b>생성:</b> {' / '.join(earn_parts[:6])}")
        if spend_parts:
            insights.append(f"  └ 📉 <b>소각:</b> {' / '.join(spend_parts[:5])}")

    # 소각률
    if bp_total_spent > 0 and bp_earned > 0:
        sink_ratio = round(int(bp_total_spent) / max(int(bp_earned), 1) * 100, 1)
        if sink_ratio > 150:
            insights.append(f"  └ 🔴 소각률 {sink_ratio}% — 디플레이션 위험")
        elif sink_ratio > 100:
            insights.append(f"  └ 🟡 소각률 {sink_ratio}% — 건전한 싱크 작동 ✓")
        else:
            insights.append(f"  └ 🟢 소각률 {sink_ratio}% — 생성 우세")

    # 1인당 경제
    if dau > 0:
        bp_per_dau = round(bp_circulation / dau, 0)
        earn_per_dau = round(int(bp_earned) / dau, 1) if bp_earned > 0 else 0
        insights.append(
            f"  └ 👤 DAU당 보유 {bp_per_dau:,.0f}BP, 생성 +{earn_per_dau:.0f}")

    # 뽑기 분석
    if gacha_pulls > 0:
        avg_cost = gacha_spent // max(gacha_pulls, 1)
        gacha_per_dau = round(gacha_pulls / max(dau, 1), 1)
        insights.append(
            f"🎰 <b>뽑기:</b> {gacha_pulls:,}회 ({gacha_spent:,}BP), "
            f"회당 {avg_cost}BP, DAU당 {gacha_per_dau:.1f}회")

    insight_html = ""
    if insights:
        items = "".join(f'<li style="margin-bottom:6px;font-size:13px">{ins}</li>' for ins in insights)
        insight_html = f"""
<div class="section">
<div class="section-title">💡 인사이트</div>
<ul style="list-style:none;padding:0">{items}</ul>
</div>"""

    # 시간대별 활성 그래프
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
            bars += (
                f'<div style="display:flex;flex-direction:column;align-items:center;flex:1;min-width:0">'
                f'<div style="width:100%;background:{bar_color};height:{max(pct, 2)}px;border-radius:2px 2px 0 0;min-height:2px"></div>'
                f'<div style="font-size:9px;{label_style};margin-top:2px">{hr}</div>'
                f'</div>'
            )
        hourly_html = f"""
<div class="section">
<div class="section-title">🕐 시간대별 활성 (피크: {peak_hr}시, {hourly.get(peak_hr, 0)}명)</div>
<div style="display:flex;gap:1px;align-items:flex-end;height:80px;padding:0 4px">{bars}</div>
</div>"""

    # Top 채널
    top_html = ""
    if top_chats:
        items = ""
        for i, ch in enumerate(top_chats, 1):
            title = (ch.get("chat_title") or "?")[:15]
            members = ch.get("member_count", 0)
            items += f'<li><span class="rank">{i}</span><span>{title}</span><span class="cnt">{ch["today_spawns"]}회 · {members}명</span></li>'
        top_html = f'<div class="section"><div class="section-title">📈 Top 채널 (스폰 기준)</div><ul class="channel-list">{items}</ul></div>'

    body = f"""
{delta_html}

<div class="section">
<div class="section-title">👥 유저</div>
<div class="grid grid-3">
<div class="card"><div class="label">DAU</div><div class="value accent">{dau}</div></div>
<div class="card"><div class="label">신규가입</div><div class="value">{new_users}</div></div>
<div class="card"><div class="label">총 유저</div><div class="value">{total_users}</div></div>
</div></div>

<div class="section">
<div class="section-title">🎯 스폰 / 포획</div>
<div class="grid">
<div class="card"><div class="label">총 스폰</div><div class="value">{spawns:,}</div></div>
<div class="card"><div class="label">포획</div><div class="value accent">{catches:,}</div><div class="sub">포획률 {catch_rate}%</div></div>
<div class="card"><div class="label">이로치 포획</div><div class="value" style="color:#ff9800">{shiny_caught}</div></div>
<div class="card"><div class="label">마스터볼 사용</div><div class="value">{mb_used}</div></div>
</div></div>

<div class="section">
<div class="section-title">⚔️ 배틀</div>
<div class="grid grid-3">
<div class="card"><div class="label">총 배틀</div><div class="value">{battles}</div></div>
<div class="card"><div class="label">랭크전</div><div class="value">{ranked_battles}</div></div>
<div class="card"><div class="label">BP 생성</div><div class="value">+{int(bp_earned):,}</div></div>
</div></div>

<div class="section">
<div class="section-title">💰 BP 흐름 (당일)</div>
<div class="grid grid-3">
<div class="card"><div class="label">생성</div><div class="value" style="color:#4caf50">+{int(bp_earned):,}</div></div>
<div class="card"><div class="label">소각</div><div class="value accent">-{int(bp_total_spent):,}</div></div>
<div class="card"><div class="label">순변동</div><div class="value" style="color:{'#4caf50' if bp_net >= 0 else '#e53935'}">{bp_net:+,}</div></div>
</div>
{bp_source_cards_html}
<div class="grid" style="margin-top:6px">
<div class="card"><div class="label">총 유통량</div><div class="value">{int(bp_circulation):,}</div>{delta_badge(bp_circulation, prev_bp_circulation) if prev_bp_circulation else ''}<div class="sub">보유자 평균 {int(bp_avg):,}BP</div></div>
<div class="card"><div class="label">뽑기</div><div class="value">{gacha_pulls:,}회</div><div class="sub">-{gacha_spent:,}BP</div></div>
</div></div>

<div class="section">
<div class="section-title">💰 경제</div>
<div class="grid">
<div class="card"><div class="label">마스터볼 보유</div><div class="value">{eco_mb}</div></div>
<div class="card"><div class="label">하이퍼볼 보유</div><div class="value">{eco_hb}</div></div>
<div class="card"><div class="label">거래소</div><div class="value">{market_sold}</div><div class="sub">신규 {market_new}건</div></div>
<div class="card"><div class="label">구독 매출</div><div class="value accent">${float(sub_revenue):.1f}</div><div class="sub">활성 {sub_active}명</div></div>
</div></div>

{hourly_html}
{top_html}
{patch_html}
{insight_html}"""

    date_str = f"{target_date} ({weekday})"
    html = HTML_TEMPLATE.format(title="📊 일일 KPI 리포트", date_str=date_str, body=body)
    filename = f"kpi_daily_{target_date.replace('-', '')}.html"

    buf = io.BytesIO(html.encode("utf-8"))
    buf.name = filename
    bot = Bot(token=BOT_TOKEN)
    await bot.send_document(chat_id=ADMIN_ID, document=buf, caption=f"📊 일일 KPI 리포트 — {date_str}")
    print(f"Daily KPI report sent for {date_str}!")

asyncio.run(main())
