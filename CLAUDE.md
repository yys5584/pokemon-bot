# TGPoke Bot

Telegram 포켓몬 수집/배틀/거래 봇. python-telegram-bot 기반, PostgreSQL, Oracle Cloud VM 운영.

## Repo Map

```
main.py                 # 봇 엔트리포인트 (핸들러 등록, 스케줄러)
config.py               # 모든 설정값, 커스텀 이모지 ID, 칭호 정의, 코스트
handlers/               # 텔레그램 메시지/콜백 핸들러
  admin.py              #   관리자 명령 (강제스폰, 대회시작 등)
  battle.py             #   배틀, 상점, 팀 표시, 랭크전
  dm_pokedex.py         #   상태창, 도감, 칭호, 팀등록
  dm_market.py          #   거래소 DM
  dm_fusion.py          #   합성 DM
  dm_trade.py           #   교환 DM
  group.py              #   그룹 채팅 명령
  tournament.py         #   대회 참가 (ㄷ)
  tutorial.py           #   튜토리얼
services/               # 비즈니스 로직 (핸들러에서 분리)
  battle_service.py     #   배틀 엔진 (_resolve_battle, _hp_bar)
  spawn_service.py      #   스폰/포획
  tournament_service.py #   토너먼트 진행
  ranked_service.py     #   랭크전 매칭
  market_service.py     #   거래소
  fusion_service.py     #   합성
database/               # PostgreSQL 쿼리 레이어
  queries.py            #   메인 쿼리
  battle_queries.py     #   배틀 관련 쿼리
  ranked_queries.py     #   랭크전 쿼리
  schema.py             #   테이블 생성/마이그레이션
  connection.py         #   DB 커넥션 풀
models/                 # 포켓몬 데이터 정의 (스탯, 스킬, 타입)
utils/                  # 유틸리티 (이모지, 배틀 계산, 카드 이미지)
dashboard/              # 웹 대시보드 (Flask, tgpoke.com)
  server.py             #   메인 서버
  templates/index.html  #   SPA 프론트엔드
assets/                 # 포켓몬 이미지, 스티커, 이모지 원본
scripts/                # 일회성 스크립트 (패치노트, 마이그레이션)
docs/                   # 설계 문서
```

## Rules

### 필수
- 모든 시간은 **KST (UTC+9)** 기준
- 커스텀 이모지 사용 시 반드시 `parse_mode="HTML"`
- 커스텀 이모지 형식: `<tg-emoji emoji-id="ID">fallback</tg-emoji>`
- InlineKeyboardButton 라벨, query.answer() 팝업은 커스텀 이모지 **불가** → 기본 이모지 사용
- DB 스키마 변경 시 `database/schema.py`에 마이그레이션 추가

### 금지
- **배포/푸시/머지를 사용자 확인 없이 절대 하지 말 것**
- **봇 재시작을 사용자 확인 없이 절대 하지 말 것**
- `config.py`의 이모지 ID를 임의로 변경하지 말 것

### 컨벤션
- 언어: 한국어
- 브랜치: `dev` (개발/배포), `main` (안정)
- 커밋 메시지: 한국어 또는 영어, `feat:/fix:/chore:` 접두사

## Infra

| 항목 | 값 |
|------|-----|
| VM | 158.180.93.94 (ubuntu) |
| SSH 키 | 회사: `./oracle_vm`, 집: `~/.ssh/oracle_vm` |
| 봇 재시작 | `sudo systemctl restart pokemon-bot` |
| 로그 | `sudo journalctl -u pokemon-bot -f` |
| 대시보드 | https://tgpoke.com (port 8080, Cloudflare tunnel) |
| GitHub | https://github.com/yys5584/pokemon-bot |

## Commands

```bash
# 프리뷰 대시보드 (로컬)
python dashboard/run_preview.py    # port 8090

# 배포
ssh -i oracle_vm ubuntu@158.180.93.94
cd ~/pokemon-bot && git pull origin dev && sudo systemctl restart pokemon-bot
```
