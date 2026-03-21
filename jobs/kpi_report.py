"""KPI 리포트 생성 및 발송 — 일일/주간."""

import asyncio
import io
import logging
import os
from datetime import datetime, timedelta

import config
from database.connection import get_db
from database import kpi_queries

logger = logging.getLogger(__name__)


def _kpi_html_template(title: str, body: str, date_str: str) -> str:
    """KPI 리포트용 HTML 템플릿."""
    return f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f0f2f5;color:#1a1a2e;padding:12px;line-height:1.4;font-size:12px}}
.report{{max-width:640px;margin:0 auto;background:#fff;border-radius:12px;box-shadow:0 2px 12px rgba(0,0,0,.06);overflow:hidden}}
.header{{background:linear-gradient(135deg,#e53935,#ff6f61);color:#fff;padding:16px 20px;text-align:center}}
.header h1{{font-size:16px;font-weight:700;margin-bottom:2px}}
.header .date{{font-size:12px;opacity:.85}}
.body{{padding:12px 16px}}
.section{{margin-bottom:12px}}
.section-title{{font-size:13px;font-weight:700;color:#e53935;margin-bottom:6px;display:flex;align-items:center;gap:6px;border-bottom:1.5px solid #fce4ec;padding-bottom:4px}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:6px}}
.grid-3{{grid-template-columns:1fr 1fr 1fr}}
.grid-4{{grid-template-columns:1fr 1fr 1fr 1fr}}
.card{{background:#fafafa;border-radius:6px;padding:8px 6px;text-align:center;border:1px solid #f0f0f0}}
.card .label{{font-size:10px;color:#888;margin-bottom:2px;letter-spacing:.3px}}
.card .value{{font-size:16px;font-weight:700;color:#1a1a2e}}
.card .value.accent{{color:#e53935}}
.card .sub{{font-size:10px;color:#999;margin-top:1px}}
.channel-list{{list-style:none}}
.channel-list li{{display:flex;justify-content:space-between;align-items:center;padding:4px 8px;border-radius:4px;margin-bottom:2px;background:#fafafa;font-size:11px}}
.channel-list li:nth-child(1){{background:#fff3e0;font-weight:600}}
.channel-list li:nth-child(2){{background:#fce4ec}}
.channel-list .rank{{font-weight:700;color:#e53935;min-width:20px}}
.channel-list .cnt{{color:#666;font-size:11px}}
.row{{display:flex;gap:6px;margin-bottom:4px;font-size:11px}}
.row .tag{{background:#fafafa;border-radius:4px;padding:3px 8px;border:1px solid #f0f0f0;white-space:nowrap}}
.row .tag b{{color:#e53935}}
.footer{{text-align:center;padding:10px;color:#aaa;font-size:10px;border-top:1px solid #f0f0f0}}
</style></head><body>
<div class="report">
<div class="header"><h1>{title}</h1><div class="date">{date_str}</div></div>
<div class="body">{body}</div>
<div class="footer">TGPoke KPI Report &mdash; auto-generated</div>
</div></body></html>"""


def _delta_badge(today, yesterday, suffix="", reverse=False):
    """전일 대비 변화 뱃지 HTML. reverse=True면 감소가 긍정(예: 마볼 소비)."""
    if yesterday is None or yesterday == 0:
        return ""
    diff = today - yesterday
    pct = round(diff / yesterday * 100)
    if diff == 0:
        return '<span style="color:#888;font-size:11px">→ 0%</span>'
    color = "#4caf50" if (diff > 0) != reverse else "#e53935"
    arrow = "▲" if diff > 0 else "▼"
    return f'<span style="color:{color};font-size:11px;font-weight:600">{arrow} {abs(pct)}%{suffix}</span>'


async def _build_abuse_report_section(interval: str = "1 day") -> str:
    """어뷰저 의심 유저 섹션 HTML 생성. 시간당 과다포획 기준."""
    try:
        pool = await get_db()
        # 해당 기간 내 포획시도 상위 유저 (시간당 50회 이상 기록 있는 유저)
        suspects = await pool.fetch(
            f"""SELECT ca.user_id, u.display_name, u.username,
                       COUNT(*) as total_attempts,
                       COUNT(CASE WHEN ss.is_shiny = 1 THEN 1 END) as shiny_catches,
                       COUNT(CASE WHEN ss.caught_by_user_id = ca.user_id THEN 1 END) as successful,
                       a.total_challenges, a.challenge_passes, a.challenge_fails
                FROM catch_attempts ca
                JOIN users u ON ca.user_id = u.user_id
                JOIN spawn_sessions ss ON ca.session_id = ss.id
                LEFT JOIN abuse_scores a ON ca.user_id = a.user_id
                WHERE ca.attempted_at > NOW() - interval '{interval}'
                GROUP BY ca.user_id, u.display_name, u.username,
                         a.total_challenges, a.challenge_passes, a.challenge_fails
                HAVING COUNT(*) >= 200
                ORDER BY COUNT(*) DESC LIMIT 10"""
        )
        if not suspects:
            return ""

        rows = ""
        for s in suspects:
            uid = s["user_id"]
            name = s["display_name"] or "?"
            uname = f"@{s['username']}" if s["username"] else ""
            total = s["total_attempts"]
            successful = s["successful"]
            shiny = s["shiny_catches"]
            ch_total = s["total_challenges"] or 0
            ch_pass = s["challenge_passes"] or 0
            ch_fail = s["challenge_fails"] or 0

            # 해당 기간 획득 BP
            bp_earned = await pool.fetchval(
                f"SELECT COALESCE(SUM(amount), 0) FROM bp_log WHERE user_id = $1 "
                f"AND source = 'catch' AND created_at > NOW() - interval '{interval}'",
                uid,
            )

            # 색상: 500+면 빨강, 300+면 주황
            color = "#e53935" if total >= 500 else "#ff9800" if total >= 300 else "#888"

            rows += (
                f'<div style="display:flex;align-items:center;gap:8px;padding:8px;'
                f'background:#1a1a2e;border-radius:6px;margin-bottom:6px">'
                f'<div style="flex:1;min-width:0">'
                f'<div style="font-size:13px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">'
                f'{name} <span style="color:#888;font-size:11px">{uname}</span></div>'
                f'<div style="display:flex;gap:6px;margin-top:4px;font-size:11px;color:#aaa">'
                f'<span>시도 {total:,}</span>'
                f'<span>포획 {successful:,}</span>'
                f'<span>이로치 {shiny}</span>'
                f'<span>BP +{bp_earned:,}</span>'
                f'<span>챌린지 {ch_total}(P{ch_pass}/F{ch_fail})</span>'
                f'</div></div>'
                f'<div style="text-align:right;min-width:60px">'
                f'<div style="font-size:16px;font-weight:700;color:{color}">{total:,}</div>'
                f'<div style="font-size:10px;color:#888">시도</div>'
                f'</div></div>'
            )

        return f"""
<div class="section">
<div class="section-title">🚨 과다포획 유저</div>
{rows}
</div>"""
    except Exception as e:
        logger.warning(f"_build_abuse_report_section error: {e}")
        return ""


def _bp_daily_chart(bp_daily: list[dict]) -> str:
    """주간 BP 뽑기 소비 일별 바 차트 HTML."""
    if not bp_daily:
        return ""
    weekdays = ["월", "화", "수", "목", "금", "토", "일"]
    max_spent = max((d.get("spent", 0) for d in bp_daily), default=1) or 1
    bars = ""
    for d in bp_daily:
        spent = d.get("spent", 0)
        pulls = d.get("pulls", 0)
        pct = round(spent / max_spent * 100)
        try:
            from datetime import datetime as _dt
            day_dt = _dt.strptime(d["date"], "%Y-%m-%d")
            day_label = weekdays[day_dt.weekday()]
            date_label = day_dt.strftime("%m/%d")
        except Exception:
            day_label = "?"
            date_label = d["date"][-5:]
        bars += (
            f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">'
            f'<span style="min-width:50px;font-size:12px;color:#888">{date_label}({day_label})</span>'
            f'<div style="background:linear-gradient(90deg,#e53935,#ff6f61);height:22px;border-radius:4px;width:{pct}%;min-width:2px"></div>'
            f'<span style="font-size:13px;font-weight:600">-{spent:,} ({pulls}회)</span>'
            f'</div>'
        )
    return f"""<div class="section">
<div class="section-title">🎰 일별 BP 뽑기 소비</div>
{bars}
</div>"""


def _get_today_patches() -> list[str]:
    """오늘 날짜의 git 커밋 메시지 목록 (feat/fix만), 주요 패치 우선 정렬."""
    import subprocess
    try:
        today_str = config.get_kst_now().strftime("%Y-%m-%d")
        result = subprocess.run(
            ["git", "log", f"--since={today_str} 00:00", f"--until={today_str} 23:59",
             "--pretty=format:%s", "--no-merges"],
            capture_output=True, text=True, timeout=5, cwd="/home/ubuntu/pokemon-bot",
        )
        lines = [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
        patches = [l for l in lines if any(l.startswith(p) for p in ("feat:", "fix:", "refactor:"))]
        # 주요 패치 우선 정렬: feat > fix > refactor, 내용이 긴 것(상세한 것) 우선
        def _patch_priority(p: str) -> tuple:
            prefix = p.split(":")[0]
            type_score = {"feat": 0, "fix": 1, "refactor": 2}.get(prefix, 3)
            msg = p.split(":", 1)[1].strip() if ":" in p else p
            # 주요 키워드 부스트
            boost = 0
            for kw in ("시스템", "추가", "도입", "신규", "개편", "리뉴얼", "엔진"):
                if kw in msg:
                    boost -= 1
            return (type_score + boost, -len(msg))
        patches.sort(key=_patch_priority)
        return patches
    except Exception:
        return []


async def _build_gen4_report_section(pool) -> str:
    """Gen4(4세대) 업데이트 전후 비교 섹션 HTML 생성. 업데이트일(2026-03-16) 이후에만 표시."""
    from datetime import timezone, timedelta as _td
    _KST = timezone(_td(hours=9))
    _now = config.get_kst_now()
    _today_start = _now.replace(hour=0, minute=0, second=0, microsecond=0)
    _today_end = _today_start + _td(days=1)
    _before_start = _today_start - _td(days=7)

    rarity_ko = {"common": "커먼", "rare": "레어", "epic": "에픽",
                  "legendary": "전설", "ultra_legendary": "초전설"}
    rarity_cls = {"common": "#888", "rare": "#2196f3", "epic": "#9c27b0",
                  "legendary": "#ff9800", "ultra_legendary": "#e53935"}

    # ── Gen4 스폰/포획 (오늘) ──
    g4_row = await pool.fetchrow(
        """SELECT COUNT(*) as s, COUNT(caught_by_user_id) as c
           FROM spawn_log WHERE spawned_at >= $1 AND spawned_at < $2
           AND pokemon_id >= 387 AND pokemon_id <= 493""",
        _today_start, _today_end)
    g4_spawns = g4_row["s"] if g4_row else 0
    g4_catches = g4_row["c"] if g4_row else 0
    g4_catch_rate = round(g4_catches / max(g4_spawns, 1) * 100, 1)

    total_row = await pool.fetchrow(
        "SELECT COUNT(*) as s FROM spawn_log WHERE spawned_at >= $1 AND spawned_at < $2",
        _today_start, _today_end)
    total_spawns = total_row["s"] if total_row else 1
    g4_pct = round(g4_spawns / max(total_spawns, 1) * 100, 1)

    # 7일 평균 (before)
    avg7_row = await pool.fetchrow(
        "SELECT COUNT(*)::float/7 as s, COUNT(caught_by_user_id)::float/7 as c FROM spawn_log WHERE spawned_at >= $1 AND spawned_at < $2",
        _before_start, _today_start)
    avg7_spawns = round(avg7_row["s"]) if avg7_row else 0
    avg7_catches = round(avg7_row["c"]) if avg7_row else 0
    avg7_rate = round(avg7_catches / max(avg7_spawns, 1) * 100, 1)

    # ── Gen4 인기 Top 10 ──
    g4_popular = await pool.fetch(
        """SELECT sl.pokemon_id, pm.name_ko, pm.rarity, COUNT(*) as cnt
           FROM spawn_log sl JOIN pokemon_master pm ON pm.id = sl.pokemon_id
           WHERE sl.spawned_at >= $1 AND sl.spawned_at < $2
           AND sl.pokemon_id >= 387 AND sl.pokemon_id <= 493
           AND sl.caught_by_user_id IS NOT NULL
           GROUP BY sl.pokemon_id, pm.name_ko, pm.rarity ORDER BY cnt DESC LIMIT 10""",
        _today_start, _today_end)

    popular_html = ""
    for i, p in enumerate(g4_popular, 1):
        r_color = rarity_cls.get(p["rarity"], "#888")
        r_name = rarity_ko.get(p["rarity"], p["rarity"])
        popular_html += (
            f'<div style="display:flex;justify-content:space-between;align-items:center;'
            f'padding:6px 10px;background:#fafafa;border-radius:6px;margin-bottom:3px;font-size:13px">'
            f'<span><b style="color:#e53935;margin-right:6px">{i}</b>'
            f'#{p["pokemon_id"]} <b>{p["name_ko"]}</b> '
            f'<span style="color:{r_color};font-size:11px">{r_name}</span></span>'
            f'<span style="font-weight:700">{p["cnt"]}마리</span></div>')
    if not popular_html:
        popular_html = '<div style="font-size:13px;color:#888;text-align:center;padding:12px">아직 포획 데이터 없음</div>'

    # ── Gen4 레어리티 분포 ──
    g4_rarity = await pool.fetch(
        """SELECT pm.rarity, COUNT(*) as cnt
           FROM spawn_log sl JOIN pokemon_master pm ON pm.id = sl.pokemon_id
           WHERE sl.spawned_at >= $1 AND sl.spawned_at < $2
           AND sl.pokemon_id >= 387 AND sl.pokemon_id <= 493
           GROUP BY pm.rarity ORDER BY cnt DESC""",
        _today_start, _today_end)
    g4_rarity_map = {r["rarity"]: r["cnt"] for r in g4_rarity}
    g4_total = sum(g4_rarity_map.values()) or 1

    rarity_bars = ""
    for rk in ["common", "rare", "epic", "legendary", "ultra_legendary"]:
        cnt = g4_rarity_map.get(rk, 0)
        pct = round(cnt / g4_total * 100, 1)
        color = rarity_cls.get(rk, "#888")
        rarity_bars += (
            f'<div style="display:flex;align-items:center;gap:6px;margin-bottom:3px">'
            f'<span style="min-width:50px;font-size:11px;color:{color};font-weight:700;text-align:right">{rarity_ko.get(rk, rk)}</span>'
            f'<div style="flex:1;height:16px;background:#f5f5f5;border-radius:3px;overflow:hidden">'
            f'<div style="height:100%;width:{pct}%;background:{color};border-radius:3px;opacity:.7"></div></div>'
            f'<span style="font-size:11px;min-width:60px">{cnt:,} ({pct}%)</span></div>')

    # ── Gen4 보유 현황 ──
    g4_owners = await pool.fetchval(
        "SELECT COUNT(DISTINCT user_id) FROM user_pokemon WHERE pokemon_id >= 387 AND pokemon_id <= 493") or 0
    g4_total_owned = await pool.fetchval(
        "SELECT COUNT(*) FROM user_pokemon WHERE pokemon_id >= 387 AND pokemon_id <= 493") or 0
    g4_shiny = await pool.fetchval(
        "SELECT COUNT(*) FROM user_pokemon WHERE pokemon_id >= 387 AND pokemon_id <= 493 AND is_shiny = true") or 0

    # ── Gen4 전설/초전설 ──
    g4_legends = await pool.fetch(
        """SELECT pm.name_ko, pm.rarity, COUNT(*) as cnt
           FROM user_pokemon up JOIN pokemon_master pm ON pm.id = up.pokemon_id
           WHERE up.pokemon_id >= 387 AND up.pokemon_id <= 493
           AND pm.rarity IN ('legendary', 'ultra_legendary')
           GROUP BY pm.name_ko, pm.rarity ORDER BY pm.rarity DESC, cnt DESC""")
    legend_items = ""
    for p in g4_legends:
        r_color = rarity_cls.get(p["rarity"], "#888")
        r_name = rarity_ko.get(p["rarity"], "")
        legend_items += (
            f'<span style="display:inline-block;padding:3px 8px;background:#fafafa;border-radius:6px;'
            f'margin:2px;font-size:12px;border:1px solid #f0f0f0">'
            f'<b style="color:{r_color}">{p["name_ko"]}</b> ×{p["cnt"]}</span>')
    if not legend_items:
        legend_items = '<span style="font-size:12px;color:#888">아직 포획 기록 없음</span>'

    # ── 세대별 도감 현황 ──
    dex_stats = await pool.fetch(
        """SELECT
             CASE WHEN pokemon_id <= 151 THEN 1 WHEN pokemon_id <= 251 THEN 2
                  WHEN pokemon_id <= 386 THEN 3 ELSE 4 END as gen,
             COUNT(DISTINCT pokemon_id) as species, COUNT(*) as total
           FROM user_pokemon GROUP BY gen ORDER BY gen""")
    gen_totals = {1: 151, 2: 100, 3: 135, 4: 107}
    dex_cards = ""
    for row in dex_stats:
        g = row["gen"]
        total = gen_totals.get(g, 0)
        species = row["species"]
        comp = round(species / max(total, 1) * 100, 1)
        is_g4 = g == 4
        style = 'border:2px solid #e53935' if is_g4 else ''
        dex_cards += (
            f'<div class="card" style="{style}">'
            f'<div class="label">{"🌟 " if is_g4 else ""}{g}세대</div>'
            f'<div class="value" style="font-size:18px;{"color:#e53935" if is_g4 else ""}">{species}/{total}</div>'
            f'<div class="sub">{comp}% · {row["total"]:,}마리</div></div>')

    # ── 조립 ──
    section = f"""
<div class="section" style="border:2px solid #e8eaf6;border-radius:12px;padding:16px;margin-bottom:20px;background:linear-gradient(135deg,#fafafa,#f3e5f5 50%,#e8eaf6)">
<div class="section-title" style="color:#4a148c;border-bottom-color:#ce93d8">🌟 v3.0 — 4세대(신오) 업데이트 보고서</div>

<div style="font-size:12px;color:#666;margin-bottom:12px;padding:8px;background:rgba(255,255,255,.7);border-radius:6px">
📌 <b>업데이트 내용:</b> 107종 추가(387~493), 분기진화 2종, 크로스세대 진화 18종, 한카리아스/레지기가스 에픽 조정, 커스텀이모지 전면 적용, 챌린지 3분
</div>

<div style="font-size:11px;color:#888;margin-bottom:8px">Before = 7일 평균 | After = 오늘 | Gen4 = 387~493번</div>

<div class="grid grid-3" style="margin-bottom:12px">
<div class="card"><div class="label">Gen4 스폰</div><div class="value accent">{g4_spawns:,}</div><div class="sub">전체의 {g4_pct}%</div></div>
<div class="card"><div class="label">Gen4 포획</div><div class="value" style="color:#4caf50">{g4_catches:,}</div><div class="sub">포획률 {g4_catch_rate}%</div></div>
<div class="card"><div class="label">Gen4 이로치</div><div class="value" style="color:#ff9800">{g4_shiny}</div></div>
</div>

<div class="grid" style="margin-bottom:12px">
<div class="card"><div class="label">포획률 변화</div><div class="value" style="font-size:16px">{avg7_rate}% → {g4_catch_rate}%</div><div class="sub">7일 평균 → Gen4</div></div>
<div class="card"><div class="label">Gen4 보유자</div><div class="value" style="color:#1565c0">{g4_owners:,}명</div><div class="sub">총 {g4_total_owned:,}마리</div></div>
</div>

<div style="margin-bottom:12px">
<div style="font-size:13px;font-weight:700;color:#4a148c;margin-bottom:6px">🏆 Gen4 인기 포켓몬 Top 10</div>
{popular_html}
</div>

<div style="margin-bottom:12px">
<div style="font-size:13px;font-weight:700;color:#4a148c;margin-bottom:6px">📊 Gen4 레어리티 분포</div>
{rarity_bars}
</div>

<div style="margin-bottom:12px">
<div style="font-size:13px;font-weight:700;color:#4a148c;margin-bottom:6px">👑 Gen4 전설 / 초전설</div>
<div>{legend_items}</div>
</div>

<div style="margin-bottom:8px">
<div style="font-size:13px;font-weight:700;color:#4a148c;margin-bottom:6px">📖 세대별 도감 현황</div>
<div class="grid" style="grid-template-columns:1fr 1fr 1fr 1fr">{dex_cards}</div>
</div>

</div>"""

    return section


async def _send_daily_kpi_report(context, target_date=None):
    """매일 23:55 KST: 일일 KPI 리포트 v2 — 유저 동향 중심. target_date로 특정 날짜 조회."""
    import io
    try:
        d = await kpi_queries.kpi_daily_snapshot(target_date=target_date)
        eco = d["economy"]

        if target_date:
            # 수동 트리거: 스냅샷 저장 스킵, 리텐션/전일 데이터 없음
            d1_ret = None
            d7_ret = None
            prev = await kpi_queries.get_previous_snapshot()
            today = target_date
        else:
            # 스냅샷 저장 + D+1/D+7 리텐션 계산
            retention = await kpi_queries.save_kpi_snapshot(d)
            d1_ret = retention.get("d1_retention")
            d7_ret = retention.get("d7_retention")
            prev = await kpi_queries.get_previous_snapshot()
            today = config.get_kst_now().replace(hour=0, minute=0, second=0, microsecond=0)

        catch_rate = d["catch_rate"]

        # ── v2 상세 데이터 수집 ──
        (
            new_users_detail, churned_users, top_users,
            shiny_catches, market_trends, battle_meta,
            sub_changes, chat_health, checkin_stats,
            new_user_sources,
        ) = await asyncio.gather(
            kpi_queries.report_new_users_detail(today),
            kpi_queries.report_churned_users(today),
            kpi_queries.report_top_active_users(today),
            kpi_queries.report_shiny_catches(today),
            kpi_queries.report_market_trends(today),
            kpi_queries.report_battle_meta(today),
            kpi_queries.report_subscription_changes(today),
            kpi_queries.report_chat_health(today),
            kpi_queries.report_checkin_stats(today),
            kpi_queries.report_new_user_sources(today),
        )

        # ── 핵심 DAU (출석/문유사랑해/방문) ──
        _pool = await get_db()
        _kst_today = today if isinstance(today, datetime) else datetime.strptime(str(today).split()[0], "%Y-%m-%d").replace(tzinfo=config.KST)
        _kst_end = _kst_today + timedelta(days=1)
        _checkin_users = await _pool.fetchval(
            "SELECT COUNT(DISTINCT user_id) FROM bp_log WHERE source = 'daily_checkin' AND created_at >= $1 AND created_at < $2",
            _kst_today, _kst_end) or 0
        _love_users = 0
        try:
            _love_users = await _pool.fetchval(
                "SELECT COUNT(DISTINCT user_id) FROM bp_purchase_log WHERE item = 'love_hidden_reward' AND purchased_at >= $1 AND purchased_at < $2",
                _kst_today, _kst_end) or 0
        except Exception:
            pass
        _visit_users = 0
        try:
            _cv_exists = await _pool.fetchval(
                "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name='camp_visits')")
            if _cv_exists:
                _visit_users = await _pool.fetchval(
                    "SELECT COUNT(DISTINCT user_id) FROM camp_visits WHERE visited_at = $1::date",
                    _kst_today) or 0
        except Exception:
            pass
        # union으로 핵심 DAU 계산
        _core_ids = set()
        for _src, _icol, _tbl, _tcol in [
            ("daily_checkin", "source", "bp_log", "created_at"),
        ]:
            _rows = await _pool.fetch(
                f"SELECT DISTINCT user_id FROM {_tbl} WHERE {_icol} = $1 AND {_tcol} >= $2 AND {_tcol} < $3",
                _src, _kst_today, _kst_end)
            _core_ids.update(r["user_id"] for r in _rows)
        try:
            _rows = await _pool.fetch(
                "SELECT DISTINCT user_id FROM bp_purchase_log WHERE item = 'love_hidden_reward' AND purchased_at >= $1 AND purchased_at < $2",
                _kst_today, _kst_end)
            _core_ids.update(r["user_id"] for r in _rows)
        except Exception:
            pass
        try:
            _cv_exists2 = await _pool.fetchval(
                "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name='camp_visits')")
            if _cv_exists2:
                _rows = await _pool.fetch(
                    "SELECT DISTINCT user_id FROM camp_visits WHERE visited_at = $1::date", _kst_today)
                _core_ids.update(r["user_id"] for r in _rows)
        except Exception:
            pass
        _core_dau = len(_core_ids)
        _core_dau_pct = round(_core_dau / max(d["dau"], 1) * 100) if d["dau"] else 0

        # ── 전일 대비 섹션 ──
        if prev:
            delta_html = f"""
<div class="section">
<div class="section-title">📊 전일 대비</div>
<div class="grid grid-3">
<div class="card"><div class="label">DAU</div><div class="value">{d['dau']}</div>{_delta_badge(d['dau'], prev.get('dau'))}</div>
<div class="card"><div class="label">스폰</div><div class="value">{d['spawns']:,}</div>{_delta_badge(d['spawns'], prev.get('spawns'))}</div>
<div class="card"><div class="label">포획</div><div class="value">{d['catches']:,}</div>{_delta_badge(d['catches'], prev.get('catches'))}</div>
<div class="card"><div class="label">배틀</div><div class="value">{d['battles']}</div>{_delta_badge(d['battles'], prev.get('battles'))}</div>
<div class="card"><div class="label">신규가입</div><div class="value">{d['new_users']}</div>{_delta_badge(d['new_users'], prev.get('new_users'))}</div>
<div class="card"><div class="label">이로치</div><div class="value">{d['shiny_caught']}</div>{_delta_badge(d['shiny_caught'], prev.get('shiny_caught'))}</div>
</div></div>"""
        else:
            delta_html = ""

        # ── 오늘 패치 섹션 ──
        patches = _get_today_patches()
        if patches:
            patch_items = ""
            feat_count = sum(1 for p in patches if p.startswith("feat:"))
            fix_count = sum(1 for p in patches if p.startswith("fix:"))
            # 중복 메시지 제거 (같은 기능 반복 커밋 시)
            seen_msgs = set()
            unique_patches = []
            for p in patches:
                msg = p.split(":", 1)[1].strip() if ":" in p else p
                # 핵심 키워드로 중복 판별 (앞 10자 기준)
                key = msg[:10]
                if key not in seen_msgs:
                    seen_msgs.add(key)
                    unique_patches.append(p)
            max_show = 5
            for p in unique_patches[:max_show]:
                prefix = p.split(":")[0]
                emoji = "🆕" if prefix == "feat" else "🔧" if prefix == "fix" else "♻️"
                msg = p.split(":", 1)[1].strip() if ":" in p else p
                patch_items += f'<div style="display:flex;gap:6px;align-items:start;margin-bottom:6px;font-size:13px"><span>{emoji}</span><span>{msg}</span></div>'
            remaining = len(patches) - max_show
            if remaining > 0:
                patch_items += f'<div style="font-size:12px;color:#888;margin-top:4px">외 {remaining}건</div>'
            patch_html = f"""
<div class="section">
<div class="section-title">🛠️ 오늘 패치 ({feat_count} feat / {fix_count} fix)</div>
{patch_items}
</div>"""
        else:
            patch_html = '<div class="section"><div class="section-title">🛠️ 오늘 패치</div><div style="font-size:13px;color:#888">배포 없음</div></div>'

        # ── 어뷰저 의심 유저 섹션 ──
        abuse_html = await _build_abuse_report_section("1 day")

        # ── Gen4 업데이트 보고서 섹션 ──
        gen4_html = ""
        try:
            # Gen4가 DB에 시딩되어 있을 때만 표시
            _pool = await get_db()
            g4_count = await _pool.fetchval(
                "SELECT COUNT(*) FROM pokemon_master WHERE id >= 387 AND id <= 493")
            if g4_count and g4_count >= 100:
                gen4_html = await _build_gen4_report_section(_pool)
        except Exception as _e:
            logger.warning(f"Gen4 report section skipped: {_e}")

        # ── 마일스톤 로드 ──
        milestones_today = []
        milestones_recent = []
        try:
            import json as _json
            ms_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "milestones.json")
            with open(ms_path, "r", encoding="utf-8") as f:
                all_ms = _json.load(f)
            today_str_ms = d["date"]
            from datetime import datetime as _dt, timedelta as _td
            for ms in all_ms:
                if ms["date"] == today_str_ms:
                    milestones_today.append(ms)
                # 최근 7일 이내 마일스톤
                ms_date = _dt.strptime(ms["date"], "%Y-%m-%d")
                today_date = _dt.strptime(today_str_ms, "%Y-%m-%d")
                if 0 < (today_date - ms_date).days <= 7:
                    milestones_recent.append(ms)
        except Exception:
            pass

        # ── 인사이트 섹션 ──
        insights = []

        # 오늘 마일스톤
        for ms in milestones_today:
            tag_emoji = {"content": "🎮", "system": "⚙️", "balance": "⚖️", "monetization": "💎", "event": "🎪"}.get(ms["tag"], "📌")
            insights.append(f"{tag_emoji} <b>오늘 마일스톤:</b> {ms['title']}")

        # ── 1. 유저 활성도 + 유입 소스 분석 ──
        new_users = d.get("new_users", 0)
        prev_new = prev.get("new_users", 0) if prev else 0
        if prev:
            dau_diff = d["dau"] - prev.get("dau", 0)
            dau_pct = round(dau_diff / max(prev.get("dau", 1), 1) * 100, 1)

            # DAU 변동 + 원인 추론
            if dau_diff > 0:
                cause_parts = []
                # 신규 유입 소스 분석
                if new_user_sources:
                    top_src = new_user_sources[0]
                    top_title = (top_src["chat_title"] or "?")[:15]
                    top_cnt = top_src["cnt"]
                    top_pct = round(top_cnt / max(new_users, 1) * 100)
                    if top_pct >= 30:
                        cause_parts.append(f"<b>{top_title}</b>에서 {top_cnt}명({top_pct}%) 유입")
                    if len(new_user_sources) >= 3:
                        cause_parts.append(f"총 {len(new_user_sources)}개 채널에서 유입")
                if milestones_recent:
                    recent_titles = [ms["title"] for ms in milestones_recent[:2]]
                    cause_parts.append(f"최근 업데이트({' / '.join(recent_titles)}) 효과")
                elif patches:
                    cause_parts.append(f"오늘 패치 {len(patches)}건 영향")

                cause_str = ". ".join(cause_parts) if cause_parts else "유입 원인 분석 필요"
                insights.append(
                    f"📈 <b>DAU +{dau_diff}명({dau_pct:+.1f}%)</b>, 신규 {new_users}명(전일 {prev_new}명). "
                    f"{cause_str}.")

                # 신규 급증 시 추가 인사이트
                if new_users > 0 and prev_new > 0:
                    new_growth = round((new_users - prev_new) / max(prev_new, 1) * 100)
                    if new_growth >= 50:
                        insights.append(
                            f"  └ 🚀 신규 가입 전일 대비 <b>+{new_growth}%</b> 급증. "
                            f"{'외부 채널 이벤트/바이럴 효과 확인.' if new_user_sources and new_user_sources[0]['cnt'] >= 10 else '업데이트 효과 추정.'}")

            elif dau_diff < 0:
                if milestones_recent:
                    context_str = " / ".join(ms["title"] for ms in milestones_recent[:2])
                    insights.append(
                        f"📉 <b>DAU {dau_diff}명({dau_pct:+.1f}%)</b>. "
                        f"최근 업데이트({context_str}) 이후 안정화 구간. "
                        f"신규 {new_users}명(전일 {prev_new}명).")
                else:
                    insights.append(
                        f"📉 <b>DAU {dau_diff}명({dau_pct:+.1f}%)</b>. "
                        f"신규 {new_users}명(전일 {prev_new}명). "
                        f"{'콘텐츠 소진 구간 — 신규 콘텐츠 투입 검토.' if abs(dau_diff) > 10 else '자연 변동 범위.'}")
            else:
                insights.append(f"📊 DAU 전일 동일({d['dau']}명). 신규 {new_users}명.")

        # 신규 유저 전환율 분석
        if new_users_detail and new_users >= 5:
            active_new = sum(1 for u in new_users_detail if u["catches"] > 0)
            battled_new = sum(1 for u in new_users_detail if u["battles"] > 0)
            activation_rate = round(active_new / max(new_users, 1) * 100)
            battle_rate = round(battled_new / max(new_users, 1) * 100)
            insights.append(
                f"🆕 <b>신규 전환율:</b> 포획 {activation_rate}%({active_new}명), "
                f"배틀 {battle_rate}%({battled_new}명)")
            if activation_rate < 50:
                insights.append("  └ ⚠️ 포획 전환 50% 미만 — 첫 경험 온보딩 개선 필요.")
            if battle_rate < 10 and active_new >= 10:
                insights.append("  └ 💡 포획→배틀 전환 낮음 — 배틀 유도 튜토리얼/보상 강화 고려.")

        # ── 2. 리텐션 분석 ──
        if d1_ret is not None or d7_ret is not None:
            ret_parts = []
            if d1_ret is not None:
                d1_status = "🟢" if d1_ret >= 70 else "🟡" if d1_ret >= 50 else "🔴"
                ret_parts.append(f"D+1 {d1_ret}%{d1_status}")
            if d7_ret is not None:
                d7_status = "🟢" if d7_ret >= 40 else "🟡" if d7_ret >= 25 else "🔴"
                ret_parts.append(f"D+7 {d7_ret}%{d7_status}")
            ret_str = " / ".join(ret_parts)
            insights.append(f"🔄 <b>리텐션:</b> {ret_str}")
            if d1_ret is not None and d1_ret < 50:
                insights.append("  └ D+1 50% 미만 — 첫날 경험 개선 또는 복귀 인센티브 검토.")
            if d7_ret is not None and d7_ret >= 40:
                insights.append("  └ D+7 40%+ — 핵심 루프 건재. 장기 콘텐츠 타이밍.")

        # ── 3. 포획/배틀 활성도 ──
        if prev:
            catch_prev = prev.get("catches", 0)
            battle_prev = prev.get("battles", 0)

            # 포획률 변동
            if catch_prev and d["catches"]:
                prev_rate = round(catch_prev / max(prev.get("spawns", 1), 1) * 100, 1)
                rate_diff = round(catch_rate - prev_rate, 1)
                if abs(rate_diff) > 2:
                    direction = "상승" if rate_diff > 0 else "하락"
                    reason = ""
                    if rate_diff > 5 and new_users >= 10:
                        reason = " 신규 유저 대량 유입으로 경쟁 완화 추정."
                    elif rate_diff < -5:
                        reason = " 스폰 대비 활성 유저 부족 또는 이벤트 종료."
                    insights.append(
                        f"🎯 <b>포획률 {prev_rate}% → {catch_rate}%({rate_diff:+.1f}%p)</b>. "
                        f"스폰 {d['spawns']}회 중 {d['catches']}회 포획.{reason}")

            # 배틀 활성도
            if d["battles"] > 0:
                if battle_prev:
                    bt_diff = d["battles"] - battle_prev
                    bt_pct = round(bt_diff / max(battle_prev, 1) * 100, 1)
                    if abs(bt_pct) > 20:
                        if bt_diff > 0:
                            reason = "보상/콘텐츠 효과." if milestones_recent else "유저 참여도 자연 증가."
                        else:
                            reason = "매칭 대기 또는 보상 포화." if d["dau"] >= prev.get("dau", 0) else "DAU 감소에 따른 자연 감소."
                        insights.append(
                            f"⚔️ 배틀 {battle_prev} → {d['battles']}건({bt_pct:+.1f}%). {reason}")
            elif d["dau"] > 0:
                insights.append("⚔️ <b>배틀 0건</b> — 매칭 시스템 점검 필요.")

            # 1인당 활동량
            if d["dau"] > 0 and prev.get("dau", 0) > 0:
                actions_per_user = round((d["catches"] + d["battles"]) / d["dau"], 1)
                prev_actions = round((catch_prev + battle_prev) / max(prev.get("dau", 1), 1), 1)
                diff = round(actions_per_user - prev_actions, 1)
                if abs(diff) > 1:
                    insights.append(
                        f"👤 1인당 활동 {prev_actions} → {actions_per_user}회/일({diff:+.1f}). "
                        f"{'참여 밀도 ↑' if diff > 0 else '참여 밀도 ↓ — 콘텐츠 소진 또는 허들 존재'}.")

        # ── 4. BP 경제 분석 ──
        bp_earned = d.get("bp_earned", 0)
        bp_total_spent = d.get("bp_total_spent", 0)
        gacha_spent = d.get("gacha_bp_spent", 0)
        gacha_pulls = d.get("gacha_pulls", 0)
        bp_circulation = eco.get("bp_circulation", 0)
        bp_avg = eco.get("bp_avg", 0)
        bp_sources = d.get("bp_sources", {})
        bp_net = bp_earned - bp_total_spent

        source_labels = {
            "battle": "⚔️ 배틀", "ranked_battle": "🏟️ 랭크전", "catch": "🎯 포획",
            "tournament": "🏆 토너먼트", "mission": "📋 미션", "bet_win": "🎲 야차(승)",
            "daily_checkin": "💰 출석(!돈)", "gacha_refund": "🎰 뽑기환급",
            "gacha_jackpot": "💎 뽑기잭팟",
            "ranked_reward": "🏅 시즌보상", "admin": "🔧 관리자",
            "shop_masterball": "🔴 상점(마볼)", "shop_hyperball": "🔵 상점(하볼)",
            "shop_gacha_ticket": "🎫 상점(뽑기권)", "shop_arcade_speed": "⚡ 상점(속도)",
            "shop_arcade_extend": "⏱️ 상점(연장)",
            "bet_refund": "🎲 야차(환불)", "trade_refund": "🔄 교환(환불)",
        }

        # 뽑기 BP 소각을 bp_sources에 합산 (gacha_log 기반)
        if gacha_spent > 0:
            bp_total_spent += gacha_spent
            bp_net = bp_earned - bp_total_spent
            if "gacha_pull" not in bp_sources:
                bp_sources["gacha_pull"] = {"earned": 0, "spent": gacha_spent}
            else:
                bp_sources["gacha_pull"]["spent"] += gacha_spent
            source_labels["gacha_pull"] = "🎰 뽑기"

        # BP 소스별 카드 HTML 생성
        _bp_src_order = ["catch", "battle", "ranked_battle", "tournament", "daily_checkin",
                         "mission", "bet_win", "gacha_refund", "gacha_jackpot",
                         "ranked_reward", "admin"]
        _bp_src_cards = []
        for _src in _bp_src_order:
            if _src in bp_sources and bp_sources[_src]["earned"] > 0:
                _lbl = source_labels.get(_src, _src)
                _val = bp_sources[_src]["earned"]
                _bp_src_cards.append(
                    f'<div class="card"><div class="label">{_lbl}</div>'
                    f'<div class="value" style="font-size:18px;color:#4caf50">+{_val:,}</div></div>')
        # 나머지 소스 (위 목록에 없는 것)
        for _src, _v in sorted(bp_sources.items(), key=lambda x: x[1]["earned"], reverse=True):
            if _src not in _bp_src_order and _v["earned"] > 0:
                _lbl = source_labels.get(_src, _src)
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

        # 전일 BP 유통량 (스냅샷에서)
        prev_bp_circulation = prev.get("bp_circulation") if prev else None
        bp_circ_delta = bp_circulation - prev_bp_circulation if prev_bp_circulation is not None else None
        prev_bp_earned = prev.get("bp_earned", 0) if prev else 0

        # --- BP 경제 요약 ---
        insights.append(f"💰 <b>BP 경제:</b>")

        # 유통량 + 전일 대비
        circ_delta_str = ""
        if bp_circ_delta is not None:
            circ_pct = round(bp_circ_delta / max(prev_bp_circulation, 1) * 100, 1)
            circ_delta_str = f" ({bp_circ_delta:+,}, {circ_pct:+.1f}%)"
        insights.append(
            f"  └ 총 유통량 <b>{bp_circulation:,}</b>BP{circ_delta_str}, "
            f"보유자 평균 {bp_avg:,}BP")

        # 당일 생성/소각
        if bp_earned > 0 or bp_total_spent > 0:
            insights.append(
                f"  └ 당일 생성 <b>+{bp_earned:,}</b> / 소각 <b>-{bp_total_spent:,}</b> / "
                f"순변동 <b>{bp_net:+,}</b>BP")

            # 전일 대비 생성량 변화
            if prev_bp_earned > 0:
                earn_diff = bp_earned - prev_bp_earned
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
                insights.append(f"  └ 📈 <b>생성 상세:</b> {' / '.join(earn_parts[:6])}")
            if spend_parts:
                insights.append(f"  └ 📉 <b>소각 상세:</b> {' / '.join(spend_parts[:5])}")

            # 생성 비중 분석: 가장 큰 소스
            total_earned = sum(v["earned"] for v in bp_sources.values())
            if total_earned > 0:
                top_src = max(bp_sources.items(), key=lambda x: x[1]["earned"])
                top_pct = round(top_src[1]["earned"] / total_earned * 100, 1)
                top_label = source_labels.get(top_src[0], top_src[0])
                if top_pct > 60:
                    insights.append(
                        f"  └ ⚠️ <b>{top_label}</b>이 생성의 {top_pct}% 차지 — 소스 편중 주의")

        # 소각률 평가
        if bp_total_spent > 0:
            sink_ratio = round(bp_total_spent / max(bp_earned, 1) * 100, 1)
            if sink_ratio > 150:
                insights.append(
                    f"  └ 🔴 <b>소각률 {sink_ratio}%</b> (생성 대비) — 디플레이션 위험. "
                    f"유저 BP 고갈 → 활동 저하 우려.")
            elif sink_ratio > 100:
                insights.append(
                    f"  └ 🟡 소각률 {sink_ratio}% — 건전한 싱크 작동 중. 인플레 억제 ✓")
            else:
                insights.append(
                    f"  └ 🟢 소각률 {sink_ratio}% — 생성 우세. 추가 싱크 검토 가능.")

        # 1인당 BP 경제
        if d["dau"] > 0:
            bp_per_dau = round(bp_circulation / d["dau"], 0)
            earn_per_dau = round(bp_earned / d["dau"], 1) if bp_earned > 0 else 0
            spend_per_dau = round(bp_total_spent / d["dau"], 1) if bp_total_spent > 0 else 0
            insights.append(
                f"  └ 👤 DAU당 보유 {bp_per_dau:,.0f}BP, "
                f"생성 +{earn_per_dau:.0f}, 소각 -{spend_per_dau:.0f}")
            if bp_per_dau > 2000:
                insights.append(f"     └ ⚠️ 고인플레 구간. 추가 싱크 필요.")
            elif bp_per_dau < 300:
                insights.append(f"     └ ⚠️ BP 부족 우려. 획득 경로 확인.")

        # 뽑기 분석
        gacha_dist = d.get("gacha_distribution", {})
        if gacha_pulls > 0:
            avg_cost = gacha_spent // max(gacha_pulls, 1)
            gacha_per_dau = round(gacha_pulls / max(d["dau"], 1), 1)
            insights.append(
                f"🎰 <b>뽑기:</b> {gacha_pulls:,}회 ({gacha_spent:,}BP), "
                f"회당 {avg_cost}BP, DAU당 {gacha_per_dau:.1f}회")
            if gacha_dist:
                top_items = sorted(gacha_dist.items(), key=lambda x: x[1], reverse=True)[:3]
                dist_str = ", ".join(f"{k}({v}회)" for k, v in top_items)
                rare_items = {k: v for k, v in gacha_dist.items() if k in ("shiny_ticket", "shiny_egg", "bp_jackpot", "iv_reroll_one")}
                if rare_items:
                    rare_str = ", ".join(f"{k}({v})" for k, v in rare_items.items())
                    insights.append(f"  └ TOP: {dist_str} | 레어: {rare_str}")
                else:
                    insights.append(f"  └ TOP: {dist_str}")
        elif gacha_dist:
            insights.append(f"🎰 뽑기 {gacha_pulls}회 (뽑기 활동 없음)")

        insight_html = ""
        if insights:
            items = "".join(f'<li style="margin-bottom:6px;font-size:13px">{ins}</li>' for ins in insights)
            insight_html = f"""
<div class="section">
<div class="section-title">💡 인사이트</div>
<ul style="list-style:none;padding:0">{items}</ul>
</div>"""

        # ── 시간대별 활성 그래프 ──
        hourly = d.get("hourly", {})
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

        # ── Top 채널 ──
        top_html = ""
        if d["top_chats"]:
            items = ""
            for i, ch in enumerate(d["top_chats"], 1):
                title = ch.get("chat_title", "?")[:15]
                members = ch.get("member_count", 0)
                items += f'<li><span class="rank">{i}</span><span>{title}</span><span class="cnt">{ch["today_spawns"]}회 · {members}명</span></li>'
            top_html = f"""<div class="section">
<div class="section-title">📈 Top 채널 (스폰 기준)</div>
<ul class="channel-list">{items}</ul></div>"""

        # ── 유저 동향 섹션 (v2 핵심) ──
        # Top 활동 유저
        top_users_html = ""
        if top_users:
            items = ""
            medals = ["🥇", "🥈", "🥉"]
            for i, u in enumerate(top_users[:10]):
                medal = medals[i] if i < 3 else f"{i+1}."
                name = (u["display_name"] or "?")[:12]
                items += (
                    f'<div style="display:flex;justify-content:space-between;align-items:center;'
                    f'padding:6px 10px;background:{"#fff3e0" if i < 3 else "#fafafa"};'
                    f'border-radius:6px;margin-bottom:3px;font-size:12px">'
                    f'<span><b>{medal}</b> {name}</span>'
                    f'<span style="color:#666">🎯{u["catches"]} ⚔️{u["battles"]}({u["wins"]}승)</span>'
                    f'</div>'
                )
            top_users_html = f"""
<div class="section">
<div class="section-title">🏆 오늘의 Top 활동 유저</div>
{items}
</div>"""

        # 신규 유저 상세 + 유입 채널 분석
        new_users_html = ""
        if new_users_detail:
            # 채널별 유입 소스
            source_items = ""
            if new_user_sources:
                tracked_total = sum(s["cnt"] for s in new_user_sources)
                untracked = d.get("new_users", 0) - tracked_total
                for s in new_user_sources[:5]:
                    title = (s["chat_title"] or "?")[:15]
                    source_items += f'<div style="font-size:12px;padding:3px 0">📍 <b>{title}</b> — {s["cnt"]}명</div>'
                if untracked > 0:
                    source_items += f'<div style="font-size:12px;padding:3px 0;color:#888">📍 기타/미포획 — {untracked}명</div>'
            # Top 활동 신규 유저
            user_items = ""
            for u in new_users_detail[:5]:
                name = (u["display_name"] or "?")[:12]
                activity = []
                if u["catches"]:
                    activity.append(f"포획 {u['catches']}회")
                if u["battles"]:
                    activity.append(f"배틀 {u['battles']}판")
                act_str = ", ".join(activity) if activity else "활동 없음"
                user_items += f'<div style="font-size:12px;padding:3px 0;border-bottom:1px solid #f5f5f5">🆕 <b>{name}</b> — {act_str}</div>'
            new_users_html = f"""
<div class="section">
<div class="section-title">🆕 신규 가입 ({d['new_users']}명)</div>
{source_items}
{f'<div style="border-top:1px solid #eee;margin:6px 0"></div>' if source_items else ''}
{user_items}
</div>"""

        # 이탈 징후 유저
        churned_html = ""
        if churned_users:
            items = ""
            for u in churned_users[:8]:
                name = (u["display_name"] or "?")[:12]
                last = u["last_active_at"].strftime("%m/%d") if u.get("last_active_at") else "?"
                items += f'<div style="font-size:12px;padding:4px 0;border-bottom:1px solid #f5f5f5">⚠️ <b>{name}</b> — 최근접속 {last}, 주간포획 {u["week_catches"]}회</div>'
            churned_html = f"""
<div class="section">
<div class="section-title">📉 이탈 징후 (7일 활성 → 오늘 미접속)</div>
{items}
</div>"""

        # ── 이로치 포획 요약 (한 줄) ──
        shiny_html = ""
        if shiny_catches:
            total_shiny = sum(s["cnt"] for s in shiny_catches)
            top3 = " / ".join(
                f"{(s['display_name'] or '?')[:8]} {s['cnt']}마리"
                for s in shiny_catches[:3]
            )
            shiny_html = f"""
<div class="section">
<div class="section-title">✨ 이로치 포획 — 총 {total_shiny}마리</div>
<div style="font-size:12px;color:#666;padding:4px 0">🏅 {top3}</div>
</div>"""

        # ── 거래소 트렌드 ──
        market_html = ""
        if market_trends:
            items = ""
            for m in market_trends[:10]:
                shiny_mark = "✨" if m.get("is_shiny") else ""
                price_str = f"{m['price']:,} BP"
                items += (
                    f'<div style="font-size:12px;padding:3px 0;border-bottom:1px solid #f5f5f5">'
                    f'{shiny_mark}<b>{m["name_ko"]}</b> — {price_str} '
                    f'<span style="color:#888">({m.get("seller_name", "?")[:8]} → {m.get("buyer_name", "?")[:8]})</span></div>'
                )
            market_html = f"""
<div class="section">
<div class="section-title">🏪 거래소 ({d['market_sold']}건 거래, {d['market_new']}건 등록)</div>
{items}
</div>"""

        # ── 배틀 메타 ──
        meta_html = ""
        if battle_meta:
            items = ""
            for i, m in enumerate(battle_meta[:8]):
                bar_w = min(100, int(m["uses"] / max(battle_meta[0]["uses"], 1) * 100))
                wr = m.get("win_rate") or 0
                wr_color = "#4caf50" if wr >= 55 else "#ff9800" if wr >= 45 else "#e53935"
                items += (
                    f'<div style="display:flex;align-items:center;gap:6px;font-size:12px;margin-bottom:4px">'
                    f'<span style="min-width:70px"><b>{m["name_ko"]}</b></span>'
                    f'<div style="flex:1;background:#f5f5f5;border-radius:3px;height:14px;overflow:hidden">'
                    f'<div style="width:{bar_w}%;height:100%;background:#ffcdd2;border-radius:3px"></div></div>'
                    f'<span style="min-width:40px;text-align:right">{m["uses"]}회</span>'
                    f'<span style="min-width:45px;text-align:right;color:{wr_color};font-weight:600">{wr}%</span>'
                    f'</div>'
                )
            meta_html = f"""
<div class="section">
<div class="section-title">⚔️ 배틀 메타 (사용횟수 / 승률)</div>
{items}
</div>"""

        # ── 구독 변동 ──
        sub_html = ""
        sub_new = sub_changes.get("new", [])
        sub_expired = sub_changes.get("expired", [])
        if sub_new or sub_expired:
            items = ""
            for s in sub_new:
                items += f'<div style="font-size:12px;padding:3px 0">🟢 <b>{s["display_name"][:12]}</b> 신규 구독 ({s["tier"]})</div>'
            for s in sub_expired:
                items += f'<div style="font-size:12px;padding:3px 0">🔴 <b>{s["display_name"][:12]}</b> 구독 만료 ({s["tier"]})</div>'
            sub_html = f"""
<div class="section">
<div class="section-title">💎 구독 변동 (활성 {d['sub_active']}명, 매출 ${d['sub_revenue_today']:.1f})</div>
{items}
</div>"""

        # ── 채팅방 건강도 ──
        chat_health_html = ""
        if chat_health:
            items = ""
            for ch in chat_health[:10]:
                title = (ch.get("chat_title") or "?")[:15]
                t_spawns = ch["today_spawns"]
                y_spawns = ch["yesterday_spawns"]
                if y_spawns > 0:
                    diff_pct = round((t_spawns - y_spawns) / y_spawns * 100)
                    trend = f'<span style="color:{"#4caf50" if diff_pct >= 0 else "#e53935"};font-weight:600">{"▲" if diff_pct >= 0 else "▼"}{abs(diff_pct)}%</span>'
                else:
                    trend = '<span style="color:#888">NEW</span>'
                items += (
                    f'<div style="display:flex;justify-content:space-between;font-size:12px;padding:4px 0;border-bottom:1px solid #f5f5f5">'
                    f'<span>{title} ({ch.get("member_count", 0)}명)</span>'
                    f'<span>{y_spawns}→{t_spawns} {trend}</span></div>'
                )
            chat_health_html = f"""
<div class="section">
<div class="section-title">💬 채팅방 건강도 (어제→오늘 스폰)</div>
{items}
</div>"""

        # ── 출석 체크 ──
        checkin_html = ""
        if checkin_stats.get("checkins", 0) > 0:
            checkin_cnt = checkin_stats["checkins"]
            checkin_rate = round(checkin_cnt / max(d["dau"], 1) * 100, 1)
            checkin_html = f'<div class="card"><div class="label">!돈 출석</div><div class="value">{checkin_cnt}명</div><div class="sub">DAU 대비 {checkin_rate}%</div></div>'

        body = f"""
{delta_html}

<div class="section">
<div class="section-title">👥 유저 · 리텐션</div>
<div class="grid grid-4">
<div class="card"><div class="label">DAU</div><div class="value accent">{d['dau']}</div></div>
<div class="card"><div class="label">핵심DAU</div><div class="value">{_core_dau}</div><div class="sub">{_core_dau_pct}%</div></div>
<div class="card"><div class="label">신규</div><div class="value">{d['new_users']}</div></div>
<div class="card"><div class="label">총유저</div><div class="value">{d['total_users']}</div></div>
</div>
<div class="grid grid-4" style="margin-top:4px">
<div class="card"><div class="label">D+1 리텐션</div><div class="value accent">{f'{d1_ret}%' if d1_ret is not None else '-'}</div></div>
<div class="card"><div class="label">D+7 리텐션</div><div class="value" style="color:#ff9800">{f'{d7_ret}%' if d7_ret is not None else '-'}</div></div>
<div class="card"><div class="label">💰출석</div><div class="value">{_checkin_users}</div></div>
<div class="card"><div class="label">💕사랑해</div><div class="value">{_love_users}</div></div>
</div>
</div>

<div class="section">
<div class="section-title">🎯 포획 · ⚔️ 배틀</div>
<div class="grid grid-4">
<div class="card"><div class="label">스폰</div><div class="value">{d['spawns']:,}</div></div>
<div class="card"><div class="label">포획</div><div class="value accent">{d['catches']:,}</div><div class="sub">{catch_rate}%</div></div>
<div class="card"><div class="label">✨이로치</div><div class="value" style="color:#ff9800">{d['shiny_caught']}</div></div>
<div class="card"><div class="label">🔴마볼</div><div class="value">{d['mb_used']}</div></div>
</div>
<div class="grid grid-4" style="margin-top:4px">
<div class="card"><div class="label">배틀</div><div class="value">{d['battles']}</div></div>
<div class="card"><div class="label">랭크전</div><div class="value">{d['ranked_battles']}</div></div>
<div class="card"><div class="label">뽑기</div><div class="value">{gacha_pulls:,}</div><div class="sub">-{gacha_spent:,}BP</div></div>
<div class="card"><div class="label">🏕️방문</div><div class="value">{_visit_users}</div></div>
</div>
</div>

{top_users_html}
{shiny_html}
{meta_html}

<div class="section">
<div class="section-title">💰 BP 경제</div>
<div class="grid grid-3">
<div class="card"><div class="label">생성</div><div class="value" style="color:#4caf50">+{bp_earned:,}</div></div>
<div class="card"><div class="label">소각</div><div class="value accent">-{bp_total_spent:,}</div></div>
<div class="card"><div class="label">순변동</div><div class="value" style="color:{'#4caf50' if bp_net >= 0 else '#e53935'}">{bp_net:+,}</div></div>
</div>
{bp_source_cards_html}
<div class="grid grid-4" style="margin-top:4px">
<div class="card"><div class="label">유통량</div><div class="value">{bp_circulation:,}</div>{_delta_badge(bp_circulation, prev_bp_circulation) if prev_bp_circulation else ''}</div>
<div class="card"><div class="label">평균</div><div class="value">{bp_avg:,}</div></div>
<div class="card"><div class="label">거래소</div><div class="value">{d['market_sold']}/{d['market_new']}</div><div class="sub">매매/등록</div></div>
<div class="card"><div class="label">구독$</div><div class="value accent">${d['sub_revenue_today']:.1f}</div><div class="sub">{d['sub_active']}명</div></div>
</div>
<div class="grid grid-4" style="margin-top:4px">
<div class="card"><div class="label">🔴마볼</div><div class="value">{eco['master_balls_circulation']}</div></div>
<div class="card"><div class="label">🔵하볼</div><div class="value">{eco['hyper_balls_circulation']}</div></div>
<div class="card" style="grid-column:span 2"><div class="label">뽑기 소각</div><div class="value">{gacha_spent:,}BP</div></div>
</div>
</div>

{new_users_html}
{churned_html}
{market_html}
{sub_html}
{chat_health_html}
{hourly_html}
{abuse_html}
{patch_html}
{gen4_html}
{insight_html}"""

        date_str = f"{d['date']} ({d['weekday']})"
        html = _kpi_html_template("📊 일일 KPI 리포트", body, date_str)
        filename = f"kpi_daily_{d['date'].replace('-', '')}.html"

        for admin_id in config.ADMIN_IDS:
            try:
                buf = io.BytesIO(html.encode("utf-8"))
                buf.name = filename
                await context.bot.send_document(
                    chat_id=admin_id, document=buf,
                    caption=f"📊 일일 KPI 리포트 — {date_str}",
                )
            except Exception:
                pass
        logger.info("Daily KPI report (HTML) sent to admins.")
    except Exception as e:
        import traceback
        logger.error(f"Daily KPI report error: {e}\n{traceback.format_exc()}")


async def _send_weekly_kpi_report(context):
    """매주 월요일 00:01 KST: 주간 KPI 리포트를 HTML 파일로 관리자 DM 발송."""
    import io
    now = config.get_kst_now()
    if now.weekday() != 0:
        return
    try:
        w = await kpi_queries.kpi_weekly_snapshot()

        dau_hist = w.get("dau_history", [])
        weekdays = ["월", "화", "수", "목", "금", "토", "일"]
        avg_dau = round(sum(h.get("dau", 0) for h in dau_hist) / max(len(dau_hist), 1), 1)
        max_dau = max((h.get("dau", 0) for h in dau_hist), default=1) or 1

        # DAU bar chart HTML
        bars = ""
        for i, h in enumerate(dau_hist):
            dau = h.get("dau", 0)
            pct = round(dau / max_dau * 100)
            day = weekdays[i % 7]
            bars += f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px"><span style="min-width:20px;font-size:12px;color:#888">{day}</span><div style="background:linear-gradient(90deg,#e53935,#ff6f61);height:22px;border-radius:4px;width:{pct}%;min-width:2px"></div><span style="font-size:13px;font-weight:600">{dau}</span></div>'

        body = f"""
<div class="section">
<div class="section-title">📈 DAU 트렌드</div>
{bars}
<div class="card" style="margin-top:10px"><div class="label">주간 평균 DAU</div><div class="value accent">{avg_dau}</div></div>
</div>

<div class="section">
<div class="section-title">👥 유저</div>
<div class="grid">
<div class="card"><div class="label">WAU (주간 활성)</div><div class="value accent">{w['wau']}</div></div>
<div class="card"><div class="label">신규가입</div><div class="value">{w['new_users']}</div></div>
</div></div>

<div class="section">
<div class="section-title">🎯 스폰 / 포획</div>
<div class="grid">
<div class="card"><div class="label">총 스폰</div><div class="value">{w['spawns']:,}</div></div>
<div class="card"><div class="label">포획</div><div class="value accent">{w['catches']:,}</div><div class="sub">포획률 {w['catch_rate']}%</div></div>
<div class="card"><div class="label">이로치</div><div class="value" style="color:#ff9800">{w['shiny_caught']}</div></div>
<div class="card"><div class="label">마볼 소비</div><div class="value">{w['mb_used']}</div></div>
</div></div>

<div class="section">
<div class="section-title">⚔️ 배틀</div>
<div class="grid">
<div class="card"><div class="label">총 배틀</div><div class="value">{w['battles']}</div></div>
<div class="card"><div class="label">BP 획득</div><div class="value">+{w['bp_earned']:,}</div></div>
<div class="card"><div class="label">BP 뽑기소비</div><div class="value" style="color:#e53935">-{w['gacha_bp_spent']:,}</div></div>
<div class="card"><div class="label">뽑기 횟수</div><div class="value">{w['gacha_pulls']:,}</div></div>
</div></div>

{_bp_daily_chart(w.get('bp_daily', []))}

<div class="section">
<div class="section-title">💰 경제</div>
<div class="grid">
<div class="card"><div class="label">거래소 체결</div><div class="value">{w['market_sold']}</div></div>
<div class="card"><div class="label">구독 매출</div><div class="value accent">${w['sub_revenue']:.1f}</div></div>
</div></div>"""

        # 어뷰저 의심 유저 (주간)
        abuse_weekly = await _build_abuse_report_section("7 days")
        if abuse_weekly:
            body += abuse_weekly

        period = w["period"]
        html = _kpi_html_template("📊 주간 KPI 리포트", body, period)
        filename = f"kpi_weekly_{now.strftime('%Y%m%d')}.html"

        for admin_id in config.ADMIN_IDS:
            try:
                buf = io.BytesIO(html.encode("utf-8"))
                buf.name = filename
                await context.bot.send_document(
                    chat_id=admin_id, document=buf,
                    caption=f"📊 주간 KPI 리포트 — {period}",
                )
            except Exception:
                pass
        logger.info("Weekly KPI report (HTML) sent to admins.")
    except Exception as e:
        logger.error(f"Weekly KPI report error: {e}")

