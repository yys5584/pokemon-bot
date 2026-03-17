"""Send newbie spawn patch note DM preview to admin."""
import requests

BOT_TOKEN = "8578621482:AAETKN-hwDsiCLJ4Yk3SD45Rtrd3-dQtqYk"
ADMIN_ID = 1832746512


text = (
    "🌱 <b>뉴비 스폰 시스템 도입!</b>\n"
    "\n"
    "새로운 트레이너에게 기회를!\n"
    "아케이드 스폰에 뉴비 전용 스폰이 추가됩니다.\n"
    "\n"
    "🎮 <b>뉴비 스폰이란?</b>\n"
    "  아케이드 스폰 <b>5회 중 1회</b> 🌱 표시와 함께 등장\n"
    "  도감 수가 적은 트레이너에게 <b>포획 우선권</b> 부여\n"
    "\n"
    "📖 <b>우선순위</b>\n"
    "  🥇 도감 100개 미만 — 포획 보장 + 최우선\n"
    "  🥈 도감 200개 미만 — 포획 보장 + 차순위\n"
    "  🥉 도감 300개 미만 — 포획 보장 + 3순위\n"
    "  💀 도감 300개 이상 — 일반 확률, 후순위\n"
    "\n"
    "⚫ <b>마스터볼 / 하이퍼볼</b>\n"
    "  뉴비 스폰에서는 효과 없음 (자동 환불)\n"
    "  일반 포획(ㅊ)으로 자동 전환\n"
    "\n"
    "✨ <b>이로치 확률</b>\n"
    "  뉴비 스폰 이로치 확률 <b>~3.3%</b> (1/30)\n"
    "\n"
    "━━━━━━━━━━━━━━━\n"
    "\n"
    "💬 <b>문유의 한마디</b>\n"
    "<i>\"고인물만 잡아가는 아케이드는 그만!\n"
    "이제 뉴비도 포켓몬을 잡을 수 있습니다.\n"
    "마볼 던져도 도감 10개인 뉴비한테 밀려요 ㅋㅋ\n"
    "열심히 도감 채우세요 여러분 🫡\"</i>"
)

url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
resp = requests.post(url, data={
    "chat_id": str(ADMIN_ID),
    "text": text,
    "parse_mode": "HTML",
})
print(f"Status: {resp.status_code}")
result = resp.json()
print(f"OK: {result.get('ok', False)}")
if not result.get("ok"):
    print(result)
