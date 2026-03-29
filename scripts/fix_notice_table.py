"""One-off script: replace markdown table in v2.2 notice with HTML table."""
import asyncio
import asyncpg
import os

HTML_TABLE = """<table style="width:100%;border-collapse:collapse;font-size:13px;margin:10px 0">
<thead>
<tr style="background:#e8f5e9">
<th style="padding:8px 10px;border:1px solid #ddd;text-align:left;font-weight:700">#</th>
<th style="padding:8px 10px;border:1px solid #ddd;text-align:left;font-weight:700">포켓몬</th>
<th style="padding:8px 10px;border:1px solid #ddd;text-align:left;font-weight:700">타입</th>
<th style="padding:8px 10px;border:1px solid #ddd;text-align:left;font-weight:700">변경 전</th>
<th style="padding:8px 10px;border:1px solid #ddd;text-align:left;font-weight:700">변경 후</th>
</tr>
</thead>
<tbody>
<tr><td style="padding:6px 10px;border:1px solid #ddd">49</td><td style="padding:6px 10px;border:1px solid #ddd">도나리</td><td style="padding:6px 10px;border:1px solid #ddd">벌레/독</td><td style="padding:6px 10px;border:1px solid #ddd;color:#e74c3c">사이코키네시스(에스퍼)</td><td style="padding:6px 10px;border:1px solid #ddd;color:#2ecc71;font-weight:600">오물폭탄(독)</td></tr>
<tr style="background:#fafafa"><td style="padding:6px 10px;border:1px solid #ddd">108</td><td style="padding:6px 10px;border:1px solid #ddd">내루미</td><td style="padding:6px 10px;border:1px solid #ddd">노말</td><td style="padding:6px 10px;border:1px solid #ddd;color:#e74c3c">핥기(고스트)</td><td style="padding:6px 10px;border:1px solid #ddd;color:#2ecc71;font-weight:600">하이퍼빔(노말)</td></tr>
<tr><td style="padding:6px 10px;border:1px solid #ddd">117</td><td style="padding:6px 10px;border:1px solid #ddd">시드라</td><td style="padding:6px 10px;border:1px solid #ddd">물</td><td style="padding:6px 10px;border:1px solid #ddd;color:#e74c3c">용의파동(드래곤)</td><td style="padding:6px 10px;border:1px solid #ddd;color:#2ecc71;font-weight:600">하이드로펌프(물)</td></tr>
<tr style="background:#fafafa"><td style="padding:6px 10px;border:1px solid #ddd">159</td><td style="padding:6px 10px;border:1px solid #ddd">엘리게이</td><td style="padding:6px 10px;border:1px solid #ddd">물</td><td style="padding:6px 10px;border:1px solid #ddd;color:#e74c3c">물어뜯기(악)</td><td style="padding:6px 10px;border:1px solid #ddd;color:#2ecc71;font-weight:600">아쿠아테일(물)</td></tr>
<tr><td style="padding:6px 10px;border:1px solid #ddd">209</td><td style="padding:6px 10px;border:1px solid #ddd">블루</td><td style="padding:6px 10px;border:1px solid #ddd">페어리</td><td style="padding:6px 10px;border:1px solid #ddd;color:#e74c3c">물어뜯기(악)</td><td style="padding:6px 10px;border:1px solid #ddd;color:#2ecc71;font-weight:600">마법빛나(페어리)</td></tr>
<tr style="background:#fafafa"><td style="padding:6px 10px;border:1px solid #ddd">217</td><td style="padding:6px 10px;border:1px solid #ddd">링곰</td><td style="padding:6px 10px;border:1px solid #ddd">노말</td><td style="padding:6px 10px;border:1px solid #ddd;color:#e74c3c">크로스촙(격투)</td><td style="padding:6px 10px;border:1px solid #ddd;color:#2ecc71;font-weight:600">기가임팩트(노말)</td></tr>
<tr><td style="padding:6px 10px;border:1px solid #ddd">234</td><td style="padding:6px 10px;border:1px solid #ddd">노라키</td><td style="padding:6px 10px;border:1px solid #ddd">노말</td><td style="padding:6px 10px;border:1px solid #ddd;color:#e74c3c">사이코키네시스(에스퍼)</td><td style="padding:6px 10px;border:1px solid #ddd;color:#2ecc71;font-weight:600">박치기(노말)</td></tr>
<tr style="background:#fafafa"><td style="padding:6px 10px;border:1px solid #ddd">246</td><td style="padding:6px 10px;border:1px solid #ddd">애버라스</td><td style="padding:6px 10px;border:1px solid #ddd">바위/땅</td><td style="padding:6px 10px;border:1px solid #ddd;color:#e74c3c">물어뜯기(악)</td><td style="padding:6px 10px;border:1px solid #ddd;color:#2ecc71;font-weight:600">암석봉인(바위)</td></tr>
<tr><td style="padding:6px 10px;border:1px solid #ddd">328</td><td style="padding:6px 10px;border:1px solid #ddd">톱치</td><td style="padding:6px 10px;border:1px solid #ddd">땅</td><td style="padding:6px 10px;border:1px solid #ddd;color:#e74c3c">물어뜯기(악)</td><td style="padding:6px 10px;border:1px solid #ddd;color:#2ecc71;font-weight:600">대지의힘(땅)</td></tr>
<tr style="background:#fafafa"><td style="padding:6px 10px;border:1px solid #ddd">352</td><td style="padding:6px 10px;border:1px solid #ddd">켈리몬</td><td style="padding:6px 10px;border:1px solid #ddd">노말</td><td style="padding:6px 10px;border:1px solid #ddd;color:#e74c3c">섀도클로(고스트)</td><td style="padding:6px 10px;border:1px solid #ddd;color:#2ecc71;font-weight:600">몸통박치기(노말)</td></tr>
<tr><td style="padding:6px 10px;border:1px solid #ddd">367</td><td style="padding:6px 10px;border:1px solid #ddd">헌테일</td><td style="padding:6px 10px;border:1px solid #ddd">물</td><td style="padding:6px 10px;border:1px solid #ddd;color:#e74c3c">깨물어부수기(악)</td><td style="padding:6px 10px;border:1px solid #ddd;color:#2ecc71;font-weight:600">아쿠아테일(물)</td></tr>
<tr style="background:#fafafa"><td style="padding:6px 10px;border:1px solid #ddd">368</td><td style="padding:6px 10px;border:1px solid #ddd">분홍장이</td><td style="padding:6px 10px;border:1px solid #ddd">물</td><td style="padding:6px 10px;border:1px solid #ddd;color:#e74c3c">사이코키네시스(에스퍼)</td><td style="padding:6px 10px;border:1px solid #ddd;color:#2ecc71;font-weight:600">하이드로펌프(물)</td></tr>
<tr><td style="padding:6px 10px;border:1px solid #ddd">370</td><td style="padding:6px 10px;border:1px solid #ddd">사랑동이</td><td style="padding:6px 10px;border:1px solid #ddd">물</td><td style="padding:6px 10px;border:1px solid #ddd;color:#e74c3c">달콤한키스(페어리)</td><td style="padding:6px 10px;border:1px solid #ddd;color:#2ecc71;font-weight:600">물대포(물)</td></tr>
<tr style="background:#fafafa"><td style="padding:6px 10px;border:1px solid #ddd">374</td><td style="padding:6px 10px;border:1px solid #ddd">메탕</td><td style="padding:6px 10px;border:1px solid #ddd">강철/에스퍼</td><td style="padding:6px 10px;border:1px solid #ddd;color:#e74c3c">박치기(노말)</td><td style="padding:6px 10px;border:1px solid #ddd;color:#2ecc71;font-weight:600">코멧펀치(강철)</td></tr>
</tbody>
</table>"""


async def main():
    conn = await asyncpg.connect(os.environ["DATABASE_URL"], statement_cache_size=0)

    row = await conn.fetchrow("SELECT content FROM board_posts WHERE id=13")
    content = row[0]

    # Find and replace the markdown table section
    # The markdown table starts with "| 포켓몬" and ends after "| 메탕 ..." line
    lines = content.split("\n")
    new_lines = []
    in_table = False
    for line in lines:
        if line.startswith("| 포켓몬") or line.startswith("|--------"):
            if not in_table:
                in_table = True
                new_lines.append(HTML_TABLE)
            continue
        if in_table and line.startswith("| "):
            continue  # skip markdown table rows
        in_table = False
        new_lines.append(line)

    new_content = "\n".join(new_lines)

    await conn.execute("UPDATE board_posts SET content=$1 WHERE id=13", new_content)
    print("OK! Updated.")
    print("Has <table>:", "<table" in new_content)
    print("Has |-----:", "|-----" in new_content)
    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
