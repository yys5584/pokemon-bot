import asyncio, os, asyncpg
from dotenv import load_dotenv
load_dotenv()

CONTENT = """🔧 v2.6.1 마이너 패치 (2026-03-15)

✅ 버그 수정
• 이로치 전환 시 오류 발생하던 문제 수정
• 랭크전 일일 상한(20판)이 KST 0시 기준으로 리셋되지 않던 문제 수정
• 상태창 키보드에서 프리미엄 버튼 누락 수정
• 구독 결제 자동 확인이 작동하지 않던 문제 수정

📊 대시보드 개선
• 배틀 랭킹: BP/승률/승수/연승 각 기준별 Top 100 합산 표시
• 데이터 갱신 주기 변경 + 갱신 주기 안내 표시

🗄️ 인프라
• DB 서버 안정성 개선"""

async def main():
    conn = await asyncpg.connect(os.environ["DATABASE_URL"], statement_cache_size=0)
    row = await conn.fetchrow(
        "INSERT INTO board_posts (board_type, user_id, display_name, tag, title, content) "
        "VALUES ($1, $2, $3, $4, $5, $6) RETURNING id",
        "notice", 1832746512, "TG포켓", "패치",
        "v2.6.1 마이너 패치", CONTENT
    )
    print(f"OK - post id: {row['id']}")
    await conn.close()

asyncio.run(main())
